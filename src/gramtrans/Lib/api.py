"""UI ↔ engine surface (T058, contracts/module-ui.md).

The single entry point the PyQt UI calls into. Five functions:

- `initialize_run(host_handle)` → builds a `RunContextStub` from the
  FlexTools host's open project.
- `list_target_candidates(stub)` → enumerates available FLEx projects (per
  research.md R5 filesystem scan).
- `bind_target(stub, choice)` → opens the target for write, refuses on
  lock / same-as-source, returns a finalized `RunContext` (FR-019, FR-020).
- `compute_preview(context, selection, ws_mapping)` → two-stage call:
  asks for a WS mapping when `ws_mapping is None`, otherwise returns a
  `RunPlan`. Never mutates target.
- `execute_move(context, plan)` → executes the plan; returns a `RunReport`.

The UI layer (`Lib/ui/`) MUST go through THIS module only (per
contracts/module-ui.md) — no raw flexicon imports in UI code.
"""
from __future__ import annotations

import enum
import logging
import os
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

if __package__:
    from .models import (
        CreateDefinitionAction,
        GrammarCategory,
        RunContext,
        RunMode,
        RunPlan,
        RunReport,
        Selection,
        WSKind,
        WSMapping,
    )
    from .preview import build_run_plan
    from .ws_mapping import WSMappingIncomplete, is_complete, required_ws_set
    from .debuglog import enable_from_env as _enable_debug_logging
else:
    from models import (  # type: ignore
        CreateDefinitionAction,
        GrammarCategory,
        RunContext,
        RunMode,
        RunPlan,
        RunReport,
        Selection,
        WSKind,
        WSMapping,
    )
    from preview import build_run_plan  # type: ignore
    from ws_mapping import WSMappingIncomplete, is_complete, required_ws_set  # type: ignore
    from debuglog import enable_from_env as _enable_debug_logging  # type: ignore

_log = logging.getLogger(__name__)

# Anti-deadlock diagnostics for LCM calls that can block cross-process.
#
# FLExProject.CloseProject() "saves pending changes and disposes the LCM object"
# (releasing the file lock). When the target is co-held by another process (a
# second FLExTools/MCP session or the FLEx GUI), the dispose step
# (SharedXMLBackendProvider.ShutdownInternal takes the commit-log mutex with NO
# timeout) can block INDEFINITELY -- the deadlock that froze coverage_report.py
# mid-run on the custom-field schema-write handle. A co-holder is NOT reliably
# detectable up front: co-open succeeds and the Palaso FileLock records only
# one owner (probe-results.md op 009).
#
# CRITICAL THREAD-AFFINITY CONSTRAINT (learned the hard way): LCM calls that
# raise events (Save, CloseProject) MUST run on the thread that opened the
# project. flexicon creates the LCM ThreadHelper on the opening thread, and
# event handlers marshal to it via ISynchronizeInvoke.Invoke; a pump-less
# Python host never services invokes queued from another thread, so running
# Save/Close on a watchdog thread deadlocks LCM itself (observed live: a
# post-transfer Save with 169 gathered changes wedged on a daemon thread
# while a schema-only Save, which gathers nothing and raises nothing,
# sailed through). So we do NOT bound these calls by running them off-thread.
# Instead a passive WATCHER thread labels a hang in the log/console after
# the deadline, converting a mystery freeze into an actionable diagnosis
# while the call runs on the correct thread.
_SCHEMA_CLOSE_TIMEOUT_S = float(
    os.environ.get("GRAMTRANS_SCHEMA_CLOSE_TIMEOUT", "90")
)


def _watched_call(fn, timeout_s: float, what: str, diagnose=None):
    """Run ``fn()`` ON THIS THREAD with a passive hang-labeling watcher.

    LCM thread affinity forbids moving the call to a watchdog thread (see the
    module comment above). If ``fn`` has not returned within ``timeout_s``
    seconds, a daemon watcher emits a WARNING naming the operation and the
    likely cause (a co-holder of the target project) -- it cannot abort the
    call (a wedged .NET call cannot be safely interrupted from Python), but
    the operator sees exactly what is stuck and why instead of a silent
    freeze. Exceptions from ``fn`` propagate unchanged.

    ``diagnose``: optional zero-arg callable returning extra diagnostic text
    for the timeout warning (run on the watcher thread; exceptions swallowed).
    """
    done = threading.Event()

    def _watch() -> None:
        if not done.wait(timeout_s):
            msg = (
                f"{what} has not completed after {timeout_s:g}s -- the target "
                f"is almost certainly open in another process (a second "
                f"FLExTools/MCP session or the FLEx GUI). Close every other "
                f"holder of the project; if this process stays stuck, kill it "
                f"and re-run single-owner. (Deadline via the "
                f"GRAMTRANS_SCHEMA_CLOSE_TIMEOUT env var.)"
            )
            if diagnose is not None:
                try:
                    msg += f"\n[DIAG] {diagnose()}"
                except Exception as exc:  # noqa: BLE001 -- diagnostics only
                    msg += f"\n[DIAG] unavailable: {exc!r}"
            _log.warning("%s", msg)
            print(f"[WARN] {msg}", flush=True)

    w = threading.Thread(
        target=_watch, name=f"gramtrans-watch-{what}", daemon=True
    )
    w.start()
    try:
        return fn()
    finally:
        done.set()


def _close_project_watchdog(proj, timeout_s: float, what: str) -> None:
    """Call ``proj.CloseProject()`` on this thread with a hang-labeling watcher."""
    _watched_call(proj.CloseProject, timeout_s, f"CloseProject() for {what}")


def _persist_without_close(proj, what: str) -> None:
    """Persist all pending changes -- INCLUDING custom-field schema -- to disk
    without disposing the LCM cache. This is FLEx's own persist path: custom
    fields ride on every normal commit (BackendProvider.HaveAnythingToCommit
    pulls the full list from the metadata cache; XMLBackendProvider.
    WriteCommitWork writes the <AdditionalFields> element), so no
    CloseProject() is needed to make a schema write durable.

    flexicon's non-undoable open (the mode every GramTrans handle uses) holds
    an ambient NonUndoableTask from OpenProject onward, and
    UnitOfWorkService.Save() throws "Commit at wrong place" (and rolls back!)
    while any task is open. So the persist step is the same triplet
    CloseProject() runs minus the deadlock-prone Dispose():
    EndNonUndoableTask -> IUndoStackManager.Save -> BeginNonUndoableTask
    (restoring the ambient-task invariant CloseProject expects later).

    Everything runs on the CALLER'S thread (LCM thread affinity: event
    handlers raised during Save marshal to the opening thread via
    ThreadHelper.Invoke -- see _watched_call); the watcher only labels a
    hang, it never moves the call off-thread.
    """
    from SIL.LCModel import IUndoStackManager  # lazy -- unavailable in unit tests

    mca = proj.project.MainCacheAccessor
    usm = proj.ObjectRepository(IUndoStackManager)
    _log.debug(
        "_persist_without_close: End/Save/Begin checkpoint for %s "
        "(handle id=%s)", what, id(proj),
    )
    def _diagnose_backend() -> str:
        """Reflect the XML backend's private state (watcher-thread safe: field
        reads only, no LCM calls that marshal). Names the wedge when Save
        blocks: a stale-mtime mismatch means the commit consumer bailed into
        ReportProblem's UI marshal, which a pump-less host never services."""
        from System.IO import File as DotNetFile  # noqa: PLC0415
        from SIL.LCModel.Utils import ReflectionHelper  # noqa: PLC0415

        parts = []
        bep = ReflectionHelper.GetField(usm, "m_dataStorer")
        parts.append(f"backend={bep.GetType().Name}")
        try:
            recorded = ReflectionHelper.GetField(bep, "m_lastWriteTime")
            path = str(proj.project.ProjectId.Path)
            current = DotNetFile.GetLastWriteTimeUtc(path)
            parts.append(f"m_lastWriteTime={recorded.ToString('o')}")
            parts.append(f"fwdata_mtime_utc={current.ToString('o')}")
            parts.append(f"mtime_match={recorded.Equals(current)}")
        except Exception as exc:  # noqa: BLE001
            parts.append(f"mtime_reflect_failed={exc!r}")
        try:
            ct = ReflectionHelper.GetProperty(bep, "CommitThread")
            if ct is None:
                parts.append("CommitThread=None")
            else:
                parts.append(f"CommitThread.m_isIdle={ReflectionHelper.GetField(ct, 'm_isIdle')}")
        except Exception as exc:  # noqa: BLE001
            parts.append(f"commit_thread_reflect_failed={exc!r}")
        return " ".join(str(p) for p in parts)

    mca.EndNonUndoableTask()
    try:
        _watched_call(
            usm.Save, _SCHEMA_CLOSE_TIMEOUT_S, f"Save() for {what}",
            diagnose=_diagnose_backend,
        )
    finally:
        # Always restore the ambient task, even if Save raised -- the handle
        # stays usable and CloseProject()'s EndNonUndoableTask still has a
        # task to end.
        mca.BeginNonUndoableTask()
    _log.debug(
        "_persist_without_close: checkpoint for %s persisted (handle id=%s)",
        what, id(proj),
    )


# ============================================================================
# Custom-field schema constants (LCM / CellarPropertyType refs)
# ============================================================================

# CellarPropertyType values for list-backed reference fields.
# ReferenceAtomic = 24 (LCM CellarPropertyType.ReferenceAtomic)
# ReferenceCollection = 26 (LCM CellarPropertyType.ReferenceCollection)
# See probe-results.md §"destinationClass / list-field ruling".
_LIST_FIELD_TYPES: frozenset = frozenset((24, 26))

# CmPossibility.ClassID in LCM — used as destinationClass for list-backed
# reference fields in the 7-arg AddCustomField overload.
# See probe-results.md §"Corrected API facts" and LCM class registry.
_CM_POSSIBILITY_CLASS_ID: int = 7  # CmPossibility

# CellarPropertyType values LibLCM's commit serializer can actually write
# (the exhaustive case list of BackendProvider.GetFlidTypeAsString; anything
# else THROWS "Property element name not recognized" at commit time, and the
# serializer's catch path -- ReportProblem -> WinForms Control.Invoke --
# wedges a headless host forever). AddCustomField itself does NOT validate,
# so we must: a Nil(0)-typed field is a delayed-action process killer.
# Boolean=1 Integer=2 Numeric=3 Float=4 Time=5 Guid=6 Image=7 GenDate=8
# Binary=9 String=13 MultiString=14 Unicode=15 MultiUnicode=16
# OwningAtomic=23 ReferenceAtomic=24 OwningCollection=25
# ReferenceCollection=26 OwningSequence=27 ReferenceSequence=28
_SERIALIZABLE_FIELD_TYPES: frozenset = frozenset(
    (1, 2, 3, 4, 5, 6, 7, 8, 9, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28)
)

# ============================================================================
# Stub + candidate types (contracts/module-ui.md)
# ============================================================================

class PreviewState(enum.Enum):
    NEEDS_WS_MAPPING = "needs_ws_mapping"
    PREVIEW_READY = "preview_ready"


@dataclass(frozen=True)
class RunContextStub:
    """Partial RunContext built before the target is picked. The target
    fields are filled in by `bind_target`."""
    source_handle: object
    source_project_name: str
    source_project_path: str
    run_id: str
    started_at: str


@dataclass(frozen=True)
class TargetCandidate:
    """One entry in the target-picker list."""
    project_name: str
    project_path: str

    def __post_init__(self) -> None:
        if not self.project_name:
            raise ValueError("TargetCandidate.project_name must be non-empty")


@dataclass(frozen=True)
class RequiredWSMapping:
    """The set of source (ws_id, kind) pairs the current Selection touches —
    returned by `compute_preview` when the user hasn't supplied a mapping
    yet."""
    pairs: frozenset = field(default_factory=frozenset)  # frozenset[(str, WSKind)]


# ============================================================================
# Exceptions (contracts/module-ui.md error surfaces)
# ============================================================================

class TargetUnavailable(Exception):
    """Raised by `bind_target` when the target is locked / read-only /
    otherwise unwritable (FR-020). The UI shows a modal and returns to the
    target picker."""


class SameProjectError(Exception):
    """Raised by `bind_target` when the user picked the same project as
    the source (FR-019). UI shows a modal and refuses to advance."""


class PreviewStale(Exception):
    """Raised by `execute_move` when the plan it was passed doesn't match
    the current Selection/WSMapping. UI bug — the state-machine gate in
    contracts/module-ui.md should prevent this from ever happening."""


# ============================================================================
# API functions
# ============================================================================

def initialize_run(host_handle, *, source_project_name: str,
                   source_project_path: str = "") -> RunContextStub:
    """Build a partial RunContext from the FlexTools host's open project.

    The host hands us its already-open project handle (the source per
    Clarification Q2). We mint the run_id + started_at now so they are
    stable across the WS mapping + preview + Move sequence.
    """
    import datetime
    now = datetime.datetime.now()
    return RunContextStub(
        source_handle=host_handle,
        source_project_name=source_project_name,
        source_project_path=source_project_path,
        run_id="GT-" + now.strftime("%Y%m%d-%H%M%S"),
        started_at=now.strftime("%Y-%m-%dT%H:%M:%S"),
    )


def list_target_candidates(stub: RunContextStub,
                           projects_root: str = r"C:\ProgramData\SIL\FieldWorks\Projects",
                           ) -> List[TargetCandidate]:
    """Enumerate FLEx projects in the standard directory (research.md R5),
    excluding the source project by path."""
    candidates: List[TargetCandidate] = []
    if not os.path.isdir(projects_root):
        return candidates
    for name in sorted(os.listdir(projects_root)):
        path = os.path.join(projects_root, name)
        if not os.path.isdir(path):
            continue
        # FLEx projects are directories containing a <name>.fwdata file.
        fwdata = os.path.join(path, f"{name}.fwdata")
        if not os.path.isfile(fwdata):
            continue
        # Exclude source if paths match (case-insensitive on Windows).
        if stub.source_project_path and os.path.normcase(stub.source_project_path).rstrip(os.sep) == os.path.normcase(path).rstrip(os.sep):
            continue
        if stub.source_project_name and name == stub.source_project_name:
            continue
        candidates.append(TargetCandidate(project_name=name, project_path=path))
    return candidates


def _disable_project_sharing(project_path: str, project_name: str) -> bool:
    """Force the plain (exclusive) XML backend for a write session by turning
    OFF the target's project-sharing flag before it is opened.

    LibLCM silently upgrades a kXML open to kSharedXML whenever
    <project>/SharedSettings/LexiconSettings.plsx says projectSharing="true"
    (LcmCache.GetProviderTypeFromProjectId -> LcmSettings.IsProjectSharingEnabled).
    The SharedXML backend is a multi-process peer protocol (global commit-log
    mutex, cross-peer reconciliation, UI marshals on its writer thread) that
    a pump-less headless host cannot safely participate in: observed live, a
    large commit wedged the mutex-holding writer and every subsequent Save()
    deadlocked. GramTrans's contract is EXCLUSIVE write access to the target
    (bind_target refuses locked targets), so sharing buys nothing here and
    the plain XML backend is the proven-correct path. As a bonus, with
    sharing off a co-holder (FLEx GUI / second session) makes OpenProject
    fail FAST with a lock error instead of deadlocking mid-run.

    Returns True if the flag was flipped, False if it was already off / the
    settings file does not exist. Fail-loud on unexpected file content.
    """
    import re

    plsx = os.path.join(project_path, "SharedSettings", "LexiconSettings.plsx")
    if not os.path.isfile(plsx):
        return False
    with open(plsx, encoding="utf-8") as fh:
        text = fh.read()
    new_text, n = re.subn(
        r'(<ProjectLexiconSettings\b[^>]*\bprojectSharing=")true(")',
        r"\g<1>false\g<2>",
        text,
        count=1,
    )
    if n == 0:
        return False
    with open(plsx, "w", encoding="utf-8") as fh:
        fh.write(new_text)
    _log.warning(
        "bind_target: disabled projectSharing on %r (%s) -- GramTrans "
        "requires exclusive write access; the SharedXML backend deadlocks "
        "headless hosts. Re-enable sharing in FLEx (Project Properties > "
        "Sharing) if you use it.",
        project_name, plsx,
    )
    return True


def bind_target(stub: RunContextStub, choice: TargetCandidate) -> RunContext:
    """Open the chosen target for write, raise on lock/read-only/same-project.

    This call DOES touch the LCM layer (opens the target), so it can't be
    fully exercised in unit tests. The lock-detection mechanism per R11
    surfaces as a `TargetUnavailable` — the caller (UI) returns to the
    picker.
    """
    if stub.source_project_name == choice.project_name:
        raise SameProjectError(
            f"Source and target are the same project ({choice.project_name!r}); "
            "Phase 0 refuses to run (FR-019)."
        )
    if stub.source_project_path and os.path.normcase(stub.source_project_path).rstrip(os.sep) == os.path.normcase(choice.project_path).rstrip(os.sep):
        raise SameProjectError(
            f"Source and target paths resolve to the same project; refusing "
            "to advance (FR-019)."
        )

    try:
        from flexicon import FLExProject  # lazy
    except ImportError:
        raise TargetUnavailable(
            "flexicon is not installed; cannot open the target project."
        )

    # Exclusive-backend guard: must run BEFORE OpenProject (the backend type
    # is chosen at open from the on-disk sharing flag).
    try:
        _disable_project_sharing(choice.project_path, choice.project_name)
    except Exception as exc:  # noqa: BLE001 — diagnose-don't-block
        _log.warning(
            "bind_target: could not check/disable projectSharing for %r: %s "
            "(a shared-backend open may deadlock on Save under a co-holder)",
            choice.project_name, exc,
        )

    target = FLExProject()
    try:
        target.OpenProject(projectName=choice.project_name, writeEnabled=True)
    except Exception as exc:  # noqa: BLE001 — LCM raises a variety of types
        raise TargetUnavailable(
            f"Target {choice.project_name!r} is unavailable: {exc!s}"
        ) from exc

    # Persist diagnostics: the target is opened writeEnabled=True but with NO
    # `undoable=` argument, so flexicon's default (undoable=False) applies. A
    # non-undoable open changes how/whether CloseProject persists writes.
    _log.debug(
        "bind_target: opened %r writeEnabled=True, undoable=<default False> "
        "(no undoable= arg passed); handle id=%s",
        choice.project_name, id(target),
    )

    return RunContext(
        source_handle=stub.source_handle,
        source_project_name=stub.source_project_name,
        source_project_path=stub.source_project_path,
        target_handle=target,
        target_project_name=choice.project_name,
        target_project_path=choice.project_path,
        run_id=stub.run_id,
        started_at=stub.started_at,
    )


def compute_preview(context: RunContext,
                    selection: Selection,
                    ws_mapping: Optional[WSMapping],
                    ) -> Tuple[PreviewState, object]:
    """Compute a preview plan.

    Phase 3c wizard change: WS is now a project-level page-1 decision made
    once up-front.  The two-stage NEEDS_WS_MAPPING handshake is RETIRED.
    When `ws_mapping` is None, an empty identity mapping is substituted
    (the wizard has already collected WS choices on page 1).

    Returns:
        (PREVIEW_READY, RunPlan) — always; the plan consumes the Selection
            + WSMapping directly.

    Never mutates target (Principle III).
    """
    # WS handshake retired (Phase 3c wizard): treat None as empty identity mapping.
    # The wizard collects WS choices on page 1; by the time compute_preview is
    # called the mapping is already resolved (or empty for projects with matching WSes).
    if ws_mapping is None:
        ws_mapping = WSMapping(entries=())

    plan = build_run_plan(context, selection, ws_mapping,
                          context.source_handle, context.target_handle)
    return (PreviewState.PREVIEW_READY, plan)


def _ensure_custom_fields(proj, create_actions: list) -> list:
    """Custom-field pre-pass: create missing field definitions on the OPEN
    target handle, then persist the schema WITHOUT closing.

    Called by execute_move BEFORE transfer.execute. Creates each field via
    IFwMetaDataCacheManaged.AddCustomField on ``proj`` (the caller's target
    handle), then checkpoints via _persist_without_close so the schema is on
    disk before any value write. This is FLEx parity: AddCustomFieldDlg runs
    AddCustomField in-memory and lets a normal commit write the
    <AdditionalFields> element -- it never closes the project, which is why
    FLEx never hangs here. The old PATH-CLOSE-REBIND close/reopen dance
    deadlocked whenever anything co-held the target, because only the
    Dispose() step (not Save) takes the SharedXML commit-log mutex without a
    timeout.

    Parameters
    ----------
    proj:
        The already-open write-enabled (non-undoable) target FLExProject.
        AddCustomField is purely an in-memory metadata-cache mutation, so the
        new flids are immediately usable by this same handle -- no reopen.
    create_actions:
        List of CreateDefinitionAction instances from the plan.  Only NEW
        fields (plan_action returned CreateDefinitionAction) reach here;
        already-present fields are Skip(ALREADY_PRESENT_BY_IDENTITY).

    Returns
    -------
    list[str]
        Names of fields successfully created (for logging).  On any
        AddCustomField returning flid==0 or raising, raises RuntimeError
        with field name + cause (fail-loud, per probe-results.md).

    Notes
    -----
    - No reload happens anymore, so the flids AddCustomField returns stay
      valid for this session. (The old flids-renumber-on-reload warning only
      applied to the retired close/reopen dance.)
    - Crash-safety: a crash between the schema checkpoint and the value
      writes leaves a valid project with empty custom fields -- same as
      creating a field in FLEx and never filling it in. The reverse order
      (values before schema) would be the ghost-field corruption trap.
    - Idempotency: if the field already exists (FindField truthy) when this
      runs, skip AddCustomField for that field -- safe for re-run.
    - 4th arg to AddCustomField is destinationClass (Int32), NOT
      list_root_guid.  For non-list types pass 0; for list types pass
      GetClassId(list_root_class).  list_root_guid is the 7th arg of the
      extended overload (probe-results.md).
    """
    created: list = []
    if not create_actions:
        return created

    try:
        from SIL.LCModel.Infrastructure import IFwMetaDataCacheManaged
    except ImportError as exc:
        raise RuntimeError(
            f"SIL.LCModel.Infrastructure not available: {exc}"
        ) from exc

    _log.debug(
        "_ensure_custom_fields: running AddCustomField pre-pass for %d "
        "action(s) on the caller's target handle id=%s",
        len(create_actions), id(proj),
    )
    mdc_managed = IFwMetaDataCacheManaged(proj.Cache.MetaDataCacheAccessor)
    cf_ops = proj.CustomFields

    for act in create_actions:
        # Idempotency: skip if already present (re-run safety).
        existing = cf_ops.FindField(act.owner_class, act.field_name)
        if existing:
            continue
        # FAIL-LOUD type guard: AddCustomField accepts ANY CellarPropertyType
        # (including Nil=0) but the commit serializer only writes the types in
        # _SERIALIZABLE_FIELD_TYPES -- anything else detonates LATER on the
        # commit-writer thread and wedges the process (see the frozenset's
        # comment). Refuse here, before any schema mutation.
        if act.field_type not in _SERIALIZABLE_FIELD_TYPES:
            raise RuntimeError(
                f"Refusing to create custom field "
                f"{act.owner_class}.{act.field_name!r}: CellarPropertyType "
                f"{act.field_type} is not serializable by LibLCM "
                f"(GetFlidTypeAsString would throw at commit time and wedge "
                f"the process). A type of 0 means the source field's type "
                f"was never harvested -- check "
                f"categories._harvest_field_shape / GetAllFields."
            )
        # AddCustomField's 3rd arg is a CellarPropertyType enum, not a
        # raw int; pythonnet won't coerce int->Enum implicitly (TypeError
        # "Use Enum(int_value)"). Wrap the stored int field_type.
        from SIL.LCModel.Core.Cellar import CellarPropertyType  # noqa: PLC0415
        from System import Guid as DotNetGuid  # noqa: PLC0415
        field_type_enum = CellarPropertyType(act.field_type)
        field_ws = getattr(act, "field_ws", 0)
        if act.field_type in _LIST_FIELD_TYPES:
            # 7-arg overload for list-backed reference fields:
            #   (className, fieldName, fieldType, destinationClass=CmPossibility,
            #    fieldHelp, fieldWs, fieldListRoot: Guid)
            list_root_guid = DotNetGuid.Parse(act.list_root_guid)
            flid = mdc_managed.AddCustomField(
                act.owner_class, act.field_name, field_type_enum,
                _CM_POSSIBILITY_CLASS_ID, "", field_ws, list_root_guid,
            )
        else:
            # 7-arg overload so the source's wsSelector carries over
            # (String/MultiUnicode fields need it for FLEx display):
            #   (className, fieldName, fieldType, destinationClass=0,
            #    fieldHelp, fieldWs, fieldListRoot=Guid.Empty)
            flid = mdc_managed.AddCustomField(
                act.owner_class, act.field_name, field_type_enum, 0,
                "", field_ws, DotNetGuid.Empty,
            )
        if not flid:
            raise RuntimeError(
                f"AddCustomField returned flid=0 for "
                f"{act.owner_class}.{act.field_name!r} "
                f"(type {act.field_type}); schema write failed."
            )
        created.append(act.field_name)

    _log.debug(
        "_ensure_custom_fields: AddCustomField pre-pass done (created=%r); "
        "checkpointing schema to disk without closing (handle id=%s)",
        created, id(proj),
    )
    _persist_without_close(proj, "custom-field schema write")

    return created


def execute_move(context: RunContext, plan: RunPlan) -> RunReport:
    """Execute the plan against the target. PRECONDITION: caller has verified
    the plan was produced from the current Selection/WSMapping (UI
    state-machine gate, contracts/module-ui.md).

    WS mapping is NOT a parameter here by design: the WSMapping is a
    preview-time concern that `compute_preview` has already baked into `plan`
    (how source WS-tagged strings resolve into target objects). `execute_move`
    is a faithful executor of an already-decided plan. Do NOT add a WSMapping
    argument and re-map at execute time — that would let the committed result
    diverge from the previewed one. The plan is the single source of truth.

    Custom-field create path (T017, reworked): if the plan contains
    CreateDefinitionActions for new custom fields, this function:
      1. Collects those actions from plan.actions.
      2. Calls _ensure_custom_fields(context.target_handle, ...) to
         AddCustomField each new field on the existing handle and checkpoint
         the schema to disk via _persist_without_close. No close, no reopen,
         no handle rebind -- the flids are live in the in-memory metadata
         cache immediately (FLEx-parity; see _persist_without_close).
      3. After transfer.execute, checkpoints again so the VALUE writes are on
         disk even if the caller's final CloseProject later wedges on a
         co-held target.
    transfer.execute internals are unchanged (Principle: zero edits to transfer).
    """
    # Honor GRAMTRANS_DEBUG on the export path (idempotent, no-op when off).
    _enable_debug_logging()
    if plan.context is not context and plan.context != context:
        raise PreviewStale(
            "Plan's context does not match the call context; the UI must "
            "re-Preview before Move."
        )
    if __package__:
        from .transfer import execute
        from .residue import ImportResidueTag
    else:
        from transfer import execute  # type: ignore
        from residue import ImportResidueTag  # type: ignore

    tag = ImportResidueTag(
        run_id=context.run_id,
        source_project_name=context.source_project_name,
        timestamp=context.started_at,
    )

    # Custom-field create path: CreateDefinitionActions for new custom fields.
    create_actions = [
        a for a in plan.actions
        if isinstance(a, CreateDefinitionAction)
    ]
    if _log.isEnabledFor(logging.DEBUG):
        _log.debug(
            "execute_move: entry  actions=%d create_actions=%d "
            "source=%r target=%r target_handle_id=%s tag=%r",
            len(plan.actions), len(create_actions),
            context.source_project_name, context.target_project_name,
            id(getattr(context, "target_handle", None)),
            tag.serialize() if hasattr(tag, "serialize") else str(tag),
        )
    if create_actions:
        # Schema pre-pass on the caller's own handle: AddCustomField is an
        # in-memory metadata-cache mutation; the checkpoint inside persists
        # the <AdditionalFields> schema to disk with NO close/reopen (the
        # close-to-persist dance was the co-held deadlock). The caller's
        # context keeps the one true handle, so the wizard cleanup in
        # gramtrans._run_gui closes the right object.
        _ensure_custom_fields(context.target_handle, create_actions)

    # We need a `report_sink` with .Info / .Warning / .Error / .Blank — the
    # UI passes the FlexTools report object through. For programmatic API
    # calls (e.g. from a test), a tiny null sink is the safe default.
    sink = _NullReportSink()
    _log.debug(
        "execute_move: calling execute() with a _NullReportSink — per-item "
        ".Warning() reports are DISCARDED (target_handle id=%s)",
        id(getattr(context, "target_handle", None)),
    )
    try:
        return execute(plan, context.source_handle, context.target_handle, sink, tag)
    finally:
        if create_actions:
            # Persist the value writes NOW, decoupled from the caller's final
            # CloseProject: even if a co-held close later wedges (and the
            # watchdog abandons it), the transferred data is already on disk.
            try:
                _persist_without_close(
                    context.target_handle, "post-transfer value writes"
                )
            except Exception as exc:  # noqa: BLE001 — must not mask execute()
                _log.warning(
                    "execute_move: post-transfer checkpoint failed/timed out "
                    "(final CloseProject becomes the persist point): %s", exc,
                )


class _NullReportSink:
    """Drop-in for the FlexTools report object when the UI hasn't supplied
    one (programmatic / test contexts). Accepts the same four methods and
    discards everything."""
    def Info(self, msg: str) -> None:  # noqa: N802
        pass

    def Warning(self, msg: str) -> None:  # noqa: N802
        pass

    def Error(self, msg: str) -> None:  # noqa: N802
        pass

    def Blank(self) -> None:  # noqa: N802
        pass

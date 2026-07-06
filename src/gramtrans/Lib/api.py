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


def _ensure_custom_fields(target_project_name: str,
                           create_actions: list,
                           ) -> list:
    """PATH-CLOSE-REBIND pre-pass: create missing custom field definitions.

    Called by execute_move BEFORE transfer.execute, after the Phase-1 preview
    handle has been closed.  Opens a FRESH undoable FLExProject, creates each
    field via IFwMetaDataCacheManaged.AddCustomField in a
    NonUndoableUnitOfWorkHelper.Do block, then closes it so the schema change
    persists to disk.

    Parameters
    ----------
    target_project_name:
        Name of the target project as passed to FLExProject.OpenProject.
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
    - flids renumber on reload; DO NOT cache flids across this boundary.
    - Idempotency: if the field already exists (FindField truthy) when this
      runs, skip AddCustomField for that field -- safe for re-run.
    - 4th arg to AddCustomField is destinationClass (Int32), NOT
      list_root_guid.  For non-list types pass 0; for list types pass
      GetClassId(list_root_class).  list_root_guid is the 7th arg of the
      extended overload (probe-results.md).
    - This helper has no unit-test coverage for the live LCM path; the
      FLExProject boundary is mocked/stubbed in tests per the task memo.
      Flag for main-session MCP value-round-trip verification.
    """
    try:
        from flexicon import FLExProject  # lazy -- unavailable in unit tests
        from SIL.LCModel.Infrastructure import IFwMetaDataCacheManaged
    except ImportError as exc:
        raise RuntimeError(
            f"flexicon / SIL.LCModel.Infrastructure not available: {exc}"
        ) from exc

    created: list = []
    if not create_actions:
        return created

    proj = FLExProject()
    try:
        proj.OpenProject(projectName=target_project_name, writeEnabled=True)
    except Exception as exc:  # noqa: BLE001 — LCM raises a variety of types
        raise RuntimeError(
            f"_ensure_custom_fields: could not open {target_project_name!r} "
            f"for schema write: {exc!s}"
        ) from exc
    try:
        mdc_managed = IFwMetaDataCacheManaged(proj.Cache.MetaDataCacheAccessor)
        cf_ops = proj.CustomFields

        def _do_creates():
            for act in create_actions:
                # Idempotency: skip if already present (re-run safety).
                existing = cf_ops.FindField(act.owner_class, act.field_name)
                if existing:
                    continue
                if act.field_type in _LIST_FIELD_TYPES:
                    # 7-arg overload for list-backed reference fields:
                    #   (className, fieldName, fieldType, destinationClass=CmPossibility,
                    #    fieldHelp, fieldWs, fieldListRoot: Guid)
                    from System import Guid as DotNetGuid  # noqa: PLC0415
                    list_root_guid = DotNetGuid.Parse(act.list_root_guid)
                    flid = mdc_managed.AddCustomField(
                        act.owner_class, act.field_name, act.field_type,
                        _CM_POSSIBILITY_CLASS_ID, "", 0, list_root_guid,
                    )
                else:
                    # 4-arg overload for value types:
                    #   (className, fieldName, fieldType, destinationClass=0)
                    flid = mdc_managed.AddCustomField(
                        act.owner_class, act.field_name, act.field_type, 0
                    )
                if not flid:
                    raise RuntimeError(
                        f"AddCustomField returned flid=0 for "
                        f"{act.owner_class}.{act.field_name!r} "
                        f"(type {act.field_type}); schema write failed."
                    )
                created.append(act.field_name)

        # NonUndoableUnitOfWorkHelper.Do equivalent via flexicon's UoW context.
        # Schema (MDC) writes are non-undoable by LCM design; flexicon exposes
        # this via the project's ActionHandler at CurrentDepth==0.
        #
        # Citation: probe-results.md §"Evidence" op-005 confirms CurrentDepth==0
        # at snippet start (undoable open, before any UndoableOperation block).
        # probe-results.md §"Required engine flow (Option B, PATH-CLOSE-REBIND)"
        # step 2 states: "run the create-definition pre-pass at CurrentDepth==0,
        # before any value-write UndoableOperation block."  The PATH-CLOSE-REBIND
        # single-owner contract guarantees this: we close the Phase-1 handle
        # before opening here, so no other UoW owner can be active.
        _do_creates()
    finally:
        proj.CloseProject()

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

    PATH-CLOSE-REBIND (T017): if the plan contains CreateDefinitionActions
    for new custom fields, this function:
      1. Collects those actions from plan.actions.
      2. Calls _ensure_custom_fields() to close the Phase-1 handle, open a
         fresh undoable project, AddCustomField each new field, then close.
         (The Phase-1 handle in context.target_handle is the preview handle
         opened by bind_target; it is stale after schema writes.)
      3. Re-opens the target and re-binds context before calling transfer.execute.
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

    # PATH-CLOSE-REBIND: handle CreateDefinitionActions for new custom fields.
    create_actions = [
        a for a in plan.actions
        if isinstance(a, CreateDefinitionAction)
    ]
    if _log.isEnabledFor(logging.DEBUG):
        _log.debug(
            "execute_move: entry  actions=%d create_actions=%d "
            "source=%r target=%r target_handle_id=%s tag=%r "
            "PATH-CLOSE-REBIND=%s",
            len(plan.actions), len(create_actions),
            context.source_project_name, context.target_project_name,
            id(getattr(context, "target_handle", None)),
            tag.serialize() if hasattr(tag, "serialize") else str(tag),
            bool(create_actions),
        )
    if create_actions:
        phase1_handle = context.target_handle
        _log.debug(
            "execute_move PATH-CLOSE-REBIND: closing Phase-1 preview handle "
            "id=%s (the handle stored on the caller's context)",
            id(phase1_handle),
        )
        # Step 1: close the Phase-1 preview handle.
        try:
            context.target_handle.CloseProject()
        except Exception:
            pass  # already closed or unavailable

        # Step 2: open fresh undoable handle, run AddCustomField pre-pass, close.
        _ensure_custom_fields(context.target_project_name, create_actions)

        # Step 3: re-open the target (fresh handle now sees persisted fields).
        try:
            from flexicon import FLExProject  # lazy
            fresh_target = FLExProject()
            fresh_target.OpenProject(
                projectName=context.target_project_name, writeEnabled=True
            )
        except Exception as exc:
            raise RuntimeError(
                f"Re-open of target {context.target_project_name!r} after "
                f"custom-field schema write failed: {exc}"
            ) from exc

        # Handle divergence is a prime suspect for the persist bug: writes go to
        # `fresh_target` (created locally here), but the wizard cleanup in
        # gramtrans._run_gui closes the ORIGINAL handle stored on its context.
        _log.debug(
            "execute_move PATH-CLOSE-REBIND: opened fresh_target id=%s "
            "(created locally). Writes below target THIS handle; the caller's "
            "context still references the disposed Phase-1 handle id=%s. This "
            "branch owns closing fresh_target (see Step 5).",
            id(fresh_target), id(phase1_handle),
        )

        # Step 4: re-bind context with the fresh handle (frozen dataclass replace).
        import dataclasses
        context = dataclasses.replace(context, target_handle=fresh_target)
        # Also update the plan's embedded context so execute() sees the fresh handle.
        plan = dataclasses.replace(plan, context=context)

        # Step 5: run the transfer and CLOSE the fresh handle ourselves.
        # The wizard's cleanup (gramtrans.py _run_gui) closes the ORIGINAL
        # target_handle, which we disposed in Step 1; closing a disposed handle
        # is a silent no-op. FLEx only persists writes on CloseProject()
        # (EndNonUndoableTask + usm.Save), so this branch must own closing
        # fresh_target or every object write below is discarded on exit.
        _log.debug(
            "execute_move PATH-CLOSE-REBIND: calling execute() with a "
            "_NullReportSink — per-item .Warning() reports are DISCARDED "
            "(fresh_target id=%s)", id(fresh_target),
        )
        try:
            return execute(
                plan, context.source_handle, context.target_handle,
                _NullReportSink(), tag,
            )
        finally:
            _log.debug(
                "execute_move PATH-CLOSE-REBIND: closing fresh_target id=%s "
                "(this branch owns the disk-write for the create path)",
                id(fresh_target),
            )
            try:
                fresh_target.CloseProject()
            except Exception:
                pass  # don't let a close error mask the execute result/exception

    # We need a `report_sink` with .Info / .Warning / .Error / .Blank — the
    # UI passes the FlexTools report object through. For programmatic API
    # calls (e.g. from a test), a tiny null sink is the safe default.
    sink = _NullReportSink()
    _log.debug(
        "execute_move: calling execute() with a _NullReportSink — per-item "
        ".Warning() reports are DISCARDED (target_handle id=%s)",
        id(getattr(context, "target_handle", None)),
    )
    return execute(plan, context.source_handle, context.target_handle, sink, tag)


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

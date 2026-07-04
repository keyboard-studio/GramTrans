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
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

if __package__:
    from .models import (
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
else:
    from models import (
        GrammarCategory,
        RunContext,
        RunMode,
        RunPlan,
        RunReport,
        Selection,
        WSKind,
        WSMapping,
    )
    from preview import build_run_plan
    from ws_mapping import WSMappingIncomplete, is_complete, required_ws_set


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


def execute_move(context: RunContext, plan: RunPlan) -> RunReport:
    """Execute the plan against the target. PRECONDITION: caller has verified
    the plan was produced from the current Selection/WSMapping (UI
    state-machine gate, contracts/module-ui.md).

    WS mapping is NOT a parameter here by design: the WSMapping is a
    preview-time concern that `compute_preview` has already baked into `plan`
    (how source WS-tagged strings resolve into target objects). `execute_move`
    is a faithful executor of an already-decided plan. Do NOT add a WSMapping
    argument and re-map at execute time — that would let the committed result
    diverge from the previewed one. The plan is the single source of truth."""
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

    # We need a `report_sink` with .Info / .Warning / .Error / .Blank — the
    # UI passes the FlexTools report object through. For programmatic API
    # calls (e.g. from a test), a tiny null sink is the safe default.
    sink = _NullReportSink()
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

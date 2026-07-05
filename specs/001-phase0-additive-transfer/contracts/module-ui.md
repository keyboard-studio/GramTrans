# Contract: Module UI ↔ Core

**Plan**: [../plan.md](../plan.md)
**Data Model**: [../data-model.md](../data-model.md)

The PyQt UI layer (`src/gramtrans/Lib/ui/`) MUST NOT import flexicon directly or
reach into the engine internals. Its only window onto the engine is the small
surface declared here, exposed as module-level functions in `src/gramtrans/Lib/api.py`.
Per constitution v5.1.0 Principle II there is no `flavors/` or `categories/`
subpackage to ban — the prohibition is simply "no `from flexicon ...` imports in
`Lib/ui/`; call `Lib/api.py` instead".

## Main window lifecycle (UI calls into core)

```python
# Pseudocode — actual Python signatures land in code.

def initialize_run(host_handle) -> RunContextStub:
    """
    Build a partial RunContext from the FlexTools host's open project.
    `target_handle` is None at this point. Called once on module open.
    """

def list_target_candidates(stub: RunContextStub) -> list[TargetCandidate]:
    """
    Enumerate available FLEx projects, excluding `stub.source_handle`'s project.
    """

def bind_target(stub: RunContextStub, choice: TargetCandidate) -> RunContext:
    """
    Open the chosen target for write; refuse and raise TargetUnavailable if locked /
    read-only / same as source (FR-019, FR-020). Returns a finalized RunContext.
    """

def compute_preview(
    context: RunContext,
    selection: Selection,
    ws_mapping: WSMapping | None,
) -> tuple[PreviewState, RunPlan | RequiredWSMapping]:
    """
    Two-stage call.

    - If `ws_mapping` is None, returns (NEEDS_WS_MAPPING, RequiredWSMapping(...))
      listing every (source_ws_id, kind) the current selection requires.
    - If `ws_mapping` is provided and complete, returns (PREVIEW_READY, RunPlan).
    - If `ws_mapping` is provided but incomplete (missing some required WSs),
      returns (NEEDS_WS_MAPPING, RequiredWSMapping(...)) again with the gap.

    Never mutates the target.
    """

def execute_move(
    context: RunContext,
    plan: RunPlan,
) -> RunReport:
    """
    Execute the plan against the target. PRECONDITION: the plan was produced by
    a `compute_preview` call with the SAME selection and ws_mapping as the user
    currently has. The UI MUST gate the Move button to enforce this; if violated,
    raise PreviewStale.
    """
```

## UI components and their responsibilities

| Component | Reads | Writes (to engine) | Forbidden |
|-----------|-------|---------------------|-----------|
| `main_window.py` | `RunContext`, `Selection`, current `RunPlan`, current `RunReport` | `Selection`, triggers `compute_preview` / `execute_move` via `Lib/api.py` | Direct LCM access, raw `from flexicon ...` imports, bypassing `Lib/api.py`. |
| `target_picker.py` | `TargetCandidate[]` | Returns chosen `TargetCandidate` | Modifying any state besides its return value. |
| `ws_mapping_dialog.py` | `RequiredWSMapping`, current target's WS inventory | Returns `WSMapping` | Mutating the target (WS creation is staged in `WSMapping`; only the engine performs the create). |
| `affix_tree_picker.py` | Source affix inventory grouped by template → slot → affix + Unbound | Returns `frozenset[str]` for `Selection.affix_picks` | Mutating source. |
| `stats_panel.py` | `RunReport` | (Read-only) | Anything. |

## Preview / Move state machine (UI-enforced)

The Move button MUST be disabled unless **all** of these are true:
1. A `RunContext` exists with both `source_handle` and `target_handle`.
2. The current `Selection` is non-empty (at least one category on).
3. A `RunPlan` was computed by `compute_preview(context, current_selection,
   current_ws_mapping)` after the most recent change to `current_selection` or
   `current_ws_mapping`.
4. The cached `RunPlan`'s `selection` and `ws_mapping` fields equal the current ones
   (object equality, not identity).

Any change to `Selection` or `WSMapping` invalidates the cached plan and re-disables
Move. This is the mechanical enforcement of Principle III.

## Error surfaces

| Engine raises | UI does |
|---------------|---------|
| `TargetUnavailable(reason)` | Show modal error in target picker; return to picker. |
| `PreviewStale` | Should never happen if state machine is honored; if it does, show a bug-report dialog and refuse Move. |
| `WSMappingIncomplete(missing: list[(ws_id, kind)])` | Reopen `ws_mapping_dialog` with `missing` highlighted. |
| `SameProjectError` | Modal error; do not allow Run. (FR-019) |
| Any unexpected exception during Move | Catch; produce a partial `RunReport(mode=MOVE)` with the failure recorded in `skips`; show stats panel. |

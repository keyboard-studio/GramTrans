# Phase 2 Quickstart — Validation Scenarios

Runnable validation guide that proves Phase 2 works end-to-end. Implementation details (model bodies, full test suites) live in `tasks.md` and the implementation phase, not here.

## Prerequisites

- Phase 1 complete and verified (commits e129b72..f4cdd9c on `main`).
- flexicon fork installed per [CLAUDE.md](../../CLAUDE.md).
- Ejagham Mini and Ejagham Full GT-Test projects available at `C:\ProgramData\SIL\FieldWorks\Projects\`.
- A backup of Ejagham Full GT-Test (the scenarios are write-mode).
- Python 3.12, PyQt5, pytest, all already on the dev environment per Phase 1.

## Scenario A — Phase 2 disabled is bit-identical to Phase 1

**Goal**: Prove Phase 2 is additive — turning the gate off restores Phase 1 behavior exactly.

**Setup**: Restore Ejagham Full GT-Test from backup so it carries the same residue state Phase 1 verification left behind (commit 50f873d / f4cdd9c).

**Run**:
```python
sel = Selection(
    categories={c: True for c in PHASE1_CATS},
    enable_overwrite=True,
    pos_picks=frozenset({VERB_GUID}),
    interactive_merge=False,   # <- Phase 2 gate OFF
)
```

**Expected**:
- 67 overwrites, 0 skips (matches Phase 1 verification logs).
- Run report shows `interactive_resolved=0`, `interactive_skipped=0`.
- LiftResidue on every touched object carries `snap=` but NO `merge=` segment.
- Wall clock comparable to Phase 1 (~1.5–2.0 s).
- pytest: full 168-test suite still green; new Phase 2 tests skipped or pass with the disabled-gate path.

**Pass criteria**: residue tag wire format on each touched object MUST be the Phase 1 5-segment form. Any 6-segment tag is a regression.

## Scenario B — Per-conflict prompt fires and writes merge=

**Goal**: Prove FR-201..208 end-to-end with one fabricated conflict.

**Setup**:
1. Manually edit one verb entry in Ejagham Full GT-Test: set Comment = "target-side annotation, keep me".
2. The matching source entry in Ejagham Mini already has Comment = "source comment".

**Run**:
```python
sel = Selection(
    categories={c: True for c in PHASE1_CATS},
    enable_overwrite=True,
    pos_picks=frozenset({VERB_GUID}),
    interactive_merge=True,    # <- Phase 2 gate ON
)
# In a test harness, inject FakeConflictResolver returning
# MergeDecision(field_name="Comment", resolution=MERGE)
```

**Expected**:
- Plan emits one `ConflictPrompt` for that entry's Comment.
- `FakeConflictResolver.resolve()` is called with exactly one prompt.
- `transfer.execute()` writes the merged value `target-side annotation, keep me\n--- merged GT-... ---\nsource comment` to target.
- The target object's LiftResidue is a 6-segment tag with both `snap=` and `merge=`.
- Run report shows `interactive_resolved=1` for the entry category.

**Pass criteria**: probe the target object's LiftResidue post-run; `ImportResidueTag.parse(...).decode_merge_log()` returns a `MergeDecisionLog` with the one MERGE decision.

## Scenario C — Prior-run recall (US3)

**Goal**: Re-run Scenario B with no source-side changes; prior decisions pre-fill.

**Setup**: Scenario B has already run; LiftResidue carries the merge log.

**Run**: Same Selection as Scenario B. Inject a `FakeConflictResolver` that asserts `prompts[0].prior_decision is not None and prompts[0].prior_decision.resolution == MERGE`, then returns the same decision.

**Expected**:
- The fake's assertion passes (prior decision recovered).
- Run report shows the resolution as "carried-over" (FR-208) — distinguishable from a fresh interactive resolution by `prior_run_id` being set.
- No new prompts beyond the carried-over one (same field, same conflict).

**Pass criteria**: zero new prompts when re-running with all defaults accepted; previous decisions are honored.

## Scenario D — WS-mapping wizard fires before plan build

**Goal**: Prove FR-209..212.

**Setup**: Identify (or fabricate) a writing-system mismatch between Ejagham Mini and Ejagham Full GT-Test. If they're WS-identical in the live data, add a new WS to Mini ("xyz-temp") and ensure Target doesn't have it.

**Run**: `MainFunction` with a `FakeWSResolver` that picks `WSChoice.MAP` to an existing target WS for `xyz-temp`.

**Expected**:
- `detect_ws_mismatches` returns a non-empty tuple before any plan is built.
- The fake's `resolve()` is invoked; its choices are folded into `Selection.ws_mapping_choices`.
- `build_run_plan` respects the mapping; objects with `xyz-temp` content are routed to the chosen target WS slot.

**Pass criteria**: `WSResolver.resolve` is called exactly once per Move invocation; the resulting transfer respects every choice.

## Scenario E — Cancellation atomicity (FR-213)

**Goal**: Prove cancellation leaves the target project bit-identical.

**Setup**: Snapshot Ejagham Full GT-Test's `.fwdata` file hash.

**Run**: Inject a `FakeConflictResolver` that raises `UserCancelled` on the first prompt.

**Expected**:
- `MainFunction` catches `UserCancelled` and returns without calling `transfer.execute()`.
- No LCM writes occur.
- Post-run `.fwdata` file hash equals the pre-run hash.

**Pass criteria**: file hash equality. Any difference is a Phase 2 atomicity bug.

## Test Suite

```powershell
# All Phase 2 unit tests
python -m pytest tests/unit/test_conflict_detect.py tests/unit/test_conflict_resolve.py tests/unit/test_merge_log_round_trip.py tests/unit/test_ws_mapping_detect.py tests/unit/test_residue_merge_segment.py -v

# Full regression
python -m pytest tests/unit -q

# Integration (mocked resolvers)
python -m pytest tests/integration/test_phase2_e2e.py -v
```

Expected end state: 168 Phase 0/1 tests still green + ~30 new Phase 2 tests green = ~200 tests total.

## Live MCP Validation

```python
# In flextools-mcp / Ejagham Full GT-Test (writeEnabled=True):
import sys, datetime, importlib
GRAMTRANS_LIB = r"D:\Github\_Projects\_LEX\GramTrans\src\gramtrans\Lib"
if GRAMTRANS_LIB not in sys.path:
    sys.path.insert(0, GRAMTRANS_LIB)
# (reload models, residue, preview, transfer, conflict, ws_mapping)
# Run Scenarios B–E with FakeConflictResolver / FakeWSResolver injected.
# Probe LiftResidue on each touched object; confirm 6-segment tags.
```

## Done When

- All five Scenarios A–E pass.
- pytest unit + integration full green.
- A live MCP run on Ejagham Mini → Ejagham Full GT-Test demonstrates Scenarios B and D with real PyQt dialogs (manual exercise, not automated).
- The Phase 1 168-test regression suite is unchanged in behavior.

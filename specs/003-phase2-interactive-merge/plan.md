# Implementation Plan: Phase 2 — Interactive Merge

**Branch**: `003-phase2-interactive-merge` | **Date**: 2026-06-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-phase2-interactive-merge/spec.md`

## Summary

Replace Phase 1's silent FR-109 "source wins" policy with a per-field interactive prompt offering {take-source, keep-target, merge, skip, edit-custom}. Add an SFM-style writing-system mapping wizard that fires before category selection. Persist every interactive resolution into the existing residue tag's wire format via a new `merge=<base64>` segment so a re-run can offer "use last time's choice" defaults. Wraps but does not replace the Phase 1 overwrite executor — all interactive code is additive.

Technical approach: A new `Lib/conflict.py` module owns the `ConflictPrompt` / `MergeDecisionLog` data model and a `resolve_conflicts()` entry point. `Lib/preview.py` builds the prompt list during planning; `Lib/transfer.py` consumes the resolved log and filters `src_props` per decision before calling `ApplySyncableProperties`. The PyQt widgets live in `Lib/ui/conflict_dialog.py` and `Lib/ui/ws_wizard.py`, both already-Qt-based per Phase 1's `Lib/ui/` directory. The residue tag's `serialize()` / `parse()` widens from 4-or-5 segments to 4-or-5-or-6 in a backward-compatible way.

## Technical Context

**Language/Version**: Python 3.12 (matches Phase 0/1; FlexTools host's pythonnet runtime).

**Primary Dependencies**:
- `flexlibs2` (MattGyverLee fork) — direct LCM access (per constitution Principle II).
- `PyQt5` — already imported by `Lib/ui/` in Phase 1 for the category-picker widget.
- `base64` + `json` (stdlib) — for the residue `merge=` segment encoding.

**Storage**: No new persistent storage. All state lives in the residue tag on the target LCM objects (LiftResidue or Description, per `Lib/residue.py`). Mid-session navigation state (US4) is in-memory Qt model state.

**Testing**:
- `pytest` unit tests in `tests/unit/test_conflict_*.py` and `tests/unit/test_ws_wizard_*.py`.
- The Qt widgets are tested by injecting a `ConflictResolver` protocol; the actual `QDialog` subclass is not exercised in unit tests (manual MCP verification only, per Phase 1 precedent).
- Live MCP verification against `Ejagham Mini` → `Ejagham Full GT-Test` confirms the residue round-trip end-to-end.

**Target Platform**: Windows desktop FlexTools host (PyQt + pythonnet + LCM 9.x). No headless or browser support; non-interactive callers fall back to Phase 1 source-wins (FR-109 default).

**Project Type**: FlexTools-compatible Python module (FLExTrans convention) — single project, flat entry file (`src/gramtrans/gramtrans.py`) plus `src/gramtrans/Lib/` sibling helpers loaded via `site.addsitedir(Lib)`.

**Performance Goals**:
- SC-201: 50-conflict transfer on 5,000-entry lexicon completes in under 15 min on recall-all path. Implies: residue parse < 1 ms/object, prompt dispatch < 50 ms.
- A single conflict round-trip (read tgt_pre_props → diff → present prompt → write merge= segment) should add < 100 ms per touched field.

**Constraints**:
- Constitution Principle III: Preview-Before-Mutate. Conflict detection happens during Preview; user resolutions are collected before any Move write.
- Constitution Principle IV: Phase 2 is additive over Phase 1. No Phase 1 code path may be removed; the interactive layer is a no-op when `Selection.interactive_merge=False`.
- The entire interactive transfer (wizard + prompts + writes) must fit inside the single UndoableUnitOfWork the FlexTools runner wraps `MainFunction` in. A long-running open transaction during user think-time is acceptable per spec Assumptions.
- The Phase 1 residue carrier write fix (commit 50f873d) is a prerequisite — without setattr-on-None landing snap= on disk, the prior-decision recall (US3) cannot read its own prior writes.

**Scale/Scope**:
- Up to ~500 simultaneously-conflicted fields per transfer (50 entries × ~10 conflicted props each = realistic ceiling for a single linguist session).
- The merge decision log persists per-object; aggregate log size across 500 fields ≈ 50 KB base64 in worst case (well within LiftResidue's Unicode-string capacity).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design (below).*

| Principle | Status | Justification |
|-----------|--------|---------------|
| I. FLEx Domain Fidelity | PASS | Phase 2 ADDS user choice on conflicts but never weakens GUID identity, GOLD inviolability, or cross-reference resolution. The merge resolutions affect only field VALUES on already-matched objects. |
| II. flexlibs2-Direct | PASS | No new `flavors/` files. New modules (`Lib/conflict.py`, `Lib/ui/conflict_dialog.py`, `Lib/ui/ws_wizard.py`) import `flexlibs2` directly when they touch LCM objects. The PyQt widget code touches no LCM API. |
| III. Preview-Before-Mutate | PASS | Conflict detection and prompt collection happen during Preview / plan-build. Move execution consumes the resolved `MergeDecisionLog` as a frozen input. No Move write occurs before the user clicks "apply". |
| IV. Phased Merge Discipline | PASS | Phase 2 is ordered behind Phase 1 (which shipped in this session as commits e129b72..f4cdd9c). FR-213/FR-214 enforce the single-UoW commit boundary required by constitution Phase 2 framing ("undoable"). |
| V. Referential Completeness | PASS | Phase 2 does not alter the dependency closure walker. User choices on a field value never cause a cross-reference to dangle. |

**No violations. No Complexity Tracking entries required.**

### Re-check after Phase 1 design (this document, post-data-model)

| Principle | Status | Notes |
|-----------|--------|-------|
| I. | PASS | `MergeDecisionLog` and `WSMappingChoice` (data-model.md) are field-value entities only; they do not alter LCM object identity. |
| II. | PASS | `contracts/conflict-prompt.md` and `contracts/ws-wizard.md` are pure-Python contracts; no flavor-adapter shape. |
| III. | PASS | `contracts/conflict-prompt.md` requires the prompt list to be a Preview-phase output. |
| IV. | PASS | `quickstart.md` exercises the no-op (Phase-2-disabled) path as Validation Scenario A; confirms Phase 1 still works unchanged. |
| V. | PASS | No closure change. |

## Project Structure

### Documentation (this feature)

```text
specs/003-phase2-interactive-merge/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── conflict-prompt.md
│   ├── ws-wizard.md
│   └── residue-merge-segment.md
├── checklists/
│   └── requirements.md  # Spec quality checklist (already green)
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
src/gramtrans/
├── gramtrans.py                 # Entry; MainFunction; unchanged shape, gains
│                                # Selection.interactive_merge bool wire-through
└── Lib/
    ├── models.py                # +ConflictPrompt, +MergeDecisionLog,
    │                            # +WSMappingChoice; Selection gains
    │                            # interactive_merge: bool = False
    ├── conflict.py              # NEW: detect_conflicts(plan), resolve_conflicts(log)
    ├── ws_mapping.py            # NEW: detect_ws_mismatches(src, tgt) -> list[WSMismatch]
    ├── preview.py               # MOD: call detect_conflicts during plan build
    │                            # when selection.interactive_merge; attach
    │                            # ConflictPrompt list to RunPlan.conflicts
    ├── transfer.py              # MOD: read RunPlan.conflicts + MergeDecisionLog;
    │                            # filter src_props per decision before
    │                            # ApplySyncableProperties; serialize merge=
    │                            # segment into residue tag
    ├── residue.py               # MOD: ImportResidueTag gains merge_b64: str|None;
    │                            # serialize/parse widen to 6-segment form;
    │                            # new with_merge_log(decisions) / decode_merge_log()
    ├── report.py                # MOD: CategoryReport gains interactive_resolved,
    │                            # interactive_skipped, ws_mapped, ws_created,
    │                            # ws_skipped counters
    └── ui/
        ├── conflict_dialog.py   # NEW: PyQt5 QDialog showing side-by-side conflict
        ├── ws_wizard.py         # NEW: PyQt5 QWizard listing source WSes + choices
        └── (existing widgets)   # unchanged

tests/
├── unit/
│   ├── test_conflict_detect.py        # NEW
│   ├── test_conflict_resolve.py       # NEW
│   ├── test_merge_log_round_trip.py   # NEW
│   ├── test_ws_mapping_detect.py      # NEW
│   ├── test_residue_merge_segment.py  # NEW
│   └── (existing 168 tests)           # unchanged; must all still pass
└── integration/
    └── test_phase2_e2e.py             # NEW: full overwrite run with mocked
                                        # ConflictResolver protocol
```

**Structure Decision**: Single project; FLExTrans-style flat entry + `Lib/` siblings; no new top-level packages. The only new files are two `Lib/ui/` widgets and two `Lib/` modules (`conflict.py`, `ws_mapping.py`). All other work is additive edits to existing `models.py`, `preview.py`, `transfer.py`, `residue.py`, `report.py`. PyQt5 is already a transitive dependency via `Lib/ui/`.

## Complexity Tracking

> Constitution Check passed with no violations. Section intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| _(none)_  | _(none)_   | _(none)_                            |

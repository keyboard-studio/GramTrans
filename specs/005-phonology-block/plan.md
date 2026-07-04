# Implementation Plan: Phase 3a — Phonology Block

**Branch**: `005-phonology-block` | **Date**: 2026-06-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-phonology-block/spec.md`

## Summary

Wire six self-contained categories into the existing `Lib/categories.py` registry — phonological_features, phonemes, natural_classes, ph_environment (relocated), phonological_rules, strata — following the validated 22-step ordering from [specs/004-phase3-pipeline/ordering-memo.md](../004-phase3-pipeline/ordering-memo.md). All six are anchored at `LangProject.PhonologicalDataOA` (5) or `LangProject.MorphologicalDataOA` (1); none reference LexEntry, so Phase 0/1/2 verb-vertical paths stay bit-identical.

Technical approach: extend `GrammarCategory` enum with five new members, add five callbacks per category in `Lib/categories.py` matching the shape of the existing complete categories. For each LCM type, MCP-probe the factory at planning time to determine whether `Create(Guid, ...)` is supported; categories whose factories lack Guid overloads fall back to `identity_remap` per FR-303 (mirrors Phase 1's MSA/Allomorph pattern). Strata use `project.GetService(IMoStratumFactory)` directly since flexicon has no `StratumOperations` class.

## Technical Context

**Language/Version**: Python 3.12.

**Primary Dependencies**:
- `flexicon` (MattGyverLee fork) — direct LCM access per constitution Principle II. Exposes `PhonFeatureOperations`, `PhonemeOperations`, `NaturalClassOperations`, `EnvironmentOperations`, `PhonologicalRuleOperations` (all in `flexicon/code/Grammar/`). Strata accessed via `project.GetService(IMoStratumFactory)` since no `StratumOperations` class exists.
- `SIL.LCModel` interfaces (lazy-imported per existing pattern): `IPhPhoneme`, `IPhNaturalClass`, `IPhNCSegments`, `IPhNCFeatures`, `IPhEnvironment`, `IPhPhonologicalRule`, `IMoStratum`, `IFsClosedFeature`, `IFsClosedFeatureFactory`, plus factories per category.

**Storage**: No new storage. State lives in target LCM objects + the existing residue tag (Phase 1's `snap=` and Phase 2's `merge=` segments work unchanged).

**Testing**:
- `pytest` unit tests in `tests/unit/test_categories_phon_features.py`, `test_categories_phonemes.py`, etc. Six new test files matching the six categories.
- Live MCP verification on `Ejagham Mini` → `Ejagham Full GT-Test` exercising all six categories with both Phase 0 additive and Phase 1 overwrite paths.

**Target Platform**: Same as Phases 0-2 — Windows desktop FlexTools host (pythonnet + LCM 9.x).

**Project Type**: FlexTools-compatible Python module (FLExTrans convention). Single project; flat entry + `src/gramtrans/Lib/` siblings.

**Performance Goals**:
- SC-301: 30 phonemes + 10 natural classes + 5 rules + 2 strata transfer in under 5s wall-clock.
- Per-category enumerate_source < 100ms for inventories under 1000 items each.

**Constraints**:
- Constitution Principle II: flexicon-Direct; no flavor-adapter wrappers.
- Principle III: Preview-Before-Mutate — every category's plan_action runs during build_run_plan, no LCM writes.
- Principle IV: additive over Phases 0/1/2 — no Phase 0/1/2 code path removed.
- Some factories (TBD via MCP) lack `Create(Guid)`; those fall back to `identity_remap` (FR-303 / Phase 1 FR-012 pattern). MCP probing in Phase 0 of this plan confirms exact behaviour.

**Scale/Scope**:
- Realistic ceiling: ~200 phonemes, ~50 natural classes, ~30 rules, ~5 strata, ~500 environments per project. Phase 3a is sized for this.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Justification |
|-----------|--------|---------------|
| I. FLEx Domain Fidelity | PASS | GUID preservation is the default; identity_remap is the documented fallback for factories lacking Guid overloads. GOLD inviolability not directly relevant (no phonology GOLD catalog), but `CatalogBackedMixin` exists for any catalog-backed phonology entities discovered during MCP probing. Cross-references resolve or skip with `DEPENDENCY_UNRESOLVED` per FR-304. |
| II. flexicon-Direct | PASS | Every new callback imports `flexicon` directly. No `flavors/`. Strata, lacking a dedicated `StratumOperations`, use `project.GetService(IMoStratumFactory)` which is the documented Direct fallback per the constitution. |
| III. Preview-Before-Mutate | PASS | Five callbacks per category match the existing pattern: enumerate_source / dependencies / required_writing_systems / plan_action all read-only; only execute_action writes. |
| IV. Phased Merge Discipline | PASS | Phase 3a is ordered behind Phases 0-2 (already shipped). FR-309..311 require Phase 1 + Phase 2 semantics to apply unchanged; FR-311 explicitly forbids modifying existing Phase 0/1/2 paths. |
| V. Referential Completeness | PASS | FR-304 enforces dependency closure for phonological rules → phonemes + natural classes. NaturalClass.SegmentsRC and feature-struct dependencies handled by their respective categories preceding (#3 phonemes, #2 phon features). |

**No violations. No Complexity Tracking entries required.**

### Re-check after Phase 1 design

| Principle | Status | Notes |
|-----------|--------|-------|
| I. | PASS | data-model.md entities map cleanly to LCM types. |
| II. | PASS | contracts/category-callbacks.md uses flexicon Operations + GetService(IFooFactory) — both Principle-II-sanctioned. |
| III. | PASS | quickstart.md exercises Preview (no writes) first, then Move. |
| IV. | PASS | quickstart.md's Scenario E confirms Phase 0/1/2 unchanged. |
| V. | PASS | Phonological-rule dependency closure documented in data-model.md. |

## Project Structure

### Documentation (this feature)

```text
specs/005-phonology-block/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── category-callbacks.md
│   └── phonology-rule-dependencies.md
├── checklists/
│   └── requirements.md  # Spec quality checklist (green)
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
src/gramtrans/Lib/
├── models.py                # +5 GrammarCategory enum members
│                            # (PHONOLOGICAL_FEATURES, PHONEMES,
│                            #  NATURAL_CLASSES, PHONOLOGICAL_RULES,
│                            #  STRATA -- ph_environment already exists)
├── categories.py            # MOD: 5 new (category, 5-callback) registry
│                            # entries -- plus relocation of
│                            # ph_environment from allomorph-bundled to
│                            # standalone (FR-307 idempotency)
├── preview.py               # MOD: build_run_plan iterates the new
│                            # categories via the existing registry
│                            # dispatch; no special wiring needed
├── transfer.py              # MOD: execute() dispatches per-category;
│                            # existing _execute_overwrite handles Phase 1
│                            # writes via category callbacks
├── conflict.py              # NO CHANGES (the new categories use the
│                            # existing collect_overwrite_conflicts
│                            # by virtue of going through the planner)
└── ws_mapping.py            # NO CHANGES

tests/
├── unit/
│   ├── test_categories_phon_features.py   # NEW
│   ├── test_categories_phonemes.py        # NEW
│   ├── test_categories_natural_classes.py # NEW
│   ├── test_categories_ph_environments.py # NEW (idempotency w/ Phase 0)
│   ├── test_categories_phon_rules.py      # NEW (incl. FR-304 dep skip)
│   ├── test_categories_strata.py          # NEW
│   └── (existing 267 tests)               # unchanged
└── integration/
    └── test_phase3a_phonology_e2e.py      # NEW: full phonology run
                                           # against fake LCM surface
```

**Structure Decision**: Single project, FLExTrans-style flat entry + `Lib/` siblings. No new top-level packages. Phase 3a is overwhelmingly additive — the existing registry pattern (5 callbacks per category) absorbs all 6 new categories without restructure. The only "moved" code is the ph_environment relocation (FR-307), which is a logical move — physically the environment-creation function stays in `Lib/categories.py` but its placement in the ordered plan shifts from "with allomorphs" to "before phonological rules."

## Complexity Tracking

> Constitution Check passed with no violations.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| _(none)_  | _(none)_   | _(none)_                            |

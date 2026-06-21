# Implementation Plan: Phase 3b — Inflection / Lexicon-Prep Block

**Branch**: `006-inflection-prep-block` | **Date**: 2026-06-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-inflection-prep-block/spec.md`

## Summary

Wire nine project-level configuration categories (memo steps 6-13b) through the existing `_LEAF_DISPATCH_CATEGORIES` loop that landed in commit 608b72c. Five callbacks are already implemented and hardened in `Lib/categories.py` (gram_categories, inflection_features, inflection_classes, stem_names, exception_features — orphan-safe per 3863ed2); Phase 3b extends the dispatch tuple to include them, fills three stub categories (custom_fields, variant_types, complex_form_types), and adds one new enum + callback set (semantic_domains). None of the nine touch LexEntry directly — Phase 0/1/2/3a paths stay bit-identical.

Technical approach: Per Phase 3a's template, MCP-probe each factory used by the three new + one new-enum category at planning time to confirm `Create(Guid)` support; categories whose factories lack Guid overloads fall back to `identity_remap` per FR-303. Custom fields use FLEx's `MetaDataCacheAccessor.AddCustomField` since they aren't first-class LCM objects with a factory. Semantic domains use `IFsPossibilityListFactory` for the project-level list (already exists) and standard `CmPossibility` ownership via `PossibilitiesOS`. Re-use Phase 3a's `_create_with_guid` + `_safe_add_to_owner` helpers verbatim.

## Technical Context

**Language/Version**: Python 3.12.

**Primary Dependencies**:
- `flexlibs2` (MattGyverLee fork) — direct LCM access per constitution Principle II. Pre-existing Operations classes already used by the five COMPLETE callbacks: `POSOperations`, `InflectionFeatureOperations`, `InflectionClassOperations`, `StemNameOperations`, `ExceptionFeatureOperations` (paths in `flexlibs2/code/Grammar/`). For the three stubs + new category, MCP probe at planning time to confirm exact accessor surface: variant types and complex form types live under `project.LexDb.VariantEntryTypesOA` / `ComplexEntryTypesOA`; custom fields go through `project.Cache.MetaDataCacheAccessor.AddCustomField(class, name, type, ...)`; semantic domains under `project.LangProject.SemanticDomainListOA.PossibilitiesOS`.
- `SIL.LCModel` interfaces (lazy-imported): `IPartOfSpeech`, `IFsClosedFeature`, `IMoInflClass`, `IMoStemName`, `IFsSymFeatVal`, `ILexEntryType` (variants + complex forms), `ICmSemanticDomain`, plus factories. `MetaDataCacheAccessor` for custom fields.

**Storage**: No new storage. State lives in target LCM objects + the existing residue tag.

**Testing**:
- `pytest` unit tests. Five new test files for the three stubs + one new category + a leaf-dispatch wiring test:
  `test_categories_custom_fields.py`, `test_categories_variant_types.py`, `test_categories_complex_form_types.py`, `test_categories_semantic_domains.py`, `test_phase3b_leaf_dispatch.py`. The five COMPLETE categories already have unit coverage in the Phase 0 test files; Phase 3b adds dispatch-integration tests, not callback-shape tests for them.
- Live MCP verification on `Ejagham Mini` → `Ejagham Full GT-Test` exercising all nine categories with Phase 0 additive and Phase 1 overwrite paths.

**Target Platform**: Same as Phases 0-2/3a — Windows desktop FlexTools host (pythonnet + LCM 9.x).

**Project Type**: FlexTools-compatible Python module. Single project; flat entry + `src/gramtrans/Lib/` siblings.

**Performance Goals**:
- SC-321: 2-POS hierarchy + 30 inflection features + 10 inflection classes + 6 stem names + 4 exception bearings + 3 custom fields + 4 variant types + 2 complex form types + 5 custom semantic domains transfer in under 5 seconds wall-clock.
- Per-category `enumerate_source` < 100ms for inventories under 1000 items each (semantic domains is the largest realistic inventory — ~1700 standard catalog + custom).

**Constraints**:
- Constitution Principle II: flexlibs2-Direct.
- Principle III: Preview-Before-Mutate — every new `plan_action` runs during `build_run_plan`, no LCM writes.
- Principle IV: additive over Phases 0/1/2/3a — no earlier-phase path removed.
- Standard FW catalog detection on semantic domains MUST use `CatalogSourceId` non-empty (the existing `_is_gold` heuristic). ~1700 standard FW semantic domains MUST be skipped on every run.
- Custom fields use a non-factory creation path (`MetaDataCacheAccessor.AddCustomField`); the planner's `_create_with_guid` helper doesn't apply. The custom-field execute path is a direct MDC call wrapped in fail-loud per the same orphan-guard discipline.

**Scale/Scope**:
- Realistic ceiling per category: ~50 POSes, ~50 inflection features × ~10 values each, ~10 custom fields, ~50 inflection classes, ~30 stem names, ~10 exception bearings, ~50 variant types, ~20 complex form types, ~50 custom semantic domains. Phase 3b sized for this.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Justification |
|-----------|--------|---------------|
| I. FLEx Domain Fidelity | PASS | GUID preservation is default; identity_remap is the documented fallback. GOLD inviolability is central to Phase 3b — FR-324 reaffirms `Skip(GOLD_INVIOLABLE)` for POS, inflection features, and (per FR-326) semantic-domain catalog entries. The five COMPLETE callbacks already honor this; the three new + one new-enum follow the same `_is_gold` check. |
| II. flexlibs2-Direct | PASS | All callbacks import `flexlibs2` directly. Custom fields' `MetaDataCacheAccessor` is the documented LCM-direct path for non-first-class objects (analogous to Strata's `GetService(IMoStratumFactory)` Direct-fallback in Phase 3a). |
| III. Preview-Before-Mutate | PASS | Five-callback shape preserved across all nine categories. |
| IV. Phased Merge Discipline | PASS | Phase 3b ordered behind 0-2-3a. FR-328..330 require Phase 1 + Phase 2 + FR-308 semantics to apply unchanged; FR-331 explicitly forbids modifying earlier-phase paths. |
| V. Referential Completeness | PASS | FR-327 enforces dependency closure for variant types → inflection features; existing exception-features `dependencies` callback already enforces POS + IFsSymFeatVal closure; custom-field target-class validity handled in `plan_action`. |

**No violations. No Complexity Tracking entries required.**

### Re-check after Phase 1 design

| Principle | Status | Notes |
|-----------|--------|-------|
| I. | PASS | data-model.md maps the nine categories cleanly to LCM types and clarifies GOLD detection per-category. |
| II. | PASS | contracts/category-callbacks.md uses flexlibs2 Operations classes for 8 of 9; custom_fields uses `MetaDataCacheAccessor.AddCustomField` (LCM-direct). |
| III. | PASS | quickstart.md exercises Preview first, then Move. |
| IV. | PASS | quickstart.md Scenario E confirms Phase 0/1/2/3a unchanged. |
| V. | PASS | Variant-type → inflection-feature dependency documented in data-model.md. |

## Project Structure

### Documentation (this feature)

```text
specs/006-inflection-prep-block/
|-- plan.md              # This file
|-- research.md          # Phase 0 output (MCP-probe results for new categories)
|-- data-model.md        # Phase 1 output
|-- quickstart.md        # Phase 1 output
|-- contracts/           # Phase 1 output
|   |-- category-callbacks.md
|   `-- custom-field-creation.md
|-- checklists/
|   `-- requirements.md  # Spec quality checklist (green)
`-- tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
src/gramtrans/Lib/
|-- models.py                # +1 GrammarCategory enum member
|                            # (SEMANTIC_DOMAINS -- other 8 already exist)
|-- categories.py            # MOD: 4 new (category, 5-callback) registry
|                            # entries (custom_fields, variant_types,
|                            # complex_form_types, semantic_domains).
|                            # 5 existing COMPLETE callbacks unchanged.
|-- preview.py               # MOD: extend _LEAF_DISPATCH_CATEGORIES
|                            # to include the 9 Phase 3b categories.
|-- transfer.py              # MOD: same _LEAF_DISPATCH_CATEGORIES
|                            # extension for the executor side.
|-- conflict.py              # NO CHANGES
`-- ws_mapping.py            # NO CHANGES

tests/
|-- unit/
|   |-- test_categories_custom_fields.py      # NEW
|   |-- test_categories_variant_types.py      # NEW
|   |-- test_categories_complex_form_types.py # NEW
|   |-- test_categories_semantic_domains.py   # NEW
|   |-- test_phase3b_leaf_dispatch.py         # NEW
|   `-- (existing 305 tests)                  # unchanged
`-- integration/
    `-- test_phase3b_inflection_e2e.py        # NEW: 9-category run
                                              # against fake LCM surface
```

**Structure Decision**: Single project, FLExTrans-style flat entry + `Lib/` siblings. Phase 3b is overwhelmingly additive — the existing registry + leaf-dispatch pattern absorbs all nine categories. The bulk of new code is concentrated in three stub fills (custom_fields, variant_types, complex_form_types), one new category (semantic_domains), and the two-line `_LEAF_DISPATCH_CATEGORIES` tuple extensions in `preview.py` and `transfer.py`.

## Complexity Tracking

> Constitution Check passed with no violations.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| _(none)_  | _(none)_   | _(none)_                            |

# Phase 3b Quickstart — Validation Scenarios

Five live-MCP scenarios exercising the nine Phase 3b categories against
`Ejagham Mini` (source) → `Ejagham Full GT-Test` (target). All scenarios
run via [src/gramtrans/__init__.py](../../src/gramtrans/__init__.py)'s
`MainFunction` entry point through `flextools_run_module`. Scenarios A-D
are the Phase 3a-style live-verification quartet; Scenario E confirms
no Phase 0/1/2/3a regression.

## Prerequisites

- flexicon fork installed editable: `pip install -e D:/Github/_Projects/_LEX/flexicon`
- FlexTools MCP session started against `Ejagham Full GT-Test` with write enabled.
- Phase 3a six-category dispatch verified (`pytest tests/integration/test_phase3a_phonology_e2e.py` green).
- Target snapshot taken via `git`-style backup before Scenario B (overwrite re-run is destructive on identity_remap-fallback objects).

## Scenario A — Additive transfer of all nine categories

**Setup**: Source has populated POS hierarchy (2-3 non-GOLD POSes), 30 inflection features, 3 custom fields, 10 inflection classes, 6 stem names, 4 exception-feature bearings, 4 variant types, 2 complex form types, 5 custom semantic domains. Target has empty `PartsOfSpeechOA`, empty `MsFeatureSystemOA`, empty `LexDbOA.VariantEntryTypesOA`, etc. (or just FW's GOLD entries).

**Run**: `MainFunction(report)` with default Selection including all nine Phase 3b categories, `enable_overwrite=False`.

**Expected outcomes**:
- `report.per_category[GRAM_CATEGORIES].added` == 2-3 (non-GOLD POSes)
- `report.per_category[GRAM_CATEGORIES].skipped` == GOLD POS count (Verb, Noun, etc.)
- `report.per_category[INFLECTION_FEATURES].added` == custom features (non-GOLD)
- `report.per_category[CUSTOM_FIELDS].added` == 3
- `report.per_category[INFLECTION_CLASSES].added` == 10
- `report.per_category[STEM_NAMES].added` == 6
- `report.per_category[EXCEPTION_FEATURES].added` == 4
- `report.per_category[VARIANT_TYPES].added` == custom variants (non-GOLD)
- `report.per_category[COMPLEX_FORM_TYPES].added` == custom complex forms (non-GOLD)
- `report.per_category[SEMANTIC_DOMAINS].added` == 5
- `report.per_category[SEMANTIC_DOMAINS].skipped` == ~1700 GOLD entries from FW standard catalog
- 0 `DEPENDENCY_UNRESOLVED` skips
- All new objects in target have source GUIDs (or identity_remap entry per FR-303)
- Wall clock < 5 seconds (SC-321)

## Scenario B — Phase 1 overwrite re-run

**Setup**: Immediately after Scenario A. Source un-modified, target carries all the Phase 3b objects from Scenario A.

**Run**: `MainFunction(report)` with `enable_overwrite=True`.

**Expected outcomes**:
- All non-GOLD non-empty source objects emit `PlannedOverwrite` (since GUID matches existing in target).
- `report.per_category[*].overwritten` reflects per-category counts; `added` ~ 0.
- Custom fields: 0 PlannedOverwrites (custom fields use `(class_id, name)` sync check — already-synced records emit no action).
- Residue tag on each overwritten object now carries `snap=<base64>` per FR-106.

## Scenario C — Dependency closure for variant types with feature constraints

**Setup**: Source has a variant type referencing an `IFsSymFeatVal` that's GOLD-skipped on the inflection-features pass (because the parent feature is GOLD). Target's GOLD catalog already contains the value by canonical GUID.

**Run**: `MainFunction(report)` with VARIANT_TYPES + INFLECTION_FEATURES selected.

**Expected outcomes**:
- Variant type lands successfully — its `InflFeatsOS` constraint references target's existing GOLD `IFsSymFeatVal` by GUID.
- 0 `DEPENDENCY_UNRESOLVED` skips on VARIANT_TYPES.

**Negative case (variant constraint refers to a value NOT present in target NOR in plan)**: emit `Skip(DEPENDENCY_UNRESOLVED)` per FR-327; rest of variant-type batch continues.

## Scenario D — Empty-source UX (FR-308 inherited)

**Setup**: Source has zero POSes, zero inflection features, zero custom fields, zero of all nine Phase 3b categories. (Practically: pick a source project that's phonology-only or freshly-spawned.)

**Run**: `MainFunction(report)` with all nine Phase 3b categories selected.

**Expected outcomes**:
- `render_text_summary(report)` emits 9 `[skip] no items in source for X` lines.
- 0 errors, 0 actions, 0 mutations to target.

## Scenario E — Phase 0/1/2/3a regression check

**Setup**: A separate target project with verb-vertical content from Phase 0 era. Source is a Phase-0-shape verb-vertical source.

**Run**: `MainFunction(report)` with ONLY Phase 0/1/2/3a categories selected (no Phase 3b ticks).

**Expected outcomes**:
- Bit-identical behaviour to pre-Phase-3b: same actions, same skips, same residue. Phase 3b code paths produce zero side effects.
- Validated by snapshot diff on `report.to_snapshot_json()` against the Phase 3a-era baseline.

## Smoke-test commands

```powershell
# unit
pytest tests/unit/test_categories_custom_fields.py tests/unit/test_categories_variant_types.py tests/unit/test_categories_complex_form_types.py tests/unit/test_categories_semantic_domains.py tests/unit/test_phase3b_leaf_dispatch.py -v

# integration (fake LCM surface)
pytest tests/integration/test_phase3b_inflection_e2e.py -v

# full regression (Phase 0+1+2+3a+3b)
pytest -q
```

## Done when

- [ ] All five scenarios pass with expected outcomes
- [ ] Wall clock under 5 seconds for Scenario A
- [ ] `report.to_snapshot_json()` for Scenario E matches Phase 3a baseline
- [ ] No `DEPENDENCY_UNRESOLVED` skips in Scenarios A or C positive case
- [ ] No regressions in the existing 305-test unit suite

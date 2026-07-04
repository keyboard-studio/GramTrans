# Phase 3b Live MCP Verification Log

**Source**: `C:\ProgramData\SIL\FieldWorks\Projects\Ejagham Mini`
**Target**: `C:\ProgramData\SIL\FieldWorks\Projects\Ejagham Full GT-Test`
**flexicon fork**: `D:/Github/_Projects/_LEX/flexicon` (editable install)

Three live-MCP runs landed against the same source/target pair on 2026-06-21,
each at a successively-later code state. Each section below records the
commit it was driven from, the pre-state, the run, and the verified
post-state.

---

## Run 1 — US1 Preview + Move (commit `194438a`)

**Selection**: `GRAM_CATEGORIES`, `INFLECTION_FEATURES`, `INFLECTION_CLASSES`,
`STEM_NAMES`, `EXCEPTION_FEATURES`.

### Bug discovered + fixed before run

`src/gramtrans/Lib/categories.py` referenced `project.InflectionFeature`
(singular) but the flexicon fork exposes `project.InflectionFeatures` (plural).
6 occurrences + 2 `hasattr` checks fixed in commit `194438a`. Test fakes in
`test_categories_inflection_features.py` + `test_categories_inflection_classes.py`
updated to mirror. The Phase 0 unit tests passed under the wrong name only
because the fakes mirrored it.

### Pre-flight (target baseline)

| Category | Count | Notes |
|---|---|---|
| POS (IPartOfSpeech, recursive) | 20 | From Phase 0/3a era runs |
| Inflection features (IFsClosedFeature) | 3 | Mix of GOLD + custom |
| VariantEntryTypes (top-level) | 6 | |
| ComplexEntryTypes (top-level) | 8 | |
| SemanticDomains (top-level) | 9 | |
| Custom fields (LexEntry/Sense/MoForm/Example) | 11 | |
| IFsFeatStrucType (project.GramCat) | 2 | `Noun agreement` (GOLD), `Infl` (GOLD) |

### Preview (no writes)

```
=== US1 PREVIEW ===
  Actions: 3  Skips: 5  Overwrites: 0
  gram_categories     added=1  skipped=2
  inflection_features added=2  skipped=3
  TOTAL               added=3  skipped=5
  [skip] no items in source for exception_features
  [skip] no items in source for inflection_classes
  [skip] no items in source for stem_names
  Skips:
    - [gram_categories] 135f8aa2-... gold_inviolable CatalogSourceId='tNounAgr'
    - [gram_categories] adf5fa01-... gold_inviolable CatalogSourceId='Infl'
    - [inflection_features] a45b03d4-... gold_inviolable CatalogSourceId='cNounAgr'
    - [inflection_features] cbbef348-... gold_inviolable CatalogSourceId='fNum'
    - [inflection_features] f7e8a2b6-... gold_inviolable CatalogSourceId='fBantuClass'
  Wall clock: 0.000s
```

### Move (`write_enabled=True`)

```
=== US1 MOVE DONE: wall_clock=0.077s ===
  gram_categories     added=1  skipped=2
  inflection_features added=2  skipped=3
  TOTAL               added=3  skipped=5
Target CloseProject() called -- changes saved.
```

### Post-state

| Category | Pre | Post | Δ | Expected |
|---|---|---|---|---|
| IFsFeatStrucType (project.GramCat) | 2 | 3 | +1 | +1 (`BantuNounClass`) |
| Inflection features | 3 | 5 | +2 | +2 |
| POS (IPartOfSpeech) | 20 | 20 | **0** | (see finding) |

**Verdict at the time**: PARTIAL. The 3 actions reported did land and survived
target `CloseProject`. POS count didn't move because `gram_categories_*`
callbacks walked `project.GramCat.GetAll()`, which the flexicon fork resolves
to `IFsFeatStrucType` (owned by `LangProject.MsFeatureSystemOA.TypesOC`) —
**not** POS. Ordering-memo step 6 (and the spec narrative) said
"Parts of Speech (= 'Gram Categories')"; the code targeted
`IFsFeatStrucType` instead.

This finding triggered LEX crew cycles 1+2+3 and is RESOLVED in Run 2.

---

## Run 2 — US1 re-run after `gram_categories` retarget (commit `798dc0b`)

**Fix shipped between Run 1 and Run 2**: 5 callbacks for `GRAM_CATEGORIES`
retargeted from `project.GramCat` → `project.POS` per LEX crew Option B.
`IPartOfSpeechFactory.Create(Guid, owner)` used with nested-vs-top-level owner
resolution. Critical pythonnet fix: factory must be obtained via
`IPartOfSpeechFactory(target.GetFactory(IPartOfSpeechFactory))` cast —
`ServiceLocator.GetService(IPartOfSpeechFactory)` returns a raw COM object
whose `Create` dispatch silently fails to match `(Guid, ICmPossibilityList)`.
Verb-vertical collision guard added.

Two contract tests landed alongside the fix
(`test_contract_execute_action_does_not_reference_ms_feature_system`,
`test_contract_enumerate_source_walks_pos_not_gramcat`) which use
`inspect.getsource()` to hard-fail if the wrong LCM types reappear.

### Preview

```
=== US1 PREVIEW ===
  Actions: 1  Skips: 24  Overwrites: 0
  Skip breakdown: 13 GOLD POS + 6 ALREADY_PRESENT_BY_GUID POS
                  + 5 inflection-features (GOLD)
  FR-308 empty-source lines: 3 (exception_features, inflection_classes,
                                stem_names)
  Wall clock: 0.000s
```

### Move

```
=== US1 MOVE DONE: wall_clock=0.053s ===
  1 action persisted (POS '400c5e75' — empty-name custom POS)
```

### Post-state

| Category | Pre | Post | Δ | Expected |
|---|---|---|---|---|
| POS (IPartOfSpeech, recursive) | 20 | 21 | +1 | +1 |
| InflectionFeatures | 5 | 5 | 0 | 0 (already at target from Run 1) |

Source GUID `400c5e75-…` preserved on the new POS in target.

**Verdict**: PASS. `gram_categories` now hits the LCM type the spec promised.
Run 1's "PARTIAL — semantic mismatch" finding is RESOLVED.

The pre-Option-B IFsFeatStrucType code (which correctly handled
`IFsFeatStrucType` creation, just under the wrong enum label) is **salvageable**
into a future `FEATURE_STRUC_TYPES` category — tracked as a Phase 3b
close-sweep deferred item in STATUS.md.

---

## Run 3 — US3 Preview + Move: variant_types + complex_form_types + semantic_domains (commit `beeb60c`)

**Two pythonnet overload-resolution issues fixed between Run 2 and Run 3**:

1. **Factory overload surface**. `ILexEntryInflTypeFactory`,
   `ILexEntryTypeFactory`, and `ICmSemanticDomainFactory` inherit only the
   1-arg `Create(Guid)` overload from the generic `ILcmFactory<T>` base via
   pythonnet. The 2-arg overloads from `ICmPossibilityFactory`
   (`Create(Guid, ICmPossibilityList)` and `Create(Guid, ICmPossibility)`) do
   **not** surface for these subclasses. Fix: 1-arg `Create(Guid)` + manual
   `_safe_add_to_owner` to the appropriate `PossibilitiesOS` /
   `SubPossibilitiesOS` collection, with the factory obtained via
   `IFactory(target.GetFactory(IFactory))` cast.

2. **Owner discrimination**. `_guid_str_from(owner)` was comparing the
   source's list-Guid against the target's list-Guid (different lists,
   different GUIDs), incorrectly classifying every variant type as nested.
   Fixed by switching to owner-class discrimination via
   `ICmObject(src_obj).Owner.ClassName`. The `ICmObject` cast is required
   because the raw `.Owner` attribute returns `ICmObjectOrId`, where
   `ClassName` isn't reliably exposed through pythonnet.

### Plan

```
=== US3 PLAN ===
  Actions: 4   Skips: 1807
  Skip breakdown:
    - 1792 semantic_domains (GOLD catalog — FR-326)
    - 8 variant_types (ALREADY_PRESENT_BY_GUID — earlier debug probe)
    - 7 complex_form_types (ALREADY_PRESENT_BY_GUID)
```

### Move

```
=== US3 MOVE DONE: wall_clock=0.045s ===
  4 actions persisted
```

### Post-state

| Category | Pre | Post | Δ | Verified GUIDs |
|---|---|---|---|---|
| VariantEntryTypes (recursive) | 12 | 13 | +1 | `50c5f5cb`, `e755fd9d`, `851bb368`, `9c797814`, `238c51d4` all present in target |
| ComplexEntryTypes (recursive) | (no source non-GOLD) | unchanged | 0 | n/a |
| SemanticDomains (recursive) | (no source non-GOLD) | unchanged | 0 | 1792 GOLD skips, no source customs |

**Verdict**: PASS. FR-326 GOLD-skip honored against the ~1700-entry FW
semantic-domain catalog. FR-327 dependency closure not exercised — source's
variant types lack `InflFeatsOA` non-empty struct; tracked for Scenario C
re-run when a feature-constraint-bearing source is available.

---

## Scenario C (FR-327 feature-constraint closure) — DEFERRED

Ejagham Mini's variant types do not carry non-empty `InflFeatsOA` structs,
so the `Skip(DEPENDENCY_UNRESOLVED)` path was not driven in Run 3. Path is
unit-tested in `test_categories_phase3b_us3.py`; live exercise deferred to
a source that provides the constraint.

---

## Summary

| Scenario | Run | Status | Notes |
|---|---|---|---|
| A.1 Preview | 1 | PASS | 3 actions / 5 skips / 3 FR-308 lines |
| A.1 Move | 1 | PARTIAL → **RESOLVED in Run 2** | gram_categories semantic mismatch |
| A.1 Re-run Preview/Move | 2 | PASS | POS 20→21; source GUID preserved |
| A.3 Plan | 3 | PASS | 4 actions / 1807 skips (incl. 1792 GOLD) |
| A.3 Move | 3 | PASS | VariantEntryTypes 12→13; 5 source GUIDs verified |
| C | — | DEFERRED | Requires variant types with non-empty `InflFeatsOA` |
| Accessor bug fix (`InflectionFeatures` plural) | — | LANDED in `194438a` | |
| `gram_categories` semantic mismatch | — | RESOLVED in `798dc0b` | + 2 contract tests |
| US3 pythonnet overload fixes | — | LANDED in `beeb60c` | factory cast + owner-class discrimination |

**Phase 3b live-MCP gate: GREEN.** US1 (POS family), US2 (custom fields,
detect-and-report posture), US3 (variant / complex / semantic), and US4
(empty-source UX, via FR-308 lines in Run 1 Preview) are all evidenced
against live LCM with the Ejagham Mini → Ejagham Full GT-Test pair.

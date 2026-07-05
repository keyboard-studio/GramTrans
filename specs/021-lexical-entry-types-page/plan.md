# Implementation Plan: Lexical-Entry Types Page (Model-B Independent Block)

**Branch**: `021-lexical-entry-types-page` | **Date**: 2026-07-05 | **Spec**: [spec.md](./spec.md)

## Summary

Add the **Lexical-Entry Types** wizard page — the second Model-B (independent-block)
selector — at position 6 (after Grammatical deps, before Finish). A pure builder
enumerates the two entry-type categories (Variant Types, Complex Form Types) from the
source, walking their `VariantEntryTypesOA` / `ComplexEntryTypesOA` possibility lists
recursively, all user-defined items preselected (ALL by default), each with
008/009/010 target-status. The user toggles the whole block off or trims individual
types. Inflection-feature dependencies travel automatically (FR-327 already in
`variant_types_dependencies`). Missing references are routed to the shared Move gate.

Delivering per-item trim (FR-005/US2, P1) requires **one contained engine touch**
mirroring spec 010: add `Selection.leaf_item_picks` entries for
`GrammarCategory.VARIANT_TYPES` and `GrammarCategory.COMPLEX_FORM_TYPES`, honored by
the two `enumerate_source` helpers. The field already exists in `models.py`; only the
two enumerate helpers need the filter (absent key => transfer all — every existing
caller unchanged).

The **GOLD-detection gate** for entry types is isolated behind a single
`_is_gold_entry_type(node)` helper (see Workstream 4 below) to allow easy reswap if
`CatalogSourceId` proves unreliable for `ILexEntryType` / `ILexEntryInflType`.

Validated live target: Ejagham Mini -> Ejagham Full GT-Test (same pair as spec 010).

## Technical Context

**Language/Version**: Python 3 (FlexTools host). **Primary deps**: PyQt6,
MattGyverLee/flexicon fork, SIL.LCModel via pythonnet. **Testing**: pytest (fake
handles) + live FlexTools MCP. **Project type**: FLExTrans-style flat `Lib/`.
**Constraints**: pure builder (fake-handle testable); LCM access via the existing
cast/`getattr` guards; the engine enumerate-filter is guarded so absent-subset
preserves all-items behavior. **Scale/Scope**: possibility-list walk, two categories.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- **I. FLEx Domain Fidelity** -- PASS. Read-only derivation; GUID identity; correct
  LCM anchors (`LexDbOA.VariantEntryTypesOA`, `LexDbOA.ComplexEntryTypesOA`);
  recursive `_walk_possibilities_via_lexdb` already implemented and verified.
- **II. flexicon-Direct** -- PASS. Direct imports; no adapter; enumerate helpers
  already call `_walk_possibilities_via_lexdb(context.source_handle, ...)`.
- **III. Preview-Before-Mutate** -- PASS. The page builds a `Selection` only; the
  sole write stays in the page-Finish Move handler.
- **IV. Phased Merge Discipline** -- PASS. No conflict-mode UI; Layer-1 defaults
  applied automatically (FR-012 / SC-008).
- **V. Referential Completeness** -- PASS (central). Whole block preselected
  (closure-by-default); per-item trim allowed; a kept `ILexEntryInflType` whose
  inflection-feature ref is absent from target raises an aggregated missing-ref
  warning gated once at Move -- never silent.

## Project Structure

### Documentation (this feature)

```text
specs/021-lexical-entry-types-page/
├── plan.md              # this file
└── tasks.md             # TDD task list
```

### Source Code (repository root)

```text
src/gramtrans/Lib/
├── categories.py        # EXTEND variant_types_enumerate_source (1066-1069) and
│                        #   complex_form_types_enumerate_source (1219-1222) to filter
│                        #   _walk_possibilities_via_lexdb() result by
│                        #   selection.leaf_item_picks.get(cat) when not None
│                        #   (same pattern as _phonology_simple_enumerate).
│                        # ADD _is_gold_entry_type(node) helper: delegates to _is_gold,
│                        #   isolated for reswap (see GOLD-detection gate below).
├── selection.py         # ADD build_entry_types_inventory(source, target=None)
│                        #   -> EntryTypesInventory (frozen dataclass)
│                        # ADD EntryTypesRow, EntryTypesCategoryGroup, EntryTypesInventory
│                        #   dataclasses, mirroring PhonologyRow/PhonologyCategoryGroup/
│                        #   PhonologyInventory (selection.py:2060-2085)
│                        # ADD collapse_entry_types(inventory, checked_by_category) -> dict
│                        # ADD _entry_types_target_sets helper
│                        # ADD entry_types_missing_ref_warnings helper (FR-010/FR-011)
└── ui/selection_wizard.py  # ADD _PageEntryTypes at index 5 (after gram_deps, before finish)
                            # EXTEND SelectionWizard.__init__ page list: insert
                            #   self._page_entry_types = _PageEntryTypes() and
                            #   self.addPage(self._page_entry_types) after gram_deps (idx 4)
                            # ADD page_entry_types() named accessor
                            # EXTEND _build_preview_selection to merge entry-types collapse
                            # EXTEND _PageFinish._on_move to include entry-types missing-ref count
                            # UPDATE step titles: "Step N of 7" (was "of 6")

tests/
├── unit/
│   ├── _fakes_phonology.py               # EXTEND with FakeEntryType, FakeInflEntryType,
│   │                                     #   FakeEntryTypeSource (VariantEntryTypesOA /
│   │                                     #   ComplexEntryTypesOA nodes with .guid, .Guid,
│   │                                     #   .Name, .InflFeatsOA for ILexEntryInflType,
│   │                                     #   settable .CatalogSourceId for GOLD testing)
│   ├── test_leaf_item_picks_entry_types.py  # NEW: filter tests mirroring test_leaf_item_picks.py
│   ├── test_entry_types_inventory.py        # NEW: builder tests (dataclasses, counts, preselect,
│   │                                        #   target-status, empty category, hierarchy)
│   ├── test_entry_types_display.py          # NEW: UI render + whole-block toggle tests (no-Qt guard)
│   └── test_wizard_page_order.py            # EXTEND: assert page_entry_types accessor + 7-page order
```

## Workstreams and Key Decisions

### Workstream 1 -- Thread selection into enumerate helpers

Add `selection` threading + `leaf_item_picks` filter to:

- `variant_types_enumerate_source` (categories.py:1066-1069,
  `GrammarCategory.VARIANT_TYPES`)
- `complex_form_types_enumerate_source` (categories.py:1219-1222,
  `GrammarCategory.COMPLEX_FORM_TYPES`)

Copying the **exact precedent** from `_phonology_simple_enumerate` (categories.py:1594):

```python
picks = selection.leaf_picks_for(category)  # None -> transfer all
if picks is not None:
    records = [r for r in records if _guid_str_from(r) in picks]
```

**P0 GUID DISCIPLINE** (spec-010 lesson): normalize via `_guid_str_from` on BOTH sides.
Do NOT use raw `.Guid` on either side. Empty-user-defined-list (picks is empty
`frozenset`) must NOT be collapsed to GOLD-only list -- FR-006 "show empty, don't
block" applies.

Churn constraint: edit ONLY `variant_types_enumerate_source` (1066-1069) and
`complex_form_types_enumerate_source` (1219-1222). Do not refactor
`_walk_possibilities` / `_walk_possibilities_via_lexdb` signatures.

### Workstream 2 -- _PageEntryTypes wizard page

Model on `_PageGramDeps` (selection_wizard.py:1851, title at 1869) and `_PagePhonology`
(selection_wizard.py:2154). Key structural choices:

- Two category groups: "Variant Types (N)" and "Complex Form Types (N)"
- Tree renders hierarchy (SubPossibilitiesOS children as tree-child items)
- Whole-block tristate toggle (`_whole_block` QCheckBox, identical pattern to _PagePhonology)
- Per-item checkable rows with GUID stored in data role
- Target-status column (NEW / IN TARGET / SIMILAR), blank when no target
- No ADD_NEW/MERGE/OVERWRITE controls (FR-012 / SC-008)
- Step title: "Step 6 of 7: Lexical-Entry Types"

Page insertion: append `page_entry_types` AFTER `page_gram_deps` (idx 4), BEFORE
`page_finish` (previously idx 5, now idx 6). Step-count labels across all pages change
from "of 6" to "of 7"; reconciliation is done in a single pass in this feature to avoid
merge fragility with 018/019.

### Workstream 3 -- Entry-types inventory builder

Mirror `build_phonology_inventory` (selection.py:2175) and the frozen
`PhonologyInventory` dataclass (selection.py:2070-2085):

```python
@dataclass(frozen=True)
class EntryTypesRow:
    guid: str
    label: str
    runs: tuple          # WS-font runs for display
    status: Optional[str]  # "new" | "in_target" | "similar" | None
    preselected: bool
    category: GrammarCategory
    depth: int           # 0=top-level, 1=child, etc. (for tree nesting)

@dataclass(frozen=True)
class EntryTypesCategoryGroup:
    category: GrammarCategory
    label: str
    rows: Tuple[EntryTypesRow, ...]

@dataclass(frozen=True)
class EntryTypesInventory:
    groups: Tuple[EntryTypesCategoryGroup, ...]
    # For FR-010 missing-ref derivation: variant_type_guid -> frozenset[infl_feat_val_guid]
    variant_infl_feat_deps: Dict[str, FrozenSet[str]] = field(default_factory=dict)
```

Pure/read-only. All user-defined items preselected, GOLD items shown as in_target
(matched by identity). Target-status by-GUID (`in_target` if GUID present in target,
`new` otherwise; `similar` by name-match fallback). None when no target.

Walk: `VariantEntryTypesOA` via `_walk_possibilities_via_lexdb(source,
"VariantEntryTypesOA")` and `ComplexEntryTypesOA` similarly. Depth tracking: retain
the SubPossibilitiesOS parent-child structure for tree rendering (depth field on row).

Target-status helper `_entry_types_target_sets(target, accessor)` mirrors
`_phon_target_sets` (selection.py:2094-2142).

### Workstream 4 -- Move-gate aggregation (FR-010/FR-011)

For each kept `ILexEntryInflType` (variant type with `InflFeatsOA`), compute the
dependency chain:

```
InflFeatsOA -> FeatureSpecsOC[] -> ValueRA -> _guid_str_from(val)
-> (INFLECTION_FEATURES, val_guid)
```

Mirror `variant_types_dependencies` (categories.py:1072-1095), with guard
`if struct is None: return ()` already in place.

If a kept variant type's referenced inflection-feature value is:
- absent from target, AND
- not in the user's selection (leaf_item_picks for INFLECTION_FEATURES)

then emit one missing-reference warning per kept type, aggregated into the shared
`el_count` in `_PageFinish._on_move` (selection_wizard.py:2840), following the phonology
feed pattern (`_phonology_excluded_lossy_for` at ~2869).

### GOLD-Detection Gate (defensive)

`_is_gold` (categories.py:78-91) uses `getattr(obj, "CatalogSourceId", None)`. For
`ILexEntryType` / `ILexEntryInflType`, this attribute may be `None` even for GOLD
objects (unconfirmed behavior -- a lex-verification probe is running in parallel).

**Isolation strategy**: add `_is_gold_entry_type(node)` in `categories.py` that
currently delegates to `_is_gold`, with a clear TODO:

```python
def _is_gold_entry_type(node) -> bool:
    """GOLD detection for ILexEntryType / ILexEntryInflType.

    TODO (spec-021 GOLD-gate): CatalogSourceId may be None for entry types even
    when the type is GOLD-shipped. Until lex-verification confirms the attribute
    is reliable for ILexEntryType, this delegates to the generic _is_gold helper.
    If the probe shows CatalogSourceId is missing/None for GOLD entry types,
    replace this body with an identity-based detection:
        from SIL.LCModel import ICmObject
        obj_id = _guid_str_from(node)
        return obj_id in _KNOWN_GOLD_ENTRY_TYPE_GUIDS  # pre-populated set
    The GOLD path uses _plan_gold_reserved_edit (165-204) -> Skip(GOLD_INVIOLABLE);
    redefined-meaning source GOLD with differing GUID falls through as new user-defined.
    """
    return _is_gold(node)
```

The existing `variant_types_plan_action` and `complex_form_types_plan_action` already
call `_is_gold(piece)` and Skip(GOLD_INVIOLABLE). This feature adds
`_is_gold_entry_type` as the single reswap point for entry types specifically; the
existing plan_action functions continue to call `_is_gold` (they are NOT touched by
this feature). The builder (`build_entry_types_inventory`) uses `_is_gold_entry_type`
for inventory-side GOLD detection.

## Complexity Tracking

| Deviation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| Engine touch: `leaf_item_picks` for VARIANT_TYPES/COMPLEX_FORM_TYPES | Per-item trim (FR-005/US2, P1); field already on Selection | Whole-block-only rejected by user -- per-item trim is the defining Model-B affordance |
| `_is_gold_entry_type` helper isolation | CatalogSourceId may be unreliable for ILexEntryType per spec (probe running) | Calling _is_gold directly is not reswappable without editing both enumerate/plan callsites |
| Hierarchy (depth) in tree | ComplexFormTypes/VariantTypes are recursive possibility lists | Flat list would silently drop sub-type nesting visible in FLEx |
| Step-count "of 7" reconciliation | Inserting a 7th page before Finish; 018/019 siblings also bump this | Leaving it "of 6" after insertion is wrong UX; single reconcile point in this PR |

## Shared-Hotspot Merge Notes

These edits must be reconciled with sibling specs 018 (rules-page) and 019 (stems):

1. **`selection_wizard.py` page-insertion list** (~2977-2982): this feature inserts
   `_page_entry_types` at idx 5 (shifting old idx 5 `_page_finish` to idx 6). If 018
   or 019 also modify the page list, the merge is an ordered-list reconciliation.
2. **Named accessors block** (~2990-3013): add `page_entry_types()` returning
   `self._page_entry_types`. Additive; no conflict with existing accessors.
3. **Step-count labels ("of N")**: changing from "of 6" to "of 7" affects all existing
   pages. If 018/019 also change this, reconcile to the final N at integration time.
4. **`_build_preview_selection`** (~2700-2737): add entry-types collapse step. If 018
   or 019 add a similar step, each is additive (dict-merge pattern).
5. **`_PageFinish._on_move` el_count** (~2840-2869): add entry-types missing-ref count.
   Additive alongside phonology count. If 018/019 add their own counts, each
   `el_count +=` line is an additive single-line reconciliation.

## Known Limitations

- **KL-021-1**: GOLD detection via `CatalogSourceId` for `ILexEntryType` /
  `ILexEntryInflType` is unconfirmed (probe running). `_is_gold_entry_type` is the
  single reswap point; no GOLD entry type will be duplicated because the existing
  `plan_action` already emits `Skip(GOLD_INVIOLABLE)`. The builder renders GOLD types
  as `in_target` (matched by identity) -- the correct behaviour per spec clarification.
- **KL-021-2**: `variant_types_missing_ref_warnings` covers `InflFeatsOA ->
  FeatureSpecsOC -> ValueRA` only; it does NOT cover any other feature-structure
  references that may exist on `ILexEntryInflType`. Deferred to a post-021 follow-up.

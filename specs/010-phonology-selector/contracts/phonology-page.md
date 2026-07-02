# Contract: Phonology Page ↔ Engine

Defines the UI contract for `_PagePhonology`, the builder signature, and how the page's picks
merge into the `Selection` the Preview page builds. No code bodies — signatures + invariants.

## Builder (selection.py)

```
build_phonology_inventory(source, target=None) -> PhonologyInventory
```

- **Pure**: no writes; duck-typed `source`/`target` handles (fake-handle testable).
- Enumerates the five categories via the source's phonology accessors (`GetAll()`); computes
  each row's target-status by GUID (IN TARGET) / fingerprint (SIMILAR) / else NEW; blank
  (`None`) when `target is None`.
- Populates the reference maps (`rule_referenced_*`, `nc_referenced_*`,
  `phoneme_referenced_*`) for the EXCLUDED-LOSSY derivation.
- Empty category ⇒ empty `rows` (never raises).

## Wizard integration

### Page placement
- `_PagePhonology` is added at **index 1**; final order: `0` Project+WS, `1` Phonology,
  `2` Affixes, `3` Skeleton, `4` GramDeps, `5` Preview, `6` Finish. (FR-001 / SC-007)

### Cross-page lookups (refactor prerequisite)
- `SelectionWizard` exposes named accessors: `page_phonology()`, `page_items()`,
  `page_skeleton()`, `page_gram_deps()`, `page_preview()`, `page_finish()`.
- All existing `wizard.page(<literal>)` calls in `_PageSkeleton`, `_PageGramDeps`,
  `_PagePreview`, `_PageFinish` are replaced with the matching accessor. **Invariant**: no page
  may reference another page by literal index.

### Page state API (`_PagePhonology`)

```
initializePage()                        # build inventory from bound source+target; ALL preselected
collect_phonology_picks() -> dict        # {GrammarCategory: set[str] checked guids} for the 5 categories
whole_block_on() -> bool                 # convenience: any category has ≥1 checked row
deselected_needed_guids() -> frozenset   # preselected-but-unchecked guids (input to EXCLUDED-LOSSY)
```

- Opens **ALL checked** (FR-003). Whole-block toggle sets every row checked/unchecked;
  category group toggles are tristate over their rows (FR-004/FR-005).
- Empty-block invariant: if all five categories are empty, the whole-block toggle reads
  **unchecked/disabled** (NOT vacuously fully-selected) and advancing plans nothing (Edge Case).
- No `ADD_NEW/MERGE/OVERWRITE` control appears (FR-012 / SC-008).

## Selection merge (in `_PagePreview._on_preview`)

The preview builds one `Selection` from all pages. Phonology contributes:

```
categories        += {cat: True for each phonology category with ≥1 checked row}
categories        += {STRATA: True} iff PHONOLOGICAL_RULES on and ≥1 rule checked   # FR-009
leaf_item_picks   += {cat: frozenset(checked)} for each on-category trimmed below full;
                     key OMITTED when all rows checked (⇒ transfer-all)
```

**Invariants**:
- Absent `leaf_item_picks[cat]` ⇒ engine transfers all items in `cat` (back-compat).
- `STRATA` is never keyed in `leaf_item_picks` and never a user row.
- Phonology categories use the Layer-1 default conflict mode (no per-category UI); GOLD-reserved
  ones (`PHONOLOGICAL_FEATURES`) keep MERGE per `_DEFAULT_CONFLICT_MODES`.

## Move gate (in `_PageFinish._on_move`)

- Phonology missing-reference warnings are aggregated into the **same** `el_count` used for the
  skeleton/deps EXCLUDED-LOSSY total (FR-011): one consolidated confirmation dialog covering all
  pages. No separate phonology dialog.
- Warning count is entry-centric: one per kept phonology item with an unresolvable, target-absent
  reference (SC-006).

## Engine contract (categories.py + models.py)

- `Selection.leaf_item_picks` added (see data-model.md). The six phonology `enumerate_source`
  helpers filter `GetAll()` by `selection.leaf_item_picks.get(cat)` when present, comparing
  `_guid_str_from(it)` (NOT raw `str(it.Guid)`) against the pick set — the builder stores
  `row.guid` through the same `_guid_str_from` normalization so both sides match.
- EXCLUDED-LOSSY warning builder consumes the **per-rule** dict maps
  (`rule_referenced_nc_guids[rule] `/ `rule_referenced_phoneme_guids[rule]`) so each warning
  is attributed to the specific kept rule (entry-centric SC-006).
- **Named-accessor invariant** (P-1): no page references another by literal index; a
  `test_wizard_page_order.py` type-identity test guards the ordering (P-2).
- **Regression invariant**: with no `leaf_item_picks` key, every phonology callback behaves
  exactly as spec-005 (all 324+ existing tests unchanged; live idempotency FR-307 preserved).

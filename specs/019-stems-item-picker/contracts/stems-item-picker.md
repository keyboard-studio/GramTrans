# Contract: Stems Item Picker (019)

## Engine contract — `Lib/selection.py`

Each of the four builders gains a partition selector (default preserves affix behavior
byte-for-byte). Naming (`want_affix: bool = True` vs a shared `_partition_entries` helper) is a
/speckit-tasks decision; the observable contract is fixed here.

### `_build_target_sets(..., want_affix: bool = True)`
- `want_affix=True`: existing target guid/form sets over affix-morphtype entries.
- `want_affix=False`: same sets over **stem** entries (include-on-exception partition).
- Both tabs must obtain target-status from this function; no duplicate enumeration logic.

### `build_pos_grouped_inventory(..., want_affix: bool = True)`
- `want_affix=False`: returns the stem inventory grouped by POS (`MoStemMsa.PartOfSpeechRA`).
- Each entry appears in exactly one partition (SC-001: complete + disjoint).
- Zero-stem source → empty inventory (not an error); the tab renders empty (FR-007/SC-006).

### `build_skeleton_inventory(..., want_stem: bool = False)` / `build_deps_inventory(...)`
- Stem path walks `PartOfSpeechRA → POS.{InflectionClassesOC, StemNamesOC, InflectableFeatsRC}`
  + `MoStemMsa.MsFeaturesOA`.
- **MUST NOT** cast a stem MSA to `IMoInflAffMsa`, read `SlotsRC`, or enter the affix
  slot/template skeleton builder (FR-013).

### MSA dispatch (`~selection.py:706-810`)
- New arm: `class_name == "MoStemMsa"` → read `PartOfSpeechRA` + `MsFeaturesOA`.
- A non-`MoStemMsa` MSA on a stem-partitioned entry is skipped, not recast.

### Partition null guard (contract-critical)
```
# affix filter (existing): skip-on-exception
try: is_affix = to_morph_type(entry).IsAffixType
except (AttributeError, TypeError): continue          # entry excluded from AFFIX tab

# stem filter (new): INCLUDE-on-exception
try: is_affix = to_morph_type(entry).IsAffixType
except (AttributeError, TypeError): is_affix = False  # entry -> STEM bucket, never dropped
if is_affix: continue                                  # affixes excluded from STEM tab
```

## Selection contract — `Lib/models.py`
- `Selection.stem_picks: frozenset[str]` (new).
- Invariant: non-empty `stem_picks` ⇒ `categories[GrammarCategory.STEMS]` on.

## UI contract — `Lib/ui/selection_wizard.py`
- `_PageItemPicker`: Stems tab **enabled** (placeholder at :625-689 removed); populated from
  `build_pos_grouped_inventory(..., want_affix=False)`.
- Check/uncheck a stem row toggles its GUID in the pick set.
- `collect_selection()` returns a `Selection` with `stem_picks` populated (mirror of the
  `affix_picks` path at :1189-1206).
- Pages 3–5: `_get_stem_picks()` mirrors `_get_affix_picks()`; `stem_picks` threads into
  `build_skeleton_inventory`/`build_deps_inventory`.
- Move gate: stem warnings via `build_excluded_lossy_warnings()` →
  `plan.excluded_lossy_count()` (:3171). **No new dialog** (FR-010).
- No ADD_NEW/MERGE/OVERWRITE control on the pane (FR-012/SC-007).

## Invariants preserved
- GOLD-shipped objects never re-created; GUID-first identity (FR-011, Constitution I).
- Nothing on the pane writes to the target; only Move writes (FR-008, Constitution III).
- Shared dependency pulled once, deduplicated by GUID (affix ∩ stem).

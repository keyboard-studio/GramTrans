# Phase 1 Data Model: Affixes-by-POS Item Picker

New types live in `src/gramtrans/Lib/selection.py` alongside the retained
`SourceAffixInventory`. All are frozen dataclasses (pure data; no LCM handles retained
after the build).

## AffixRow

One affix as shown in one group appearance.

| Field | Type | Notes |
|---|---|---|
| `entry_guid` | `str` | lower-cased affix LexEntry GUID; selection/dedup/mirror identity |
| `form` | `str` | best-vernacular lexeme form; `"?"` if unreadable |
| `glosses` | `str` | deduped sense glosses joined `"; "`; `"(no gloss)"` if none |
| `msa_kind` | `str` | `"infl"` \| `"deriv"` \| `"uncl"` (worst/primary kind for this appearance) |
| `from_pos` | `Optional[str]` | attaches-to POS label for this appearance (deriv/infl/uncl); None if n/a |
| `to_pos` | `Optional[str]` | produces POS label (deriv only); None otherwise |
| `role` | `str` | `"attaches"` \| `"produces"` — which subgroup this appearance belongs to |

Row identity within a group: `(entry_guid, pos_guid, role)`. Multiple senses/MSAs of the
same entry landing in the same `(pos_guid, role)` collapse into one row (glosses merged).

## PosNode

A node in the POS hierarchy carrying the affixes attached to / produced by it.

| Field | Type | Notes |
|---|---|---|
| `pos_guid` | `str` | POS GUID |
| `label` | `str` | Abbreviation preferred, else Name |
| `children` | `tuple[PosNode, ...]` | sub-POS in hierarchy order |
| `inflectional` | `tuple[AffixRow, ...]` | infl + uncl attaches-to rows |
| `deriv_attaches` | `tuple[AffixRow, ...]` | deriv From = this POS |
| `deriv_produces` | `tuple[AffixRow, ...]` | deriv To = this POS (NOT swept by header check) |

A node renders even if all three lists are empty when it has non-empty descendants
(so the hierarchy path to a populated sub-POS is preserved). Header-check selection set =
`inflectional` ∪ `deriv_attaches` over the node and its descendants.

## JunkDrawer

| Field | Type | Notes |
|---|---|---|
| `no_pos` | `tuple[AffixRow, ...]` | has ≥1 MSA but no readable POS on any of them |
| `no_analysis` | `tuple[AffixRow, ...]` | no sense / no MSA |

Junk rows use `from_pos=None, to_pos=None`; still checkable/selectable by `entry_guid`.

## PosGroupedAffixInventory

Top-level result of the builder.

| Field | Type | Notes |
|---|---|---|
| `roots` | `tuple[PosNode, ...]` | top-level POS nodes in hierarchy order |
| `junk` | `JunkDrawer` | unattached affixes |

Helper: `all_affix_guids() -> frozenset[str]` (defensive dedup used by collapse).

## Relationship to existing types (unchanged)

- **`Selection`** (`models.py`) — collapse writes resolved GUIDs into `affix_picks` via
  `build_selection`. No new fields.
- **`PickerState`** (`selection.py`) — only `checked_affixes` populated from this picker;
  `checked_templates` / `checked_slots` remain empty (reserved for the template phase).
- **`SourceAffixInventory`** (`selection.py`) — retained untouched for the deferred
  template picker.

## Validation rules (from spec)

- Every source affix appears exactly once per distinct `(pos_guid, role)` it reaches, and
  in `junk` iff it reaches no POS (FR-002, FR-013, SC-001).
- A multi-POS affix appears in each reached group but resolves to one `entry_guid` in the
  selection (FR-012, SC-002).
- Every derivational affix with non-null From and To appears in both a `deriv_attaches`
  list and a `deriv_produces` list (FR-007, SC-003).
- Header-check selection excludes `deriv_produces`-only affixes (FR-008, SC-005).

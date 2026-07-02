# Phase 1 Data Model: Phonology Selector (Model-B)

Pure-data shapes for the Phonology page builder + the one engine field. Fake-handle testable;
no LCM types leak into the dataclasses (GUIDs are strings, status is a string enum-lite).

## Engine extension (models.py)

### `Selection.leaf_item_picks` (NEW field)

```python
leaf_item_picks: dict = field(default_factory=dict)
# dict[GrammarCategory, frozenset[str]]  — source GUIDs to transfer within a leaf category.
# Semantics: key PRESENT ⇒ transfer only those GUIDs; key ABSENT ⇒ transfer ALL (unchanged
# behavior for every existing caller). Empty frozenset ⇒ transfer none of that category.
```

- Consulted only by leaf `enumerate_source` helpers (phonology first; the mechanism is generic
  and other leaf categories may adopt it later).
- No `__post_init__` coupling required (unlike `affix_picks`), because an item-pick subset for
  a category that is off is simply ignored by the leaf-dispatch (`is_on` gates first). Optional
  validation: a key present for a category not in `categories` is harmless (dead subset).

### `_phonology_simple_enumerate` (EXTENDED, categories.py)

```
items = list(getattr(source, ops_attr).GetAll())
picks = selection.leaf_item_picks.get(<this category>)   # None when absent
if picks is not None:
    items = [it for it in items if _guid_str_from(it) in picks]
return items
```

Same guard added to the strata enumerate. `None`-check preserves all-items default.

**GUID-normalization invariant (P0 — cycle-2 QC)**: both the builder (`PhonologyRow.guid`)
and this trim filter MUST normalize GUIDs through `_guid_str_from` (categories.py:94-104 —
`str(ICmObject(obj).Guid).lower()`, braces stripped). Raw `str(it.Guid)` is uppercase-with-
braces (`{12A3B456-...}`) and would never match a stored pick, silently dropping **every**
trimmed item. `None`/empty Guid ⇒ `_guid_str_from` returns `""`, which never matches a real
UUID, so such an item is filtered out when a trim key is present for its category (deliberate;
do NOT "helpfully" make `""` match-all).

## Page-side dataclasses (selection.py)

### `PhonologyRow`

| Field | Type | Notes |
|-------|------|-------|
| `guid` | `str` | source LCM GUID |
| `label` | `str` | display name (phoneme repr / NC name / rule name / feature name / env repr) |
| `category` | `GrammarCategory` | one of the five user-facing phonology categories |
| `preselected` | `bool` | always `True` this feature (ALL default); field kept for symmetry with 009 |
| `status` | `str \| None` | `"new"` / `"in_target"` / `"similar"` / `None` (no target bound) |

### `PhonologyCategoryGroup`

| Field | Type | Notes |
|-------|------|-------|
| `category` | `GrammarCategory` | the group's category |
| `label` | `str` | e.g. "Phonemes" |
| `rows` | `tuple[PhonologyRow, ...]` | may be empty (empty category renders, no error) |
| `count` | `int` | `len(rows)` — annotated on the group header (FR-006) |

### `PhonologyInventory`

| Field | Type | Notes |
|-------|------|-------|
| `groups` | `tuple[PhonologyCategoryGroup, ...]` | ordered: features, phonemes, natural classes, environments, rules |
| `rule_referenced_nc_guids` | `dict[str, frozenset[str]]` | rule guid → referenced NC guids (rules→NC via `IPhSimpleContextNC`) |
| `rule_referenced_phoneme_guids` | `dict[str, frozenset[str]]` | rule guid → referenced phoneme guids (rules→phoneme-direct via `IPhSimpleContextSeg`) |
| `nc_referenced_phoneme_guids` | `dict[str, frozenset[str]]` | NC guid → phoneme guids via `SegmentsRC` |
| `phoneme_referenced_feature_guids` | `dict[str, frozenset[str]]` | phoneme guid → feature guids via `FeaturesOA` |
| `has_rules` | `bool` | convenience: any rule present (drives strata gating) |

> Strata is **not** a group here — it is never user-facing (FR-009). It is derived at
> selection-collapse time from whether any rule is kept.

**Per-rule map shape (cycle-2 domain)**: the two rule maps are keyed by `_guid_str_from(rule)`
with values `_guid_str_from(IPhSimpleContext*.FeatureStructureRA)` per rule. This per-rule shape
(not a flat set) is required so `build_excluded_lossy_warnings` (008/009) can attribute an
entry-centric SC-006 warning to the *specific* kept rule ("rule X references deselected NC Y").
All four reference maps are therefore `dict[guid → frozenset[guid]]`.

**RHS-path note (do not "fix" back to bug #142)**: rule RHS context is read from
`rhs.LeftContextOA` / `rhs.RightContextOA` on `IPhSegRuleRHS` — explicitly NOT
`StrucDescOS[0].LeftContextOA` (the bug-#142 path). Environments stay excluded from the rule
chain (they live on `IMoAffixAllomorph.PhoneEnvRC`, allomorph-side).

## Selection-collapse (page → engine)

`collapse_phonology(inventory, checked_guids_by_category) → dict` produces the fragments merged
into the Preview page's `Selection`:

```
categories:        {PHON_FEATURES: on, PHONEMES: on, NATURAL_CLASSES: on,
                    PH_ENVIRONMENT: on, PHONOLOGICAL_RULES: on}   # each True iff its group has ≥1 checked row
                   + {STRATA: True} iff PHONOLOGICAL_RULES on with ≥1 checked rule   # FR-009
leaf_item_picks:   {cat: frozenset(checked guids)} for each on-category whose checked set
                   is a PROPER SUBSET of its rows (trim). Omit the key when ALL rows checked
                   (⇒ transfer all, avoids listing every GUID).
```

Whole-block toggle OFF ⇒ no phonology categories set, no `leaf_item_picks`, no strata.

## Missing-reference (EXCLUDED-LOSSY) derivation

A deselected item is a stranded reference when a **kept** item references it and the **target
lacks** it. Aggregation is entry-centric (one warning per kept item, per FR-010/SC-006):

| Kept item | References (deselected + target-absent) → warning about the kept item |
|-----------|------------------------------------------------------------------------|
| phonological rule (guid `r`) | any `rule_referenced_nc_guids[r]` NC, or `rule_referenced_phoneme_guids[r]` phoneme |
| natural class (guid `nc`) | any `nc_referenced_phoneme_guids[nc]` phoneme |
| phoneme (guid `p`) | any `phoneme_referenced_feature_guids[p]` feature |

Environments are excluded from the rule chain (allomorph-side). Warnings feed the shared 009
Move gate (single consolidated dialog).

> **KL-010-1 (known limitation)** — this derivation traverses `PhRegularRule` contexts
> (`StrucDescOS` + `rhs.Left/RightContextOA`). It does **not** traverse `PhMetathesisRule`
> (`Left/RightPartOfMetathesisOS`) or `PhReduplicationRule` (`Left/RightPartOfReduplicationOS`)
> part-sequences, whose `IPhSimpleContext*` entries can also reference NCs/phonemes. A kept
> metathesis/reduplication rule stranded against a deselected NC/phoneme raises NO warning.
> Safe for the current Ejagham corpus (PhRegularRule only); tracked as a post-010 follow-up.

## Reused / unchanged

- `RunReport`, `PlannedAction`, leaf-dispatch loop, all six phonology callbacks (behavior
  unchanged except the enumerate filter) — reused verbatim.
- Target-status computation + `build_excluded_lossy_warnings` shape — reused from 008/009.

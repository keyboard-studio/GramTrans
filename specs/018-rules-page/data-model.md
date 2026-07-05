# Phase 1 Data Model — 018 Rules Page

Reuses the 010 `Selection.leaf_item_picks` mechanism (no new engine selection
field). New artifacts are the UI-side inventory dataclasses in `selection.py`.

## Reused engine field (no change)

```python
# models.py (already exists, from 010)
Selection.leaf_item_picks: dict[GrammarCategory, frozenset[str]]
#   key ADHOC_COMPOUND_RULES absent  => transfer ALL rules (default)
#   present => transfer only rules whose normalized GUID is in the frozenset
#   GUIDs normalized via _guid_str_from on BOTH sides (010 invariant)
```

## New UI dataclasses (selection.py)

```python
@dataclass(frozen=True)
class RuleRow:
    guid: str                 # normalized (_guid_str_from)
    label: str                # display name (Name best-analysis; fallback synthesized)
    subclass: str             # ClassName: MoAlloAdhocProhib | MoMorphAdhocProhib
                              #   | MoAdhocProhibGr | MoEndoCompound | MoExoCompound
    checked: bool             # default True (preselect-all)
    target_status: str        # "NEW" | "IN TARGET" | "SIMILAR" | "" (no target)
    parent_group_guid: str | None  # set for adhoc children owned by a group node

@dataclass(frozen=True)
class RuleCategoryGroup:
    category_label: str       # "Ad Hoc Rules" | "Compound Rules"
    rows: tuple[RuleRow, ...] # user-defined rules; grouping nodes appear as rows
                              #   with parent_group_guid=None and own children linked
    count: int                # user-defined rule count (FR-011)

@dataclass(frozen=True)
class RulesInventory:
    adhoc: RuleCategoryGroup
    compound: RuleCategoryGroup
    has_any: bool             # False => whole-block toggle unchecked/disabled (edge case)
```

## Builder

```python
def build_rules_inventory(source, target=None) -> RulesInventory
```

- Walks `AdhocCoProhibitionsOS` (recursing `IMoAdhocProhibGr.MembersOC`) and
  `CompoundRulesOS`.
- Filters to **user-defined** rules (GOLD-shipped rules excluded — Constitution I;
  in practice rule lists are user-authored, but the GOLD guard is applied for parity).
- Each row's `target_status` computed against `target` via the shared 008/009/010
  status helper (GUID match => IN TARGET; fingerprint match => SIMILAR; else NEW;
  blank when `target is None`).
- `checked=True` for every row (FR-009). `has_any` = (adhoc.count + compound.count) > 0.

## Selection collapse

`_PageRules` collapses checked rows into
`Selection.leaf_item_picks[ADHOC_COMPOUND_RULES] = frozenset(checked_guids)`:
- whole block ON, nothing trimmed => key ABSENT (transfer all) OR full set — both
  equivalent; prefer absent for the untouched case (SC-004 count parity).
- whole block OFF => empty frozenset (transfer none, SC-005).
- individual trim => full set minus deselected GUIDs.

Grouping-node semantics (edge case): a group node is included iff ≥1 child is kept;
deselected children are excluded; kept children keep group ownership (engine
`execute_action` re-parents kept children under the created group's `MembersOC`).

## Missing-reference warning record (preview.py)

Reuses the 010 aggregated-warning shape:

```python
# one per kept rule with an unresolvable member reference
MissingRefWarning(
    category=ADHOC_COMPOUND_RULES,
    rule_guid=str, rule_label=str,
    stranded_ref_kind=str,   # "allomorph" | "morpheme" | "part-of-speech"
    stranded_ref_label=str,
)
```

All instances flow into the single shared Move gate (FR-015).

## GUID-normalization invariant

Every GUID stored on `RuleRow.guid`, every key in `leaf_item_picks`, and every
lookup in `enumerate`/`plan`/wiring MUST pass through `_guid_str_from`
(lowercase, braces stripped). Raw `str(obj.Guid)` is uppercase-braced and breaks
matching silently.

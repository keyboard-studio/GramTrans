# Phase 1 Data Model — 020 Conflict-Mode Field Merge

020 is a UI/wiring feature. It adds **one** new model-layer surface
(`allowed_modes_for`) and **reuses** every existing conflict/merge entity
unchanged. No new dataclass is required on the engine side; the new artifacts are
a UI-side view model for the per-category mode selector and one behavior change
in `protection.py`. All entities below already exist except where marked **NEW**.

## Reused engine entities (no change)

```python
# models.py (exist)
ConflictMode(ADD_NEW | MERGE | OVERWRITE)                      # L74
MergeResolution(TAKE_SOURCE | KEEP_TARGET | MERGE | SKIP | EDIT_CUSTOM)  # L201
Selection.category_conflict_modes: dict[GrammarCategory, ConflictMode]   # L355
Selection.conflict_mode_for(category) -> ConflictMode          # L439 (override-else-default)
Selection._replace_conflict_modes(dict) -> Selection          # L452 (frozen-safe)
_DEFAULT_CONFLICT_MODES: dict[GrammarCategory, ConflictMode]   # L160 (Layer-1 default)
PlannedOverwrite(..., write_mode="overwrite"|"merge")          # L583 (fill-gaps flag)
ConflictPrompt(..., merge_eligible: bool)                      # L738
MergeDecision / MergeDecisionLog                               # L661 / L684
InteractiveSession.merge_decisions_by_guid: dict[str, MergeDecisionLog]  # L790
```

```python
# conflict.py (exist)
detect_conflicts(src_props, tgt_pre_props, target_guid, target_class_name, prior_log=None)  # L91
collect_overwrite_conflicts(plan, source, target, prior_logs_by_guid=None)                  # L288
_OW_OPS: dict[str, (src_ops, tgt_ops, finder_name)]   # L233 — pos/entry/sense/allomorph only
_deterministic_merge(left, right, run_id)             # L155
load_prior_log / load_prior_decision                  # L385 / L435
UserCancelled                                         # L47
```

## NEW — `allowed_modes_for` (R3 / GAP3 / FR-001)

Surfaces (does not redefine — FR-011) the Layer-1 permitted-mode set. Promote the
kind-sets from `_build_default_conflict_modes` locals (`models.py:102-157`) to
module-level frozensets, then:

```python
# models.py (NEW)
_MULTI_INSTANCE_CATS: frozenset[GrammarCategory]         # promoted from local
_SINGLETON_CATS: frozenset[GrammarCategory]              # promoted from local
_GOLD_RESERVED_CATS: frozenset[GrammarCategory]          # promoted from local
_CUSTOM_FIELDS_CATS: frozenset[GrammarCategory]          # promoted from local

def allowed_modes_for(category: GrammarCategory) -> frozenset[ConflictMode]:
    """Read-only Layer-1 permitted-mode set. Companion to conflict_mode_for.
    MULTI_INSTANCE          -> {ADD_NEW, MERGE, OVERWRITE}
    SINGLETON_NONDELETABLE  -> {MERGE, OVERWRITE}          # ADD_NEW hidden
    GOLD_RESERVED           -> {MERGE}                      # ADD_NEW hidden, OVERWRITE forbidden
    CUSTOM_FIELDS           -> {MERGE}                      # conservative
    """
```

Invariant: `conflict_mode_for(cat) in allowed_modes_for(cat)` for every category
(the default is always permitted). The wizard uses this to populate the selector
and to reject an out-of-set override.

## NEW (behavior change) — `_is_protected` fails closed (R4 / GAP4 / US4)

```python
# protection.py (CHANGE)
def _is_protected(lcm_obj) -> bool:
    # was: bare lcm_obj.IsProtected; except -> return False (permissive/fail-open)
    # now: cast via ICmPossibility(lcm_obj).IsProtected;
    #      on failed cast / absent -> return True (fail-CLOSED) + diagnostic log
```

`apply_isprotected_layer2` (`protection.py:41`) is unchanged in signature; it
still downgrades a protected item to `MERGE`. Only the indeterminate-state
polarity flips from permissive to protective.

## NEW — per-category mode-selector view model (UI side)

Lives beside the existing wizard page builders (`selection.py` / the page module),
not in the engine. Pure builder, fake-handle testable.

```python
@dataclass(frozen=True)
class ConflictModeChoice:
    category: GrammarCategory
    current: ConflictMode                 # conflict_mode_for(category)
    allowed: tuple[ConflictMode, ...]     # sorted(allowed_modes_for(category))
    field_diff_tier: str                  # "A" (real diff) | "B" (selector-only) | "C" (blocked)
    blocked_reason: str = ""              # Tier C only: flexicon bug ref
```

- `field_diff_tier` is derived from the R2 tier table (a static category→tier map
  in the UI layer, sourced from probe-results.md — NOT re-decided per run).
- The page collapses user choices into
  `Selection.category_conflict_modes[category] = chosen` via
  `_replace_conflict_modes`; an unchanged category leaves the key **absent** so
  `conflict_mode_for` returns the Layer-1 default (SC-002 no-regression).

## Field-conflict scope (R5 / GAP5 correction)

`detect_conflicts` operates on the `GetSyncableProperties` dict, which per
[probe-results.md §1/§4] contains:

- scalar/text props (in scope; MERGE-eligible unless int/bool/None),
- **atomic `*RA` GUID refs** (in scope; surface as GUID-valued conflicts —
  `merge_eligible=False` since GUID strings are not text-mergeable in practice),
- **NOT** `*RS`/`*OC` sequence/collection refs (excluded upstream by flexicon).

No model field encodes this; it is an emergent property of the syncable dict and
is documented so the spec's "reference fields" language is precise.

## State transitions (mode change → decision invalidation, R8 / FR-009)

```text
category mode: OVERWRITE --(user switches)--> ADD_NEW | MERGE
  => wizard drops InteractiveSession.merge_decisions_by_guid entries whose
     target belongs to that category (stale, no longer applicable).
item is NEW (not in target)
  => no ConflictPrompt regardless of mode (plain create).
```

## GUID-normalization invariant

Any new Tier-A target finder (InflectionFeature / NaturalClass / MorphRule) MUST
match on `str(ICmObject(concrete).Guid).lower()` on both sides, exactly as the
existing `_find_target_*_by_guid` helpers (`conflict.py:248-285`).

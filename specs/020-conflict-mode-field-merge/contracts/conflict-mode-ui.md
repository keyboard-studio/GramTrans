# Contract — Conflict-Mode UI & Field-Level Merge (020)

Defines the seams between the per-category mode selector (US1), the field-level
resolver (US2/US3), the Layer-1/Layer-2 gating (US4), the merge-preview pane
(US5), and the existing engine. Contracts are the stable surface; internals may
change. Line refs are to the 020 worktree.

## C1 — Mode selector ↔ Selection (US1 / FR-001 / FR-002)

**Query (surfacing, read-only):**
```python
allowed_modes_for(category) -> frozenset[ConflictMode]   # models.py (NEW, R3)
Selection.conflict_mode_for(category) -> ConflictMode     # exists (L439)
```
**Persist:**
```python
Selection._replace_conflict_modes({category: mode, ...}) -> Selection   # exists (L452)
```
Contract:
- The selector MUST offer exactly `allowed_modes_for(category)`, preselecting
  `conflict_mode_for(category)`.
- Setting a mode MUST persist to `category_conflict_modes` and become the value
  returned by `conflict_mode_for`. An unset category MUST leave the key absent
  (Layer-1 default; SC-002 no-regression for untouched categories).
- A mode not in `allowed_modes_for(category)` MUST be rejected (not selectable).
- Invariant: `conflict_mode_for(cat) in allowed_modes_for(cat)` always holds.

## C2 — Field-level resolver ↔ engine (US2 / FR-003 / FR-004 / FR-005)

**Producer:**
```python
collect_overwrite_conflicts(plan, source, target, prior_logs_by_guid=None)
    -> tuple[ConflictPrompt, ...]           # conflict.py:288
```
**Resolver protocol (production = ConflictDialog):**
```python
ConflictResolver.resolve(prompts) -> tuple[MergeDecision, ...]   # conflict.py:57
    # same length & order as prompts; raises UserCancelled on dismiss
```
**Fold + execute:**
```python
build_session_from_resolutions(prompts, decisions) -> InteractiveSession  # conflict.py:451
# transfer.execute consumes InteractiveSession; per-field decisions filter props
```
Contract:
- Prompts are produced **only** for items in `plan.overwrites` (i.e. categories
  running `OVERWRITE`). MERGE mode produces no prompts (R1).
- One `ConflictPrompt` per conflicting field; identical src/tgt values are
  suppressed (FR-004; `conflict.py:131-132`).
- `merge_eligible=False` ⇒ dialog hides the MERGE radio (scalars, atomic RA GUIDs).
- Field scope = scalar/text + atomic `*RA` GUID refs; `*RS`/`*OC` excluded (R5).
- Execution applies each field's decision individually (TAKE_SOURCE / KEEP_TARGET
  / MERGE / SKIP / EDIT_CUSTOM), not a wholesale object overwrite (FR-005).

## C3 — `_OW_OPS` extension for Tier-A categories (FR-012, field-detection)

```python
_OW_OPS: dict[str, tuple[str, str, str]]   # conflict.py:233
#   category.value -> (source_ops_attr, target_ops_attr, target_finder_name)
```
Contract:
- Ships covering `pos, entry, sense, allomorph` (existing) PLUS the new Tier-A
  entries: `inflection_features`, `natural_classes`, `gram_categories`?/`morph`
  as confirmed by a live re-probe (R2a). Each new entry MUST supply a
  `_find_target_<x>_by_guid` finder using lowercase-normalized GUID match.
- Categories absent from `_OW_OPS` return `None` at the lookup and are skipped for
  field detection — this is the deliberate Tier-B ("selector-only") behavior; it
  MUST NOT raise.
- Tier-C categories (PHONEMES, PH_ENVIRONMENT) MUST NOT be added to `_OW_OPS`
  while the flexicon `GetSyncableProperties` bug is open (R6); adding them would
  propagate the AttributeError. They remain selector-only.

## C4 — Layer-1 / Layer-2 veto (US4 / FR-007)

```python
allowed_modes_for(category)                      # Layer-1: OVERWRITE not in set => not selectable
apply_isprotected_layer2(cat, lcm_item, mode)    # Layer-2: protected => downgrade to MERGE (protection.py:41)
_is_protected(lcm_obj) -> bool                   # CHANGED: fail-CLOSED + ICmPossibility cast (R4)
```
Contract:
- GOLD_RESERVED / CUSTOM_FIELDS ⇒ `OVERWRITE ∉ allowed_modes_for` ⇒ selector must
  not offer it (FR-007, SC-004).
- A protected (`IsProtected`) target ⇒ Layer-2 downgrades the effective mode to
  MERGE regardless of the chosen mode; the corresponding field decisions that
  would write it MUST be vetoed (disabled in dialog and/or refused at execute).
- Indeterminate protection state MUST fail closed (treat as protected) — never
  fail open (R4). `IsProtected` MUST be read via `ICmPossibility(x).IsProtected`.

## C5 — Merge-preview pane reflects choices (US5 / FR-008)

Contract:
- The preview MUST render each affected item's planned action (create / overwrite
  / link) derived from `conflict_mode_for(category)` + Layer-2, and the
  field-level diff derived from the captured `MergeDecision`s.
- A category left at its Layer-1 default MUST render identically to pre-020
  behavior (SC-006 / FR-008 no-regression).
- Tier-B/C categories render the mode/action but no field-level diff rows (no-op).

## C6 — Cancel / stale-decision invalidation (FR-009 / FR-010)

- `UserCancelled` from the resolver ⇒ no partial write for that run; return to the
  page (FR-010; existing `conflict.py:47` + MainFunction catch).
- Changing a category's mode ⇒ drop that category's captured
  `merge_decisions_by_guid` entries (R8 / FR-009); the user is never left with
  stale, silently-applied decisions.

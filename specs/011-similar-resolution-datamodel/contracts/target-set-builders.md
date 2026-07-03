# Contract: Target-Set Builder Return Shapes (011)

The real contract surface of feature 011 is the return-shape change of the two existing
target-set builders in `src/gramtrans/Lib/selection.py`. Everything else (new dataclass fields)
is additive and defaulted. This document pins the old → new signatures so the contract test
targets the exact seam that changed. Both changes were validated live via the FLExTools MCP
(research D1, D3, D4, D5).

---

## C1 — `_build_target_sets` (affix side, FR-002 / research D4)

### Before

```python
def _build_target_sets(target) -> Tuple[Set[str], Set[str]]:
    """-> (target_guids, target_forms)"""
```

- `target_guids`: lower-cased affix entry GUID strings.
- `target_forms`: `strip().casefold()` best-vernacular forms.

### After

```python
def _build_target_sets(
    target,
) -> Tuple[Set[str], Set[str], Dict[str, Tuple[SimilarCandidate, ...]], Tuple[SimilarCandidate, ...]]:
    """-> (target_guids, target_forms, form_to_candidates, all_candidates)"""
```

- `target_guids`, `target_forms`: **unchanged** (existing SIMILAR/IN-TARGET status logic keeps
  working identically — `_entry_status` is not modified).
- `form_to_candidates`: `dict[normalized_form -> Tuple[SimilarCandidate, ...]]`. Each tuple is
  **HVO-ascending, non-empty**, and may have length > 1 (live-proven: form `'n'` → 5 candidates).
  Forms whose `_best_form` is `'?'` are excluded.
- `all_candidates`: flat, **deduplicated by `target_guid`** (SC-002), **HVO-ascending**
  `Tuple[SimilarCandidate, ...]` covering every distinct candidate referenced by any form.

### Consumers

- **Sole caller:** `build_pos_grouped_inventory` (selection.py:536) — verified single caller
  (research D4). It MUST:
  1. Unpack the 4-tuple.
  2. For each SIMILAR `AffixRow`, set `suggested_target_guid` = first candidate for the row's
     normalized form (via `_suggested_target_guid_for`), else `None`.
  3. Carry `all_candidates` onto the returned `PosGroupedAffixInventory.target_affix_candidates`.
- No other code may unpack `_build_target_sets` as a 2-tuple (contract test asserts arity == 4).

### Contract assertions

- `no target bound` → `build_pos_grouped_inventory` still returns rows with `status=None` and
  `suggested_target_guid=None`; `target_affix_candidates == ()` (graceful degrade).
- `form_to_candidates[f]` is sorted HVO-ascending and its first element's `target_guid` equals the
  SIMILAR row's `suggested_target_guid` for form `f`.
- `all_candidates` contains each `target_guid` exactly once (dedup) and is a superset of every
  per-form tuple's candidates (SC-002).

---

## C2 — `_phon_target_sets` (phonology side, FR-006 / research D3, D5)

### Before

```python
def _phon_target_sets(target, accessor, *, phoneme: bool = False) -> Tuple[Set[str], Set[str]]:
    """-> (guids, labels)"""
```

### After

```python
def _phon_target_sets(
    target, accessor, *, phoneme: bool = False,
) -> Tuple[Set[str], Set[str], Dict[str, str]]:
    """-> (guids, labels, label_to_guid)"""
```

- `guids`, `labels`: **unchanged** (existing IN-TARGET/SIMILAR status logic in
  `build_phonology_inventory` keeps working identically).
- `label_to_guid`: `dict[casefold_label -> target_guid]`. **Collision-aware, output single-valued:**
  when a casefold label maps to multiple target objects (live-proven: all 5 NaturalClass names
  collide), the value is the **lowest-HVO** object's GUID, and the collapse is logged at `INFO`
  (label + chosen GUID). Blank/dangling-empty target items are skipped (existing `_phon_is_empty`
  contract) and never enter the map.

### Consumers

- **`build_phonology_inventory`** threads the per-category `label_to_guid` into row construction:
  for each SIMILAR `PhonologyRow`, `matched_target_guid = label_to_guid.get(row_label.strip().casefold())`.
  NEW rows and the no-target case → `None`.

### Contract assertions

- `no target bound` (or `accessor` absent) → `({}, set(), {})`; every row `matched_target_guid=None`.
- On a colliding label, `label_to_guid[label]` == the GUID of the lowest-HVO colliding object, and
  exactly one INFO log line is emitted for that label.
- A SIMILAR phonology row's `matched_target_guid` is non-None and present in the target's `guids`
  set; a NEW row's is `None` (SC-005).

---

## Non-contract (explicitly unchanged)

- `_entry_status`, `_best_form`, `_collect_glosses`, `_phon_label`, `_phon_guid`, `_phon_is_empty`
  — signatures and behavior unchanged (spec Assumptions: reuse existing normalization; no new
  policy).
- No planner / closure / executor / Preview / Move signature changes (FR-010).

# Tasks: Similar-Resolution Transfer (Merge Write-Mode)

**Feature**: 013-similar-resolution-transfer | **Date**: 2026-07-03

Task ordering: S1/S2 spikes -> R4 carrier -> R2 flexlibs2 kwarg -> R3 fingerprint
helper -> FR-009 child extractor -> FR-008 executor branch -> FR-006 identity_remap
threading -> FR-001 planner hook -> S3 verification.

Tasks marked **[FORK]** touch the flexlibs2 repository at
`D:/Github/_Projects/_LEX/flexlibs2`. Run `pip install -e D:/Github/_Projects/_LEX/flexlibs2`
after each fork edit before running GramTrans tests.

---

## T-S1 — Live-Verify: multistring emptiness predicate

**Spike / gate** | **Blocks**: T-R2 (multistring fill-gaps guard)

Verify against the Ejagham Mini -> Ejagham Full GT-Test pair that the correct LCM 9.x
call for reading a target multistring WS slot is:

```python
prop_obj.get_String(tgt_handle).Text.strip()  # non-empty -> target wins
```

and not `.RunCount > 0` or another predicate. Open a scratch transfer session, pick a
multistring field with content in the target, and assert that `get_String(handle).Text`
returns the expected non-empty string after strip.

**Deliverable**: A one-paragraph note in this task's PR/commit confirming the call form
and whether `.Text` needs `.strip()` or is already trimmed, plus any observed edge cases
(e.g. ITsString vs plain str return type differs by FW version).

**Files touched**: None (read-only probe against live project).

---

## T-S2 — Live-Verify: MSA/Allomorph Owner resolves to ILexEntry

**Spike / gate** | **Blocks**: T-R3

Verify in the Ejagham Mini -> Ejagham Full GT-Test pair that `msa.Owner` and
`allo.Owner` both resolve to an `ILexEntry` (not an intermediate `MoForm` or other
LCM object) for inflectional affix entries.

Reference: `matcher.py:112` (`msa.Owner.Guid`) and `matcher.py:153` (`allo.Owner.Guid`).

**Deliverable**: Confirmation that `type(msa.Owner).__name__` and
`type(allo.Owner).__name__` are both `"LexEntry"` (or the actual interface name observed)
in the real data, so fingerprint tuple index 1 can be treated as the owning entry GUID
without an extra `.Owner` hop.

**Files touched**: None (read-only probe against live project).

---

## T-R4 — Add write_mode field to PlannedOverwrite

**Depends on**: None (purely additive to frozen dataclass)

Add `write_mode: str = "overwrite"` as the last field of `PlannedOverwrite` in
`models.py`. Valid values: `"overwrite"` | `"merge"`. Default `"overwrite"` ensures
all existing `PlannedOverwrite` construction sites are backward-compatible without
change.

**File**: `src/gramtrans/Lib/models.py`, class `PlannedOverwrite` at line 553.
**Insertion point**: after `owner_guid: str = ""` at line 572 (current last field).

**Checklist**:
- [ ] Add `write_mode: str = "overwrite"` after `owner_guid` (last field preserves
      positional backward compat since all existing callers use keyword args or the
      frozen default).
- [ ] Update the docstring to document the two valid values.
- [ ] Confirm no existing `PlannedOverwrite(...)` call site breaks (grep for
      `PlannedOverwrite(` and verify all use keyword args or omit write_mode).

---

## T-R2 — [FORK] Add fill_gaps kwarg to ApplySyncableProperties (BaseOperations)

**Depends on**: T-S1

**[FORK]** Edit `flexlibs2/code/BaseOperations.py:1028`.

Change signature to:
```python
def ApplySyncableProperties(self, item, props, ws_map=None, fill_gaps=False):
```

In the loop body (lines 1102-1172), add fill-gaps guards per R1:

- **multistring branch** (line 1105 `isinstance(value, dict)`): before `set_String`
  at line 1121, add:
  ```python
  if fill_gaps:
      existing = prop_obj.get_String(tgt_handle)
      if (existing.Text or "").strip():  # S1 to confirm: .Text returns None on empty ITsString
          continue  # target alt non-empty: target wins
  ```
  Use the call form confirmed by T-S1. NOTE: `existing` is always an ITsString (never
  None) in LCM 9.x; the `is not None` guard is unnecessary. `.Text` returns Python None
  on an empty ITsString, so the `or ""` coercion is required to avoid AttributeError on
  `.strip()`. Accepted alternative: `existing.RunCount > 0`.
- **plain str branch** (line 1124 `isinstance(value, str)`): before `setattr` at
  line 1140 (and the ITsString fallback), add:
  ```python
  if fill_gaps:
      current = getattr(item, prop_name, None)
      if current is not None and str(current).strip():
          continue  # target str non-empty: target wins
  ```
- **bool/int branch** (line 1163 `isinstance(value, bool) or isinstance(value, int)`):
  add at the top of the branch:
  ```python
  if fill_gaps:
      continue  # stored False/0 is a real choice; never overwrite in fill-gaps mode
  ```

**Reinstall after edit**: `pip install -e D:/Github/_Projects/_LEX/flexlibs2`

---

## T-R2b — [FORK] Propagate fill_gaps through all 8 Grammar subclass overrides

**Depends on**: T-R2

**[FORK]** Each of the 8 Grammar Operations subclass overrides calls
`super().ApplySyncableProperties(...)`. Add `fill_gaps=fill_gaps` to each super() call
and add `fill_gaps=False` to each override's signature.

Files and line numbers (all in `flexlibs2/code/Grammar/`):

| File | Line |
|------|------|
| `POSOperations.py` | 1159 |
| `MorphRuleOperations.py` | 914 |
| `GramCatOperations.py` | 640 |
| `InflectionFeatureOperations.py` | 1693 |
| `NaturalClassOperations.py` | 1074 |
| `EnvironmentOperations.py` | 707 |
| `PhonologicalRuleOperations.py` | 1448 |
| `PhonemeOperations.py` | 1328 |

For each file: change `def ApplySyncableProperties(self, item, props, ws_map=None)` to
`def ApplySyncableProperties(self, item, props, ws_map=None, fill_gaps=False)` and
thread `fill_gaps=fill_gaps` into the `super()` call.

**Reinstall after edit**: `pip install -e D:/Github/_Projects/_LEX/flexlibs2`

---

## T-R3 — Add fingerprint_with_owner helper to matcher.py

**Depends on**: T-S2

Add a pure helper to `src/gramtrans/Lib/matcher.py` after the existing fingerprint
functions (`fingerprint_for_msa` at line 94, `fingerprint_for_allomorph` at line 134):

```python
def fingerprint_with_owner(fn, obj, owner_guid_override, ws_handle=None):
    """Return the fingerprint produced by fn(obj, ws_handle) with tuple
    index 1 (owner_guid) replaced by owner_guid_override.

    Used by the merge-into planner path to evaluate source fingerprints
    against a resolved target entry (different GUID than the source entry),
    so that fingerprint matching correctly identifies already-present
    children under the resolved target.
    """
    fp = fn(obj, ws_handle)
    return (fp[0], owner_guid_override) + fp[2:]
```

**File**: `src/gramtrans/Lib/matcher.py`, new function after line ~170.

**Checklist**:
- [ ] Function is pure (no side effects, no LCM imports).
- [ ] Export via `__all__` if matcher.py uses one; otherwise leave as module-level.
- [ ] Unit test: `fingerprint_with_owner(fingerprint_for_msa, fake_msa, "new-guid")`
      returns a tuple with index 1 == "new-guid" and all other indices unchanged.

---

## T-FR009 — Extract _populate_entry_children helper from _execute_layer3

**Depends on**: None (pure extraction, no behavior change)

Extract the per-entry child-creation body from `transfer.py:_execute_layer3` lines
816-846 into a new function `_populate_entry_children`. The inline block creates:

1. Senses + MSAs (loop lines 820-836, calling `_create_lexsense_with_guid` at line 935
   and `_create_inflaff_msa_with_guid` at lines 1012-1015).
2. Allomorphs + environments (loop lines 840-846, calling `_create_allomorph_with_guid`
   at lines 1065-1068).

**Signature**:

```python
def _populate_entry_children(
    new_entry,
    src_entry,
    identity_remap: dict,
    source,
    target,
    target_verb,
    target_slot_by_guid: dict,
    env_guid_to_target: dict,
    tag,
    report_sink,
) -> None:
```

Replace the inline block at lines 816-846 with a call to `_populate_entry_children(...)`.
No behavior change; this task is a pure refactor that creates the shared call site for
T-FR008.

**Checklist**:
- [ ] Existing Layer-3 execution tests (if any) pass unchanged after extraction.
- [ ] The helper is private (underscore prefix).
- [ ] Docstring names the two call sites: normal add path (here) and merge-into path
      (T-FR008).

---

## T-FR008 — Executor: handle match_via="identity_remap" in ENTRY branch

**Depends on**: T-R4, T-FR009, T-R2, T-R2b, T-FR001

**File**: `src/gramtrans/Lib/transfer.py`, function `_execute_overwrite`, ENTRY
sub-branch at lines 1303-1335.

After locating `tgt_entry` (line 1307-1309) and `src_entry` (line 1314-1321) and
applying entry-level fields at line 1331, add a read of `overwrite.match_via` and
`overwrite.write_mode`:

1. Replace the bare `ApplySyncableProperties` call at line 1331 with:
   ```python
   target.LexEntry.ApplySyncableProperties(
       tgt_entry, src_props,
       fill_gaps=(overwrite.write_mode == "merge"),
   )
   ```

2. After the `apply_residue` call at line 1333, add the identity-remap branch:
   ```python
   if overwrite.match_via == "identity_remap":
       _populate_entry_children(
           tgt_entry, src_entry, identity_remap,
           source, target, target_verb, target_slot_by_guid,
           env_guid_to_target, tag, report_sink,
       )
   ```
   where `identity_remap`, `target_verb`, `target_slot_by_guid`, and
   `env_guid_to_target` must be threaded into `_execute_overwrite` from
   `_execute_layer3` (or re-derived from context available there).

**Checklist**:
- [ ] `write_mode="overwrite"` path: `fill_gaps=False` -> behavior byte-for-byte
      identical to pre-feature for all existing ENTRY overwrites.
- [ ] `write_mode="merge"` path: fill-gaps kwarg is passed; T-S3 tests confirm.
- [ ] `match_via="guid"` path: no `_populate_entry_children` call (existing behavior).
- [ ] `match_via="identity_remap"` path: children created under `tgt_entry`.
- [ ] Missing `tgt_entry` (GUID lookup fails): Warning logged, return early, no crash.

---

## T-FR006 — Thread identity_remap into Layer-3 planner signatures

**Depends on**: T-R4

**File**: `src/gramtrans/Lib/preview.py`

Add `identity_remap: dict` to the signature chain:

1. `_plan_layer3_for_pos` (`def` at line 286): add `identity_remap: dict` parameter.
2. `build_run_plan` call-site at line 83: pass `identity_remap=identity_remap`.
3. `_plan_layer3_verb_affixes_inner` (line 466 signature): add
   `identity_remap: dict` parameter.
4. `_plan_layer3_for_pos` -> `_plan_layer3_verb_affixes_inner` call at line 298:
   pass `identity_remap=identity_remap`.

The `identity_remap` dict (`build_run_plan` line 75) is already passed into `RunPlan`
at line 175. This task ensures it flows into the walker so T-FR001 can write into it.

**Checklist**:
- [ ] No callers of `_plan_layer3_for_pos` other than `build_run_plan` (grep to
      confirm); if any exist, add `identity_remap={}` default to preserve compat.
- [ ] Existing planner tests pass unchanged (the extra parameter with an empty dict
      is a no-op).

---

## T-FR001 — Planner: resolution hook in Layer-3 walker

**Depends on**: T-FR006, T-R3, T-R4

**File**: `src/gramtrans/Lib/preview.py`, function
`_plan_layer3_verb_affixes_inner`, after the Phase-1 overwrite check block
(lines 583-703).

After line 587 (`entry_is_overwrite` evaluated), and before the `if entry_is_overwrite:`
branch (line 589), add a resolution read:

```python
resolution = selection.similar_resolution_for(entry_guid)
```

Branch logic (insert between the Phase-1 `if entry_is_overwrite:` block and the
Phase-0 add block at line 705):

```
if not entry_is_overwrite and resolution is not None
        and resolution.action in ("overwrite", "merge"):
    # Identity-remap path: plan ENTRY action against the resolved target GUID.
    tgt_entry_for_remap = target_entry_index.get(resolution.target_guid)
    # Emit PlannedOverwrite with match_via="identity_remap"
    overwrites.append(PlannedOverwrite(
        category=GrammarCategory.ENTRY,
        source_guid=entry_guid,
        target_guid=resolution.target_guid,
        summary=f"LexEntry {entry_hw!r} -> identity remap",
        match_via="identity_remap",
        write_mode=resolution.action,
        pulled_in_by=() if selection.is_on(GrammarCategory.ENTRY)
                     else (src_verb_guid,),
        owner_guid="",
    ))
    identity_remap[entry_guid] = resolution.target_guid
    # Plan children against the resolved target entry.
    # MSA/allomorph fingerprint matching uses fingerprint_with_owner to
    # override owner GUID to the resolved target so cross-entry comparison works.
    if tgt_entry_for_remap is not None:
        _plan_identity_remap_children(
            entry, entry_guid, entry_hw, resolution.target_guid,
            tgt_entry_for_remap, src_verb_guid, src_slot_guids,
            source, target, selection,
            actions, skips, overwrites, seen_env_guids,
        )
    continue  # skip Phase-0 add path for this entry
```

For `resolution.action == "create_new"` or `resolution is None`, fall through to the
existing Phase-0 add path (no change required).

**Child planning helper** `_plan_identity_remap_children` (new private function):
Mirrors the Phase-1 MSA/allomorph fingerprint-match block (preview.py lines 609-703,
verified correct) but uses
`fingerprint_with_owner(fingerprint_for_msa, msa, resolution.target_guid)` and
`fingerprint_with_owner(fingerprint_for_allomorph, allo, resolution.target_guid)` so
fingerprint comparison is against the resolved target's children.

### Sub-task: Implement _plan_identity_remap_children

**File**: `src/gramtrans/Lib/preview.py`, new private function (add after the
`_match_allomorphs_by_fingerprint` helpers).

**Signature**:
```python
def _plan_identity_remap_children(
    src_entry,
    src_entry_guid: str,
    src_entry_hw: str,
    tgt_entry_guid: str,
    tgt_entry,
    src_verb_guid: str,
    src_slot_guids: set,
    source,
    target,
    selection: Selection,
    actions: list,
    skips: list,
    overwrites: list,
    seen_env_guids: set,
) -> None:
```

Mirrors lines 609-703 of `_plan_layer3_verb_affixes_inner` (the Phase-1 fingerprint block)
with these differences:
- Pass `tgt_entry_guid` (the resolved target GUID) as the owner override to
  `fingerprint_with_owner`, so MSA/allomorph fingerprints compare against children
  under the resolved target entry rather than the source entry.
- Use `tgt_entry` (the resolved target entry object) as the target for
  `_match_msas_by_fingerprint` and `_match_allomorphs_by_fingerprint`.

**Checklist**:
- [ ] Function is private (underscore prefix).
- [ ] `fingerprint_with_owner` is imported from `matcher.py` at call sites.
- [ ] All MSA/allomorph/PhEnvironment plan items emitted with `owner_guid=tgt_entry_guid`.
- [ ] No mutation of source or target project objects (planner-only, preview pass).
- [ ] Called from the identity-remap branch in T-FR001 when `tgt_entry_for_remap is not None`.

**Checklist** (T-FR001 overall):
- [ ] `similar_resolution_for` returns `None` for non-SIMILAR / unresolved entries:
      falls through to Phase-0 path unchanged.
- [ ] `create_new` resolution: falls through to Phase-0 path unchanged.
- [ ] `overwrite` resolution, target lacks entry GUID: identity-remap PlannedOverwrite
      emitted.
- [ ] `merge` resolution, target lacks entry GUID: identity-remap PlannedOverwrite with
      `write_mode="merge"` emitted.
- [ ] `identity_remap[entry_guid] == resolution.target_guid` after plan build.
- [ ] Phase-1 same-GUID overwrite path (entry_is_overwrite=True) takes priority:
      no resolution read for entries already in target by GUID.
- [ ] `_plan_identity_remap_children` called when `tgt_entry_for_remap is not None`;
      skipped (children deferred to executor) when resolved target not yet in index.

---

## T-R2c — Extract _apply_props_loop pure helper from ApplySyncableProperties

**Depends on**: T-R2

**Decision**: EXTRACT (not mock). The loop body in `BaseOperations.ApplySyncableProperties`
is extracted into a pure helper `_apply_props_loop(item, props, target_ws_by_id, fill_gaps)`
so T-S3a can call it directly without a live `self.project`. This is mandatory:
`self.project.WritingSystems.GetAll()` (BaseOperations.py:1099) fires unconditionally on
every `ApplySyncableProperties` call, so any test touching the method requires a real
project unless the loop body is isolated.

**File**: `flexlibs2/code/BaseOperations.py`

Extract the loop body (lines 1102-1172) into:
```python
def _apply_props_loop(item, props, target_ws_by_id, fill_gaps=False):
    """Pure loop body of ApplySyncableProperties. No project handle required.

    Args:
        item: LCM object to update.
        props: dict of {prop_name: value} from GetSyncableProperties.
        target_ws_by_id: dict of {ws_id: handle} for multistring WS resolution.
        fill_gaps: if True, skip non-empty target values (fill-gaps mode).
    """
    ...  # loop body moved here
```

`ApplySyncableProperties` calls `_apply_props_loop(item, props, ws_map_resolved, fill_gaps)`.

**Reinstall after edit**: `pip install -e D:/Github/_Projects/_LEX/flexlibs2`

**Checklist**:
- [ ] `_apply_props_loop` has no reference to `self` or `self.project`.
- [ ] `ApplySyncableProperties` behavior is byte-for-byte identical (pure refactor).
- [ ] All 8 Grammar subclass `super()` calls unchanged (they call `ApplySyncableProperties`,
      not `_apply_props_loop` directly).

---

## T-S3a — Unit test: fill-gaps never overwrites non-empty target alt

**Depends on**: T-R2, T-R2b, T-R2c

**File**: `tests/unit/test_013_fill_gaps.py` (new)

**Approach**: Call `_apply_props_loop` directly (see T-R2c). This is the chosen path
(EXTRACT, not mock) — the loop body is now a pure function with no project handle, so
fabricated `item` objects and fake `target_ws_by_id` dicts suffice. No `unittest.mock.patch`
needed.

Write a parametrized unit test covering all three value shapes:

| Shape | Test case | Expected outcome |
|-------|-----------|------------------|
| multistring | tgt alt non-empty after strip | `set_String` NOT called |
| multistring | tgt alt empty (strip yields "") | `set_String` called |
| plain str | target attr non-empty | `setattr` NOT called |
| plain str | target attr None | `setattr` called |
| bool/int | any target value | `setattr` NOT called (fill_gaps=True) |
| bool/int | any target value | `setattr` called (fill_gaps=False) |

**Checklist**:
- [ ] All six parameter combinations have an assertion.
- [ ] Test imports `_apply_props_loop` directly from `BaseOperations`.
- [ ] Test is marked `not integration` (no LCM fixture needed).

---

## T-S3b — Regression test: write_mode="overwrite" is byte-for-byte unchanged

**Depends on**: T-R4, T-R2, T-FR008

**File**: `tests/unit/test_013_executor_merge.py` (new)

Run the planner + executor with an empty `similar_resolutions` (or a
`write_mode="overwrite"` explicit resolution) against a fake source/target pair and
assert:

1. The resulting `plan.actions`, `plan.overwrites`, `plan.skips` are identical to the
   pre-feature baseline for that fixture (no new items, no changed items).
2. After execution, the fake target object's fields have the source values (source-wins,
   fill-gaps guards did not fire).

**Checklist**:
- [ ] Baseline captured as a fixture (dict of expected actions/overwrites/skips) before
      any feature-013 code lands.
- [ ] `assert plan_actions == baseline_actions` (not just len check).
- [ ] Test marked `not integration`.

---

## T-S3c — Integration test: merge write mode against real project pair

**Depends on**: T-S1, T-S2, T-FR001, T-FR008, T-R2, T-R2b | **Requires**: live LCM

**File**: `tests/integration/test_013_merge_live.py` (new) or added to existing
integration suite.

Run a headless transfer with a `SimilarResolution(X, "merge", Y)` against the
Ejagham Mini -> Ejagham Full GT-Test pair. After the run:

1. Assert that non-empty fields on target entry Y are unchanged.
2. Assert that empty/absent fields on Y have been filled from source entry X.
3. Assert X's senses / MSAs / allomorphs appear under Y.
4. Assert no duplicate children (fingerprint-matched children not re-created).

Mark `@pytest.mark.integration` so it is excluded from the default `not integration`
run.

**Checklist**:
- [ ] Test uses the real project path
      `C:/ProgramData/SIL/FieldWorks/Projects/Ejagham Full GT-Test`.
- [ ] Source project path set to Ejagham Mini (from existing integration fixture).
- [ ] Cleanup / rollback after run (or run against a copy).

---

## Dependency Summary

```
T-S1 ──────────────────────────────────> T-R2 -> T-R2b -> T-FR008
                                          T-R2 -> T-R2c -> T-S3a
T-S2 ────────────────────────────────────────────> T-R3 -> T-FR001 -> T-FR008
T-R4 ─────────────────────────────────────────────────> T-FR008, T-FR006
T-FR009 ──────────────────────────────────────────────> T-FR008
T-FR006 ──────────────────────────────────────────────> T-FR001
T-FR001 ──────────────────────────────────────────────> T-FR008, T-S3c
T-R2, T-R2b, T-R2c ───────────────────────────────────> T-S3a
T-R4, T-R2, T-FR008 ──────────────────────────────────> T-S3b
T-S3c requires T-S1, T-S2, T-FR001, T-FR008, T-R2, T-R2b, T-R2c
```

## Task Count

| ID | Description | Scope | Gate |
|----|-------------|-------|------|
| T-S1 | Live-verify multistring emptiness predicate | Read-only probe | Blocks T-R2 |
| T-S2 | Live-verify MSA/Allomorph Owner type | Read-only probe | Blocks T-R3 |
| T-R4 | Add write_mode to PlannedOverwrite | models.py | — |
| T-R2 | fill_gaps kwarg — BaseOperations | [FORK] BaseOperations.py | T-S1 |
| T-R2b | fill_gaps kwarg — 8 Grammar subclasses | [FORK] 8 files | T-R2 |
| T-R2c | Extract _apply_props_loop pure helper | [FORK] BaseOperations.py | T-R2 |
| T-R3 | fingerprint_with_owner helper | matcher.py | T-S2 |
| T-FR009 | Extract _populate_entry_children | transfer.py | — |
| T-FR008 | Executor identity_remap branch | transfer.py | T-R4, T-FR009, T-R2b, T-FR001 |
| T-FR006 | Thread identity_remap into planner | preview.py | T-R4 |
| T-FR001 | Resolution hook in Layer-3 walker | preview.py | T-FR006, T-R3, T-R4 |
| T-S3a | Unit test: fill-gaps predicate | tests/unit/ | T-R2, T-R2b, T-R2c |
| T-S3b | Regression: overwrite unchanged | tests/unit/ | T-R4, T-R2, T-FR008 |
| T-S3c | Integration: merge live project pair | tests/integration/ | All above |

**Total: 14 tasks** (2 spikes, 10 implementation, 2 unit verification, 1 integration gate)

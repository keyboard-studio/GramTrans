# Phase 3c Contract: 17.1 MSA-Slot Wiring Sub-Pass

**Date**: 2026-06-22
**Spec FR**: FR-333
**Data model**: [../data-model.md#e5--171-msa-slot-wiring-sub-pass](../data-model.md)

The 17.1 sub-pass wires `IMoInflAffMsa.SlotsRC` after both affix MSAs (from `AFFIXES` category) and slots (from `SLOTS` category) are stable in target. It runs as a post-execute tail block on the `AFFIX_TEMPLATES` executor — chosen as the wiring site because templates already need slots in target (they consume `PrefixSlotsRS`/`SuffixSlotsRS`), so the dispatch step where slot-availability is guaranteed is the same step where 17.1 runs.

## Contract

**Trigger**: After `AFFIX_TEMPLATES.execute_action` has written every template's slot references for the current `src_pos_guid`. Before the dispatch loop advances to the next category (`STEMS`).

**Input**: `plan.msa_slot_bindings: dict[Guid, list[Guid]]` — populated during `AFFIXES.plan_action` with `(msa_guid, [src_slot_guid, ...])` entries for each affix MSA whose source `SlotsRC` was non-empty.

**Output**: Side-effecting writes on target MSAs' `SlotsRC` reference collections. No new `PlannedAction`s; the wire emits `Skip(DEPENDENCY_UNRESOLVED)` into the run report on missing target MSA/slot.

## Algorithm

```text
for (src_msa_guid, src_slot_guids) in plan.msa_slot_bindings.items():
    # Resolve MSA in target
    target_msa_guid = run_ctx.identity_remap.get(src_msa_guid, src_msa_guid)
    target_msa = target.get_object_by_guid(target_msa_guid)
    if target_msa is None:
        emit Skip(DEPENDENCY_UNRESOLVED, detail=f"msa_guid={src_msa_guid} not in target after affix transfer")
        continue
    # Resolve each slot in target (slots are GUID-preserved per E8)
    for src_slot_guid in src_slot_guids:
        target_slot = target.get_object_by_guid(src_slot_guid)
        if target_slot is None:
            emit Skip(DEPENDENCY_UNRESOLVED, detail=f"slot_guid={src_slot_guid} not in target after slot transfer")
            continue
        target_msa.SlotsRC.Add(target_slot)
```

## Invariants

1. **Idempotency**: Re-running 17.1 against a fully-wired target produces zero new writes — `target_msa.SlotsRC` already contains the resolved slot; `Add` is a no-op for already-present references (verified semantics on `ILcmReferenceCollection`).
2. **No PlannedAction inflation**: 17.1 writes are NOT counted as new actions in `RunReport.added_count`. They are side effects of `AFFIX_TEMPLATES` execution.
3. **Skip granularity**: Each unresolved MSA or slot produces one Skip entry. A single MSA with two unresolved slots produces two Skip entries (one per unresolved slot reference).
4. **No fallback**: Unresolved slot GUIDs are NOT fingerprint-matched, NOT name-matched, NOT closured to GOLD. Skip-and-report only.

## Tests

| Test | Asserts |
|---|---|
| `test_categories_affix_templates.py::test_171_basic_wiring` | 1 MSA with 1 slot binding → 1 `SlotsRC` write after templates execute |
| `test_categories_affix_templates.py::test_171_multi_slot_per_msa` | 1 MSA with 3 slot bindings → 3 `SlotsRC.Add` calls in source order |
| `test_categories_affix_templates.py::test_171_unresolved_slot` | 1 MSA, 2 slots stashed, 1 slot missing in target → 1 successful Add + 1 `Skip(DEPENDENCY_UNRESOLVED)` |
| `test_categories_affix_templates.py::test_171_unresolved_msa` | 1 binding, MSA absent from target → 1 `Skip(DEPENDENCY_UNRESOLVED)` with msa_guid detail |
| `test_categories_affix_templates.py::test_171_idempotent_rerun` | Pre-wired target + same plan → 0 net writes, 0 new skips |
| `test_categories_affix_templates.py::test_171_unbound_affix` | Source MSA with empty `SlotsRC` → no entry in `plan.msa_slot_bindings`; MSA remains unbound (matches Ejagham Mini `ro~-` case) |

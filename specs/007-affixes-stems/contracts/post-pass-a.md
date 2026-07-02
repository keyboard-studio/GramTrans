# Phase 3c Contract: Post-Pass A (LexEntryRef Wiring)

**Date**: 2026-06-22
**Spec FR**: FR-340
**Data model**: [../data-model.md#e7--lexentryref-post-pass-a](../data-model.md)

Post-pass A wires `ILexEntryRef.ComponentLexemesRS` and `PrimaryLexemesRS` after both affix LexEntries (from `AFFIXES`) and stem LexEntries (from `STEMS`) are stable in target. It runs as a post-execute tail block on the `STEMS` executor — the last category in the Phase 3c block — because stem-to-affix and stem-to-stem references are both expected.

## Contract

**Trigger**: After `STEMS.execute_action` has written every stem entry's owned-child closure. Before the dispatch loop advances past `STEMS` (effectively the end of Phase 3c).

**Input**: `plan.lexentry_ref_bindings: dict[Guid, dict[str, list[Guid]]]` — populated during `AFFIXES.plan_action` AND `STEMS.plan_action` with `{src_entry_guid: {"ComponentLexemesRS": [...], "PrimaryLexemesRS": [...]}}` entries for each entry whose source EntryRef collections were non-empty.

**Output**: Side-effecting writes on target EntryRefs' `ComponentLexemesRS`/`PrimaryLexemesRS` reference sequences. Emits `Skip(DEPENDENCY_UNRESOLVED)` on unresolved component lexemes.

## Algorithm

```text
for (src_entry_guid, ref_dict) in plan.lexentry_ref_bindings.items():
    target_entry = target.get_object_by_guid(src_entry_guid)
    if target_entry is None:
        emit Skip(DEPENDENCY_UNRESOLVED, detail=f"entry_guid={src_entry_guid} not in target after affixes+stems transfer")
        continue
    # Walk EntryRefs on the target entry (source order preserved)
    for (src_ref, target_ref) in zip(src_entry.EntryRefsOS, target_entry.EntryRefsOS):
        for field_name in ("ComponentLexemesRS", "PrimaryLexemesRS"):
            src_guids = ref_dict.get(field_name, [])
            for src_lex_guid in src_guids:
                # Resolve against (a) in-plan creation list, (b) target-by-GUID
                target_lex = (
                    run_ctx.in_plan_entries.get(src_lex_guid)
                    or target.get_object_by_guid(src_lex_guid)
                )
                if target_lex is None:
                    emit Skip(DEPENDENCY_UNRESOLVED, detail=f"{field_name} component {src_lex_guid} unresolved")
                    continue
                getattr(target_ref, field_name).Add(target_lex)
```

## Resolution rules (FR-340)

1. **In-plan first**: `run_ctx.in_plan_entries` is the set of entry guids created during the current `transfer.execute(plan, ...)` call (both affixes and stems). This is the authoritative source for entries that didn't exist in target before the run.
2. **Target-by-GUID second**: For lexemes already in target from prior runs/manual edits.
3. **No fingerprint fallback**: Per FR-340, post-pass A MUST NOT scan target for fuzzy/name/form matches.
4. **No persistent state**: Bindings are NOT serialised, NOT carried across runs. Re-derivation from source on each invocation is the contract.

## Invariants

1. **Idempotency**: Re-running post-pass A against a fully-wired target produces zero net writes. `ILcmReferenceSequence.Add` of an already-present reference is implementation-defined; the executor MUST check membership before Add to guarantee no-op on re-run.
2. **Source order preserved**: The order of `ComponentLexemesRS` and `PrimaryLexemesRS` MUST match source. Even when some references skip, the remaining wired references retain their relative position.
3. **Skip granularity**: One Skip per unresolved component lexeme. An EntryRef with 3 components and 1 unresolved produces 1 Skip + 2 successful Adds.
4. **EntryRefsOS pairing**: Target EntryRefs are owned children created by `AFFIXES.execute_action` / `STEMS.execute_action`; their source-order pairing with `src_entry.EntryRefsOS` is guaranteed by atomic-owned-child-write contract (E2).

## Tests

| Test | Asserts |
|---|---|
| `test_phase3c_post_pass_a.py::test_basic_component_wiring` | 1 entry with 1 EntryRef + 2 ComponentLexemes (both in-plan) → 2 Adds |
| `test_phase3c_post_pass_a.py::test_target_by_guid_resolution` | 1 component in-plan + 1 component already in target by GUID → both wired |
| `test_phase3c_post_pass_a.py::test_unresolved_component` | 1 component neither in-plan nor in target → 1 Skip(DEPENDENCY_UNRESOLVED) |
| `test_phase3c_post_pass_a.py::test_primary_lexemes_field` | 1 EntryRef with non-empty `PrimaryLexemesRS` only → wires that field correctly |
| `test_phase3c_post_pass_a.py::test_no_persistent_state` | Two `execute()` calls back-to-back; second call re-derives bindings from source, NOT from a cached file |
| `test_phase3c_post_pass_a.py::test_no_fingerprint_fallback` | Source guid X has a target entry with matching CitationForm but different guid → still emits Skip; does NOT match by form |
| `test_phase3c_post_pass_a.py::test_idempotent_rerun` | Pre-wired target + same plan → 0 net Adds (membership check guards) |
| `test_phase3c_post_pass_a.py::test_source_order_preserved` | 3 components, middle one unresolved → final RS contains 2 components in correct relative positions |

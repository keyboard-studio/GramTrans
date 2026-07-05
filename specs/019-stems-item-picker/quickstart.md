# Quickstart / Validation: Stems Item Picker (019)

Validates the feature end-to-end against a live source→target FLEx pair. See
[data-model.md](./data-model.md) and [contracts/stems-item-picker.md](./contracts/stems-item-picker.md)
for the shapes referenced here.

## Prerequisites

- FlexTools host with `pyflexicon>=4.1` installed (`pip install -e D:/Github/_Projects/_LEX/flexlibs2`).
- A **source** project containing both affix-morphtype and stem-morphtype entries (Ejagham Mini
  or similar), and a **target** project bound on the Project+WS page.
- Worktree: `D:/Github/_Projects/_LEX/GramTrans-019-stems-item-picker`.

## Unit test run

```
pytest tests/unit/test_stem_partition.py \
       tests/unit/test_build_stem_inventory.py \
       tests/unit/test_selection_invariants.py \
       tests/unit/test_selection_ui.py -q
```

Expected: partition is complete + disjoint; null-guard cases (null lexeme form, null
morphtype, uncastable morphtype) all land in the Stems tab; stem closure walks POS deps, not
slots; `stem_picks` invariant enforced.

## Live wizard scenarios

1. **SC-001 partition** — Open the Item picker. The Stems tab is enabled (no "[STUBBED]"),
   lists exactly the stem-morphtype entries; the Affixes tab lists only affixes. No entry in
   both. Verify an entry with a null/odd morphtype appears in Stems (not dropped).
2. **SC-002/003 closure** — Pick a stem whose sense MSA references a POS P not otherwise
   selected. Advance: P (and its inflection class / stem name) is preselected on
   Skeleton / Grammatical-deps and appears in the plan. Deselect the stem: P is dropped from
   the plan (unless another kept item needs it).
3. **SC-004 target status** — Bind source=target: every stem row reads IN TARGET. Bind a fresh
   target: rows read NEW. No target bound: status column blank, no crash.
4. **SC-005 aggregated warning** — Keep a stem needing POS P; deselect P on Skeleton against a
   target lacking P. Preview shows one entry-centric warning naming the stem; Move pops a
   single consolidated confirmation (with other omissions folded in, still one dialog).
5. **SC-006 empty tab** — Bind a source with zero stems: the Stems tab renders empty (non-stub,
   non-error); the wizard advances.
6. **SC-007 no conflict UI** — Confirm the pane shows no ADD_NEW/MERGE/OVERWRITE control; the
   Layer-1 default applies automatically.

## Verification artifacts (constitution gate)

Run a dry-run then Move on the source→fresh-target pair with a mixed stem+affix selection.
Attach pre/post Import Residue artifacts. Confirm: create-vs-skip by GUID, GOLD-skip, shared
POS pulled once (dedup), owned-child closure travels with each stem.

# Tasks: Skeleton + Grammatical-Deps Selectors

**Feature dir**: `specs/009-skeleton-deps-selectors/` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

TDD-ordered. Reuse from 008: `_cast`, `AffixRow.status`/`_entry_status`/`_build_target_sets`,
POS enumeration, and the fake-handle pattern in `tests/unit/_fakes_affix.py` (extend, don't
fork). Out of scope: phonology & other blocks, conflict-mode UI, GramTrans #1/#2.

## Phase 1: Setup

- [ ] T001 Extend `tests/unit/_fakes_affix.py` with fakes for slots (`AffixSlotsOC`,
  `IMoInflAffixSlot`), templates (`AffixTemplatesOS`, referenced-slot sequences),
  `IMoInflAffMsa.SlotsRC`, `InflectableFeatsRC`, `InflectionClassesOC`, `StemNamesOC`,
  `ExceptionFeaturesOC` — duck-typed, no pythonnet.

## Phase 2: Foundational — pure builders + collapse (blocks the UI)

- [ ] T002 [P] Unit tests for `build_skeleton_inventory` in `tests/unit/test_skeleton_inventory.py`:
  POS preselected iff a picked affix attaches; slot preselected iff a picked affix fills it
  (SlotsRC); unfilled POS slots present-but-unchecked; per-slot affix count; template lists
  slots read-only; template preselected when it arranges a referenced slot; POS-rooted nesting;
  empty-POS pruning.
- [ ] T003 [P] Unit tests for template-forces-slots + no-affix-re-expansion in
  `tests/unit/test_skeleton_inventory.py`: selecting a template yields its full referenced slot
  set (incl. empty extras); deselecting yields only affix-filled slots; affix_picks unchanged
  either way.
- [ ] T004 [P] Unit tests for `build_deps_inventory` in `tests/unit/test_deps_inventory.py`:
  features/classes/stem-names/exception-features derived from picked affixes' POSes, all
  preselected; empty collections render empty (no error); target-status per row.
- [ ] T005 [P] Unit tests for EXCLUDED-LOSSY aggregation in
  `tests/unit/test_excluded_lossy_grouping.py`: N deselected-needed-absent items -> N entry
  warnings but ONE consolidated gate payload; items present in target -> no warning (LINK).
- [ ] T006 Implement `build_skeleton_inventory(source, affix_picks, target=None)` +
  skeleton dataclasses in `src/gramtrans/Lib/selection.py` (reuse `_cast`, status, POS-walk;
  read `AffixSlotsOC`/`AffixTemplatesOS`/`IMoInflAffMsa.SlotsRC` with casts). Makes T002/T003 pass.
- [ ] T007 Implement `build_deps_inventory(source, affix_picks, target=None)` + deps dataclasses
  in `src/gramtrans/Lib/selection.py` (InflectableFeatsRC / InflectionClassesOC / StemNamesOC /
  ExceptionFeaturesOC with casts). Makes T004 pass.
- [ ] T008 Implement the EXCLUDED-LOSSY derivation + aggregation helper (pure) feeding the
  Preview warning channel in `src/gramtrans/Lib/preview.py` / `selection.py`. Makes T005 pass.

## Phase 3: US1 — Preselect affixes (P1)

- [ ] T009 [US1] Default every affix row + group tristate to checked in `_PageItemPicker`
  (`src/gramtrans/Lib/ui/selection_wizard.py`); confirm collapse yields all affixes pre-interaction.
- [ ] T010 [P] [US1] Unit test preselect-all state -> `affix_picks` == all source affixes.

## Phase 4: US2 — Skeleton page (P1)

- [ ] T011 [US2] Add `_PageSkeleton` in `src/gramtrans/Lib/ui/selection_wizard.py`: POS-rooted
  tree, Slots + Templates subgroups, per-slot affix counts, templates list slots read-only,
  target-status column; `initializePage` builds from affix picks + bound target.
- [ ] T012 [US2] Implement template check/deselect semantics (force full slot set; never
  re-expand affix picks) and collapse of skeleton selection into the plan.
- [ ] T013 [P] [US2] Live MCP integration in `tests/integration/test_skeleton_deps_live.py`:
  Ejagham — v (4 slots, 1 template), n & num (1 slot, 1 template), 28/33 affix MSAs map to a
  slot; assert preselection + counts. (Written; main session executes.)

## Phase 5: US3 — Grammatical-deps page (P2)

- [ ] T014 [US3] Add `_PageGramDeps` in `src/gramtrans/Lib/ui/selection_wizard.py`: sections
  for features/classes/stem-names/exception-features, preselected + per-item deselectable,
  target-status column; empty sections render cleanly.
- [ ] T015 [P] [US3] Extend live integration: Ejagham deps (0 classes, 0 stem names, features
  0–1 per POS) render preselected without error.

## Phase 6: US4/US5 — Status + closure safety (P1/P2)

- [ ] T016 [US4] Ensure target-status column populates on skeleton + deps rows (reuse FR-018
  logic); blank when no target.
- [ ] T017 [US5] Wire skeleton/deps deselections into the Preview EXCLUDED-LOSSY warning list
  and the SINGLE consolidated confirm-on-Move dialog (`selection_wizard.py` finish handler +
  `stats_panel`); never per-item prompts.
- [ ] T018 [P] [US5] Unit test the Move-gate payload aggregates all omissions into one dialog.

## Phase 7: Sequence + polish

- [ ] T019 Rewire the wizard page order to Project+WS → Affixes → Skeleton → Grammatical deps
  → Preview → Finish in `src/gramtrans/Lib/ui/selection_wizard.py`; remove `_PageScopeConflict`
  from the flow (keep the class or delete per lead call); update page-index references
  (Preview/Finish `wizard.page(n)`).
- [ ] T020 Apply Layer-1 conflict-mode defaults automatically in the plan build (no UI);
  confirm no ADD/MERGE/OVERWRITE controls remain on selection pages.
- [ ] T021 Run `python -m pytest tests/unit -q`; fix any page-index/regression fallout from
  the sequence rewire. Confirm >= prior baseline + new tests.
- [ ] T022 Manual UI smoke on Ejagham per quickstart: preselected affixes → skeleton
  preselected with slot counts → deps preselected → deselect a filled slot → one Move warning.

## Dependencies & Order

Setup (T001) → Foundational builders (T002–T008) block the pages. US1 (T009–T010) independent.
US2 (T011–T013) needs T006. US3 (T014–T015) needs T007. US4/US5 (T016–T018) need T006–T008.
Sequence rewire (T019) after pages exist. Polish (T020–T022) last.
Live integration tasks (T013, T015) share one file — write sequentially; main session runs them.

## MVP

US1 + US2 (T001–T013): affixes preselected and the skeleton page derived/preselected — the
core value; deps page and full closure-safety follow.

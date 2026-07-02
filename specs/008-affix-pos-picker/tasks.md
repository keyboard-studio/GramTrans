# Tasks: Affixes-by-POS Item Picker

**Feature dir**: `specs/008-affix-pos-picker/` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

TDD ordering: within each phase, tests (fake handles) come before the implementation
they cover. Live MCP integration assertions land in the story they prove.

**Out of scope (do NOT touch)**: GramTrans issues #1 (`affixes_dependencies` derivational
closure) and #2 (`affixes_enumerate_source` EntriesOC). Tracked separately.

---

## Phase 1: Setup

- [ ] T001 Create test module skeletons with imports and xfail placeholders: `tests/unit/test_pos_grouped_inventory.py`, `tests/unit/test_affix_pos_collapse.py`, `tests/integration/test_affix_pos_picker_live.py` (so the suite collects before implementation).
- [ ] T002 [P] Add a shared fake-handle helper for affix/MSA/POS duck types (`.ClassName`, `.PartOfSpeechRA`, `.FromPartOfSpeechRA`, `.ToPartOfSpeechRA`, `MorphoSyntaxAnalysesOC`, `LexemeFormOA.MorphTypeRA.IsAffixType`, `SensesOS[*].Gloss`, POS `SubPossibilitiesOS`) in `tests/unit/_fakes_affix.py`, mirroring the existing selection-helper fake pattern.

## Phase 2: Foundational (blocks all user stories)

Shared model + pure builder + pure collapse/mirroring helpers in `src/gramtrans/Lib/selection.py`.

- [ ] T003 [P] Unit test the data types in `tests/unit/test_pos_grouped_inventory.py`: `AffixRow`, `PosNode`, `JunkDrawer`, `PosGroupedAffixInventory` are frozen dataclasses with the fields from [data-model.md](./data-model.md) and `all_affix_guids()` dedups.
- [ ] T004 [P] Unit test `build_pos_grouped_inventory` grouping in `tests/unit/test_pos_grouped_inventory.py`: inflectional/unclassified fake MSAs group under `PartOfSpeechRA`; POS hierarchy nesting preserved (no rollup); rows sorted alpha by form; glosses deduped and `"; "`-joined with `"(no gloss)"` fallback; label prefers Abbreviation then Name.
- [ ] T005 [P] Unit test derivational + junk classification in `tests/unit/test_pos_grouped_inventory.py`: a deriv fake (From/To) yields one row in From node `deriv_attaches` and one in To node `deriv_produces`; a multi-POS affix yields a row in each reached group; MSA-with-null-POS → `junk.no_pos`; no-sense/no-MSA → `junk.no_analysis`; unrecognized `ClassName` → junk.
- [ ] T006 [P] Unit test `collapse_pos_grouped` in `tests/unit/test_affix_pos_collapse.py`: checked GUIDs (incl. one appearing in N groups) collapse to a `Selection` whose `affix_picks` is the deduped set; template/slot picks empty; unknown GUIDs filtered.
- [ ] T007 [P] Unit test `mirror_check_state` in `tests/unit/test_affix_pos_collapse.py`: given fake items sharing a GUID, returns matching `(item, state)` assignments for every appearance.
- [ ] T008 Implement the data types (`AffixRow`, `PosNode`, `JunkDrawer`, `PosGroupedAffixInventory` + `all_affix_guids`) in `src/gramtrans/Lib/selection.py` per [data-model.md](./data-model.md). Keep existing `SourceAffixInventory` untouched. (Makes T003 pass.)
- [ ] T009 Implement `build_pos_grouped_inventory(source)` in `src/gramtrans/Lib/selection.py` per [contracts/pos-grouped-inventory.md](./contracts/pos-grouped-inventory.md): `LexDbOA.Entries` + `IsAffixType` filter; POS hierarchy from `PartsOfSpeechOA`; `msa.ClassName` dispatch with guarded `ICmPossibility`/`ILexEntry`/`IMultiAccessorBase`/concrete-MSA casts; defensive per-object skip → junk; deterministic ordering. (Makes T004, T005 pass.)
- [ ] T010 Implement `collapse_pos_grouped(checked_guids, inventory)` and pure `mirror_check_state(items, new_state)` in `src/gramtrans/Lib/selection.py`, reusing `PickerState`/`build_selection` unchanged. (Makes T006, T007 pass.)

## Phase 3: User Story 1 — See affixes grouped by attaches-to POS (P1)

**Goal**: page 2 populates from the bound source, grouped by POS, no empty pane.
**Independent test**: bind Ejagham, open page 2 → 33 affixes under v/n/num/pro + 1 junk.

- [ ] T011 [US1] Rework `_PageItemPicker._build_ui` and add `populate_pos_tree(inventory)` in `src/gramtrans/Lib/ui/selection_wizard.py`: 4-column tree (Affix form→glosses | Type | From | To), nested POS nodes → subgroup nodes → per-`(entry,group)` rows; store `entry_guid`/kind on each item via item-data roles.
- [ ] T012 [US1] Wire `_PageItemPicker.initializePage` in `src/gramtrans/Lib/ui/selection_wizard.py` to build the inventory from the bound source (page 0 context) via `build_pos_grouped_inventory` and call `populate_pos_tree` — the currently-missing feed. Guard for no-source (empty labeled tree, no crash).
- [ ] T013 [P] [US1] Live MCP integration in `tests/integration/test_affix_pos_picker_live.py`: build inventory for **Ejagham Full GT-Test**; assert 33 affixes, all inflectional, attaches-to groups v:14/n:11/num:6/pro:1, 0 multi-POS, 1 no-POS junk (anchors from [contracts/pos-grouped-inventory.md](./contracts/pos-grouped-inventory.md)).

## Phase 4: User Story 2 — Select by group, refine per item (P1)

**Goal**: group-check selects attaches-to affixes; per-item deselect; collapse to `affix_picks`.
**Independent test**: check Verb group, deselect one → selection = verb-attaching minus that one.

- [ ] T014 [US2] Implement group/parent check semantics in `src/gramtrans/Lib/ui/selection_wizard.py`: Qt auto-tristate so a POS-node check sweeps the Inflectional + Derivation-attaches subgroups and descendant POS nodes, but NOT the Derivation-produces subgroup (structure produces rows so the header tristate excludes them).
- [ ] T015 [US2] Implement `_PageItemPicker.picker_state()`/`collect_selection` to gather checked leaf `entry_guid`s and route through `collapse_pos_grouped` in `src/gramtrans/Lib/ui/selection_wizard.py`; ensure page-4 preview reads the resulting `affix_picks`.
- [ ] T016 [US2] Implement the `itemChanged` GUID-mirroring handler in `src/gramtrans/Lib/ui/selection_wizard.py` using `mirror_check_state`, under a `_mirroring` re-entrancy guard (replaces the current stub). 
- [ ] T017 [P] [US2] Unit test the collapse/mirroring wiring at the state level in `tests/unit/test_affix_pos_collapse.py` (extend): a picker-state fixture with a group-checked set minus a deselected GUID yields the expected `affix_picks`; produces-only GUIDs excluded from a header check.

## Phase 5: User Story 3 — Derivational affixes by direction (P2)

**Goal**: deriv affix under both From group and To produces-subgroup, annotated; toggling mirrors.
**Independent test**: bind Esperanto, `igi (From=Root,To=v)` in both places; toggle mirrors.

- [ ] T018 [US3] Ensure `populate_pos_tree` renders the Derivation—attaches-to and Derivation—produces subgroups with From/To column annotations in `src/gramtrans/Lib/ui/selection_wizard.py` (builder already supplies the rows; this is the render + labeling).
- [ ] T019 [P] [US3] Live MCP integration in `tests/integration/test_affix_pos_picker_live.py`: build inventory for **Esperanto**; assert 68 affixes (infl=41/deriv=31/uncl=12), attaches-to Root:43/v:12/VRoot:9/ARoot:3/n:3/NRoot:2/adj:2, produces n:14/v:10/adj:5/adv:1, 13 multi-POS.

## Phase 6: User Story 4 — Unattached affixes drawer (P2)

**Goal**: no-POS and no-sense/no-MSA affixes visible in a two-subgroup drawer, selectable.
**Independent test**: Esperanto → 7 affixes in the "no part of speech" subgroup.

- [ ] T020 [US4] Render the "Unattached affixes" drawer with `no_pos` and `no_analysis` subgroups in `src/gramtrans/Lib/ui/selection_wizard.py`; rows checkable/selectable like any group (From/To columns show em-dash).
- [ ] T021 [P] [US4] Extend the live integration assertions in `tests/integration/test_affix_pos_picker_live.py`: Esperanto junk `no_pos=7`, `no_analysis=0`; Ejagham junk `no_pos=1`.

## Phase 7: Polish & Cross-Cutting

- [ ] T022 [P] Add a module-docstring note to `src/gramtrans/Lib/ui/affix_tree_picker.py` marking the standalone dialog legacy/unused for the wizard path and pointing at `_PageItemPicker` (per research R6); confirm its existing unit tests still pass (template-shaped inventory retained).
- [ ] T023 [P] Run the full unit suite (`python -m pytest tests/unit -q`) and confirm no regressions in existing selection/wizard tests; fix any fallout from the `_PageItemPicker` rework.
- [ ] T024 Manual UI smoke on Esperanto per [quickstart.md](./quickstart.md) (populate, subgroups, group-check excludes produces, multi-POS mirror, preview reflects picks); record result.

---

## Dependencies & Order

- **Setup (T001–T002)** → **Foundational (T003–T010)** blocks everything.
- **US1 (T011–T013)** depends on Foundational; is the MVP.
- **US2 (T014–T017)** depends on US1 (tree must render before selection wiring).
- **US3 (T018–T019)** depends on US1 render + Foundational builder (deriv already built).
- **US4 (T020–T021)** depends on US1 render + Foundational builder (junk already built).
- **Polish (T022–T024)** last.

## Parallel Opportunities

- T003–T007 (unit tests, distinct files/areas) run in parallel before T008–T010.
- T013, T019, T021 are all in the live integration file — write sequentially (same file)
  even though marked per-story; the [P] reflects story-independence, not file-independence.
- T022, T023 parallel in Polish.

## MVP Scope

**US1 only (T001–T013)**: the picker populates and shows affixes grouped by attaches-to
POS for the inflectional baseline — this alone unblocks the wizard's page 2 and is
independently demoable on Ejagham.

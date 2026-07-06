# Tasks: Lexical-Entry Types Page (Model-B Independent Block)

**Feature dir**: `specs/021-lexical-entry-types-page/` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

TDD-ordered. Reuse from 008/009/010: `_guid_str_from`, target-status logic, fake-handle
pattern in `tests/unit/_fakes_phonology.py` (extend, don't fork). Mirror spec 010
throughout; `_PagePhonology` is the structural template.

**Engine reality**: `leaf_item_picks` already exists on `Selection` (models.py:368).
Per-item trim (US2/FR-005) requires the contained engine touch in Phase 2. **Absent
`leaf_item_picks` key => transfer all** -- the guard that keeps all existing tests and
FR-307 idempotency intact.

**GOLD-detection gate**: `_is_gold_entry_type(node)` in `categories.py` is the single
reswap point. It delegates to `_is_gold` now; the TODO documents the reswap contract.

**Out of scope**: phonology, affixes, custom fields, stems, semantic domains, ad-hoc
rules, conflict-mode UI, KL-021-2 (extended feature-structure reference traversal).

---

## Phase 1: Setup

- [x] T001 Extend `tests/unit/_fakes_phonology.py` with entry-type fakes (no
  pythonnet):
  - `FakeInflFeatSpec(value_ref)`: `.ValueRA = value_ref` stand-in for
    `IFsFeatureSpecification`
  - `FakeInflFeatStruc(specs)`: `.FeatureSpecsOC = [...]` stand-in for
    `IFsFeatStruc` (used by `InflFeatsOA`)
  - `FakeEntryType(guid, name, *, catalog_source_id=None, raw_guid=None,
    sub_possibilities=())`: base entry type. `.guid`, `.Guid`, `.Name`, `.CatalogSourceId`
    (None or non-empty string to exercise `_is_gold`), `.SubPossibilitiesOS` list
  - `FakeInflEntryType(guid, name, *, infl_feats=(), catalog_source_id=None,
    raw_guid=None, sub_possibilities=())`: `ILexEntryInflType` stand-in. Inherits
    `FakeEntryType`; adds `.InflFeatsOA = FakeInflFeatStruc(infl_feats)` (or None
    when `infl_feats` is empty)
  - `FakePossibilityList(items)`: `.PossibilitiesOS = list(items)` (no `.GetAll()` --
    `_walk_possibilities` accesses `.PossibilitiesOS` / `.SubPossibilitiesOS` directly)
  - `FakeLexDb(*, variant_entry_types=(), complex_entry_types=())`: exposes
    `.VariantEntryTypesOA = FakePossibilityList(variant_entry_types)` and
    `.ComplexEntryTypesOA = FakePossibilityList(complex_entry_types)`
  - `FakeLexDbSource(lex_db)`: `.Cache.LangProject.LexDbOA = lex_db` (nested via
    simple attribute objects); also exposes `.VariantEntryTypesOA` and
    `.ComplexEntryTypesOA` as shortcuts for direct-attribute path tests
  - GUIDs mixed-case + braces on `.Guid` to exercise `_guid_str_from` normalization

---

## Phase 2: Foundational (blocks all user stories)

**CRITICAL**: engine touch + GOLD isolation + pure builder. No page work until done.

### Engine touch -- leaf_item_picks filter (Workstream 1)

- [x] T002 [P] Unit tests for the `leaf_item_picks` enumerate filter in
  `tests/unit/test_leaf_item_picks_entry_types.py`:
  - Key absent => all items (back-compat; VARIANT_TYPES and COMPLEX_FORM_TYPES)
  - Key present => only those GUIDs (frozenset of normalized GUIDs)
  - Empty frozenset => zero items returned
  - GUID match works with mixed-case/braced source `.Guid` vs normalized picks
    (both sides via `_guid_str_from`)
  - A `leaf_item_picks` key for a category with `is_on(cat) is False` is inert
    (the `is_on` gate in leaf-dispatch fires first; the enumerate filter alone does
    not control transfer)
  - A GOLD item (catalog_source_id set) in the source list is still returned when
    picks is None (transfer-all); filtered out only when its guid is not in picks
  - Empty-user-defined-list (picks is empty frozenset) is NOT the same as picks=None:
    zero items returned, not all items (FR-006 distinction)

- [x] T003 Add `_is_gold_entry_type(node)` helper to
  `src/gramtrans/Lib/categories.py` immediately after `_is_gold` (line ~91):
  - Delegates to `_is_gold(node)` now
  - Carries the TODO reswap contract comment (see plan.md GOLD-Detection Gate)
  - Used by `build_entry_types_inventory`; NOT used by existing `variant_types_plan_action`
    or `complex_form_types_plan_action` (those are out of scope -- they keep calling
    `_is_gold` directly)

- [x] T004 Extend `variant_types_enumerate_source` (categories.py:1066-1069) to
  filter the result of `_walk_possibilities_via_lexdb` by
  `selection.leaf_picks_for(GrammarCategory.VARIANT_TYPES)` when not None, comparing
  `_guid_str_from(r)` (NOT raw `.Guid`). Makes T002 pass for VARIANT_TYPES. Confirm
  `is_on` still gates before enumerate in `src/gramtrans/Lib/preview.py` leaf-dispatch.
  **Churn constraint**: edit only lines 1066-1069; do not refactor helper signatures.

- [x] T005 Extend `complex_form_types_enumerate_source` (categories.py:1219-1222)
  identically for `GrammarCategory.COMPLEX_FORM_TYPES`. Makes T002 pass for
  COMPLEX_FORM_TYPES. Same churn constraint.

### Pure builder + collapse + missing-ref derivation (Workstream 3)

- [x] T006 [P] Unit tests for `build_entry_types_inventory` in
  `tests/unit/test_entry_types_inventory.py`:
  - Two category groups in order (VARIANT_TYPES, COMPLEX_FORM_TYPES) with correct counts
  - All user-defined rows preselected; GOLD rows shown but not user-modifiable
    (spec: shown as in_target because GOLD is a cross-reference device)
  - Empty category => empty `rows` list, no error; group still present
  - Target-status per row: source=target => `in_target`, fresh target => `new`,
    `target=None` => `None`
  - Hierarchy: a top-level entry type with one child => two rows, depths 0 and 1
    (or child is a nested tree-item -- see display test for rendering)
  - `variant_infl_feat_deps` populated: a FakeInflEntryType with infl_feats =>
    its guid maps to frozenset of value guids; base FakeEntryType => no entry
  - GUID normalization: raw mixed-case/braced `.Guid` on fake objects normalized
    correctly by `_guid_str_from` on both source and target sides

- [x] T007 [P] Unit tests for `collapse_entry_types` in
  `tests/unit/test_entry_types_inventory.py`:
  - All-checked => each category on, no `leaf_item_picks` key (transfer-all)
  - Trimmed category => `leaf_item_picks[cat]` = checked subset (frozenset of guids)
  - Whole-block off => no categories, no picks
  - Empty-block => nothing planned (no error)

- [x] T008 [P] Unit tests for entry-types missing-reference warnings in
  `tests/unit/test_entry_types_inventory.py`:
  - Kept ILexEntryInflType with infl-feat ref V, V absent from target =>
    1 entry-centric warning
  - Kept ILexEntryInflType with infl-feat ref V, V present in target =>
    0 warnings (reference resolves)
  - Kept base ILexEntryType (no InflFeatsOA) => 0 warnings
  - N kept inflection variant types with unresolvable refs => N warnings aggregated
  - guard: `if struct is None: return ()` -- no false dep on base ILexEntryType

- [x] T009 Implement `EntryTypesRow`, `EntryTypesCategoryGroup`, `EntryTypesInventory`
  dataclasses and `build_entry_types_inventory(source, target=None)` in
  `src/gramtrans/Lib/selection.py`. Uses `_walk_possibilities_via_lexdb` for both
  categories; `_is_gold_entry_type` from categories.py for GOLD detection; reuses
  `_phon_target_sets` pattern for target-status. Makes T006 pass.

- [x] T010 Implement `collapse_entry_types(inventory, checked_by_category)` in
  `src/gramtrans/Lib/selection.py`: emit `categories` on-flags and `leaf_item_picks`
  only for trimmed categories (fully-checked => key absent => transfer-all). Makes
  T007 pass.

- [x] T011 Implement `entry_types_missing_ref_warnings(inventory, checked_guids_by_cat,
  target)` in `src/gramtrans/Lib/selection.py`: for each kept `ILexEntryInflType`
  in `checked_guids_by_cat[VARIANT_TYPES]`, look up `variant_infl_feat_deps[guid]`,
  check each dep val_guid against the target's INFLECTION_FEATURES. Return a list of
  warning dicts (entry-centric, one per kept type with an unresolvable ref). Makes
  T008 pass.

### Wizard-order regression test update

- [x] T012 [P] Extend `tests/unit/test_wizard_page_order.py` to add
  `("page_entry_types", "_page_entry_types")` to `_ACCESSORS` and assert the accessor
  returns the expected type (`isinstance(w.page_entry_types(), _PageEntryTypes)`).
  The test also asserts 7 distinct pages. Extend the `test_no_literal_page_index_calls`
  regex guard to pass (it is already additive).

**Checkpoint**: engine honors per-item picks for both entry-type categories; builder is
green; page-order test extended.

---

## Phase 3: US1 -- Transfer the whole entry-types block (Priority: P1)

**Goal**: Lexical-entry types page at index 5, both categories preselected,
one-click transfer-all.

**Independent Test**: Bind Ejagham Mini; page 6 is Lexical-entry types; both categories
preselected with correct counts; advancing unchanged plans every user-defined entry type.

- [x] T013 [US1] Add `_PageEntryTypes` (grouped tree: 2 category groups, item rows
  with hierarchy, counts on headers, ALL user-defined rows preselected) in
  `src/gramtrans/Lib/ui/selection_wizard.py`. `initializePage` builds via
  `build_entry_types_inventory(source, target)`. Empty category renders (no error).
  Title: "Step 6 of 7: Lexical-Entry Types".

- [x] T014 [US1] Insert `_PageEntryTypes` at index 5 in `SelectionWizard.__init__`:
  - Add `self._page_entry_types = _PageEntryTypes()`
  - `self.addPage(self._page_entry_types)` after `self.addPage(self._page_gram_deps)`
  - `self.addPage(self._page_finish)` remains last
  - Add `page_entry_types(self)` named accessor returning `self._page_entry_types`
  - Update ALL step-title strings from "of 6" to "of 7" across all wizard pages
    (single reconciliation pass; see plan.md Shared-Hotspot Merge Notes §3)
  - Update `SelectionWizard.__doc__` comment block listing page order

- [x] T015 [US1] Merge entry-types picks into the Selection built in
  `_build_preview_selection` (`collapse_entry_types` -> `categories` +
  `leaf_item_picks`), applying Layer-1 default conflict modes; nothing writes (Move
  only).

- [x] T016 [P] [US1] Unit test in `tests/unit/test_entry_types_display.py`:
  - Page preselect-all state -> collapse yields both categories on with no
    `leaf_item_picks` keys (SC-001/SC-002)
  - Assert `_PageEntryTypes` renders NO ADD_NEW/MERGE/OVERWRITE conflict-mode
    control (SC-008 / FR-012)
  - Assert "of 7" title string (FR-001 / SC-007)

**Checkpoint**: whole block transfers end-to-end via Preview with zero interaction.

---

## Phase 4: US2 -- Toggle the block off, or trim individual types (Priority: P1)

**Goal**: whole-block toggle (ALL/NONE) + per-item deselect -> `leaf_item_picks`.

**Independent Test**: toggle off => zero entry-type items planned; deselect 1 variant
type => all but that one planned.

- [x] T017 [US2] Add the whole-block toggle + per-category tristate group toggles to
  `_PageEntryTypes` (whole-block reflects the aggregate; empty-block => toggle
  unchecked/disabled, not vacuously checked). Mirror `_PagePhonology._on_whole_block_clicked`.

- [x] T018 [US2] Wire per-item deselect -> `collect_entry_type_picks()` so trimmed
  categories produce `leaf_item_picks[cat]` subsets and fully-checked categories omit
  the key.

- [x] T019 [P] [US2] Unit tests in `tests/unit/test_entry_types_display.py`:
  - whole-block off => empty collapse (SC-003)
  - trim 1-of-N => subset pick
  - category all-checked => key omitted (transfer-all back-compat)
  - deselect parent type does not affect sibling category group toggle

**Checkpoint**: US1 + US2 both work; NONE and bare-bones trims are expressible.

---

## Phase 5: US3 -- GOLD-shipped types are cross-referenced by identity (Priority: P2)

**Goal**: GOLD types show as IN TARGET (matched by identity); a redefined GOLD type
shows as NEW (separate user-defined row).

**Independent Test**: bind a source mixing GOLD defaults + user-defined types; GOLD rows
show in_target; a source GOLD type with redefined meaning shows as NEW.

- [x] T020 [US3] Confirm `build_entry_types_inventory` uses `_is_gold_entry_type` to
  mark GOLD items as `in_target` (not shown as NEW); a type that was GOLD but has been
  redefined (different GUID from any target GOLD) is shown as NEW user-defined.
  `_is_gold_entry_type(node)` delegates to `_is_gold` per the TODO contract.

- [x] T021 [P] [US3] Unit tests in `tests/unit/test_entry_types_inventory.py`:
  - FakeEntryType with `catalog_source_id` set => shown as `in_target` (GOLD link)
  - FakeEntryType with `catalog_source_id=None` and GUID absent from target => `new`
  - FakeEntryType with `catalog_source_id=None` but GUID present in target => `in_target`
  - Both `catalog_source_id=None` AND `catalog_source_id=""` treated as non-GOLD

**Checkpoint**: GOLD cross-referencing correct; no GOLD duplication.

---

## Phase 6: US4 -- Know what already exists in the target (Priority: P2)

**Goal**: NEW / IN TARGET / SIMILAR per entry-type row; blank when no target.

**Independent Test**: source=target => every user-defined row IN TARGET; fresh target =>
NEW; no target => blank, no crash.

- [x] T022 [US4] Render the target-status column on `_PageEntryTypes` rows using the
  row `.status` from `build_entry_types_inventory` (reuse `_STATUS_LABELS`), blank
  when `None`.

- [x] T023 [P] [US4] Unit test in `tests/unit/test_entry_types_inventory.py`:
  - status computed by GUID (in_target) / name-match (similar) / else new
  - `target=None` => blank (status=None) -- no crash (SC-005 / FR-007)

**Checkpoint**: collision status visible on every entry-type row.

---

## Phase 7: US5 -- Inflection-feature dependencies are automatically carried (Priority: P2)

**Goal**: a kept `ILexEntryInflType` whose referenced infl-feat value is target-absent
raises an aggregated warning into the single shared Move gate.

**Independent Test**: keep an `ILexEntryInflType` referencing value V that is absent
from target; Preview warns; Move pops ONE consolidated dialog (not a per-type prompt).

- [x] T024 [US5] Expose `_PageEntryTypes.missing_ref_warnings(target)` and feed
  entry-types missing-reference warnings into the aggregated `el_count` in
  `_PageFinish._on_move` (selection_wizard.py:2840) -- same single dialog as
  skeleton/deps/phonology (FR-011). Wire via an `_entry_types_missing_ref_for(wizard)`
  helper mirroring `_phonology_excluded_lossy_for`.

- [x] T025 [P] [US5] Unit test in `tests/unit/test_entry_types_display.py`:
  - N entry-types missing-ref warnings + M phonology warnings => ONE combined Move
    confirmation covering all; resolved references => no warning (SC-006)
  - base ILexEntryType (no InflFeatsOA) => 0 warnings

**Checkpoint**: all P1 stories (US1, US2, US5) complete -> MVP.

---

## Phase 8: Polish & Cross-Cutting

- [x] T026 Full regression sweep: confirm all existing unit tests remain green
  (`leaf_item_picks` absent-key back-compat for VARIANT_TYPES/COMPLEX_FORM_TYPES).
  Run `pytest tests/unit/ -x -q` before and after changes to confirm no regression.

- [ ] T027 [P] Live MCP integration (optional, post-unit-tests): Ejagham Mini ->
  Ejagham Full GT-Test -- whole-block, block-off, per-item trim, infl-feat dep
  carried, idempotency re-run. (Written; main session executes.)

- [x] T028 Update STATUS.md handoff; note merge-reconciliation items (see plan.md
  Shared-Hotspot Merge Notes); commit topic-aligned increments.

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** -> no deps.
- **Phase 2 (Foundational)** -> blocks all US phases. Within it: engine (T002-T005),
  builder (T006-T011), and wizard-order test (T012) are three independent [P] streams;
  T006->T009, T007->T010, T008->T011.
- **US1 (Phase 3)** depends on Foundational (needs the builder + page-order test).
- **US2 (Phase 4)** depends on Foundational + US1.
- **US3/US4 (Phases 5, 6)** depend on Foundational + US1; independent of US2/each other.
- **US5 (Phase 7)** depends on Foundational (missing-ref derivation) + US1; independent
  of US2/US3/US4.
- **Polish** depends on all desired US phases.

### MVP scope (P1 stories)

**US1 + US2 + US5** = the Model-B MVP (whole-block transfer, trim/off, referential-
completeness gate). US3 (GOLD cross-ref) and US4 (target-status) are P2 increments.

### Parallel opportunities

- Foundational: T002 / T006+T007+T008 / T012 run as parallel streams.
- All `[P]` unit tests within a story run together.
- After Foundational: US3 and US4 can be built in parallel.

---

## Notes

- `[P]` = different files, no incomplete-task deps. `[USn]` = story traceability.
- The absent-key `leaf_item_picks` guard is the back-compat contract -- verify T026
  before ship.
- Verify each unit test FAILS before implementing (TDD).
- Commit after each task or logical group.
- **Merge reconciliation with 018/019** (see plan.md Shared-Hotspot Merge Notes):
  - `selection_wizard.py` page-insertion order (additive, append before _page_finish)
  - Named accessors block (additive)
  - "of N" step-count labels (single reconcile at integration)
  - `_build_preview_selection` entry-types step (additive dict-merge)
  - `_PageFinish._on_move` el_count (additive `+=` line)

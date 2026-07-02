# Tasks: Phonology Selector (Model-B Independent Block)

**Feature dir**: `specs/010-phonology-selector/` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

TDD-ordered. Reuse from 008/009: `_cast` / `_guid_str_from`, target-status logic
(`_build_target_sets` / `_entry_status`), `build_excluded_lossy_warnings` shape, POS/collection
enumeration, and the fake-handle pattern in `tests/unit/_fakes_*.py` (extend, don't fork).

**Engine reality (research.md R1)**: the spec-005 leaf-dispatch transfers whole categories.
Per-item trim (US2/FR-005) requires the contained engine touch in Phase 2 (Foundational).
**Absent `leaf_item_picks` key ⇒ transfer all** — the guard that keeps all 324+ existing tests
and FR-307 idempotency intact.

**Out of scope**: variant/complex types, ad-hoc/compound rules, custom fields, stems, semantic
domains; conflict-mode UI; KL-010-1 (metathesis/reduplication reference traversal — see Polish).

---

## Phase 1: Setup

- [X] T001 Add `tests/unit/_fakes_phonology.py` with duck-typed fakes (no pythonnet): source
  handle exposing `PhFeatureSystem`/`Phonemes`/`NaturalClasses`/`Environments`/`PhonRules`
  accessors with `.GetAll()`; fake phoneme (`.Guid`, `.FeaturesOA` → feature refs), fake NC
  (`.Guid`, `.SegmentsRC` → phoneme refs), fake rule (`.Guid`, `.StrucDescOS` +
  `rhs.LeftContextOA`/`RightContextOA` with `IPhSimpleContextNC`/`IPhSimpleContextSeg`
  → `.FeatureStructureRA.Guid`, `.StratumRA`), fake feature, fake environment; matching target
  handle for status. GUIDs mixed-case + braces to exercise `_guid_str_from` normalization.

---

## Phase 2: Foundational (blocks all user stories)

**⚠️ CRITICAL**: engine touch + refactor prerequisites + pure builder. No page work until done.

### Engine touch — `leaf_item_picks` (research.md R1; data-model.md)

- [X] T002 [P] Unit tests for the `leaf_item_picks` enumerate filter in
  `tests/unit/test_leaf_item_picks.py`: key absent ⇒ all items (back-compat); key present ⇒
  only those GUIDs; empty frozenset ⇒ none; GUID match works with mixed-case/braced source
  GUIDs vs normalized picks (both sides via `_guid_str_from`); a `leaf_item_picks` key for a
  category with `is_on(cat) is False` is inert (A-1).
- [X] T003 Add `Selection.leaf_item_picks: dict = field(default_factory=dict)` to
  `src/gramtrans/Lib/models.py` with a `__post_init__` comment documenting the deliberate
  no-coupling exemption (unlike `affix_picks`/`template_picks`/`pos_picks`); default `{}`
  preserves every existing caller.
- [X] T004 Extend `_phonology_simple_enumerate` (and the strata enumerate) in
  `src/gramtrans/Lib/categories.py` to filter `GetAll()` by
  `selection.leaf_item_picks.get(cat)` when not `None`, comparing `_guid_str_from(it)` (NOT raw
  `str(it.Guid)`). Makes T002 pass. Confirm `is_on` still gates before enumerate in
  `src/gramtrans/Lib/preview.py` leaf-dispatch.

### Wizard-index refactor prerequisite (plan.md P-1/P-2; QC Q3)

- [X] T005 Add named page accessors to `SelectionWizard` in
  `src/gramtrans/Lib/ui/selection_wizard.py` (`page_project_ws`/`page_phonology`/`page_items`/
  `page_skeleton`/`page_gram_deps`/`page_preview`/`page_finish`) returning the stored
  `self._page_*` attributes; replace ALL literal `wizard.page(N)`/`w.page(N)` calls
  (current sites: 1363, 1575, 1689, 1711, 1780, 1787, 1798) with the accessors. No behavior
  change yet (page still absent). Invariant: no page references another by literal index.
- [X] T006 [P] Wizard-order regression test in `tests/unit/test_wizard_page_order.py`:
  assert each named accessor returns the expected page TYPE in post-insertion order
  (`isinstance(w.page_items(), _PageItemPicker)`, … for all 7 pages incl. Phonology at index 1).

### Pure builder + collapse + EXCLUDED-LOSSY derivation (data-model.md)

- [X] T007 [P] Unit tests for `build_phonology_inventory` in
  `tests/unit/test_phonology_inventory.py`: 5 category groups in order (features, phonemes,
  NCs, environments, rules) with correct counts; all rows preselected; empty category ⇒ empty
  `rows` (no error); target-status per row (source=target ⇒ `in_target`, fresh ⇒ `new`,
  `target=None` ⇒ `None`); reference maps populated per-rule / per-NC / per-phoneme.
- [X] T008 [P] Unit tests for `collapse_phonology` in `tests/unit/test_phonology_inventory.py`:
  all-checked ⇒ each category on, no `leaf_item_picks` key (transfer-all); trimmed category ⇒
  `leaf_item_picks[cat]` = checked subset; whole-block off ⇒ no categories, no picks, no strata;
  empty-block ⇒ nothing planned.
- [X] T009 [P] Unit tests for phonology EXCLUDED-LOSSY in
  `tests/unit/test_phonology_excluded_lossy.py`: kept rule + deselected+absent NC ⇒ 1
  entry-centric warning naming the rule; kept rule + deselected+absent direct phoneme ⇒ 1
  warning; kept NC + deselected+absent phoneme ⇒ 1 warning; kept phoneme + deselected+absent
  feature ⇒ 1 warning; reference resolves in target ⇒ NO warning; N omissions ⇒ N warnings but
  ONE consolidated gate payload (per-rule attribution via dict maps).
- [X] T010 Implement `build_phonology_inventory(source, target=None)` + `PhonologyRow` /
  `PhonologyCategoryGroup` / `PhonologyInventory` dataclasses (reference maps as
  `dict[guid → frozenset[guid]]`, keys via `_guid_str_from`) in
  `src/gramtrans/Lib/selection.py`. Reuse 008/009 status logic; RHS path is
  `rhs.LeftContextOA`/`RightContextOA` (NOT the bug-#142 `StrucDescOS[0]` path). Makes T007 pass.
- [X] T011 Implement `collapse_phonology(inventory, checked_by_category)` in
  `src/gramtrans/Lib/selection.py`: emit `categories` on-flags, rule-gated `{STRATA: True}`
  (FR-009), and `leaf_item_picks` only for trimmed categories. Makes T008 pass.
- [X] T012 Implement the phonology missing-reference derivation feeding the shared Move-gate
  channel in `src/gramtrans/Lib/preview.py` / `selection.py` (per-rule/NC/phoneme dict maps,
  entry-centric). Makes T009 pass.

**Checkpoint**: engine honors per-item picks; wizard is index-safe; builders are green.

---

## Phase 3: US1 — Transfer the whole phonology block (Priority: P1) 🎯 MVP

**Goal**: Phonology page at index 1, all five categories preselected, one-click transfer-all.

**Independent Test**: Bind Ejagham Mini; page 2 is Phonology; all categories preselected with
correct counts; advancing unchanged plans every phonology item.

- [X] T013 [US1] Add `_PagePhonology` (grouped tree: 5 category groups, item rows, counts on
  headers, ALL preselected) in `src/gramtrans/Lib/ui/selection_wizard.py`; `initializePage`
  builds via `build_phonology_inventory(source, target)`; empty category renders (no error).
- [X] T014 [US1] Insert `_PagePhonology` at index 1 in `SelectionWizard` (order: Project+WS,
  Phonology, Affixes, Skeleton, GramDeps, Preview, Finish); update step titles ("Step N of 7").
  Relies on T005 accessors so downstream pages resolve correctly.
- [X] T015 [US1] Merge phonology picks into the Selection built in `_PagePreview._on_preview`
  (`collapse_phonology` → `categories` + `leaf_item_picks`), applying Layer-1 default conflict
  modes; nothing writes (Move only).
- [X] T016 [P] [US1] Unit test in `tests/unit/test_phonology_inventory.py`: page preselect-all
  state → collapse yields all 5 categories on with no `leaf_item_picks` keys (SC-001/SC-002);
  **and assert `_PagePhonology` renders NO ADD_NEW/MERGE/OVERWRITE conflict-mode control
  (SC-008 / FR-012)** — closes analyze finding G1.

**Checkpoint**: whole block transfers end-to-end via Preview with zero interaction.

---

## Phase 4: US2 — Toggle the block off, or trim individual items (Priority: P1)

**Goal**: whole-block toggle (ALL/NONE) + per-item deselect → `leaf_item_picks`.

**Independent Test**: toggle off ⇒ zero phonology items planned; deselect 3 phonemes ⇒ all
but those 3 planned.

- [ ] T017 [US2] Add the whole-block toggle + per-category tristate group toggles to
  `_PagePhonology` in `src/gramtrans/Lib/ui/selection_wizard.py` (whole-block reflects the
  aggregate; empty-block ⇒ toggle unchecked/disabled, not vacuously checked).
- [ ] T018 [US2] Wire per-item deselect → `collect_phonology_picks()` so trimmed categories
  produce `leaf_item_picks[cat]` subsets and fully-checked categories omit the key.
- [ ] T019 [P] [US2] Unit tests in `tests/unit/test_leaf_item_picks.py`: whole-block off ⇒
  empty collapse; trim 3-of-N ⇒ subset pick; category all-checked ⇒ key omitted (SC-003).

**Checkpoint**: US1 + US2 both work; NONE and bare-bones trims are expressible.

---

## Phase 5: US3 — Strata travel automatically and invisibly (Priority: P2)

**Goal**: strata included iff ≥1 phonological rule kept; never a user-facing row.

**Independent Test**: keep ≥1 rule ⇒ plan includes strata; deselect all rules ⇒ no strata; no
strata row ever shown.

- [ ] T020 [US3] Confirm/finish strata gating in `collapse_phonology`
  (`src/gramtrans/Lib/selection.py`): `{STRATA: True}` iff `PHONOLOGICAL_RULES` on with ≥1
  checked rule; ensure no strata group is ever added to `_PagePhonology`.
- [ ] T021 [P] [US3] Unit tests in `tests/unit/test_strata_gating.py`: rules kept ⇒ strata on;
  rules off but phonemes/NCs on ⇒ no strata; whole-block off ⇒ no strata; no strata row in the
  page tree (SC-003/SC-004, FR-009).

**Checkpoint**: strata dependency correct and invisible.

---

## Phase 6: US4 — Know what already exists in the target (Priority: P2)

**Goal**: NEW / IN TARGET / SIMILAR per phonology row; blank when no target.

**Independent Test**: source=target ⇒ every row IN TARGET; fresh target ⇒ NEW; no target ⇒
blank, no crash.

- [ ] T022 [US4] Render the target-status column on `_PagePhonology` rows using the row
  `.status` from `build_phonology_inventory` (reuse `_STATUS_LABELS`), blank when `None`.
- [ ] T023 [P] [US4] Unit test in `tests/unit/test_phonology_inventory.py`: status computed by
  GUID (in_target) / fingerprint (similar) / else new; `target=None` ⇒ blank (SC-005, FR-007).

**Checkpoint**: collision status visible on every phonology row.

---

## Phase 7: US5 — Trimming a needed item is reported, not silent (Priority: P1)

**Goal**: deselecting a needed, target-absent phonology item raises an aggregated warning into
the single shared Move gate.

**Independent Test**: keep a rule referencing NC C; deselect C against a target lacking C ⇒
Preview warns naming the rule; Move pops ONE consolidated dialog.

- [ ] T024 [US5] Expose `_PagePhonology.deselected_needed_guids()` and feed phonology
  missing-reference warnings into the aggregated `el_count` in `_PageFinish._on_move`
  (`src/gramtrans/Lib/ui/selection_wizard.py`) — same single dialog as skeleton/deps (FR-011).
- [ ] T025 [US5] Surface the phonology missing-reference entries in the Preview StatsPanel
  channel (entry-centric, per kept item) alongside the 009 warnings.
- [ ] T026 [P] [US5] Unit test in `tests/unit/test_phonology_excluded_lossy.py`: N phonology
  omissions + M skeleton/deps omissions ⇒ ONE combined Move confirmation covering all; resolved
  references ⇒ no warning (SC-006).
- [ ] T026b [US5] **Principle-V guard for KL-010-1** (analyze finding C1): in
  `build_phonology_inventory` / `collapse_phonology` (`src/gramtrans/Lib/selection.py`),
  detect when any selected rule is a `PhMetathesisRule` / `PhReduplicationRule` (whose
  part-sequence references are NOT traversed) and, if the user trims NCs/phonemes, surface a
  coarse "reference check not supported for this rule type — trim may strand references" notice
  into the same aggregated Move gate rather than transferring silently. Keeps Referential
  Completeness honest until the T029 traversal follow-up lands.
- [ ] T026c [P] [US5] Unit test in `tests/unit/test_phonology_excluded_lossy.py`: a selected
  `PhMetathesisRule`/`PhReduplicationRule` + a phonology trim ⇒ the coarse KL-010-1 notice
  appears in the Move gate (guard fires); PhRegularRule-only ⇒ no such notice.

**Checkpoint**: all P1 stories (US1, US2, US5) complete → MVP.

---

## Phase 8: Polish & Cross-Cutting

- [ ] T027 [P] Live MCP integration in `tests/integration/test_phonology_live.py`: Ejagham Mini
  → Ejagham Full GT-Test — Scenarios A–E from quickstart.md (whole-block, block-off, per-item
  trim, rule-gated strata, FR-307 idempotency re-run). (Written; main session executes.)
- [ ] T028 Full regression sweep: confirm the 324+ existing unit tests remain green
  (leaf_item_picks absent-key back-compat) and the 009 wizard pages still resolve via accessors.
- [ ] T029 [P] KL-010-1 follow-up entry: record the metathesis/reduplication reference-traversal
  gap (extend traversal to `Left/RightPartOfMetathesisOS` + `Left/RightPartOfReduplicationOS`,
  add fixtures) as a post-010 backlog item in STATUS.md.
- [ ] T030 Update STATUS.md handoff + point the CLAUDE.md SPECKIT marker note; commit
  topic-aligned increments.

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** → no deps.
- **Phase 2 (Foundational)** → blocks all US phases. Within it: engine (T002-T004),
  refactor (T005-T006), and builders (T007-T012) are three independent [P] streams; T003→T004,
  T007→T010, T008→T011, T009→T012.
- **US1 (P3 phase)** depends on Foundational (needs the builder + accessors).
- **US2** depends on Foundational (needs `leaf_item_picks`) + US1 (the page exists).
- **US3/US4** depend on Foundational + US1; independent of US2/each other.
- **US5** depends on Foundational (EXCLUDED-LOSSY derivation) + US1; independent of US2/US3/US4.
- **Polish** depends on all desired US phases.

### MVP scope (P1 stories)

**US1 + US2 + US5** = the Model-B MVP (whole-block transfer, trim/off, and the referential-
completeness gate). US3 (strata) and US4 (target-status) are P2 increments.

### Parallel opportunities

- Foundational: T002 / T005+T006 / T007+T008+T009 run as parallel streams.
- All `[P]` unit tests within a story run together.
- After Foundational: US3 and US4 can be built in parallel by different developers.

---

## Notes

- `[P]` = different files, no incomplete-task deps. `[USn]` = story traceability.
- The absent-key `leaf_item_picks` guard is the back-compat contract — verify T028 before ship.
- Verify each unit test FAILS before implementing (TDD).
- Commit after each task or logical group.

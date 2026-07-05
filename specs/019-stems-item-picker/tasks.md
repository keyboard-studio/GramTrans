---
description: "Task list for Stems Item Picker (Model-A) — Un-stub the Disabled Pane"
---

# Tasks: Stems Item Picker (Model-A) — Un-stub the Disabled Pane

**Input**: Design documents from `specs/019-stems-item-picker/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/stems-item-picker.md, quickstart.md

**Tests**: INCLUDED. The quickstart names unit-test modules and plan Phase B mandates TDD
(null-guard inversion is the highest-risk correctness point). Test tasks are written FIRST and
MUST FAIL before their implementation task.

**Organization**: Grouped by user story. Priority order: US1 (P1, MVP) → US2 (P1) → US4 (P1) →
US3 (P2). Each maps to one of the four `selection.py` builders plus its UI wiring.

**Worktree root**: `D:/Github/_Projects/_LEX/GramTrans-019-stems-item-picker`. All paths below
are relative to that root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 / US2 / US3 / US4 (setup/foundational/polish carry no story label)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the worktree can build and test before touching engine code.

- [ ] T001 Confirm baseline: `pyflexicon>=4.1` installed and the existing suite is green — run `pytest tests/unit -q` from the worktree root and record the pass count (byte-stable-affix-behavior baseline for regression checks in Phase 7).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The `stem_picks` selection field and the shared partition helper that all four
builders and the UI depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T002 [P] Write failing invariant test: non-empty `stem_picks` requires `categories[GrammarCategory.STEMS]` on (mirror the affix invariant) in tests/unit/test_selection_invariants.py
- [ ] T003 Add `stem_picks: frozenset[str]` field (sibling to `affix_picks`) and the STEMS-category invariant to the `Selection` dataclass in src/gramtrans/Lib/models.py — make T002 pass
- [ ] T004 [P] Create failing partition tests in tests/unit/test_stem_partition.py: `IsAffixType == True` → AFFIX; `IsAffixType == False`, null `LexemeFormOA`, null `MorphTypeRA`, and uncastable morphtype → STEM (include-on-exception); partition is complete + disjoint over `LexDbOA.Entries`. Note: clitics (proclitic/enclitic) have `IsAffixType == False` and therefore correctly land in the STEM bucket — this is expected behavior, not a failure. Test comments should document this explicitly.
- [ ] T005 Implement the shared `_partition_entries(entries) -> Tuple[List, List]` helper returning `(affix_entries, stem_entries)` (include-on-exception for the stem side: null/uncastable morphtype goes to `stem_entries` per FR-002; the affix `except (AttributeError, TypeError): continue` skip at selection.py:600 is NOT copied — the inversion is deliberate). Each call site replaces its filter block with a call to `_partition_entries` and iterates the appropriate list (`affix_entries` or `stem_entries`). In src/gramtrans/Lib/selection.py — make T004 pass

**Checkpoint**: `stem_picks` exists and validates; the partition helper is proven against all null-guard cases.

---

## Phase 3: User Story 1 - Pick stem entries from an enabled Stems tab (Priority: P1) 🎯 MVP

**Goal**: The Stems tab is enabled and lists the source's stem-morphtype entries; the user can toggle each one, exactly like the Affixes tab.

**Independent Test**: Bind a source with both affix and stem entries; open the Item picker; confirm the Stems tab is enabled (no "[STUBBED]" placeholder), lists exactly the stem-morphtype entries (no overlap with Affixes), and toggling records the pick.

### Tests for User Story 1 ⚠️ (write first, ensure they FAIL)

- [ ] T006 [P] [US1] Create tests/unit/test_build_stem_inventory.py: `build_pos_grouped_inventory(..., want_affix=False)` returns the stem inventory grouped by `MoStemMsa.PartOfSpeechRA`; entries are disjoint from the affix inventory (SC-001); a zero-stem source yields an empty inventory, not an error (FR-007/SC-006)
- [ ] T007 [P] [US1] Extend tests/unit/test_selection_ui.py: the Stems tab is enabled (no stub placeholder), is populated from the stem inventory, and checking/unchecking a stem row toggles its GUID in `stem_picks`

### Implementation for User Story 1

- [ ] T008 [US1] Parameterize `build_pos_grouped_inventory(..., want_affix: bool = True)` (~selection.py:600) to route through `_partition_entries`; the affix call site keeps the default so existing behavior is byte-stable — make T006 pass — in src/gramtrans/Lib/selection.py
- [ ] T009 [US1] Un-stub `_PageItemPicker`: remove the "[STUBBED]" placeholder at selection_wizard.py:625-689, enable the Stems tab, and populate it from `build_pos_grouped_inventory(..., want_affix=False)` in src/gramtrans/Lib/ui/selection_wizard.py
- [ ] T010 [US1] Wire stem-row check state → `stem_picks` and emit `stem_picks` from `collect_selection()` (mirror the affix path at ~:1189-1206) — make T007 pass — in src/gramtrans/Lib/ui/selection_wizard.py

**Checkpoint**: The Stems tab is live and picks are recorded — MVP is independently testable.

---

## Phase 4: User Story 2 - Picked stems drive grammatical-dependency closure (Priority: P1)

**Goal**: Picked stems compute and preselect their POS / inflection classes / stem names / inflection features / exception features on the Skeleton and Grammatical-deps pages, and their owned-child closure travels with them.

**Independent Test**: Pick a stem whose sense MSA references POS P (not otherwise selected); confirm P is preselected on Skeleton and appears in the plan; deselect the stem and confirm P is dropped on the stem's account.

### Tests for User Story 2 ⚠️ (write first, ensure they FAIL)

- [ ] T011 [US2] Add MSA-dispatch tests to tests/unit/test_build_stem_inventory.py: a `MoStemMsa` arm reads `PartOfSpeechRA` + `MsFeaturesOA`; a stem MSA is NEVER cast to `IMoInflAffMsa`, `SlotsRC` is never read, and a non-`MoStemMsa` MSA on a stem entry is skipped, not recast (FR-013). ADD assertion: the `MoStemMsa` arm also reads `InflectionClassRA` (cast to `IMoStemMsa`, None-guarded); when `InflectionClassRA` is null (Ejagham 0/2444 case) the read is a no-op with no exception raised.
- [ ] T011a [US2] Synthetic-fixture unit test for the populated `InflectionClassRA` branch (the branch live Ejagham cannot exercise): construct a stub stem MSA where `IMoStemMsa.InflectionClassRA` is non-null and the referenced inflection class is ABSENT from the target; assert the reference surfaces as an FR-009 missing-reference warning via `build_excluded_lossy_warnings()` and increments `plan.excluded_lossy_count`. Fixture lives in tests/unit/test_build_stem_inventory.py (same module as T011-T013; do NOT mark [P]).
- [ ] T012 [US2] Add closure tests: stem walk pulls `POS.InflectionClassesOC`, `IPartOfSpeech.StemNamesOC`, `POS.InflectableFeatsRC`, `MoStemMsa.MsFeaturesOA` (FR-004); owned-child closure (`SensesOS`, `MorphoSyntaxAnalysesOC`, `AlternateFormsOS`, `ExamplesOS`, `LexemeFormOA`) travels with the stem (FR-005); a POS needed by both a picked affix and a picked stem is pulled once, deduplicated by GUID — in tests/unit/test_build_stem_inventory.py. P2 flag: verify `EntryRefsOS` coverage in the shared owned-child closure — note tension with research Decision 4 (which scopes entry-refs out as categories.py-only). Do NOT silently change scope; flag for human decision.
- [ ] T013 [US2] Add downstream-drop test: deselecting a stem removes dependencies pulled solely on its account (unless another kept item needs them) in tests/unit/test_build_stem_inventory.py

### Implementation for User Story 2

- [ ] T014 [US2] Add the `MoStemMsa` arm to the MSA dispatch (~selection.py:706-810): `class_name == "MoStemMsa"` → read `PartOfSpeechRA` + `MsFeaturesOA`; skip (do not recast) any non-`MoStemMsa` arm on a stem-partitioned entry — make T011 pass — in src/gramtrans/Lib/selection.py. Note: `MoStemMsa.MsFeaturesOA` returns a SINGLE `IFsFeatStruc` (not a collection); use the cast chain `_cast(msa, "IMoStemMsa").MsFeaturesOA` and perform a nullable/None check before reading the feature GUID. The MSA dispatch `elif` chain ends in `else: pass` (~:817), so unrecognized classes already fall through — no redundant skip guard needed.
- [ ] T015 [US2] Keep `build_skeleton_inventory` (~selection.py:1151) AFFIX-ONLY — do NOT add a `want_stem` parameter. Per FR-013, stems must never enter the affix slot/template skeleton builder. Remove any `want_stem` parameter or stem-walk prose that was previously implied for this function. In src/gramtrans/Lib/selection.py
- [ ] T016 [US2] Parameterize `build_deps_inventory(stem_picks, ...)` (~selection.py:1502) to accept `stem_picks` and walk the POS-dependency collections for each picked stem: `PartOfSpeechRA → POS.{InflectionClassesOC, StemNamesOC, InflectableFeatsRC}` + `MoStemMsa.MsFeaturesOA` (no `SlotsRC`) + `MoStemMsa.InflectionClassRA` (cast to `IMoStemMsa`, None-guarded; if non-null, feed the FR-009 missing-reference aggregation via `build_excluded_lossy_warnings()` — additive to `POS.InflectionClassesOC`, not a replacement). Include shared-dependency GUID dedup across affix and stem picks — make T012 and T013 pass — in src/gramtrans/Lib/selection.py
- [ ] T017 [US2] Add `_get_stem_picks()` on pages 3–5 (mirror `_get_affix_picks()` at ~:1410, :1897) and thread `stem_picks` into `build_skeleton_inventory` / `build_deps_inventory` in src/gramtrans/Lib/ui/selection_wizard.py
- [ ] T018a [US2] Write a FAILING unit test that `stem_picks` flows into `compute_plan` and produces the expected owned-child plan entries (closes FR-005/SC-002 TDD gap). In tests/unit/test_selection_ui.py — MUST FAIL before T018 is implemented.
- [ ] T018 [US2] Verify picked stems flow through `compute_plan` (owned-child + grammatical closure) via the shared engine in src/gramtrans/Lib/preview.py and src/gramtrans/Lib/transfer.py (no new plan path; confirm the pick set is consumed) — make T018a pass

**Checkpoint**: Picking a stem produces correct Model-A closure end-to-end in the plan.

---

## Phase 5: User Story 4 - Deselecting a needed dependency is reported, not silent (Priority: P1)

**Goal**: A kept stem whose needed grammatical dependency is deselected and absent from the target produces exactly one aggregated warning, folded into the single shared Move confirmation.

**Independent Test**: Keep a stem whose POS is deselected on Skeleton against a target lacking that POS; confirm Preview shows one aggregated warning naming the stem and Move requires a single consolidated confirmation (with other omissions folded into the same dialog).

### Tests for User Story 4 ⚠️ (write first, ensure they FAIL)

- [ ] T019 [P] [US4] Add missing-reference tests to tests/unit/test_build_stem_inventory.py: a kept stem with a deselected, target-absent dependency emits exactly one `(kept-stem, stranded-dependency)` warning per stem via `build_excluded_lossy_warnings()`; several such omissions still aggregate to a single `plan.excluded_lossy_count()` confirmation (FR-009/FR-010), never one prompt per stranded dependency

### Implementation for User Story 4

- [ ] T020 [US4] Route stem missing-reference warnings into `build_excluded_lossy_warnings()` (~selection.py:1705) so they feed the existing `plan.excluded_lossy_count()` aggregation at selection_wizard.py:3171 — no new dialog (FR-010) — make T019 pass — in src/gramtrans/Lib/selection.py. Note: FR-011 GOLD-skip is covered by the shared engine only (no dedicated unit test); this is acceptable because byte-stable behavior is inherited from the affix path.

**Checkpoint**: Stranded stem dependencies surface in the single shared Move gate — Referential Completeness (Constitution V) holds.

---

## Phase 6: User Story 3 - Know what already exists in the target (Priority: P2)

**Goal**: Every stem row shows NEW / IN TARGET / SIMILAR against the bound target using the affix picker's logic; blank when no target is bound.

**Independent Test**: Bind source=target and confirm every stem row reads IN TARGET; bind a fresh target and confirm rows read NEW; unbind the target and confirm the status column is blank with no crash.

### Tests for User Story 3 ⚠️ (write first, ensure they FAIL)

- [ ] T021 [P] [US3] Add target-status tests to tests/unit/test_build_stem_inventory.py: `_build_target_sets(..., want_affix=False)` yields stem target sets; source=target → all IN TARGET; fresh target → NEW; no target bound → blank/safe-default (treat target as lacking the reference), no crash (FR-006/SC-004)

### Implementation for User Story 3

- [ ] T022 [US3] Parameterize `_build_target_sets(..., want_affix: bool = True)` (~selection.py:339) for the stem partition in a single enumeration pass (both tabs obtain target-status from this one function; no duplicate enumeration) — make T021 pass — in src/gramtrans/Lib/selection.py
- [ ] T023 [US3] Render the NEW / IN TARGET / SIMILAR column per stem row (blank when no target bound), reusing the affix fingerprint unless a stem-specific fingerprint proves necessary (see plan Open Question) in src/gramtrans/Lib/ui/selection_wizard.py

**Checkpoint**: Every stem row carries a target-presence status; all four user stories are independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns / Live Verification

**Purpose**: Confirm no conflict-mode UI, run the quickstart, and attach the constitution verification artifacts.

- [ ] T024 [P] Assert the pane presents no ADD_NEW / MERGE / OVERWRITE control and the Layer-1 per-category default applies without user input (FR-012/SC-007) — add to tests/unit/test_selection_ui.py. Also add a unit assertion that `collect_selection()` invokes no write-side method and returns no write actions (FR-008).
- [ ] T025 Run the full quickstart unit set from quickstart.md (`pytest tests/unit/test_stem_partition.py tests/unit/test_build_stem_inventory.py tests/unit/test_selection_invariants.py tests/unit/test_selection_ui.py -q`) and confirm all pass; re-run the Phase 1 baseline suite to confirm affix behavior is byte-stable (no regression)
- [ ] T026 Live source→target verification per specs/019-stems-item-picker/quickstart.md scenarios 1–6: SC-001 disjoint/complete partition (incl. null-morphtype entry lands in Stems), SC-002/003 closure in plan + deselect-drop, SC-004 target status, SC-005 single aggregated Move warning, SC-006 zero-stem empty tab, SC-007 no conflict-mode control
- [ ] T027 Run dry-run then Move on a mixed stem+affix selection against a fresh target; attach pre/post Import Residue artifacts; confirm create-vs-skip by GUID, GOLD-skip (FR-011), shared POS pulled once (dedup), owned-child closure travels with each stem (constitution verification gate)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup. BLOCKS all user stories (`stem_picks` field + `_partition_entries` helper).
- **US1 (Phase 3)**: Depends on Foundational. MVP.
- **US2 (Phase 4)**: Depends on Foundational; uses the US1 inventory/pick path in practice (pick set must exist to compute closure).
- **US4 (Phase 5)**: Depends on US2 (a dependency must be deselectable to be stranded).
- **US3 (Phase 6)**: Depends on Foundational + US1 (rows must exist); independent of US2/US4.
- **Polish (Phase 7)**: Depends on all desired stories.

### Within Each User Story

- Test tasks (⚠️) are written first and MUST FAIL before their implementation task.
- Engine (`selection.py`) before UI (`selection_wizard.py`) within a story.

### Parallel Opportunities

- T002 ∥ T004 (Foundational tests, different files).
- T006 ∥ T007 (US1 tests, different files).
- T011, T012, T013 (US2 tests) all write to tests/unit/test_build_stem_inventory.py — run SEQUENTIALLY to avoid file-conflict hazard; remove the [P] parallel marker for these tasks.
- Engine builders (T008, T014/T015/T016, T020, T022) all edit `selection.py` — serialize edits to that file even across stories.
- US3 (Phase 6) can proceed in parallel with US4 (Phase 5) once US1 lands, IF `selection.py` edits are serialized.

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational (CRITICAL) → 3. Phase 3 US1 → **STOP and validate**: the Stems tab lists stems and records picks. Demo.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 → Stems tab live (MVP).
3. US2 → picks drive closure into the plan.
4. US4 → stranded dependencies surface in the Move gate.
5. US3 → target-status column.
6. Polish → live verification + constitution artifacts.

---

## Notes

- **Highest-risk task**: T005 — the null-guard inversion (include-on-exception). Signature is `_partition_entries(entries) -> Tuple[List, List]` returning `(affix_entries, stem_entries)`. Do NOT copy the affix `except (...): continue` skip pattern; a null/uncastable morphtype MUST land in `stem_entries` (FR-002). T004 covers exactly these cases.
- **Never** cast a stem MSA to `IMoInflAffMsa` or read `SlotsRC` (FR-013); `MoStemMsa` exposes neither `SlotsRC` nor the affix slot/template builder.
- `MoStemMsa.InflectionClassRA` (cast via `IMoStemMsa`) IS read, but only with a None-guard; a null result is a no-op (Ejagham 0/2444 case). A non-null result feeds the FR-009 missing-reference aggregation. This is READ-IF-PRESENT and additive to `POS.InflectionClassesOC` — do not confuse with the forbidden `SlotsRC` read.
- `build_skeleton_inventory` (~:1151) is AFFIX-ONLY (FR-013 — stems must never enter the affix slot/template skeleton builder). The stem grammatical-dependency closure (`PartOfSpeechRA -> POS.{InflectionClassesOC, StemNamesOC, InflectableFeatsRC}` + `MoStemMsa.MsFeaturesOA` + `MoStemMsa.InflectionClassRA` None-guarded) lives in T016 / `build_deps_inventory` (~:1502) which accepts `stem_picks`.
- All engine builders parameterize existing functions (`want_affix` default preserves affix byte-stability) rather than duplicating a parallel `build_stem_*` family (plan Key Design Decision 1).
- Nothing on the pane writes to the target; the only write is at Move (Constitution III / FR-008).
- Commit after each task or logical group; serialize `selection.py` edits.

---

description: "Task list for Phase 0 — Additive Grammar Transfer (reconciled with constitution v5.0.0 on 2026-06-19)"
---

# Tasks: Phase 0 — Additive Grammar Transfer

**Input**: Design documents from [specs/001-phase0-additive-transfer/](.)

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md), [constitution v5.0.0](../../.specify/memory/constitution.md)

**Tests**: Included — both `plan.md` Testing section and constitution Development-Workflow gate require unit + integration tests with pre/post Import Residue artifacts.

**Organization**: Tasks are grouped by user story so each story can ship independently. US1 and US2 are both P1 and together form the MVP; US3 is P2.

**Reconciliation note (2026-06-19)**: This task list was regenerated after the
`/speckit-analyze` audit found that Layer 1+2 implementation had outrun the planned
scaffolding (constitution v4.0.0 adapter pattern was bypassed; Move-mode writes occurred
before Preview engine existed). Per constitution v5.0.0:
- The flavor-adapter contract is removed (Principle II). Former T016/T017/T018 are gone.
- Layer 1+2 Move-mode work is acknowledged as a one-time validation spike (STATUS.md);
  the inline logic MUST be refactored into `Lib/preview.py` + `Lib/transfer.py` before
  Layer 3 — see **T-Spike** below.
- Per-category file split survives only for the heavy ones (affixes, templates, MSAs);
  leaf categories collapse into a single `Lib/categories.py`.
- Layout is FLExTrans-style: `gramtrans.py` entry + flat `Lib/` siblings.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User-story label (US1, US2, US3) — required for story phases only
- Paths follow [plan.md](plan.md) Project Structure: `src/gramtrans/gramtrans.py` + `src/gramtrans/Lib/*.py` + `src/gramtrans/Lib/ui/*.py` + `tests/{unit,integration,fixtures}/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic scaffolding.

- [x] T001 Create the directory skeleton from [plan.md](plan.md) Project Structure: `src/gramtrans/gramtrans.py`, `src/gramtrans/Lib/__init__.py` (or empty stub for `site.addsitedir`), `src/gramtrans/Lib/ui/__init__.py`, `tests/{unit,integration,fixtures}/`. DONE during Layer 1+2 validation spike.
- [x] T002 Initialize Python packaging in `pyproject.toml` at repo root: declare `gramtrans` package, Python version per the FlexTools host, runtime deps `flexicon>=2.0` (installed from the MattGyverLee fork, see [../../CLAUDE.md](../../CLAUDE.md)) and PyQt, dev deps `pytest`. DONE 2026-06-19.
- [x] T003 [P] Configure linting/formatting in `pyproject.toml`: `ruff` rules + `black` line length, exclude `tests/fixtures/`. DONE.
- [x] T004 [P] Configure pytest in `pyproject.toml`: `testpaths = ["tests"]`, marker registration for `integration` (requires FlexTools host) so unit-only runs can `-m "not integration"`. DONE.
- [ ] T005 Create `tests/fixtures/toy_source/README.md` pointing at the live `Ejagham Mini` project; commit a placeholder `tests/fixtures/copy_target.py` stub to be filled in by T015

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Lock the flexicon surface, document the fork dependency, scaffold the
helper modules under `Lib/`, and lay down the data-model types every user story depends
on. There is **no** flavor-adapter contract to scaffold (constitution v5.0.0).

**STATUS (2026-06-19)**: D-validation tasks T006–T012 were executed against the live
flexicon surface via the FLExToolsMCP. Findings are baked into [research.md](research.md)
R1, R6, R7, R10 and into [.specify/memory/constitution.md](../../.specify/memory/constitution.md)
v5.0.0. These tasks are marked complete as a record; no further validation work blocks
user-story phases.

### MCP-Mediated Validation (research.md D1–D7) — RESOLVED

- [x] T006 [P] Validate per-operation flavor mapping (research.md D1, R1) via `mcp__flextools-mcp__flextools_get_object_api` + `flextools_find_wrappers_for_lcm` — DONE 2026-06-19; R1 table rewritten in flexicon-direct form
- [x] T007 [P] Confirm FlexTools module entry-point shape (research.md D2) via `mcp__flextools-mcp__flextools_get_module_template` — DONE; `docs = {...}` + `MainFunction(project, report, modifyAllowed)` per FLExTrans convention confirmed (`FlexToolsModuleClass` wrapper NOT required)
- [ ] T008 [P] Confirm PyQt vs PySide for the host (research.md D3) — DEFERRED to UI implementation start; default PyQt5 per `pyproject.toml`, switch to PySide2 if import fails
- [x] T009 [P] Identify the project-enumeration mechanism (research.md D4) — DONE; filesystem scan of `C:\ProgramData\SIL\FieldWorks\Projects` (no flexicon / LCM method enumerates the disk; the MCP's own `flextools_list_projects` is the reference implementation)
- [x] T010 [P] Enumerate per-LCM-type GUID-on-create permissibility (research.md D5) — DONE; some flexicon factory wrappers DO accept a `Guid` parameter on `Create()` (verified against POS, Template, Slot during the Layer 1+2 spike — see STATUS.md); for the remainder the pattern is `factory.Create()` → add to owner → assign `obj.Guid`. The single helper lives inline in `Lib/transfer.py`.
- [x] T011 [P] Enumerate per-LCM-type residue-field availability (research.md D6) — DONE; dual-carrier strategy: `LiftResidue` where present (Lex + MoForm + MSA classes), `Description`-append with `[GT-Tag]:` marker elsewhere
- [x] T012 [P] Confirm `UndoableUnitOfWorkHelper` Python accessibility (research.md D7) — DONE; the FlexTools runner pre-wraps every snippet in a UOW (`STATUS.md` MCP validator quirks); module code does NOT nest its own UOW
- [x] T013 Synthesis: R1 / R6 / R7 / R10 in [research.md](research.md) updated; [plan.md](plan.md) Constitution Check rewritten for v5.0.0 (no adapter contract; LibLCM port is a separate sibling repo)

### Fork Dependency & Validation-Spike Closing — NEW under v5.0.0

- [ ] T-Fork **[BLOCKING US1 impl]** Document the flexicon fork dependency in [../../CLAUDE.md](../../CLAUDE.md) and the repo README: list the 9 patched files (`BaseOperations.py` + 8 Grammar Operations subclasses), the two patches (the `WritingSystems` enumeration fix + the new `ApplySyncableProperties` method), the fork URL or local path (`D:/Github/_Projects/_LEX/flexicon`), and the install steps. The `pyproject.toml` requirement stays as `flexicon>=2.0`; the fork is installed manually.
- [ ] T-Spike **[BLOCKING Layer 3]** Refactor the existing `src/gramtrans/gramtrans.py.transfer_verb_vertical()` inline Move logic into the Preview/Move split required by constitution v5.0.0 Principle III closing clause.

  **Dependency order**: T019 (data-model types in `Lib/types.py`) → T020 (`Lib/residue.py`) → T-Spike → all other US1 implementation tasks.

  **Steps**:
  1. [x] Extract the plan-building portion into `Lib/preview.py` (returns a `RunPlan` object per [data-model.md E4](data-model.md); MUST NOT mutate the target). DONE 2026-06-19 — `build_run_plan()` walks the Verb-vertical closure read-only.
  2. [x] Extract the write portion into `Lib/transfer.py` (consumes a `RunPlan`, writes; emits a `RunReport`). DONE 2026-06-19 — `execute()` consumes the plan; per-layer creators (`_create_pos_with_guid`, `_create_template_with_guid`, `_create_slot_with_guid`) extracted verbatim from the pre-T-Spike monolith so the parity rubric below verifies byte-for-byte.
  3. [x] **FULL PASS 2026-06-19** (post-spike preview + fresh-target Move both run via FlexTools MCP):
     - **Post-spike Preview** against `Ejagham Full GT-Test` containing the prior spike's writes: 0 actions + 6 skips, all GUIDs `already_present_by_guid`. SC-006 verified (`is_certified_readonly=true`).
     - **Fresh-target Move** after `FieldWorks.exe -restore` wiped the target: 6 PlannedActions, 0 skips. `Lib/transfer.execute` created POS `86ff66f6` 'Verb', template `821a96d6`, and 4 slots (SbjAgr/Neg/Mood/Repetative/VSuffix) with all source GUIDs preserved and `lcm_undoable_action_count=7` (Ctrl+Z reverts the entire run). Wall clock 0.082s.
     - **Residue verification**: 6/6 freshly-created objects carry a parseable `[GT-Tag]: GT|GT-20260619-222958|Ejagham Mini|…` line in Description (Carrier B). `ImportResidueTag.parse()` round-trips against live LCM data.
  4. [x] Snapshot artifact `tests/integration/_snapshots/spike_close_post.json` captured 2026-06-19. Contains the 6 verification records with the live-confirmed GUIDs, names, and run_id match.

  **Parity rubric** (step 3 succeeds iff ALL pass):
  - **Same created objects**: every GUID created by the spike's `transfer_verb_vertical()` is also created by `Lib/transfer.py.execute(plan)`; no extra, no missing.
  - **Same residue tag values**: each created object carries an identical `GT|<run_id>|Ejagham Mini|<iso_ts>` tag, with `run_id` and timestamp generated by the new code path (i.e., parseable via `ImportResidueTag.parse`).
  - **Empty skip list**: `RunReport.skips` is empty for the verb-vertical scenario (no closure unresolvable, no GOLD violation, no UNMAPPED_WS).
  - **Same Ctrl+Z behavior**: after the new-pair Move completes, `Ctrl+Z` once in FLEx undoes the entire run (the FlexTools runner's outer UOW still wraps the loop).
  - **Preview-no-writes**: a Preview-only run through `Lib/preview.py` produces a `RunPlan` with the same `actions` count as the Move run, AND the target's pre/post snapshot equality holds (SC-006).

  This task closes the one-time validation-spike exception in Principle III. Layer 3 (LexEntry / Sense / MSA / Allomorph / PhEnvironment) implementation MUST NOT begin until T-Spike completes.

### Test Fixtures

- [ ] T014 Wire **Ejagham Mini** (live at `C:\ProgramData\SIL\FieldWorks\Projects\Ejagham Mini`) as the canonical `toy_source` by reference. Add `tests/fixtures/toy_source/README.md` documenting that this is a pointer to the live project, the project's grammar inventory (≤ a few hundred pieces spanning the FR-004 categories), and the assertion (verified at test setup) that the source remains read-only throughout the run.
- [ ] T015 Build a **persistent-throwaway** fixture helper at `tests/fixtures/copy_target.py`: invokes `FieldWorks.exe -restore 'D:/Github/_Projects/_LEX/GramTrans/backups/Ejagham Full.fwbackup' -db 'Ejagham Full GT-Test' -include c` to refresh the throwaway target before each integration run. Backups live at `D:/Github/_Projects/_LEX/GramTrans/backups/` (both `Ejagham Mini.fwbackup` and `Ejagham Full.fwbackup`). The pre-run snapshot is taken from the restored project as the pristine baseline; SC-004 verifies pre/post equality against that snapshot. This replaces the v4.0.0 temp-snapshot pattern with the realistic "restore-before-each-run" workflow shown in STATUS.md.

### Core Data Model (depends on T013)

- [x] T019 Implement the entity dataclasses + enums from [data-model.md](data-model.md) E1–E4 in `src/gramtrans/Lib/models.py` (renamed from `types.py` to avoid shadowing stdlib `types` under `site.addsitedir`): `GrammarCategory`, `WSKind`, `RunMode`, `SkipReason`, `RunContext`, `Selection`, `WSMappingEntry`, `WSMapping`, `PlannedAction`, `Skip`, `RunPlan`, with the documented invariants enforced in `__post_init__`. **The `Flavor` enum is removed** per constitution v5.0.0. DONE 2026-06-19.
- [x] T020 [P] Implement `src/gramtrans/Lib/residue.py` — `ImportResidueTag` ([data-model.md E5](data-model.md), [spec.md FR-010 / Q5](spec.md)): `serialize()` produces `GT|<run_id>|<source_project_name>|<iso_timestamp>`; classmethod `parse(s)`; helpers `apply_carrier_a(obj, tag)` / `apply_carrier_b(obj, tag)` / `apply_residue(obj, ws, tag)` dispatcher; run_id-matches-timestamp invariant in `__post_init__`. DONE 2026-06-19.
- [x] T021 [P] Implement `src/gramtrans/Lib/report.py` — `RunReport.build_from_plan(plan, mode, wall_clock_seconds=0)` factory classmethod + `to_snapshot_json()` method (per_category dict keyed by enum NAME, ordered by enum declaration order) + `render_text_summary(report)` for the FlexTools report pane. FR-018 invariant enforced in `RunReport.__post_init__` ([data-model.md E6](data-model.md), [contracts/run-report.md](contracts/run-report.md)). DONE 2026-06-19.
- [ ] T022 Implement `src/gramtrans/gramtrans.py` per the FLExTrans convention: module-level `docs = {FTM_Name, FTM_Version, FTM_ModifiesDB, FTM_Synopsis, FTM_Help, FTM_Description}` dict + `MainFunction(project, report, modifyAllowed)` callable, with `import site; site.addsitedir(r"Lib")` at the top. `MainFunction` instantiates the PyQt main window. This **replaces** the v4.0.0 `module.py` + `FlexToolsModuleClass` plan; STATUS.md confirms the no-wrapper template is what the MCP returns.

### Foundational Tests

- [x] T023 [P] Unit test for tag serialize/parse round-trip in `tests/unit/test_residue_format.py` — verifies [data-model.md E5](data-model.md) invariants. DONE 2026-06-19, 7 tests passing.
- [x] T024 [P] Unit test for `RunReport.to_snapshot_json()` field ordering + content in `tests/unit/test_report.py`. DONE 2026-06-19, 3 tests passing.
- [x] T025 [P] Unit test for `Selection` invariants in `tests/unit/test_selection_invariants.py`. DONE 2026-06-19, 4 tests passing.
- [x] T026 [P] Unit test for `WSMapping` 1:1 invariant in `tests/unit/test_ws_mapping_invariants.py`. DONE 2026-06-19, 3 tests passing.

**Checkpoint**: Foundation ready — user-story phases can begin. T-Spike and T-Fork are
prerequisites for any further Move-mode work or Layer 3 implementation.

---

## Phase 3: User Story 1 — Copy Grammar Pieces from Toy Project to Production (Priority: P1) 🎯 MVP (with US2)

**Goal**: A linguist opens the toy source in FlexTools, runs the module, picks the target,
maps writing systems, previews, and moves all selected grammar pieces (with closure) to
the target. New objects appear in the target with preserved GUIDs and Import Residue
tags. ([spec.md US1](spec.md))

**Independent Test**: Run [quickstart.md](quickstart.md) Scenario A end-to-end against
Ejagham Mini → restored `Ejagham Full GT-Test`; verify acceptance scenarios 1–4 from US1.

### Tests for User Story 1 ⚠️

> Write tests FIRST and ensure they fail before implementation. Integration tests
> require the FlexTools host + the Ejagham fixture pair.

- [x] T027 [P] [US1] Unit test for dependency-closure traversal in `tests/unit/test_closure.py` — verifies BFS order, diamond-dependency dedup (single visit + multi-parent record), seed-semantics-win on items appearing as both seed and dep, cycle safety, generator-input compatibility, `topological()` dependencies-first reverse. DONE 2026-06-19, 8 tests passing.
- [x] T028 [P] [US1] Unit test for WS-mapping validation in `tests/unit/test_ws_mapping.py` — verifies `validate()` raises `WSMappingIncomplete` listing missing pairs; `is_complete()` predicate; strict-overspec mode; kind-mismatch handling. DONE 2026-06-19, 7 tests passing. Implementation: `src/gramtrans/Lib/ws_mapping.py` (T036 implementation also done as part of this commit).
- [x] T029 [P] [US1] Unit test asserting Preview Mode produces ZERO mutations against fakes in `tests/unit/test_preview_no_writes.py` — record-everything fake target; covers empty-source edge case, populated-source-empty-target (4 PlannedActions, 0 writes), and target-already-has-GUIDs (skip path, 0 writes). Also covers FR-019 (same source/target handle refusal) via `RunContext` invariant. DONE 2026-06-19, 4 tests passing.
- [ ] T030 [P] [US1] Integration test for full-categories transfer ([US1 Acceptance 1](spec.md)) in `tests/integration/test_e2e_all_categories.py` — runs Move against a freshly-restored `Ejagham Full GT-Test`, snapshots the result via [contracts/run-report.md](contracts/run-report.md), verifies SC-001 timing budget
- [ ] T031 [P] [US1] Integration test for pre-existing target objects not modified ([US1 Acceptance 2](spec.md), [SC-004](spec.md)) in `tests/integration/test_target_preserved.py` — pre-snapshot vs post-snapshot diff equals exactly the added items
- [ ] T032 [P] [US1] Integration test for WS-mapping required-before-write ([US1 Acceptance 4](spec.md), Scenario E) in `tests/integration/test_ws_mapping_required.py`
- [ ] T033 [P] [US1] Integration test for same-source-and-target refusal ([FR-019](spec.md), Scenario D) in `tests/integration/test_same_project_refused.py`
- [ ] T033b [P] [US1] **Integration test for target lock / read-only refusal ([FR-020](spec.md))** in `tests/integration/test_target_locked.py` — open the target in FLEx itself or set the project directory read-only; verify the module surfaces the lock condition before any write and aborts. Closes the coverage gap flagged in the 2026-06-19 audit.
- [ ] T034 [P] [US1] Integration test asserting GUID preservation per [R6](research.md) on the benchmark fixture in `tests/integration/test_guid_preservation.py`
- [ ] T035 [P] [US1] Integration test asserting GOLD inviolability ([FR-022](spec.md)) in `tests/integration/test_gold_inviolable.py` — pre/post snapshot of GOLD objects, asserts byte equality

### Implementation for User Story 1

- [x] T036 [US1] Implement `src/gramtrans/Lib/ws_mapping.py` — `validate(ws_mapping, required, *, strict_overspec=False)` raises `WSMappingIncomplete` (listing missing `(source_ws_id, kind)` pairs) when the mapping is incomplete; `is_complete()` predicate for UI gating; `required_ws_set()` helper to build the required frozenset from a closure-walker's union. The closure-side `required_writing_systems(piece)` per-category call lands with T039+. DONE 2026-06-19, T028 verifies.
- [x] T037 [US1] Implement `src/gramtrans/Lib/closure.py` — `walk(seeds, dependencies_fn)` returns `(visit_order, pulled_in_by)`; dedups by `(category, source_guid)`; seed-semantics-win on items present both as seed and as dependency; handles cycles defensively; works with generator seed input. Companion `topological(order, parents)` reverses for dependencies-first execution. DONE 2026-06-19, T027 verifies.
- [ ] T038 [P] [US1] Implement WS-creation pre-step in `src/gramtrans/Lib/ws_mapping.py`: materializes `WSMapping.entries[create_in_target=True]` into the target via `project.WritingSystem.Create*` (no separate `categories/writing_systems.py` file under v5.0.0)
- [~] T039 [US1] `src/gramtrans/Lib/categories.py` — **SHELL DONE 2026-06-19**. Per-leaf-category function signatures + `LEAF_CATEGORIES` dispatch registry + `for_category(cat)` lookup, all 10 leaf categories. Bodies raise `NotImplementedError("T039: ...")` with task pointers. Test: `tests/unit/test_category_registry.py` (6 tests) locks the registry shape. Full bodies pending LCM live-run validation post-T-Spike.
- [x] T049 [US1] **Affix closure done via `Lib/preview._plan_layer3_verb_affixes` + `Lib/transfer._execute_layer3` 2026-06-19**. 20 allomorphs created with new GUIDs (LibLCM factory limitation; FR-012 identity_remap captures); `PhoneEnvRC` re-wired by GUID lookup against target environments (which were `Skip(ALREADY_PRESENT_BY_GUID)` since FW templates ship them). The category-protocol shell at `categories_affixes.py` stays as a stub for the eventual generic-walker refactor. MCP-verified: 13 LexEntries + 20 allomorphs created in 0.387s on the Ejagham Mini → Full GT-Test pair.
- [x] T050 [US1] Slot transfer inline in `Lib/categories_templates.py` — DONE: no separate `categories_slots.py`. Verb-vertical slot path already lives in `Lib/preview.py._plan_verb_vertical` + `Lib/transfer.py._execute_verb_vertical`.
- [~] T051 [US1] `src/gramtrans/Lib/categories_templates.py` — **SHELL DONE 2026-06-19**. Signature + `BUNDLE` registry. Bodies raise `NotImplementedError("T051: ...")`. Verb-vertical path already implemented in preview.py/transfer.py from T-Spike; T051 generalizes to non-Verb POSes.
- [x] T051b [US1] **MSA + Allomorph + Environment closure done via `Lib/preview._plan_layer3_verb_affixes` + `Lib/transfer._execute_layer3` 2026-06-19**. 13 MoInflAffMsas wired to slots via `SlotsRC` (12 with one slot each, 1 Unbound — matches FR-007 Q4 bucket). 2 PhEnvironments reused from target's FW-template defaults. New GUIDs for MSAs + allomorphs (LibLCM factory limitation) captured in `identity_remap`. MCP-verified live: 59 created total, 0.387s wall-clock, `lcm_undoable_action_count=62`.
- [ ] T052 [US1] Implement `src/gramtrans/Lib/preview.py`: drives source enumeration → closure walk → `plan_action` per category, assembles `RunPlan` per [data-model.md E4](data-model.md) — MUST NOT mutate target (enforced by unit test T029). **Note**: T-Spike must complete first so this file already contains the refactored Layer 1+2 plan-building logic.
- [ ] T053 [US1] Implement `src/gramtrans/Lib/transfer.py`: consumes a `RunPlan`, runs WS-mapping pre-step then iterates `actions` calling the appropriate category function, attaches `ImportResidueTag` to every created object; produces a `RunReport(MOVE)`. The FlexTools runner already wraps each `MainFunction` call in a UOW (per [R10](research.md) + STATUS.md MCP-validator quirks), so this module does NOT open its own `UndoableUnitOfWork`. T-Spike must complete first.
- [x] T054 [P] [US1] `src/gramtrans/Lib/ui/target_picker.py` — `TargetPickerDialog(candidates, parent)` modal QDialog, single-select QListWidget, OK gated on selection, returns chosen `TargetCandidate` via `.selected_candidate()`. DONE 2026-06-19.
- [x] T055 [P] [US1] `src/gramtrans/Lib/ui/ws_mapping_dialog.py` — `WSMappingDialog(required_pairs, target_existing_ws_ids, parent)` modal QDialog with a 4-column table (source ws id / kind / target picker combo / create-in-target checkbox); OK button enabled only when every required row is mapped; returns `WSMapping` via `.selected_mapping()`. DONE 2026-06-19.
- [x] T056 [P] [US1] `src/gramtrans/Lib/ui/stats_panel.py` — `StatsPanel.set_report(report)` renders per-category counts table (added/skipped/closure_pulled_in), skip list, identity remap (hidden when empty), wall-clock footer. Header includes mode + run_id + source→target. Per FR-017 + contracts/run-report.md. DONE 2026-06-19.
- [x] T057 [US1] `src/gramtrans/Lib/ui/main_window.py` — `MainWindow` QDialog drives the full state machine: header → target picker → 14 category toggles + closure toggle → Preview button (opens WSMappingDialog if compute_preview returns NEEDS_WS_MAPPING) → cached-plan-signature gating → Move button → stats panel. Selection / closure-toggle changes invalidate the cached plan and disable Move (Principle III mechanical enforcement). DONE 2026-06-19.
- [x] T058 [US1] Wire the UI ↔ core surface in `src/gramtrans/Lib/api.py` per [contracts/module-ui.md](contracts/module-ui.md): `initialize_run` (mints `RunContextStub` + GT- run_id), `list_target_candidates` (filesystem scan, excludes source by name/path), `bind_target` (FR-019 same-project refusal + lazy flexicon open with TargetUnavailable on LCM error), `compute_preview` (two-stage NEEDS_WS_MAPPING / PREVIEW_READY), `execute_move` (PreviewStale guard + ImportResidueTag construction + `_NullReportSink` fallback). DONE 2026-06-19; 9 unit tests in `tests/unit/test_api_surface.py` cover the LCM-independent paths. The `bind_target` flexicon open + `execute_move` actual writes require FlexTools host (integration tests).
- [ ] T059 [US1] Run [quickstart.md](quickstart.md) Scenarios A and D against the Ejagham fixture pair; capture the snapshot JSONs as pre/post Import Residue artifacts (constitution Development-Workflow gate)

**Checkpoint**: User Story 1 fully functional. Linguists can run the complete additive
transfer end-to-end. T030–T035 + T033b all pass.

---

## Phase 4: User Story 2 — See What Was Transferred (Priority: P1) 🎯 MVP (with US1)

**Goal**: After every run (Preview or Move), the user sees a structured statistics panel
listing per-category added / skipped counts with reasons, plus per-object identifiability
via the Import Residue tag. ([spec.md US2](spec.md))

**Independent Test**: Run [quickstart.md](quickstart.md) Scenarios A and B; verify the
stats panel content matches [contracts/run-report.md](contracts/run-report.md), and
inspect target objects in FLEx to confirm the tag is readable.

### Tests for User Story 2 ⚠️

- [ ] T060 [P] [US2] Integration test for run-report categorization ([US2 Acceptance 1](spec.md)) in `tests/integration/test_run_report_categories.py` — runs a transfer that mixes adds and skips across multiple categories, verifies the snapshot JSON shape
- [ ] T061 [P] [US2] Integration test for unresolvable-dependency skip ([US2 Acceptance 2](spec.md)) in `tests/integration/test_unresolved_dependency_skip.py` — synthesize an item with a dangling ref in the source fixture, verify it appears in `skips` with a human-readable reason and NO partial copy in target
- [ ] T062 [P] [US2] Integration test for residue-tag presence and parseability in target ([US2 Acceptance 3](spec.md), [FR-010 / Q5](spec.md)) in `tests/integration/test_residue_tagging.py` — for every added object, fetch its residue field (Carrier A or B), parse via `ImportResidueTag.parse`, assert run_id + source name + timestamp all populated
- [x] T063 [P] [US2] Unit test for the FR-018 no-silent-drops invariant in `tests/unit/test_no_silent_drops.py` — fabricated `RunPlan` with N actions + M skips, verifies factory accounts for every item; covers actions-only, skips-only, mixed, `closure_pulled_in` as a subcount, empty plan, and direct-construction guard on inconsistent counts. DONE 2026-06-19, 6 tests passing.

### Implementation for User Story 2

- [x] T064 [US2] `Lib/report.py.RunReport.build_from_plan` increments `closure_pulled_in` for each `PlannedAction` whose `pulled_in_by` is non-empty. DONE 2026-06-19 as part of T021.
- [x] T065 [US2] FR-018 invariant in `Lib/models.py.RunReport.__post_init__` (where the dataclass lives) — raises if `sum(per_category[*].skipped) != len(skips)`. DONE 2026-06-19; T063 verifies.
- [ ] T066 [US2] Extend `src/gramtrans/Lib/ui/stats_panel.py` to render the skip list with reasons + the identity remap section per the ASCII layout in [contracts/run-report.md](contracts/run-report.md)
- [x] T067 [US2] `ImportResidueTag` surfaced in `docs[FTM_Description]` in `src/gramtrans/gramtrans.py` — description mentions "look in Residue (Lex* classes) or the object's Description ([GT-Tag]: line) to find this run's additions". DONE 2026-06-19.
- [ ] T068 [US2] Run [quickstart.md](quickstart.md) Scenario A step 12 verification (Residue tag inspection) end-to-end

**Checkpoint**: US1 + US2 together constitute the MVP. The module ships at this point if
needed; US3 is an enhancement.

---

## Phase 5: User Story 3 — Choose Which Grammar Piece Categories to Transfer (Priority: P2)

**Goal**: The user selects which grammar-piece categories participate in a transfer,
including per-affix selection via a tree picker (template → slot → affix + Unbound).
([spec.md US3](spec.md))

**Independent Test**: Run [quickstart.md](quickstart.md) Scenarios B and F; verify
Affixes-only transfer pulls in closure correctly, and that closure-off mode skips items
with `BARE_BONES_MISSING_CLOSURE`.

### Tests for User Story 3 ⚠️

- [ ] T069 [P] [US3] Integration test for affix-only transfer with closure pull-in ([US3 Acceptance 2](spec.md), Scenario B) in `tests/integration/test_closure_pull_in.py`
- [ ] T070 [P] [US3] Integration test for affix tree picker shape (Q4) in `tests/integration/test_affix_tree_picker.py` — verifies the tree contains a top-level "Unbound" branch and template → slot → affix branches for affixes bound to templates
- [ ] T071 [P] [US3] Integration test for closure-off → BARE_BONES_MISSING_CLOSURE skip (Scenario F) in `tests/integration/test_closure_off_skip.py`
- [x] T072 [P] [US3] Unit test for the convenience-toggle behavior in `tests/unit/test_affix_tree_selection.py` — verifies template-pick pulls all descendant affixes via slot membership, slot-pick pulls only that slot's affixes, individual affix picks survive, unbound affixes work, multi-level picks union, unknown GUIDs ignored, templates don't propagate from slot/affix picks, `build_selection` sets the right `categories` toggles + propagates extras + honors `include_closure`. DONE 2026-06-19, 13 tests passing.

### Implementation for User Story 3

- [x] T073 [US3] Implement `src/gramtrans/Lib/selection.py` — `PickerState` + `SourceAffixInventory` dataclasses, `compute_required_affixes(picker, inventory)` and `compute_required_templates(picker, inventory)` set-math helpers, and `build_selection(picker, inventory, *, include_closure=True, extra_categories=())` factory that produces the canonical `Selection` shape consumed by preview. DONE 2026-06-19, T072 verifies.
- [x] T074 [US3] `src/gramtrans/Lib/ui/affix_tree_picker.py` — `AffixTreePicker(inventory, affix_label_for, slot_label_for, template_label_for, parent)` modal QDialog with QTreeWidget rendering Template → Slot → Affix nodes + a top-level "Unbound" bucket; uses Qt's `ItemIsAutoTristate` for convenience-toggle propagation; `picker_state()` collapses checkbox state into a `PickerState`. DONE 2026-06-19.
- [ ] T075 [US3] Wire `affix_tree_picker.py` into `Lib/ui/main_window.py` — opens when the user toggles AFFIXES on (or clicks "Pick specific affixes…"). Closure on/off toggle ALREADY in the main window (T057). Affix-picker wiring pending source-inventory enumeration (depends on `Lib/categories_affixes.py` T049).
- [x] T076 [US3] Closure-off mode skip semantics in `Lib/preview.py`: when `selection.include_closure=False`, user-selected pieces whose dependencies are NOT also user-selected become `Skip(reason=BARE_BONES_MISSING_CLOSURE)`. Pieces in non-user-selected categories simply don't appear. Closure-ON sanity test confirms templates/slots still get pulled in regardless. DONE 2026-06-19, 6 tests in `tests/unit/test_closure_off_skip.py` passing.
- [ ] T077 [US3] Run [quickstart.md](quickstart.md) Scenarios B and F end-to-end

**Checkpoint**: All three user stories functional. Module is feature-complete for
Phase 0.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verification artifacts, constitution gates, and documentation that span all
stories.

- [ ] T078 [P] Run the full integration suite (`pytest -m integration`) against the Ejagham fixture pair; capture per-test snapshot JSONs in `tests/integration/_snapshots/`
- [ ] T079 [P] Verify [SC-001](spec.md) (≤100-piece benchmark in <5 min) by running [quickstart.md](quickstart.md) Scenario A with a timer; record the wall-clock in `tests/integration/_snapshots/sc001.txt`
- [ ] T080 [P] Verify [SC-003](spec.md) (zero dangling refs in target) by post-Move integrity scan in `tests/integration/test_no_dangling_refs.py`
- [ ] T081 [P] Verify [SC-004](spec.md) (zero modifications to pre-existing target objects) via the pre/post snapshot diff already in T031, extracted into a standalone scenario in `tests/integration/_snapshots/sc004.json`
- [ ] T082 Capture pre/post Import Residue artifacts (constitution Development-Workflow gate): export `tests/integration/_snapshots/residue_pre.json` (empty) and `residue_post.json` (all added objects with parsed tags) from the benchmark run
- [x] T083 Update [plan.md](plan.md) Constitution Check for constitution v5.0.0: no flavor-adapter contract; no LibLCM in this repo; Phase 3 LibLCM port is a separate sibling repo. DONE 2026-06-19 as part of the v5.0.0 pivot.
- [x] T084 [P] `docs = {...}` dict in `src/gramtrans/gramtrans.py` carries `FTM_Name`, `FTM_Version` (0.1.0), `FTM_ModifiesDB=True`, `FTM_Synopsis`, `FTM_Description` (including the Q5 tag-format note). DONE 2026-06-19.
- [x] T085 [P] [CLAUDE.md](../../CLAUDE.md) SPECKIT block updated for v5.0.0 + fork-dependency section added. DONE 2026-06-19.
- [ ] T086 Run [quickstart.md](quickstart.md) Scenarios A–F all the way through against the Ejagham fixture pair; produce a one-page release-notes summary in `specs/001-phase0-additive-transfer/release-notes.md` enumerating which acceptance scenarios passed and the wall-clock per scenario

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No prior dependencies — already complete from the Layer 1+2 spike.
- **Foundational (Phase 2)**: Depends on Phase 1. The D-validation subgroup (T006–T013) is complete. **T-Fork** and **T-Spike** are new blocking tasks under v5.0.0; T-Fork blocks any US1 implementation, T-Spike blocks any Layer 3 work (T051b).
- **US1 (Phase 3)**: Depends on Phase 2 completion + T-Spike (for `Lib/preview.py` + `Lib/transfer.py` existence). MVP-critical.
- **US2 (Phase 4)**: Depends on Phase 2. Test code can be authored alongside US1 implementation; tests run after US1's engine code lands.
- **US3 (Phase 5)**: Depends on Phase 2. Independent of US1/US2 conceptually; integration tests run against a working transfer engine, so they execute after US1's engine code lands.
- **Polish (Phase 6)**: Depends on all desired stories.

### Within Each User Story

- Tests (T027–T035 + T033b for US1, T060–T063 for US2, T069–T072 for US3) MUST be written and FAIL before their implementation tasks.
- `Lib/preview.py` (T052) and `Lib/transfer.py` (T053) are seeded by T-Spike, then extended by US1 work.
- Leaf categories (T039) before categories that depend on them (T049 affixes, T051 templates, T051b MSAs).
- UI before main-window wiring (T054–T056 before T057).

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel.
- All D-validation tasks (T006–T012) ran in parallel — all complete.
- All foundational unit tests (T023–T026) are parallel.
- T-Fork and T-Spike are sequential: T-Fork is documentation only and can run in parallel with anything; T-Spike requires the data-model types from T019.
- All US1 UI files (T054, T055, T056) are parallel; the main window (T057) waits for them.
- All US2 tests (T060–T063) are parallel.
- All US3 tests (T069–T072) are parallel.
- Different stories can be staffed in parallel by different developers once Phase 2 completes.

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Phase 1: Setup — complete.
2. Phase 2: Foundational — D-validation complete; **execute T-Fork (documentation) and T-Spike (Layer 1+2 refactor into Preview/Move pair) first**; then the data-model + residue + report modules + tests.
3. Phase 3: US1 — engine + UI code; Layer 3 (T051b MSAs) gated on T-Spike.
4. Phase 4: US2 — small (4 tests + 5 impl tasks); mostly tightens existing reporting.
5. **STOP and VALIDATE**: Run quickstart scenarios A, D, E. Confirm pre/post Residue artifacts captured.
6. Ship MVP.

### Incremental Delivery

1. T-Fork + T-Spike → foundation safe for further Move work.
2. Foundation tests + data-model types → user-story phases begin.
3. US1 → ship MVP candidate; collect feedback on transfer correctness.
4. US2 → tighten reporting; ship updated MVP.
5. US3 → add affix tree-picker + closure-off mode; ship Phase 0 final.
6. Phase 6 polish → cut Phase 0 release.

### Constitution Gate Reminders

- Phase 0 imports flexicon directly. There is no `flavors/` directory; no adapter contract. (Principle II, v5.0.0)
- Preview Mode MUST produce zero writes; T029 + T081 enforce this. The Layer 1+2 Move-mode spike is the one-time exception closed by T-Spike. (Principle III)
- GOLD inviolability test T035 MUST pass before Phase 0 ships. (Principle I)
- Phase 1 / Phase 2 features (overwrite, interactive merge) MUST NOT appear in this Phase 0 codebase. (Principle IV)
- Phase 3 (LibLCM-direct) MUST NOT appear in this codebase — it is a separate sibling repo. (Principle IV, v5.0.0)
- Closure-by-default is the UI default; opt-out is a deliberate user action. (Principle V)

---

## Notes

- `[P]` tasks operate on different files with no incomplete-task dependencies.
- `[Story]` label maps to spec.md user stories for traceability.
- Tests fail before implementation (red-green discipline). **Carve-out**: Layer 1+2 work in STATUS.md ran ahead of TDD as the recorded validation spike per constitution v5.0.0 Principle III; T-Spike closes that exception and Layer 3 onward returns to red-green discipline.
- Stop at any checkpoint to validate the just-completed user story end-to-end against quickstart scenarios.
- The `mcp__flextools-mcp__*` calls in Phase 2 are **author-side**, not runtime — per constitution Principle II, no MCP imports appear in `src/gramtrans/` code.

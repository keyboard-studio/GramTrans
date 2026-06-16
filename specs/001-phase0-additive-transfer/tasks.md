---

description: "Task list for Phase 0 — Additive Grammar Transfer"
---

# Tasks: Phase 0 — Additive Grammar Transfer

**Input**: Design documents from [specs/001-phase0-additive-transfer/](.)

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md), [constitution v3.0.0](../../.specify/memory/constitution.md)

**Tests**: Included — both `plan.md` Testing section and constitution Development-Workflow gate require unit + integration tests with pre/post Import Residue artifacts.

**Organization**: Tasks are grouped by user story so each story can ship independently. US1 and US2 are both P1 and together form the MVP; US3 is P2.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User-story label (US1, US2, US3) — required for story phases only
- Paths follow [plan.md](plan.md) Project Structure: `src/gramtrans/{ui,core,flavors,categories}/` and `tests/{unit,integration,fixtures}/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic scaffolding.

- [ ] T001 Create the directory skeleton from [plan.md](plan.md) Project Structure: `src/gramtrans/__init__.py`, `src/gramtrans/{ui,core,flavors,categories}/__init__.py`, `tests/{unit,integration,fixtures}/`
- [ ] T002 Initialize Python packaging in `pyproject.toml` at repo root: declare `gramtrans` package, Python version per the FlexTools host, runtime deps `flexlibs1` and PyQt (LibLCM is consumed via the FlexTools .NET bridge, not pip), dev deps `pytest`
- [ ] T003 [P] Configure linting/formatting in `pyproject.toml`: `ruff` rules + `black` line length, exclude `tests/fixtures/`
- [ ] T004 [P] Configure pytest in `pyproject.toml`: `testpaths = ["tests"]`, marker registration for `integration` (requires FlexTools host) so unit-only runs can `-m "not integration"`
- [ ] T005 Create empty `tests/fixtures/toy_source/.gitkeep` and `tests/fixtures/empty_target/.gitkeep` placeholders; document that real FLEx project copies land here during T013

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Resolve the constitution-mandated flavor validation, scaffold the flavor adapters, and lay down the data-model types every user story depends on.

**⚠️ CRITICAL**: No user-story work begins until this phase completes. The D-validation tasks (T006–T012) can REVERT LibLCM rows in `research.md` R1 back to flexlibs1 — code written before these complete risks being wrong about which flavor to call.

### MCP-Mediated Validation (research.md D1–D7)

Per constitution v3.0.0 Principle II, each LibLCM call site requires Constitution-Check justification. These tasks gather that evidence using the FLExToolsMCP author-side assistant.

- [ ] T006 [P] Validate per-operation flavor mapping (research.md D1, R1) by calling `mcp__flextools-mcp__flextools_get_object_api` + `flextools_find_wrappers_for_lcm` for each operation family; update R1 table in [research.md](research.md), flip any LibLCM row back to flexlibs1 where flexlibs1 actually suffices
- [ ] T007 [P] Confirm FlexTools module entry-point shape (research.md D2) via `mcp__flextools-mcp__flextools_get_module_template` + `flextools_list_skeletons`; record findings in [research.md](research.md) R3
- [ ] T008 [P] Confirm PyQt vs PySide for the host (research.md D3) via `mcp__flextools-mcp__flextools_find_examples`; record findings in [research.md](research.md) R4
- [ ] T009 [P] Identify the project-enumeration mechanism (research.md D4) via `mcp__flextools-mcp__flextools_search_by_capability` (query: "list FLEx projects"); record findings in [research.md](research.md) R5/R11
- [ ] T010 [P] Enumerate per-LCM-type GUID-on-create permissibility (research.md D5) via `mcp__flextools-mcp__flextools_get_object_api` per category from [FR-004](spec.md); record findings in [research.md](research.md) R6 and as a table in `src/gramtrans/flavors/_guid_permissibility.md`
- [ ] T011 [P] Enumerate per-LCM-type residue-field availability (research.md D6) via `mcp__flextools-mcp__flextools_resolve_property` per category; record findings in [research.md](research.md) R7 and as a table in `src/gramtrans/flavors/_residue_fields.md`
- [ ] T012 [P] Confirm `UndoableUnitOfWork` (or equivalent) Python accessibility (research.md D7) via `mcp__flextools-mcp__flextools_find_wrappers_for_lcm`; record findings in [research.md](research.md) R10
- [ ] T013 Once T006–T012 complete: update [research.md](research.md) R1's "Flavor" column with the final per-operation choice (flexlibs1 by default, LibLCM only where T006–T012 prove it necessary), and update [plan.md](plan.md) Constitution Check row II with the count of surviving LibLCM call sites and their justifications

### Test Fixtures (manual, gated on D-validation results)

- [ ] T014 Create the real `tests/fixtures/toy_source/` FLEx project: ≤20 grammar pieces spanning every category from [FR-004](spec.md) (a few phonemes, gram categories, inflection features, custom fields, a handful of affixes with allomorphs + APRs, one slot, one template, one variant type, one compound rule), at least one item per category, at least one affix bound to a slot + one Unbound affix (per Q4)
- [ ] T015 [P] Create the real `tests/fixtures/empty_target/` FLEx project: pristine new project, same FLEx version as `toy_source/`, with NO grammar pieces beyond the FLEx defaults (no extra categories, no extra inflection features beyond GOLD)

### Flavor Adapter Scaffolding (depends on T013)

- [ ] T016 [P] Define the abstract adapter interface in `src/gramtrans/flavors/base.py`: one abstract method per primitive (`open_project_for_read`, `open_project_for_write`, `enumerate_writing_systems`, `create_writing_system`, `create_object`, `set_field`, `set_string_field`, `set_residue`, `set_guid_on_create`, `open_undo_unit`, `commit_undo_unit`, plus per-category traversal helpers); declare the `Flavor` enum (`FLEXLIBS1`, `LIBLCM`)
- [ ] T017 [P] Implement `src/gramtrans/flavors/flexlibs1_adapter.py`: full implementation of every primitive from T016 using flexlibs1 (preferred flavor per constitution Principle II)
- [ ] T018 [P] Implement `src/gramtrans/flavors/liblcm_adapter.py`: implementations ONLY for the primitives that T013 proved flexlibs1 cannot satisfy; each method's docstring must state "flexlibs1 cannot do X because Y"

### Core Data Model (depends on T013)

- [ ] T019 Implement the entity dataclasses + enums from [data-model.md](data-model.md) E1–E4 in `src/gramtrans/core/types.py`: `GrammarCategory`, `Flavor` (re-export from flavors.base), `WSKind`, `RunMode`, `SkipReason`, `RunContext`, `Selection`, `WSMappingEntry`, `WSMapping`, `PlannedAction`, `Skip`, `RunPlan`, with the documented invariants enforced in `__post_init__`
- [ ] T020 [P] Implement `src/gramtrans/core/residue.py` — `ImportResidueTag` ([data-model.md E5](data-model.md), [spec.md FR-010 / Q5](spec.md)): `serialize() -> str` produces `GT|<run_id>|<source_project_name>|<iso_timestamp>`; classmethod `parse(s) -> ImportResidueTag | None` so Phase 1/2 read tags unchanged
- [ ] T021 [P] Implement `src/gramtrans/core/report.py` — `CategoryReport`, `RunReport` ([data-model.md E6](data-model.md)) with `to_snapshot_json()` matching the schema in [contracts/run-report.md](contracts/run-report.md)
- [ ] T022 Implement `src/gramtrans/module.py` — FlexTools entry point per T007 result; exposes `FlexToolsModuleClass` + a `Main` function that instantiates the PyQt main window (UI implementation lands in US1 phase)

### Foundational Tests

- [ ] T023 [P] Unit test for tag serialize/parse round-trip in `tests/unit/test_residue_format.py` — verifies [data-model.md E5](data-model.md) invariants (`prefix == "GT"`, `run_id` matches timestamp)
- [ ] T024 [P] Unit test for `RunReport.to_snapshot_json()` field ordering + content in `tests/unit/test_report.py` — uses fabricated `RunReport` objects, asserts deterministic key order per [contracts/run-report.md](contracts/run-report.md)
- [ ] T025 [P] Unit test for `Selection` invariants in `tests/unit/test_selection_invariants.py` (e.g., `affix_picks` non-empty ⇒ `categories[AFFIXES]=True`)
- [ ] T026 [P] Unit test for `WSMapping` 1:1 invariant in `tests/unit/test_ws_mapping_invariants.py` — no two entries share `target_ws_id` unless they share `source_ws_id`

**Checkpoint**: Foundation ready — user-story phases can begin. D-validation results are baked into the flavor adapters and research.md.

---

## Phase 3: User Story 1 — Copy Grammar Pieces from Toy Project to Production (Priority: P1) 🎯 MVP (with US2)

**Goal**: A linguist opens the toy source in FlexTools, runs the module, picks an empty target, maps writing systems, previews, and moves all selected grammar pieces (with closure) to the target. New objects appear in the target with preserved GUIDs and Import Residue tags. ([spec.md US1](spec.md))

**Independent Test**: Run [quickstart.md](quickstart.md) Scenario A end-to-end against the fixture pair; verify acceptance scenarios 1–4 from US1.

### Tests for User Story 1 ⚠️

> Write tests FIRST and ensure they fail before implementation. Integration tests require the FlexTools host; unit tests run without it.

- [ ] T027 [P] [US1] Unit test for dependency-closure traversal (BFS, dedup on diamond deps, leaf categories produce empty refs) in `tests/unit/test_closure.py`
- [ ] T028 [P] [US1] Unit test for WS-mapping validation (every referenced source WS must be mapped; reject mappings missing required entries) in `tests/unit/test_ws_mapping.py`
- [ ] T029 [P] [US1] Unit test asserting Preview Mode produces ZERO mutations against fakes (`tests/unit/test_preview_no_writes.py`) — uses an in-memory fake target that records any write attempt; asserts the recorder is empty after `compute_preview`
- [ ] T030 [P] [US1] Integration test for full-categories transfer ([US1 Acceptance 1](spec.md)) in `tests/integration/test_e2e_all_categories.py` — runs Move against a fresh copy of `empty_target/`, snapshots the result via [contracts/run-report.md](contracts/run-report.md), verifies SC-001 timing budget
- [ ] T031 [P] [US1] Integration test for pre-existing target objects not modified ([US1 Acceptance 2](spec.md), [SC-004](spec.md)) in `tests/integration/test_target_preserved.py` — pre-snapshot vs post-snapshot diff equals exactly the added items
- [ ] T032 [P] [US1] Integration test for WS-mapping required-before-write ([US1 Acceptance 4](spec.md), Scenario E) in `tests/integration/test_ws_mapping_required.py`
- [ ] T033 [P] [US1] Integration test for same-source-and-target refusal ([FR-019](spec.md), Scenario D) in `tests/integration/test_same_project_refused.py`
- [ ] T034 [P] [US1] Integration test asserting GUID preservation per [R6](research.md) on the benchmark fixture in `tests/integration/test_guid_preservation.py`
- [ ] T035 [P] [US1] Integration test asserting GOLD inviolability ([FR-022](spec.md)) in `tests/integration/test_gold_inviolable.py` — pre/post snapshot of GOLD objects, asserts byte equality

### Implementation for User Story 1

- [ ] T036 [US1] Implement `src/gramtrans/core/ws_mapping.py`: builds the required-WS set from a `Selection` (calls `CategoryTransfer.required_writing_systems` per category), validates a user-provided `WSMapping` against that set, raises `WSMappingIncomplete(missing)` per [contracts/module-ui.md](contracts/module-ui.md)
- [ ] T037 [US1] Implement `src/gramtrans/core/closure.py`: BFS over `CategoryTransfer.dependencies()`, dedup by `(category, source_guid)`, returns ordered `(category, source_guid)` list for [data-model.md E4](data-model.md) `RunPlan.actions`
- [ ] T038 [P] [US1] Implement `src/gramtrans/categories/writing_systems.py` — pre-step that materializes `WSMapping.entries[create_in_target=True]` into the target via the flexlibs1 adapter (or LibLCM per T013 result)
- [ ] T039 [P] [US1] Implement `src/gramtrans/categories/gram_categories.py` — GOLD-aware (`SkipReason.GOLD_INVIOLABLE` when the piece IS a GOLD object; refs to GOLD objects are normal-resolved)
- [ ] T040 [P] [US1] Implement `src/gramtrans/categories/inflection_features.py` — GOLD-aware (same rule as gram_categories)
- [ ] T041 [P] [US1] Implement `src/gramtrans/categories/custom_fields.py`
- [ ] T042 [P] [US1] Implement `src/gramtrans/categories/inflection_classes.py`
- [ ] T043 [P] [US1] Implement `src/gramtrans/categories/stem_names.py`
- [ ] T044 [P] [US1] Implement `src/gramtrans/categories/exception_features.py`
- [ ] T045 [P] [US1] Implement `src/gramtrans/categories/variant_types.py` — closure includes associated inflection features ([FR-004](spec.md))
- [ ] T046 [P] [US1] Implement `src/gramtrans/categories/complex_form_types.py`
- [ ] T047 [P] [US1] Implement `src/gramtrans/categories/adhoc_rules.py`
- [ ] T048 [P] [US1] Implement `src/gramtrans/categories/compound_rules.py`
- [ ] T049 [US1] Implement `src/gramtrans/categories/affixes.py` ([FR-005](spec.md)) — closure pulls in allomorphs, APRs, inflection features, classes, stem names, exception features; depends on T040–T044
- [ ] T050 [US1] Implement `src/gramtrans/categories/slots.py` — slots are reached from templates; standalone selection allowed
- [ ] T051 [US1] Implement `src/gramtrans/categories/templates.py` ([FR-006](spec.md)) — closure includes slots + filling affixes; depends on T049, T050
- [ ] T052 [US1] Implement `src/gramtrans/core/preview.py`: drives `enumerate_source` → closure walk → `plan_action` per category, assembles `RunPlan` per [data-model.md E4](data-model.md) — MUST NOT mutate target (enforced by unit test T029)
- [ ] T053 [US1] Implement `src/gramtrans/core/transfer.py`: consumes a `RunPlan`, opens a single `UndoableUnitOfWork` per [R10](research.md), runs WS-mapping pre-step then iterates `actions` calling `execute_action` per category, attaches `ImportResidueTag` to every created object; produces a `RunReport(MOVE)`
- [ ] T054 [P] [US1] Implement `src/gramtrans/ui/target_picker.py` per [contracts/module-ui.md](contracts/module-ui.md) — list candidates from T009 result, exclude source by path, single-select, returns `TargetCandidate`
- [ ] T055 [P] [US1] Implement `src/gramtrans/ui/ws_mapping_dialog.py` ([FR-011 / Q3](spec.md)) — shows every required `(source_ws_id, kind)`, lets user pick from existing target WSs or create new; refuses confirm until complete; returns `WSMapping`
- [ ] T056 [P] [US1] Implement `src/gramtrans/ui/stats_panel.py` ([FR-017](spec.md), [contracts/run-report.md](contracts/run-report.md)) — basic per-category counts + skip list + identity remap section (US2 will refine the closure-pulled-in display)
- [ ] T057 [US1] Implement `src/gramtrans/ui/main_window.py` — instantiates from `module.py`, drives the [data-model.md state machine](data-model.md): source detection → target picker → category toggles + closure toggle → Preview → WS mapping → Preview result → Move (gated by current-selection-equals-cached-plan-selection per Principle III)
- [ ] T058 [US1] Wire the UI ↔ core surface from [contracts/module-ui.md](contracts/module-ui.md): `initialize_run`, `list_target_candidates`, `bind_target`, `compute_preview`, `execute_move` in `src/gramtrans/core/api.py` (the single entry point UI calls)
- [ ] T059 [US1] Run [quickstart.md](quickstart.md) Scenarios A and D against the fixture pair; capture the snapshot JSONs as pre/post Import Residue artifacts (constitution Development-Workflow gate)

**Checkpoint**: User Story 1 fully functional. Linguists can run the complete additive transfer end-to-end. T030–T035 all pass.

---

## Phase 4: User Story 2 — See What Was Transferred (Priority: P1) 🎯 MVP (with US1)

**Goal**: After every run (Preview or Move), the user sees a structured statistics panel listing per-category added / skipped counts with reasons, plus per-object identifiability via the Import Residue tag. ([spec.md US2](spec.md))

**Independent Test**: Run [quickstart.md](quickstart.md) Scenarios A and B; verify the stats panel content matches [contracts/run-report.md](contracts/run-report.md), and inspect target objects in FLEx to confirm the tag is readable.

### Tests for User Story 2 ⚠️

- [ ] T060 [P] [US2] Integration test for run-report categorization ([US2 Acceptance 1](spec.md)) in `tests/integration/test_run_report_categories.py` — runs a transfer that mixes adds and skips across multiple categories, verifies the snapshot JSON shape
- [ ] T061 [P] [US2] Integration test for unresolvable-dependency skip ([US2 Acceptance 2](spec.md)) in `tests/integration/test_unresolved_dependency_skip.py` — synthesize an item with a dangling ref in the source fixture, verify it appears in `skips` with a human-readable reason and NO partial copy in target
- [ ] T062 [P] [US2] Integration test for residue-tag presence and parseability in target ([US2 Acceptance 3](spec.md), [FR-010 / Q5](spec.md)) in `tests/integration/test_residue_tagging.py` — for every added object, fetch its residue field, parse via `ImportResidueTag.parse`, assert run_id + source name + timestamp all populated
- [ ] T063 [P] [US2] Unit test for the FR-018 no-silent-drops invariant in `tests/unit/test_no_silent_drops.py` — fabricates a `RunPlan` with N actions + M skips, asserts the resulting `RunReport` accounts for N+M items across `added`/`skipped` counts with zero loss

### Implementation for User Story 2

- [ ] T064 [US2] Extend `src/gramtrans/core/report.py` to compute per-category `closure_pulled_in` count by inspecting `PlannedAction.pulled_in_by` from the plan
- [ ] T065 [US2] Add the FR-018 invariant check to `src/gramtrans/core/report.py.RunReport.__post_init__` — raises if any planned action is missing from both `added` counts and `skips` (defensive; T063 verifies)
- [ ] T066 [US2] Extend `src/gramtrans/ui/stats_panel.py` to render the skip list with reasons + the identity remap section per the ASCII layout in [contracts/run-report.md](contracts/run-report.md)
- [ ] T067 [US2] Surface `ImportResidueTag` in the user-visible help (one-line "Look in Residue for `GT|<run-id>|...` to find this run's additions") via the module's docs / help text in `src/gramtrans/module.py`
- [ ] T068 [US2] Run [quickstart.md](quickstart.md) Scenario A step 12 verification (Residue tag inspection) end-to-end

**Checkpoint**: US1 + US2 together constitute the MVP. The module ships at this point if needed; US3 is an enhancement.

---

## Phase 5: User Story 3 — Choose Which Grammar Piece Categories to Transfer (Priority: P2)

**Goal**: The user selects which grammar-piece categories participate in a transfer, including per-affix selection via a tree picker (template → slot → affix + Unbound). ([spec.md US3](spec.md))

**Independent Test**: Run [quickstart.md](quickstart.md) Scenarios B and F; verify Affixes-only transfer pulls in closure correctly, and that closure-off mode skips items with `BARE_BONES_MISSING_CLOSURE`.

### Tests for User Story 3 ⚠️

- [ ] T069 [P] [US3] Integration test for affix-only transfer with closure pull-in ([US3 Acceptance 2](spec.md), Scenario B) in `tests/integration/test_closure_pull_in.py`
- [ ] T070 [P] [US3] Integration test for affix tree picker shape (Q4) in `tests/integration/test_affix_tree_picker.py` — verifies the tree contains a top-level "Unbound" branch and template → slot → affix branches for affixes bound to templates
- [ ] T071 [P] [US3] Integration test for closure-off → BARE_BONES_MISSING_CLOSURE skip (Scenario F) in `tests/integration/test_closure_off_skip.py`
- [ ] T072 [P] [US3] Unit test for the convenience-toggle behavior (selecting a template selects all affixes under it; affix-level selection still possible) in `tests/unit/test_affix_tree_selection.py`

### Implementation for User Story 3

- [ ] T073 [US3] Extend `src/gramtrans/core/selection.py` (split out of `core/types.py` if it has grown) with helpers: `compute_required_affixes(selection, source_inventory) -> frozenset[str]`, `compute_required_templates(...)` — translates tree-picker output into the `Selection` shape consumed by preview
- [ ] T074 [US3] Implement `src/gramtrans/ui/affix_tree_picker.py` ([FR-007 / Q4](spec.md)) — tree organized template → slot → affix, with a top-level "Unbound" bucket for affixes not yet in any template; template- and slot-level checkboxes toggle all descendants but per-affix selection remains; returns `frozenset[str]` for `Selection.affix_picks`
- [ ] T075 [US3] Wire `affix_tree_picker.py` into `ui/main_window.py` — opens when the user toggles AFFIXES on (or clicks "Pick specific affixes…"); also add the closure on/off toggle to the main window if not already present
- [ ] T076 [US3] Surface closure-off mode's skip semantics in `core/preview.py`: when `selection.include_closure=False`, any selected piece whose deps are not also selected becomes a `Skip(reason=BARE_BONES_MISSING_CLOSURE)`
- [ ] T077 [US3] Run [quickstart.md](quickstart.md) Scenarios B and F end-to-end

**Checkpoint**: All three user stories functional. Module is feature-complete for Phase 0.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verification artifacts, constitution gates, and documentation that span all stories.

- [ ] T078 [P] Run the full integration suite (`pytest -m integration`) against the fixture pair; capture per-test snapshot JSONs in `tests/integration/_snapshots/`
- [ ] T079 [P] Verify [SC-001](spec.md) (≤100-piece benchmark in <5 min) by running [quickstart.md](quickstart.md) Scenario A with a timer; record the wall-clock in `tests/integration/_snapshots/sc001.txt`
- [ ] T080 [P] Verify [SC-003](spec.md) (zero dangling refs in target) by post-Move integrity scan in `tests/integration/test_no_dangling_refs.py`
- [ ] T081 [P] Verify [SC-004](spec.md) (zero modifications to pre-existing target objects) via the pre/post snapshot diff already in T031, extracted into a standalone scenario in `tests/integration/_snapshots/sc004.json`
- [ ] T082 Capture pre/post Import Residue artifacts (constitution Development-Workflow gate): export `tests/integration/_snapshots/residue_pre.json` (empty) and `residue_post.json` (all added objects with parsed tags) from the benchmark run
- [ ] T083 Update [plan.md](plan.md) Constitution Check row II with the final post-T013 count of surviving LibLCM call sites; for each, paste the "flexlibs1 cannot do X because Y" justification line from the relevant adapter docstring
- [ ] T084 [P] Add module docstring + the in-module help string in `src/gramtrans/module.py` so FlexTools' module list shows a one-sentence description and the help action surfaces the Q5 tag-format note
- [ ] T085 [P] Update [CLAUDE.md](../../CLAUDE.md) SPECKIT block already done by `/speckit-plan`; no-op unless paths changed
- [ ] T086 Run [quickstart.md](quickstart.md) Scenarios A–F all the way through against the fixture pair; produce a one-page release-notes summary in `specs/001-phase0-additive-transfer/release-notes.md` enumerating which acceptance scenarios passed and the wall-clock per scenario

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No prior dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1. The D-validation subgroup (T006–T013) blocks T014–T026 because flavor choices feed adapter implementations.
- **US1 (Phase 3)**: Depends on Phase 2 completion. MVP-critical.
- **US2 (Phase 4)**: Depends on Phase 2. Independent of US1's implementation tasks; tests CAN share the same fixture run, but T060–T063 require US1's transfer engine to be working so they run after US1's implementation in practice (the test code can be authored in parallel — the [P] markers reflect that).
- **US3 (Phase 5)**: Depends on Phase 2. Independent of US1/US2 stories conceptually, but its integration tests run against a working transfer engine, so they execute after US1's engine code lands.
- **Polish (Phase 6)**: Depends on all desired stories.

### Within Each User Story

- Tests (T027–T035 for US1, T060–T063 for US2, T069–T072 for US3) MUST be written and FAIL before their implementation tasks.
- Core engine before per-category modules (categories use the engine's enums/types).
- Categories with no closure deps (T039–T048) before categories that depend on them (T049 affixes, T051 templates).
- UI before main-window wiring (T054–T056 before T057).

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel.
- All D-validation tasks (T006–T012) can run in parallel — they query different MCP tool families and update independent sections of research.md.
- Adapter scaffolding (T016–T018) is parallel once T013 lands.
- All foundational unit tests (T023–T026) are parallel.
- All US1 category implementations without closure deps (T039–T048) are parallel.
- All US1 UI files (T054, T055, T056) are parallel; the main window (T057) waits for them.
- All US2 tests (T060–T063) are parallel.
- All US3 tests (T069–T072) are parallel.
- Different stories can be staffed in parallel by different developers once Phase 2 completes.

---

## Parallel Example: User Story 1 categories burst

```text
# Once T036 (ws_mapping) and T037 (closure) land, the leaf-category implementations
# can all run in parallel — they share no files:

Task: T039 Implement categories/gram_categories.py
Task: T040 Implement categories/inflection_features.py
Task: T041 Implement categories/custom_fields.py
Task: T042 Implement categories/inflection_classes.py
Task: T043 Implement categories/stem_names.py
Task: T044 Implement categories/exception_features.py
Task: T045 Implement categories/variant_types.py
Task: T046 Implement categories/complex_form_types.py
Task: T047 Implement categories/adhoc_rules.py
Task: T048 Implement categories/compound_rules.py

# Then T049 (affixes) and T050 (slots), which depend on the leaves above,
# and finally T051 (templates) which depends on T049 + T050.
```

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Complete Phase 1: Setup (~5 small tasks).
2. Complete Phase 2: Foundational — the D-validation block is the longest pole here; everything else parallelizes.
3. Complete Phase 3: US1 — the bulk of the engine + UI code.
4. Complete Phase 4: US2 — small (4 tests + 5 impl tasks); mostly tightens existing reporting.
5. **STOP and VALIDATE**: Run quickstart scenarios A, D, E. Confirm pre/post Residue artifacts captured.
6. Ship MVP.

### Incremental Delivery

1. Foundation ready → user-story phases begin.
2. US1 → ship MVP candidate; collect feedback on transfer correctness.
3. US2 → tighten reporting; ship updated MVP.
4. US3 → add affix tree-picker + closure-off mode; ship Phase 0 final.
5. Phase 6 polish → cut Phase 0 release.

### Constitution Gate Reminders

- Every LibLCM call site that survives T013 MUST be justified in [plan.md](plan.md) Constitution Check row II (Principle II).
- Preview Mode MUST produce zero writes; T029 + T081 enforce this (Principle III).
- GOLD inviolability test T035 MUST pass before Phase 0 ships (Principle I).
- Phase 1 / Phase 2 features (overwrite, interactive merge) MUST NOT appear in this Phase 0 codebase (Principle IV).
- Closure-by-default is the UI default; opt-out is a deliberate user action (Principle V).

---

## Notes

- `[P]` tasks operate on different files with no incomplete-task dependencies.
- `[Story]` label maps to spec.md user stories for traceability.
- Tests fail before implementation (red-green discipline); commit at each task or logical group.
- Stop at any checkpoint to validate the just-completed user story end-to-end against quickstart scenarios.
- The `mcp__flextools-mcp__*` calls in Phase 2 are **author-side**, not runtime — per constitution Principle II, no MCP imports appear in `src/gramtrans/` code.

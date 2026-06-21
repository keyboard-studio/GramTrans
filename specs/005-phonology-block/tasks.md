---

description: "Phase 3a — Phonology Block tasks"

---

# Tasks: Phase 3a — Phonology Block

**Input**: Design documents from `/specs/005-phonology-block/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Organization**: Tasks are grouped by user story (US1–US4 from [spec.md](spec.md)). Each story is independently testable per its acceptance scenarios. Tests are included per spec.md SC-305 (target ~310 total).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 / US2 / US3 / US4 — maps to spec.md user stories
- File paths are absolute relative to repository root

## Path Conventions

- Source: `src/gramtrans/Lib/` (FLExTrans-style flat helpers)
- Tests: `tests/unit/`, `tests/integration/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add enum members + stub callback registrations. No business logic yet.

- [ ] T001 Add 5 `GrammarCategory` enum members (`PHONOLOGICAL_FEATURES`, `PHONEMES`, `NATURAL_CLASSES`, `PHONOLOGICAL_RULES`, `STRATA`) in `src/gramtrans/Lib/models.py` per data-model.md E-3a-1
- [ ] T002 Add 6 new registry entries to `LEAF_CATEGORIES` in `src/gramtrans/Lib/categories.py` — one per (phon_features, phonemes, natural_classes, ph_environment relocation, phon_rules, strata) — each pointing at 5 placeholder functions that raise `NotImplementedError("Phase 3a stub")`
- [ ] T003 Confirm `src/gramtrans/Lib/preview.py.build_run_plan` iterates the `LEAF_CATEGORIES` registry via the existing dispatch (read-only check; no edit expected; if a special-case branch is missing, add it)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: MCP-probe each category's LCM factory + Operations surface to determine GUID-preservability before any execute callback is written. Per research R2, phoneme Guid support is TBD; same for natural classes and phonological rules.

**⚠️ CRITICAL**: Stories US1–US4 cannot begin writing execute callbacks until this phase is complete.

- [ ] T004 [P] MCP-probe `IPhPhonemeFactory` constructor signatures via `flextools_get_object_api(object_type='IPhPhonemeFactory')`; record Guid-overload availability in a new `specs/005-phonology-block/probe-results.md` file
- [ ] T005 [P] MCP-probe `IPhNCSegmentsFactory` and `IPhNCFeaturesFactory` constructor signatures; append findings to `probe-results.md`
- [ ] T006 [P] MCP-probe `IPhEnvironmentFactory.Create` signatures (verify the existing Phase 0 GUID-preservation still works); append to `probe-results.md`
- [ ] T007 [P] MCP-probe `IPhRegularRuleFactory` / `IPhSegmentRuleFactory` / `IPhMetathesisRuleFactory`; append to `probe-results.md`
- [ ] T008 [P] MCP-probe `IMoStratumFactory` constructor signatures + relevant Stratum properties; append to `probe-results.md`
- [ ] T009 [P] MCP-probe `IFsClosedFeatureFactory` for the phonological-feature subsystem; confirm the same factory serves both the phon and inflection systems or whether a separate one exists; append to `probe-results.md`
- [ ] T010 Wait/check on flexlibs#196 — if `StratumOperations` lands in flexlibs2 fork before T035, update T035-T038 task descriptions to use `project.Strata.*` instead of the `GetService` workaround

**Checkpoint**: T004-T009 outputs land in `probe-results.md`. T010 is gated on external flexlibs2 PR.

---

## Phase 3: User Story 1 — Phonemes + Natural Classes + Phonological Rules (Priority: P1) 🎯 MVP

**Goal**: Transfer a phoneme inventory + natural classes + phonological rules from source to target with GUIDs preserved (or identity_remap'd), with FR-304 dependency closure enforced.

**Independent Test**: Quickstart Scenario A (additive) + Scenario C (dependency-unresolved skip).

### Phon Features (#2)

- [ ] T011 [P] [US1] Implement `phon_features_enumerate_source` in `src/gramtrans/Lib/categories.py` — walks the phonological feature subsystem, returns iterable of `IFsClosedFeature` objects
- [ ] T012 [P] [US1] Implement `phon_features_plan_action` and `phon_features_execute_action` in `src/gramtrans/Lib/categories.py` — mirrors existing `inflection_features` callback pattern; creates `IFsClosedFeature` + values via the factory probed in T009
- [ ] T013 [US1] Unit tests in `tests/unit/test_categories_phon_features.py`: enumerate_source returns expected count, plan_action emits PlannedAction for new + Skip(ALREADY_PRESENT_BY_GUID) for matched

### Phonemes (#3)

- [ ] T014 [P] [US1] Implement `phonemes_enumerate_source` in `src/gramtrans/Lib/categories.py` — iterates `source.Phonemes.GetAll()`
- [ ] T015 [P] [US1] Implement `phonemes_dependencies` and `phonemes_required_writing_systems` — phonemes are leaves dep-wise; WSes come from name multistring
- [ ] T016 [US1] Implement `phonemes_plan_action` in `src/gramtrans/Lib/categories.py` — uses the GUID-overload probed in T004; falls back to identity_remap if absent
- [ ] T017 [US1] Implement `phonemes_execute_action` in `src/gramtrans/Lib/categories.py` — creates `IPhPhoneme`, adds to `target.PhonologicalDataOA.PhonemeSetsOS[0].PhonemesOC`, applies syncable properties + Carrier-A residue
- [ ] T018 [US1] Unit tests in `tests/unit/test_categories_phonemes.py`: GUID-preserving create when factory supports, identity_remap fallback when not, feature struct (FeaturesOA) survives import, name multistring transfers

### Natural Classes (#4)

- [ ] T019 [P] [US1] Implement `natural_classes_enumerate_source` in `src/gramtrans/Lib/categories.py` — iterates `source.NaturalClasses.GetAll()`, returns both Segments and Features subtypes
- [ ] T020 [P] [US1] Implement `natural_classes_dependencies` — for IPhNCSegments, returns the GUIDs of phonemes referenced via `SegmentsRC`; for IPhNCFeatures, empty (FeaturesOA is owned, not referenced)
- [ ] T021 [US1] Implement `natural_classes_plan_action` and `natural_classes_execute_action` — branch on `ICmObject(obj).ClassName` to choose between `IPhNCSegmentsFactory` and `IPhNCFeaturesFactory`
- [ ] T022 [US1] Unit tests in `tests/unit/test_categories_natural_classes.py`: both subtypes create with correct factory, `SegmentsRC` resolution against the in-flight phoneme plan, `FeaturesOA` survives owned

### Phonological Rules (#5) — incl. FR-304 dependency closure

- [ ] T023 [P] [US1] Implement `phon_rules_enumerate_source` in `src/gramtrans/Lib/categories.py` — iterates `source.PhonRules.GetAll()`
- [ ] T024 [US1] Implement `phon_rules_dependencies` in `src/gramtrans/Lib/categories.py` — walks each rule's input segments, output segments, left/right contexts, plus `StratumRA`; returns tuple of referenced GUIDs (phoneme + class + env + stratum)
- [ ] T025 [US1] Implement `phon_rules_plan_action` in `src/gramtrans/Lib/categories.py` per [contracts/phonology-rule-dependencies.md](contracts/phonology-rule-dependencies.md) — emits `Skip(DEPENDENCY_UNRESOLVED, detail=<unresolved GUIDs>)` when any reference is missing from target AND from the in-flight plan
- [ ] T026 [US1] Implement `phon_rules_execute_action` — creates the right subtype (regular / segment / metathesis), wires input/output segments + contexts + `StratumRA`, applies residue
- [ ] T027 [US1] Unit tests in `tests/unit/test_categories_phon_rules.py`: dependency-closure walk identifies all referenced GUIDs, plan_action skips when phoneme deselected, execute wires all four reference types (input, output, left ctx, right ctx)
- [ ] T028 [US1] Integration test in `tests/integration/test_phase3a_phonology_e2e.py::test_us1_phoneme_nc_rule_round_trip` exercising Scenario A from quickstart (additive happy path)
- [ ] T029 [US1] Integration test `test_us1_dependency_unresolved_skip` exercising Scenario C (rule references unimported phoneme → DEPENDENCY_UNRESOLVED Skip)

**Checkpoint**: US1 ships in isolation. Phonemes / classes / rules transfer end-to-end with closure enforcement. Phase 0/1/2 regression suite still 267-of-267 green.

---

## Phase 4: User Story 2 — Strata (Priority: P1)

**Goal**: Strata import as a standalone category, ready for Phase 3b morphology consumers' `StratumRA` references.

**Independent Test**: Stratum category transfers with source GUIDs preserved; later morphology-block ordering (when Phase 3b lands) finds strata already in target.

- [ ] T030 [P] [US2] If flexlibs#196 has landed: implement `strata_*` callbacks using `project.Strata.*` Operations API. If NOT landed: implement using `project.GetService(IMoStratumFactory)` per research R1, with a TODO comment naming the issue.
- [ ] T031 [P] [US2] Implement `strata_enumerate_source` in `src/gramtrans/Lib/categories.py` — iterates `source.Cache.LangProject.MorphologicalDataOA.StrataOS`
- [ ] T032 [US2] Implement `strata_plan_action` and `strata_execute_action` — create via factory probed in T008, add to `target.Cache.LangProject.MorphologicalDataOA.StrataOS`, apply Carrier-A residue
- [ ] T033 [US2] Unit tests in `tests/unit/test_categories_strata.py`: GUID handling, syncable properties (Name + Abbreviation multistring), empty-source returns empty
- [ ] T034 [US2] Integration test `test_us2_strata_transfer` exercising Scenario A's strata sub-step

**Checkpoint**: US2 ships independently. Strata are in target ready for Phase 3b.

---

## Phase 5: User Story 3 — PhEnvironment idempotency (Priority: P2)

**Goal**: Phase 3a's phonology block populates PhEnvironments BEFORE Phase 0/1/2 allomorph closure runs, so allomorph creation finds them by GUID.

**Independent Test**: Quickstart Scenario D.

- [ ] T035 [P] [US3] Implement `ph_environment_enumerate_source` standalone in `src/gramtrans/Lib/categories.py` — iterates `source.Environments.GetAll()` (project-wide, not allomorph-bundled)
- [ ] T036 [US3] Refactor the existing Phase 0/1/2 allomorph closure code in `src/gramtrans/Lib/preview.py` to: (a) skip emitting PlannedAction for an env that's ALREADY in the in-flight plan from the phonology-block enumerate (set-based dedup); (b) keep the create-if-missing fallback path for Phase 0 single-allomorph runs that don't enable the phonology block
- [ ] T037 [US3] Unit tests in `tests/unit/test_categories_ph_environments.py`: idempotency — when phonology-block has emitted an env action, the allomorph-closure walker does NOT emit a duplicate
- [ ] T038 [US3] Integration test `test_us3_ph_env_idempotency` exercising Scenario D — phonology runs first, then verb-vertical runs and produces zero new PhEnv creates

**Checkpoint**: US3 ships. The relocation is invisible to existing Phase 0/1/2 callers; existing tests continue to pass.

---

## Phase 6: User Story 4 — Empty-source graceful skip (Priority: P3)

**Goal**: Categories with empty source short-circuit without error.

**Independent Test**: Run with all six phonology+strata categories enabled against a source whose `PhonologicalDataOA` and `MorphologicalDataOA.StrataOS` are empty.

- [ ] T039 [P] [US4] Verify each `enumerate_source` callback returns `()` (empty tuple) cleanly when the source collection is empty (no exceptions). Add explicit guards if any LCM accessor raises on an empty container.
- [ ] T040 [US4] Enhance `src/gramtrans/Lib/report.py.render_text_summary` to emit a one-line `[skip] no items in source for X` per zero-source-zero-overwrite-zero-skip category, matching the memo's UX section
- [ ] T041 [US4] Unit tests in `tests/unit/test_categories_empty_source.py`: each of the six categories with empty source returns `()` from enumerate_source and produces zero plan actions
- [ ] T042 [US4] Integration test `test_us4_all_empty_source` exercising the empty-source-everywhere case

**Checkpoint**: US4 ships. Categories without source items are visible in the run report as `[skip] no items in source for X` lines.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Regression sweep, live MCP verification, and STATUS handoff.

- [ ] T043 [P] Run the full unit-test suite: `python -m pytest tests/unit -q`; confirm 267 Phase 0/1/2 tests + ~40 new Phase 3a tests all green (target ~307)
- [ ] T044 [P] Run the integration suite: `python -m pytest tests/integration -q`; all Phase 3a e2e tests green
- [ ] T045 Live MCP verification: run quickstart Scenarios A-E in order against Ejagham Mini → Ejagham Full GT-Test via `flextools_run_module`; log results into `specs/005-phonology-block/verification-log.md`
- [ ] T046 Update `STATUS.md` to mark Phase 3a complete and queue Phase 3b (the morphology block: steps 6-13 and 14-18 of the ordering memo, modulo any already-COMPLETE leaf categories)
- [ ] T047 Commit in topic-aligned increments: T001-T010 (setup + foundational), then one commit per US (US1, US2, US3, US4), then polish

---

## Dependencies

```
Phase 1 (Setup) ──▶ Phase 2 (Foundational) ──▶ Phase 3 (US1, MVP)
                                            ├▶ Phase 4 (US2)
                                            ├▶ Phase 5 (US3)
                                            └▶ Phase 6 (US4)
                    Phase 7 (Polish) runs after all stories.
```

Story-level dependencies:
- US1: depends on Phase 2 (MCP probes). MVP.
- US2: depends on Phase 2 + (optionally) flexlibs#196 landing. Independent of US1.
- US3: depends on US1 (uses the phonology-block enumeration the US1 categories produce). Conceptually independent of US2.
- US4: depends on nothing beyond setup; testable in isolation.

## Parallel Opportunities

- **Phase 1 (Setup)**: T001 / T002 / T003 sequential (same file edits + verification).
- **Phase 2 (Foundational)**: T004-T009 fully parallel — each probes a different LCM type independently.
- **Phase 3 (US1)**: per-category subgroups parallel — Phon Features (T011/T012), Phonemes (T014-T017), Natural Classes (T019-T021), Rules (T023-T026) can all be developed in parallel by independent contributors. Tests (T013/T018/T022/T027/T028/T029) parallel within each sub-block.
- **Phase 4 (US2)**: T030/T031 parallel; T032 depends on probe.
- **Phase 5 (US3)**: T035 parallel with US1 work; T036 (refactor) depends on US1's phonology-block enumerate being callable.
- **Phase 6 (US4)**: T039 parallel with US1-3; T040 / T041 / T042 sequential within polish.
- **Phase 7**: T043 / T044 / T045 parallel.

## MVP Scope

**MVP = Phases 1 + 2 + 3 (US1 only)**: 29 tasks. At MVP:
- A linguist can transfer phonemes, natural classes, and phonological rules from a sister project.
- FR-304 dependency closure surfaces unresolved references explicitly.
- Phase 0/1/2 verb-vertical transfer continues to work unchanged.

US2 (strata, Phase 4) is highly recommended for Phase 3b readiness but not blocking. US3 (relocation, Phase 5) is a cleanup. US4 (empty-skip, Phase 6) is UX polish.

## Independent Test Criteria

| Story | Criterion |
|-------|-----------|
| US1 | Run Scenario A (additive) → 30 phonemes / 10 NCs / 5 rules land. Run Scenario C → rule references unimported phoneme → Skip(DEPENDENCY_UNRESOLVED). |
| US2 | Run Scenario A's strata sub-step → 2 strata land in target.MoMorphData.StrataOS with source GUIDs. |
| US3 | Run Scenario A then Scenario D → verb-vertical allomorph closure emits zero ph_environment Create calls. |
| US4 | Run with all six categories on against empty-phonology source → 6 `[skip] no items in source for X` lines, zero errors. |

## Task Count

- **Phase 1 (Setup)**: 3 tasks
- **Phase 2 (Foundational)**: 7 tasks
- **Phase 3 (US1 / MVP)**: 19 tasks
- **Phase 4 (US2)**: 5 tasks
- **Phase 5 (US3)**: 4 tasks
- **Phase 6 (US4)**: 4 tasks
- **Phase 7 (Polish)**: 5 tasks
- **Total**: 47 tasks

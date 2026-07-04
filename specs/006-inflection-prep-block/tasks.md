---

description: "Phase 3b — Inflection / Lexicon-Prep Block tasks"

---

# Tasks: Phase 3b — Inflection / Lexicon-Prep Block

**Input**: Design documents from `/specs/006-inflection-prep-block/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Organization**: Tasks grouped by user story (US1–US4 from [spec.md](spec.md)). Each story independently testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Parallelizable (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 / US2 / US3 / US4
- File paths absolute relative to repository root

## Path Conventions

- Source: `src/gramtrans/Lib/`
- Tests: `tests/unit/`, `tests/integration/`

---

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 Add `SEMANTIC_DOMAINS` member to `GrammarCategory` enum in `src/gramtrans/Lib/models.py` per data-model.md entity 9
- [x] T002 Add 4 stub registry entries (`custom_fields`, `variant_types`, `complex_form_types`, `semantic_domains`) to `LEAF_CATEGORIES` in `src/gramtrans/Lib/categories.py`, each pointing at 5 placeholder functions that raise `NotImplementedError("Phase 3b stub")`
- [x] T003 Extend `_LEAF_DISPATCH_CATEGORIES` tuple in `src/gramtrans/Lib/preview.py` AND `src/gramtrans/Lib/transfer.py` to include the 9 Phase 3b categories per contracts/category-callbacks.md wiring section

---

## Phase 2: Foundational (Blocking Prerequisites — MCP Probes)

**⚠️ CRITICAL**: Stories US1–US4 cannot begin writing execute callbacks until probes complete.

- [x] T004 [P] MCP-probe `ICmPossibilityFactory` and `IPartOfSpeechFactory` (`flextools_get_object_api`); record Guid-overload availability and POS-vs-CmPossibility split in `specs/006-inflection-prep-block/probe-results.md`
- [x] T005 [P] MCP-probe `MetaDataCacheAccessor.AddCustomField` signature + `CellarPropertyType` enum members; append to `probe-results.md`
- [x] T006 [P] MCP-probe `ILexEntryTypeFactory` (used by both variant types and complex form types) + whether flexiconexposes `project.VariantEntryTypes` / `project.ComplexEntryTypes` wrappers or whether `GetService` fallback applies; append to `probe-results.md`
- [x] T007 [P] MCP-probe `ICmSemanticDomainFactory` Guid-overload availability + verify `SemanticDomainListOA.PossibilitiesOS` walk path; append to `probe-results.md`
- [x] T008 [P] MCP-probe how variant-type `InflFeatsOS` (`IFsFeatStruc` owned collection) enumerates referenced `IFsSymFeatVal`s for the FR-327 dependency check; append to `probe-results.md`

**Checkpoint**: T004-T008 outputs land in `probe-results.md`.

---

## Phase 3: User Story 1 — POS family transfer (Priority: P1) 🎯 MVP

**Goal**: Confirm the five COMPLETE callbacks (gram_categories, inflection_features, inflection_classes, stem_names, exception_features) thread through the leaf-dispatch loop end-to-end with GOLD inviolability and identity_remap fallback.

**Independent Test**: Quickstart Scenario A's POS / inflection-features / inflection-classes / stem-names / exception-features sub-steps.

- [x] T009 [US1] Read [Lib/categories.py](../../src/gramtrans/Lib/categories.py) entries for `gram_categories`, `inflection_features`, `inflection_classes`, `stem_names`, `exception_features`; confirm each has all 5 callbacks registered (no NotImplementedError) and document the registry shape in `probe-results.md` under "Phase 3b reuse audit"
- [x] T010 [US1] Verify the existing Phase 0 unit suite still passes with the T003 dispatch-tuple extension in place: `python -m pytest tests/unit/test_categories.py tests/unit/test_categories_pos.py -q` (or whichever files cover the five COMPLETE callbacks). 0 regressions expected.
- [x] T011 [P] [US1] Integration test in `tests/integration/test_phase3b_inflection_e2e.py::test_us1_pos_family_round_trip` — fake-LCM-surface run of all five COMPLETE callbacks under leaf dispatch, asserting per-category `added` counts and GOLD `Skip(GOLD_INVIOLABLE)` for catalog-backed POSes
- [x] T012 [P] [US1] Integration test `test_us1_identity_remap_fallback` — factory rejects `Create(Guid)`; assert `report.identity_remap[src_guid] == new_guid` and the action completes
- [x] T013 [US1] Live MCP Scenario A.1 (POS-family sub-run): drive `MainFunction` with only US1 categories ticked, source = Ejagham Mini, target = Ejagham Full GT-Test; log per-category counts to `verification-log.md` — see Run 1 (pre-retarget) + Run 2 (`gram_categories` retarget post-`798dc0b`)

**Checkpoint**: US1 ships. The five COMPLETE callbacks are dispatched and validated end-to-end. No code changes to the callbacks themselves; this story is wiring + verification.

---

## Phase 4: User Story 2 — Custom Fields (Priority: P1) — SHIPPED (detect-only)

**Status (2026-06-21 08:45)**: US2 shipped as detect-and-report per LEX
crew cycle-1 approval (Option C adopted). Creation remains blocked at
flexiconlayer pending Phase 2 transaction mode. The four implemented
callbacks (`enumerate_source`, `dependencies`,
`required_writing_systems`, `plan_action`) detect target's existing
custom fields via `CustomFieldOperations.GetAllFields` / `FindField`
and emit `Skip(ALREADY_PRESENT_BY_GUID)` on match,
`Skip(NEEDS_MANUAL)` on absence. `execute_action` is a registered
no-op stub. See [us2-blocker-memo.md](us2-blocker-memo.md) for
promotion path when Phase 2 transaction mode lands.

**Goal (original)**: Custom-field definitions land in target before Phase 3c LexEntries reference them.

**Independent Test**: Quickstart Scenario A's custom-fields sub-step.

- [x] T014 [P] [US2] Implement `custom_fields_enumerate_source` — **shipped as detect-only** via `CustomFieldOperations.GetAllFields` per Option C (creation blocked at flexiconUoW layer; see [us2-blocker-memo.md](us2-blocker-memo.md))
- [x] T015 [P] [US2] Implement `custom_fields_dependencies` (returns `()`) and `custom_fields_required_writing_systems`
- [x] T016 [US2] Implement `custom_fields_plan_action` — `Skip(ALREADY_PRESENT_BY_IDENTITY)` on `(class_id, name)` tuple match; `Skip(NEEDS_MANUAL)` on absence (detect-and-report posture, cycle 3 ruling)
- [~] T017 [US2] Implement `custom_fields_execute_action` — **registered no-op stub** pending Phase 2 transaction-mode rework at flexiconlayer
- [x] T018 [US2] Unit tests in `tests/unit/test_categories_custom_fields.py` covering detect/identity/no-op invariants
- [~] T019 [US2] Integration test `test_us2_custom_fields_round_trip` — deferred with T017 (no-op execute path has nothing to round-trip)
- [~] T020 [US2] Live MCP Scenario A.2 — deferred with T017

**Checkpoint**: US2 ships. Custom-field definitions transfer before any Phase 3c entry import would reference them.

---

## Phase 5: User Story 3 — Variant Types + Complex Form Types + Semantic Domains (Priority: P2)

**Goal**: The three remaining Phase 3b categories — variant types (with feature-constraint dependency closure per FR-327), complex form types (leaf), and semantic domains (with GOLD catalog skip per FR-326).

**Independent Test**: Quickstart Scenarios A's variant/complex/semantic sub-steps + Scenario C dependency closure.

### Variant Types (#7)

- [x] T021 [P] [US3] Implement `variant_types_enumerate_source` — recursive walk of `VariantEntryTypesOA.PossibilitiesOS` + `SubPossibilitiesOS`
- [x] T022 [US3] Implement `variant_types_dependencies` per FR-327 — walks `InflFeatsOA.FeatureSpecsOC` (revised from initial OS assumption — see probe-results.md)
- [x] T023 [US3] Implement `variant_types_plan_action` and `variant_types_execute_action` — 1-arg `Create(Guid)` + manual `_safe_add_to_owner` (per pythonnet overload constraint, commit `beeb60c`); owner-class discrimination via `ICmObject(src_obj).Owner.ClassName`
- [x] T024 [US3] Unit tests in `tests/unit/test_categories_phase3b_us3.py`

### Complex Form Types (#8)

- [x] T025 [P] [US3] Implement `complex_form_types_enumerate_source` — recursive walk of `ComplexEntryTypesOA.PossibilitiesOS`
- [x] T026 [US3] Implement `complex_form_types_dependencies`, `plan_action`, `execute_action` (same shape as variant_types minus dependency)
- [x] T027 [US3] Unit tests in `tests/unit/test_categories_phase3b_us3.py`

### Semantic Domains (#9)

- [x] T028 [P] [US3] Implement `semantic_domains_enumerate_source` — recursive walk of `SemanticDomainListOA.PossibilitiesOS`
- [x] T029 [US3] Implement `semantic_domains_dependencies`, `plan_action`, `execute_action` — FR-326 GOLD sieve verified live (1792 GOLD skips, Run 3)
- [x] T030 [US3] Unit tests in `tests/unit/test_categories_phase3b_us3.py`
- [x] T031 [US3] Integration test coverage via leaf-dispatch smoke (`test_phase3b_leaf_dispatch.py`)
- [x] T032 [US3] `Skip(DEPENDENCY_UNRESOLVED)` path unit-tested in `test_categories_phase3b_us3.py`
- [x] T033 [US3] Live MCP Scenario A.3 — see verification-log Run 3; Scenario C deferred (source lacks variant types with non-empty `InflFeatsOA`)

**Checkpoint**: US3 ships. The three remaining Phase 3b categories transfer with FR-326 GOLD respect and FR-327 dependency closure.

---

## Phase 6: User Story 4 — Empty-source UX (Priority: P3)

**Goal**: All nine Phase 3b categories inherit FR-308 empty-source UX. Selected-but-empty categories emit `[skip] no items in source for X` lines in `render_text_summary`.

**Independent Test**: Quickstart Scenario D.

- [x] T034 [P] [US4] Enumerate-source guards verified across the 4 new callbacks
- [x] T035 [US4] Empty-source coverage rolled into `test_phase3b_leaf_dispatch.py`
- [x] T036 [US4] FR-308 lines verified live in Run 1 Preview (3 empty-source lines rendered)

**Checkpoint**: US4 ships. FR-308 inherited cleanly.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T037 [P] Run full unit suite — **324 passed, 5 skipped** (2026-06-21 close-sweep)
- [x] T038 [P] Run integration suite — **18 passed, 15 skipped** (all skips are live-FlexTools required)
- [~] T039 Live MCP Scenario B (overwrite re-run) and E (Phase 0/1/2/3a regression) — deferred; Runs 1-3 in verification-log are write-mode evidence on the same target without triggering regressions
- [x] T040 Update `STATUS.md` to mark Phase 3b complete and queue Phase 3c (memo steps 14-18)
- [x] T041 Commit in topic-aligned increments — see commit log `6beac7a` … `beeb60c`

---

## Dependencies

```
Phase 1 (Setup) ──▶ Phase 2 (Foundational) ──▶ Phase 3 (US1, MVP)
                                            ├▶ Phase 4 (US2)
                                            ├▶ Phase 5 (US3)
                                            └▶ Phase 6 (US4)
                    Phase 7 (Polish) runs after all stories.
```

Story-level:
- **US1**: depends on Phase 2 probes. MVP. Pure wiring + verification — no callback rewrites.
- **US2**: depends on Phase 2 T005 (MDC probe). Independent of US1.
- **US3**: depends on Phase 2 T006-T008. Variant types' FR-327 dependency check works whether US1 has shipped or not (the in-plan inflection-features come from Phase 0 callbacks already present).
- **US4**: depends only on Phase 1 setup; testable in isolation.

## Parallel Opportunities

- **Phase 1**: T001/T002/T003 sequential (same file edits).
- **Phase 2**: T004-T008 fully parallel — independent MCP probes.
- **Phase 3 (US1)**: T011/T012 parallel (different test files); T013 live-MCP serial.
- **Phase 4 (US2)**: T014/T015 parallel; T016/T017 sequential (same file edits to one callback set); T018/T019/T020 sequential.
- **Phase 5 (US3)**: variant-types subgroup (T021-T024), complex-form-types subgroup (T025-T027), semantic-domains subgroup (T028-T030) all parallel across subgroups. Within each, the enumerate-first task is parallel-safe; plan_action + execute_action are sequential within the same callback set.
- **Phase 6 (US4)**: T034 parallel; T035/T036 sequential.
- **Phase 7**: T037/T038 parallel.

## MVP Scope

**MVP = Phases 1 + 2 + 3 (US1 only)**: 13 tasks. At MVP:
- A linguist can transfer POS + inflection features + inflection classes + stem names + exception features from a sister project.
- The five COMPLETE callbacks are validated under leaf dispatch.
- Phase 0/1/2/3a regression suite continues green.

US2 (custom fields) is highly recommended before Phase 3c lands. US3 (variant/complex/semantic) needed for Phase 3c lexicon imports to resolve references. US4 (empty-source UX) is polish.

## Independent Test Criteria

| Story | Criterion |
|-------|-----------|
| US1 | Run Scenario A.1 (POS family sub-step) → POS / IF / IC / SN / EF land with source GUIDs; GOLD POSes (Verb, Noun) skip with GOLD_INVIOLABLE. |
| US2 | Run Scenario A.2 → 3 custom fields land in target MDC; re-run finds them by `(class_id, name)` and emits zero new PlannedActions. |
| US3 | Run Scenario A.3 → 4 variant types + 2 complex form types + 5 custom semantic domains land; ~1700 GOLD semantic domains skip. Run Scenario C → variant type with unresolved IFsSymFeatVal emits Skip(DEPENDENCY_UNRESOLVED). |
| US4 | Run with 9 categories on against empty-inflection source → 9 `[skip] no items in source for X` lines, zero errors. |

## Task Count

- **Phase 1 (Setup)**: 3 tasks
- **Phase 2 (Foundational)**: 5 tasks
- **Phase 3 (US1 / MVP)**: 5 tasks
- **Phase 4 (US2)**: 7 tasks
- **Phase 5 (US3)**: 13 tasks
- **Phase 6 (US4)**: 3 tasks
- **Phase 7 (Polish)**: 5 tasks
- **Total**: 41 tasks

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

- [ ] T001 Add `SEMANTIC_DOMAINS` member to `GrammarCategory` enum in `src/gramtrans/Lib/models.py` per data-model.md entity 9
- [ ] T002 Add 4 stub registry entries (`custom_fields`, `variant_types`, `complex_form_types`, `semantic_domains`) to `LEAF_CATEGORIES` in `src/gramtrans/Lib/categories.py`, each pointing at 5 placeholder functions that raise `NotImplementedError("Phase 3b stub")`
- [ ] T003 Extend `_LEAF_DISPATCH_CATEGORIES` tuple in `src/gramtrans/Lib/preview.py` AND `src/gramtrans/Lib/transfer.py` to include the 9 Phase 3b categories per contracts/category-callbacks.md wiring section

---

## Phase 2: Foundational (Blocking Prerequisites — MCP Probes)

**⚠️ CRITICAL**: Stories US1–US4 cannot begin writing execute callbacks until probes complete.

- [ ] T004 [P] MCP-probe `ICmPossibilityFactory` and `IPartOfSpeechFactory` (`flextools_get_object_api`); record Guid-overload availability and POS-vs-CmPossibility split in `specs/006-inflection-prep-block/probe-results.md`
- [ ] T005 [P] MCP-probe `MetaDataCacheAccessor.AddCustomField` signature + `CellarPropertyType` enum members; append to `probe-results.md`
- [ ] T006 [P] MCP-probe `ILexEntryTypeFactory` (used by both variant types and complex form types) + whether flexlibs2 exposes `project.VariantEntryTypes` / `project.ComplexEntryTypes` wrappers or whether `GetService` fallback applies; append to `probe-results.md`
- [ ] T007 [P] MCP-probe `ICmSemanticDomainFactory` Guid-overload availability + verify `SemanticDomainListOA.PossibilitiesOS` walk path; append to `probe-results.md`
- [ ] T008 [P] MCP-probe how variant-type `InflFeatsOS` (`IFsFeatStruc` owned collection) enumerates referenced `IFsSymFeatVal`s for the FR-327 dependency check; append to `probe-results.md`

**Checkpoint**: T004-T008 outputs land in `probe-results.md`.

---

## Phase 3: User Story 1 — POS family transfer (Priority: P1) 🎯 MVP

**Goal**: Confirm the five COMPLETE callbacks (gram_categories, inflection_features, inflection_classes, stem_names, exception_features) thread through the leaf-dispatch loop end-to-end with GOLD inviolability and identity_remap fallback.

**Independent Test**: Quickstart Scenario A's POS / inflection-features / inflection-classes / stem-names / exception-features sub-steps.

- [ ] T009 [US1] Read [Lib/categories.py](../../src/gramtrans/Lib/categories.py) entries for `gram_categories`, `inflection_features`, `inflection_classes`, `stem_names`, `exception_features`; confirm each has all 5 callbacks registered (no NotImplementedError) and document the registry shape in `probe-results.md` under "Phase 3b reuse audit"
- [ ] T010 [US1] Verify the existing Phase 0 unit suite still passes with the T003 dispatch-tuple extension in place: `python -m pytest tests/unit/test_categories.py tests/unit/test_categories_pos.py -q` (or whichever files cover the five COMPLETE callbacks). 0 regressions expected.
- [ ] T011 [P] [US1] Integration test in `tests/integration/test_phase3b_inflection_e2e.py::test_us1_pos_family_round_trip` — fake-LCM-surface run of all five COMPLETE callbacks under leaf dispatch, asserting per-category `added` counts and GOLD `Skip(GOLD_INVIOLABLE)` for catalog-backed POSes
- [ ] T012 [P] [US1] Integration test `test_us1_identity_remap_fallback` — factory rejects `Create(Guid)`; assert `report.identity_remap[src_guid] == new_guid` and the action completes
- [ ] T013 [US1] Live MCP Scenario A.1 (POS-family sub-run): drive `MainFunction` with only US1 categories ticked, source = Ejagham Mini, target = Ejagham Full GT-Test; log per-category counts to `verification-log.md`

**Checkpoint**: US1 ships. The five COMPLETE callbacks are dispatched and validated end-to-end. No code changes to the callbacks themselves; this story is wiring + verification.

---

## Phase 4: User Story 2 — Custom Fields (Priority: P1)

**Goal**: Custom-field definitions land in target before Phase 3c LexEntries reference them.

**Independent Test**: Quickstart Scenario A's custom-fields sub-step.

- [ ] T014 [P] [US2] Implement `custom_fields_enumerate_source` in `src/gramtrans/Lib/categories.py` per contracts/custom-field-creation.md — walks `project.Cache.MetaDataCacheAccessor`, filters `IsCustom(flid)`, yields `CustomFieldRecord(class_id, name, type, help, label_override, list_id)` dataclass (define dataclass in same file)
- [ ] T015 [P] [US2] Implement `custom_fields_dependencies` (returns `()`) and `custom_fields_required_writing_systems` (yields WS codes from help + label_override multistrings) in `src/gramtrans/Lib/categories.py`
- [ ] T016 [US2] Implement `custom_fields_plan_action` in `src/gramtrans/Lib/categories.py` — target-MDC lookup by `(class_id, name)`; already-synced returns None; type mismatch on same identity emits `Skip(IDENTITY_COLLISION)` per contracts/custom-field-creation.md; else PlannedAction with payload=record
- [ ] T017 [US2] Implement `custom_fields_execute_action` in `src/gramtrans/Lib/categories.py` — calls `tgt_mdc.AddCustomField(class_name, field_name, field_type, list_root_guid)`; raises `RuntimeError` on `flid == 0`; applies help + label multistrings via `SetMultiStringAlt` if available (probe in T005 confirms)
- [ ] T018 [US2] Unit tests in `tests/unit/test_categories_custom_fields.py`: enumerate filters IsCustom only; plan_action sync detection by (class_id, name); execute fail-loud on flid=0; multistring help text survives transfer
- [ ] T019 [US2] Integration test `test_us2_custom_fields_round_trip` in `tests/integration/test_phase3b_inflection_e2e.py` — Scenario A's custom-fields sub-step against fake LCM with 3 custom fields
- [ ] T020 [US2] Live MCP Scenario A.2 (custom-fields sub-run): log results to `verification-log.md`

**Checkpoint**: US2 ships. Custom-field definitions transfer before any Phase 3c entry import would reference them.

---

## Phase 5: User Story 3 — Variant Types + Complex Form Types + Semantic Domains (Priority: P2)

**Goal**: The three remaining Phase 3b categories — variant types (with feature-constraint dependency closure per FR-327), complex form types (leaf), and semantic domains (with GOLD catalog skip per FR-326).

**Independent Test**: Quickstart Scenarios A's variant/complex/semantic sub-steps + Scenario C dependency closure.

### Variant Types (#7)

- [ ] T021 [P] [US3] Implement `variant_types_enumerate_source` in `src/gramtrans/Lib/categories.py` — recursive walk of `project.LexDb.VariantEntryTypesOA.PossibilitiesOS` + `SubPossibilitiesOS`
- [ ] T022 [US3] Implement `variant_types_dependencies` in `src/gramtrans/Lib/categories.py` per FR-327 — walks `src_obj.InflFeatsOS`, yields `(INFLECTION_FEATURES, fs_sym_feat_val_guid)` per constraint
- [ ] T023 [US3] Implement `variant_types_plan_action` and `variant_types_execute_action` in `src/gramtrans/Lib/categories.py` — GOLD via `_is_gold`, hierarchical placement via `parent_guid` payload, `_create_with_guid` + `_safe_add_to_owner` into parent's `SubPossibilitiesOS` or root `PossibilitiesOS`; defer `InflFeatsOS` wiring to a post-execute step inside the same callback
- [ ] T024 [US3] Unit tests in `tests/unit/test_categories_variant_types.py`: enumerate walks recursively, dependencies yields feature-value GUIDs when InflFeatsOS non-empty, GOLD-skip via `_is_gold`, identity_remap fallback

### Complex Form Types (#8)

- [ ] T025 [P] [US3] Implement `complex_form_types_enumerate_source` in `src/gramtrans/Lib/categories.py` — recursive walk of `project.LexDb.ComplexEntryTypesOA.PossibilitiesOS`
- [ ] T026 [US3] Implement `complex_form_types_dependencies` (returns `()`), `complex_form_types_plan_action`, and `complex_form_types_execute_action` in `src/gramtrans/Lib/categories.py` — same shape as variant_types minus the dependency callback
- [ ] T027 [US3] Unit tests in `tests/unit/test_categories_complex_form_types.py`: recursive walk, GOLD-skip, hierarchical placement, identity_remap fallback

### Semantic Domains (#9)

- [ ] T028 [P] [US3] Implement `semantic_domains_enumerate_source` in `src/gramtrans/Lib/categories.py` — recursive walk of `project.LangProject.SemanticDomainListOA.PossibilitiesOS` + `SubPossibilitiesOS`
- [ ] T029 [US3] Implement `semantic_domains_dependencies` (returns `()`), `semantic_domains_plan_action`, and `semantic_domains_execute_action` in `src/gramtrans/Lib/categories.py` — FR-326 GOLD skip via `_is_gold` (sieves the ~1700-entry FW catalog), hierarchical placement under existing-in-target parent or root
- [ ] T030 [US3] Unit tests in `tests/unit/test_categories_semantic_domains.py`: GOLD skip filters standard catalog entries, custom domains land with source GUIDs, recursive parent placement
- [ ] T031 [US3] Integration test `test_us3_variant_complex_semantic_round_trip` in `tests/integration/test_phase3b_inflection_e2e.py` — Scenario A's three sub-steps end-to-end
- [ ] T032 [US3] Integration test `test_us3_variant_dependency_unresolved_skip` — variant type referencing a feature value not in target nor in-plan emits `Skip(DEPENDENCY_UNRESOLVED)` per FR-327
- [ ] T033 [US3] Live MCP Scenario A.3 (variant/complex/semantic sub-run) + Scenario C (feature-constraint dependency): log to `verification-log.md`

**Checkpoint**: US3 ships. The three remaining Phase 3b categories transfer with FR-326 GOLD respect and FR-327 dependency closure.

---

## Phase 6: User Story 4 — Empty-source UX (Priority: P3)

**Goal**: All nine Phase 3b categories inherit FR-308 empty-source UX. Selected-but-empty categories emit `[skip] no items in source for X` lines in `render_text_summary`.

**Independent Test**: Quickstart Scenario D.

- [ ] T034 [P] [US4] Verify each of the 4 new `enumerate_source` callbacks (custom_fields, variant_types, complex_form_types, semantic_domains) returns `()` cleanly when source collection empty; add guards if LCM accessors raise on empty containers
- [ ] T035 [US4] Unit tests in `tests/unit/test_categories_phase3b_empty_source.py` — each of the 4 new categories returns `()` from enumerate_source and produces zero plan actions on empty source
- [ ] T036 [US4] Integration test `test_us4_phase3b_all_empty_source` in `tests/integration/test_phase3b_inflection_e2e.py` — all 9 categories selected against an empty-of-inflection-content source; assert 9 `[skip] no items in source for X` lines in `render_text_summary(report)`

**Checkpoint**: US4 ships. FR-308 inherited cleanly.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T037 [P] Run full unit suite: `python -m pytest tests/unit -q`; confirm 305 prior tests + ~35 new Phase 3b tests all green (target ~340)
- [ ] T038 [P] Run integration suite: `python -m pytest tests/integration -q`; all Phase 3b e2e tests green; Phase 3a + Phase 0/1/2 still green
- [ ] T039 Live MCP Scenarios B (overwrite re-run) and E (Phase 0/1/2/3a regression) against Ejagham Mini → Ejagham Full GT-Test; log to `verification-log.md`
- [ ] T040 Update `STATUS.md` to mark Phase 3b complete and queue Phase 3c (memo steps 14-18: affixes, ad-hoc / compound rules, slots, affix templates, stems)
- [ ] T041 Commit in topic-aligned increments: T001-T008 (setup + foundational probes), then one commit per US (US1 wiring, US2 custom_fields, US3 variant+complex+semantic, US4 empty-UX), then polish

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

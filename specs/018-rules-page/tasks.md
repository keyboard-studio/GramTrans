# Tasks: Rules Page — Ad Hoc & Compound Rules (Model-B Block + Engine)

**Feature**: 018-rules-page | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Ground truth**: [probe-results.md](./probe-results.md) — FLExTools MCP probes.
**Do not guess LCM API.** Confirm open items (R3a/R4a) with a live MCP `run_module`
probe before wiring. Reuse the `phonological_rules` engine pattern in
`src/gramtrans/Lib/categories.py`.

**Tests**: requested (plan Project Structure lists unit + integration suites).

---

## Phase 1: Setup

- [ ] T001 Confirm `GrammarCategory.ADHOC_COMPOUND_RULES` plumbing is live (registry, preview, transfer, wizard imports) with a grep sanity check across `src/gramtrans/Lib/{models.py,categories.py,preview.py,transfer.py,ui/selection_wizard.py,ui/main_window.py}`; record findings (no code change expected).
- [ ] T002 [P] Live MCP probe (read-only) via `flextools_run_module` against Ejagham Mini to confirm research open items R3a (compound base member-MSA field names `LeftMsaOA`/`RightMsaOA` + `PartOfSpeechRA` path) and R4a (MSA factory/ownership for owned `IMoStemMsa`), and confirm `IMoExoCompoundFactory` exists; append confirmed facts to [probe-results.md](./probe-results.md).

---

## Phase 2: Foundational (blocking prerequisites)

- [ ] T003 Add a shared per-subclass dispatch helper `_rule_subclass_info(obj)` in `src/gramtrans/Lib/categories.py` returning `(class_name, factory_iface, ref_spec)` for the five classes and raising loudly on any other ClassName (FR-006, SC-008).
- [ ] T004 Add `_rules_enumerate_all(source)` walker in `src/gramtrans/Lib/categories.py` that yields every prohibition from `MorphologicalDataOA.AdhocCoProhibitionsOS` (recursing `IMoAdhocProhibGr.MembersOC`) and every rule from `CompoundRulesOS`, using `getattr`/cast guards.

**Checkpoint**: dispatch + enumeration helpers exist and are unit-importable before story work.

---

## Phase 3: User Story 1 — Engine transfers ad hoc & compound rules by subclass (P1)

**Goal**: The five `adhoc_compound_rules_*` callbacks create the correct LCM subclass per source rule, GUID-preserved, references wired, idempotent.

**Independent test**: Source with one of each subclass → engine plan+execute against fresh target → one matching-subclass object each, refs resolved; re-run all Skip (SC-001/002); unknown subclass fails loud (SC-008).

- [ ] T005 [US1] Implement `adhoc_compound_rules_enumerate_source(context, selection)` in `src/gramtrans/Lib/categories.py` using `_rules_enumerate_all` + `leaf_item_picks` filter (absent key ⇒ all; `_guid_str_from` both sides); exclude GOLD-shipped rules (Constitution I). Replaces the `NotImplementedError("Phase 3c T056")`.
- [ ] T006 [US1] Implement `adhoc_compound_rules_required_writing_systems(piece)` in `src/gramtrans/Lib/categories.py` returning `()` (parity with `phonological_rules_*`). Replaces its `NotImplementedError`.
- [ ] T007 [US1] Implement `adhoc_compound_rules_plan_action(piece, context, ws_mapping)` in `src/gramtrans/Lib/categories.py` via `_phonology_simple_plan(piece, context, GrammarCategory.ADHOC_COMPOUND_RULES, ops_attr, label)` (GUID-first ALREADY_PRESENT_BY_GUID skip / PlannedAction). Replaces its `NotImplementedError`.
- [ ] T008 [US1] Implement `adhoc_compound_rules_execute_action(action, context, ws_mapping, tag)` in `src/gramtrans/Lib/categories.py`: locate source by `action.source_guid`; dispatch via `_rule_subclass_info`; `_create_with_guid(factory, owner, src_guid, target)` (owner = OS or parent group `MembersOC`); `GetSyncableProperties`→`ApplySyncableProperties(new, props, ws_map=ws_mapping)`; then `apply_carrier_b`. Raise on unhandled subclass. Replaces its `NotImplementedError`.
- [ ] T009 [US1] Add manual reference wiring in `adhoc_compound_rules_execute_action` for adhoc subclasses: resolve `FirstAllomorphRA` / `RestOfAllosRS` / `AllomorphsRS` (`IMoForm`) and `FirstMorphemeRA` / `RestOfMorphsRS` / `MorphemesRS` (`IMoMorphSynAnalysis`) against target by normalized GUID, preserving source order.
- [ ] T010 [US1] Add compound member/result MSA handling in `adhoc_compound_rules_execute_action`: create owned `IMoStemMsa` member/result children (endo `OverridingMsaOA` + `HeadLast`; exo `ToMsaOA`; base left/right members per confirmed R3a) with GUID preserved, and wire each MSA `PartOfSpeechRA` to the resolved target POS.
- [ ] T011 [US1] Handle `IMoAdhocProhibGr` grouping nodes in `adhoc_compound_rules_execute_action`: create the group only if ≥1 kept child, and re-parent each kept child under the created group's `MembersOC`; deselected children are not created (edge case + FR-004).
- [ ] T012 [P] [US1] Unit test `tests/unit/test_rules_plan_dispatch.py`: fake-handle GUID-first skip/add per subclass; idempotent re-plan; unknown subclass raises loudly.
- [ ] T013 [P] [US1] Integration test `tests/integration/test_rules_live.py`: MCP Ejagham source→fresh target; all five subclasses created, GUID-preserved, refs wired; re-run idempotent (SC-001/002/008).

**Checkpoint**: engine transfers every subclass correctly and idempotently, standalone (no UI).

---

## Phase 4: User Story 2 + 3 — Whole-block transfer, toggle off, per-item trim (P1)

**Goal**: Rules page renders both categories all-preselected with counts + status; whole-block toggle and per-item deselect feed the plan.

**Independent test**: Open page → both categories preselected with correct counts (SC-003/004); toggle off → zero rules; back on, deselect one → all but that one (SC-005).

- [ ] T014 [US2] Add rule inventory dataclasses (`RuleRow`, `RuleCategoryGroup`, `RulesInventory`) per [data-model.md](./data-model.md) in `src/gramtrans/Lib/selection.py`.
- [ ] T015 [US2] Implement `build_rules_inventory(source, target=None)` in `src/gramtrans/Lib/selection.py`: walk both collections (recurse grouping nodes), preselect all, compute per-row target-status via the shared 008/009/010 helper (blank when no target), set `has_any`; normalize GUIDs via `_guid_str_from`.
- [ ] T016 [US2] Implement `adhoc_compound_rules_dependencies(piece)` in `src/gramtrans/Lib/categories.py`: per-subclass member-reference GUIDs (allos; morphemes; compound owned-MSA `PartOfSpeechRA` POS; group ⇒ union of children), cast/`getattr`-guarded. Replaces the current `return ()` stub.
- [ ] T017 [US3] Add `_PageRules` QWizardPage in `src/gramtrans/Lib/ui/selection_wizard.py` (mirror `_PagePhonology`/`_PageCustomFields`): two grouped tristate trees + whole-block toggle; all rows checked; empty category renders empty (FR-011); no ADD_NEW/MERGE/OVERWRITE control (FR-016).
- [ ] T018 [US3] Register `_PageRules` in the wizard: instantiate `self._page_rules`, `addPage` immediately before `self._page_finish`, add named accessor `page_rules()` (P-1 pattern, no literal indices) in `src/gramtrans/Lib/ui/selection_wizard.py`.
- [ ] T019 [US3] Collapse checked rows into `Selection.leaf_item_picks[ADHOC_COMPOUND_RULES]` on page-leave and merge into the plan build in `_PagePreview` (absent/full set for untouched ⇒ SC-004; empty ⇒ SC-005) in `src/gramtrans/Lib/ui/selection_wizard.py`.
- [ ] T020 [P] [US2] Unit test `tests/unit/test_rules_inventory.py`: 2 categories, counts, preselect-all, target status, empty category, grouping-node structure represented.
- [ ] T021 [P] [US3] Unit test `tests/unit/test_rules_leaf_item_picks.py`: enumerate filter subset present ⇒ subset, absent ⇒ all, GUID normalized both sides, grouping recursion.
- [ ] T022 [P] [US3] Extend `tests/unit/test_wizard_page_order.py`: `page_rules()` returns `_PageRules` in post-insertion order.

**Checkpoint**: page transfers the whole block, toggles off, and trims individual rules end-to-end.

---

## Phase 5: User Story 4 — Missing member references reported, never silently broken (P1)

**Goal**: A kept rule whose member ref is deselected AND target-absent produces one aggregated warning + a single Move confirmation.

**Independent test**: Keep a compound rule whose left-member POS was deselected and is absent from target → Preview shows one aggregated warning naming the rule; Move pops one consolidated confirmation (SC-006).

- [ ] T023 [US4] Add rules missing-reference detection in `src/gramtrans/Lib/preview.py`: for each kept rule, if a member ref (allomorph/morpheme/POS) is neither in-flight nor in target by GUID, emit one entry-centric `MissingRefWarning` (data-model shape); no warning when it resolves.
- [ ] T024 [US4] Route rules `MissingRefWarning`s into the shared aggregated Move gate consumed by `_PageFinish` (one combined confirmation across pages, FR-015) in `src/gramtrans/Lib/ui/selection_wizard.py`.
- [ ] T025 [P] [US4] Unit test `tests/unit/test_rules_missing_ref.py`: kept rule + deselected/absent member ⇒ exactly one aggregated warning; no warning when ref resolves; aggregation across multiple rules.

**Checkpoint**: referential completeness holds; no silent broken transfers.

---

## Phase 6: User Story 5 — Target-presence status column (P2)

**Goal**: Every rule row shows NEW / IN TARGET / SIMILAR; blank when no target.

**Independent test**: source=target ⇒ all IN TARGET; fresh target ⇒ all NEW; no target ⇒ blank, no crash (SC-007).

- [ ] T026 [US5] Verify/finish per-row `target_status` rendering in `_PageRules` (`src/gramtrans/Lib/ui/selection_wizard.py`) using the status set by `build_rules_inventory`; blank-and-no-crash when target unbound.
- [ ] T027 [P] [US5] Add target-status assertions to `tests/unit/test_rules_inventory.py` (source=target ⇒ IN TARGET; fresh ⇒ NEW; None target ⇒ blank).

---

## Phase 7: Polish & Cross-Cutting

- [ ] T028 [P] Run full unit suite (`pytest tests/unit/test_rules_*.py tests/unit/test_wizard_page_order.py`) and the live integration test; attach pre/post Import Residue artifacts per Constitution verification gate.
- [ ] T029 [P] Confirm no `NotImplementedError("Phase 3c ...")` remains for `adhoc_compound_rules_*` in `src/gramtrans/Lib/categories.py`; update the module comment header (lines ~1793-1815) to reflect the shipped 018 implementation.
- [ ] T030 Update [STATUS.md](../../STATUS.md) handoff with 018 completion + verification evidence.

---

## Dependencies & Execution Order

- **Setup (T001-T002)** → **Foundational (T003-T004)** → user stories.
- **US1 (T005-T013)** is the MVP and unblocks everything (page has nothing to feed without it). T009/T010/T011 depend on T008; T010 depends on T002 (R3a/R4a confirmation).
- **US2+US3 (T014-T022)** depend on US1 (engine) + Foundational; T016 (dependencies) needed before US4.
- **US4 (T023-T025)** depends on US2/US3 (selection) + T016.
- **US5 (T026-T027)** depends on US2 (builder status).
- **Polish (T028-T030)** last.

## Parallel Opportunities

- T012 ∥ T013 (US1 tests, different files).
- T020 ∥ T021 ∥ T022 (US2/US3 tests).
- Within implementation, engine (categories.py) and page (selection_wizard.py) tasks touch different files but share the `leaf_item_picks` contract — sequence T005-T011 before T017-T019 to keep the contract stable.

## MVP Scope

**User Story 1 (T001-T013)** — the engine — is the minimum shippable slice: it transfers all five subclasses correctly and idempotently, verifiable without any UI.

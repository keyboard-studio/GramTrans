---

description: "Phase 2 — Interactive Merge tasks"

---

# Tasks: Phase 2 — Interactive Merge

**Input**: Design documents from `/specs/003-phase2-interactive-merge/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Organization**: Tasks are grouped by user story (US1–US4 from [spec.md](spec.md)) so each story is independently implementable and testable. Tests are organized into the same story phase as the implementation they cover.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 / US2 / US3 / US4 — maps to a spec.md user story
- File paths are absolute relative to repository root

## Path Conventions

- Source: `src/gramtrans/Lib/` (FLExTrans-style flat helpers)
- Tests: `tests/unit/` (pytest), `tests/integration/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the Phase 2 data-model types and selection flag without touching any executor or UI code yet. Phase 1 is intentionally tiny — most of the work happens in foundational + per-story phases.

- [x] T001 [P] Add `MergeResolution` and `WSChoice` enums to `src/gramtrans/Lib/models.py` per [data-model.md](data-model.md) E10 / E15
- [x] T002 [P] Add `INTERACTIVE_SKIP` and `UNMAPPED_WS_USER_CHOSE_SKIP` variants to `SkipReason` enum in `src/gramtrans/Lib/models.py`
- [x] T003 Add `Selection.interactive_merge: bool = False` and `Selection.ws_mapping_choices: tuple = ()` fields (with validation in `__post_init__`) in `src/gramtrans/Lib/models.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add the Phase 2 entity dataclasses, residue-segment plumbing, and `UserCancelled` exception. These types and the residue extension are used by every user story; nothing else can land before they exist.

**⚠️ CRITICAL**: Stories US1–US4 cannot begin until this phase is complete.

- [x] T004 [P] Add `MergeDecision` dataclass + validation in `src/gramtrans/Lib/models.py` per [data-model.md](data-model.md) E11
- [x] T005 [P] Add `MergeDecisionLog` dataclass + `to_json()` / `from_json()` in `src/gramtrans/Lib/models.py` per E12
- [x] T006 [P] Add `ConflictPrompt` dataclass in `src/gramtrans/Lib/models.py` per E13
- [x] T007 [P] Add `WSMismatch` dataclass in `src/gramtrans/Lib/models.py` per E14
- [x] T008 [P] Add `WSMappingChoice` dataclass + validation in `src/gramtrans/Lib/models.py` per E15
- [x] T009 [P] Add `InteractiveSession` dataclass in `src/gramtrans/Lib/models.py` per E16
- [x] T010 Add `RunPlan.conflicts: tuple = ()` field in `src/gramtrans/Lib/models.py` per E4 modification (depends on T006)
- [x] T011 Create `src/gramtrans/Lib/conflict.py` exception module: define `class UserCancelled(Exception)` and the `ConflictResolver` Protocol per [contracts/conflict-prompt.md](contracts/conflict-prompt.md)
- [x] T012 Extend `ImportResidueTag` in `src/gramtrans/Lib/residue.py` with `merge_b64: Optional[str] = None`, widen `serialize()` to emit the optional `merge=<b64>` segment, and widen `parse()` to accept 4/5/6 segments with prefix-based recognition per [contracts/residue-merge-segment.md](contracts/residue-merge-segment.md) (depends on T005)
- [x] T013 Add `ImportResidueTag.with_merge_log(log)` and `ImportResidueTag.decode_merge_log()` methods in `src/gramtrans/Lib/residue.py` (depends on T012)
- [x] T014 [P] Add unit tests for the 6-segment residue round-trip in `tests/unit/test_residue_merge_segment.py`: 4-seg, 5-seg (snap only), 5-seg (merge only), 6-seg (snap+merge), corrupted base64, malformed JSON, ordering enforcement (`merge=` must follow `snap=`) (depends on T013)
- [x] T015 [P] Add unit tests for `MergeDecisionLog.to_json` / `from_json` round-trip in `tests/unit/test_merge_log_round_trip.py` (depends on T005)
- [x] T016 Add `CategoryReport` counter fields (`interactive_resolved`, `interactive_skipped`, `ws_mapped`, `ws_created`, `ws_skipped`) in `src/gramtrans/Lib/models.py` per E6 modification

**Checkpoint**: All Phase 2 types and residue plumbing exist. 168 Phase 1 tests still green. New tests T014/T015 green.

---

## Phase 3: User Story 1 — Per-Conflict Merge Prompt (Priority: P1) 🎯 MVP

**Goal**: Replace the Phase 1 silent FR-109 "source wins" policy with a per-field interactive prompt offering {take-source, keep-target, merge, skip, edit-custom} on overwrite-candidate objects. This is the MVP for Phase 2: without it, Phase 1 silently destroys target-side annotations.

**Independent Test**: Set up a target entry with a non-empty Comment that differs from the source's. Run `transfer.execute()` with `Selection.interactive_merge=True` and a `FakeConflictResolver` injected. Verify the prompt list, the user's choice is applied, and the residue tag carries the `merge=` segment. Quickstart Scenario B.

- [x] T017 [P] [US1] Implement `Lib/conflict.py.detect_conflicts(src_props, tgt_pre_props, target_guid, target_class_name, prior_log=None) -> tuple[ConflictPrompt, ...]` per [contracts/conflict-prompt.md](contracts/conflict-prompt.md) — iterate intersection of keys, emit prompts for non-equal values, suppress identical-valued pairs (FR-216), determine `merge_eligible` by type
- [x] T018 [P] [US1] Implement deterministic merge helper `Lib/conflict.py._deterministic_merge(left, right, run_id) -> object` per [research.md](research.md) R4: strings get `<left>\n--- merged GT-<run_id> ---\n<right>`, multistrings recurse per WS, sets union, scalars not eligible
- [x] T019 [P] [US1] Add unit tests for `detect_conflicts` in `tests/unit/test_conflict_detect.py`: identical-value suppression, missing-key suppression, multistring conflict detection, scalar `merge_eligible=False`, prior_log threading
- [x] T020 [P] [US1] Add unit tests for `_deterministic_merge` in `tests/unit/test_conflict_merge_semantics.py`: string concat with separator, set union, scalar rejection (raises), idempotency-on-already-merged check
- [x] T021 [US1] Implement `Lib/transfer.py._apply_merge_decisions(src_props, decisions, tgt_pre_props, run_id) -> tuple[dict, list[Skip]]` per [research.md](research.md) R3: filter `src_props` per resolution, return modified dict + any `Skip(INTERACTIVE_SKIP)` records (depends on T018)
- [x] T022 [US1] Add unit tests for `_apply_merge_decisions` in `tests/unit/test_conflict_resolve.py` covering all five resolutions (TAKE_SOURCE / KEEP_TARGET / MERGE / SKIP / EDIT_CUSTOM) and the Skip emission for SKIP
- [x] T023 [US1] Modify `Lib/preview.py.build_run_plan` to call `detect_conflicts` inside each overwrite branch (POS, LexEntry, LexSense, Allomorph) when `selection.interactive_merge=True`; accumulate prompts and attach to `RunPlan.conflicts` (depends on T017, T010)
- [x] T024 [US1] Modify `Lib/transfer.py._execute_overwrite` to invoke `_apply_merge_decisions` before each `ApplySyncableProperties` call when `RunPlan.conflicts` is non-empty; thread the per-object `MergeDecisionLog` from `InteractiveSession` (depends on T021)
- [x] T025 [US1] Modify `Lib/transfer.py._execute_overwrite` to call `tag.with_merge_log(log)` before `apply_residue` for each touched object; verify the residue parse round-trip captures the log (depends on T013, T024)
- [x] T026 [US1] Create `Lib/ui/conflict_dialog.py.ConflictDialog` (PyQt5 `QDialog`) implementing the `ConflictResolver` Protocol; renders side-by-side `left_value` / `right_value` with five resolution buttons; emits `MergeDecision` per prompt; raises `UserCancelled` on dismiss
- [x] T027 [US1] Wire `gramtrans.py.MainFunction` to: collect prompts from the built plan, instantiate `ConflictDialog`, call `resolver.resolve(prompts)`, fold the returned tuple of `MergeDecision`s into an `InteractiveSession`, pass to `transfer.execute(...)` (depends on T024, T026)
- [x] T028 [US1] Add `FakeConflictResolver` test double in `tests/unit/conftest.py` returning a fixture-driven decision list per the contract
- [ ] T029 [US1] Add integration test `tests/integration/test_phase2_e2e.py::test_us1_per_conflict_prompt` exercising Scenario B from quickstart.md with `FakeConflictResolver`; assert residue tag carries `merge=` and decision survives parse round-trip (depends on T028, T025)
- [x] T030 [US1] Update `Lib/report.py.RunReport.build_from_plan` to increment `interactive_resolved` / `interactive_skipped` counters per `MergeDecisionLog` entries; render in `render_text_summary` when non-zero (depends on T016)

**Checkpoint**: US1 ships in isolation. A linguist can now answer per-conflict prompts; the residue tag persists the decisions. Scenario A regression (Phase 1 untouched when gate off) must also pass.

---

## Phase 4: User Story 2 — Writing-System Mapping Wizard (Priority: P1)

**Goal**: Surface every source-WS-not-in-target as an explicit user choice {map, create, skip} BEFORE plan build. Eliminates Phase 0's silent `unmapped_ws` skips.

**Independent Test**: Fabricate a source WS absent in target. Run `MainFunction` with a `FakeWSResolver` injected. Verify the wizard fires, the user's choice populates `WSMapping`, and downstream transfer respects it. Quickstart Scenario D.

- [x] T031 [P] [US2] Create `src/gramtrans/Lib/ws_mapping.py.detect_ws_mismatches(source, target) -> tuple[WSMismatch, ...]` per [contracts/ws-wizard.md](contracts/ws-wizard.md) — enumerates source vs target WSes via `project.WritingSystems.GetAll()`, sorts `target_ws_candidates` by similarity heuristic
- [x] T032 [P] [US2] Add unit tests for `detect_ws_mismatches` in `tests/unit/test_ws_mapping_detect.py` with fake source/target projects: zero mismatches, single mismatch, multiple, candidate sort-order assertion
- [x] T033 [P] [US2] Define `WSResolver` Protocol in `src/gramtrans/Lib/ws_mapping.py` per the contract
- [x] T034 [US2] Create `Lib/ui/ws_wizard.py.WSWizard` (PyQt5 `QWizard`) implementing the `WSResolver` Protocol; one page per mismatch with three radio choices and a target-WS dropdown for MAP; "Finish" step applies CREATE choices to the target project before returning
- [x] T035 [US2] Wire `gramtrans.py.MainFunction` to call `detect_ws_mismatches` before plan build; if non-empty, instantiate `WSWizard`, call `resolver.resolve(mismatches)`, fold the result into `Selection.ws_mapping_choices` and the existing `WSMapping.entries` (depends on T034, T003)
- [x] T036 [US2] Modify `Lib/preview.py.build_run_plan` to recognize `WSMappingChoice(SKIP)` entries and emit `Skip(UNMAPPED_WS_USER_CHOSE_SKIP)` for objects whose only WS-keyed content is in a skipped WS (depends on T035)
- [x] T037 [US2] Add `FakeWSResolver` test double in `tests/unit/conftest.py` returning a fixture-driven choice list per the contract
- [ ] T038 [US2] Add integration test `tests/integration/test_phase2_e2e.py::test_us2_ws_wizard` exercising Scenario D with `FakeWSResolver` choosing MAP for one fabricated mismatch
- [x] T039 [US2] Update `Lib/report.py.RunReport.build_from_plan` to increment `ws_mapped` / `ws_created` / `ws_skipped` counters per `Selection.ws_mapping_choices`; render in `render_text_summary` (depends on T016)

**Checkpoint**: US2 ships in isolation. The wizard fires before plan build; WS mismatches surface explicitly. US1's per-conflict path still works regardless of US2 path.

---

## Phase 5: User Story 3 — Prior-Run Decision Recall (Priority: P2)

**Goal**: A re-run pre-fills every conflict prompt with the prior run's decision so the linguist can accept-all rather than re-decide.

**Independent Test**: Run US1's scenario, then re-run with no source-side changes. Verify every prompt's `prior_decision` is set and accepting all yields a no-op run. Quickstart Scenario C.

- [x] T040 [US3] Implement `Lib/conflict.py.load_prior_decision(tgt_object, field_name, ws, class_uses_carrier_a_table) -> Optional[MergeDecision]` per [research.md](research.md) R7: read the residue tag via `apply_residue`-inverse, call `decode_merge_log()`, look up the field name (depends on T013)
- [x] T041 [US3] Modify `Lib/conflict.py.detect_conflicts` to accept an optional `prior_log: MergeDecisionLog | None` and attach matching entries to `ConflictPrompt.prior_decision` (depends on T017, T040)
- [x] T042 [US3] Modify `Lib/preview.py.build_run_plan` to call `load_prior_decision` for each overwrite-candidate object and pass the resulting `MergeDecisionLog` (built from per-field decisions) into `detect_conflicts` (depends on T040, T023)
- [x] T043 [US3] Modify `Lib/ui/conflict_dialog.py.ConflictDialog` to pre-select the `prior_decision.resolution` radio when present and display "from run GT-<id>" annotation (depends on T026)
- [ ] T044 [US3] Modify `MergeDecision` construction in the dialog: when the user accepts a pre-filled prior decision unchanged, propagate the original `prior_run_id` (mark carried-over per FR-208) (depends on T043)
- [x] T045 [US3] Add unit tests for `load_prior_decision` in `tests/unit/test_conflict_prior_recall.py`: present-and-valid, absent, corrupted-tag (returns None per FR-215), wrong-field-name
- [ ] T046 [US3] Add integration test `tests/integration/test_phase2_e2e.py::test_us3_prior_recall` exercising Scenario C: run US1 scenario, capture residue, re-run with same FakeConflictResolver, assert `prompts[0].prior_decision is not None` (depends on T029, T042)
- [ ] T047 [US3] Update `Lib/report.py.RunReport` to distinguish "carried-over" decisions (prior_run_id set) from fresh interactive resolutions in the report rendering

**Checkpoint**: US3 ships. Re-runs are now no-op confirmations rather than re-decision exercises. US1 and US2 paths continue to work.

---

## Phase 6: User Story 4 — Batched Resolution Within One Move (Priority: P3)

**Goal**: Collect all prompt answers before any LCM write; allow back-navigation in the wizard; single "apply all" commit point.

**Independent Test**: Trigger a run with 5+ conflicts; navigate back-and-forward in the dialog without losing answers; confirm a single `transfer.execute()` call performs all resolutions inside the existing UndoableUnitOfWork.

- [ ] T048 [US4] Modify `Lib/ui/conflict_dialog.py.ConflictDialog` to render as a single multi-prompt wizard (QStackedWidget or paged QDialog) with Back / Next / Finish navigation, preserving per-page state across navigation
- [ ] T049 [US4] Add cancellation atomicity test `tests/integration/test_phase2_e2e.py::test_us4_cancel_atomicity` exercising Scenario E: snapshot file hash, raise `UserCancelled` mid-wizard, verify post-run hash matches (depends on T028)
- [ ] T050 [US4] Add navigation/back-button test `tests/unit/test_conflict_dialog_navigation.py` using `FakeConflictResolver` that simulates a back-then-edit flow; assert decision tuple reflects the edited value not the original

**Checkpoint**: US4 ships. Linguists can pause/resume/edit decisions mid-wizard without losing state. Cancel is atomic.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Run the regression suite, perform live MCP verification, and update the session handoff document.

- [x] T051 [P] Run the full unit-test suite: `python -m pytest tests/unit -q`; verify 168 Phase 1 tests + ~30 Phase 2 tests all green
- [ ] T052 [P] Run the integration suite: `python -m pytest tests/integration -q`; all Phase 2 e2e tests green
- [ ] T053 Live MCP verification of Scenarios A–E from [quickstart.md](quickstart.md) on Ejagham Mini → Ejagham Full GT-Test, with FakeResolvers for the headless probes and real PyQt dialogs for one manual end-to-end pass
- [x] T054 Update `STATUS.md` to mark Phase 2 complete and queue any deferred items (batch-apply, three-way multistring merge, etc.)
- [x] T055 Commit Phase 2 in topic-aligned increments: T001-T016 (foundations), then one commit per story (US1, US2, US3, US4), then polish

---

## Dependencies

```
Phase 1 (Setup) ──▶ Phase 2 (Foundational) ──▶ Phase 3 (US1, MVP)
                                            ├▶ Phase 4 (US2)
                                            ├▶ Phase 5 (US3)  [needs Phase 3]
                                            └▶ Phase 6 (US4)  [needs Phase 3]
                    Phase 7 (Polish) runs after all stories.
```

Story-level dependencies:
- US1: independent (MVP).
- US2: independent of US1 (WS wizard fires before plan build; orthogonal to per-conflict prompt).
- US3: depends on US1 (prior-decision recall reads what US1 wrote).
- US4: depends on US1 (batched navigation operates on US1's prompt list).

## Parallel Opportunities

- **Phase 1**: T001 and T002 in parallel (different enum sections, same file but independent edits if applied carefully — or sequence to avoid edit conflicts).
- **Phase 2**: T004–T009 are all `[P]` (independent dataclasses in the same file — sequence or use Edit with replace_all=false on distinct anchors). T014 and T015 are pure new test files, fully parallel.
- **Phase 3 (US1)**: T017 / T018 / T019 / T020 parallel — different files / independent logic. T021 depends on T018; T023 depends on T017+T010. The dialog (T026) is independent of the executor wiring (T024); both block T027.
- **Phase 4 (US2)**: T031 / T032 / T033 fully parallel — independent files. T034 depends on T033. The integration test (T038) needs T037 + T034.
- **Phase 5 (US3)**: T045 (unit tests) parallel with T040/T041 implementation; the integration test (T046) is the latest dependency.
- **Phase 6 (US4)**: T048 + T049 + T050 all touch independent code paths.

## MVP Scope

**MVP = Phases 1 + 2 + 3 (US1 only).** After MVP:
- A linguist using overwrite mode no longer silently loses target annotations.
- Per-field decisions land in the residue tag with full round-trip integrity.
- Phase 1's bit-identical behavior is preserved when `interactive_merge=False` (Scenario A).

US2 (Phase 4) is highly recommended for production use (eliminates silent WS skips) but the engine ships without it. US3/US4 are quality-of-life additions.

## Independent Test Criteria

| Story | Criterion |
|-------|-----------|
| US1 | Run with one fabricated Comment conflict; verify dialog fires, decision applies, residue gains `merge=` segment. |
| US2 | Run with one fabricated WS mismatch; verify wizard fires before plan build; choice flows through to transfer. |
| US3 | Re-run US1 scenario; verify `prior_decision` pre-fills; accepting all = no-op. |
| US4 | Navigate back-and-forth in a 5-prompt wizard; cancel mid-flow leaves target bit-identical. |

## Task Count

- **Phase 1 (Setup)**: 3 tasks
- **Phase 2 (Foundational)**: 13 tasks
- **Phase 3 (US1 / MVP)**: 14 tasks
- **Phase 4 (US2)**: 9 tasks
- **Phase 5 (US3)**: 8 tasks
- **Phase 6 (US4)**: 3 tasks
- **Phase 7 (Polish)**: 5 tasks
- **Total**: 55 tasks

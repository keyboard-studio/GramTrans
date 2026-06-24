---

description: "Phase 3c — Affixes / Stems / Templates Block tasks"

---

# Tasks: Phase 3c — Affixes / Stems / Templates Block

**Input**: Design documents from `/specs/007-affixes-stems/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (3 files), quickstart.md (all present)

**Organization**: Tasks grouped by user story (US1–US5 from [spec.md](spec.md)). Each story independently testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Parallelizable (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 / US2 / US3 / US4 / US5
- File paths absolute relative to repository root

## Path Conventions

- Source: `src/gramtrans/Lib/`
- Tests: `tests/unit/`, `tests/integration/`

---

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Add 5 new members (`AFFIXES`, `ADHOC_COMPOUND_RULES`, `SLOTS`, `AFFIX_TEMPLATES`, `STEMS`) to `GrammarCategory` enum in `src/gramtrans/Lib/models.py` per data-model.md E1 — shipped in `b1a060c` (rename commit: TEMPLATES→AFFIX_TEMPLATES, ADHOC_RULES+COMPOUND_RULES merged → ADHOC_COMPOUND_RULES, STEMS added, AFFIXES + SLOTS pre-existing)
- [X] T002 Extend `RunPlan` dataclass in `src/gramtrans/Lib/models.py` with `msa_slot_bindings: dict[Guid, list[Guid]]` and `lexentry_ref_bindings: dict[Guid, dict[str, list[Guid]]]` fields per data-model.md E11; default-factory both (supports FR-333 + FR-340)
- [X] T003 Add 5 stub registry entries (`affixes`, `adhoc_compound_rules`, `slots`, `affix_templates`, `stems`) to `LEAF_CATEGORIES` in `src/gramtrans/Lib/categories.py`, each pointing at 5 placeholder functions that raise `NotImplementedError("Phase 3c <task-id>")`; updated `test_category_registry.py` to migrate AFFIXES/SLOTS/AFFIX_TEMPLATES from HEAVY to LEAF + add STEMS to LEAF
- [X] T004 Extend `_LEAF_DISPATCH_CATEGORIES` tuple in `src/gramtrans/Lib/preview.py` AND `src/gramtrans/Lib/transfer.py` to include the 5 Phase 3c categories per contracts/category-callbacks.md wiring section; order is `AFFIXES → ADHOC_COMPOUND_RULES → SLOTS → AFFIX_TEMPLATES → STEMS` to satisfy 17.1 sub-pass timing (FR-333)

---

## Phase 2: Foundational (Blocking Prerequisites — MCP Probes)

**CRITICAL**: Stories US1–US5 cannot begin writing execute callbacks until probes complete. Probe outputs land in `specs/007-affixes-stems/probe-results.md` (created by T005).

- [ ] T005 Create `specs/007-affixes-stems/probe-results.md` skeleton (sections per R1–R11 of research.md); subsequent probe tasks append to it
- [ ] T006 [P] MCP-probe `ILexExampleSentenceFactory`, `ILexPronunciationFactory`, `ILexEtymologyFactory`, `ILexEntryRefFactory` via `flextools_get_object_api`; record `Create(Guid, owner)` availability or ServiceLocator fallback path; append to `probe-results.md`
- [ ] T007 [P] MCP-probe `MSAOperations.CreateDerivAff`, `CreateUnclassified`, `CreateStem` wrapper signatures (via `flextools_find_wrappers_for_lcm` on `IMoDerivAffMsa`, `IMoUnclassifiedAffixMsa`, `IMoStemMsa`); fall-back paths if absent; append to `probe-results.md`
- [ ] T008 [P] MCP-probe `IMoEndoCompoundFactory` and `IMoExoCompoundFactory` surface; enumerate concrete `IMoCompoundRule` subclasses; verify subclass-specific accessor names (`LeftMsaOA`, `RightMsaOA`, `ToMsaOA`, `HeadLast`); **probe the residue carrier accessor (`LiftResidue` vs `Description` multistring)** on each compound subclass so T060 ships a concrete carrier choice instead of a probe-pending branch; append to `probe-results.md`
- [ ] T009 [P] MCP-probe `IMoAdhocProhibAtomFactory` and `IMoAdhocProhibitionGrFactory` surface; verify `MembersRS` accessor on `MoAdhocProhibitionGr`; append to `probe-results.md`
- [ ] T010 [P] MCP-probe `IMoInflAffixTemplate.PrefixSlotsRS` and `SuffixSlotsRS` accessor names + collection types (RS sequence vs OS owning); verify `IPartOfSpeech.AffixSlotsOC` and `AffixTemplatesOS` accessor surface; append to `probe-results.md`
- [ ] T011 [P] MCP-probe `LangProject.MorphologicalDataOA.AdhocCoProhibitionsOC` and `CompoundRulesOS` accessors; verify owner-attach pattern; append to `probe-results.md`
- [ ] T012 [P] MCP-probe Ejagham Mini inventory: count compound rules, ad-hoc prohibitions, stem entries (by `not IsAffixType`), slots per POS, templates per POS, EntryRefs across all entries; append to `probe-results.md`

**Checkpoint**: T006–T012 outputs land in `probe-results.md`; any factory whose `Create(Guid, owner)` is unavailable is flagged for identity_remap usage per FR-303.

---

## Phase 3: User Story 1 — Affix entries with owned children (Priority: P1) 🎯 MVP

**Goal**: Transfer affix LexEntries (partitioned by `IsAffixType`) with full owned-child closure — senses, MSAs (subclass-dispatched), allomorphs (subclass-dispatched), examples, pronunciations, etymologies, entry-refs. `MSA.SlotsRC` left empty for US2's 17.1 sub-pass; `LexEntryRef.ComponentLexemesRS`/`PrimaryLexemesRS` stashed in `plan.lexentry_ref_bindings` for US3's post-pass A.

**Independent Test**: Quickstart Scenario A's `AFFIXES` sub-step against Ejagham Mini's 13 verb-affix entries — expect 13 entries + 13 senses + 13 MSAs + 20 allomorphs created with owned-child closure intact.

- [ ] T013 [US1] Implement `affixes.enumerate_source` in `src/gramtrans/Lib/categories.py` per contracts/category-callbacks.md — filter `EntriesOC` by `entry.LexemeFormOA.MorphTypeRA.IsAffixType`; entries failing closure surface to planner for skip-recording
- [ ] T014 [US1] Implement `affixes.dependencies` — yield `(POS, msa.PartOfSpeechRA.Guid)` per MSA; no MorphType edge (FW-global)
- [ ] T015 [US1] Implement `affixes.plan_action` — one PlannedAction per affix LexEntry; stash `(msa.Guid, [slot.Guid, ...])` in `plan.msa_slot_bindings` for each MSA with non-empty source `SlotsRC`; stash EntryRef-component-lexeme bindings in `plan.lexentry_ref_bindings`
- [ ] T016 [US1] Implement `_walk_lex_entry_closure` helper in `src/gramtrans/Lib/categories.py` shared between affixes and stems; walks `SensesOS` → `MorphoSyntaxAnalysesOC` → `LexemeFormOA` → `AlternateFormsOS` → `PronunciationsOS` → `EtymologyOS` → `EntryRefsOS` per data-model.md E2
- [ ] T017 [US1] Implement `_dispatch_msa_subclass` in `src/gramtrans/Lib/categories.py` — `ClassName`-based dispatch to `MSAOperations.CreateInflAff` / `CreateDerivAff` / `CreateUnclassified` per data-model.md E4; unknown subclass → `Skip(NEEDS_MANUAL)`
- [ ] T018 [US1] Implement `_dispatch_allomorph_subclass` in `src/gramtrans/Lib/categories.py` — `MoAffixAllomorph` / `MoStemAllomorph` dispatch per data-model.md E3; `identity_remap` capture for no-Guid-overload paths; unknown subclass (including `MoAffixProcess` per spec.md "Out of scope") emits `Skip(NEEDS_MANUAL)`
- [ ] T019 [US1] Implement `affixes.execute_action` — atomic owned-child write via `_walk_lex_entry_closure` + the two subclass dispatchers; MSA `SlotsRC` left empty (US2 territory)
- [ ] T020 [US1] Implement `affixes.apply_residue` — Carrier A (`LiftResidue`) on entry + senses + MSAs + allomorphs per data-model.md E9
- [ ] T021 [P] [US1] Unit test `tests/unit/test_categories_affixes.py::test_enumerate_filters_by_is_affix_type` — fixture with 2 affix + 3 stem entries; enumerate yields exactly 2
- [ ] T022 [P] [US1] Unit test `test_plan_action_stashes_msa_slot_bindings` — affix MSA with 2-slot source `SlotsRC` produces `plan.msa_slot_bindings[msa.Guid] == [slot1.Guid, slot2.Guid]`
- [ ] T023 [P] [US1] Unit test `test_plan_action_stashes_lexentry_ref_bindings` — entry with non-empty `ComponentLexemesRS` populates `plan.lexentry_ref_bindings[entry.Guid]["ComponentLexemesRS"]`
- [ ] T024 [P] [US1] Unit test `test_execute_action_creates_owned_closure` — single affix entry: assert 1 entry + 1 sense + 1 MSA + 1 lexeme-form allomorph + N alt-forms created
- [ ] T025 [P] [US1] Unit test `test_execute_action_dependency_unresolved_on_missing_lexeme_form` — entry with `LexemeFormOA is None` → `Skip(DEPENDENCY_UNRESOLVED)`; entry NOT created
- [ ] T026 [P] [US1] Unit test `test_msa_dispatch_unknown_subclass_skip` — fake MSA with `ClassName == "MoFutureSubclassMsa"` → `Skip(NEEDS_MANUAL)` per FR-341 posture extended to MSAs
- [ ] T026b [P] [US1] Unit test `test_allomorph_dispatch_affix_process_needs_manual` — source allomorph with `ClassName == "MoAffixProcess"` → `Skip(NEEDS_MANUAL)` per spec.md "Out of scope"; no allomorph created, parent entry continues with remaining allomorphs
- [ ] T027 [P] [US1] Unit test `test_phase3c_leaf_dispatch.py::test_affixes_in_dispatch_tuple` — `AFFIXES` appears in `_LEAF_DISPATCH_CATEGORIES` in both `preview.py` and `transfer.py`, before `ADHOC_COMPOUND_RULES`
- [ ] T028 [P] [US1] Integration test `tests/integration/test_phase3c_affixes_stems_e2e.py::test_us1_affix_round_trip` — fake-LCM-surface run of `AFFIXES` only, asserting 13 entries created against Ejagham-Mini-shaped fixture

**Checkpoint US1 ready**: T013–T028 complete and green. MSA `SlotsRC` is intentionally empty at this point; US2 wires it.

---

## Phase 4: User Story 2 — Slots + Affix Templates + 17.1 MSA-slot wiring (Priority: P1)

**Goal**: Create slots under target POSes; create templates with `PrefixSlotsRS`/`SuffixSlotsRS` wired; run 17.1 sub-pass as post-execute tail block on `AFFIX_TEMPLATES` executor consuming `plan.msa_slot_bindings` from US1.

**Independent Test**: Quickstart Scenario A's `SLOTS` + `AFFIX_TEMPLATES` sub-steps — expect ~25 slots + ~5 templates + ~12 MSA-slot wires (one short of total MSA count, matching Phase 0's `ro~-` unbound case).

- [ ] T029 [US2] Implement `slots.enumerate_source` + `dependencies` + `plan_action` + `execute_action` + `apply_residue` in `src/gramtrans/Lib/categories.py` per contracts/category-callbacks.md; sub-iterate `IPartOfSpeech.AffixSlotsOC` for each POS already in target; Carrier B residue on `Description`
- [ ] T030 [US2] Implement `affix_templates.enumerate_source` + `dependencies` + `plan_action` + base `execute_action` (without the 17.1 tail) + `apply_residue`; wire `PrefixSlotsRS`/`SuffixSlotsRS` in source order via target-slot GUID lookup
- [ ] T031 [US2] Implement the 17.1 sub-pass as a post-execute tail block on `affix_templates.execute_action` per contracts/msa-slot-wiring.md algorithm: iterate `plan.msa_slot_bindings`, resolve MSA via `identity_remap`, resolve each slot by GUID, write `msa.SlotsRC.Add(slot)`; emit `Skip(DEPENDENCY_UNRESOLVED)` on missing MSA or slot
- [ ] T032 [P] [US2] Unit test `tests/unit/test_categories_slots.py::test_slot_creation_under_pos` — 1 source slot under Verb POS, target has Verb POS already → 1 slot created with GUID preserved + owner attach
- [ ] T033 [P] [US2] Unit test `test_slot_collision_already_present_by_guid` — slot guid already in target → `Skip(ALREADY_PRESENT_BY_GUID)` per FR-334
- [ ] T034 [P] [US2] Unit test `tests/unit/test_categories_affix_templates.py::test_template_creation_with_slot_refs` — 1 template with 2 prefix slots + 1 suffix slot → template created + `PrefixSlotsRS`/`SuffixSlotsRS` wired in source order
- [ ] T035 [P] [US2] Unit test `test_171_basic_wiring` — 1 MSA with 1 slot binding stashed → 1 `SlotsRC` write after templates execute (per contracts/msa-slot-wiring.md test list)
- [ ] T036 [P] [US2] Unit test `test_171_multi_slot_per_msa` — 1 MSA with 3 slot bindings → 3 `SlotsRC.Add` calls in source order
- [ ] T037 [P] [US2] Unit test `test_171_unresolved_slot` — 1 MSA, 2 slots stashed, 1 slot missing in target → 1 successful Add + 1 `Skip(DEPENDENCY_UNRESOLVED)`
- [ ] T038 [P] [US2] Unit test `test_171_unresolved_msa` — 1 binding, MSA absent from target → 1 `Skip(DEPENDENCY_UNRESOLVED)` with `msa_guid={...}` detail
- [ ] T039 [P] [US2] Unit test `test_171_idempotent_rerun` — pre-wired target + same plan → 0 net writes, 0 new skips (membership check guards `Add`)
- [ ] T040 [P] [US2] Unit test `test_171_unbound_affix` — source MSA with empty `SlotsRC` → no entry in `plan.msa_slot_bindings`; MSA remains unbound (matches Phase 0 `ro~-` case)
- [ ] T040b [P] [US2] Unit test `tests/unit/test_categories_affixes.py::test_affix_overwrite_uses_phase1_path_without_category_specific_branch` — `Selection(categories={AFFIXES}, enable_overwrite=True)` over a pre-populated target flows through Phase 1's `_apply_overwrite` path; assert no Phase-3c-specific merge code executes and `Overwrite` actions emit per FR-338 / SC-302. Same pattern asserts Phase 2 `ConflictPrompt` surfacing for a conflicting-field source/target pair without Phase-3c merge code.
- [ ] T041 [P] [US2] Integration test `test_phase3c_affixes_stems_e2e.py::test_us2_slots_templates_171` — Ejagham-Mini-shaped fixture: 13 MSAs from US1, 4 slots, 1 template; assert 12 MSA-slot wires + 1 unbound MSA after AFFIX_TEMPLATES executes

**Checkpoint US2 ready**: US1 + US2 form the MVP — Phase 3c can transfer affix entries with full MSA-slot wiring against an Ejagham-Mini-shaped target without touching stems or compound rules.

---

## Phase 5: User Story 3 — Stems with semantic-domain refs and post-pass A (Priority: P2)

**Goal**: Transfer stem LexEntries (partitioned by `not IsAffixType`) with full owned-child closure; wire `MoStemMsa.StratumRA` against Phase 3a Strata; wire `sense.SemanticDomainsRC` against Phase 3b semantic domains; run post-pass A on `STEMS` executor consuming `plan.lexentry_ref_bindings` from US1 + US3.

**Independent Test**: Quickstart Scenario A's `STEMS` sub-step against Ejagham Mini's ~239 stem entries; assert all stems created with semantic-domain refs resolved and post-pass A wires complete.

- [ ] T042 [US3] Implement `stems.enumerate_source` + `dependencies` + `plan_action` + `execute_action` + `apply_residue` in `src/gramtrans/Lib/categories.py`; reuse `_walk_lex_entry_closure` (T016) + `_dispatch_msa_subclass` (T017) + `_dispatch_allomorph_subclass` (T018); filter `EntriesOC` by `not e.LexemeFormOA.MorphTypeRA.IsAffixType`
- [ ] T043 [US3] Extend `_dispatch_msa_subclass` (T017) to handle `MoStemMsa` — `MSAOperations.CreateStem(sense, pos)` per probe-results T007; wire `StratumRA` by GUID lookup to Phase 3a-transferred Strata; missing → `Skip(DEPENDENCY_UNRESOLVED)` per FR-336
- [ ] T044 [US3] Add sense-to-semantic-domain wiring in `stems.execute_action` — for each `sense.SemanticDomainsRC` entry, resolve target domain by GUID against `LangProject.SemanticDomainListOA.PossibilitiesOS`; missing → `Skip(DEPENDENCY_UNRESOLVED)` per FR-335
- [ ] T045 [US3] Implement post-pass A as a post-execute tail block on `stems.execute_action` per contracts/post-pass-a.md algorithm: iterate `plan.lexentry_ref_bindings`, resolve target entry by GUID, resolve each component lexeme via (a) `run_ctx.in_plan_entries`, (b) target-by-GUID; write RS sequence in source order; emit `Skip(DEPENDENCY_UNRESOLVED)` on unresolved
- [ ] T046 [P] [US3] Unit test `tests/unit/test_categories_stems.py::test_enumerate_filters_to_stems` — fixture with 2 affix + 3 stem entries; enumerate yields exactly 3
- [ ] T047 [P] [US3] Unit test `test_stem_msa_stratum_wiring` — stem MSA with `StratumRA` referencing a stratum already in target → wire succeeds; missing stratum → `Skip(DEPENDENCY_UNRESOLVED)`
- [ ] T048 [P] [US3] Unit test `test_sense_semantic_domain_wiring` — sense with 2 `SemanticDomainsRC` refs; 1 resolves, 1 missing → 1 Add + 1 Skip
- [ ] T049 [P] [US3] Unit test `tests/unit/test_phase3c_post_pass_a.py::test_basic_component_wiring` — 1 entry + 1 EntryRef + 2 ComponentLexemes (both in-plan) → 2 Adds
- [ ] T050 [P] [US3] Unit test `test_target_by_guid_resolution` — 1 component in-plan + 1 component already in target by GUID → both wired
- [ ] T051 [P] [US3] Unit test `test_unresolved_component` — 1 component neither in-plan nor in target → 1 `Skip(DEPENDENCY_UNRESOLVED)`
- [ ] T052 [P] [US3] Unit test `test_no_fingerprint_fallback` — source guid X has a target entry with matching CitationForm but different guid → still emits Skip; does NOT match by form (FR-340 anti-fallback)
- [ ] T053 [P] [US3] Unit test `test_no_persistent_state` — two `execute()` calls back-to-back; second call re-derives bindings from source, NOT from a cached file
- [ ] T054 [P] [US3] Unit test `test_source_order_preserved` — 3 components, middle one unresolved → final RS contains 2 components in correct relative positions
- [ ] T055 [P] [US3] Integration test `test_phase3c_affixes_stems_e2e.py::test_us3_stem_round_trip` — Ejagham-Mini-shaped fixture: ~239 stems with sense-to-domain wires + post-pass A; assert all wires complete or skip-recorded

**Checkpoint US3 ready**: Stems + post-pass A complete. Phase 3c can now transfer the full LexEntry inventory (affixes + stems).

---

## Phase 6: User Story 4 — Ad Hoc + Compound Rules (Priority: P2)

**Goal**: Transfer ad-hoc prohibitions and compound rules with per-subclass factory dispatch per FR-341.

**Independent Test**: Quickstart Scenario A's `ADHOC_COMPOUND_RULES` sub-step; assert all rules created via their respective subclass factories with reference fields (`LeftMsaOA`, `RightMsaOA`, `ToMsaOA`, `MembersRS`) wired through `identity_remap`.

- [ ] T056 [US4] Implement `adhoc_compound_rules.enumerate_source` in `src/gramtrans/Lib/categories.py` — concatenate `AdhocCoProhibitionsOC` + `CompoundRulesOS`
- [ ] T057 [US4] Implement `adhoc_compound_rules.dependencies` — compound rules yield `(AFFIXES, msa.Guid)` for referenced MSAs; ad-hoc groups yield `(AFFIXES, member.Guid)` for each `MembersRS` entry
- [ ] T058 [US4] Implement `adhoc_compound_rules.plan_action` — `ClassName` dispatch; unknown subclass → `Skip(NEEDS_MANUAL)` per FR-341
- [ ] T059 [US4] Implement `adhoc_compound_rules.execute_action` — per-subclass factory call (`IMoEndoCompoundFactory.Create(Guid)`, `IMoExoCompoundFactory.Create(Guid)`, `IMoAdhocProhibAtomFactory.Create(Guid)`, `IMoAdhocProhibitionGrFactory.Create(Guid)`); wire subclass-specific fields (`LeftMsaOA`, `RightMsaOA`, `ToMsaOA`, `HeadLast`, `MembersRS`) through `identity_remap` per FR-337
- [ ] T060 [US4] Implement `adhoc_compound_rules.apply_residue` — Carrier B on `Description` (or probe-derived alternative from T008/T009)
- [ ] T061 [P] [US4] Unit test `tests/unit/test_categories_adhoc_compound.py::test_endo_compound_dispatch` — source `MoEndoCompound` → `IMoEndoCompoundFactory.Create(Guid)` + `HeadLast` written
- [ ] T062 [P] [US4] Unit test `test_exo_compound_dispatch` — source `MoExoCompound` → `IMoExoCompoundFactory.Create(Guid)` + `ToMsaOA` written
- [ ] T063 [P] [US4] Unit test `test_unknown_compound_subclass_needs_manual` — fake subclass `MoFutureCompound` → `Skip(NEEDS_MANUAL)` per FR-341; no factory call
- [ ] T064 [P] [US4] Unit test `test_adhoc_atom_dispatch` — source `MoAdhocProhibAtom` → atom factory
- [ ] T065 [P] [US4] Unit test `test_adhoc_group_membersrs_via_identity_remap` — group with 2 members where 1 member's affix guid was remapped → `MembersRS` wires the remapped guid, not the source guid
- [ ] T066 [P] [US4] Integration test `test_phase3c_affixes_stems_e2e.py::test_us4_adhoc_compound_round_trip` — fixture with 1 endo + 1 exo + 1 atom + 1 group; assert all 4 created with subclass-correct factories

**Checkpoint US4 ready**: All five Phase 3c categories implemented. Full chain Phase 3a → 3b → 3c is end-to-end functional against fake LCM fixtures.

---

## Phase 7: User Story 5 — Empty-source UX (Priority: P3)

**Goal**: Inherit Phase 3a FR-308 empty-source UX for all five new Phase 3c categories per FR-339; no new module code, only test coverage.

**Independent Test**: Run with a source that has zero affixes, zero stems, zero compound rules, etc.; assert `[skip] no items in source for X` lines emitted per empty category.

- [ ] T067 [P] [US5] Unit test `tests/unit/test_phase3c_leaf_dispatch.py::test_empty_source_affixes_emits_ux_line` — selection includes `AFFIXES`, source has zero affix entries → `render_text_summary` output contains `[skip] no items in source for AFFIXES`
- [ ] T068 [P] [US5] Same for `STEMS`
- [ ] T069 [P] [US5] Same for `SLOTS`
- [ ] T070 [P] [US5] Same for `AFFIX_TEMPLATES`
- [ ] T071 [P] [US5] Same for `ADHOC_COMPOUND_RULES`

**Checkpoint US5 ready**: FR-308 inheritance confirmed across all five new categories.

---

## Phase 8: Live MCP Verification

**Goal**: Run Quickstart Scenarios A–F against `Ejagham Mini → Ejagham Full GT-Test` per Phase 3a/3b precedent; record outputs to `specs/007-affixes-stems/verification-log.md`.

- [ ] T072 Create `specs/007-affixes-stems/verification-log.md` skeleton (one section per Scenario A–F)
- [ ] T073 Live MCP Scenario A — empty target, full Phase 3a→3b→3c chain; log per-category counts and wall-clock; SC-301 target < 30s end-to-end
- [ ] T074 Live MCP Scenario B — Phase 3c re-run on populated target; assert `added_count == 0` (FR-307 inheritance)
- [ ] T075 Live MCP Scenario C — Phase 1 overwrite path on edited affix sense; assert 1 Overwrite + merge residue
- [ ] T076 Live MCP Scenario D — Phase 2 interactive merge with FakeResolver; assert N ConflictPrompts collected + resolved per policy
- [ ] T077 Live MCP Scenario E — preview-only (`modifyAllowed=False`); assert `Cache.UnitOfWorkService.IsDirty == False` after preview
- [ ] T078 Live MCP Scenario F — Phase 0 verb-vertical re-run after Phase 3c; assert SC-303 (`added_count == 0`, FR-334 collision guard holds)

---

## Phase 9: Polish & Cross-cutting Concerns

- [ ] T079 Update `STATUS.md` with Phase 3c close-sweep summary (commits, test totals, live-MCP results, deferred items)
- [ ] T080 **[Phase 3b housekeeping]** Rewrite `specs/006-inflection-prep-block/contracts/custom-field-creation.md` per Phase 3b deferred-doc-sweep item (STATUS.md line 29) — describe the Option-C detect-and-report path, not the abandoned `AddCustomField` write path
- [ ] T081 **[Phase 3b housekeeping]** Run lex-qc pattern audit (STATUS.md line 37 deferred item): sweep all `project.<Accessor>.GetAll()` callsites in `categories.py` against the flexlibs2 fork's actual accessor names vs the spec's claimed LCM collection; document findings in `specs/007-affixes-stems/qc-pattern-audit.md`
- [ ] T082 Full unit + integration regression: `python -m pytest tests/ -q`; expect 324 + 14 (new Phase 3c unit) + 5 (new Phase 3c integration) ≈ 343 passed; 0 regressions on existing 324
- [ ] T083 Final close-sweep commit: stage all Phase 3c changes; one merged commit `Phase 3c CLOSE-SWEEP — affixes/stems/templates block` with co-author tag

---

## Dependencies

```text
Phase 1 (T001–T004) — Setup
    ↓
Phase 2 (T005–T012) — Foundational probes (T006–T012 parallel after T005)
    ↓
    ├── Phase 3 US1 (T013–T028) — Affixes MVP slice
    │       ↓ (T015 stashes msa_slot_bindings consumed by US2)
    ├── Phase 4 US2 (T029–T041) — Slots + Templates + 17.1
    │       (US1 + US2 together = MVP)
    │       ↓
    ├── Phase 5 US3 (T042–T055) — Stems + post-pass A (depends on US1's _walk_lex_entry_closure helper)
    │       ↓
    ├── Phase 6 US4 (T056–T066) — Ad-hoc + compound rules (depends on US1 for affix identity_remap)
    │       ↓
    └── Phase 7 US5 (T067–T071) — Empty-source UX (independent; all 5 categories must exist)
        ↓
Phase 8 (T072–T078) — Live MCP verification (sequential by scenario)
    ↓
Phase 9 (T079–T083) — Polish + final commit
```

## Parallel Execution Opportunities

- **Phase 2 probes**: T006–T012 run in parallel after T005 creates the skeleton (7 parallel probes).
- **US1 tests**: T021–T028 run in parallel after T013–T020 ship (8 parallel tests).
- **US2 wiring tests**: T032–T041 run in parallel after T029–T031 ship (10 parallel tests).
- **US3 post-pass tests**: T046–T055 run in parallel after T042–T045 ship (10 parallel tests).
- **US4 dispatch tests**: T061–T066 run in parallel after T056–T060 ship (6 parallel tests).
- **US5 UX tests**: T067–T071 run in parallel (5 parallel tests; no implementation tasks).

## Independent Test Criteria

| Story | Independent Test |
|---|---|
| US1 | 13 Ejagham Mini affix entries transferred with owned-child closure (sense+MSA+allomorph+examples+etc.); `MSA.SlotsRC` intentionally empty |
| US2 | ~25 slots + ~5 templates created; 12-of-13 MSAs wired to slots; `ro~-` remains unbound |
| US3 | ~239 stem entries transferred; sense-to-semantic-domain refs resolve against Phase 3b transfers; post-pass A wires complete |
| US4 | All compound rule subclasses dispatch correctly; unknown subclass produces `NEEDS_MANUAL` skip |
| US5 | `[skip] no items in source for X` emitted for empty-source categories across all five new entries |

## MVP Scope

**US1 + US2** = Phase 3c MVP. Affix entries with full owned-child closure plus slots/templates with 17.1 wiring is the minimum viable Phase 3c deliverable — stems (US3) and compound rules (US4) extend the surface but the leaf-dispatch pattern is already proven by US1/US2. Empty-source UX (US5) is pure FR-308 inheritance with no risk.

US3 follows US2 because it reuses `_walk_lex_entry_closure` (T016) and `_dispatch_msa_subclass` (T017) from US1, plus depends on Phase 3b's semantic-domain transfers (FR-326) and Phase 3a's Strata (FR-336). US4 follows US3 because compound rules reference affix MSAs via `identity_remap` populated by US1.

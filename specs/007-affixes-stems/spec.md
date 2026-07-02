# Feature Specification: Phase 3c — Affixes / Stems / Templates Block

**Feature Branch**: `007-affixes-stems`

**Created**: 2026-06-21

**Status**: Ready for `/speckit-plan` — all clarifications resolved (Session 2026-06-22); quality checklist green ([checklists/requirements.md](checklists/requirements.md))

## Clarifications

### Session 2026-06-22

- Q: Which LCM filter partitions LexEntries into "affix" (US1) vs "stem" (US3)? → A: `IMoMorphType.IsAffixType` — each LexEntry's primary `LexemeFormOA.MorphTypeRA.IsAffixType` boolean decides the partition. Matches FLEx UI's affix/stem split and the lexicon export pipeline.
- Q: How should post-pass A resolve `LexEntryRef.ComponentLexemesRS` / `PrimaryLexemesRS` targets? → A: In-plan + target lookup. Resolve against (a) entries created in this Phase 3c plan plus (b) entries already in target by GUID. Unresolved refs skip with `DEPENDENCY_UNRESOLVED`. No cross-phase persistent state.
- Q: Where does the 17.1 MSA-slot wiring sub-pass live in the dispatch loop? → A: Post-execute on the `AFFIX_TEMPLATES` executor (after slot-GUIDs from `SLOTS` are stable). Affix-entry executor stashes the (msa_guid, slot_guid_list) pairs on the plan; templates executor's tail block writes `MSA.SlotsRC` via the stashed mapping. No new `LEAF_CATEGORIES` entry; matches Phase 3a `natural_classes` SegmentsRC and Phase 3b `variant_types` InflFeatsOA post-execute patterns.
- Q: How wide is Phase 0 verb-vertical's collision with Phase 3c affix transfer expected to be? → A: Phase 0 verb-vertical was a POC / MVP — never the steady-state model. The production pipeline ordering is: POS pre-reqs (inflection features, classes, stem names, exception features — Phase 3b) → POS + empty templates + empty slots (memo steps 6, 16, 17) → Affixes (memo step 14) → MSA-slot/template wiring (17.1) → Stems (step 18). Phase 0 should be retired / subsumed once Phase 3c lands. During the transition window, the collision-guard (target-GUID lookup before `_create_with_guid`) suffices for any Phase-0-then-Phase-3c re-run scenario; expected overlap = Phase 0's picked-POS affix subset.
- Q: How should compound-rule subclasses (`IMoEndoCompound`, `IMoExoCompound`) be handled? → A: Per-subclass factories. `execute_action` inspects `ICmObject(src_obj).ClassName` and dispatches to `IMoEndoCompoundFactory` or `IMoExoCompoundFactory` (and any other concrete subclasses surfaced by MCP probe). Subclass-specific fields (e.g., `IMoExoCompound.ToMsaRA`) round-trip fully. Unknown subclasses emit `Skip(NEEDS_MANUAL)` rather than fall back to a lossy generic path.

**Input**: Third implementation slice of the Phase 3 full-pipeline build-out per [specs/004-phase3-pipeline/ordering-memo.md](../004-phase3-pipeline/ordering-memo.md) — memo steps 14–18 plus the 17.1 MSA-slot wiring sub-pass. Builds on the project-level inflection scaffolding shipped by Phase 3b ([specs/006-inflection-prep-block/](../006-inflection-prep-block/)) and the phonology block shipped by Phase 3a ([specs/005-phonology-block/](../005-phonology-block/)).

## In-scope categories (memo steps 14–18)

| Step | Category | Source path | Dependencies |
|---|---|---|---|
| 14 | **Affixes** (LexEntries with affix morph_type + owned children: senses, MSAs, lexeme-form allomorph, alternate-forms, examples, pronunciations, etymologies, entry-refs) | `LangProject.LexDbOA.EntriesOC` filtered by affix morph types | 6, 7, 9, 10, 11, 12, 4b, 5b |
| 15 | **Ad Hoc + Compound Rules** | `LangProject.MorphologicalDataOA.AdhocCoProhibitionsOC` / `CompoundRulesOS` | 5b, 14 |
| 16 | **Slots** (owned by POS) | `IPartOfSpeech.AffixSlotsOC` | 6 |
| 17 | **Affix Templates** + **17.1 MSA-slot wiring** | `IPartOfSpeech.AffixTemplatesOS` | 6, 5b, 14, 16 |
| 18 | **Stems** (LexEntries with stem morph_type + owned children) | `LangProject.LexDbOA.EntriesOC` filtered by stem morph types | all prior morphology + lex-types + 13b |

## User Stories *(draft — to clarify)*

### US1 — Affix entries with owned children (P1)
Linguist transfers verbal-affix LexEntries with senses, MSAs, allomorphs, examples, pronunciations, etymologies, and entry-refs. `MSA.SlotsRC` and `LexEntryRef.ComponentLexemesRS` / `PrimaryLexemesRS` left empty for later passes.

### US2 — Slots + Affix Templates + MSA-slot wiring (P1)
Slots created under target POSes; templates created with `PrefixSlotsRS` / `SuffixSlotsRS` wired to slots; **17.1 sub-pass**: for every affix MSA from US1, fill `MSA.SlotsRC` from slot-GUIDs stashed by US1's planner.

### US3 — Stems with semantic-domain refs (P2)
Stem LexEntries with senses; sense-to-semantic-domain refs resolve through Phase 3b's semantic-domain transfer (FR-326). `MSA.StratumRA` resolves to Strata from Phase 3a.

### US4 — Ad Hoc + Compound Rules (P2)
Constraint rules reference affix LexEntries (from US1), POS (from Phase 3b), and Strata (from Phase 3a).

### US5 — Empty-source UX (P3)
FR-308 inheritance for all 5 new categories.

## Functional Requirements *(draft)*

- **FR-331**: Add `AFFIXES`, `ADHOC_COMPOUND_RULES`, `SLOTS`, `AFFIX_TEMPLATES`, `STEMS` to `GrammarCategory` enum (5 new members). Extend `_LEAF_DISPATCH_CATEGORIES` in `Lib/preview.py` + `Lib/transfer.py`.
- **FR-332**: Affix LexEntry transfer MUST bring owned children (senses, MSAs, allomorphs, examples, pronunciations, etymologies, entry-refs) atomically with the parent entry. The affix-vs-stem partition is decided per-entry by `entry.LexemeFormOA.MorphTypeRA.IsAffixType` (the LCM `IMoMorphType.IsAffixType` boolean). Entries whose lexeme-form is absent or whose MorphType is unresolved skip with `Skip(DEPENDENCY_UNRESOLVED)`.
- **FR-333**: `MSA.SlotsRC` and `LexEntryRef.ComponentLexemesRS` / `PrimaryLexemesRS` MUST be deferred — populated at 17.1 sub-pass and post-pass A respectively. The 17.1 sub-pass lives as a post-execute tail block on the `AFFIX_TEMPLATES` executor (runs after `SLOTS` has populated slot-GUIDs in target). The affix-entry executor (US1) stashes `(msa_guid, [slot_guid, ...])` mappings on the plan via a dedicated `plan.msa_slot_bindings` dict; the templates tail block consumes that mapping to write `MSA.SlotsRC`. Unresolved slot-GUIDs at wire time emit `Skip(DEPENDENCY_UNRESOLVED)` on the affected MSA, not on the template.
- **FR-334**: Phase 0 verb-vertical was a POC / MVP scaffold and is not the steady-state model — the production pipeline runs the full ordered chain (Phase 3b pre-reqs → POS + empty templates + empty slots → Affixes → 17.1 wiring → Stems). For the transition window where Phase 0 may have already run against a target, Phase 3c MUST guard each `_create_with_guid` with a target-GUID lookup; on hit, emit `Skip(ALREADY_PRESENT_BY_GUID)` (same pattern as Phase 3b `gram_categories` post-retarget). No category-specific Phase-0-collision code beyond the universal guard.
- **FR-335**: Stem LexEntry sense-to-semantic-domain refs MUST resolve against Phase 3b's transferred semantic domains (FR-326). `Skip(DEPENDENCY_UNRESOLVED)` if the referenced domain is absent from target and not in the in-flight plan.
- **FR-336**: Stratum references across Phase 3c MUST resolve to Phase 3a-transferred Strata by GUID lookup. The scope is broader than originally specified — three accessors carry `StratumRA`:
  - `IMoStemMsa.StratumRA` (US3 stem MSAs).
  - `IMoCompoundRule.StratumRA` (US4 compound rules, inherited by `MoEndoCompound` + `MoExoCompound`).
  - `IMoInflAffixTemplate.StratumRA` (US2 affix templates).
  Missing Stratum in target → `Skip(DEPENDENCY_UNRESOLVED)` on the owning object. FR-307 idempotency holds — re-running doesn't duplicate strata.
- **FR-337**: Ad-Hoc + Compound rules MUST resolve their referenced affix LexEntries through `identity_remap` (Phase 1 FR-101..110) when source-GUID and target-GUID diverge.
- **FR-340**: Post-pass A (`LexEntryRef.ComponentLexemesRS` / `PrimaryLexemesRS` wiring) MUST resolve referenced LexEntries against (a) entries created in the current Phase 3c plan and (b) entries already present in target by GUID. Refs that resolve to neither emit `Skip(DEPENDENCY_UNRESOLVED)`. Post-pass A MUST NOT scan target for fuzzy/fingerprint matches and MUST NOT depend on persistent state from earlier phase runs.
- **FR-341**: Compound-rule + ad-hoc-prohibition transfer (US4 / memo step 15) MUST dispatch on `ICmObject(src_obj).ClassName` to per-subclass factories. The LCM model surfaced by T008/T009 MCP probes is:
  - **Compound rules** (`LangProject.MorphologicalDataOA.CompoundRulesOS`): base `IMoCompoundRule` carries `Name`, `Description` (Carrier B residue), `Disabled`, `StratumRA` (→ Phase 3a Strata per FR-336), `ToProdRestrictRC`. Concrete subclasses:
    - `MoEndoCompound`: adds `HeadLast` (bool) + `OverridingMsaOA` (owned `IMoStemMsa`, optional).
    - `MoExoCompound`: adds `ToMsaOA` (owned `IMoStemMsa`, mandatory).
    - **There is NO `LeftMsaOA`/`RightMsaOA` on either subclass** — the parser derives operands from the morpheme chain at parse time; the rule stores only the result MSA.
    - Recommended creation path: `MorphRuleOperations.CreateCompoundRule(name, endocentric=True, description=None)` (flexlibs2 wrapper). ServiceLocator fallback only if the wrapper proves unsuitable at write-implementation time.
  - **Ad-hoc prohibitions** (`LangProject.MorphologicalDataOA.AdhocCoProhibitionsOC`): base `IMoAdhocProhib` carries `Adjacency` (int) + `Disabled` (bool). Concrete subclasses:
    - `MoAdhocProhibGr` (GROUP): adds `Name`, `Description` (Carrier B residue), **`MembersOC` (owned collection)** of nested `IMoAdhocProhib` atoms. Note: members are OWNED, not referenced — atoms are children of their parent group.
    - `MoAlloAdhocProhib` (ATOMIC, allomorph-based): adds `AllomorphsRS` + `FirstAllomorphRA` + `RestOfAllosRS` referencing `IMoForm` allomorphs from US1.
    - `MoMorphAdhocProhib` (ATOMIC, morpheme-based): adds `MorphemesRS` + `FirstMorphemeRA` + `RestOfMorphsRS` referencing `IMoMorphSynAnalysis` from US1.
    - Atomic prohibitions carry **NO residue carrier** — neither `Description` nor `LiftResidue`/`ImportResidue` is exposed. Phase 3c posture: skip residue silently on atomic prohibitions; group-owned atomics inherit the group's residue trail; top-level atomic prohibitions emit a run-report info line only.
  - References to affix LexEntries (`AllomorphsRS`/`FirstAllomorphRA`/`RestOfAllosRS`, `MorphemesRS`/`FirstMorphemeRA`/`RestOfMorphsRS`) resolve through `identity_remap` per FR-337.
  - Unknown subclasses emit `Skip(NEEDS_MANUAL)`.
  - **US4 live-verification gap**: Ejagham Mini contains 0 compound rules and 0 ad-hoc prohibitions (T012 inventory). US4 ships with unit + synthetic-fixture integration coverage only; live MCP Scenario A (T073) skips the US4 sub-step. Documented gap in `verification-log.md`.
- **FR-338**: All 5 new categories MUST honor Phase 1 overwrite (`enable_overwrite=True`) and Phase 2 interactive merge (per-field conflicts surface as `ConflictPrompt`s).
- **FR-339**: FR-308 empty-source UX MUST emit `[skip] no items in source for X` lines for each of the 5 new categories when source collection is empty.

## Open Questions *(for `/speckit-clarify`)*

1. ~~Affix morph-type filter~~ — resolved (Clarifications, Session 2026-06-22): use `IMoMorphType.IsAffixType` boolean on `entry.LexemeFormOA.MorphTypeRA`.
2. ~~Entry-ref handling order~~ — resolved (Clarifications, Session 2026-06-22): in-plan + target-by-GUID; see FR-340.
3. ~~17.1 implementation site~~ — resolved (Clarifications, Session 2026-06-22): post-execute tail on `AFFIX_TEMPLATES` executor consuming `plan.msa_slot_bindings`. See FR-333.
4. ~~Phase 0 collision width~~ — resolved (Clarifications, Session 2026-06-22): Phase 0 is POC, not steady-state; universal collision-guard suffices for the transition window. See FR-334 and the production-ordering note.
5. ~~Compound-rule sub-classes~~ — resolved (Clarifications, Session 2026-06-22): per-subclass factories with `ClassName` dispatch. See FR-341.

## Success Criteria *(draft)*

- **SC-301**: Ejagham Mini → Ejagham Full GT-Test full Phase 3c run completes in <10 s wall-clock for ~250 affix + stem entries, ~25 slots, ~5 templates.
- **SC-302**: All 5 new categories inherit Phase 1 overwrite + Phase 2 merge without category-specific code in the merge planner.
- **SC-303**: Phase 0 verb-vertical re-run after a full Phase 3c transfer produces zero new actions (FR-307 idempotency holds for affixes/MSAs/allomorphs already-created by 3c).

## Out of scope

- LexEntry inter-entry refs (`ComponentLexemesRS` / `PrimaryLexemesRS`) post-pass A — defer to a follow-up slice.
- Reversal indices (memo step 18b), Texts (step 19), WordformAnalyses (step 20) — covered by post-Phase-3c slices.
- **`IMoAffixProcess` allomorph subclass** — Phase 3c handles `MoAffixAllomorph` and `MoStemAllomorph` only. Source allomorphs whose `ClassName == "MoAffixProcess"` emit `Skip(NEEDS_MANUAL)` per the same fail-loud posture as FR-341 compound subclasses. Production support deferred to a post-Phase-3c slice once MCP probes characterise the AffixProcess rule chain.

## Next steps

1. Run `/speckit-clarify` against the 5 open questions above.
2. Run `/speckit-plan` for research / data-model / contracts / quickstart.
3. Run `/speckit-tasks` to fan out into a tasks.md (estimate: 40-50 tasks across 7 phases following the 3a/3b template).
4. MCP-probe the open questions before writing callbacks.

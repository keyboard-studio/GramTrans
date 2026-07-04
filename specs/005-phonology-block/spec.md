# Feature Specification: Phase 3a — Phonology Block

**Feature Branch**: `005-phonology-block`

**Created**: 2026-06-20

**Status**: Draft

**Input**: User description: First implementation slice of the validated 22-step Phase 3 pipeline (per [specs/004-phase3-pipeline/ordering-memo.md](../004-phase3-pipeline/ordering-memo.md)) — six self-contained categories anchored at `PhonologicalDataOA` and `MorphologicalDataOA` with no LexEntry coupling.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Transfer a phoneme inventory + natural classes + phonological rules (Priority: P1)

A linguist has built up a phoneme inventory, natural classes ("voiced stops", "front vowels"), and a small set of phonological rules in a sister project — say, an earlier-stage version of the same language she's now consolidating into a master project. She runs GramTrans selecting the phonology categories and expects all of it to come across with GUIDs preserved (so re-runs are idempotent), Phase 1 overwrite semantics on conflicts, and a clear warning if any phonological rule references a phoneme that didn't make it into target.

**Why this priority**: This is the headline value of Phase 3a — the first slice of grammar that's NOT LexEntry-coupled. Linguists need to share phoneme inventories across sister projects routinely, and currently GramTrans has no path for it. P1 because nothing else in Phase 3+ unblocks without phonology in place (allomorph environments, affix MSAs, and stratum-referenced templates all eventually want phonology to be present).

**Independent Test**: Set up a source project with a non-empty phoneme inventory, ≥1 natural class, and ≥1 phonological rule. Run the transfer with phonology categories enabled and overwrite=false. Verify (a) every phoneme appears in target with source's GUID; (b) every natural class appears with its phoneme references resolving to the just-transferred phonemes; (c) every phonological rule's structural description references phonemes/classes that exist in target; (d) the run report shows the per-category added counts matching the source's `enumerate_source` counts.

**Acceptance Scenarios**:

1. **Given** a source project with 30 phonemes (all project-specific, no GOLD), **When** the linguist transfers the Phonemes category, **Then** all 30 phonemes appear in target with source GUIDs and the run report shows `phonemes added=30 skipped=0`.
2. **Given** a source project that uses an inflection-feature-attached natural class, **When** the linguist transfers Natural Classes, **Then** the class's feature struct (`IPhNCFeatures.FeaturesOA`) imports with the class and the run completes without DEPENDENCY_UNRESOLVED skips for phonological features.
3. **Given** a source phonological rule that references phoneme P-NEW (in source but not yet in target), **When** the linguist transfers Phonological Rules without first transferring Phonemes, **Then** the rule entry produces a `Skip(DEPENDENCY_UNRESOLVED)` with a detail message naming P-NEW.
4. **Given** Phase 1 overwrite=True on a target that has 5 of the 30 source phonemes already (by GUID), **When** the transfer runs, **Then** 5 land as PlannedOverwrites and 25 as PlannedActions per Phase 1 conventions, and the residue tag carries the snapshot of overwritten phonemes' pre-overwrite syncable props.

---

### User Story 2 — Strata import before any morphology runs (Priority: P1)

A linguist has source-side strata ("Stratum 1", "Clitic Stratum") that her affix templates and stem MSAs reference. She doesn't think about strata as a category she's choosing to transfer — she expects them to come along automatically whenever she transfers anything that references them. When she later runs the morphology block (Phase 3b+), templates / MSAs / compound rules can wire their `StratumRA` references without dangling.

**Why this priority**: P1 because the validated ordering memo identifies strata as a prerequisite for steps 14 (Affixes), 15 (Ad Hoc + Compound Rules), 17 (Affix Templates), and 18 (Stems). Without strata-first, every morphology step risks DEPENDENCY_UNRESOLVED. This story IS Phase 3b's hard prerequisite.

**Independent Test**: Run a transfer with Strata enabled against a source that has ≥1 stratum. Verify: (a) the stratum imports with source GUID; (b) `MoMorphData.StrataOS` in target contains the new stratum after the run; (c) a follow-up transfer that includes a stratum-referencing object (template, MSA, compound rule) does NOT skip with DEPENDENCY_UNRESOLVED.

**Acceptance Scenarios**:

1. **Given** a source with 3 strata, **When** the linguist transfers the Strata category, **Then** all 3 appear in `target.MorphologicalDataOA.StrataOS` with source GUIDs.
2. **Given** Strata is selected but source has zero strata, **When** the transfer runs, **Then** the run report shows `[skip] no items in source for strata` and the run continues.

---

### User Story 3 — PhEnvironments live in the phonology block, not bundled with allomorphs (Priority: P2)

A linguist runs Phase 0/1/2 (allomorph-creating transfers) AFTER Phase 3a has already populated `PhonologicalDataOA.EnvironmentsOS` with the source's environments. The legacy allomorph-creation path (which previously created environments on-the-fly when missing) now finds every environment already present by GUID and falls into a no-op for that step.

**Why this priority**: P2 because the Phase 0/1/2 allomorph flow already works around this case (creates-if-missing). This story is a cleanup — moving environments to their natural ownership location — not a new capability.

**Independent Test**: Run Phase 3a transferring phonology including PhEnvironments. Then run the existing Phase 0 verb-vertical transfer. Verify: (a) every environment the allomorph closure references is found by GUID in target (no creates); (b) the run report's `ph_environment added` count is 0 and `overwritten` count matches whatever Phase 1 expects given the target state.

**Acceptance Scenarios**:

1. **Given** target has all source environments already present, **When** Phase 0 verb-vertical runs over the same source, **Then** no new IPhEnvironment objects are created (zero adds).
2. **Given** target has none of source's environments, **When** Phase 3a transfers PhEnvironments before allomorph creation, **Then** allomorph `PhoneEnvRC` references in step 14 resolve to the just-created targets.

---

### User Story 4 — Empty-source skip-graceful (Priority: P3)

A linguist is running a lexicon-focused transfer where the source has zero phonological features / phonemes / natural classes / rules / strata. She still has those categories ticked on the wizard (it's a one-click "transfer everything" mode). The transfer SHOULD scan, report "nothing to transfer for X" per empty category, and continue without error.

**Why this priority**: P3 because this is a UX polish — the system already handles the "no source items" case at the planner level for the five complete leaf categories; Phase 3a should extend the same handling to phonology + strata.

**Independent Test**: Set up a source with empty `PhonologicalDataOA` (no phonemes, no NCs, no rules, no envs) and empty `MorphologicalDataOA.StrataOS`. Run the transfer with all six phonology+strata categories enabled. Verify the run completes successfully and the report contains `[skip] no items in source for X` for each empty category.

**Acceptance Scenarios**:

1. **Given** all six categories are empty in source, **When** the transfer runs, **Then** the run report shows 6 `[skip] no items in source for ...` lines and zero errors.

---

### Edge Cases

- What happens when **a source phonological rule references a natural class that's in source but the user un-ticked Natural Classes**? The rule produces a `Skip(DEPENDENCY_UNRESOLVED)` naming the missing class. User remediation: re-run with Natural Classes ticked, or accept the skip and edit the rule manually post-transfer.
- What happens when **two source phonemes have identical IPA representations but different GUIDs** (an actual data-quality issue in the source)? Both transfer with their distinct GUIDs; the target then carries two phonemes with identical IPA — same outcome as if the user had copied the source's data directly. No GramTrans-level dedup is performed.
- What happens when **target has a phoneme with the same IPA but a different GUID** than source's? Phase 1's matcher uses GUID-first, fingerprint-second matching. A fingerprint match (IPA + class) would surface as a PlannedOverwrite via Phase 1's `identity_remap` (FR-103) — the source's GUID does NOT replace the target's; the target's existing GUID is reused for inbound references.
- What happens when **a phonological rule has an empty structural description or change** (an unfinished rule in source)? Transfer as-is; the empty fields land empty in target. Linguist can finish in target as before.
- What happens when **strata are referenced but the source has zero strata defined** (legacy data without strata)? `MoMorphData.StrataOS` is empty in source; the category scan emits the empty-source skip; no strata land in target. Later morphology transfer steps that try to write `StratumRA` to None should fall back to the default stratum or omit the reference (out of scope for Phase 3a; handled in Phase 3b).
- What happens when **the user cancels mid-transfer via the Phase 2 conflict dialog** on a phonology-block run? Same atomicity contract as Phase 2 — `UserCancelled` aborts the entire transfer with zero database mutations.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-301**: System MUST add `phonological_features`, `phonemes`, `natural_classes`, `phonological_rules`, and `strata` as enum members of `GrammarCategory`. (Note: `ph_environment` already exists in the enum from Phase 0; Phase 3a re-points its sourcing logic.)
- **FR-302**: For each of the six categories in scope (PhonFeatures, Phonemes, NaturalClasses, PhEnvironments, PhonRules, Strata), System MUST register the five callbacks (`enumerate_source`, `dependencies`, `required_writing_systems`, `plan_action`, `execute_action`) in `Lib/categories.py`, matching the shape of the five COMPLETE categories.
- **FR-303**: System MUST preserve GUIDs on transfer for every category in scope when LCM factories support a Guid overload. When a category's factory does NOT support GUID preservation (a flexicon limitation discovered during MCP probing), the planner MUST record the source-GUID → new-GUID mapping in `identity_remap` so downstream references can resolve (same pattern as FR-012).
- **FR-304**: Phonological Rules MUST scan their structural-description and structural-change fields for referenced phonemes and natural classes, and emit `Skip(DEPENDENCY_UNRESOLVED)` for any rule whose references cannot be resolved in target (either already present by GUID or co-transferred in the same run).
- **FR-305**: Natural Classes referencing inflection features (via `IPhNCFeatures.FeaturesOA`) MUST import their owned feature struct as part of the class — the struct is OA on the class, no separate ordering dependency on the Phase 7 Inflection Features category beyond what already exists.
- **FR-306**: Strata transfer MUST run before any object that carries `StratumRA` (Phase 3b+ affix templates, MSAs, compound rules). Phase 3a guarantees strata are positioned in the validated ordering at step 5b (after Phonological Rules, before POS).
- **FR-307**: PhEnvironments transfer MUST be idempotent with the existing Phase 0/1/2 allomorph environment-creation path: when an environment exists in target by GUID, no new IPhEnvironment is created.
- **FR-308**: Each in-scope category MUST honor the existing skip-empty UX (per Phase 3 memo): when source has zero items, emit `[skip] no items in source for X` in the run report and continue.
- **FR-309**: Phase 1 overwrite semantics (FR-101..110) MUST apply to phonology-block categories without modification. When `enable_overwrite=True` and a phoneme / natural class / rule / environment / stratum already exists in target by GUID, the planner emits a PlannedOverwrite; execute applies source's syncable properties and stamps the residue tag with the pre-overwrite snapshot.
- **FR-310**: Phase 2 interactive merge (FR-201..217) MUST apply to phonology-block categories without modification. Per-field conflicts on phoneme / class / rule / environment / stratum objects surface as ConflictPrompts in the standard flow.
- **FR-311**: Phase 3a MUST NOT modify the existing Phase 0/1/2 verb-vertical or multi-POS executor paths. The phonology-block runs as additional categories in the existing `build_run_plan` / `execute` flow; it does not replace or restructure them.

### Key Entities *(include if feature involves data)*

- **PhonologicalFeature**: Represents one phonological feature definition (e.g. "voiced", "high"). Carries a name, abbreviation, and feature values. Owned by `IFsFeatureSystem` (the phonological subsystem, distinct from the inflectional `MsFeatureSystemOA`).
- **Phoneme**: Represents one phoneme in the language's inventory. Carries an IPA representation, a name, optionally a feature struct (`FeaturesOA`) tying it to phonological features.
- **NaturalClass**: A grouping of phonemes (e.g. "voiced stops"). Two subtypes: `IPhNCSegments` (membership-based via `SegmentsRC` → phonemes) and `IPhNCFeatures` (feature-based via owned `FeaturesOA`).
- **PhEnvironment**: A phonological context for allomorph distribution or rule application (e.g. "/_C", "/_V"). Carries an IPA pattern.
- **PhonologicalRule**: A morphophonological rule with structural-description, structural-change, and optional left/right contexts. References phonemes, natural classes, and environments via RC fields.
- **Stratum**: A linguistic-stratum label used to scope morphological operations to a phase of derivation. Carries a name and abbreviation. Referenced by affix templates, derivational MSAs, stem MSAs, and compound rules via `StratumRA`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-301**: A linguist transferring a 30-phoneme inventory + 10 natural classes + 5 phonological rules + 2 strata from a sister project completes the transfer in under 5 seconds wall-clock.
- **SC-302**: 100% of GUID-preserved categories (PhonFeatures, Phonemes, NaturalClasses, PhEnvironments, Strata) carry source GUIDs into target on first run. Categories whose factory cannot preserve GUIDs (TBD — to be confirmed by Phase 3a's MCP probing pass) record their remap entries in `identity_remap` for downstream resolution.
- **SC-303**: After Phase 3a is shipped, the Phase 0/1/2 verb-vertical transfer with allomorph references to PhEnvironments produces ZERO new `IPhEnvironment` creates when the phonology block has already populated those environments — confirming idempotency.
- **SC-304**: Zero source items are silently dropped: every object enumerated by a category's `enumerate_source` ends up as either a `PlannedAction` (additive), a `PlannedOverwrite` (Phase 1), or a `Skip` (with explicit reason). Audit via FR-018 invariant on `RunReport`.
- **SC-305**: The Phase 0/1/2 168 unit + 99 Phase 2 integration tests (267 total) continue to pass without modification. Phase 3a adds new unit + integration tests bringing the suite to a target of ~310 passing tests.
- **SC-306**: A linguist who selects ONLY the phonology block (un-ticking all other categories) and runs the transfer leaves the lexicon, morphology, and POS sections of the target project bit-identical to their pre-transfer state.

## Assumptions

- The flexicon fork at `D:/Github/_Projects/_LEX/flexicon` exposes the five Operations classes named in the user input (`PhonFeatureOperations`, `PhonemeOperations`, `NaturalClassOperations`, `EnvironmentOperations`, `PhonologicalRuleOperations`). Strata lack a dedicated Operations class; Phase 3a will use direct LCM `GetFactory(IMoStratumFactory)` / `LangProject.MorphologicalDataOA.StrataOS.Add(...)` patterns and document the result.
- GUID preservation is supported for `IPhPhoneme`, `IPhNaturalClass`, `IPhEnvironment`, and `IMoStratum` factories. If MCP probing during Phase 3a planning reveals a factory lacks a Guid-accepting constructor, the planner falls back to identity_remap and a clarification will be raised at Phase 3a planning time (not in this spec).
- `IPhPhonologicalRule` cross-references (structural description, structural change, contexts) are detectable via per-rule property walks the planner can implement without changing the LCM model.
- The default phoneme set (`PhonemeSetsOS[0]`) is the canonical home for both source and target phonemes. Multi-phoneme-set projects (rare, advanced configuration) are out of scope for Phase 3a; the planner uses index 0.
- Constitution v5.0.0 Principle II (flexicon-Direct) — all new code imports flexicon directly. No flavor-adapter shape introduced.
- Constitution Principle IV (Phased Merge Discipline) — Phase 3a layers on top of Phases 0+1+2; no Phase-0-only or Phase-1-only path is removed.
- The Phase 2 `phase2_interactive_move()` helper extends transparently to the new categories: no new wiring required at the MainFunction level beyond enabling the categories in the default Selection dict.

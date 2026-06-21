# Feature Specification: Phase 3b — Inflection / Lexicon-Prep Block

**Feature Branch**: `006-inflection-prep-block`

**Created**: 2026-06-21

**Status**: Draft

**Input**: User description: Second implementation slice of the Phase 3 full-pipeline build-out per [specs/004-phase3-pipeline/ordering-memo.md](../004-phase3-pipeline/ordering-memo.md) — nine project-level configuration categories (steps 6 through 13b) that prepare the target for the Phase 3c lexicon import. Five callbacks already complete in `Lib/categories.py` from Phase 0; Phase 3b wires them through the leaf-dispatch loop that landed in commit 608b72c and fills in the three remaining stubs plus one new category (Semantic Domains).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Transfer POS hierarchy + inflection features + inflection classes + stem names + exception features (Priority: P1)

A linguist has a fully developed inflection system in a sister project — Verb / Noun POS hierarchy, ~30 inflection features (Tense, Aspect, Mood, Number, Gender, ...) with closed sets of values, a handful of inflection classes per POS, stem-name variants for each class, and exception features that pick up unusual paradigms. She runs GramTrans selecting the inflection categories. Every GOLD-catalogued object on the source (anything carrying a non-empty `CatalogSourceId`) is skipped per FR-022 / Principle I — only the user-defined additions to the GOLD baseline transfer.

**Why this priority**: This is the headline value of Phase 3b. The five callbacks are already implemented and hardened (3863ed2); Phase 3b is the first time they actually fire through the leaf-dispatch loop end-to-end. A linguist who's been building up an inflectional analysis for months can finally share it across projects without rebuilding by hand. P1 because Phase 3c (affixes / templates / stems) doesn't function without POS + InflClasses + StemNames + ExceptionFeatures already in place — those references are how affix MSAs and stem MSAs attach themselves.

**Independent Test**: Set up a source project with a non-GOLD POS subhierarchy and at least one inflection feature, inflection class, stem name, and exception-feature wiring. Run the transfer with those five categories selected and `enable_overwrite=False`. Verify: (a) every non-GOLD piece appears in target with source's GUID; (b) every GOLD piece emits `Skip(GOLD_INVIOLABLE)`; (c) inflection classes attach to the right POS; (d) exception-feature references resolve to the just-transferred inflection-feature values.

**Acceptance Scenarios**:

1. **Given** source has 2 user-defined POSes (Verb, Noun) and target has empty `PartsOfSpeechOA`, **When** the linguist transfers Gram Categories, **Then** both POSes appear in target with source GUIDs and the run report shows `gram_categories added=2 skipped=0`.
2. **Given** source's Verb POS has 5 inflection classes, **When** the linguist transfers Inflection Classes, **Then** all 5 classes appear under target's Verb POS via `InflectionClassesOC` with source GUIDs.
3. **Given** source has 4 inflection features (each carrying value sets), **When** the linguist transfers Inflection Features, **Then** all 4 features land in `target.MsFeatureSystemOA.FeaturesOC` with their owned values attached (P0-A pattern from 3863ed2 keeps the value loop orphan-safe).
4. **Given** source's GOLD Verb POS (from FW's standard catalog), **When** the linguist transfers Gram Categories, **Then** GOLD Verb produces `Skip(GOLD_INVIOLABLE)` with a detail line citing the source's `CatalogSourceId`.
5. **Given** Phase 1 `enable_overwrite=True` and target already has 3 of the 5 inflection classes by GUID, **When** the transfer runs, **Then** 3 land as PlannedOverwrites and 2 as PlannedActions; the residue tag carries the pre-overwrite snapshot.

---

### User Story 2 — Transfer Custom Field definitions (Priority: P1)

A linguist's source project has FLEx custom-field definitions like "Noun class" on LexEntry, "Tone melody" on LexSense, "Loanword origin" on LexEntry. She runs Phase 3b with Custom Fields selected. The definitions land in target before any Phase 3c LexEntry import would try to use them. Without Phase 3b's Custom Fields step, Phase 3c entries that carry "Noun class" values would silently drop those values on import (because the target wouldn't know the field exists).

**Why this priority**: P1 because Phase 3c (LexEntries with custom-field values) loses data without this. Custom Fields are project-wide schema; once the definitions exist, every entry import can populate them. Their absence is a silent-data-loss bug.

**Independent Test**: Source with 2-3 custom fields defined (different target classes, different value types). Run Phase 3b with Custom Fields selected against an empty-of-custom-fields target. Verify each definition appears in target's CustomFlid registry with name, target class, and value type matching source.

**Acceptance Scenarios**:

1. **Given** source has a "Noun class" custom field defined on LexEntry, **When** the linguist transfers Custom Fields, **Then** target's LexEntry custom-field registry includes "Noun class" with the same value type.
2. **Given** source has 0 custom fields, **When** the linguist transfers Custom Fields, **Then** the run report emits `[skip] no items in source for custom_fields` and the run continues.

---

### User Story 3 — Transfer Variant Types + Complex Form Types + custom Semantic Domains (Priority: P2)

A linguist transfers lexicon-prep categories: Variant Types (e.g., "Plural", "Past Tense") and Complex Form Types (e.g., "Compound", "Idiom") from her sister project's `LexDb`, plus any project-specific Semantic Domains beyond FW's standard catalog. Standard FW semantic-domain entries (those carrying a CatalogSourceId from the FW master domain list) are NOT transferred — they ship with FieldWorks already.

**Why this priority**: P2 because Phase 3c's LexEntries can carry variant-of / complex-form / semantic-domain references that need these definitions to resolve. But unlike US2 (where missing custom fields silently drop data), missing variant types just emit `Skip(DEPENDENCY_UNRESOLVED)` for the referring entry — a more recoverable failure mode.

**Independent Test**: Source with custom variant types + complex form types + at least one non-GOLD semantic domain. Run Phase 3b with those three categories selected. Verify (a) custom variant types land with source GUIDs; (b) GOLD semantic domains are skipped; (c) the run report shows correct counts per category.

**Acceptance Scenarios**:

1. **Given** source has 4 user-defined variant types, **When** the linguist transfers Variant Types, **Then** all 4 land in target's `LexDbOA.VariantEntryTypesOA.PossibilitiesOS`.
2. **Given** source uses FW's standard 1700+ semantic domain catalog plus 3 custom additions, **When** the linguist transfers Semantic Domains, **Then** only the 3 custom domains transfer; standard catalog entries skip with `GOLD_INVIOLABLE`.

---

### User Story 4 — Empty-source skip-graceful for all 9 categories (Priority: P3)

A linguist runs a phonology-only transfer where source has no POS hierarchy, no inflection features, no custom fields, etc. (unusual but possible — e.g. a phonology-tracking project that doesn't model morphology). She still has all Phase 3b categories ticked. The transfer scans, reports `[skip] no items in source for X` per empty category, and continues.

**Why this priority**: P3 because Phase 3a US4 already established the empty-source UX path via FR-308. Phase 3b just inherits it for the nine new categories.

**Independent Test**: Source with empty `PartsOfSpeechOA`, empty `MsFeatureSystemOA`, etc. (or a minimal phonology-only project). Run the transfer with all 9 Phase 3b categories selected. Verify the run report emits 9 `[skip] no items in source for X` lines and zero errors.

**Acceptance Scenarios**:

1. **Given** all 9 categories are empty in source, **When** the transfer runs, **Then** the run report shows 9 `[skip] no items in source for ...` lines, 0 errors, 0 actions.

---

### Edge Cases

- What happens when **an inflection class references its owning POS, but the user un-ticked POS in the Selection**? The inflection class emits `Skip(DEPENDENCY_UNRESOLVED)` naming the missing owner-POS GUID. User remediation: re-run with POS ticked.
- What happens when **target already has a non-GOLD POS by name but a DIFFERENT GUID** than source's? Phase 1 matcher uses GUID-first, fingerprint-second matching. A fingerprint match emits PlannedOverwrite via `identity_remap`; the source's GUID does NOT replace the target's. Downstream inflection classes wired by source-GUID resolve through the remap.
- What happens when **a custom field's target class doesn't exist** in the source schema (corrupt source)? Custom-field `plan_action` emits `Skip(DEPENDENCY_UNRESOLVED)` naming the missing target class. No partial-definition writes.
- What happens when **an exception feature's referenced `IFsSymFeatVal` was skipped as GOLD on the inflection-features pass**? Exception-feature `execute_action` looks up the value by GUID in the target's `MsFeatureSystemOA`. If the GOLD value already exists in target (it should, because GOLD entries ship with FW), the wiring resolves. If somehow absent, emit `Skip(DEPENDENCY_UNRESOLVED)`.
- What happens when **standard FW semantic-domain catalog entries appear in source with their FW canonical GUIDs**? They carry `CatalogSourceId` so Phase 3b skips them per FR-022. Target's standard catalog already has them by canonical GUID.
- What happens when **a variant type carries a feature constraint** but Inflection Features wasn't enabled in the same run? Variant-type `plan_action` emits `Skip(DEPENDENCY_UNRESOLVED)` naming the missing inflection-feature GUID.
- What happens when **the user cancels Phase 2 interactive merge mid-run**? Same atomicity contract as Phase 2 — `UserCancelled` aborts the entire transfer with zero database mutations.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-321**: System MUST add `SEMANTIC_DOMAINS` as a new enum member of `GrammarCategory`. The other eight categories already exist in the enum from prior phases (Phase 0 leaves: GRAM_CATEGORIES, INFLECTION_FEATURES, CUSTOM_FIELDS, INFLECTION_CLASSES, STEM_NAMES, EXCEPTION_FEATURES, VARIANT_TYPES, COMPLEX_FORM_TYPES).
- **FR-322**: System MUST extend the leaf-dispatch tuple in `Lib/preview.py.build_run_plan` and `Lib/transfer.py.execute` to include the nine Phase 3b categories so they thread through the existing dispatch loop the same way the six Phase 3a categories do.
- **FR-323**: System MUST implement the five callbacks (`enumerate_source`, `dependencies`, `required_writing_systems`, `plan_action`, `execute_action`) for the three stub categories (`custom_fields`, `variant_types`, `complex_form_types`) and for the new `semantic_domains`. Each follows the existing five-callback contract from `Lib/categories.py`.
- **FR-324**: The five existing COMPLETE callbacks (gram_categories, inflection_features, inflection_classes, stem_names, exception_features) MUST continue to honor GOLD inviolability per FR-022. Phase 3b makes no changes to GOLD handling beyond confirming each category's `plan_action` already emits `Skip(GOLD_INVIOLABLE)` for catalog-backed pieces.
- **FR-325**: Custom-field transfer MUST preserve the field's target class (LexEntry / LexSense / MoForm / etc.) and value type. A custom field defined on LexEntry in source MUST land on LexEntry in target — no class-rebinding.
- **FR-326**: Semantic-domain transfer MUST distinguish standard FW catalog domains (skip per `GOLD_INVIOLABLE`) from project-specific custom additions (transfer with source GUID).
- **FR-327**: Variant-Type transfer MUST detect any referenced inflection-feature constraint and emit `Skip(DEPENDENCY_UNRESOLVED)` when the referenced feature is not present in target nor in the same plan's in-flight inflection-features actions.
- **FR-328**: Phase 1 overwrite semantics (FR-101..110) MUST apply to all nine Phase 3b categories without modification. When `enable_overwrite=True` and a piece already exists in target by GUID, the planner emits a `PlannedOverwrite`; execute applies source's syncable properties and stamps the residue tag per FR-106 snapshot.
- **FR-329**: Phase 2 interactive merge (FR-201..217) MUST apply to all nine Phase 3b categories. Per-field conflicts surface as `ConflictPrompt`s in the standard flow.
- **FR-330**: Each in-scope category MUST honor the FR-308 skip-empty UX: when source has zero items, `render_text_summary` emits `[skip] no items in source for X`. The Phase 3a `empty_categories` mechanism on `RunReport` is reused.
- **FR-331**: Phase 3b MUST NOT modify the existing Phase 0/1/2/3a execution paths. The new categories run as additional categories in the existing `build_run_plan` / `execute` flow; no Phase 0/1/2/3a code paths are removed or restructured.
- **FR-332**: All factories used by Phase 3b's three new category implementations MUST be MCP-probed at planning time to confirm `Create(Guid)` support, mirroring the Phase 3a foundational MCP probes (T004-T009). Factories lacking Guid-overloads fail loud per `_create_with_guid` / `_safe_add_to_owner`.

### Key Entities *(include if feature involves data)*

- **Part of Speech**: A grammatical category (Verb, Noun, Adjective, ...) hierarchically arranged under `LangProject.PartsOfSpeechOA.PossibilitiesOS`. Carries the inflection-class hierarchy, affix-slot inventory, affix-template list, exception-feature bearings, and stem-name list. GOLD-aware via `CatalogSourceId`.
- **Inflection Feature**: A closed set of inflection-feature values (e.g., "Tense" feature with values "Past", "Present", "Future"). Owned by `MsFeatureSystemOA.FeaturesOC`. GOLD-aware.
- **Custom Field**: A project-defined extension to a built-in LCM class (LexEntry, LexSense, etc.), carrying a name + target class + value type. Persisted at the project level.
- **Inflection Class**: A grouping of stems that share an inflectional paradigm (e.g., "first conjugation", "irregular"). Owned by a POS via `InflectionClassesOC`.
- **Stem Name**: A naming convention for inflected stems within an inflection class (e.g., "infinitive", "perfect stem"). Owned by a POS via `StemNamesOC`.
- **Exception Feature**: A reference from a POS's `BearableFeaturesRC` to a specific `IFsSymFeatVal` value, used to mark POSes that bear unusual features (e.g., a POS that bears "dual" number without having a full dual paradigm).
- **Variant Type**: A category for entry variants (e.g., "Past Tense Variant", "Dialect Variant"). Owned by `LexDbOA.VariantEntryTypesOA.PossibilitiesOS`. May carry feature constraints referencing inflection features.
- **Complex Form Type**: A category for complex entries (e.g., "Compound", "Idiom", "Phrasal Verb"). Owned by `LexDbOA.ComplexEntryTypesOA.PossibilitiesOS`.
- **Semantic Domain**: A topical classification for senses (e.g., "Animal", "Color", "Kinship"). Owned by `LangProject.SemanticDomainListOA.PossibilitiesOS`. Standard FW catalog ships ~1700 entries; project-specific additions are GOLD-distinguished.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-321**: A linguist transferring a 2-POS hierarchy with 30 inflection features, 10 inflection classes, 6 stem names, 4 exception-feature bearings, 3 custom fields, 4 variant types, 2 complex form types, and 5 custom semantic domains completes the transfer in under 5 seconds wall-clock.
- **SC-322**: 100% of non-GOLD pieces carry source GUIDs into target on first run. 100% of GOLD pieces (catalog-backed) skip with `GOLD_INVIOLABLE` and are not duplicated.
- **SC-323**: After Phase 3b ships, Phase 3c (LexEntries) can reference any Phase 3b-transferred inflection class, stem name, variant type, complex form type, or custom semantic domain without `DEPENDENCY_UNRESOLVED` — the references resolve by GUID at plan time.
- **SC-324**: Zero source items silently dropped: every object enumerated by a category's `enumerate_source` lands as `PlannedAction`, `PlannedOverwrite`, or `Skip` (with explicit reason). Audited via FR-018 invariant on `RunReport`.
- **SC-325**: 305 Phase 0/1/2/3a passing tests continue to pass without modification. Phase 3b adds new unit + integration tests bringing the suite to a target of ~340 passing tests.
- **SC-326**: A linguist who selects ONLY the Phase 3b nine categories (un-ticking all others) leaves the lexicon, morphology beyond POS / inflection classes, phonology, and texts of the target project bit-identical to their pre-transfer state.

## Assumptions

- The flexlibs2 fork at `D:/Github/_Projects/_LEX/flexlibs2` exposes Operations classes (or accessible factories) for all nine Phase 3b categories: `project.GramCat`, `project.InflectionFeatures` (with `InflectionClassGetAll`), `project.POS` (with `InflectionClassesOC` / `StemNamesOC` / `BearableFeaturesRC`), plus whatever surface flexlibs2 provides for CustomFields, VariantTypes, ComplexFormTypes, and SemanticDomains. The exact accessor names will be MCP-probed at planning time and recorded in `probe-results.md`.
- Five of the nine callbacks (gram_categories, inflection_features, inflection_classes, stem_names, exception_features) are already implemented in `Lib/categories.py` and were hardened in commit 3863ed2 with `_safe_add_to_owner`. Phase 3b reuses them as-is — no modifications beyond extending the leaf-dispatch tuple.
- All factories used by the new category implementations support `Create(Guid)` overloads (per the Phase 3a foundational MCP probe pattern). If any factory lacks this, the implementation fails loud via `_create_with_guid` / `_safe_add_to_owner` — same fail-loud contract as Phase 3a.
- The Phase 2 `phase2_interactive_move()` helper extends transparently to the new categories: no new wiring at the MainFunction level beyond enabling the categories in the default Selection dict.
- Constitution v5.0.0 Principle II (flexlibs2-Direct) — all new code imports flexlibs2 directly. No flavor-adapter shape introduced.
- Constitution Principle IV (Phased Merge Discipline) — Phase 3b layers on top of Phases 0+1+2+3a; no earlier-phase path is removed.
- Standard FW catalog detection uses `CatalogSourceId` non-empty (already the GOLD heuristic per `_is_gold` in `Lib/categories.py`). Phase 3b assumes this is reliable for all nine categories; the existing five COMPLETE callbacks already rely on it.
- POS hierarchy depth is bounded in practice (linguistic projects rarely exceed 3-4 levels). The recursive `GetAll(recursive=True)` enumeration is acceptable.
- Custom-field VALUES on entries/senses are out of Phase 3b scope; only the field DEFINITIONS transfer here. Per-entry custom-field values transfer in Phase 3c with the LexEntries.

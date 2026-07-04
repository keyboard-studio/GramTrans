# Phase 3b Research: Inflection / Lexicon-Prep Block

**Status**: Phase 0 of `/speckit-plan`. Resolves NEEDS CLARIFICATION items from `plan.md` Technical Context. Live MCP probe results land in `probe-results.md` during the implementation tasks (T002-T010 equivalents).

## Decision: Reuse Phase 3a `_LEAF_DISPATCH_CATEGORIES` plumbing verbatim

**Decision**: Extend the `_LEAF_DISPATCH_CATEGORIES` tuple in both [Lib/preview.py](../../src/gramtrans/Lib/preview.py) and [Lib/transfer.py](../../src/gramtrans/Lib/transfer.py) to include the nine Phase 3b categories. No new dispatch machinery.

**Rationale**: Phase 3a's leaf-dispatch loop is exactly the shape Phase 3b needs — each category contributes a 5-callback registry entry and the loop iterates them in `GrammarCategory.value` order. The five COMPLETE callbacks (gram_categories, inflection_features, inflection_classes, stem_names, exception_features) are already in tree from Phase 0 and were hardened in commit 3863ed2. The four new callback sets (custom_fields, variant_types, complex_form_types, semantic_domains) slot into the same registry.

**Alternatives considered**:
- *Phase 3a's six categories as a "phonology phase" tuple, Phase 3b as a separate "inflection phase" tuple* — rejected because the leaf-dispatch loop has no phase concept; categories are independent and order through `GrammarCategory.value`.
- *Reintroduce the Phase 0 "POS pulled in by verb-vertical" shortcut* — rejected. The Phase 3a memo step 4b move of `PH_ENVIRONMENT` to LEAF established the rule: anything with no LexEntry closure dependency runs as a leaf. POS is the same shape.

## Decision: Custom fields use `MetaDataCacheAccessor.AddCustomField`, NOT a factory

**Decision**: Custom-field `execute_action` calls `project.Cache.MetaDataCacheAccessor.AddCustomField(class_id, field_name, field_type, ...)` rather than going through `_create_with_guid`. The planner emits a `PlannedAction` per custom field with the target class-id + name + value-type stashed in `action.payload`.

**Rationale**: Custom fields are not first-class LCM `ICmObject`s — they're virtual flids registered in the meta-data cache (MDC). There's no factory and no GUID; identity is `(class_id, name)`. The MDC creates a new flid integer on each `AddCustomField` call (no Guid-preservation concept). This is structurally analogous to Phase 3a's Strata, where `StratumOperations` doesn't exist and we fall back to `GetService(IMoStratumFactory)` — except for custom fields the fallback is even more direct (no factory at all).

**Alternatives considered**:
- *flexicon-side `CustomFieldOperations` wrapper* — would need to be added upstream first; not blocking for Phase 3b. The MDC call is one line; wrapping it doesn't simplify.
- *Preserve a "synthetic GUID" per custom field for residue identity* — rejected. The residue tag is per-LCM-object and custom fields aren't ICmObjects. Per-field re-run idempotency is checked by `(class_id, name)` match in `enumerate_source`.

## Decision: Variant-type and complex-form-type creation uses POSOperations-shaped wrappers

**Decision**: `variant_types_execute_action` and `complex_form_types_execute_action` create `ILexEntryType` via the flexicon wrapper on the LexDb. Probe at planning time to confirm the exact entry point — likely `project.LexEntryTypes` or `project.LexDb` has a typed factory. If no flexicon wrapper exists, fall back to `project.GetService(ILexEntryTypeFactory).Create(Guid)` per the Phase 3a strata pattern.

**Rationale**: Variant types and complex form types are both `ILexEntryType` instances with a discriminator (variant vs complex). They own `BackRefsRC` from LexEntries (back-references, not forward refs — Phase 3c LexEntries will reference these). Phase 3b creates the definitions; Phase 3c attaches the references.

**Alternatives considered**:
- *Treat variant and complex as a single category with a type field* — rejected. They have separate owning collections (`VariantEntryTypesOA.PossibilitiesOS` vs `ComplexEntryTypesOA.PossibilitiesOS`) and FR-327 puts the variant-type → inflection-feature dependency on variant types alone. Two categories cleaner.

## Decision: Semantic-domain GOLD detection via `CatalogSourceId` reuses `_is_gold`

**Decision**: `semantic_domains_plan_action` calls the existing `_is_gold(src_obj)` helper to detect standard FW catalog entries. Custom domains have `CatalogSourceId == ""` (or None); standard FW catalog domains have non-empty `CatalogSourceId` like `"SemDom-1.2.3"`.

**Rationale**: This mirrors POS / inflection-features GOLD detection — same heuristic. The FW catalog ships in target by canonical GUID, so we don't need to transfer the ~1700 standard entries; only project-specific additions transfer with source GUIDs.

**Alternatives considered**:
- *Check `OwningList.Name` against a whitelist of "this is the FW standard semantic-domain list"* — rejected. `CatalogSourceId` is the constitution's canonical GOLD signal (FR-022). Don't introduce a parallel detection path.

## Decision: Variant-type `dependencies` callback walks feature constraints

**Decision**: `variant_types_dependencies(src_obj)` returns `[(GrammarCategory.INFLECTION_FEATURES, fs_feat_val_guid) for fs_feat_val_guid in walk(src_obj.InflFeatsOS or related-feature-constraint-collection)]` when the variant type carries a feature constraint. Empty tuple when the variant type carries no feature constraint.

**Rationale**: FR-327 requires `Skip(DEPENDENCY_UNRESOLVED)` when a referenced inflection feature isn't present in target nor in-flight. The dependency callback feeds the planner's existing dependency-closure machinery (same shape as exception_features' POS + IFsSymFeatVal dependencies).

**Alternatives considered**:
- *Defer feature-constraint wiring to a post-pass* — rejected. The constraint is a forward reference to an existing IFsSymFeatVal; if it can be resolved at plan time we wire it then, same as exception features. No reason to defer.

## Decision: Five existing COMPLETE callbacks need ZERO modifications

**Decision**: Phase 3b's `categories.py` diff is purely additive (4 new registry entries + 1 enum addition). The five existing entries (gram_categories, inflection_features, inflection_classes, stem_names, exception_features) and their callback bodies are unchanged. Confirmation comes from running the existing Phase 0 unit suite + a new `test_phase3b_leaf_dispatch.py` integration test that drives the dispatch loop end-to-end on a fake LCM surface.

**Rationale**: 3863ed2 hardened all five with `_safe_add_to_owner`; FR-324 only requires they "continue to honor GOLD inviolability per FR-022," which they already do. Phase 3b adds dispatch wiring, not callback rewrites.

**Alternatives considered**:
- *Refactor the five existing callbacks to share a common base-class skeleton* — rejected. Premature abstraction; each category's enumerate/dependencies surface is distinct enough that the base-class would be mostly hooks. Leave as-is.

## Decision: MCP probes deferred to first implementation task block

**Decision**: Specific factory and accessor names for the three stubs + one new category are PROBED, not researched in this Phase 0 doc. Probes live in `tasks.md` as T002-T010 equivalents and results land in `probe-results.md`.

**Rationale**: Phase 3a established the pattern — `research.md` makes architectural decisions, `probe-results.md` captures the literal flexicon API surface for each factory. Keeps research stable (it doesn't change when flexicon ships a new wrapper) and probe results fresh (they reflect the current installed flexicon fork).

**Alternatives considered**:
- *Probe everything now during `/speckit-plan`* — rejected. MCP discovery is best done at task start with live FlexTools session warmth; the planner doesn't need the exact API names to commit to the design.

## Open questions deferred to Phase 1 (data-model.md)

- Custom-field value-type enumeration (Integer, MultiString, OwningAtomic, etc.) — documented in `data-model.md`'s Custom Field entity.
- Whether variant types carry both `InflFeatsOS` AND a separate inflection-feature back-link — surfaces in `data-model.md` Variant Type entity.
- Semantic-domain hierarchical depth and whether to enumerate recursively — `data-model.md` Semantic Domain entity.

## No NEEDS CLARIFICATION remaining

All Technical Context entries are concrete. The MCP probes during implementation are confirmations, not unresolved unknowns.

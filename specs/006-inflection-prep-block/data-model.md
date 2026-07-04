# Phase 3b Data Model: Inflection / Lexicon-Prep Block

**Status**: Phase 1 design output. Maps each Phase 3b category to its LCM type, owner, dependencies, and GOLD signal.

## Entities

### 1. Part of Speech (`gram_categories` — COMPLETE)

- **LCM type**: `IPartOfSpeech`
- **Owner**: `LangProject.PartsOfSpeechOA.PossibilitiesOS` (hierarchical — `SubPossibilitiesOS` for child POSes)
- **GOLD signal**: `CatalogSourceId` non-empty (e.g., FW's GOLD Verb has `"vrb"`)
- **Dependencies** (forward refs at plan time): none direct. Owns affix slots (#16), templates (#17), inflection classes (#9), stem names (#10), exception bearings (#11).
- **Status**: COMPLETE in [Lib/categories.py](../../src/gramtrans/Lib/categories.py); orphan-hardened in 3863ed2.

### 2. Inflection Feature (`inflection_features` — COMPLETE)

- **LCM type**: `IFsClosedFeature` (with owned `ValuesOC` of `IFsSymFeatVal`)
- **Owner**: `LangProject.MsFeatureSystemOA.FeaturesOC`
- **GOLD signal**: `CatalogSourceId` non-empty (FW's GOLD Tense, Aspect, etc.)
- **Dependencies**: none direct. Values (IFsSymFeatVal) are owned and travel with the feature.
- **Status**: COMPLETE; P0-A orphan-hardened in 3863ed2 (value-loop uses `_safe_add_to_owner`).

### 3. Custom Field (`custom_fields` — STUB to fill)

- **LCM type**: Virtual flid registered via `MetaDataCacheAccessor` — NOT a first-class `ICmObject`.
- **Owner**: The MDC itself; no owning collection.
- **GOLD signal**: N/A (custom fields are by definition non-catalog; users create them).
- **Identity**: `(class_id, name)` tuple. No GUID.
- **Fields**: target class-id (e.g., `LexEntryTags.kClassId`), name (string), value type (one of `CellarPropertyType.{String, MultiString, MultiUnicode, OwningAtomic, ...}`), help string (multistring), display label override (multistring), list ID (for `OwningAtomic`-typed fields pointing at a possibility list — Phase 3b sets to null when not applicable).
- **Validation rules**:
  - Target class-id must resolve in source's schema; emit `Skip(DEPENDENCY_UNRESOLVED)` otherwise.
  - Value type must be one of the supported MDC types; otherwise emit `Skip(DEPENDENCY_UNRESOLVED)`.
  - If a custom field with the same `(class_id, name)` already exists in target, treat as already-synced (no `PlannedAction`).
- **Status**: STUB. Implementation uses `MetaDataCacheAccessor.AddCustomField(...)`.

### 4. Inflection Class (`inflection_classes` — COMPLETE)

- **LCM type**: `IMoInflClass`
- **Owner**: `IPartOfSpeech.InflectionClassesOC` (each class owned by its POS)
- **GOLD signal**: typically none (inflection classes are user-defined per project); inherit `_is_gold` check defensively.
- **Dependencies**: POS owner must exist (planner emits the owning POS first if not present in target).
- **Status**: COMPLETE; P0-C orphan-hardened in 3863ed2.

### 5. Stem Name (`stem_names` — COMPLETE)

- **LCM type**: `IMoStemName`
- **Owner**: `IPartOfSpeech.StemNamesOC`
- **GOLD signal**: typically none.
- **Dependencies**: POS owner.
- **Status**: COMPLETE; P0-D orphan-hardened in 3863ed2.

### 6. Exception Feature (`exception_features` — COMPLETE)

- **LCM type**: Reference from `IPartOfSpeech.BearableFeaturesRC` to `IFsSymFeatVal`
- **Owner**: the POS owns the RC collection; values themselves are owned by the inflection feature.
- **GOLD signal**: skip when the underlying value carries `CatalogSourceId` (rare — GOLD values bear standard features).
- **Dependencies**: POS (#1) + IFsSymFeatVal (#2). Compound identity `(pos_guid, val_guid)`.
- **Status**: COMPLETE.

### 7. Variant Type (`variant_types` — STUB to fill)

- **LCM type**: `ILexEntryType` (with `VariantTypeTags.kClassId` discriminator)
- **Owner**: `LangProject.LexDbOA.VariantEntryTypesOA.PossibilitiesOS` (hierarchical — `SubPossibilitiesOS`)
- **GOLD signal**: `CatalogSourceId` non-empty (FW ships some standard variant types like "Spelling Variant").
- **Fields**: Name (multistring), Abbreviation (multistring), ReverseName (multistring), ReverseAbbr (multistring), Description (multistring), InflFeatsOS (owned collection of `IFsFeatStruc` feature constraints — may be empty).
- **Dependencies**: When `InflFeatsOS` is non-empty, each constraint references one or more `IFsSymFeatVal` — those must exist in target or be in-flight in the same plan (FR-327).
- **Status**: STUB.

### 8. Complex Form Type (`complex_form_types` — STUB to fill)

- **LCM type**: `ILexEntryType` (with `ComplexFormTypeTags` discriminator, or the shared `ILexEntryType` interface in flexicon)
- **Owner**: `LangProject.LexDbOA.ComplexEntryTypesOA.PossibilitiesOS`
- **GOLD signal**: `CatalogSourceId` non-empty (FW ships "Compound", "Idiom", "Phrasal Verb" etc.).
- **Fields**: Name, Abbreviation, ReverseName, ReverseAbbr, Description (all multistring). No feature constraints.
- **Dependencies**: none direct.
- **Status**: STUB.

### 9. Semantic Domain (`semantic_domains` — NEW enum + callbacks)

- **LCM type**: `ICmSemanticDomain`
- **Owner**: `LangProject.SemanticDomainListOA.PossibilitiesOS` (hierarchical)
- **GOLD signal**: `CatalogSourceId` non-empty — FW ships the ~1700-entry standard catalog with `CatalogSourceId` like `"SemDom-1.2.3"`. Custom domains have empty `CatalogSourceId`.
- **Fields**: Name, Abbreviation, Description (multistring), QuestionsOS (owned), SubPossibilitiesOS (recursive).
- **Dependencies**: hierarchical parent if nested under another custom domain. Standard catalog parents are skipped per GOLD but already exist in target by canonical GUID, so child-of-standard resolves at execute time.
- **Status**: NEW. Adds `SEMANTIC_DOMAINS` member to `GrammarCategory` enum + 5 callbacks.

## Dependency graph (Phase 3b internal)

```
   gram_categories (POS)
        |
        +---> inflection_classes  (owned)
        +---> stem_names          (owned)
        +---> exception_features  (refs IFsSymFeatVal)
                       ^
                       |
              inflection_features (owns IFsSymFeatVals)
                       ^
                       |
              variant_types (when InflFeatsOS non-empty -- FR-327)

   custom_fields         -- independent leaf
   complex_form_types    -- independent leaf
   semantic_domains      -- internal hierarchy + standard-catalog GOLD skip
```

## Identity & GUID preservation

- All 8 ICmObject-shaped categories preserve source GUID via `_create_with_guid` when the factory supports `Create(Guid)`. Identity remap (FR-303) is the fallback.
- Custom fields have no GUID; identity is `(class_id, name)`.
- Standard FW catalog GOLD entries (POS, inflection features, variant types, complex form types, semantic domains, sometimes more) are NEVER created on target — they ship with FieldWorks. Plans emit `Skip(GOLD_INVIOLABLE)`.

## RunReport coverage

Each of the nine categories appears in `report.per_category` when active. FR-330 + Phase 3a's `empty_categories` mechanism surfaces selected-but-empty categories as `[skip] no items in source for X` lines in `render_text_summary`.

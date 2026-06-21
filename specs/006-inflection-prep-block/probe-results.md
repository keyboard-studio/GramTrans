# Phase 3b MCP Probe Results

**Date**: 2026-06-21
**Project**: Ejagham Full GT-Test (read-only)
**Session**: `flextools_start(api_mode=flexlibs2)`

Records the literal flexlibs2 / LCM 9.x API surface for each factory and
accessor used by Phase 3b implementations (T004-T008).

## T004 — ICmPossibilityFactory + IPartOfSpeechFactory

Both support **Guid + parent-overload**. No Guid-less Create surface —
factories are Guid-mandatory (mirrors Phase 3a phon-feature factories).

### `ICmPossibilityFactory`

```text
Create(Guid guid, ICmPossibilityList owner)
Create(Guid guid, ICmPossibility owner)        # hierarchical parent
```

### `IPartOfSpeechFactory`

```text
Create(Guid guid, ICmPossibilityList owner)
Create(Guid guid, IPartOfSpeech owner)         # hierarchical parent
```

**Implication**: `_create_with_guid` works directly. The 2-arg form (the
owner is the second positional) requires picking the right parent type
per call site:
- Top-level POS / possibility: pass `LangProject.PartsOfSpeechOA` (an
  `ICmPossibilityList`).
- Nested under another POS: pass the parent `IPartOfSpeech`.

## T005 — MetaDataCacheAccessor.AddCustomField

`IFwMetaDataCacheManaged.AddCustomField` returns `Int32` (the new flid).
Two overloads:

```text
AddCustomField(String className,
               String fieldName,
               CellarPropertyType fieldType,
               Int32 destinationClass)
                                              # short form

AddCustomField(String className,
               String fieldName,
               CellarPropertyType fieldType,
               Int32 destinationClass,
               String fieldHelp,
               Int32 fieldWs,
               Guid fieldListRoot)
                                              # full form
```

**Implication**:
- Custom-field creation goes through the long-form overload when help
  text, default WS, or list-root GUID is non-default.
- Return type is the flid integer; `0` is the documented failure signal
  (treat as `RuntimeError` per contracts/custom-field-creation.md).
- `destinationClass` is the int32 class-id (e.g., `LexEntryTags.kClassId`)
  — NOT a `Guid`.
- `fieldType` is the `CellarPropertyType` enum (String / MultiString /
  MultiUnicode / OwningAtomic / etc.).
- The CellarPropertyType enum lives in `SIL.LCModel.Core.Cellar`; import
  via `from SIL.LCModel.Core.Cellar import CellarPropertyType`.

**Note**: `CustomFlid` is NOT a property surface; custom-field
enumeration uses MDC methods (`GetFieldIds`, `IsCustom`,
`GetOwnClsId`, `GetFieldName`, `GetFieldType`, `GetFieldHelp`,
`GetFieldLabel`, `GetFieldListRoot`) per the
contracts/custom-field-creation.md source-side recipe.

## T006 — ILexEntryTypeFactory / ILexEntryInflTypeFactory

The discovery surface reports `ILexEntryTypeFactory` and
`ILexEntryInflTypeFactory` as **0-method stubs** in the MCP catalogue.
This is the expected pythonnet behaviour for factories whose `Create`
methods are inherited from a base interface. The actual creation surface
is on `ICmPossibilityFactory` (which `LexEntryTypeFactory` derives from)
plus the typed `Create<T>` extension that LCM provides at runtime.

**Working implementation pattern** (mirrors Phase 3a strata fallback):

```python
# variant types
from SIL.LCModel import ILexEntryInflType
factory = project.Cache.ServiceLocator.GetInstance[ILexEntryInflTypeFactory]()
obj = factory.Create(src_guid, owner_list_or_parent_type)
```

For **complex form types**, FLEx uses the base `ILexEntryType` (not the
`InflType` subclass). Confirmed: `ILexEntryInflType` carries
`InflFeatsOA` (the variant-only feature-constraint owning-atomic),
which the base `ILexEntryType` lacks.

**Owning collections**:
- `project.LexDb.VariantEntryTypesOA.PossibilitiesOS` — variant types
  hierarchically owned.
- `project.LexDb.ComplexEntryTypesOA.PossibilitiesOS` — complex form
  types hierarchically owned.
- Nested types use the parent's `SubPossibilitiesOS`.

## T007 — ICmSemanticDomainFactory

Same shape as `IPartOfSpeechFactory`:

```text
Create(Guid guid, ICmPossibilityList owner)
Create(Guid guid, ICmSemanticDomain owner)     # hierarchical parent
```

**Implication**: `_create_with_guid` applies directly; pick
`LangProject.SemanticDomainListOA` (list owner) or parent
`ICmSemanticDomain` per nesting level. GOLD entries (CatalogSourceId
non-empty) skip per `_is_gold`; only custom domains call the factory.

## T008 — Variant-Type InflFeats constraint walk

`ILexEntryInflType` carries `InflFeatsOA` — Owning Atomic, NOT Owning
Sequence (the spec draft was wrong about plurality).

```text
ILexEntryInflType.InflFeatsOA -> IFsFeatStruc  (single owned struct)
IFsFeatStruc.FeatureSpecsOC   -> IFsFeatureSpecification  (OC of specs)
IFsFeatStruc.FeatureDisjunctionsOC -> IFsFeatStrucDisj  (OC of disjuncts)
```

Each `IFsFeatureSpecification` carries the feature reference (typically
via subclass `IFsClosedValue.FeatureRA` + `ValueRA` pointing at
`IFsSymFeatVal`). The variant-type `dependencies` callback walks
`InflFeatsOA.FeatureSpecsOC` and emits `(INFLECTION_FEATURES, guid)`
per `ValueRA.Guid` found.

**Concrete dependency-walk shape**:

```python
def variant_types_dependencies(src_obj):
    struct = src_obj.InflFeatsOA
    if struct is None:
        return ()
    deps = []
    for spec in struct.FeatureSpecsOC:
        val = getattr(spec, "ValueRA", None)
        if val is not None and val.Guid is not None:
            deps.append((GrammarCategory.INFLECTION_FEATURES, str(val.Guid)))
    return tuple(deps)
```

## Phase 3b reuse audit (T009 deliverable, recorded here)

The five COMPLETE callbacks confirmed present in
[Lib/categories.py](../../src/gramtrans/Lib/categories.py) with full
5-callback registry entries (orphan-hardened in 3863ed2):

| Category | enumerate | dependencies | required_ws | plan_action | execute_action | Notes |
|----------|-----------|--------------|-------------|-------------|----------------|-------|
| `gram_categories` | yes | yes | yes | yes | yes | P0-B hardened |
| `inflection_features` | yes | yes | yes | yes | yes | P0-A hardened |
| `inflection_classes` | yes | yes | yes | yes | yes | P0-C hardened |
| `stem_names` | yes | yes | yes | yes | yes | P0-D hardened |
| `exception_features` | yes | yes | yes | yes | yes | compound `(pos, val)` ident |

Phase 3b adds no edits to these callbacks; T010 verifies regression via
existing Phase 0 unit suite.

## Summary

| Probe | Status | Key Finding |
|-------|--------|-------------|
| T004 | OK | POS + CmPossibility factories: `Create(Guid, parent)` -- Guid-mandatory, parent dispatches on list vs hierarchical |
| T005 | OK | `AddCustomField` returns flid:Int32; 0 == fail-loud |
| T006 | OK | LexEntryType factories accessed via `ServiceLocator.GetInstance[T]()` (factory MCP entries are 0-method stubs); ILexEntryInflType for variants, ILexEntryType for complex |
| T007 | OK | SemanticDomainFactory: same Guid+parent shape as POS |
| T008 | OK | InflFeatsOA is Owning Atomic (not OS); walk `FeatureSpecsOC -> ValueRA.Guid` |

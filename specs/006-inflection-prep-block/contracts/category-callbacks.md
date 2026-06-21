# Contract: Category Callbacks — Phase 3b

Five-callback shape for each new / new-enum category. The five existing
COMPLETE callbacks (gram_categories, inflection_features,
inflection_classes, stem_names, exception_features) already match this
shape and are not re-specified here — see [Lib/categories.py](../../../src/gramtrans/Lib/categories.py).

## Callback signatures (recap from Phase 3a)

```python
def enumerate_source(project: FLExProject, ctx: PlanContext) -> Iterable[Any]:
    """Yield each source LCM object (or non-ICmObject record) in this
    category that's a candidate for transfer. MUST NOT write."""

def dependencies(src_obj) -> Iterable[tuple[GrammarCategory, str]]:
    """Yield (referenced_category, referenced_guid) tuples that must
    exist in target before this object can be planned. Empty tuple
    when this category is a pure leaf for the current object."""

def required_writing_systems(src_obj) -> Iterable[str]:
    """Yield WS ICU-locale codes that this object's multistring fields
    use. Drives the WS-mapping wizard at Phase 2."""

def plan_action(src_obj, planner: Planner) -> PlannedAction | Skip:
    """Decide PlannedAction / PlannedOverwrite / Skip. Read-only on
    target. GOLD detection via _is_gold; existing-by-GUID detection
    via planner's target index."""

def execute_action(action: PlannedAction, ctx: RunContext) -> None:
    """Apply the action against target. Uses _create_with_guid /
    _safe_add_to_owner from categories.py. Wraps in fail-loud per
    constitution Principle II."""
```

## custom_fields (STUB to fill)

```python
def enumerate_source(project, ctx):
    """Iterate project.Cache.MetaDataCacheAccessor.GetFieldIds(),
    filtering by IsCustom(flid). Yield a CustomFieldRecord dataclass
    capturing (class_id, name, type, help, label_override, list_id)."""

def dependencies(src_record):
    """Empty for now -- custom-field semantic-domain list references
    deferred to a post-pass when semantic_domains have been
    transferred."""
    return ()

def required_writing_systems(src_record):
    """Yield WS codes used by the help / label_override multistrings."""

def plan_action(src_record, planner):
    """If (class_id, name) already exists in target MDC, return None
    (already synced -- not a Skip, just nothing to do). Else
    PlannedAction with payload=src_record."""

def execute_action(action, ctx):
    """Call ctx.target_project.Cache.MetaDataCacheAccessor
    .AddCustomField(class_id, name, type, ...) inside a fail-loud
    try/except. No _create_with_guid; no Add-to-owner."""
```

## variant_types (STUB to fill)

```python
def enumerate_source(project, ctx):
    """Recursively walk project.LexDb.VariantEntryTypesOA
    .PossibilitiesOS + SubPossibilitiesOS. Yield each ILexEntryType."""

def dependencies(src_obj):
    """For each IFsFeatStruc in src_obj.InflFeatsOS, yield
    (INFLECTION_FEATURES, guid) for each referenced IFsSymFeatVal.
    Empty when InflFeatsOS is empty -- FR-327."""

def required_writing_systems(src_obj):
    """Yield WS codes for Name, Abbreviation, ReverseName, ReverseAbbr,
    Description multistrings."""

def plan_action(src_obj, planner):
    """_is_gold -> Skip(GOLD_INVIOLABLE).
    existing-by-GUID + enable_overwrite=False -> Skip(ALREADY_SYNCED).
    existing-by-GUID + enable_overwrite=True -> PlannedOverwrite.
    else -> PlannedAction with parent_guid in payload for hierarchical
    placement."""

def execute_action(action, ctx):
    """_create_with_guid(factory, src_guid) -> _safe_add_to_owner into
    parent's SubPossibilitiesOS or root VariantEntryTypesOA
    .PossibilitiesOS. Apply syncable props (Name, Abbrs, Description).
    InflFeatsOS wiring deferred to post-pass when target's
    IFsSymFeatVals are known to exist."""
```

## complex_form_types (STUB to fill)

```python
def enumerate_source(project, ctx):
    """Recursively walk project.LexDb.ComplexEntryTypesOA
    .PossibilitiesOS. Yield each ILexEntryType."""

def dependencies(src_obj):
    return ()  # leaf

def required_writing_systems(src_obj):
    """Multistring WS codes for Name, Abbreviation, etc."""

def plan_action(src_obj, planner):
    """Same GOLD + existing + overwrite shape as variant_types."""

def execute_action(action, ctx):
    """_create_with_guid + _safe_add_to_owner into
    ComplexEntryTypesOA.PossibilitiesOS or parent's
    SubPossibilitiesOS."""
```

## semantic_domains (NEW)

```python
def enumerate_source(project, ctx):
    """Recursively walk project.LangProject.SemanticDomainListOA
    .PossibilitiesOS + SubPossibilitiesOS. Yield each
    ICmSemanticDomain."""

def dependencies(src_obj):
    return ()  # parent links resolve at execute time

def required_writing_systems(src_obj):
    """WS codes for Name, Abbreviation, Description."""

def plan_action(src_obj, planner):
    """_is_gold -> Skip(GOLD_INVIOLABLE) -- the ~1700-entry FW catalog
    sieves out here. Custom domains land as PlannedAction with
    parent_guid in payload."""

def execute_action(action, ctx):
    """_create_with_guid + _safe_add_to_owner under parent
    (existing-in-target ICmSemanticDomain) or root
    SemanticDomainListOA.PossibilitiesOS."""
```

## Wiring (preview.py + transfer.py)

```python
# Lib/preview.py and Lib/transfer.py
_LEAF_DISPATCH_CATEGORIES = (
    # Phase 3a (already in tree, commit 608b72c)
    GrammarCategory.PHONOLOGICAL_FEATURES,
    GrammarCategory.PHONEMES,
    GrammarCategory.NATURAL_CLASSES,
    GrammarCategory.PH_ENVIRONMENT,
    GrammarCategory.PHONOLOGICAL_RULES,
    GrammarCategory.STRATA,
    # Phase 3b additions
    GrammarCategory.GRAM_CATEGORIES,
    GrammarCategory.INFLECTION_FEATURES,
    GrammarCategory.CUSTOM_FIELDS,
    GrammarCategory.INFLECTION_CLASSES,
    GrammarCategory.STEM_NAMES,
    GrammarCategory.EXCEPTION_FEATURES,
    GrammarCategory.VARIANT_TYPES,
    GrammarCategory.COMPLEX_FORM_TYPES,
    GrammarCategory.SEMANTIC_DOMAINS,
)
```

Order within the tuple is for readability — actual dispatch sorts by
`GrammarCategory.value` (the enum's declaration order maintained by
[Lib/models.py](../../../src/gramtrans/Lib/models.py)).

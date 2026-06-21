"""Leaf-category transfer functions (T039 — consolidated under v5.0.0).

This module hosts the per-category transfer surface for **leaf** FR-004
categories (no recursive closure of their own). Per the v5.0.0 layout, only
the heavy categories (affixes, templates, MSAs) get dedicated files; the rest
share this single module to keep boilerplate down.

Each category exposes the contract from
`specs/001-phase0-additive-transfer/contracts/category-transfer.md`:
- `enumerate_source(context, selection) → Iterable[SourcePiece]`
- `dependencies(piece) → Iterable[Ref]`  (empty for leaf categories)
- `required_writing_systems(piece) → Iterable[(ws_id, WSKind)]`
- `plan_action(piece, context, ws_mapping) → PlannedAction | Skip`
- `execute_action(action, context, ws_mapping, residue_tag) → ExecutionResult`

Implementation status (2026-06-20):
- `gram_categories`, `inflection_features`, `inflection_classes`,
  `stem_names`, `exception_features` are fully implemented (T039).
- `custom_fields`, `variant_types`, `complex_form_types`, `adhoc_rules`,
  `compound_rules` retain NotImplementedError stubs pending dedicated tasks.

GOLD check (Principle I, FR-022):
  A piece whose `CatalogSourceId` attribute is non-empty is a GOLD object.
  `plan_action` yields `Skip(GOLD_INVIOLABLE)` for such pieces; references
  *to* GOLD objects are not skips — they are resolved refs.

LCM API notes (discovered during implementation):
  - `IFsFeatStrucTypeFactory.Create(Guid)` is available for gram_categories.
    Top-level cats live in MsFeatureSystemOA.TypesOC; sub-cats in
    parent.SubPossibilitiesOS and use ICmPossibilityFactory.Create(Guid).
  - `IFsClosedFeatureFactory.Create(Guid, featureSystem)` (2-arg) is
    attempted first for inflection_features; Path B falls back to
    `Create(Guid)` + `FeaturesOC.Add()` per fork pattern in
    InflectionFeatureOperations._factory_create_attached.
  - `IMoInflClassFactory` and `IMoStemNameFactory` both support
    `Create(Guid)` — confirmed by transfer.py slot/template precedent.
  - `exception_features` in FLEx are `IFsSymFeatVal` items referenced by
    `IPartOfSpeech.ExceptionFeaturesOC`. A full transfer requires the
    source value GUID to already exist in the target (via inflection_features
    closure). The execute_action wires the target value into the target
    POS.ExceptionFeaturesOC by GUID lookup; it does NOT create new
    IFsSymFeatVal objects — those come from inflection_features.
"""
from __future__ import annotations

from typing import Iterable, Tuple

if __package__:
    from .models import (
        GrammarCategory,
        PlannedAction,
        RunContext,
        Selection,
        Skip,
        SkipReason,
        WSKind,
        WSMapping,
    )
    from .residue import ImportResidueTag
else:
    from models import (  # type: ignore
        GrammarCategory,
        PlannedAction,
        RunContext,
        Selection,
        Skip,
        SkipReason,
        WSKind,
        WSMapping,
    )
    from residue import ImportResidueTag  # type: ignore


# ============================================================================
# Shared GOLD-check helper
# ============================================================================

def _is_gold(obj) -> bool:
    """Return True iff `obj` is a GOLD LCM object.

    GOLD objects carry a non-empty `CatalogSourceId` string attribute
    (validated per research.md R6 and spec.md FR-022).  The attribute is
    defined on IFsClosedFeature, IFsFeatStrucType (gram categories), and
    related catalog-backed types.  A missing or empty value means the
    object was created by the user, not from the FW/MGA catalog.
    """
    try:
        csi = getattr(obj, "CatalogSourceId", None)
        return bool(csi)
    except Exception:
        return False


def _guid_str_from(obj) -> str:
    """Extract a lower-cased GUID string from an LCM object.

    Uses ICmObject cast (same pattern as transfer.py).  Falls back to
    `obj.guid` for fake/duck-typed test objects.
    """
    try:
        from SIL.LCModel import ICmObject  # lazy — not available in unit tests
        return str(ICmObject(obj).Guid).lower()
    except Exception:
        return str(getattr(obj, "guid", "")).lower()


def _target_has_guid(target_iter, src_guid: str) -> bool:
    """Return True iff any object in `target_iter` has `src_guid`."""
    for obj in target_iter:
        if _guid_str_from(obj) == src_guid:
            return True
    return False


# ============================================================================
# Per-category surfaces
# ============================================================================
#
# Naming: `<category>_<verb>(...)`. Each block groups one category's five
# functions for readability.

# ----- gram_categories (GOLD-aware) ----------------------------------------
#
# Gram categories in LCM are IFsFeatStrucType objects (top-level) and
# ICmPossibility objects (sub-categories).  They live under
# LangProject.MsFeatureSystemOA.TypesOC (and TypesOC[*].SubPossibilitiesOS
# recursively).  The flexlibs2 accessor is `project.GramCat`.

def gram_categories_enumerate_source(context: RunContext, selection: Selection):
    """Walk source.GramCat.GetAll() and yield each category."""
    source = context.source_handle
    if not hasattr(source, "GramCat"):
        return ()
    return list(source.GramCat.GetAll(recursive=True))


def gram_categories_dependencies(piece):
    return ()  # leaf


def gram_categories_required_writing_systems(piece) -> Iterable[Tuple[str, WSKind]]:
    """Gram categories have Name, Abbreviation, Description (analysis WS)."""
    # Phase 0: analysis WS only.  The caller's WS mapping step handles
    # the actual mapping; here we just signal "I need analysis WS".
    # Return empty — the engine enforces WS mapping at the plan level.
    return ()


def gram_categories_plan_action(piece, context: RunContext, ws_mapping: WSMapping):
    """GOLD-aware: skip if the category IS a GOLD object; else plan Add."""
    if _is_gold(piece):
        return Skip(
            category=GrammarCategory.GRAM_CATEGORIES,
            source_guid=_guid_str_from(piece),
            reason=SkipReason.GOLD_INVIOLABLE,
            detail=(
                f"Gram category is a GOLD object (CatalogSourceId="
                f"{getattr(piece, 'CatalogSourceId', '?')!r}); "
                "not transferred per FR-022 / Principle I."
            ),
        )
    src_guid = _guid_str_from(piece)
    # Check whether the target already has this GUID.
    target = context.target_handle
    if hasattr(target, "GramCat"):
        if _target_has_guid(target.GramCat.GetAll(recursive=True), src_guid):
            return Skip(
                category=GrammarCategory.GRAM_CATEGORIES,
                source_guid=src_guid,
                reason=SkipReason.ALREADY_PRESENT_BY_GUID,
                detail=f"Gram category GUID {src_guid[:8]}... already present in target.",
            )
    return PlannedAction(
        category=GrammarCategory.GRAM_CATEGORIES,
        source_guid=src_guid,
        intended_target_guid=src_guid,
        summary=f"GramCategory guid={src_guid[:8]}...",
    )


def gram_categories_execute_action(action: PlannedAction, context: RunContext, ws_mapping: WSMapping, tag: ImportResidueTag):
    """Create a gram category in the target with GUID preserved.

    Top-level cats use IFsFeatStrucTypeFactory.Create(Guid);
    sub-cats use ICmPossibilityFactory.Create(Guid) + Add to parent.SubPossibilitiesOS.
    ApplySyncableProperties syncs Name/Abbreviation/Description.
    Carrier B residue via apply_carrier_b (Description-append).
    """
    from SIL.LCModel import ICmPossibilityFactory, IFsFeatStrucTypeFactory
    from System import Guid as DotNetGuid

    if __package__:
        from .residue import apply_carrier_b
    else:
        from residue import apply_carrier_b  # type: ignore

    source = context.source_handle
    target = context.target_handle
    src_guid = action.source_guid

    # Find the source object.
    src_obj = None
    for cat in source.GramCat.GetAll(recursive=True):
        if _guid_str_from(cat) == src_guid:
            src_obj = cat
            break
    if src_obj is None:
        return None  # Source vanished; caller should warn.

    cache = getattr(target, "Cache")
    ws = cache.DefaultAnalWs
    feature_system = cache.LangProject.MsFeatureSystemOA

    parsed_guid = DotNetGuid.Parse(src_guid)

    # Determine parent: if the source object's owner is a possibility
    # (not the feature system itself), it's a sub-category.
    src_owner = getattr(src_obj, "Owner", None)
    is_subcategory = False
    src_owner_guid = None
    if src_owner is not None:
        try:
            from SIL.LCModel import ICmPossibility
            ICmPossibility(src_owner)  # will raise if not a possibility
            is_subcategory = True
            src_owner_guid = _guid_str_from(src_owner)
        except Exception:
            is_subcategory = False

    if is_subcategory and src_owner_guid:
        # Find the matching target parent.
        target_parent = None
        for cat in target.GramCat.GetAll(recursive=True):
            if _guid_str_from(cat) == src_owner_guid:
                target_parent = cat
                break
        if target_parent is None:
            return None  # Owner not in target; skip.
        sl = cache.LangProject.Cache.ServiceLocator if hasattr(cache.LangProject, "Cache") else cache.ServiceLocator
        factory = sl.GetService(ICmPossibilityFactory)
        new_cat = factory.Create(parsed_guid)
        target_parent.SubPossibilitiesOS.Add(new_cat)
    else:
        # Top-level: TypesOC requires IFsFeatStrucType.
        sl = cache.ServiceLocator
        factory = sl.GetService(IFsFeatStrucTypeFactory)
        new_cat = factory.Create(parsed_guid)
        feature_system.TypesOC.Add(new_cat)

    # Apply syncable properties (Name, Abbreviation, Description).
    src_props = source.GramCat.GetSyncableProperties(src_obj)
    target.GramCat.ApplySyncableProperties(new_cat, src_props)

    # Carrier B residue (gram categories have Description on ICmPossibility).
    apply_carrier_b(new_cat, ws, tag)
    return new_cat


# ----- inflection_features (GOLD-aware) ------------------------------------
#
# Inflection features are IFsClosedFeature objects (or IFsComplexFeature).
# They live under LangProject.MsFeatureSystemOA.FeaturesOC.
# GOLD check: non-empty CatalogSourceId.
# Creation: IFsClosedFeatureFactory.Create(Guid, featureSystem) (2-arg) or
#            IFsClosedFeatureFactory.Create(Guid) + FeaturesOC.Add().

def inflection_features_enumerate_source(context: RunContext, selection: Selection):
    """Walk source.InflectionFeature.FeatureGetAll()."""
    source = context.source_handle
    if not hasattr(source, "InflectionFeature"):
        return ()
    return list(source.InflectionFeature.FeatureGetAll())


def inflection_features_dependencies(piece):
    """Inflection features pull in their IFsSymFeatVal values.

    The values are owned by the feature (feature.ValuesOC) and are
    physically created together with the feature in execute_action.
    We return them as INFLECTION_FEATURES sub-refs so the closure
    walker can record them as pulled-in by this feature.
    """
    # Values are co-created in execute_action, not separately planned.
    # Return empty here — the execute step handles value creation atomically.
    return ()


def inflection_features_required_writing_systems(piece) -> Iterable[Tuple[str, WSKind]]:
    return ()


def inflection_features_plan_action(piece, context: RunContext, ws_mapping: WSMapping):
    """GOLD-aware: Skip GOLD features; plan Add for user-defined ones."""
    if _is_gold(piece):
        return Skip(
            category=GrammarCategory.INFLECTION_FEATURES,
            source_guid=_guid_str_from(piece),
            reason=SkipReason.GOLD_INVIOLABLE,
            detail=(
                f"Inflection feature is a GOLD object (CatalogSourceId="
                f"{getattr(piece, 'CatalogSourceId', '?')!r}); "
                "not transferred per FR-022 / Principle I."
            ),
        )
    src_guid = _guid_str_from(piece)
    target = context.target_handle
    if hasattr(target, "InflectionFeature"):
        if _target_has_guid(target.InflectionFeature.FeatureGetAll(), src_guid):
            return Skip(
                category=GrammarCategory.INFLECTION_FEATURES,
                source_guid=src_guid,
                reason=SkipReason.ALREADY_PRESENT_BY_GUID,
                detail=f"Inflection feature GUID {src_guid[:8]}... already present in target.",
            )
    return PlannedAction(
        category=GrammarCategory.INFLECTION_FEATURES,
        source_guid=src_guid,
        intended_target_guid=src_guid,
        summary=f"InflectionFeature guid={src_guid[:8]}...",
    )


def inflection_features_execute_action(action: PlannedAction, context: RunContext, ws_mapping: WSMapping, tag: ImportResidueTag):
    """Create an IFsClosedFeature in the target with GUID preserved.

    Uses the 2-arg factory overload (Path A: Create(Guid, featureSystem))
    per the InflectionFeatureOperations._factory_create_attached pattern.
    Falls back to Create(Guid) + FeaturesOC.Add() if the 2-arg overload
    is unavailable.

    Values (IFsSymFeatVal) are co-created via CreateValue so they land
    in the same transaction.  Carrier B residue is applied.
    """
    from SIL.LCModel import IFsClosedFeatureFactory, IFsClosedFeature, IFsSymFeatValFactory, IFsSymFeatVal
    from System import Guid as DotNetGuid

    if __package__:
        from .residue import apply_carrier_b
    else:
        from residue import apply_carrier_b  # type: ignore

    source = context.source_handle
    target = context.target_handle
    src_guid = action.source_guid

    # Locate source feature.
    src_feat = None
    for f in source.InflectionFeature.FeatureGetAll():
        if _guid_str_from(f) == src_guid:
            src_feat = f
            break
    if src_feat is None:
        return None

    cache = getattr(target, "Cache")
    ws = cache.DefaultAnalWs
    feature_system = cache.LangProject.MsFeatureSystemOA
    parsed_guid = DotNetGuid.Parse(src_guid)

    sl = cache.ServiceLocator
    factory = sl.GetService(IFsClosedFeatureFactory)

    # Path A: 2-arg Create(Guid, featureSystem).
    new_feat = None
    try:
        new_feat = factory.Create(parsed_guid, feature_system)
    except Exception:
        new_feat = None

    if new_feat is None:
        # Path B: Create(Guid) + Add.
        try:
            new_feat = factory.Create(parsed_guid)
        except Exception:
            new_feat = factory.Create()
        feature_system.FeaturesOC.Add(new_feat)

    new_feat = IFsClosedFeature(new_feat)

    # Apply syncable properties (Name, Abbreviation, Description).
    # InflectionFeatureOperations.GetSyncableProperties works on IMoInflClass;
    # for features we read properties directly.
    src_feat_typed = IFsClosedFeature(src_feat)
    from SIL.LCModel.Core.KernelInterfaces import ITsString
    from SIL.LCModel.Core.Text import TsStringUtils
    all_ws = {ws_obj.Id: ws_obj.Handle for ws_obj in source.WritingSystems.GetAll()}
    for prop_name in ("Name", "Abbreviation", "Description"):
        src_prop = getattr(src_feat_typed, prop_name, None)
        tgt_prop = getattr(new_feat, prop_name, None)
        if src_prop is None or tgt_prop is None:
            continue
        for ws_id, ws_handle in all_ws.items():
            text = ITsString(src_prop.get_String(ws_handle)).Text
            if text:
                tgt_prop.set_String(ws_handle, TsStringUtils.MakeString(text, ws_handle))

    # Co-create values (IFsSymFeatVal) with their canonical GUIDs.
    val_factory = sl.GetService(IFsSymFeatValFactory)
    if hasattr(src_feat_typed, "ValuesOC"):
        for src_val in src_feat_typed.ValuesOC:
            val_guid = _guid_str_from(src_val)
            parsed_val_guid = DotNetGuid.Parse(val_guid)
            new_val = None
            try:
                new_val = val_factory.Create(parsed_val_guid, new_feat)
            except Exception:
                new_val = None
            if new_val is None:
                try:
                    new_val = val_factory.Create(parsed_val_guid)
                except Exception:
                    new_val = val_factory.Create()
                new_feat.ValuesOC.Add(new_val)
            new_val = IFsSymFeatVal(new_val)
            src_val_typed = IFsSymFeatVal(src_val)
            for prop_name in ("Name", "Abbreviation", "Description"):
                src_p = getattr(src_val_typed, prop_name, None)
                tgt_p = getattr(new_val, prop_name, None)
                if src_p is None or tgt_p is None:
                    continue
                for ws_id, ws_handle in all_ws.items():
                    text = ITsString(src_p.get_String(ws_handle)).Text
                    if text:
                        tgt_p.set_String(ws_handle, TsStringUtils.MakeString(text, ws_handle))

    # Carrier B: Description-append on the feature.
    apply_carrier_b(new_feat, ws, tag)
    return new_feat


# ----- custom_fields -------------------------------------------------------

def custom_fields_enumerate_source(context, selection):
    raise NotImplementedError("T039")


def custom_fields_dependencies(piece):
    return ()


def custom_fields_required_writing_systems(piece):
    raise NotImplementedError("T039")


def custom_fields_plan_action(piece, context, ws_mapping):
    raise NotImplementedError("T039")


def custom_fields_execute_action(action, context, ws_mapping, tag):
    raise NotImplementedError("T039")


# ----- inflection_classes --------------------------------------------------
#
# Inflection classes are IMoInflClass objects under
# LangProject.MorphologicalDataOA.ProdRestrictOA.PossibilitiesOS.
# No GOLD check (user-defined only).
# Factory: IMoInflClassFactory.Create(Guid) + Add to ProdRestrictOA.PossibilitiesOS.

def inflection_classes_enumerate_source(context: RunContext, selection: Selection):
    """Walk source.InflectionFeature.InflectionClassGetAll()."""
    source = context.source_handle
    if not hasattr(source, "InflectionFeature"):
        return ()
    return list(source.InflectionFeature.InflectionClassGetAll())


def inflection_classes_dependencies(piece):
    """Inflection classes reference an owner POS (via InflectionClassesRC on
    IPartOfSpeech), but in Phase 0 additive mode the class is created without
    wiring that reference — the POS wiring is handled at the affix / MSA level.
    Return empty so the closure walker treats this as a leaf.
    """
    return ()


def inflection_classes_required_writing_systems(piece) -> Iterable[Tuple[str, WSKind]]:
    return ()


def inflection_classes_plan_action(piece, context: RunContext, ws_mapping: WSMapping):
    """No GOLD check; emit PlannedAction or ALREADY_PRESENT_BY_GUID skip."""
    src_guid = _guid_str_from(piece)
    target = context.target_handle
    if hasattr(target, "InflectionFeature"):
        if _target_has_guid(target.InflectionFeature.InflectionClassGetAll(), src_guid):
            return Skip(
                category=GrammarCategory.INFLECTION_CLASSES,
                source_guid=src_guid,
                reason=SkipReason.ALREADY_PRESENT_BY_GUID,
                detail=f"Inflection class GUID {src_guid[:8]}... already present in target.",
            )
    return PlannedAction(
        category=GrammarCategory.INFLECTION_CLASSES,
        source_guid=src_guid,
        intended_target_guid=src_guid,
        summary=f"InflectionClass guid={src_guid[:8]}...",
    )


def inflection_classes_execute_action(action: PlannedAction, context: RunContext, ws_mapping: WSMapping, tag: ImportResidueTag):
    """Create IMoInflClass in target with GUID preserved.

    IMoInflClassFactory.Create(Guid) + ProdRestrictOA.PossibilitiesOS.Add().
    ApplySyncableProperties syncs Name/Abbreviation/Description.
    Carrier B residue.
    """
    from SIL.LCModel import IMoInflClassFactory, IMoInflClass
    from System import Guid as DotNetGuid

    if __package__:
        from .residue import apply_carrier_b
    else:
        from residue import apply_carrier_b  # type: ignore

    source = context.source_handle
    target = context.target_handle
    src_guid = action.source_guid

    src_obj = None
    for ic in source.InflectionFeature.InflectionClassGetAll():
        if _guid_str_from(ic) == src_guid:
            src_obj = ic
            break
    if src_obj is None:
        return None

    cache = getattr(target, "Cache")
    ws = cache.DefaultAnalWs
    morph_data = cache.LangProject.MorphologicalDataOA

    parsed_guid = DotNetGuid.Parse(src_guid)
    sl = cache.ServiceLocator
    factory = sl.GetService(IMoInflClassFactory)

    new_ic = None
    try:
        new_ic = factory.Create(parsed_guid)
    except Exception:
        new_ic = factory.Create()

    morph_data.ProdRestrictOA.PossibilitiesOS.Add(new_ic)
    new_ic = IMoInflClass(new_ic)

    # Apply syncable properties.
    src_props = source.InflectionFeature.GetSyncableProperties(src_obj)
    target.InflectionFeature.ApplySyncableProperties(new_ic, src_props)

    apply_carrier_b(new_ic, ws, tag)
    return new_ic


# ----- stem_names ---------------------------------------------------------
#
# Stem names (IMoStemName) live under IPartOfSpeech.StemNamesOC.
# They define allomorph conditioning environments (e.g., "basic stem",
# "oblique stem").  Not GOLD-aware.
# Factory: IMoStemNameFactory.Create(Guid) + pos.StemNamesOC.Add().

def stem_names_enumerate_source(context: RunContext, selection: Selection):
    """Yield all IMoStemName objects from all POSes in source."""
    source = context.source_handle
    if not hasattr(source, "POS"):
        return ()
    results = []
    for pos in source.POS.GetAll(recursive=True):
        concrete = pos.concrete if hasattr(pos, "concrete") else pos
        try:
            from SIL.LCModel import IPartOfSpeech
            pos_obj = IPartOfSpeech(concrete)
            for sn in pos_obj.StemNamesOC:
                results.append(sn)
        except Exception:
            pass
    return results


def stem_names_dependencies(piece):
    return ()  # leaf


def stem_names_required_writing_systems(piece) -> Iterable[Tuple[str, WSKind]]:
    return ()


def stem_names_plan_action(piece, context: RunContext, ws_mapping: WSMapping):
    """No GOLD check; emit PlannedAction or ALREADY_PRESENT_BY_GUID skip."""
    src_guid = _guid_str_from(piece)
    # Check target for GUID collision by scanning all POS stem names.
    target = context.target_handle
    if hasattr(target, "POS"):
        for pos in target.POS.GetAll(recursive=True):
            concrete = pos.concrete if hasattr(pos, "concrete") else pos
            try:
                from SIL.LCModel import IPartOfSpeech
                pos_obj = IPartOfSpeech(concrete)
                for sn in pos_obj.StemNamesOC:
                    if _guid_str_from(sn) == src_guid:
                        return Skip(
                            category=GrammarCategory.STEM_NAMES,
                            source_guid=src_guid,
                            reason=SkipReason.ALREADY_PRESENT_BY_GUID,
                            detail=f"StemName GUID {src_guid[:8]}... already present in target.",
                        )
            except Exception:
                pass
    return PlannedAction(
        category=GrammarCategory.STEM_NAMES,
        source_guid=src_guid,
        intended_target_guid=src_guid,
        summary=f"StemName guid={src_guid[:8]}...",
    )


def stem_names_execute_action(action: PlannedAction, context: RunContext, ws_mapping: WSMapping, tag: ImportResidueTag):
    """Create IMoStemName in target with GUID preserved.

    Requires the owner POS (by source GUID) to already exist in the
    target (either created in this run or pre-existing).  If the owner
    POS cannot be found, returns None and the caller should warn.

    IMoStemNameFactory.Create(Guid) + owner_pos.StemNamesOC.Add().
    Carrier B residue.
    """
    from SIL.LCModel import IMoStemNameFactory, IMoStemName, IPartOfSpeech, ICmObject
    from System import Guid as DotNetGuid

    if __package__:
        from .residue import apply_carrier_b
    else:
        from residue import apply_carrier_b  # type: ignore

    source = context.source_handle
    target = context.target_handle
    src_guid = action.source_guid

    # Find source stem name and its owner POS.
    src_obj = None
    src_owner_pos_guid = None
    for pos in source.POS.GetAll(recursive=True):
        concrete = pos.concrete if hasattr(pos, "concrete") else pos
        try:
            pos_obj = IPartOfSpeech(concrete)
            for sn in pos_obj.StemNamesOC:
                if _guid_str_from(sn) == src_guid:
                    src_obj = sn
                    src_owner_pos_guid = str(ICmObject(concrete).Guid).lower()
                    break
        except Exception:
            pass
        if src_obj is not None:
            break
    if src_obj is None:
        return None

    # Find target owner POS.
    target_pos = None
    if src_owner_pos_guid:
        for pos in target.POS.GetAll(recursive=True):
            concrete = pos.concrete if hasattr(pos, "concrete") else pos
            if str(ICmObject(concrete).Guid).lower() == src_owner_pos_guid:
                target_pos = IPartOfSpeech(concrete)
                break
    if target_pos is None:
        return None  # Owner POS not in target; dependency unresolved.

    cache = getattr(target, "Cache")
    ws = cache.DefaultAnalWs
    parsed_guid = DotNetGuid.Parse(src_guid)
    sl = cache.ServiceLocator
    factory = sl.GetService(IMoStemNameFactory)

    new_sn = None
    try:
        new_sn = factory.Create(parsed_guid)
    except Exception:
        new_sn = factory.Create()

    target_pos.StemNamesOC.Add(new_sn)
    new_sn = IMoStemName(new_sn)

    # Copy Name multistring directly (IMoStemName has Name but may not
    # be covered by a GetSyncableProperties wrapper in flexlibs2).
    from SIL.LCModel.Core.KernelInterfaces import ITsString
    from SIL.LCModel.Core.Text import TsStringUtils
    all_ws = {ws_obj.Id: ws_obj.Handle for ws_obj in source.WritingSystems.GetAll()}
    from SIL.LCModel import IMoStemName as IMoStemNameType
    src_sn_typed = IMoStemNameType(src_obj)
    for prop_name in ("Name", "Abbreviation", "Description"):
        src_p = getattr(src_sn_typed, prop_name, None)
        tgt_p = getattr(new_sn, prop_name, None)
        if src_p is None or tgt_p is None:
            continue
        for ws_id, ws_handle in all_ws.items():
            try:
                text = ITsString(src_p.get_String(ws_handle)).Text
                if text:
                    tgt_p.set_String(ws_handle, TsStringUtils.MakeString(text, ws_handle))
            except Exception:
                pass

    apply_carrier_b(new_sn, ws, tag)
    return new_sn


# ----- exception_features --------------------------------------------------
#
# "Exception features" in FLEx are IFsSymFeatVal items that appear in
# IPartOfSpeech.ExceptionFeaturesOC.  They are VALUE references (not owned
# features) — the canonical objects live in IFsClosedFeature.ValuesOC and
# are co-created with their parent feature during inflection_features transfer.
#
# Phase 0 model: enumerate the (POS-guid, value-guid) pairs from the source;
# plan_action checks whether the target POS already has the value wired;
# execute_action resolves the target value by GUID and adds it to the target
# POS.ExceptionFeaturesOC.  No new IFsSymFeatVal is created here.
#
# LCM NOTE: IPartOfSpeech.ExceptionFeaturesOC is an
# LcmReferenceCollection<IFsSymFeatVal> (not owning), so .Add() is a
# ref-wire only — the value must already exist in the feature system.

def exception_features_enumerate_source(context: RunContext, selection: Selection):
    """Yield (pos_guid, sym_feat_val) pairs for all wired exception features."""
    source = context.source_handle
    if not hasattr(source, "POS"):
        return ()
    results = []
    for pos in source.POS.GetAll(recursive=True):
        concrete = pos.concrete if hasattr(pos, "concrete") else pos
        try:
            from SIL.LCModel import IPartOfSpeech
            pos_obj = IPartOfSpeech(concrete)
            for val in pos_obj.ExceptionFeaturesOC:
                results.append((_guid_str_from(concrete), val))
        except Exception:
            pass
    return results


def exception_features_dependencies(piece):
    """An exception feature depends on the owning POS and the value's parent
    inflection feature.  Return empty for the Phase 0 leaf treatment;
    the execute step does a live GUID lookup to wire the ref.
    """
    return ()


def exception_features_required_writing_systems(piece) -> Iterable[Tuple[str, WSKind]]:
    return ()


def exception_features_plan_action(piece, context: RunContext, ws_mapping: WSMapping):
    """No GOLD check on IFsSymFeatVal wiring.

    `piece` is a (pos_guid_str, sym_feat_val_obj) tuple as yielded by
    enumerate_source.  The source_guid encodes both: "pos_guid::val_guid".
    This lets the executor identify the wiring uniquely.
    """
    if not (isinstance(piece, tuple) and len(piece) == 2):
        return Skip(
            category=GrammarCategory.EXCEPTION_FEATURES,
            source_guid="unknown",
            reason=SkipReason.UNSUPPORTED_LCM_TYPE,
            detail="exception_features piece must be (pos_guid, val_obj) tuple.",
        )
    pos_guid, val_obj = piece
    val_guid = _guid_str_from(val_obj)
    compound_guid = f"{pos_guid}::{val_guid}"

    # Check whether target POS already has this value wired.
    target = context.target_handle
    if hasattr(target, "POS"):
        for pos in target.POS.GetAll(recursive=True):
            concrete = pos.concrete if hasattr(pos, "concrete") else pos
            if _guid_str_from(concrete) != pos_guid:
                continue
            try:
                from SIL.LCModel import IPartOfSpeech
                pos_obj_tgt = IPartOfSpeech(concrete)
                for existing_val in pos_obj_tgt.ExceptionFeaturesOC:
                    if _guid_str_from(existing_val) == val_guid:
                        return Skip(
                            category=GrammarCategory.EXCEPTION_FEATURES,
                            source_guid=compound_guid,
                            reason=SkipReason.ALREADY_PRESENT_BY_GUID,
                            detail=(
                                f"ExceptionFeature val {val_guid[:8]}... already wired "
                                f"to POS {pos_guid[:8]}... in target."
                            ),
                        )
            except Exception:
                pass

    return PlannedAction(
        category=GrammarCategory.EXCEPTION_FEATURES,
        source_guid=compound_guid,
        intended_target_guid=compound_guid,
        summary=f"ExceptionFeature pos={pos_guid[:8]}... val={val_guid[:8]}...",
    )


def exception_features_execute_action(action: PlannedAction, context: RunContext, ws_mapping: WSMapping, tag: ImportResidueTag):
    """Wire the IFsSymFeatVal reference into the target POS.ExceptionFeaturesOC.

    The value must already exist in the target feature system (created via
    inflection_features_execute_action).  If not found, returns None.

    No new LCM object is created.  No residue tag applied (no Description
    on IFsSymFeatVal reference wiring — the value itself was tagged when
    created as part of its parent feature).
    """
    from SIL.LCModel import IPartOfSpeech, IFsSymFeatVal

    target = context.target_handle
    src_compound = action.source_guid
    if "::" not in src_compound:
        return None
    pos_guid, val_guid = src_compound.split("::", 1)

    # Find target POS.
    target_pos = None
    for pos in target.POS.GetAll(recursive=True):
        concrete = pos.concrete if hasattr(pos, "concrete") else pos
        if _guid_str_from(concrete) == pos_guid:
            target_pos = IPartOfSpeech(concrete)
            break
    if target_pos is None:
        return None  # POS not yet in target.

    # Find target IFsSymFeatVal by GUID in the feature system.
    cache = getattr(target, "Cache")
    feature_system = cache.LangProject.MsFeatureSystemOA
    target_val = None
    for feat in feature_system.FeaturesOC:
        if not hasattr(feat, "ValuesOC"):
            continue
        try:
            for v in feat.ValuesOC:
                if _guid_str_from(v) == val_guid:
                    target_val = IFsSymFeatVal(v)
                    break
        except Exception:
            pass
        if target_val is not None:
            break
    if target_val is None:
        return None  # Value not in target; inflection_features must run first.

    target_pos.ExceptionFeaturesOC.Add(target_val)
    return target_val


# ----- variant_types (closure: associated inflection features per FR-004) --

def variant_types_enumerate_source(context, selection):
    raise NotImplementedError("T039")


def variant_types_dependencies(piece):
    # NOT a leaf — variant types reference inflection features. The closure
    # walker will follow these refs to pull in the features. T039 fills in
    # the actual lookup.
    raise NotImplementedError("T039: yield (INFLECTION_FEATURES, feature_guid) refs")


def variant_types_required_writing_systems(piece):
    raise NotImplementedError("T039")


def variant_types_plan_action(piece, context, ws_mapping):
    raise NotImplementedError("T039")


def variant_types_execute_action(action, context, ws_mapping, tag):
    raise NotImplementedError("T039")


# ----- complex_form_types --------------------------------------------------

def complex_form_types_enumerate_source(context, selection):
    raise NotImplementedError("T039")


def complex_form_types_dependencies(piece):
    return ()


def complex_form_types_required_writing_systems(piece):
    raise NotImplementedError("T039")


def complex_form_types_plan_action(piece, context, ws_mapping):
    raise NotImplementedError("T039")


def complex_form_types_execute_action(action, context, ws_mapping, tag):
    raise NotImplementedError("T039")


# ----- adhoc_rules ---------------------------------------------------------

def adhoc_rules_enumerate_source(context, selection):
    raise NotImplementedError("T039")


def adhoc_rules_dependencies(piece):
    return ()


def adhoc_rules_required_writing_systems(piece):
    raise NotImplementedError("T039")


def adhoc_rules_plan_action(piece, context, ws_mapping):
    raise NotImplementedError("T039")


def adhoc_rules_execute_action(action, context, ws_mapping, tag):
    raise NotImplementedError("T039")


# ----- compound_rules ------------------------------------------------------

def compound_rules_enumerate_source(context, selection):
    raise NotImplementedError("T039")


def compound_rules_dependencies(piece):
    return ()


def compound_rules_required_writing_systems(piece):
    raise NotImplementedError("T039")


def compound_rules_plan_action(piece, context, ws_mapping):
    raise NotImplementedError("T039")


def compound_rules_execute_action(action, context, ws_mapping, tag):
    raise NotImplementedError("T039")


# ============================================================================
# Category registry — engine dispatch
# ============================================================================

# ============================================================================
# Phase 3a — phonology block + strata (memo steps 2-5 + 4b + 5b)
# Six stub categories.  enumerate_source / dependencies /
# required_writing_systems / plan_action / execute_action will be
# filled in by the per-story tasks in specs/005-phonology-block/tasks.md.
# ============================================================================

# ----- phonological_features (memo step 2) ---------------------------------

def phonological_features_enumerate_source(context, selection):
    raise NotImplementedError("Phase 3a US1 T011")


def phonological_features_dependencies(piece):
    return ()


def phonological_features_required_writing_systems(piece):
    raise NotImplementedError("Phase 3a US1 T011")


def phonological_features_plan_action(piece, context, ws_mapping):
    raise NotImplementedError("Phase 3a US1 T012")


def phonological_features_execute_action(action, context, ws_mapping, tag):
    raise NotImplementedError("Phase 3a US1 T012")


# ----- phonemes (memo step 3) ----------------------------------------------

def phonemes_enumerate_source(context, selection):
    raise NotImplementedError("Phase 3a US1 T014")


def phonemes_dependencies(piece):
    return ()


def phonemes_required_writing_systems(piece):
    raise NotImplementedError("Phase 3a US1 T015")


def phonemes_plan_action(piece, context, ws_mapping):
    raise NotImplementedError("Phase 3a US1 T016")


def phonemes_execute_action(action, context, ws_mapping, tag):
    raise NotImplementedError("Phase 3a US1 T017")


# ----- natural_classes (memo step 4) ---------------------------------------

def natural_classes_enumerate_source(context, selection):
    raise NotImplementedError("Phase 3a US1 T019")


def natural_classes_dependencies(piece):
    raise NotImplementedError("Phase 3a US1 T020")


def natural_classes_required_writing_systems(piece):
    raise NotImplementedError("Phase 3a US1 T020")


def natural_classes_plan_action(piece, context, ws_mapping):
    raise NotImplementedError("Phase 3a US1 T021")


def natural_classes_execute_action(action, context, ws_mapping, tag):
    raise NotImplementedError("Phase 3a US1 T021")


# ----- phonological_rules (memo step 5) ------------------------------------

def phonological_rules_enumerate_source(context, selection):
    raise NotImplementedError("Phase 3a US1 T023")


def phonological_rules_dependencies(piece):
    raise NotImplementedError("Phase 3a US1 T024")


def phonological_rules_required_writing_systems(piece):
    raise NotImplementedError("Phase 3a US1 T024")


def phonological_rules_plan_action(piece, context, ws_mapping):
    raise NotImplementedError("Phase 3a US1 T025")


def phonological_rules_execute_action(action, context, ws_mapping, tag):
    raise NotImplementedError("Phase 3a US1 T026")


# ----- strata (memo step 5b) -----------------------------------------------

def strata_enumerate_source(context, selection):
    raise NotImplementedError("Phase 3a US2 T031")


def strata_dependencies(piece):
    return ()


def strata_required_writing_systems(piece):
    raise NotImplementedError("Phase 3a US2 T031")


def strata_plan_action(piece, context, ws_mapping):
    raise NotImplementedError("Phase 3a US2 T032")


def strata_execute_action(action, context, ws_mapping, tag):
    raise NotImplementedError("Phase 3a US2 T032")


# ----- ph_environment (memo step 4b -- relocated from allomorph-bundled) ---

def ph_environment_enumerate_source(context, selection):
    raise NotImplementedError("Phase 3a US3 T035")


def ph_environment_dependencies(piece):
    return ()


def ph_environment_required_writing_systems(piece):
    raise NotImplementedError("Phase 3a US3 T035")


def ph_environment_plan_action(piece, context, ws_mapping):
    raise NotImplementedError("Phase 3a US3 T035")


def ph_environment_execute_action(action, context, ws_mapping, tag):
    raise NotImplementedError("Phase 3a US3 T035")


LEAF_CATEGORIES = {
    GrammarCategory.GRAM_CATEGORIES: {
        "enumerate_source": gram_categories_enumerate_source,
        "dependencies": gram_categories_dependencies,
        "required_writing_systems": gram_categories_required_writing_systems,
        "plan_action": gram_categories_plan_action,
        "execute_action": gram_categories_execute_action,
    },
    GrammarCategory.INFLECTION_FEATURES: {
        "enumerate_source": inflection_features_enumerate_source,
        "dependencies": inflection_features_dependencies,
        "required_writing_systems": inflection_features_required_writing_systems,
        "plan_action": inflection_features_plan_action,
        "execute_action": inflection_features_execute_action,
    },
    GrammarCategory.CUSTOM_FIELDS: {
        "enumerate_source": custom_fields_enumerate_source,
        "dependencies": custom_fields_dependencies,
        "required_writing_systems": custom_fields_required_writing_systems,
        "plan_action": custom_fields_plan_action,
        "execute_action": custom_fields_execute_action,
    },
    GrammarCategory.INFLECTION_CLASSES: {
        "enumerate_source": inflection_classes_enumerate_source,
        "dependencies": inflection_classes_dependencies,
        "required_writing_systems": inflection_classes_required_writing_systems,
        "plan_action": inflection_classes_plan_action,
        "execute_action": inflection_classes_execute_action,
    },
    GrammarCategory.STEM_NAMES: {
        "enumerate_source": stem_names_enumerate_source,
        "dependencies": stem_names_dependencies,
        "required_writing_systems": stem_names_required_writing_systems,
        "plan_action": stem_names_plan_action,
        "execute_action": stem_names_execute_action,
    },
    GrammarCategory.EXCEPTION_FEATURES: {
        "enumerate_source": exception_features_enumerate_source,
        "dependencies": exception_features_dependencies,
        "required_writing_systems": exception_features_required_writing_systems,
        "plan_action": exception_features_plan_action,
        "execute_action": exception_features_execute_action,
    },
    GrammarCategory.VARIANT_TYPES: {
        "enumerate_source": variant_types_enumerate_source,
        "dependencies": variant_types_dependencies,
        "required_writing_systems": variant_types_required_writing_systems,
        "plan_action": variant_types_plan_action,
        "execute_action": variant_types_execute_action,
    },
    GrammarCategory.COMPLEX_FORM_TYPES: {
        "enumerate_source": complex_form_types_enumerate_source,
        "dependencies": complex_form_types_dependencies,
        "required_writing_systems": complex_form_types_required_writing_systems,
        "plan_action": complex_form_types_plan_action,
        "execute_action": complex_form_types_execute_action,
    },
    GrammarCategory.ADHOC_RULES: {
        "enumerate_source": adhoc_rules_enumerate_source,
        "dependencies": adhoc_rules_dependencies,
        "required_writing_systems": adhoc_rules_required_writing_systems,
        "plan_action": adhoc_rules_plan_action,
        "execute_action": adhoc_rules_execute_action,
    },
    GrammarCategory.COMPOUND_RULES: {
        "enumerate_source": compound_rules_enumerate_source,
        "dependencies": compound_rules_dependencies,
        "required_writing_systems": compound_rules_required_writing_systems,
        "plan_action": compound_rules_plan_action,
        "execute_action": compound_rules_execute_action,
    },
    # Phase 3a — phonology block + strata (steps 2-5 + 4b + 5b)
    GrammarCategory.PHONOLOGICAL_FEATURES: {
        "enumerate_source": phonological_features_enumerate_source,
        "dependencies": phonological_features_dependencies,
        "required_writing_systems": phonological_features_required_writing_systems,
        "plan_action": phonological_features_plan_action,
        "execute_action": phonological_features_execute_action,
    },
    GrammarCategory.PHONEMES: {
        "enumerate_source": phonemes_enumerate_source,
        "dependencies": phonemes_dependencies,
        "required_writing_systems": phonemes_required_writing_systems,
        "plan_action": phonemes_plan_action,
        "execute_action": phonemes_execute_action,
    },
    GrammarCategory.NATURAL_CLASSES: {
        "enumerate_source": natural_classes_enumerate_source,
        "dependencies": natural_classes_dependencies,
        "required_writing_systems": natural_classes_required_writing_systems,
        "plan_action": natural_classes_plan_action,
        "execute_action": natural_classes_execute_action,
    },
    GrammarCategory.PH_ENVIRONMENT: {
        "enumerate_source": ph_environment_enumerate_source,
        "dependencies": ph_environment_dependencies,
        "required_writing_systems": ph_environment_required_writing_systems,
        "plan_action": ph_environment_plan_action,
        "execute_action": ph_environment_execute_action,
    },
    GrammarCategory.PHONOLOGICAL_RULES: {
        "enumerate_source": phonological_rules_enumerate_source,
        "dependencies": phonological_rules_dependencies,
        "required_writing_systems": phonological_rules_required_writing_systems,
        "plan_action": phonological_rules_plan_action,
        "execute_action": phonological_rules_execute_action,
    },
    GrammarCategory.STRATA: {
        "enumerate_source": strata_enumerate_source,
        "dependencies": strata_dependencies,
        "required_writing_systems": strata_required_writing_systems,
        "plan_action": strata_plan_action,
        "execute_action": strata_execute_action,
    },
}


def for_category(category: GrammarCategory) -> dict:
    """Lookup the function bundle for a leaf category. Raises KeyError if
    the category isn't a leaf (use `categories_affixes`, `categories_templates`,
    or `categories_msas` for the heavy ones)."""
    return LEAF_CATEGORIES[category]

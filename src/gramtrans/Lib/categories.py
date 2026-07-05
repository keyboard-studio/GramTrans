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
    `Create(Guid)` + `FeaturesOC.Add()` per the pattern in
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
        ConflictMode,
        CreateDefinitionAction,
        GrammarCategory,
        PlannedAction,
        PlannedOverwrite,
        RunContext,
        Selection,
        Skip,
        SkipReason,
        WSKind,
        WSMapping,
    )
    from .protection import apply_isprotected_layer2
    from .residue import ImportResidueTag
else:
    from models import (  # type: ignore
        ConflictMode,
        CreateDefinitionAction,
        GrammarCategory,
        PlannedAction,
        PlannedOverwrite,
        RunContext,
        Selection,
        Skip,
        SkipReason,
        WSKind,
        WSMapping,
    )
    from protection import apply_isprotected_layer2  # type: ignore
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


def _find_target_obj_by_guid(target_iter, src_guid: str):
    """Return the first target object whose GUID matches `src_guid`, or None."""
    for obj in target_iter:
        if _guid_str_from(obj) == src_guid:
            return obj
    return None



def _compare_multistring_per_ws(src_ms, tgt_ms, ws_list):
    """Compare source vs target multistring per writing system.

    Returns (gaps, conflicts) where:
      gaps      = list of (ws_handle, src_text) — target slot empty, source non-empty
      conflicts = list of (ws_handle, src_text, tgt_text) — both non-empty but differ
    """
    gaps = []
    conflicts = []
    for _ws_id, ws_handle in ws_list:
        src_text = None
        tgt_text = None
        try:
            src_ts = src_ms.get_String(ws_handle)
            src_text = getattr(src_ts, "Text", None) or None
        except Exception:
            src_text = None
        try:
            tgt_ts = tgt_ms.get_String(ws_handle)
            tgt_text = getattr(tgt_ts, "Text", None) or None
        except Exception:
            tgt_text = None

        if src_text is None:
            continue  # source empty -> skip
        if tgt_text is None:
            gaps.append((ws_handle, src_text))
        elif src_text != tgt_text:
            conflicts.append((ws_handle, src_text, tgt_text))
        # else: equal -> no-op
    return gaps, conflicts


def _plan_gold_reserved_edit(piece, category, context, target_iter_fn):
    """Shared GOLD_RESERVED plan_action helper (spec 017 FR-E10).

    Guard chain (FR-E01 to FR-E03):
    1. _is_gold -> Skip(GOLD_INVIOLABLE) if GOLD.
    2. target_iter_fn(context.target_handle) -> scan for GUID.
    3. If absent -> return None (caller emits PlannedAction).
    4. apply_isprotected_layer2 -> if MERGE, Skip(ALREADY_PRESENT_BY_GUID)
       with IsProtected note.
    5. MERGE-per-WS edit detection on Name, Abbreviation, Description.
       - Any gaps -> PlannedOverwrite(write_mode="merge").
       - All equal -> Skip(ALREADY_PRESENT_BY_GUID).
       - All conflicts (no gaps) -> Skip(ALREADY_PRESENT_BY_GUID) + conflict detail.
       - Mixed gaps+conflicts -> PlannedOverwrite for gaps; conflicts in summary.

    Returns a Skip, PlannedOverwrite, or None.
    - None means "not present in target" -> caller emits PlannedAction.
    """
    if _is_gold(piece):
        return Skip(
            category=category,
            source_guid=_guid_str_from(piece),
            reason=SkipReason.GOLD_INVIOLABLE,
            detail=(
                f"Item is a GOLD object (CatalogSourceId="
                f"{getattr(piece, 'CatalogSourceId', '?')!r}); "
                "not transferred per FR-022 / Principle I."
            ),
        )

    src_guid = _guid_str_from(piece)
    target_iter = target_iter_fn(context.target_handle)
    tgt_obj = _find_target_obj_by_guid(target_iter, src_guid)

    if tgt_obj is None:
        return None  # absent -> caller emits PlannedAction

    # IsProtected guard (FR-E02): downgrade to MERGE = link-only, no edit.
    mode = apply_isprotected_layer2(category, tgt_obj, ConflictMode.OVERWRITE)
    if mode == ConflictMode.MERGE:
        return Skip(
            category=category,
            source_guid=src_guid,
            reason=SkipReason.ALREADY_PRESENT_BY_GUID,
            detail=(
                f"GUID {src_guid[:8]}... present in target; "
                "edit copy suppressed by IsProtected=True."
            ),
        )

    # MERGE-per-WS edit detection (FR-E04 to FR-E07).
    # Enumerate writing systems from source side.
    source = context.source_handle
    ws_list = []
    try:
        for ws_obj in source.WritingSystems.GetAll():
            ws_list.append((getattr(ws_obj, "Id", str(ws_obj)), ws_obj.Handle))
    except Exception:
        pass

    if not ws_list:
        # No WS info available -> conservative skip (cannot prove edit).
        return Skip(
            category=category,
            source_guid=src_guid,
            reason=SkipReason.ALREADY_PRESENT_BY_GUID,
            detail=f"GUID {src_guid[:8]}... present in target (no WS info for comparison).",
        )

    all_gaps = []    # (field_name, ws_handle, src_text)
    all_conflicts = []  # (field_name, ws_handle, src_text, tgt_text)

    for field_name in ("Name", "Abbreviation", "Description"):
        src_ms = getattr(piece, field_name, None)
        tgt_ms = getattr(tgt_obj, field_name, None)
        if src_ms is None or tgt_ms is None:
            continue
        gaps, conflicts = _compare_multistring_per_ws(src_ms, tgt_ms, ws_list)
        for ws_handle, src_text in gaps:
            all_gaps.append((field_name, ws_handle, src_text))
        for ws_handle, src_text, tgt_text in conflicts:
            all_conflicts.append((field_name, ws_handle, src_text, tgt_text))

    if not all_gaps:
        # No empty-in-target slots. Either all equal or all conflicts.
        if all_conflicts:
            conflict_lines = "; ".join(
                f"{f}@ws={wh}: src={s!r} vs tgt={t!r}"
                for f, wh, s, t in all_conflicts
            )
            return Skip(
                category=category,
                source_guid=src_guid,
                reason=SkipReason.ALREADY_PRESENT_BY_GUID,
                detail=(
                    f"GUID {src_guid[:8]}... present; per-WS conflicts (not overwritten): "
                    f"{conflict_lines}"
                ),
            )
        return Skip(
            category=category,
            source_guid=src_guid,
            reason=SkipReason.ALREADY_PRESENT_BY_GUID,
            detail=f"GUID {src_guid[:8]}... present in target; all WS slots equal.",
        )

    # Gaps exist -> emit merge action.
    gap_summary = ", ".join(
        f"{f}@ws={wh}: +{s!r}" for f, wh, s in all_gaps
    )
    conflict_note = ""
    if all_conflicts:
        conflict_note = " | conflicts (not written): " + "; ".join(
            f"{f}@ws={wh}: src={s!r} vs tgt={t!r}"
            for f, wh, s, t in all_conflicts
        )
    summary = (
        f"Edit-copy GUID {src_guid[:8]}... [{category.value}]: "
        f"fill gaps {gap_summary}{conflict_note}"
    )
    return PlannedOverwrite(
        category=category,
        source_guid=src_guid,
        target_guid=src_guid,
        match_via="guid",
        write_mode="merge",
        summary=summary,
    )


# ============================================================================
# Per-category surfaces
# ============================================================================
#
# Naming: `<category>_<verb>(...)`. Each block groups one category's five
# functions for readability.

# ----- gram_categories (GOLD-aware; targets Parts of Speech) ---------------
#
# TODO: rename enum GRAM_CATEGORIES -> PARTS_OF_SPEECH at next API-break
# window. The enum string is a public serialized-plan surface; retargeted
# now (Option B per LEX crew cycle 2, 2026-06-21) to unblock US3 +
# Scenario C live verification while preserving plan compatibility.
# See STATUS.md Phase 3b deferred items.
#
# Per ordering-memo step 6: "Parts of Speech (= 'Gram Categories')" maps
# to IPartOfSpeech objects in LangProject.PartsOfSpeechOA.PossibilitiesOS
# (top-level + .SubPossibilitiesOS recursively). The flexicon accessor
# is `project.POS` -> POSOperations (NOT `project.GramCat`, which is
# legacy naming pointing at IFsFeatStrucType in MsFeatureSystemOA.TypesOC;
# that is a separate LCM subsystem deferred to Phase 3b close sweep as
# new FEATURE_STRUC_TYPES category).
#
# Pre-fix (commit 86cfbbe and earlier): callbacks targeted GramCat and
# created spurious IFsFeatStrucType objects when the user selected
# GRAM_CATEGORIES expecting POS transfer. See verification-log.md for
# the live-MCP finding that surfaced this Phase 0-era misalignment.

def gram_categories_enumerate_source(context: RunContext, selection: Selection):
    """Walk source.POS.GetAll(recursive=True) and yield each IPartOfSpeech."""
    source = context.source_handle
    if not hasattr(source, "POS"):
        return ()
    return list(source.POS.GetAll(recursive=True))


def gram_categories_dependencies(piece):
    return ()  # leaf -- POS owns inflection_classes / stem_names / exception_features


def gram_categories_required_writing_systems(piece) -> Iterable[Tuple[str, WSKind]]:
    """POS has Name, Abbreviation, Description (analysis WS)."""
    return ()


def gram_categories_plan_action(piece, context: RunContext, ws_mapping: WSMapping):
    """GOLD-aware: skip GOLD; edit-copy merge for present custom; Add for absent.

    Uses the shared _plan_gold_reserved_edit helper (spec 017 FR-E10).
    POS is ALIASED to gram_categories (shares execute at gram_categories L193+,
    Phase 0 routing) — this function handles both.
    """
    def _target_iter(target):
        if hasattr(target, "POS"):
            return target.POS.GetAll(recursive=True)
        return ()

    result = _plan_gold_reserved_edit(
        piece, GrammarCategory.GRAM_CATEGORIES, context, _target_iter
    )
    if result is not None:
        return result
    # Absent -> PlannedAction (add)
    src_guid = _guid_str_from(piece)
    return PlannedAction(
        category=GrammarCategory.GRAM_CATEGORIES,
        source_guid=src_guid,
        intended_target_guid=src_guid,
        summary=f"POS guid={src_guid[:8]}...",
    )


def gram_categories_execute_action(action: PlannedAction, context: RunContext, ws_mapping: WSMapping, tag: ImportResidueTag):
    """Create a Part of Speech in the target with GUID preserved.

    Top-level POSes are created under LangProject.PartsOfSpeechOA.PossibilitiesOS
    via IPartOfSpeechFactory.Create(Guid, ICmPossibilityList).
    Sub-categories (POS-owned sub-POSes) are created via the same factory's
    2-arg overload but the owner is the parent IPartOfSpeech (Create(Guid,
    IPartOfSpeech)).

    Verb-vertical collision guard: if a Phase 0 verb-vertical run is selected
    alongside GRAM_CATEGORIES, the POS for the verb-vertical entry would be
    created by the closure path first. We check target.POS.GetAll() inside
    execute_action and skip if the GUID is already present, mirroring the
    Phase 1 overwrite-detection pattern.
    """
    from SIL.LCModel import IPartOfSpeechFactory
    from System import Guid as DotNetGuid

    if __package__:
        from .residue import apply_carrier_b
    else:
        from residue import apply_carrier_b  # type: ignore

    source = context.source_handle
    target = context.target_handle
    src_guid = action.source_guid

    # Verb-vertical collision guard: skip if verb-vertical already created
    # this POS earlier in the same run.
    if _target_has_guid(target.POS.GetAll(recursive=True), src_guid):
        return None  # already present (created by verb-vertical or prior run)

    # Find the source POS to determine owner shape (top-level vs sub-POS).
    src_obj = None
    for pos in source.POS.GetAll(recursive=True):
        if _guid_str_from(pos) == src_guid:
            src_obj = pos
            break
    if src_obj is None:
        return None

    cache = getattr(target, "Cache")
    ws = cache.DefaultAnalWs
    parsed_guid = DotNetGuid.Parse(src_guid)

    # Determine parent: if source POS owner is another POS, this is a sub-POS;
    # otherwise it's top-level (owned by the PartsOfSpeechOA list).
    src_owner = getattr(src_obj, "Owner", None)
    is_sub_pos = False
    src_owner_guid = None
    if src_owner is not None:
        try:
            from SIL.LCModel import IPartOfSpeech
            IPartOfSpeech(src_owner)  # cast probe: raises if owner isn't a POS
            is_sub_pos = True
            src_owner_guid = _guid_str_from(src_owner)
        except Exception:
            is_sub_pos = False

    # pythonnet overload resolution requires the interface-cast wrapper
    # around target.GetFactory(); see transfer.py _create_pos_with_guid for
    # the canonical pattern. ServiceLocator.GetService returns the raw
    # COM-like object and Create dispatch fails to find the right overload.
    factory = IPartOfSpeechFactory(target.GetFactory(IPartOfSpeechFactory))

    if is_sub_pos and src_owner_guid:
        # Find the matching target parent POS.
        target_parent = None
        for p in target.POS.GetAll(recursive=True):
            if _guid_str_from(p) == src_owner_guid:
                target_parent = p
                break
        if target_parent is None:
            return None  # parent not in target; skip (will retry next run)
        try:
            new_pos = factory.Create(parsed_guid, target_parent)
        except Exception as e:
            raise RuntimeError(
                f"IPartOfSpeechFactory.Create(Guid, IPartOfSpeech) failed for "
                f"{src_guid}: {e!r}"
            ) from e
    else:
        # Top-level: owner is PartsOfSpeechOA possibility list.
        from SIL.LCModel import ICmPossibilityList
        pos_list = ICmPossibilityList(cache.LangProject.PartsOfSpeechOA)
        try:
            new_pos = factory.Create(parsed_guid, pos_list)
        except Exception as e:
            raise RuntimeError(
                f"IPartOfSpeechFactory.Create(Guid, ICmPossibilityList) failed for "
                f"{src_guid}: {e!r}"
            ) from e

    # Apply syncable properties (Name, Abbreviation, Description, etc.).
    src_props = source.POS.GetSyncableProperties(src_obj)
    target.POS.ApplySyncableProperties(new_pos, src_props)

    apply_carrier_b(new_pos, ws, tag)
    return new_pos


# ----- inflection_features (GOLD-aware) ------------------------------------
#
# Inflection features are IFsClosedFeature objects (or IFsComplexFeature).
# They live under LangProject.MsFeatureSystemOA.FeaturesOC.
# GOLD check: non-empty CatalogSourceId.
# Creation: IFsClosedFeatureFactory.Create(Guid, featureSystem) (2-arg) or
#            IFsClosedFeatureFactory.Create(Guid) + FeaturesOC.Add().

def inflection_features_enumerate_source(context: RunContext, selection: Selection):
    """Walk source.InflectionFeatures.FeatureGetAll()."""
    source = context.source_handle
    if not hasattr(source, "InflectionFeatures"):
        return ()
    return list(source.InflectionFeatures.FeatureGetAll())


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
    """GOLD-aware: Skip GOLD features; edit-copy merge for present custom; Add for absent.

    Uses the shared _plan_gold_reserved_edit helper (spec 017 FR-E10).
    """
    def _target_iter(target):
        if hasattr(target, "InflectionFeatures"):
            return target.InflectionFeatures.FeatureGetAll()
        return ()

    result = _plan_gold_reserved_edit(
        piece, GrammarCategory.INFLECTION_FEATURES, context, _target_iter
    )
    if result is not None:
        return result
    src_guid = _guid_str_from(piece)
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
    for f in source.InflectionFeatures.FeatureGetAll():
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
    # P0-A hardening: the 2-arg Create attaches automatically; the 1-arg
    # path guards Add with _safe_add_to_owner.  No no-arg fallback --
    # if Create(Guid) is unsupported on this LCM build we fail loud
    # rather than silently produce GUID-misaligned values.
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
                except Exception as e:
                    raise RuntimeError(
                        f"IFsSymFeatValFactory does not support Create(Guid); "
                        f"cannot align value GUID {val_guid} on feature {src_guid}"
                    ) from e
                _safe_add_to_owner(new_val, new_feat.ValuesOC,
                                   "IFsSymFeatValFactory", val_guid)
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


# ----- custom_fields (Phase 3b US2: detect-and-report, no creation) --------
#
# Custom-field SCHEMA creation is blocked at the flexicon layer:
# CustomFieldOperations.CreateField raises FP_TransactionError inside the
# Phase-1 UoW envelope that wraps the entire transfer.execute().  Raw
# IFwMetaDataCacheManaged.AddCustomField bypass corrupts records on next
# FLEx UI open (flexicon issue #21, 1,392 stranded senses cited in
# flexicon/docs/CUSTOM_FIELDS.md).
#
# Shipping posture (FR-325, US2 in spec.md): detect target's existing
# custom fields and Skip(NEEDS_MANUAL) for any source field that's
# absent.  User must pre-create missing fields via FLEx UI before
# re-running.  Phase 3c will populate VALUES into pre-existing target
# fields via SetValue (which works inside the UoW).
#
# See specs/006-inflection-prep-block/us2-blocker-memo.md.

# FLEx supports custom fields on these classes (per flexicon
# CustomFieldOperations._GetClassID at line ~1341):
_CUSTOM_FIELD_OWNER_CLASSES = ("LexEntry", "LexSense", "LexExampleSentence", "MoForm")


class _CustomFieldRecord:
    """Minimal record for a source custom-field definition.

    Plays the role that an ICmObject normally would for the leaf-dispatch
    contract -- carries a `guid` synthesized from the (owner_class, name)
    tuple so the existing _guid_str_from / _target_has_guid helpers work
    without modification.

    Attributes
    ----------
    guid / Guid : str
        Synthetic identity key ``"cf:<owner_class>:<name>"``.  Custom fields
        have no LCM Guid; this sentinel is recognised by the skip helpers.
    owner_class : str
        One of the four values in ``_CUSTOM_FIELD_OWNER_CLASSES``.
    name : str
        Field label as returned by ``GetAllFields`` / ``GetFieldName``.
    field_id : int
        Flid from the source MDC (0 when unknown).
    field_type : int
        ``CellarPropertyType`` integer (e.g. 13 = String, 14 = MultiString).
        0 when not yet populated.
    list_root_guid : str | None
        GUID of the possibility-list root for ReferenceAtomic /
        ReferenceCollection fields; ``None`` for all other types.
    """

    __slots__ = (
        "guid", "Guid", "owner_class", "name", "field_id",
        "field_type", "list_root_guid",
    )

    def __init__(
        self,
        owner_class: str,
        name: str,
        field_id: int = 0,
        field_type: int = 0,
        list_root_guid: str = "",
    ):
        # Synthetic identity: custom fields have no LCM Guid.  Use
        # "cf:<owner>:<name>" as the canonical key.
        self.guid = f"cf:{owner_class}:{name}"
        self.Guid = self.guid
        self.owner_class = owner_class
        self.name = name
        self.field_id = field_id
        self.field_type = field_type
        self.list_root_guid = list_root_guid

    @property
    def concrete(self):
        return self

    @property
    def CatalogSourceId(self):
        return ""  # custom fields are by definition not GOLD


# CellarPropertyType integer -> human-readable label.
# Values: Boolean=1, Integer=2, GenDate=8, String=13, MultiString=14,
# MultiUnicode=16, OwningAtomic=23, ReferenceAtomic=24, ReferenceCollection=26.
# ReferenceAtomic and ReferenceCollection both render as "List item" because
# from the user's perspective both point to a possibility-list entry.
# Labels align to research.md section 1 (FLEx UI display names).
_CELLAR_TYPE_LABELS = {
    1:  "Boolean",
    2:  "Integer",
    8:  "Date",
    13: "Text",
    14: "Multi-string",
    16: "Multi-Unicode",
    23: "Item (owned)",
    24: "List item",
    26: "List item",
}


def custom_field_type_label(field_type: int) -> str:
    """Return a human-readable label for a CellarPropertyType integer.

    Parameters
    ----------
    field_type:
        Integer CellarPropertyType value (e.g. 13 for String).

    Returns
    -------
    str
        Display label such as ``"String"``, ``"MultiString"``, or
        ``"List item"``.  Unknown values fall back to
        ``"Type <N>"`` to remain non-empty and debuggable.
    """
    return _CELLAR_TYPE_LABELS.get(field_type, f"Type {field_type}")


def _enumerate_custom_fields(project):
    """Yield _CustomFieldRecord for every custom field on the supported
    owner classes.  Read-only -- safe inside the Phase-1 UoW envelope
    (no _EnsureWriteEnabled guard on CustomFieldOperations.GetAllFields).

    ``GetAllFields(cls)`` must yield 4-tuples
    ``(field_id, name, field_type, list_root_guid)`` per the T001 fake
    contract.  The legacy 2-tuple shape ``(field_id, name)`` is handled
    defensively for backward compatibility.
    """
    cf_ops = getattr(project, "CustomFields", None)
    if cf_ops is None:
        return
    for cls in _CUSTOM_FIELD_OWNER_CLASSES:
        try:
            for row in cf_ops.GetAllFields(cls):
                if len(row) >= 4:
                    field_id, label, field_type, list_root_guid = (
                        row[0], row[1], row[2], row[3]
                    )
                else:
                    # Legacy 2-tuple path (existing fakes / older flexicon).
                    field_id, label = row[0], row[1]
                    field_type = 0
                    list_root_guid = ""  # normalized from None; str default per _CustomFieldRecord
                yield _CustomFieldRecord(
                    cls, label, field_id,
                    field_type=field_type,
                    list_root_guid=list_root_guid,
                )
        except Exception:
            # Class missing or read error -- continue with other classes.
            continue


def custom_fields_enumerate_source(context, selection):
    """Walk source.CustomFields.GetAllFields per supported owner class.

    T018 per-field filter: if ``selection.leaf_item_picks`` contains an entry
    for ``GrammarCategory.CUSTOM_FIELDS``, only fields whose synthetic guid
    (``"cf:<owner>:<name>"``) is in that frozenset are returned.  An absent key
    means transfer-all (back-compat); an empty frozenset means transfer-none.
    """
    records = list(_enumerate_custom_fields(context.source_handle))
    picks = selection.leaf_item_picks.get(GrammarCategory.CUSTOM_FIELDS)
    if picks is not None:
        records = [r for r in records if r.guid in picks]
    return records


# ---------------------------------------------------------------------------
# Classification helper (T007)
# ---------------------------------------------------------------------------

# Status tokens returned by classify_custom_field.
#   NEW       -- field absent from target; a create action will be required.
#   IN_TARGET -- field present in target by (owner_class, name) match.
#   ""        -- no target bound; classification unavailable (degrade to NEW).
_CF_STATUS_NEW = "NEW"
_CF_STATUS_IN_TARGET = "IN_TARGET"
_CF_STATUS_UNKNOWN = ""


def classify_custom_field(record: "_CustomFieldRecord", target) -> tuple:
    """Classify *record* against *target* by ``(owner_class, name)`` match.

    Parameters
    ----------
    record:
        A ``_CustomFieldRecord`` from the source enumeration.
    target:
        The target project handle (duck-typed; needs
        ``CustomFields.FindField(cls, name)`` and optionally
        ``Cache.MetaDataCacheAccessor.GetFieldType(flid)``).
        May be ``None`` or any object lacking ``CustomFields``.

    Returns
    -------
    (status, type_diff_note) : tuple[str, str | None]
        *status* is one of ``_CF_STATUS_NEW``, ``_CF_STATUS_IN_TARGET``,
        or ``_CF_STATUS_UNKNOWN`` (empty string when no target is bound).

        *type_diff_note* is a non-empty string when the target has a
        same-class/same-name field of a **different** CellarPropertyType,
        otherwise ``None``.

        A type difference is **informational only** -- it never triggers a
        collision and never produces ``IDENTITY_COLLISION`` (FR-008).

    Notes
    -----
    When no target is bound (``None``, or target lacks ``CustomFields``),
    returns ``("", None)`` so the UI can degrade to treat-as-NEW for
    preview safety without raising.
    """
    if target is None:
        return (_CF_STATUS_NEW, None)

    cf_ops = getattr(target, "CustomFields", None)
    if cf_ops is None:
        return (_CF_STATUS_NEW, None)

    # (owner_class, name) match -- the canonical identity for custom fields.
    try:
        tgt_flid = cf_ops.FindField(record.owner_class, record.name)
    except Exception:
        return (_CF_STATUS_NEW, None)

    if not tgt_flid:
        return (_CF_STATUS_NEW, None)

    # Field exists in target.  Check for a type difference (informational).
    type_diff_note = None
    if record.field_type:
        try:
            mdc = target.Cache.MetaDataCacheAccessor
            tgt_type = mdc.GetFieldType(tgt_flid)
            if tgt_type != record.field_type:
                src_label = custom_field_type_label(record.field_type)
                tgt_label = custom_field_type_label(tgt_type)
                type_diff_note = (
                    f"Source type is {src_label} ({record.field_type}), "
                    f"target type is {tgt_label} ({tgt_type}). "
                    f"Values will not be transferred into a mismatched field."
                )
        except Exception:
            # MDC accessor unavailable -- treat as no type info, not an error.
            pass

    return (_CF_STATUS_IN_TARGET, type_diff_note)


def custom_fields_dependencies(piece):
    return ()  # leaf -- no inter-category deps


def custom_fields_required_writing_systems(piece):
    return ()  # WS handled at plan/value-population time, not schema time


def custom_fields_plan_action(piece, context, ws_mapping):
    """T016 — real plan action for custom-field schema definitions.

    Decision table:
    - Field ALREADY PRESENT in target by (owner_class, name) identity:
        -> Skip(ALREADY_PRESENT_BY_IDENTITY, reuse existing flid at Move time)
    - Field ABSENT from target (or target has no CustomFields accessor):
        -> CreateDefinitionAction carrying (owner_class, field_name, field_type,
           list_root_guid) for the PATH-CLOSE-REBIND executor.

    FR-008: type difference on a (class, name) match is NOT an
    IDENTITY_COLLISION -- the field is treated as IN_TARGET and reused.
    No CreateDefinitionAction is emitted for type-diff matches.

    SC-004 ordering: CreateDefinitionActions must precede value-fill
    PlannedActions in RunPlan.actions; the preview builder enforces this
    by processing CUSTOM_FIELDS before entry/sense categories.
    """
    src_guid = piece.guid  # "cf:<owner>:<name>"
    target = context.target_handle
    cf_ops = getattr(target, "CustomFields", None)
    found = False
    if cf_ops is not None:
        try:
            existing_id = cf_ops.FindField(piece.owner_class, piece.name)
            found = bool(existing_id)
        except Exception:
            found = False
    if found:
        return Skip(
            category=GrammarCategory.CUSTOM_FIELDS,
            source_guid=src_guid,
            reason=SkipReason.ALREADY_PRESENT_BY_IDENTITY,
            detail=(
                f"Custom field {piece.owner_class}.{piece.name!r} already "
                f"present in target (matched by (class_id, name) identity; "
                f"custom fields have no LCM Guid)."
            ),
        )
    # Field is NEW in target -- emit a create-definition action.
    list_root = piece.list_root_guid or ""
    return CreateDefinitionAction(
        category=GrammarCategory.CUSTOM_FIELDS,
        source_guid=src_guid,
        owner_class=piece.owner_class,
        field_name=piece.name,
        field_type=piece.field_type,
        list_root_guid=list_root,
        summary=(
            f"Create custom field {piece.owner_class}.{piece.name!r} "
            f"(type {piece.field_type}) in target via MDC AddCustomField."
        ),
    )


def custom_fields_execute_action(action, context, ws_mapping, tag):
    """T019 — value-fill executor for custom fields.

    This path is reached for REUSE actions (field already in target by
    identity match, surfaced as PlannedAction by the preview builder's
    post-definition pass).  Schema creation (CreateDefinitionAction) is
    handled by api._ensure_custom_fields via PATH-CLOSE-REBIND BEFORE
    transfer.execute is invoked; by the time this callback fires, every
    field is guaranteed to exist.

    Value-fill:
    - Look up the target flid by name at the CURRENT open (flids renumber
      on reload -- probe-results.md; never cache flids across schema boundary).
    - Write the source custom-field value onto the already-transferred entry.

    For MVP (T019): no-op -- value population is handled by transfer.execute
    internals on the matched LCM objects.  This stub remains registered so the
    leaf-dispatch loop does not warn on a missing callback.
    """
    return None


# ----- inflection_classes --------------------------------------------------
#
# Inflection classes are IMoInflClass objects under
# LangProject.MorphologicalDataOA.ProdRestrictOA.PossibilitiesOS.
# No GOLD check (user-defined only).
# Factory: IMoInflClassFactory.Create(Guid) + Add to ProdRestrictOA.PossibilitiesOS.

def inflection_classes_enumerate_source(context: RunContext, selection: Selection):
    """Walk source.InflectionFeatures.InflectionClassGetAll()."""
    source = context.source_handle
    if not hasattr(source, "InflectionFeatures"):
        return ()
    return list(source.InflectionFeatures.InflectionClassGetAll())


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
    if hasattr(target, "InflectionFeatures"):
        if _target_has_guid(target.InflectionFeatures.InflectionClassGetAll(), src_guid):
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
    for ic in source.InflectionFeatures.InflectionClassGetAll():
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

    # P0-C hardening: no no-arg fallback (cf. probe-results.md);
    # _safe_add_to_owner surfaces Add failures with orphan-risk message.
    try:
        new_ic = factory.Create(parsed_guid)
    except Exception as e:
        raise RuntimeError(
            f"IMoInflClassFactory does not support Create(Guid); "
            f"cannot align GUID {src_guid}"
        ) from e
    _safe_add_to_owner(new_ic, morph_data.ProdRestrictOA.PossibilitiesOS,
                       "IMoInflClassFactory", src_guid)
    new_ic = IMoInflClass(new_ic)

    # Apply syncable properties.
    src_props = source.InflectionFeatures.GetSyncableProperties(src_obj)
    target.InflectionFeatures.ApplySyncableProperties(new_ic, src_props)

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

    # P0-D hardening: no no-arg fallback (cf. probe-results.md);
    # _safe_add_to_owner surfaces Add failures with orphan-risk message.
    try:
        new_sn = factory.Create(parsed_guid)
    except Exception as e:
        raise RuntimeError(
            f"IMoStemNameFactory does not support Create(Guid); "
            f"cannot align GUID {src_guid}"
        ) from e
    _safe_add_to_owner(new_sn, target_pos.StemNamesOC,
                       "IMoStemNameFactory", src_guid)
    new_sn = IMoStemName(new_sn)

    # Copy Name multistring directly (IMoStemName has Name but may not
    # be covered by a GetSyncableProperties wrapper in flexicon).
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


# ----- shared possibility-list walker (Phase 3b) ---------------------------

def _walk_possibilities(owning_list):
    """Recursive walk of a CmPossibility-shaped hierarchy.

    Iterates `owning_list.PossibilitiesOS` then each item's
    `SubPossibilitiesOS`. Returns a flat list of every node. Used by
    variant_types, complex_form_types, semantic_domains.
    """
    out = []
    if owning_list is None:
        return out
    stack = list(getattr(owning_list, "PossibilitiesOS", []) or [])
    while stack:
        node = stack.pop(0)
        out.append(node)
        subs = getattr(node, "SubPossibilitiesOS", None)
        if subs is not None:
            for child in subs:
                stack.append(child)
    return out


def _walk_possibilities_via_lexdb(source, accessor_name):
    """Resolve source.Cache.LangProject.LexDbOA.<accessor> defensively and
    return the recursive walk. `accessor_name` is e.g. 'VariantEntryTypesOA'.
    """
    try:
        lex_db = source.Cache.LangProject.LexDbOA
    except Exception:
        return []
    list_obj = getattr(lex_db, accessor_name, None)
    return _walk_possibilities(list_obj)


def _walk_semantic_domain_list(source):
    try:
        return _walk_possibilities(source.Cache.LangProject.SemanticDomainListOA)
    except Exception:
        return []


# ----- variant_types (Phase 3b memo step 12; FR-327) -----------------------

def variant_types_enumerate_source(context, selection):
    """Recursive walk of LangProject.LexDbOA.VariantEntryTypesOA.

    Spec 021 per-item trim: when `selection` carries a
    `leaf_item_picks[VARIANT_TYPES]` frozenset, the returned list is
    filtered to only those source objects whose GUID is in the subset.
    A None subset (key absent) => transfer ALL (unchanged behavior for
    every pre-spec-021 caller). GUIDs on BOTH sides are normalized via
    `_guid_str_from` (spec 010 GUID-normalization invariant).
    """
    records = _walk_possibilities_via_lexdb(context.source_handle,
                                            "VariantEntryTypesOA")
    if selection is not None:
        picks = selection.leaf_picks_for(GrammarCategory.VARIANT_TYPES)
        if picks is not None:
            records = [r for r in records if _guid_str_from(r) in picks]
    return records


def variant_types_dependencies(piece):
    """FR-327: yield (INFLECTION_FEATURES, val_guid) for each
    IFsSymFeatVal referenced by the variant type's InflFeatsOA constraint.

    ILexEntryInflType only -- base ILexEntryType has no InflFeatsOA.
    Empty tuple when piece is a base variant type or InflFeatsOA is None.
    """
    struct = getattr(piece, "InflFeatsOA", None)
    if struct is None:
        return ()
    specs = getattr(struct, "FeatureSpecsOC", None)
    if specs is None:
        return ()
    deps = []
    for spec in specs:
        val = getattr(spec, "ValueRA", None)
        if val is None:
            continue
        try:
            val_guid = _guid_str_from(val)
        except Exception:
            continue
        deps.append((GrammarCategory.INFLECTION_FEATURES, val_guid))
    return tuple(deps)


def variant_types_required_writing_systems(piece):
    return ()


def variant_types_plan_action(piece, context, ws_mapping):
    """GOLD-aware: skip GOLD variant types; edit-copy merge for present custom; Add for absent.

    Uses the shared _plan_gold_reserved_edit helper (spec 017 FR-E10).
    """
    def _target_iter(target):
        return _walk_possibilities_via_lexdb(target, "VariantEntryTypesOA")

    result = _plan_gold_reserved_edit(
        piece, GrammarCategory.VARIANT_TYPES, context, _target_iter
    )
    if result is not None:
        return result
    src_guid = _guid_str_from(piece)
    return PlannedAction(
        category=GrammarCategory.VARIANT_TYPES,
        source_guid=src_guid,
        intended_target_guid=src_guid,
        summary=f"VariantType guid={src_guid[:8]}...",
    )


def variant_types_execute_action(action, context, ws_mapping, tag):
    """Create variant type with GUID preserved.

    Uses ILexEntryInflTypeFactory.Create(Guid, owner) -- the 2-arg
    overload that ICmPossibilityFactory inherits. Top-level owner is the
    LexDb's VariantEntryTypesOA possibility list; nested owners are
    parent ILexEntryType objects.
    """
    from SIL.LCModel import ILexEntryInflTypeFactory, ICmObject, ICmPossibility, ICmPossibilityList
    from System import Guid as DotNetGuid

    if __package__:
        from .residue import apply_carrier_b
    else:
        from residue import apply_carrier_b  # type: ignore

    source = context.source_handle
    target = context.target_handle
    src_guid = action.source_guid

    # Locate source object in the recursive walk.
    src_obj = None
    for vt in _walk_possibilities_via_lexdb(source, "VariantEntryTypesOA"):
        if _guid_str_from(vt) == src_guid:
            src_obj = vt
            break
    if src_obj is None:
        return None

    cache = getattr(target, "Cache")
    ws = cache.DefaultAnalWs
    target_list = cache.LangProject.LexDbOA.VariantEntryTypesOA

    # Resolve owner: nested (parent ILexEntryType) vs top-level (possibility list).
    # Cast to ICmObject so ClassName is reliably available (raw .Owner on
    # source object returns ICmObjectOrId where ClassName may not surface).
    src_owner_guid = None
    try:
        owner = ICmObject(src_obj).Owner
        owner_class = getattr(owner, "ClassName", "")
        if owner_class and "EntryType" in owner_class:
            src_owner_guid = _guid_str_from(owner)
    except Exception:
        pass

    parsed_guid = DotNetGuid.Parse(src_guid)
    # Interface-cast wrapper required for pythonnet overload resolution.
    factory = ILexEntryInflTypeFactory(target.GetFactory(ILexEntryInflTypeFactory))

    # ILexEntryInflTypeFactory inherits only the 1-arg Create(Guid) overload
    # from the generic ILcmFactory<T> base (the 2-arg ICmPossibilityFactory
    # overloads don't surface through pythonnet for this subclass). Use
    # Create(Guid) + manual Add to the appropriate owning collection.
    try:
        new_vt = factory.Create(parsed_guid)
    except Exception as e:
        raise RuntimeError(
            f"ILexEntryInflTypeFactory.Create(Guid) failed for "
            f"{src_guid}: {e!r}"
        ) from e

    if src_owner_guid:
        target_parent_raw = None
        for vt in _walk_possibilities(target_list):
            if _guid_str_from(vt) == src_owner_guid:
                target_parent_raw = vt
                break
        if target_parent_raw is None:
            return None
        _safe_add_to_owner(
            new_vt, ICmPossibility(target_parent_raw).SubPossibilitiesOS,
            "ILexEntryInflTypeFactory", src_guid,
        )
    else:
        _safe_add_to_owner(
            new_vt, ICmPossibilityList(target_list).PossibilitiesOS,
            "ILexEntryInflTypeFactory", src_guid,
        )

    # ApplySyncableProperties via flexicon's BaseOperations if available.
    apply_carrier_b(new_vt, ws, tag)
    return new_vt


# ----- complex_form_types (Phase 3b memo step 13) --------------------------

def complex_form_types_enumerate_source(context, selection):
    """Recursive walk of LangProject.LexDbOA.ComplexEntryTypesOA.

    Spec 021 per-item trim: when `selection` carries a
    `leaf_item_picks[COMPLEX_FORM_TYPES]` frozenset, the returned list is
    filtered to only those source objects whose GUID is in the subset.
    A None subset (key absent) => transfer ALL (unchanged behavior for
    every pre-spec-021 caller). GUIDs on BOTH sides are normalized via
    `_guid_str_from` (spec 010 GUID-normalization invariant).
    """
    records = _walk_possibilities_via_lexdb(context.source_handle,
                                            "ComplexEntryTypesOA")
    if selection is not None:
        picks = selection.leaf_picks_for(GrammarCategory.COMPLEX_FORM_TYPES)
        if picks is not None:
            records = [r for r in records if _guid_str_from(r) in picks]
    return records


def complex_form_types_dependencies(piece):
    return ()


def complex_form_types_required_writing_systems(piece):
    return ()


def complex_form_types_plan_action(piece, context, ws_mapping):
    """GOLD-aware: skip GOLD complex form types; edit-copy merge for present custom; Add for absent.

    Uses the shared _plan_gold_reserved_edit helper (spec 017 FR-E10).
    """
    def _target_iter(target):
        return _walk_possibilities_via_lexdb(target, "ComplexEntryTypesOA")

    result = _plan_gold_reserved_edit(
        piece, GrammarCategory.COMPLEX_FORM_TYPES, context, _target_iter
    )
    if result is not None:
        return result
    src_guid = _guid_str_from(piece)
    return PlannedAction(
        category=GrammarCategory.COMPLEX_FORM_TYPES,
        source_guid=src_guid,
        intended_target_guid=src_guid,
        summary=f"ComplexFormType guid={src_guid[:8]}...",
    )


def complex_form_types_execute_action(action, context, ws_mapping, tag):
    """Create complex form type with GUID preserved.

    Uses ILexEntryTypeFactory.Create(Guid, owner). Owner is either the
    LexDb's ComplexEntryTypesOA possibility list (top-level) or a
    parent ILexEntryType (nested).
    """
    from SIL.LCModel import ILexEntryTypeFactory, ICmObject, ICmPossibility, ICmPossibilityList
    from System import Guid as DotNetGuid

    if __package__:
        from .residue import apply_carrier_b
    else:
        from residue import apply_carrier_b  # type: ignore

    source = context.source_handle
    target = context.target_handle
    src_guid = action.source_guid

    src_obj = None
    for cft in _walk_possibilities_via_lexdb(source, "ComplexEntryTypesOA"):
        if _guid_str_from(cft) == src_guid:
            src_obj = cft
            break
    if src_obj is None:
        return None

    cache = getattr(target, "Cache")
    ws = cache.DefaultAnalWs
    target_list = cache.LangProject.LexDbOA.ComplexEntryTypesOA

    # Owner-type discrimination (see variant_types for rationale).
    src_owner_guid = None
    try:
        owner = ICmObject(src_obj).Owner
        owner_class = getattr(owner, "ClassName", "")
        if owner_class and "EntryType" in owner_class:
            src_owner_guid = _guid_str_from(owner)
    except Exception:
        pass

    parsed_guid = DotNetGuid.Parse(src_guid)
    factory = ILexEntryTypeFactory(target.GetFactory(ILexEntryTypeFactory))

    # 1-arg Create(Guid) + manual Add (see variant_types for rationale).
    try:
        new_cft = factory.Create(parsed_guid)
    except Exception as e:
        raise RuntimeError(
            f"ILexEntryTypeFactory.Create(Guid) failed for {src_guid}: {e!r}"
        ) from e

    if src_owner_guid:
        target_parent_raw = None
        for cft in _walk_possibilities(target_list):
            if _guid_str_from(cft) == src_owner_guid:
                target_parent_raw = cft
                break
        if target_parent_raw is None:
            return None
        _safe_add_to_owner(
            new_cft, ICmPossibility(target_parent_raw).SubPossibilitiesOS,
            "ILexEntryTypeFactory", src_guid,
        )
    else:
        _safe_add_to_owner(
            new_cft, ICmPossibilityList(target_list).PossibilitiesOS,
            "ILexEntryTypeFactory", src_guid,
        )

    apply_carrier_b(new_cft, ws, tag)
    return new_cft


# ----- semantic_domains (Phase 3b memo step 13b; FR-326) -------------------

def semantic_domains_enumerate_source(context, selection):
    """Recursive walk of LangProject.SemanticDomainListOA."""
    return _walk_semantic_domain_list(context.source_handle)


def semantic_domains_dependencies(piece):
    return ()


def semantic_domains_required_writing_systems(piece):
    return ()


def semantic_domains_plan_action(piece, context, ws_mapping):
    """FR-326: skip the ~1700-entry GOLD catalog; edit-copy merge for present custom; Add for absent.

    Uses the shared _plan_gold_reserved_edit helper (spec 017 FR-E10).
    """
    def _target_iter(target):
        return _walk_semantic_domain_list(target)

    result = _plan_gold_reserved_edit(
        piece, GrammarCategory.SEMANTIC_DOMAINS, context, _target_iter
    )
    if result is not None:
        return result
    src_guid = _guid_str_from(piece)
    return PlannedAction(
        category=GrammarCategory.SEMANTIC_DOMAINS,
        source_guid=src_guid,
        intended_target_guid=src_guid,
        summary=f"SemanticDomain guid={src_guid[:8]}...",
    )


def semantic_domains_execute_action(action, context, ws_mapping, tag):
    """Create custom semantic domain with GUID preserved.

    Uses ICmSemanticDomainFactory.Create(Guid, owner). Owner is either
    the LangProject's SemanticDomainListOA possibility list or a parent
    ICmSemanticDomain (custom domain nested under a custom parent).
    """
    from SIL.LCModel import ICmSemanticDomainFactory, ICmObject, ICmPossibility, ICmPossibilityList
    from System import Guid as DotNetGuid

    if __package__:
        from .residue import apply_carrier_b
    else:
        from residue import apply_carrier_b  # type: ignore

    source = context.source_handle
    target = context.target_handle
    src_guid = action.source_guid

    src_obj = None
    for sd in _walk_semantic_domain_list(source):
        if _guid_str_from(sd) == src_guid:
            src_obj = sd
            break
    if src_obj is None:
        return None

    cache = getattr(target, "Cache")
    ws = cache.DefaultAnalWs
    target_list = cache.LangProject.SemanticDomainListOA

    # Owner-type discrimination (see variant_types for rationale).
    src_owner_guid = None
    try:
        owner = ICmObject(src_obj).Owner
        owner_class = getattr(owner, "ClassName", "")
        if owner_class == "CmSemanticDomain":
            src_owner_guid = _guid_str_from(owner)
    except Exception:
        pass

    parsed_guid = DotNetGuid.Parse(src_guid)
    factory = ICmSemanticDomainFactory(target.GetFactory(ICmSemanticDomainFactory))

    # 1-arg Create(Guid) + manual Add (see variant_types for rationale).
    try:
        new_sd = factory.Create(parsed_guid)
    except Exception as e:
        raise RuntimeError(
            f"ICmSemanticDomainFactory.Create(Guid) failed for {src_guid}: {e!r}"
        ) from e

    if src_owner_guid:
        target_parent_raw = None
        for sd in _walk_possibilities(target_list):
            if _guid_str_from(sd) == src_owner_guid:
                target_parent_raw = sd
                break
        if target_parent_raw is None:
            return None
        _safe_add_to_owner(
            new_sd, ICmPossibility(target_parent_raw).SubPossibilitiesOS,
            "ICmSemanticDomainFactory", src_guid,
        )
    else:
        _safe_add_to_owner(
            new_sd, ICmPossibilityList(target_list).PossibilitiesOS,
            "ICmSemanticDomainFactory", src_guid,
        )

    apply_carrier_b(new_sd, ws, tag)
    return new_sd


# ----- adhoc_compound_rules ------------------------------------------------
# Feature 018-rules-page (T003-T011, crew-approved 2026-07-05): per-subclass
# dispatch for five LCM subclasses (IMoAlloAdhocProhib, IMoMorphAdhocProhib,
# IMoAdhocProhibGr, IMoEndoCompound, IMoExoCompound).  Ground truth:
# probe-results.md [CONFIRMED LIVE 2026-07-05].
#
# Engine reuses the phonological_rules pattern: _phonology_simple_plan (GUID-first
# skip/add), _create_with_guid (Create(Guid)+owner.Add for owning collections),
# and manual reference wiring after ApplySyncableProperties (which only carries
# Name/Description/StratumGuid/Disabled).  Notes from the QC/domain review:
#   - Compound member/result MSAs are OWNED-ATOMIC (OA): created via
#     IMoStemMsaFactory.Create(Guid) then assigned to the OA slot
#     (rule.LeftMsaOA = msa) — the OA setter establishes ownership; this is
#     deliberately NOT owner.Add() (that idiom is for owning collections).
#   - enumerate_source sorts IMoAdhocProhibGr group nodes LAST so their child
#     co-prohibitions exist in the target before MembersOC re-parenting (SC-001
#     scenario 4).
#   - All GUID extraction routes through _guid_str_from (normalization invariant);
#     plan_action carries a GOLD_INVIOLABLE early-return (FR-003); unhandled
#     subclass and missing-source both fail loud (FR-006/SC-008).
# Deferred: the live write round-trip (Esperanto -> throwaway) that would prove
# OA-ownership persists through commit — see STATUS.md / probe-results.md.

# --- T003 -------------------------------------------------------------------

_ADHOC_COMPOUND_SUBCLASS_INFO = None  # populated lazily on first LCM import

def _rule_subclass_info(obj):
    """Return (class_name, factory_iface, ref_spec) for the five rule subclasses.

    `obj` may be a flexicon wrapper — unwrap via `.concrete` first.
    Dispatches on ICmObject(obj).ClassName.

    ref_spec is a dict of field-name -> ('RA'|'RS', ref_kind) used by
    execute_action for reference wiring.  An empty dict means no extra
    ref wiring beyond GetSyncableProperties (e.g. compound base scalars).

    Raises RuntimeError loudly for any unrecognised ClassName (FR-006/SC-008).
    """
    # Unwrap flexicon wrapper if present
    concrete = getattr(obj, "concrete", obj)
    try:
        from SIL.LCModel import (
            ICmObject,
            IMoAlloAdhocProhibFactory,
            IMoMorphAdhocProhibFactory,
            IMoAdhocProhibGrFactory,
            IMoEndoCompoundFactory,
            IMoExoCompoundFactory,
        )
        class_name = ICmObject(concrete).ClassName
    except Exception:
        # Fake/duck-typed test objects: fall back to a `class_name` attr
        class_name = getattr(concrete, "class_name",
                             getattr(concrete, "ClassName", None))
        IMoAlloAdhocProhibFactory = "IMoAlloAdhocProhibFactory"
        IMoMorphAdhocProhibFactory = "IMoMorphAdhocProhibFactory"
        IMoAdhocProhibGrFactory = "IMoAdhocProhibGrFactory"
        IMoEndoCompoundFactory = "IMoEndoCompoundFactory"
        IMoExoCompoundFactory = "IMoExoCompoundFactory"

    _DISPATCH = {
        "MoAlloAdhocProhib": (
            "MoAlloAdhocProhib",
            IMoAlloAdhocProhibFactory,
            {
                "FirstAllomorphRA": ("RA", "IMoForm"),
                "RestOfAllosRS": ("RS", "IMoForm"),
                "AllomorphsRS": ("RS", "IMoForm"),
            },
        ),
        "MoMorphAdhocProhib": (
            "MoMorphAdhocProhib",
            IMoMorphAdhocProhibFactory,
            {
                "FirstMorphemeRA": ("RA", "IMoMorphSynAnalysis"),
                "RestOfMorphsRS": ("RS", "IMoMorphSynAnalysis"),
                "MorphemesRS": ("RS", "IMoMorphSynAnalysis"),
            },
        ),
        "MoAdhocProhibGr": (
            "MoAdhocProhibGr",
            IMoAdhocProhibGrFactory,
            {},  # children handled separately in T011
        ),
        "MoEndoCompound": (
            "MoEndoCompound",
            IMoEndoCompoundFactory,
            {},  # owned MSA wiring handled separately in T010
        ),
        "MoExoCompound": (
            "MoExoCompound",
            IMoExoCompoundFactory,
            {},  # owned MSA wiring handled separately in T010
        ),
    }
    info = _DISPATCH.get(class_name)
    if info is None:
        raise RuntimeError(
            f"_rule_subclass_info: unrecognised ClassName {class_name!r} — "
            f"not one of the five expected adhoc/compound rule subclasses "
            f"(FR-006/SC-008). Object: {obj!r}"
        )
    return info


# --- T004 -------------------------------------------------------------------

def _rules_enumerate_all(source):
    """Yield every leaf prohibition and compound rule from a source project.

    Adhoc prohibitions come from
      source.Cache.LangProject.MorphologicalDataOA.AdhocCoProhibitionsOS.
    IMoAdhocProhibGr grouping nodes are recursed via MembersOC (yielding the
    GROUP node itself, then recursing — callers that want only leaves should
    filter by class_name != 'MoAdhocProhibGr').

    Compound rules come from
      source.Cache.LangProject.MorphologicalDataOA.CompoundRulesOS.

    flexicon wrapper objects are unwrapped via .concrete before yielding so
    callers always receive the concrete LCM objects.

    getattr/cast guards prevent AttributeError/TypeError from bubbling.
    """
    # Helper: unwrap flexicon wrapper if present
    def _unwrap(obj):
        return getattr(obj, "concrete", obj)

    # Recurse into an adhoc collection (list-like or OS)
    def _recurse_adhoc(coll):
        try:
            items = list(coll)
        except (TypeError, AttributeError):
            return
        for raw in items:
            obj = _unwrap(raw)
            yield obj
            # If this is a grouping node, recurse into its MembersOC
            members = getattr(obj, "MembersOC", None)
            if members is not None:
                for child in _recurse_adhoc(members):
                    yield child

    # Adhoc prohibitions from the OS collection
    try:
        morph_data = source.Cache.LangProject.MorphologicalDataOA
        adhoc_os = morph_data.AdhocCoProhibitionsOS
        for obj in _recurse_adhoc(adhoc_os):
            yield obj
    except AttributeError:
        # Fall back: try project-level wrapper (for flexicon projects).
        # GetAllAdhocCoProhibitions may flatten groups+children; dedupe by GUID
        # to avoid double-yielding a child that was already yielded as part of
        # its group's MembersOC traversal.
        try:
            _seen_guids: set = set()
            for raw in source.MorphRules.GetAllAdhocCoProhibitions():
                obj = _unwrap(raw)
                obj_guid = _guid_str_from(obj)
                if obj_guid not in _seen_guids:
                    _seen_guids.add(obj_guid)
                    yield obj
                members = getattr(obj, "MembersOC", None)
                if members is not None:
                    for child in _recurse_adhoc(members):
                        child_guid = _guid_str_from(child)
                        if child_guid not in _seen_guids:
                            _seen_guids.add(child_guid)
                            yield child
        except (AttributeError, TypeError):
            pass

    # Compound rules from CompoundRulesOS
    try:
        morph_data = source.Cache.LangProject.MorphologicalDataOA
        for raw in morph_data.CompoundRulesOS:
            yield _unwrap(raw)
    except AttributeError:
        try:
            for raw in source.MorphRules.GetAllCompoundRules():
                yield _unwrap(raw)
        except (AttributeError, TypeError):
            pass


# --- T005 -------------------------------------------------------------------

def adhoc_compound_rules_enumerate_source(context, selection):
    """Enumerate all adhoc/compound rules from source, filtered by leaf_item_picks.

    Absent key => transfer ALL.  GOLD-shipped rules excluded per Constitution I.
    """
    source = context.source_handle
    if source is None:
        return ()
    picks = selection.leaf_picks_for(GrammarCategory.ADHOC_COMPOUND_RULES)
    results = []
    for obj in _rules_enumerate_all(source):
        if _is_gold(obj):
            continue
        if picks is not None:
            if _guid_str_from(obj) not in picks:
                continue
        results.append(obj)
    # SC-001 scenario-4: group re-parenting in execute_action requires children
    # to exist in the target before MembersOC is populated.  Sort group nodes
    # (MoAdhocProhibGr) last so all children are created first — lowest-risk
    # ordering fix that works within the existing sequential execute_action loop.
    results.sort(key=lambda o: 1 if getattr(o, "ClassName", "") == "MoAdhocProhibGr" else 0)
    return results


# --- T016 -------------------------------------------------------------------

def adhoc_compound_rules_dependencies(piece):
    """Yield member-reference GUIDs for closure (FR-005).

    Per-subclass dispatch with cast/getattr guards:
    - MoAlloAdhocProhib  -> allomorph (IMoForm) GUIDs via AllomorphsRS
    - MoMorphAdhocProhib -> morpheme (IMoMorphSynAnalysis) GUID via MorphemesRS
    - MoAdhocProhibGr    -> union of children's deps (recurse MembersOC)
    - MoEndoCompound     -> LeftMsaOA / RightMsaOA / OverridingMsaOA
                            PartOfSpeechRA POS GUIDs
    - MoExoCompound      -> LeftMsaOA / RightMsaOA / ToMsaOA
                            PartOfSpeechRA POS GUIDs

    All GUIDs pass through _guid_str_from (GUID-normalization invariant).
    """
    concrete = getattr(piece, "concrete", piece)

    def _pos_guid_from_msa(msa):
        """Return normalized POS GUID from an owned IMoStemMsa, or None."""
        try:
            pos = getattr(msa, "PartOfSpeechRA", None)
            if pos is None:
                return None
            return _guid_str_from(pos)
        except Exception:
            return None

    # Determine subclass
    try:
        from SIL.LCModel import ICmObject
        class_name = ICmObject(concrete).ClassName
    except Exception:
        class_name = getattr(concrete, "class_name",
                             getattr(concrete, "ClassName", None))

    deps = []

    if class_name == "MoAlloAdhocProhib":
        # AllomorphsRS yields the full member sequence (IMoForm GUIDs)
        try:
            for allo in getattr(concrete, "AllomorphsRS", None) or []:
                g = _guid_str_from(allo)
                if g:
                    deps.append(g)
        except (AttributeError, TypeError):
            pass
        # Also include FirstAllomorphRA in case AllomorphsRS is read-only/empty
        try:
            first = getattr(concrete, "FirstAllomorphRA", None)
            if first is not None:
                g = _guid_str_from(first)
                if g and g not in deps:
                    deps.append(g)
        except (AttributeError, TypeError):
            pass

    elif class_name == "MoMorphAdhocProhib":
        # MorphemesRS yields the full member sequence (IMoMorphSynAnalysis GUIDs)
        try:
            for msa in getattr(concrete, "MorphemesRS", None) or []:
                g = _guid_str_from(msa)
                if g:
                    deps.append(g)
        except (AttributeError, TypeError):
            pass
        # Also include FirstMorphemeRA
        try:
            first = getattr(concrete, "FirstMorphemeRA", None)
            if first is not None:
                g = _guid_str_from(first)
                if g and g not in deps:
                    deps.append(g)
        except (AttributeError, TypeError):
            pass

    elif class_name == "MoAdhocProhibGr":
        # Union of children's deps (recurse)
        try:
            for child in getattr(concrete, "MembersOC", None) or []:
                for g in adhoc_compound_rules_dependencies(child):
                    if g not in deps:
                        deps.append(g)
        except (AttributeError, TypeError):
            pass

    elif class_name == "MoEndoCompound":
        # LeftMsaOA, RightMsaOA, OverridingMsaOA -> POS GUIDs
        for slot in ("LeftMsaOA", "RightMsaOA", "OverridingMsaOA"):
            try:
                msa = getattr(concrete, slot, None)
                if msa is not None:
                    g = _pos_guid_from_msa(msa)
                    if g and g not in deps:
                        deps.append(g)
            except (AttributeError, TypeError):
                pass

    elif class_name == "MoExoCompound":
        # LeftMsaOA, RightMsaOA, ToMsaOA -> POS GUIDs
        for slot in ("LeftMsaOA", "RightMsaOA", "ToMsaOA"):
            try:
                msa = getattr(concrete, slot, None)
                if msa is not None:
                    g = _pos_guid_from_msa(msa)
                    if g and g not in deps:
                        deps.append(g)
            except (AttributeError, TypeError):
                pass

    # Unknown subclass: return empty (closure won't fail; FR-006 fires in execute)
    return tuple(deps)


def adhoc_compound_rules_required_writing_systems(piece):
    """No additional writing-system probing needed (parity with phonological_rules)."""
    return ()


# --- T007 -------------------------------------------------------------------

def adhoc_compound_rules_plan_action(piece, context, ws_mapping):
    """GUID-first Skip-if-present / PlannedAction for each rule subclass."""
    # FR-003 defense-in-depth: skip GOLD pieces even if enumerate missed them.
    if _is_gold(piece):
        return Skip(
            category=GrammarCategory.ADHOC_COMPOUND_RULES,
            source_guid=_guid_str_from(piece),
            reason=SkipReason.GOLD_INVIOLABLE,
            detail=(
                f"Item is a GOLD object (CatalogSourceId="
                f"{getattr(piece, 'CatalogSourceId', '?')!r}); "
                "not transferred per FR-022 / Principle I."
            ),
        )
    # _phonology_simple_plan does GUID-first skip/add against a target iterator;
    # for rules the target collection is CompoundRulesOS + AdhocCoProhibitionsOS.
    # We reuse the existing helper by providing a synthetic ops_attr; however
    # since rules live in two OS collections we do the check inline.
    src_guid = _guid_str_from(piece)
    target = context.target_handle
    if target is not None:
        # Check both collections for an existing object with this GUID
        def _iter_target_rules(tgt):
            try:
                morph_data = tgt.Cache.LangProject.MorphologicalDataOA
                try:
                    for obj in morph_data.AdhocCoProhibitionsOS:
                        yield obj
                except (AttributeError, TypeError):
                    pass
                try:
                    for obj in morph_data.CompoundRulesOS:
                        yield obj
                except (AttributeError, TypeError):
                    pass
            except AttributeError:
                pass
        if _target_has_guid(_iter_target_rules(target), src_guid):
            return Skip(
                category=GrammarCategory.ADHOC_COMPOUND_RULES,
                source_guid=src_guid,
                reason=SkipReason.ALREADY_PRESENT_BY_GUID,
                detail=f"AdhocCompoundRule GUID {src_guid[:8]}... already present in target.",
            )
    return PlannedAction(
        category=GrammarCategory.ADHOC_COMPOUND_RULES,
        source_guid=src_guid,
        intended_target_guid=src_guid,
        summary=f"AdhocCompoundRule guid={src_guid[:8]}...",
    )


# --- T008-T011 --------------------------------------------------------------

def adhoc_compound_rules_execute_action(action, context, ws_mapping, tag):
    """Create rule + apply syncable properties + wire references.

    Dispatch:
    - MoAlloAdhocProhib: T009 reference wiring (allomorphs)
    - MoMorphAdhocProhib: T009 reference wiring (morphemes)
    - MoAdhocProhibGr: T011 group re-parenting
    - MoEndoCompound: T010 owned MSA wiring (Left/Right/Overriding + HeadLast)
    - MoExoCompound: T010 owned MSA wiring (Left/Right/ToMsa)

    Raises RuntimeError for unhandled subclass (FR-006/SC-008).
    """
    from SIL.LCModel import (
        ICmObject,
        IMoAlloAdhocProhibFactory,
        IMoMorphAdhocProhibFactory,
        IMoAdhocProhibGrFactory,
        IMoEndoCompoundFactory,
        IMoExoCompoundFactory,
        IMoStemMsaFactory,
        IPartOfSpeech,
    )
    if __package__:
        from .residue import apply_carrier_b
    else:
        from residue import apply_carrier_b  # type: ignore

    source = context.source_handle
    target = context.target_handle
    src_guid = action.source_guid

    # Locate source object
    src_rule = None
    for obj in _rules_enumerate_all(source):
        if _guid_str_from(obj) == src_guid:
            src_rule = obj
            break
    if src_rule is None:
        raise RuntimeError(
            f"adhoc_compound_rules_execute_action: source object GUID "
            f"{src_guid!r} not found in source project (FR-006/SC-008)."
        )

    # Dispatch on subclass
    class_name, factory_iface, _ref_spec = _rule_subclass_info(src_rule)

    cache = getattr(target, "Cache")
    morph_data = cache.LangProject.MorphologicalDataOA

    # Determine owner collection (compound rules OS vs adhoc OS)
    if class_name in ("MoEndoCompound", "MoExoCompound"):
        owner_coll = morph_data.CompoundRulesOS
    else:
        # Adhoc: all top-level adhoc items go into AdhocCoProhibitionsOS;
        # group children are re-parented in T011.
        owner_coll = morph_data.AdhocCoProhibitionsOS

    new_rule, _preserved = _create_with_guid(factory_iface, owner_coll, src_guid, target)

    # Apply scalar/text syncable properties (Name, Description, Disabled, StratumGuid)
    try:
        props = source.MorphRules.GetSyncableProperties(src_rule)
        target.MorphRules.ApplySyncableProperties(new_rule, props, ws_map=ws_mapping)
    except (AttributeError, TypeError):
        pass

    # Wire StratumRA manually (mirrors phonological_rules_execute_action)
    try:
        src_stratum = getattr(src_rule, "StratumRA", None)
        if src_stratum is not None:
            src_stratum_guid = str(ICmObject(src_stratum).Guid).lower()
            for tgt_stratum in target.Strata.GetAll():
                if str(ICmObject(tgt_stratum).Guid).lower() == src_stratum_guid:
                    new_rule.StratumRA = tgt_stratum
                    break
    except (AttributeError, TypeError):
        pass

    # --- T009: adhoc reference wiring ----------------------------------------
    if class_name == "MoAlloAdhocProhib":
        # Wire FirstAllomorphRA (RA -> IMoForm)
        try:
            first_allo = getattr(src_rule, "FirstAllomorphRA", None)
            if first_allo is not None:
                fa_guid = str(ICmObject(first_allo).Guid).lower()
                tgt_allo = _find_target_obj_by_guid(
                    _iter_all_allomorphs(target), fa_guid)
                if tgt_allo is not None:
                    new_rule.FirstAllomorphRA = tgt_allo
        except (AttributeError, TypeError):
            pass
        # Wire AllomorphsRS (read-only seq; use RestOfAllosRS add pattern)
        # AllomorphsRS is computed from FirstAllomorphRA + RestOfAllosRS.
        # We wire RestOfAllosRS by adding each resolved target allomorph.
        try:
            rest_allos = list(getattr(src_rule, "RestOfAllosRS", None) or [])
            for src_allo in rest_allos:
                a_guid = str(ICmObject(src_allo).Guid).lower()
                tgt_allo = _find_target_obj_by_guid(
                    _iter_all_allomorphs(target), a_guid)
                if tgt_allo is not None:
                    try:
                        new_rule.RestOfAllosRS.Add(tgt_allo)
                    except (AttributeError, TypeError):
                        pass
        except (AttributeError, TypeError):
            pass

    elif class_name == "MoMorphAdhocProhib":
        # Wire FirstMorphemeRA (RA -> IMoMorphSynAnalysis)
        try:
            first_morph = getattr(src_rule, "FirstMorphemeRA", None)
            if first_morph is not None:
                fm_guid = str(ICmObject(first_morph).Guid).lower()
                tgt_msa = _find_target_obj_by_guid(
                    _iter_all_msas(target), fm_guid)
                if tgt_msa is not None:
                    new_rule.FirstMorphemeRA = tgt_msa
        except (AttributeError, TypeError):
            pass
        # Wire RestOfMorphsRS
        try:
            rest_morphs = list(getattr(src_rule, "RestOfMorphsRS", None) or [])
            for src_msa in rest_morphs:
                m_guid = _guid_str_from(src_msa)
                tgt_msa = _find_target_obj_by_guid(
                    _iter_all_msas(target), m_guid)
                if tgt_msa is not None:
                    try:
                        new_rule.RestOfMorphsRS.Add(tgt_msa)
                    except (AttributeError, TypeError):
                        pass
        except (AttributeError, TypeError):
            pass

    # --- T011: IMoAdhocProhibGr group re-parenting ----------------------------
    elif class_name == "MoAdhocProhibGr":
        # Children were already created in the top-level OS; move kept ones
        # into the created group's MembersOC.  (Children not in scope => skipped
        # already by enumerate; this handles the parent-group itself.)
        # The group node is created above (in AdhocCoProhibitionsOS).
        # Child objects are NOT created here; they were enumerated as separate
        # items and will get their own execute_action calls — here we re-parent
        # children that already exist in the target by GUID into MembersOC.
        try:
            src_members = list(getattr(src_rule, "MembersOC", None) or [])
            for src_child in src_members:
                child_guid = _guid_str_from(src_child)
                # Find child in target top-level OS (it may have just been created)
                tgt_child = _find_target_obj_by_guid(
                    list(morph_data.AdhocCoProhibitionsOS), child_guid)
                if tgt_child is not None:
                    try:
                        # Remove from top-level OS, add to group's MembersOC
                        morph_data.AdhocCoProhibitionsOS.Remove(tgt_child)
                        new_rule.MembersOC.Add(tgt_child)
                    except (AttributeError, TypeError):
                        pass
        except (AttributeError, TypeError):
            pass

    # --- T010: compound owned-MSA wiring -------------------------------------
    elif class_name in ("MoEndoCompound", "MoExoCompound"):
        _wire_compound_msas(src_rule, new_rule, class_name, target, cache,
                            IMoStemMsaFactory, IPartOfSpeech, ICmObject)

    else:
        raise RuntimeError(
            f"adhoc_compound_rules_execute_action: unhandled subclass "
            f"{class_name!r} (FR-006/SC-008)"
        )

    try:
        apply_carrier_b(new_rule, cache.DefaultAnalWs, tag, strict=False)
    except Exception:
        pass
    return new_rule


def _iter_all_allomorphs(project):
    """Yield every IMoForm from all lexical entries in the project.

    Used for resolving FirstAllomorphRA / RestOfAllosRS refs by GUID.
    """
    try:
        for entry in project.Cache.LangProject.LexDbOA.Entries:
            try:
                for allo in entry.AlternateFormsOS:
                    yield allo
            except (AttributeError, TypeError):
                pass
            try:
                lf = entry.LexemeFormOA
                if lf is not None:
                    yield lf
            except (AttributeError, TypeError):
                pass
    except (AttributeError, TypeError):
        pass


def _iter_all_msas(project):
    """Yield every IMoMorphSynAnalysis from all lexical entries in the project.

    Used for resolving FirstMorphemeRA / RestOfMorphsRS refs by GUID.
    """
    try:
        for entry in project.Cache.LangProject.LexDbOA.Entries:
            try:
                for msa in entry.MorphoSyntaxAnalysesOC:
                    yield msa
            except (AttributeError, TypeError):
                pass
    except (AttributeError, TypeError):
        pass


def _wire_compound_msas(src_rule, new_rule, class_name, target, cache,
                        IMoStemMsaFactory, IPartOfSpeech, ICmObject):
    """Create owned IMoStemMsa children for compound rule member/result slots.

    For each of LeftMsaOA, RightMsaOA, and (endo) OverridingMsaOA / (exo) ToMsaOA:
    - Create a new IMoStemMsa in the target with GUID preserved.
    - Wire its PartOfSpeechRA to the resolved target POS (by source POS GUID).
    - Assign the new MSA to the corresponding slot on new_rule.

    Also carries HeadLast (bool) for IMoEndoCompound.
    Also carries LinkerOA if present (both subtypes).
    """
    def _resolve_pos(src_msa):
        """Return target POS for src_msa.PartOfSpeechRA, or None."""
        try:
            src_pos = src_msa.PartOfSpeechRA
            if src_pos is None:
                return None
            src_pos_guid = str(ICmObject(src_pos).Guid).lower()
            for tgt_pos in _iter_all_pos(target):
                if str(ICmObject(tgt_pos).Guid).lower() == src_pos_guid:
                    return tgt_pos
        except (AttributeError, TypeError):
            pass
        return None

    def _create_owned_msa(src_msa, parent_rule, slot_name):
        """Create an IMoStemMsa owned by the compound rule and assign to slot."""
        try:
            msa_guid = str(ICmObject(src_msa).Guid).lower()
        except (AttributeError, TypeError):
            return
        try:
            # Owner for the factory is the rule itself (owned MSA)
            # _create_with_guid uses owner.Add(); for OA we set directly after Create.
            from System import Guid as DotNetGuid
            sl = cache.ServiceLocator
            factory = sl.GetService(IMoStemMsaFactory)
            parsed_guid = DotNetGuid.Parse(msa_guid)
            new_msa = factory.Create(parsed_guid)
            # For OA slots the MSA is owned by the rule; set the slot attribute
            setattr(new_rule, slot_name, new_msa)
            # Wire POS
            tgt_pos = _resolve_pos(src_msa)
            if tgt_pos is not None:
                new_msa.PartOfSpeechRA = tgt_pos
        except Exception as e:
            raise RuntimeError(
                f"Failed to create owned IMoStemMsa for {slot_name} on "
                f"{class_name} guid={msa_guid}: {e!r}"
            ) from e

    # Left and Right MSAs are on both subclasses
    for slot in ("LeftMsaOA", "RightMsaOA"):
        src_msa = getattr(src_rule, slot, None)
        if src_msa is not None:
            try:
                _create_owned_msa(src_msa, new_rule, slot)
            except Exception:
                pass  # non-fatal; missing POS logged via apply_carrier_b residue

    # Subclass-specific slots
    if class_name == "MoEndoCompound":
        # OverridingMsaOA
        src_msa = getattr(src_rule, "OverridingMsaOA", None)
        if src_msa is not None:
            try:
                _create_owned_msa(src_msa, new_rule, "OverridingMsaOA")
            except Exception:
                pass
        # HeadLast (bool)
        try:
            new_rule.HeadLast = src_rule.HeadLast
        except (AttributeError, TypeError):
            pass
    elif class_name == "MoExoCompound":
        # ToMsaOA
        src_msa = getattr(src_rule, "ToMsaOA", None)
        if src_msa is not None:
            try:
                _create_owned_msa(src_msa, new_rule, "ToMsaOA")
            except Exception:
                pass

    # LinkerOA (optional, both subtypes) — carry if present
    try:
        linker = getattr(src_rule, "LinkerOA", None)
        if linker is not None:
            linker_guid = str(ICmObject(linker).Guid).lower()
            # LinkerOA is an owned IMoAffixForm; find in target by GUID
            tgt_linker = _find_target_obj_by_guid(
                _iter_all_allomorphs(target), linker_guid)
            if tgt_linker is not None:
                new_rule.LinkerOA = tgt_linker
    except (AttributeError, TypeError):
        pass


def _iter_all_pos(project):
    """Yield every IPartOfSpeech from the target project (flat walk of POS tree).

    Used for resolving PartOfSpeechRA by GUID during compound MSA wiring.
    """
    try:
        pos_list = project.Cache.LangProject.PartsOfSpeechOA.PossibilitiesOS
        for pos in _recurse_pos(pos_list):
            yield pos
    except (AttributeError, TypeError):
        try:
            for pos in project.GramCategories.GetAll():
                yield pos
        except (AttributeError, TypeError):
            pass


def _recurse_pos(coll):
    """Recursively yield IPartOfSpeech from a PossibilitiesOS collection."""
    try:
        items = list(coll)
    except (TypeError, AttributeError):
        return
    for pos in items:
        yield pos
        sub = getattr(pos, "SubPossibilitiesOS", None)
        if sub is not None:
            for child in _recurse_pos(sub):
                yield child


# ----- affixes (Phase 3c US1, memo step 14) --------------------------------
# Affix LexEntries partitioned by entry.LexemeFormOA.MorphTypeRA.IsAffixType.
# Owned-child closure: senses, MSAs, allomorphs, examples, pronunciations,
# etymologies, entry-refs. MSA.SlotsRC deferred to 17.1 sub-pass;
# LexEntryRef component lexemes deferred to post-pass A.

def affixes_enumerate_source(context, selection):
    raise NotImplementedError("Phase 3c T013")


def affixes_dependencies(piece):
    return ()


def affixes_required_writing_systems(piece):
    raise NotImplementedError("Phase 3c T013")


def affixes_plan_action(piece, context, ws_mapping):
    raise NotImplementedError("Phase 3c T015")


def affixes_execute_action(action, context, ws_mapping, tag):
    raise NotImplementedError("Phase 3c T019")


# ----- slots (Phase 3c US2, memo step 16) ----------------------------------
# IMoInflAffixSlot under IPartOfSpeech.AffixSlotsOC. Implementation T029.

def slots_enumerate_source(context, selection):
    raise NotImplementedError("Phase 3c T029")


def slots_dependencies(piece):
    return ()


def slots_required_writing_systems(piece):
    raise NotImplementedError("Phase 3c T029")


def slots_plan_action(piece, context, ws_mapping):
    raise NotImplementedError("Phase 3c T029")


def slots_execute_action(action, context, ws_mapping, tag):
    raise NotImplementedError("Phase 3c T029")


# ----- affix_templates (Phase 3c US2, memo step 17 + 17.1) -----------------
# IMoInflAffixTemplate under IPartOfSpeech.AffixTemplatesOS. The 17.1
# MSA-slot wiring sub-pass lives as a post-execute tail block on
# affix_templates_execute_action consuming plan.msa_slot_bindings.
# Implementation T030 (base) + T031 (17.1 tail).

def affix_templates_enumerate_source(context, selection):
    raise NotImplementedError("Phase 3c T030")


def affix_templates_dependencies(piece):
    return ()


def affix_templates_required_writing_systems(piece):
    raise NotImplementedError("Phase 3c T030")


def affix_templates_plan_action(piece, context, ws_mapping):
    raise NotImplementedError("Phase 3c T030")


def affix_templates_execute_action(action, context, ws_mapping, tag):
    raise NotImplementedError("Phase 3c T030")


# ----- stems (Phase 3c US3, memo step 18) ----------------------------------
# Stem LexEntries (not IsAffixType). Same owned-child closure as affixes.
# MoStemMsa.StratumRA resolves to Phase 3a Strata; sense.SemanticDomainsRC
# resolves to Phase 3b semantic domains. Post-pass A tail block on
# stems_execute_action consumes plan.lexentry_ref_bindings.
# Implementation T042-T045.

def stems_enumerate_source(context, selection):
    raise NotImplementedError("Phase 3c T042")


def stems_dependencies(piece):
    return ()


def stems_required_writing_systems(piece):
    raise NotImplementedError("Phase 3c T042")


def stems_plan_action(piece, context, ws_mapping):
    raise NotImplementedError("Phase 3c T042")


def stems_execute_action(action, context, ws_mapping, tag):
    raise NotImplementedError("Phase 3c T042")


# ============================================================================
# Category registry — engine dispatch
# ============================================================================

# ============================================================================
# Phase 3a — phonology block + strata (memo steps 2-5 + 4b + 5b)
# Per probe-results.md every Phase 3a factory exposes Create(Guid);
# implementations use that path with identity_remap as runtime safety net.
# ============================================================================

def _phonology_simple_enumerate(context, ops_attr, selection=None, category=None):
    """Shared enumerate_source helper for the simple phonology categories.

    When `selection`/`category` are given and the selection carries a
    per-item pick subset for that category (`leaf_item_picks`), the returned
    list is filtered to only those source objects whose GUID is in the subset.
    A None subset (key absent) ⇒ transfer ALL (unchanged behavior for every
    pre-Phase-010 caller). GUIDs on BOTH sides are normalized via
    `_guid_str_from` so a raw uppercase/braced `str(obj.Guid)` never causes a
    silent total miss (spec 010 GUID-normalization invariant).
    """
    source = context.source_handle
    if source is None or not hasattr(source, ops_attr):
        return ()
    try:
        items = list(getattr(source, ops_attr).GetAll())
    except (AttributeError, TypeError):
        return ()
    if selection is not None and category is not None:
        picks = selection.leaf_picks_for(category)
        if picks is not None:
            items = [it for it in items if _guid_str_from(it) in picks]
    return items


_GOLD_RESERVED_PHONOLOGY_CATEGORIES = frozenset({
    GrammarCategory.PHONOLOGICAL_FEATURES,
})
"""Phonology categories that are GOLD_RESERVED and participate in edit-detection.

Spec 017 scope: only PHONOLOGICAL_FEATURES among the 5 simple phonology
categories is GOLD_RESERVED. PHONEMES, NATURAL_CLASSES, PH_ENVIRONMENT, and
PHONOLOGICAL_RULES are MULTI_INSTANCE and are NOT in scope for the edit-copy
helper — their skip branch in _phonology_simple_plan is unchanged.
"""


def _phonology_simple_plan(piece, context, category, ops_attr, label):
    """Shared plan_action helper for the 5 simple phonology categories.

    For PHONOLOGICAL_FEATURES (the only GOLD_RESERVED member of this group),
    routes through _plan_gold_reserved_edit for edit-detection before falling
    back to the standard skip/add path.  The other 4 categories (PHONEMES,
    NATURAL_CLASSES, PH_ENVIRONMENT, PHONOLOGICAL_RULES) keep the existing
    ALREADY_PRESENT_BY_GUID skip unchanged (spec 017 scope guard).
    """
    if category in _GOLD_RESERVED_PHONOLOGY_CATEGORIES:
        def _target_iter(target):
            if target is not None and hasattr(target, ops_attr):
                try:
                    return getattr(target, ops_attr).GetAll()
                except (AttributeError, TypeError):
                    return ()
            return ()
        result = _plan_gold_reserved_edit(piece, category, context, _target_iter)
        if result is not None:
            return result
        src_guid = _guid_str_from(piece)
        return PlannedAction(
            category=category,
            source_guid=src_guid,
            intended_target_guid=src_guid,
            summary=f"{label} guid={src_guid[:8]}...",
        )

    src_guid = _guid_str_from(piece)
    target = context.target_handle
    if target is not None and hasattr(target, ops_attr):
        try:
            target_iter = getattr(target, ops_attr).GetAll()
        except (AttributeError, TypeError):
            target_iter = ()
        if _target_has_guid(target_iter, src_guid):
            return Skip(
                category=category,
                source_guid=src_guid,
                reason=SkipReason.ALREADY_PRESENT_BY_GUID,
                detail=f"{label} GUID {src_guid[:8]}... already present in target.",
            )
    return PlannedAction(
        category=category,
        source_guid=src_guid,
        intended_target_guid=src_guid,
        summary=f"{label} guid={src_guid[:8]}...",
    )


def _safe_add_to_owner(new_obj, owner_collection, factory_label, src_guid):
    """Add `new_obj` to `owner_collection`; raise RuntimeError on failure
    with an orphan-risk message so partial-allocation events are visible
    rather than silently leaking into the LCM cache.

    Mirrors the orphan-guard half of `_create_with_guid` so the four
    pre-Phase-3a categories that hand-roll their own Create+Add
    (gram_categories, inflection_features value loop,
    inflection_classes, stem_names) get the same protection.
    """
    try:
        owner_collection.Add(new_obj)
    except Exception as e:
        raise RuntimeError(
            f"Orphan risk: Create({src_guid}) succeeded for "
            f"{factory_label} but Add-to-owner failed: {e!r}. "
            f"Investigate target LCM state before retrying."
        ) from e


def _create_with_guid(factory_iface, owner_collection, guid_str, target):
    """Create-with-Guid helper.

    Calls factory.Create(Guid) — no fallback.  All Phase 3a factories
    (PhPhonemeFactory, PhNaturalClassFactory / PhNCSegmentsFactory,
    PhEnvironmentFactory, PhPhonologicalFeatureFactory, PhPhonRuleFactory,
    PhPhonemeSetFactory) expose Create(Guid); confirmed by MCP probes
    T004-T009 (2026-06-20).

    If Create(Guid) raises, re-raises as RuntimeError to fail loud rather
    than silently produce an object whose GUID does not match the source.

    If Create(Guid) succeeds but Add-to-owner-collection raises, re-raises
    as RuntimeError describing the orphan risk.  The created object is NOT
    stashed anywhere so the caller cannot accidentally reference it.

    Returns (new_obj, True).  The second element is always True; callers
    that previously used it to decide whether to record an identity_remap
    entry no longer need to — GUID preservation is now guaranteed or the
    call fails.
    """
    from System import Guid as DotNetGuid
    cache = getattr(target, "Cache")
    sl = cache.ServiceLocator
    factory = sl.GetService(factory_iface)
    factory_name = getattr(factory_iface, "__name__", repr(factory_iface))
    parsed_guid = DotNetGuid.Parse(guid_str)
    try:
        new_obj = factory.Create(parsed_guid)
    except Exception as e:
        raise RuntimeError(
            f"Factory {factory_name} does not support Create(Guid); "
            f"cannot align GUID {guid_str}"
        ) from e
    try:
        owner_collection.Add(new_obj)
    except Exception as e:
        raise RuntimeError(
            f"Orphan risk: Create({guid_str}) succeeded for "
            f"{factory_name} but Add-to-owner failed: {e!r}. "
            f"Investigate target LCM state before retrying."
        ) from e
    return new_obj, True


# ----- phonological_features (memo step 2) ---------------------------------

def phonological_features_enumerate_source(context, selection):
    return _phonology_simple_enumerate(
        context, "PhonFeatures", selection, GrammarCategory.PHONOLOGICAL_FEATURES)


def phonological_features_dependencies(piece):
    return ()


def phonological_features_required_writing_systems(piece):
    return ()


def phonological_features_plan_action(piece, context, ws_mapping):
    return _phonology_simple_plan(
        piece, context, GrammarCategory.PHONOLOGICAL_FEATURES,
        "PhonFeatures", "PhonologicalFeature",
    )


def phonological_features_execute_action(action, context, ws_mapping, tag):
    from SIL.LCModel import IFsClosedFeatureFactory
    if __package__:
        from .residue import apply_carrier_b
    else:
        from residue import apply_carrier_b  # type: ignore
    source = context.source_handle
    target = context.target_handle
    src_guid = action.source_guid
    src_feat = None
    for f in source.PhonFeatures.GetAll():
        if _guid_str_from(f) == src_guid:
            src_feat = f
            break
    if src_feat is None:
        return None
    cache = getattr(target, "Cache")
    owner = cache.LangProject.PhFeatureSystemOA.FeaturesOC
    new_feat, _preserved = _create_with_guid(
        IFsClosedFeatureFactory, owner, src_guid, target,
    )
    try:
        props = source.PhonFeatures.GetSyncableProperties(src_feat)
        target.PhonFeatures.ApplySyncableProperties(new_feat, props)
    except (AttributeError, TypeError):
        pass
    try:
        apply_carrier_b(new_feat, cache.DefaultAnalWs, tag, strict=False)
    except Exception:
        pass
    return new_feat


# ----- phonemes (memo step 3) ----------------------------------------------

def phonemes_enumerate_source(context, selection):
    return _phonology_simple_enumerate(
        context, "Phonemes", selection, GrammarCategory.PHONEMES)


def phonemes_dependencies(piece):
    return ()


def phonemes_required_writing_systems(piece):
    return ()


def phonemes_plan_action(piece, context, ws_mapping):
    return _phonology_simple_plan(
        piece, context, GrammarCategory.PHONEMES, "Phonemes", "Phoneme",
    )


def phonemes_execute_action(action, context, ws_mapping, tag):
    from SIL.LCModel import IPhPhonemeFactory
    if __package__:
        from .residue import apply_carrier_b
    else:
        from residue import apply_carrier_b  # type: ignore
    source = context.source_handle
    target = context.target_handle
    src_guid = action.source_guid
    src_phon = None
    for p in source.Phonemes.GetAll():
        if _guid_str_from(p) == src_guid:
            src_phon = p
            break
    if src_phon is None:
        return None
    cache = getattr(target, "Cache")
    phoneme_sets = cache.LangProject.PhonologicalDataOA.PhonemeSetsOS
    if len(phoneme_sets) == 0:
        # No phoneme set exists in target -- defer to runtime error.
        return None
    owner = phoneme_sets[0].PhonemesOC
    new_phon, _preserved = _create_with_guid(
        IPhPhonemeFactory, owner, src_guid, target,
    )
    try:
        props = source.Phonemes.GetSyncableProperties(src_phon)
        target.Phonemes.ApplySyncableProperties(new_phon, props)
    except (AttributeError, TypeError):
        pass
    try:
        apply_carrier_b(new_phon, cache.DefaultAnalWs, tag, strict=False)
    except Exception:
        pass
    return new_phon


# ----- natural_classes (memo step 4) ---------------------------------------

def natural_classes_dependencies(piece):
    """For IPhNCSegments, returns the GUIDs of referenced phonemes
    (SegmentsRC). For IPhNCFeatures, returns empty (FeaturesOA is owned)."""
    try:
        from SIL.LCModel import IPhNCSegments, ICmObject
    except ImportError:
        return ()
    try:
        nc_seg = IPhNCSegments(piece)
        return tuple(
            str(ICmObject(seg).Guid).lower() for seg in nc_seg.SegmentsRC
        )
    except (TypeError, AttributeError):
        return ()


def natural_classes_enumerate_source(context, selection):
    return _phonology_simple_enumerate(
        context, "NaturalClasses", selection, GrammarCategory.NATURAL_CLASSES)


def natural_classes_required_writing_systems(piece):
    return ()


def natural_classes_plan_action(piece, context, ws_mapping):
    return _phonology_simple_plan(
        piece, context, GrammarCategory.NATURAL_CLASSES,
        "NaturalClasses", "NaturalClass",
    )


def natural_classes_execute_action(action, context, ws_mapping, tag):
    from SIL.LCModel import (
        IPhNCSegmentsFactory, IPhNCFeaturesFactory, IPhNCSegments, ICmObject,
    )
    if __package__:
        from .residue import apply_carrier_b
    else:
        from residue import apply_carrier_b  # type: ignore
    source = context.source_handle
    target = context.target_handle
    src_guid = action.source_guid
    src_nc = None
    for nc in source.NaturalClasses.GetAll():
        if _guid_str_from(nc) == src_guid:
            src_nc = nc
            break
    if src_nc is None:
        return None
    cache = getattr(target, "Cache")
    owner = cache.LangProject.PhonologicalDataOA.NaturalClassesOS
    # Branch on subtype via ClassName.
    try:
        class_name = ICmObject(src_nc).ClassName
    except (AttributeError, TypeError):
        class_name = "PhNCSegments"
    factory_iface = IPhNCFeaturesFactory if class_name == "PhNCFeatures" else IPhNCSegmentsFactory
    new_nc, _preserved = _create_with_guid(
        factory_iface, owner, src_guid, target,
    )
    try:
        props = source.NaturalClasses.GetSyncableProperties(src_nc)
        target.NaturalClasses.ApplySyncableProperties(new_nc, props)
    except (AttributeError, TypeError):
        pass
    # PhNCSegments: wire SegmentsRC to target-side phonemes by GUID.
    # PhNCFeatures: FeaturesOA is OA (owned) and was handled by
    # ApplySyncableProperties above — no extra wiring needed.
    if class_name != "PhNCFeatures":
        try:
            src_segs = IPhNCSegments(src_nc).SegmentsRC
        except (AttributeError, TypeError):
            src_segs = src_nc.SegmentsRC
        # Build a GUID -> target phoneme lookup once.
        tgt_phoneme_by_guid = {
            _guid_str_from(p): p
            for p in target.Phonemes.GetAll()
        }
        try:
            nc_label = _guid_str_from(src_nc)
            for src_phon in src_segs:
                phon_guid = _guid_str_from(src_phon)
                tgt_phon = tgt_phoneme_by_guid.get(phon_guid)
                if tgt_phon is None:
                    raise RuntimeError(
                        f"natural_classes_execute_action: NC {nc_label} "
                        f"references source phoneme {phon_guid} which has no "
                        f"counterpart on the target.  Transfer the phoneme "
                        f"before transferring natural classes."
                    )
                try:
                    IPhNCSegments(new_nc).SegmentsRC.Add(tgt_phon)
                except (AttributeError, TypeError):
                    new_nc.SegmentsRC.Add(tgt_phon)
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(
                f"Orphan risk: NC {_guid_str_from(src_nc)} was added to target "
                f"but SegmentsRC wiring failed mid-loop: {e!r}. "
                f"Investigate target LCM state before retrying."
            ) from e
    try:
        apply_carrier_b(new_nc, cache.DefaultAnalWs, tag, strict=False)
    except Exception:
        pass
    return new_nc


# ----- ph_environment (memo step 4b -- project-wide, not allomorph-bundled) -

def ph_environment_enumerate_source(context, selection):
    return _phonology_simple_enumerate(
        context, "Environments", selection, GrammarCategory.PH_ENVIRONMENT)


def ph_environment_dependencies(piece):
    return ()


def ph_environment_required_writing_systems(piece):
    return ()


def ph_environment_plan_action(piece, context, ws_mapping):
    return _phonology_simple_plan(
        piece, context, GrammarCategory.PH_ENVIRONMENT,
        "Environments", "PhEnvironment",
    )


def ph_environment_execute_action(action, context, ws_mapping, tag):
    from SIL.LCModel import IPhEnvironmentFactory
    if __package__:
        from .residue import apply_carrier_b
    else:
        from residue import apply_carrier_b  # type: ignore
    source = context.source_handle
    target = context.target_handle
    src_guid = action.source_guid
    src_env = None
    for e in source.Environments.GetAll():
        if _guid_str_from(e) == src_guid:
            src_env = e
            break
    if src_env is None:
        return None
    cache = getattr(target, "Cache")
    owner = cache.LangProject.PhonologicalDataOA.EnvironmentsOS
    new_env, _preserved = _create_with_guid(
        IPhEnvironmentFactory, owner, src_guid, target,
    )
    try:
        props = source.Environments.GetSyncableProperties(src_env)
        target.Environments.ApplySyncableProperties(new_env, props)
    except (AttributeError, TypeError):
        pass
    try:
        apply_carrier_b(new_env, cache.DefaultAnalWs, tag, strict=False)
    except Exception:
        pass
    return new_env


# ----- strata (memo step 5b) -----------------------------------------------

def strata_enumerate_source(context, selection):
    return _phonology_simple_enumerate(
        context, "Strata", selection, GrammarCategory.STRATA)


def strata_dependencies(piece):
    return ()


def strata_required_writing_systems(piece):
    return ()


def strata_plan_action(piece, context, ws_mapping):
    return _phonology_simple_plan(
        piece, context, GrammarCategory.STRATA, "Strata", "Stratum",
    )


def strata_execute_action(action, context, ws_mapping, tag):
    from SIL.LCModel import IMoStratumFactory
    if __package__:
        from .residue import apply_carrier_b
    else:
        from residue import apply_carrier_b  # type: ignore
    source = context.source_handle
    target = context.target_handle
    src_guid = action.source_guid
    src_stratum = None
    for s in source.Strata.GetAll():
        if _guid_str_from(s) == src_guid:
            src_stratum = s
            break
    if src_stratum is None:
        return None
    cache = getattr(target, "Cache")
    owner = cache.LangProject.MorphologicalDataOA.StrataOS
    new_stratum, _preserved = _create_with_guid(
        IMoStratumFactory, owner, src_guid, target,
    )
    try:
        props = source.Strata.GetSyncableProperties(src_stratum)
        target.Strata.ApplySyncableProperties(new_stratum, props)
    except (AttributeError, TypeError):
        pass
    try:
        apply_carrier_b(new_stratum, cache.DefaultAnalWs, tag, strict=False)
    except Exception:
        pass
    return new_stratum


# ----- phonological_rules (memo step 5) -- WITH FR-304 dependency closure --

def phonological_rules_enumerate_source(context, selection):
    return _phonology_simple_enumerate(
        context, "PhonRules", selection, GrammarCategory.PHONOLOGICAL_RULES)


def phonological_rules_required_writing_systems(piece):
    return ()


def phonological_rules_dependencies(piece):
    """FR-304: walk rule's input/output segments + contexts + stratum, return
    every referenced GUID. The planner uses this to emit
    Skip(DEPENDENCY_UNRESOLVED) when references don't resolve."""
    try:
        from SIL.LCModel import IPhPhonologicalRule, ICmObject
    except ImportError:
        return ()
    refs = []
    try:
        rule = IPhPhonologicalRule(piece)
    except (TypeError, AttributeError):
        return ()
    # Stratum
    try:
        stratum = rule.StratumRA
        if stratum is not None:
            refs.append(str(ICmObject(stratum).Guid).lower())
    except (AttributeError, TypeError):
        pass
    # The rule's left/right children carry the segment + context refs.
    # We surface a best-effort walk; the planner's dependency check
    # consults target state + in-flight plan for resolution.
    try:
        for child_attr in ("InitialAttributesOA", "FinalAttributesOA",
                           "RightHandSidesOS", "LeftContextOA",
                           "RightContextOA"):
            child = getattr(rule, child_attr, None)
            if child is None:
                continue
            try:
                # Drill into the child's reference fields if present.
                for ref_attr in ("MembersRS", "SegmentsRC",
                                 "FeaturesOA", "InputOS", "OutputOS"):
                    val = getattr(child, ref_attr, None)
                    if val is None:
                        continue
                    # Iterable of refs?
                    try:
                        for v in val:
                            refs.append(str(ICmObject(v).Guid).lower())
                    except (TypeError, AttributeError):
                        # Single ref
                        try:
                            refs.append(str(ICmObject(val).Guid).lower())
                        except (TypeError, AttributeError):
                            pass
            except (AttributeError, TypeError):
                pass
    except (AttributeError, TypeError):
        pass
    return tuple(refs)


def phonological_rules_plan_action(piece, context, ws_mapping):
    """Standard plan_action plus FR-304 dependency check.

    Note: the dependency-closure resolution against the in-flight plan
    is the PLANNER's responsibility (not this callback's).  This
    callback emits PlannedAction or ALREADY_PRESENT_BY_GUID Skip.
    The planner threading dependencies() through the closure walker
    handles DEPENDENCY_UNRESOLVED.
    """
    return _phonology_simple_plan(
        piece, context, GrammarCategory.PHONOLOGICAL_RULES,
        "PhonRules", "PhonologicalRule",
    )


def phonological_rules_execute_action(action, context, ws_mapping, tag):
    """Create rule + apply syncable properties.

    Because PhonologicalRuleOperations is heterogeneous across rule
    subtypes, we use the most-permissive entry: probe the source rule's
    ClassName to pick the right factory, fall back to the segment-rule
    factory."""
    from SIL.LCModel import (
        IPhRegularRuleFactory, IPhSegmentRuleFactory, IPhMetathesisRuleFactory,
        ICmObject,
    )
    if __package__:
        from .residue import apply_carrier_b
    else:
        from residue import apply_carrier_b  # type: ignore
    source = context.source_handle
    target = context.target_handle
    src_guid = action.source_guid
    src_rule = None
    for r in source.PhonRules.GetAll():
        if _guid_str_from(r) == src_guid:
            src_rule = r
            break
    if src_rule is None:
        return None
    try:
        class_name = ICmObject(src_rule).ClassName
    except (AttributeError, TypeError):
        class_name = "PhRegularRule"
    factory_iface = {
        "PhRegularRule": IPhRegularRuleFactory,
        "PhSegmentRule": IPhSegmentRuleFactory,
        "PhMetathesisRule": IPhMetathesisRuleFactory,
    }.get(class_name, IPhRegularRuleFactory)
    cache = getattr(target, "Cache")
    owner = cache.LangProject.PhonologicalDataOA.PhonRulesOS
    new_rule, _preserved = _create_with_guid(
        factory_iface, owner, src_guid, target,
    )
    try:
        props = source.PhonRules.GetSyncableProperties(src_rule)
        target.PhonRules.ApplySyncableProperties(new_rule, props)
    except (AttributeError, TypeError):
        pass
    # Wire StratumRA if present.
    try:
        src_stratum = src_rule.StratumRA
        if src_stratum is not None:
            src_stratum_guid = str(ICmObject(src_stratum).Guid).lower()
            for tgt_stratum in target.Strata.GetAll():
                if str(ICmObject(tgt_stratum).Guid).lower() == src_stratum_guid:
                    new_rule.StratumRA = tgt_stratum
                    break
    except (AttributeError, TypeError):
        pass
    try:
        apply_carrier_b(new_rule, cache.DefaultAnalWs, tag, strict=False)
    except Exception:
        pass
    return new_rule


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
    GrammarCategory.ADHOC_COMPOUND_RULES: {
        "enumerate_source": adhoc_compound_rules_enumerate_source,
        "dependencies": adhoc_compound_rules_dependencies,
        "required_writing_systems": adhoc_compound_rules_required_writing_systems,
        "plan_action": adhoc_compound_rules_plan_action,
        "execute_action": adhoc_compound_rules_execute_action,
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
    # Phase 3b -- memo step 13b. Other 8 Phase 3b categories already
    # registered above (gram_categories, inflection_features,
    # custom_fields, inflection_classes, stem_names, exception_features,
    # variant_types, complex_form_types).
    GrammarCategory.SEMANTIC_DOMAINS: {
        "enumerate_source": semantic_domains_enumerate_source,
        "dependencies": semantic_domains_dependencies,
        "required_writing_systems": semantic_domains_required_writing_systems,
        "plan_action": semantic_domains_plan_action,
        "execute_action": semantic_domains_execute_action,
    },
    # Phase 3c (memo steps 14-18) — stubs registered for leaf-dispatch
    # discovery; real implementations land in Phase 3c US1-US4.
    # Migration from inline verb-vertical paths is gated on per-US ship.
    GrammarCategory.AFFIXES: {
        "enumerate_source": affixes_enumerate_source,
        "dependencies": affixes_dependencies,
        "required_writing_systems": affixes_required_writing_systems,
        "plan_action": affixes_plan_action,
        "execute_action": affixes_execute_action,
    },
    GrammarCategory.SLOTS: {
        "enumerate_source": slots_enumerate_source,
        "dependencies": slots_dependencies,
        "required_writing_systems": slots_required_writing_systems,
        "plan_action": slots_plan_action,
        "execute_action": slots_execute_action,
    },
    GrammarCategory.AFFIX_TEMPLATES: {
        "enumerate_source": affix_templates_enumerate_source,
        "dependencies": affix_templates_dependencies,
        "required_writing_systems": affix_templates_required_writing_systems,
        "plan_action": affix_templates_plan_action,
        "execute_action": affix_templates_execute_action,
    },
    GrammarCategory.STEMS: {
        "enumerate_source": stems_enumerate_source,
        "dependencies": stems_dependencies,
        "required_writing_systems": stems_required_writing_systems,
        "plan_action": stems_plan_action,
        "execute_action": stems_execute_action,
    },
}


def for_category(category: GrammarCategory) -> dict:
    """Lookup the function bundle for a leaf category. Raises KeyError if
    the category isn't a leaf (use `categories_affixes`, `categories_templates`,
    or `categories_msas` for the heavy ones)."""
    return LEAF_CATEGORIES[category]

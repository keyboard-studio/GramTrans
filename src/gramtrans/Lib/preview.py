"""Preview-mode plan builder (constitution v5.0.0 Principle III).

`build_run_plan(context, selection, source, target)` walks the source closure
for the user's Selection and returns an immutable RunPlan. The walk is
READ-ONLY on both source and target — MUST NOT mutate anything (the unit test
`tests/unit/test_preview_no_writes.py` will enforce this with a fake LCM that
records any write attempt).

Phase 0 MVP scope (T-Spike): only the Verb vertical (POS → Template → Slots,
with Layer 3 MSA / Allomorph / Environment as the next slice). Subsequent
tasks (T039 leaf categories, T049 affixes, T051 templates, T051b MSAs) extend
this builder with the full FR-004 category set.
"""
from __future__ import annotations

import logging
from typing import Iterable, List, Optional, Tuple

_log = logging.getLogger(__name__)

if __package__:
    from .models import (
        CategoryScope,
        ExcludedLossy,
        GrammarCategory,
        PlannedAction,
        PlannedOverwrite,
        RunContext,
        RunPlan,
        Selection,
        Skip,
        SkipReason,
        WSMapping,
    )
else:
    from models import (
        CategoryScope,
        ExcludedLossy,
        GrammarCategory,
        PlannedAction,
        PlannedOverwrite,
        RunContext,
        RunPlan,
        Selection,
        Skip,
        SkipReason,
        WSMapping,
    )


# ============================================================================
# Public API
# ============================================================================

def build_run_plan(
    context: RunContext,
    selection: Selection,
    ws_mapping: WSMapping,
    source,
    target,
) -> RunPlan:
    """Compute a complete RunPlan for the current selection.

    Source and target are flexicon FLExProject handles (or duck-typed
    equivalents for unit tests). This function:

    1. Walks the selection's closure across the source.
    2. For each source piece, decides PlannedAction or Skip (FR-021, FR-022).
    3. Returns an immutable RunPlan that Move Mode (`Lib/transfer.py.execute`)
       consumes verbatim.

    MUST NOT mutate target. (SC-006)
    """
    actions: List[PlannedAction] = []
    skips: List[Skip] = []
    overwrites: List[PlannedOverwrite] = []
    excluded_lossy: List[ExcludedLossy] = []
    identity_remap: dict = {}

    # Walk every selected POS (or all top-level POSes when categories[POS]
    # is True and pos_picks is empty). For each POS, walk its closure:
    # POS → Template → Slots → LexEntries(MSA-points-at-POS) → Senses → MSAs
    # → Allomorphs → PhEnvironments.
    _pos_count = 0
    for src_pos in _select_source_poses(source, selection):
        _pos_count += 1
        _plan_pos_closure(source, target, src_pos, selection, actions, skips, overwrites)
        _plan_layer3_for_pos(source, target, src_pos, selection, actions, skips, overwrites, excluded_lossy, identity_remap=identity_remap)
    _log.debug(
        "build_run_plan: verb-vertical closure over %d source POS(es); "
        "actions so far=%d", _pos_count, len(actions),
    )

    # Phase 3c binding accumulators — written by AFFIXES/STEMS plan_action;
    # consumed by AFFIX_TEMPLATES (17.1 sub-pass, US2) and STEMS (post-pass A, US3).
    # Thread via context so plan_action callbacks can access without signature change.
    # RunContext is frozen=True; use object.__setattr__ to attach dynamic attrs.
    _msa_slot_bindings: dict = {}
    _lexentry_ref_bindings: dict = {}
    object.__setattr__(context, '_msa_slot_bindings', _msa_slot_bindings)
    object.__setattr__(context, '_lexentry_ref_bindings', _lexentry_ref_bindings)
    # Phase 3c FR-338: thread the live Selection so entry-shaped leaf
    # plan_actions (AFFIXES/STEMS) can honor enable_overwrite by emitting a
    # PlannedOverwrite instead of a Skip when the target already has the GUID.
    object.__setattr__(context, '_selection', selection)

    # Phase 3c Selection UI: thread excluded_lossy collector so leaf-dispatch
    # plan_action callbacks can add EXCLUDED-LOSSY warnings.
    object.__setattr__(context, '_excluded_lossy', excluded_lossy)

    # Phase 3a leaf-category dispatch: iterate every Phase 3a category
    # that's enabled in the selection.  Each category's registered
    # callbacks live in Lib/categories.py.  Errors-as-skips: if an
    # enumerate_source raises, the category is treated as empty (per
    # FR-308 skip-empty semantics).
    _LEAF_DISPATCH_CATEGORIES = (
        # Phase 3a (memo steps 2-5 + 5b)
        GrammarCategory.PHONOLOGICAL_FEATURES,
        GrammarCategory.PHONEMES,
        GrammarCategory.NATURAL_CLASSES,
        GrammarCategory.PH_ENVIRONMENT,
        GrammarCategory.PHONOLOGICAL_RULES,
        GrammarCategory.STRATA,
        # Phase 3b (memo steps 6-13b)
        GrammarCategory.GRAM_CATEGORIES,
        GrammarCategory.INFLECTION_FEATURES,
        GrammarCategory.CUSTOM_FIELDS,
        GrammarCategory.INFLECTION_CLASSES,
        GrammarCategory.STEM_NAMES,
        GrammarCategory.EXCEPTION_FEATURES,
        GrammarCategory.VARIANT_TYPES,
        GrammarCategory.COMPLEX_FORM_TYPES,
        GrammarCategory.SEMANTIC_DOMAINS,
        # Phase 3c (memo steps 14-18) — order matters: 17.1 sub-pass on
        # AFFIX_TEMPLATES executor tail requires AFFIXES and SLOTS to have
        # planned first; post-pass A on STEMS executor tail requires
        # AFFIXES + STEMS planning to be complete.
        GrammarCategory.AFFIXES,
        GrammarCategory.ADHOC_COMPOUND_RULES,
        GrammarCategory.SLOTS,
        GrammarCategory.AFFIX_TEMPLATES,
        GrammarCategory.STEMS,
    )
    if __package__:
        from .categories import for_category
    else:
        from categories import for_category  # type: ignore
    for cat in _LEAF_DISPATCH_CATEGORIES:
        if not selection.is_on(cat):
            continue
        try:
            bundle = for_category(cat)
        except KeyError:
            continue
        try:
            pieces = list(bundle["enumerate_source"](context, selection))
        except Exception:
            pieces = []
        # Persist/over-transfer diagnostics: how many items this category
        # enumerated and how many actions it contributes to the plan.
        _cat_actions_before = len(actions)
        for piece in pieces:
            try:
                result = bundle["plan_action"](piece, context, ws_mapping)
            except Exception as exc:  # planner-level failures become skips
                from .models import SkipReason as _SR  # noqa
                actions.append(PlannedAction(
                    category=cat,
                    source_guid=str(getattr(piece, "Guid", "?")),
                    intended_target_guid="",
                    summary=f"plan_action raised {type(exc).__name__}: {exc}",
                ))
                continue
            if isinstance(result, Skip):
                skips.append(result)
            elif isinstance(result, PlannedOverwrite):
                overwrites.append(result)
            elif isinstance(result, PlannedAction):
                actions.append(result)
        if _log.isEnabledFor(logging.DEBUG):
            _log.debug(
                "build_run_plan leaf category=%s  enumerated=%d actions+=%d",
                cat.value, len(pieces), len(actions) - _cat_actions_before,
            )

    # T023: rules missing-reference detection (018-rules-page US4/FR-014/FR-015).
    # Runs AFTER the leaf dispatch so 'in-flight' actions are fully enumerated.
    # Routes into the shared excluded_lossy list -> single Move gate (T024).
    _rules_missing_ref_warnings(
        context, selection, actions, excluded_lossy, source, target
    )

    _log.debug(
        "build_run_plan: done  actions=%d skips=%d overwrites=%d excluded_lossy=%d",
        len(actions), len(skips), len(overwrites), len(excluded_lossy),
    )
    return RunPlan(
        context=context,
        selection=selection,
        ws_mapping=ws_mapping,
        actions=tuple(actions),
        skips=tuple(skips),
        identity_remap=identity_remap,
        overwrites=tuple(overwrites),
        msa_slot_bindings=_msa_slot_bindings,
        lexentry_ref_bindings=_lexentry_ref_bindings,
        excluded_lossy=tuple(excluded_lossy),
    )


# ============================================================================
# Rules missing-reference detection (018-rules-page T023, US4, FR-014/FR-015)
# ============================================================================

def _rules_missing_ref_warnings(
    context: "RunContext",
    selection: "Selection",
    planned_actions: List["PlannedAction"],
    excluded_lossy: List["ExcludedLossy"],
    source,
    target,
) -> None:
    """Emit ExcludedLossy warnings for kept rules with unresolvable member refs.

    For each rule that was planned (PlannedAction for ADHOC_COMPOUND_RULES),
    inspect its dependency GUIDs (via adhoc_compound_rules_dependencies).
    If a dep GUID is:
      - NOT in the set of in-flight action GUIDs (being transferred), AND
      - NOT already present in the target (by GUID),
    emit one entry-centric ExcludedLossy warning for that (rule, dep) pair
    (FR-014 one-per-ref, FR-015 routed to shared Move gate).

    ``target is None`` => treat target as lacking every ref (safe default,
    no crash — spec Assumptions / data-model.md "No target bound" invariant).

    All GUID comparisons use _guid_str_from via the categories helper so the
    normalization invariant (lowercase, braces-stripped) is upheld on both
    sides.
    """
    if __package__:
        from .categories import adhoc_compound_rules_dependencies, _rules_enumerate_all, _guid_str_from
    else:
        from categories import adhoc_compound_rules_dependencies, _rules_enumerate_all, _guid_str_from  # type: ignore

    # Build the set of GUIDs that are 'in-flight' (planned for transfer in this run)
    in_flight_guids: set = {
        a.source_guid
        for a in planned_actions
        if isinstance(a, PlannedAction)
    }

    # Build the set of GUIDs already present in the target (all rule-dep categories:
    # allomorphs, MSAs, POS objects).  We use a broad approach — collect GUIDs of
    # every reachable object in the target that might be a dep of a rule.
    target_guids: set = set()
    if target is not None:
        try:
            # Allomorphs (IMoForm)
            for entry in target.Cache.LangProject.LexDbOA.Entries:
                try:
                    for allo in entry.AlternateFormsOS:
                        target_guids.add(_guid_str_from(allo))
                except (AttributeError, TypeError):
                    pass
                try:
                    lf = entry.LexemeFormOA
                    if lf is not None:
                        target_guids.add(_guid_str_from(lf))
                except (AttributeError, TypeError):
                    pass
                # MSAs (IMoMorphSynAnalysis)
                try:
                    for msa in entry.MorphoSyntaxAnalysesOC:
                        target_guids.add(_guid_str_from(msa))
                except (AttributeError, TypeError):
                    pass
        except (AttributeError, TypeError):
            pass
        # POS objects (IPartOfSpeech — compound rule deps)
        try:
            def _iter_pos(pos_list):
                for pos in pos_list:
                    target_guids.add(_guid_str_from(pos))
                    try:
                        for child in pos.SubPossibilitiesOS:
                            _iter_pos([child])
                    except (AttributeError, TypeError):
                        pass
            poses = target.Cache.LangProject.PartsOfSpeechOA.PossibilitiesOS
            _iter_pos(list(poses))
        except (AttributeError, TypeError):
            pass

    # Identify which rules are planned (in the ADHOC_COMPOUND_RULES planned actions)
    planned_rule_guids: set = {
        a.source_guid
        for a in planned_actions
        if isinstance(a, PlannedAction)
        and getattr(a, "category", None) == GrammarCategory.ADHOC_COMPOUND_RULES
    }

    if not planned_rule_guids:
        return

    # Build a guid -> label map for kept rules using source enumeration
    rule_labels: dict = {}
    if source is not None:
        try:
            for obj in _rules_enumerate_all(source):
                g = _guid_str_from(obj)
                if g in planned_rule_guids:
                    try:
                        name = obj.Name
                        text = getattr(
                            getattr(name, "BestAnalysisAlternative", None),
                            "Text", None
                        ) if name is not None else None
                        lbl = text if text and text not in ("***", "") else g[:8]
                    except (AttributeError, TypeError):
                        lbl = g[:8]
                    rule_labels[g] = lbl
        except Exception:  # noqa: BLE001
            pass

    # Determine ref kind from dep GUID context.
    # We cannot cheaply infer ref kind from a plain GUID, so we iterate the
    # source rule objects and use the subclass-specific fields.
    def _dep_ref_kind(rule_obj, dep_guid: str) -> str:
        """Guess stranded_ref_kind from the rule subclass fields."""
        try:
            from SIL.LCModel import ICmObject
            class_name = ICmObject(getattr(rule_obj, "concrete", rule_obj)).ClassName
        except Exception:
            class_name = getattr(rule_obj, "class_name",
                                 getattr(rule_obj, "ClassName", "")) or ""
        if class_name == "MoAlloAdhocProhib":
            return "allomorph"
        if class_name == "MoMorphAdhocProhib":
            return "morpheme"
        if class_name in ("MoEndoCompound", "MoExoCompound"):
            return "part-of-speech"
        return "member"

    def _dep_label(dep_guid: str) -> str:
        return dep_guid[:8]

    # Emit warnings: one per (kept rule, stranded dep) pair
    warned: set = set()
    if source is not None:
        try:
            for rule_obj in _rules_enumerate_all(source):
                rule_guid = _guid_str_from(rule_obj)
                if rule_guid not in planned_rule_guids:
                    continue
                dep_guids = adhoc_compound_rules_dependencies(rule_obj)
                for dep_guid in dep_guids:
                    if not dep_guid:
                        continue
                    # Dep is resolved if in-flight or already in target
                    if dep_guid in in_flight_guids:
                        continue
                    if dep_guid in target_guids:
                        continue
                    key = (rule_guid, dep_guid)
                    if key in warned:
                        continue
                    warned.add(key)
                    rule_lbl = rule_labels.get(rule_guid, rule_guid[:8])
                    ref_kind = _dep_ref_kind(rule_obj, dep_guid)
                    excluded_lossy.append(ExcludedLossy(
                        category=GrammarCategory.ADHOC_COMPOUND_RULES,
                        entry_guid=rule_guid,
                        entry_label=rule_lbl,
                        dep_category=GrammarCategory.ADHOC_COMPOUND_RULES,
                        dep_guid=dep_guid,
                        dep_label=_dep_label(dep_guid),
                        message=(
                            f"Rule '{rule_lbl}' references {ref_kind} "
                            f"'{_dep_label(dep_guid)}' which is absent from the target "
                            f"and not being transferred."
                        ),
                    ))
        except Exception:  # noqa: BLE001
            pass


# ============================================================================
# Verb-vertical plan walk (mirrors STATUS.md Layer 1+2)
# ============================================================================

def _emit_present_outcome(
    category: GrammarCategory,
    src_guid: str,
    target_guid: str,
    summary: str,
    skip_detail: str,
    selection: Selection,
    skips: List[Skip],
    overwrites: Optional[List[PlannedOverwrite]],
    *,
    pulled_in_by: tuple = (),
    match_via: str = "guid",
    owner_guid: str = "",
) -> None:
    """Phase 0/1 dispatcher for "target already has source GUID":

    - Phase 0 (`selection.enable_overwrite=False`, default): emit
      `Skip(ALREADY_PRESENT_BY_GUID)` per FR-009.
    - Phase 1 (`selection.enable_overwrite=True`, per FR-108): emit
      `PlannedOverwrite` instead so the executor updates the existing
      target object's syncable properties from source.
    """
    if selection.enable_overwrite and overwrites is not None:
        overwrites.append(PlannedOverwrite(
            category=category,
            source_guid=src_guid,
            target_guid=target_guid,
            summary=summary,
            match_via=match_via,
            pulled_in_by=pulled_in_by,
            owner_guid=owner_guid,
        ))
    else:
        skips.append(Skip(
            category=category,
            source_guid=src_guid,
            reason=SkipReason.ALREADY_PRESENT_BY_GUID,
            detail=skip_detail,
        ))


def _select_source_poses(source, selection: Selection) -> List:
    """Return the list of source POS objects whose closure should be walked.

    We walk a POS's closure whenever ANY category in the POS-or-downstream
    closure is selected (POS itself, Templates, Slots, Entry, Sense, MSA,
    Allomorph, PhEnvironment). Closure-off mode produces BARE_BONES skips
    for non-selected layers; that's handled inside the walker.

    POS picking:
    - If `selection.pos_picks` is non-empty, walk only those POSes (by GUID).
    - Otherwise walk every top-level POS in source.

    Returns [] when no category in the POS closure is selected.
    """
    pos_closure_cats = (
        GrammarCategory.POS,
        GrammarCategory.AFFIX_TEMPLATES,
        GrammarCategory.SLOTS,
        GrammarCategory.ENTRY,
        GrammarCategory.SENSE,
        GrammarCategory.MSA,
        GrammarCategory.ALLOMORPH,
        # Phase 3a: PH_ENVIRONMENT is now a project-wide LEAF category
        # (memo step 4b). It no longer triggers the verb-vertical walker.
        # Allomorph closure still resolves environments by GUID against
        # the same plan, so the relocation is invisible to existing
        # Phase 0/1/2 callers selecting ALLOMORPH.
    )
    if not any(selection.is_on(c) for c in pos_closure_cats):
        return []
    all_poses = list(source.POS.GetAll(recursive=True))
    if not selection.pos_picks:
        return [_unwrap(p) for p in all_poses]
    picks = set(g.lower() for g in selection.pos_picks)
    result = []
    for p in all_poses:
        concrete = _unwrap(p)
        if _guid_str(concrete) in picks:
            result.append(concrete)
    return result


def _plan_pos_closure(
    source,
    target,
    src_pos,
    selection: Selection,
    actions: List[PlannedAction],
    skips: List[Skip],
    overwrites: List[PlannedOverwrite],
) -> None:
    """POS → Template → Slot walk for a single source POS. Mirrors the
    pre-multi-POS `_plan_verb_vertical` but parameterized on the POS."""
    _plan_verb_vertical_inner(
        source, target, src_pos, selection, actions, skips, overwrites,
    )


def _plan_layer3_for_pos(
    source,
    target,
    src_pos,
    selection: Selection,
    actions: List[PlannedAction],
    skips: List[Skip],
    overwrites: List[PlannedOverwrite],
    excluded_lossy: Optional[List[ExcludedLossy]] = None,
    identity_remap: dict = None,
) -> None:
    """Layer 3 (LexEntry / Sense / MSA / Allomorph / PhEnvironment) walk for
    affix entries whose IMoInflAffMsa.PartOfSpeechRA points at `src_pos`."""
    _plan_layer3_verb_affixes_inner(
        source, target, src_pos, selection, actions, skips, overwrites,
        excluded_lossy=excluded_lossy,
        identity_remap=identity_remap if identity_remap is not None else {},
    )


def _plan_verb_vertical_inner(
    source,
    target,
    src_pos,
    selection: Selection,
    actions: List[PlannedAction],
    skips: List[Skip],
    overwrites: Optional[List[PlannedOverwrite]] = None,
) -> None:
    """POS+Template+Slot closure for a single source POS.

    Each Add/Skip decision uses GUID-presence in the target; FR-009 still
    permits duplicates but the convention validated in STATUS.md is "if
    target already has the source GUID, skip with ALREADY_PRESENT_BY_GUID
    (informational)".

    Closure semantics (FR-013, T076):
      * `selection.include_closure=True` (default): pull every reachable
        piece in the verb vertical. Non-seed pieces carry `pulled_in_by`
        pointing at their owner (POS for templates, template for slots).
      * `selection.include_closure=False`: only emit actions for pieces in
        categories the user explicitly toggled on. Pieces whose dependencies
        (owner POS for templates, slots referenced by templates) are NOT
        also user-selected become `Skip(reason=BARE_BONES_MISSING_CLOSURE)`.
    """
    # Caller already validated that `src_pos` belongs to source; if it's None
    # (defensive), bail out.
    if src_pos is None:
        return

    # Per-scope closure for POS / AFFIX_TEMPLATES / SLOTS.
    # Scope AS_NEEDED or ALL -> closure on for that category; NONE -> off.
    pos_scope = selection.scope_for(GrammarCategory.POS)
    tpl_scope = selection.scope_for(GrammarCategory.AFFIX_TEMPLATES)
    slots_scope = selection.scope_for(GrammarCategory.SLOTS)
    # Legacy closure_on: True when ANY of the three is AS_NEEDED or ALL.
    # Used as a fallback for the inter-layer "pull in" logic below.
    closure_on = any(
        s in (CategoryScope.AS_NEEDED, CategoryScope.ALL)
        for s in (pos_scope, tpl_scope, slots_scope)
    )
    pos_on = selection.is_on(GrammarCategory.POS)
    tpl_on = selection.is_on(GrammarCategory.AFFIX_TEMPLATES)
    slots_on = selection.is_on(GrammarCategory.SLOTS)

    src_verb = src_pos  # historical local name preserved; "verb" → "POS" here
    src_verb_guid = _guid_str(src_verb)

    # ----- POS layer -----
    # POS has no upstream dependency in our scope; if the user selected it
    # OR closure is on and something downstream wants it, plan it.
    pos_wanted = pos_on or (closure_on and (tpl_on or slots_on))
    if pos_wanted:
        if _target_has_pos_guid(target, src_verb_guid):
            _emit_present_outcome(
                GrammarCategory.POS,
                src_guid=src_verb_guid,
                target_guid=src_verb_guid,
                summary=f"POS already present (guid {src_verb_guid[:8]}…)",
                skip_detail="POS 'Verb' already present in target by GUID",
                selection=selection,
                skips=skips,
                overwrites=overwrites,
            )
        else:
            actions.append(PlannedAction(
                category=GrammarCategory.POS,
                source_guid=src_verb_guid,
                intended_target_guid=src_verb_guid,
                summary=f"POS 'Verb' (guid {src_verb_guid[:8]}…)",
                pulled_in_by=() if pos_on else (src_verb_guid,),  # marker: pulled in
            ))

    # ----- Templates + slots -----
    for src_template_wrap in source.MorphRules.GetAllAffixTemplatesForPOS(src_verb):
        src_template = src_template_wrap.concrete
        tpl_guid = _guid_str(src_template)

        slots_present = any(
            True
            for slot_iter in (
                src_template_wrap.prefix_slots,
                src_template_wrap.suffix_slots,
                src_template_wrap.proclitic_slots,
                src_template_wrap.enclitic_slots,
            )
            for _ in slot_iter
        )

        if tpl_on:
            # User explicitly selected templates. Check that dependencies
            # (owner POS + slots) are satisfied under closure-off mode.
            if not closure_on:
                missing_deps = []
                if not pos_on:
                    missing_deps.append("owner POS")
                if slots_present and not slots_on:
                    missing_deps.append("slots")
                if missing_deps:
                    skips.append(Skip(
                        category=GrammarCategory.AFFIX_TEMPLATES,
                        source_guid=tpl_guid,
                        reason=SkipReason.BARE_BONES_MISSING_CLOSURE,
                        detail=(
                            f"template skipped: closure off and unselected dep(s): "
                            + ", ".join(missing_deps)
                        ),
                    ))
                    # Skip the slot layer for this template too — there's
                    # nothing to attach them to.
                    continue
            _emit_template(target, src_verb_guid, tpl_guid, tpl_on, actions, skips, selection, overwrites)
        elif closure_on:
            # Pulled in via closure from POS or slots being on.
            if pos_on or slots_on:
                _emit_template(target, src_verb_guid, tpl_guid, False, actions, skips, selection, overwrites)
            else:
                continue
        else:
            # closure off + templates not selected → template doesn't appear
            continue

        # ----- Slot layer (only reached if template was planned, not skipped) -----
        for kind_label, slot_iter in (
            ("prefix", src_template_wrap.prefix_slots),
            ("suffix", src_template_wrap.suffix_slots),
            ("proclitic", src_template_wrap.proclitic_slots),
            ("enclitic", src_template_wrap.enclitic_slots),
        ):
            for slot in slot_iter:
                if slots_on:
                    pass  # plan
                elif closure_on:
                    pass  # pulled in
                else:
                    continue  # closure off + slots not selected → omit silently

                slot_guid = _guid_str(slot)
                slot_name = _slot_name(slot)
                if _target_has_slot_guid(target, src_verb_guid, slot_guid):
                    _emit_present_outcome(
                        GrammarCategory.SLOTS,
                        src_guid=slot_guid,
                        target_guid=slot_guid,
                        summary=f"Slot {slot_name!r} ({kind_label}) already present",
                        skip_detail=f"Slot {slot_name!r} ({kind_label}) already present by GUID",
                        selection=selection,
                        skips=skips,
                        overwrites=overwrites,
                        pulled_in_by=() if slots_on else (tpl_guid,),
                        owner_guid=src_verb_guid,  # POS owner; slots live under POS.AffixSlotsOC
                    )
                else:
                    actions.append(PlannedAction(
                        category=GrammarCategory.SLOTS,
                        source_guid=slot_guid,
                        intended_target_guid=slot_guid,
                        summary=f"Slot {slot_name!r} ({kind_label}) in Verb template",
                        pulled_in_by=() if slots_on else (tpl_guid,),
                    ))


def _plan_layer3_verb_affixes_inner(
    source,
    target,
    src_pos,
    selection: Selection,
    actions: List[PlannedAction],
    skips: List[Skip],
    overwrites: Optional[List[PlannedOverwrite]] = None,
    excluded_lossy: Optional[List[ExcludedLossy]] = None,
    identity_remap: dict = None,
) -> None:
    """Walk Layer 3 for a single source POS: every source LexEntry whose
    Sense's MSA is an IMoInflAffMsa pointing at this POS. Each yields
    ENTRY+SENSE+MSA actions; each Allomorph on the entry yields an
    ALLOMORPH action; each PhEnvironment referenced by an allomorph
    (deduplicated) yields a PH_ENVIRONMENT action.

    Layer 3 is gated by category toggles:
    - ENTRY / SENSE / MSA / ALLOMORPH / PH_ENVIRONMENT must each be selected
      (or pulled in via closure when include_closure=True).
    Layer 3 is also gated by Layer 1+2 being present in the plan or target
    (POS + template + slots) — without them the MSA cross-references can't
    resolve.
    """
    src_verb = src_pos  # name retained for in-function brevity
    if src_verb is None:
        return

    if identity_remap is None:
        identity_remap = {}

    # Per-scope closure for Layer 3 categories.
    # NONE -> closure off for that category; AS_NEEDED or ALL -> closure on.
    def _scope_on(cat: GrammarCategory) -> bool:
        return selection.scope_for(cat) in (CategoryScope.AS_NEEDED, CategoryScope.ALL)

    closure_on = any(
        _scope_on(c) for c in (
            GrammarCategory.ENTRY,
            GrammarCategory.SENSE,
            GrammarCategory.MSA,
            GrammarCategory.ALLOMORPH,
            GrammarCategory.PH_ENVIRONMENT,
        )
    )
    any_l3_user = any(
        selection.is_on(c) for c in (
            GrammarCategory.ENTRY,
            GrammarCategory.SENSE,
            GrammarCategory.MSA,
            GrammarCategory.ALLOMORPH,
            GrammarCategory.PH_ENVIRONMENT,
        )
    )
    if not (any_l3_user or closure_on):
        return  # Layer 3 not selected and closure off → skip
    # Defensive: fake-source unit tests don't carry LexEntry/Allomorphs
    # accessors. Layer 3 silently skips when the source can't be walked.
    if not (hasattr(source, "LexEntry") and hasattr(source, "Allomorphs")):
        return

    src_verb_guid = _guid_str(src_verb)

    # Cache the source slot GUIDs (they should appear in target after Layer 2;
    # MSA.SlotsRC re-references them by GUID).
    src_slot_guids = set()
    for _wrap in source.MorphRules.GetAllAffixTemplatesForPOS(src_verb):
        for slot_iter in (
            _wrap.prefix_slots, _wrap.suffix_slots,
            _wrap.proclitic_slots, _wrap.enclitic_slots,
        ):
            for sl in slot_iter:
                src_slot_guids.add(_guid_str(sl))

    seen_env_guids = set()

    # Build a GUID → target-entry index once for the duration of this walk
    # (Phase 1 overwrite path uses it for direct-GUID lookup of entries/senses;
    # they're factory-created with Guid preserved, so target.LexEntry.GetAll
    # contains them under the source GUIDs).
    target_entry_index = None  # lazily built when enable_overwrite is True

    def _target_has_entry_guid(target, guid: str) -> bool:
        nonlocal target_entry_index
        if target_entry_index is None:
            target_entry_index = {}
            if hasattr(target, "LexEntry"):
                for te in target.LexEntry.GetAll():
                    target_entry_index[_guid_str(_unwrap(te))] = te
        return guid in target_entry_index

    for entry in source.LexEntry.GetAll():
        entry_qualifies = False
        sense_actions = []
        msa_actions = []

        for sense in source.LexEntry.GetSenses(entry):
            msa = _lex_sense_msa(sense)
            if msa is None:
                continue
            if _classname_of(msa) != "MoInflAffMsa":
                continue
            if not _msa_points_at_verb(msa, src_verb_guid):
                continue
            entry_qualifies = True
            sense_guid = _guid_str(sense)
            msa_guid = _guid_str(msa)
            sense_actions.append((sense, sense_guid))
            msa_actions.append((msa, msa_guid, sense_guid))

        if not entry_qualifies:
            continue

        entry_guid = _guid_str(entry)
        entry_hw = source.LexEntry.GetHeadword(entry)

        # Phase 1 (FR-101/108): if enable_overwrite is set AND the entry's
        # GUID already exists in the target, emit a PlannedOverwrite instead
        # of an ADD. Senses are owned by entries; since entry GUIDs are
        # factory-preserved in Phase 0, an entry already-in-target implies
        # its senses are too (we promote both to overwrites in lockstep).
        entry_is_overwrite = (
            selection.enable_overwrite
            and overwrites is not None
            and _target_has_entry_guid(target, entry_guid)
        )

        # T-FR001: Phase-1.5 similar-resolution hook.
        # Entry-is-overwrite (same GUID in target) takes priority — checked first.
        # Only read resolution when the entry is NOT already a same-GUID overwrite.
        if not entry_is_overwrite and overwrites is not None:
            resolution = selection.similar_resolution_for(entry_guid)
            if resolution is not None and resolution.action in ("overwrite", "merge"):
                # Identity-remap path: plan ENTRY action against the resolved target GUID.
                tgt_entry_for_remap = None
                if target_entry_index is None:
                    # Force-build the index now.
                    _target_has_entry_guid(target, resolution.target_guid)
                tgt_entry_for_remap = (target_entry_index or {}).get(resolution.target_guid)
                overwrites.append(PlannedOverwrite(
                    category=GrammarCategory.ENTRY,
                    source_guid=entry_guid,
                    target_guid=resolution.target_guid,
                    summary=f"LexEntry {entry_hw!r} -> identity remap",
                    match_via="identity_remap",
                    write_mode=resolution.action,
                    pulled_in_by=() if selection.is_on(GrammarCategory.ENTRY)
                                 else (src_verb_guid,),
                    owner_guid="",
                ))
                identity_remap[entry_guid] = resolution.target_guid
                if tgt_entry_for_remap is not None:
                    _plan_identity_remap_children(
                        entry, entry_guid, entry_hw, resolution.target_guid,
                        tgt_entry_for_remap, src_verb_guid, src_slot_guids,
                        source, target, selection,
                        actions, skips, overwrites, seen_env_guids,
                    )
                continue  # skip Phase-0 add path for this entry

        if entry_is_overwrite:
            overwrites.append(PlannedOverwrite(
                category=GrammarCategory.ENTRY,
                source_guid=entry_guid,
                target_guid=entry_guid,
                summary=f"LexEntry {entry_hw!r}",
                match_via="guid",
                pulled_in_by=() if selection.is_on(GrammarCategory.ENTRY) else (src_verb_guid,),
                owner_guid="",  # LexEntries are LexDb-owned; no parent ref needed
            ))
            for _sense, sense_guid in sense_actions:
                overwrites.append(PlannedOverwrite(
                    category=GrammarCategory.SENSE,
                    source_guid=sense_guid,
                    target_guid=sense_guid,
                    summary=f"Sense of {entry_hw!r}",
                    match_via="guid",
                    pulled_in_by=(entry_guid,),
                    owner_guid=entry_guid,
                ))
            # Phase 1.2 (FR-104): MSAs and Allomorphs are matched by
            # fingerprint against the target entry's existing MSAs and
            # allomorphs. Their GUIDs were re-assigned in Phase 0, so
            # direct GUID lookup fails — but the fingerprint
            # (class+pos+slots for MSA; lexeme_form+morphtype for
            # allomorph) is stable across runs because every piece of
            # information in it is GUID-preserved (entry, slot, morphtype).
            tgt_entry = target_entry_index[entry_guid]
            msa_match_via, _msa_overwrite_pairs, _msa_add_list = _match_msas_by_fingerprint(
                target, tgt_entry, msa_actions, entry_guid,
            )
            for src_msa, msa_guid, sense_guid in _msa_overwrite_pairs:
                tgt_msa_guid = msa_match_via[msa_guid]
                overwrites.append(PlannedOverwrite(
                    category=GrammarCategory.MSA,
                    source_guid=msa_guid,
                    target_guid=tgt_msa_guid,
                    summary=f"InflAffMsa for {entry_hw!r}",
                    match_via="fingerprint",
                    pulled_in_by=(sense_guid,),
                    owner_guid=entry_guid,
                ))
            for _src_msa, msa_guid, sense_guid in _msa_add_list:
                actions.append(PlannedAction(
                    category=GrammarCategory.MSA,
                    source_guid=msa_guid,
                    intended_target_guid=msa_guid,
                    summary=f"InflAffMsa for {entry_hw!r}",
                    pulled_in_by=(sense_guid,),
                ))
            # Allomorphs: same pattern with default-vernacular WS handle.
            allo_match_via, _allo_overwrite_list, _allo_add_list = _match_allomorphs_by_fingerprint(
                source, target, tgt_entry, entry, entry_guid,
            )
            for src_allo, allo_guid in _allo_overwrite_list:
                tgt_allo_guid = allo_match_via[allo_guid]
                overwrites.append(PlannedOverwrite(
                    category=GrammarCategory.ALLOMORPH,
                    source_guid=allo_guid,
                    target_guid=tgt_allo_guid,
                    summary=f"Allomorph of {entry_hw!r}",
                    match_via="fingerprint",
                    pulled_in_by=(entry_guid,),
                    owner_guid=entry_guid,
                ))
            for _src_allo, allo_guid in _allo_add_list:
                actions.append(PlannedAction(
                    category=GrammarCategory.ALLOMORPH,
                    source_guid=allo_guid,
                    intended_target_guid=allo_guid,
                    summary=f"Allomorph of {entry_hw!r}",
                    pulled_in_by=(entry_guid,),
                ))
            # Phone-environments: scoped to the entry, independent of MSA/Allomorph
            # overwrite outcome. Each source allomorph may reference one or more
            # environments; same target-presence check as Phase 0.
            for allo in source.Allomorphs.GetAll(entry):
                allo_obj = _unwrap(allo)
                allo_guid = _guid_str(allo_obj)
                envs = source.Allomorphs.GetPhoneEnv(allo)
                if envs is None:
                    continue
                for env in envs:
                    env_obj = _unwrap(env)
                    env_guid = _guid_str(env_obj)
                    if env_guid in seen_env_guids:
                        continue
                    seen_env_guids.add(env_guid)
                    if _target_has_environment_guid(target, env_guid):
                        if selection.enable_overwrite:
                            overwrites.append(PlannedOverwrite(
                                category=GrammarCategory.PH_ENVIRONMENT,
                                source_guid=env_guid,
                                target_guid=env_guid,
                                summary="PhEnvironment overwrite (referenced by allomorph(s))",
                                match_via="guid",
                                pulled_in_by=(allo_guid,),
                                owner_guid="",
                            ))
                        else:
                            skips.append(Skip(
                                category=GrammarCategory.PH_ENVIRONMENT,
                                source_guid=env_guid,
                                reason=SkipReason.ALREADY_PRESENT_BY_GUID,
                                detail="PhEnvironment already present in target by GUID",
                            ))
                    else:
                        actions.append(PlannedAction(
                            category=GrammarCategory.PH_ENVIRONMENT,
                            source_guid=env_guid,
                            intended_target_guid=env_guid,
                            summary="PhEnvironment referenced by allomorph(s)",
                            pulled_in_by=(allo_guid,),
                        ))
            continue  # skip the Phase 0 add path below for this entry

        # Entry, sense, MSA actions (Phase 0 path — entry not in target)
        actions.append(PlannedAction(
            category=GrammarCategory.ENTRY,
            source_guid=entry_guid,
            intended_target_guid=entry_guid,
            summary=f"LexEntry {entry_hw!r}",
            pulled_in_by=() if selection.is_on(GrammarCategory.ENTRY) else (src_verb_guid,),
        ))
        for _sense, sense_guid in sense_actions:
            actions.append(PlannedAction(
                category=GrammarCategory.SENSE,
                source_guid=sense_guid,
                intended_target_guid=sense_guid,
                summary=f"Sense of {entry_hw!r}",
                pulled_in_by=(entry_guid,),
            ))
        for _msa, msa_guid, sense_guid in msa_actions:
            actions.append(PlannedAction(
                category=GrammarCategory.MSA,
                source_guid=msa_guid,
                intended_target_guid=msa_guid,
                summary=f"InflAffMsa for {entry_hw!r}",
                pulled_in_by=(sense_guid,),
            ))

        # Phase 3c Selection UI: EXCLUDED-LOSSY check for MSA.PartOfSpeechRA.
        # If the user scoped POS to NONE or per-item excluded the POS GUID, and
        # the target does not already have it, emit an entry-centric warning.
        if excluded_lossy is not None:
            for _msa, msa_guid, _sense_guid in msa_actions:
                _check_msa_pos_excluded_lossy(
                    _msa, entry_guid, entry_hw, target, selection, excluded_lossy
                )

        # Allomorphs + environments. Allomorphs.GetAll may return wrapped
        # objects (similar to MorphRules templates); _unwrap handles both.
        for allo in source.Allomorphs.GetAll(entry):
            allo_obj = _unwrap(allo)
            allo_guid = _guid_str(allo_obj)
            actions.append(PlannedAction(
                category=GrammarCategory.ALLOMORPH,
                source_guid=allo_guid,
                intended_target_guid=allo_guid,
                summary=f"Allomorph of {entry_hw!r}",
                pulled_in_by=(entry_guid,),
            ))
            envs = source.Allomorphs.GetPhoneEnv(allo)
            if envs is None:
                continue
            for env in envs:
                env_obj = _unwrap(env)
                env_guid = _guid_str(env_obj)
                if env_guid in seen_env_guids:
                    continue
                seen_env_guids.add(env_guid)
                # PhEnvironments are project-wide and often shared across
                # FW projects via standard templates. Check target presence
                # before emitting an action; if it's already there, emit a
                # Skip(ALREADY_PRESENT_BY_GUID) so transfer.py reuses the
                # existing object instead of trying to Create a duplicate
                # GUID (which LCM rejects).
                if _target_has_environment_guid(target, env_guid):
                    if selection.enable_overwrite:
                        overwrites.append(PlannedOverwrite(
                            category=GrammarCategory.PH_ENVIRONMENT,
                            source_guid=env_guid,
                            target_guid=env_guid,
                            summary=f"PhEnvironment overwrite (referenced by allomorph(s))",
                            match_via="guid",
                            pulled_in_by=(allo_guid,),
                            owner_guid="",
                        ))
                    else:
                        skips.append(Skip(
                            category=GrammarCategory.PH_ENVIRONMENT,
                            source_guid=env_guid,
                            reason=SkipReason.ALREADY_PRESENT_BY_GUID,
                            detail=f"PhEnvironment already present in target by GUID",
                        ))
                else:
                    actions.append(PlannedAction(
                        category=GrammarCategory.PH_ENVIRONMENT,
                        source_guid=env_guid,
                        intended_target_guid=env_guid,
                        summary=f"PhEnvironment referenced by allomorph(s)",
                        pulled_in_by=(allo_guid,),
                    ))


def _check_msa_pos_excluded_lossy(
    msa,
    entry_guid: str,
    entry_label: str,
    target,
    selection: Selection,
    excluded_lossy: List[ExcludedLossy],
) -> None:
    """Emit an EXCLUDED-LOSSY warning if the entry's MSA references a POS that
    the user deliberately dropped (via NONE scope or per-item exclusion) and
    the target does not already have it.

    Outcome table (plan.md section (e)):
    1. dep exists in target by GUID -> silent (LINK).
    2. dep absent + entry doesn't reference it -> not reached here.
    3. dep absent + entry references it + user dropped it -> EXCLUDED-LOSSY.
    """
    try:
        from SIL.LCModel import IMoInflAffMsa, ICmObject
        ia = IMoInflAffMsa(_unwrap(msa))
        if ia.PartOfSpeechRA is None:
            return
        pos_guid = str(ICmObject(ia.PartOfSpeechRA).Guid).lower()
    except Exception:
        return

    pos_scope = selection.scope_for(GrammarCategory.POS)
    dep_excluded = (
        pos_scope == CategoryScope.NONE
        or selection.is_dep_excluded(pos_guid)
    )
    if not dep_excluded:
        return

    # Outcome 1: target already has it (LINK) — silent.
    if _target_has_pos_guid(target, pos_guid):
        return

    # Outcome 3: target lacks it and entry references it — EXCLUDED-LOSSY.
    excluded_lossy.append(ExcludedLossy(
        category=GrammarCategory.ENTRY,
        entry_guid=entry_guid,
        entry_label=entry_label,
        dep_category=GrammarCategory.POS,
        dep_guid=pos_guid,
        dep_label=f"POS ({pos_guid[:8]}...)",
        message=f"Entry {entry_label!r} will have no Part of Speech.",
    ))


def _target_has_environment_guid(target, env_guid: str) -> bool:
    """True iff the target's PhonologicalData.EnvironmentsOS contains this GUID."""
    try:
        envs = target.Environments.GetAll()
    except AttributeError:
        return False
    for e in envs:
        if _guid_str(_unwrap(e)) == env_guid:
            return True
    return False


def _lex_sense_msa(sense):
    from SIL.LCModel import ILexSense
    return ILexSense(sense).MorphoSyntaxAnalysisRA


def _classname_of(obj):
    from SIL.LCModel import ICmObject
    return ICmObject(obj).ClassName


def _match_msas_by_fingerprint(target, tgt_entry, msa_actions, entry_guid: str):
    """Match source MSAs against target MSAs on the same entry by fingerprint
    (FR-104). Returns:

    - `match_via`: dict[source_msa_guid → target_msa_guid] for matched pairs
    - `overwrite_pairs`: list of (src_msa, msa_guid, sense_guid) to overwrite
    - `add_list`: list of (src_msa, msa_guid, sense_guid) that found no match

    The fingerprint per FR-104 is (category, owner_entry_guid, "MoInflAffMsa",
    pos_guid, frozenset(slot_guids)). Built independently for source and target.
    """
    from SIL.LCModel import ILexEntry, ICmObject

    # Compute target-side fingerprints → target msa guid map.
    target_fp_to_guid = {}
    try:
        for tmsa in ILexEntry(tgt_entry).MorphoSyntaxAnalysesOC:
            if _classname_of(tmsa) != "MoInflAffMsa":
                continue
            fp = _msa_fingerprint(tmsa, entry_guid)
            target_fp_to_guid[fp] = str(ICmObject(tmsa).Guid).lower()
    except (AttributeError, TypeError):
        pass

    match_via = {}
    overwrite_pairs = []
    add_list = []
    for src_msa, msa_guid, sense_guid in msa_actions:
        fp = _msa_fingerprint(src_msa, entry_guid)
        tgt_msa_guid = target_fp_to_guid.get(fp)
        if tgt_msa_guid is not None:
            match_via[msa_guid] = tgt_msa_guid
            overwrite_pairs.append((src_msa, msa_guid, sense_guid))
        else:
            add_list.append((src_msa, msa_guid, sense_guid))
    return match_via, overwrite_pairs, add_list


def _msa_fingerprint(msa, owner_entry_guid: str):
    """Inline fingerprint for MSA matching — avoids the matcher.py
    indirection so the planner can operate on flexicon wrappers
    transparently."""
    from SIL.LCModel import IMoInflAffMsa, ICmObject
    ia = IMoInflAffMsa(_unwrap(msa))
    pos_guid = ""
    if ia.PartOfSpeechRA is not None:
        pos_guid = str(ICmObject(ia.PartOfSpeechRA).Guid).lower()
    slot_guids = frozenset(str(ICmObject(sl).Guid).lower() for sl in ia.SlotsRC)
    return (GrammarCategory.MSA, owner_entry_guid.lower(), "MoInflAffMsa", pos_guid, slot_guids)


def _match_allomorphs_by_fingerprint(source, target, tgt_entry, src_entry, entry_guid: str):
    """Match source allomorphs against target allomorphs on the same entry
    by fingerprint (FR-104). Returns the same shape as _match_msas_by_fingerprint.

    Fingerprint per FR-104:
    (category, owner_entry_guid, lexeme_form_text, morph_type_guid).
    """
    from SIL.LCModel import ICmObject
    cache = getattr(target, "Cache", None)
    ws_handle = None
    try:
        if cache is not None:
            ws_handle = cache.DefaultVernWs
    except AttributeError:
        ws_handle = None

    # Target-side fingerprints
    target_fp_to_guid = {}
    try:
        for tallo in target.Allomorphs.GetAll(tgt_entry):
            tallo_obj = _unwrap(tallo)
            fp = _allomorph_fingerprint(tallo_obj, entry_guid, ws_handle)
            target_fp_to_guid[fp] = str(ICmObject(tallo_obj).Guid).lower()
    except (AttributeError, TypeError):
        pass

    match_via = {}
    overwrite_list = []
    add_list = []
    src_ws_handle = None
    try:
        src_cache = getattr(source, "Cache", None)
        if src_cache is not None:
            src_ws_handle = src_cache.DefaultVernWs
    except AttributeError:
        src_ws_handle = None
    for sallo in source.Allomorphs.GetAll(src_entry):
        sallo_obj = _unwrap(sallo)
        allo_guid = _guid_str(sallo_obj)
        fp = _allomorph_fingerprint(sallo_obj, entry_guid, src_ws_handle)
        tgt_allo_guid = target_fp_to_guid.get(fp)
        if tgt_allo_guid is not None:
            match_via[allo_guid] = tgt_allo_guid
            overwrite_list.append((sallo_obj, allo_guid))
        else:
            add_list.append((sallo_obj, allo_guid))
    return match_via, overwrite_list, add_list


def _allomorph_fingerprint(allo, owner_entry_guid: str, ws_handle):
    """Inline allomorph fingerprint per FR-104."""
    from SIL.LCModel import IMoAffixAllomorph, ICmObject
    ia = IMoAffixAllomorph(allo)
    morph_type_guid = ""
    if ia.MorphTypeRA is not None:
        morph_type_guid = str(ICmObject(ia.MorphTypeRA).Guid).lower()
    lexeme_form_text = ""
    if ws_handle is not None:
        try:
            ts_string = ia.Form.get_String(ws_handle)
            lexeme_form_text = (ts_string.Text or "") if ts_string is not None else ""
        except (AttributeError, TypeError):
            lexeme_form_text = ""
    return (GrammarCategory.ALLOMORPH, owner_entry_guid.lower(), lexeme_form_text, morph_type_guid)


def _plan_identity_remap_children(
    src_entry,
    src_entry_guid: str,
    src_entry_hw: str,
    tgt_entry_guid: str,
    tgt_entry,
    src_verb_guid: str,
    src_slot_guids: set,
    source,
    target,
    selection: "Selection",
    actions: list,
    skips: list,
    overwrites: list,
    seen_env_guids: set,
) -> None:
    """Plan MSA / Allomorph / PhEnvironment children for an identity-remap entry.

    Mirrors the Phase-1 fingerprint block in _plan_layer3_verb_affixes_inner
    (lines 609-703) but uses tgt_entry_guid (the resolved target GUID) as the
    owner override so fingerprint comparison is against the resolved target's
    children rather than the source entry.

    Called from two sites:
    - T-FR001 identity-remap branch in _plan_layer3_verb_affixes_inner.
    """
    # Collect source MSA/sense actions for this entry.
    sense_actions = []
    msa_actions = []
    for sense in source.LexEntry.GetSenses(src_entry):
        msa = _lex_sense_msa(sense)
        if msa is None:
            continue
        if _classname_of(msa) != "MoInflAffMsa":
            continue
        if not _msa_points_at_verb(msa, src_verb_guid):
            continue
        sense_guid = _guid_str(sense)
        msa_guid = _guid_str(msa)
        sense_actions.append((sense, sense_guid))
        msa_actions.append((msa, msa_guid, sense_guid))

    # MSA fingerprint matching against the resolved target entry.
    # Use tgt_entry_guid as the owner override so cross-entry comparison works.
    msa_match_via, _msa_overwrite_pairs, _msa_add_list = _match_msas_by_fingerprint(
        target, tgt_entry, msa_actions, tgt_entry_guid,
    )
    for src_msa, msa_guid, sense_guid in _msa_overwrite_pairs:
        tgt_msa_guid = msa_match_via[msa_guid]
        overwrites.append(PlannedOverwrite(
            category=GrammarCategory.MSA,
            source_guid=msa_guid,
            target_guid=tgt_msa_guid,
            summary=f"InflAffMsa for {src_entry_hw!r} (identity remap)",
            match_via="fingerprint",
            pulled_in_by=(sense_guid,),
            owner_guid=tgt_entry_guid,
        ))
    for _src_msa, msa_guid, sense_guid in _msa_add_list:
        actions.append(PlannedAction(
            category=GrammarCategory.MSA,
            source_guid=msa_guid,
            intended_target_guid=msa_guid,
            summary=f"InflAffMsa for {src_entry_hw!r} (identity remap)",
            pulled_in_by=(sense_guid,),
        ))

    # Allomorph fingerprint matching against the resolved target entry.
    allo_match_via, _allo_overwrite_list, _allo_add_list = _match_allomorphs_by_fingerprint(
        source, target, tgt_entry, src_entry, tgt_entry_guid,
    )
    for src_allo, allo_guid in _allo_overwrite_list:
        tgt_allo_guid = allo_match_via[allo_guid]
        overwrites.append(PlannedOverwrite(
            category=GrammarCategory.ALLOMORPH,
            source_guid=allo_guid,
            target_guid=tgt_allo_guid,
            summary=f"Allomorph of {src_entry_hw!r} (identity remap)",
            match_via="fingerprint",
            pulled_in_by=(src_entry_guid,),
            owner_guid=tgt_entry_guid,
        ))
    for _src_allo, allo_guid in _allo_add_list:
        actions.append(PlannedAction(
            category=GrammarCategory.ALLOMORPH,
            source_guid=allo_guid,
            intended_target_guid=allo_guid,
            summary=f"Allomorph of {src_entry_hw!r} (identity remap)",
            pulled_in_by=(src_entry_guid,),
        ))

    # Phone-environments for allomorphs under the resolved entry.
    for allo in source.Allomorphs.GetAll(src_entry):
        allo_obj = _unwrap(allo)
        allo_guid = _guid_str(allo_obj)
        envs = source.Allomorphs.GetPhoneEnv(allo)
        if envs is None:
            continue
        for env in envs:
            env_obj = _unwrap(env)
            env_guid = _guid_str(env_obj)
            if env_guid in seen_env_guids:
                continue
            seen_env_guids.add(env_guid)
            if _target_has_environment_guid(target, env_guid):
                if selection.enable_overwrite:
                    overwrites.append(PlannedOverwrite(
                        category=GrammarCategory.PH_ENVIRONMENT,
                        source_guid=env_guid,
                        target_guid=env_guid,
                        summary="PhEnvironment overwrite (identity remap allomorph)",
                        match_via="guid",
                        pulled_in_by=(allo_guid,),
                        owner_guid="",
                    ))
                else:
                    skips.append(Skip(
                        category=GrammarCategory.PH_ENVIRONMENT,
                        source_guid=env_guid,
                        reason=SkipReason.ALREADY_PRESENT_BY_GUID,
                        detail="PhEnvironment already present in target by GUID",
                    ))
            else:
                actions.append(PlannedAction(
                    category=GrammarCategory.PH_ENVIRONMENT,
                    source_guid=env_guid,
                    intended_target_guid=env_guid,
                    summary="PhEnvironment referenced by identity-remap allomorph",
                    pulled_in_by=(allo_guid,),
                ))


def _msa_points_at_verb(msa, verb_guid: str) -> bool:
    from SIL.LCModel import IMoInflAffMsa, ICmObject
    ia = IMoInflAffMsa(msa)
    if ia.PartOfSpeechRA is None:
        return False
    return str(ICmObject(ia.PartOfSpeechRA).Guid).lower() == verb_guid


def _emit_template(target,
                   owner_pos_guid: str,
                   tpl_guid: str,
                   user_selected: bool,
                   actions: List[PlannedAction],
                   skips: List[Skip],
                   selection: Selection,
                   overwrites: Optional[List[PlannedOverwrite]]) -> None:
    """Emit Add or Skip-by-GUID (Phase 0) / Overwrite (Phase 1) for a template."""
    if _target_has_template_guid(target, owner_pos_guid, tpl_guid):
        _emit_present_outcome(
            GrammarCategory.AFFIX_TEMPLATES,
            src_guid=tpl_guid,
            target_guid=tpl_guid,
            summary=f"Affix template already present (guid {tpl_guid[:8]}…)",
            skip_detail="Template already present in target by GUID",
            selection=selection,
            skips=skips,
            overwrites=overwrites,
            pulled_in_by=() if user_selected else (owner_pos_guid,),
            owner_guid=owner_pos_guid,
        )
    else:
        actions.append(PlannedAction(
            category=GrammarCategory.AFFIX_TEMPLATES,
            source_guid=tpl_guid,
            intended_target_guid=tpl_guid,
            summary=f"Affix template under Verb (guid {tpl_guid[:8]}…)",
            pulled_in_by=() if user_selected else (owner_pos_guid,),
        ))


# ============================================================================
# Read-only target probes
# ============================================================================

def _target_has_pos_guid(target, guid_str: str) -> bool:
    for pos in target.POS.GetAll(recursive=True):
        if _guid_str(_unwrap(pos)) == guid_str:
            return True
    return False


def _target_has_template_guid(target, owner_pos_guid: str, tpl_guid: str) -> bool:
    target_pos = _find_pos_by_guid(target, owner_pos_guid)
    if target_pos is None:
        return False
    for t in target.MorphRules.GetAllAffixTemplatesForPOS(target_pos):
        if _guid_str(_unwrap(t)) == tpl_guid:
            return True
    return False


def _target_has_slot_guid(target, owner_pos_guid: str, slot_guid: str) -> bool:
    target_pos = _find_pos_by_guid(target, owner_pos_guid)
    if target_pos is None:
        return False
    for s in target.POS.GetAffixSlots(target_pos):
        if _guid_str(_unwrap(s)) == slot_guid:
            return True
    return False


def _find_pos_by_guid(target, guid_str: str):
    for pos in target.POS.GetAll(recursive=True):
        concrete = _unwrap(pos)
        if _guid_str(concrete) == guid_str:
            return concrete
    return None


# ============================================================================
# Tiny utilities (LCM-aware but pure-property reads)
# ============================================================================

def _guid_str(obj) -> str:
    """Lower-cased string form of `obj.Guid`. Lazy-imports ICmObject so this
    module is import-safe outside FlexTools."""
    from SIL.LCModel import ICmObject  # lazy
    return str(ICmObject(obj).Guid).lower()


def _unwrap(obj):
    """Strip a flexicon wrapper to the concrete LCM object if present."""
    return obj.concrete if hasattr(obj, "concrete") else obj


def _slot_name(slot) -> str:
    from SIL.LCModel import IMoInflAffixSlot  # lazy
    return IMoInflAffixSlot(_unwrap(slot)).Name.BestAnalysisAlternative.Text

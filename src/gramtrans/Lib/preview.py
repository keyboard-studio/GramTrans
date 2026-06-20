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

from typing import Iterable, List, Optional, Tuple

if __package__:
    from .models import (
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

    Source and target are flexlibs2 FLExProject handles (or duck-typed
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
    identity_remap: dict = {}

    # Walk every selected POS (or all top-level POSes when categories[POS]
    # is True and pos_picks is empty). For each POS, walk its closure:
    # POS → Template → Slots → LexEntries(MSA-points-at-POS) → Senses → MSAs
    # → Allomorphs → PhEnvironments.
    for src_pos in _select_source_poses(source, selection):
        _plan_pos_closure(source, target, src_pos, selection, actions, skips, overwrites)
        _plan_layer3_for_pos(source, target, src_pos, selection, actions, skips, overwrites)

    return RunPlan(
        context=context,
        selection=selection,
        ws_mapping=ws_mapping,
        actions=tuple(actions),
        skips=tuple(skips),
        identity_remap=identity_remap,
        overwrites=tuple(overwrites),
    )


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
        GrammarCategory.TEMPLATES,
        GrammarCategory.SLOTS,
        GrammarCategory.ENTRY,
        GrammarCategory.SENSE,
        GrammarCategory.MSA,
        GrammarCategory.ALLOMORPH,
        GrammarCategory.PH_ENVIRONMENT,
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
) -> None:
    """Layer 3 (LexEntry / Sense / MSA / Allomorph / PhEnvironment) walk for
    affix entries whose IMoInflAffMsa.PartOfSpeechRA points at `src_pos`."""
    _plan_layer3_verb_affixes_inner(
        source, target, src_pos, selection, actions, skips, overwrites,
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

    closure_on = selection.include_closure
    pos_on = selection.is_on(GrammarCategory.POS)
    tpl_on = selection.is_on(GrammarCategory.TEMPLATES)
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
                        category=GrammarCategory.TEMPLATES,
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

    closure_on = selection.include_closure
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
            # MSAs and Allomorphs continue as adds (their GUIDs were
            # re-assigned in Phase 0 via factory.Create() without Guid;
            # fingerprint matching for them is Phase 1.2).
            for _msa, msa_guid, sense_guid in msa_actions:
                actions.append(PlannedAction(
                    category=GrammarCategory.MSA,
                    source_guid=msa_guid,
                    intended_target_guid=msa_guid,
                    summary=f"InflAffMsa for {entry_hw!r}",
                    pulled_in_by=(sense_guid,),
                ))
            # Allomorphs handled in the loop below.
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
                    if _target_has_environment_guid(target, env_guid):
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
            GrammarCategory.TEMPLATES,
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
            category=GrammarCategory.TEMPLATES,
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
    """Strip a flexlibs2 wrapper to the concrete LCM object if present."""
    return obj.concrete if hasattr(obj, "concrete") else obj


def _slot_name(slot) -> str:
    from SIL.LCModel import IMoInflAffixSlot  # lazy
    return IMoInflAffixSlot(_unwrap(slot)).Name.BestAnalysisAlternative.Text

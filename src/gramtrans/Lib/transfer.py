"""Move-mode plan executor (constitution v5.0.0 Principle III).

`execute(plan, source, target, report)` consumes a RunPlan produced by
`Lib/preview.py.build_run_plan` and applies its actions to the target.
The FlexTools runner already wraps `MainFunction` in an UndoableUnitOfWork
(research.md R10), so this module does NOT open its own UOW — the
`Ctrl+Z`-undoes-everything property comes from the outer runner unit.

The verb-vertical per-layer creators (POS, Template, Slot) preserve source
GUIDs via the LCM factories' `Create(Guid, owner)` overloads, then apply the
source's syncable properties via the patched fork's `ApplySyncableProperties`
(see CLAUDE.md). Residue tagging routes through `Lib/residue.py.apply_residue`.
"""
from __future__ import annotations

import time
from typing import Iterable

if __package__:
    from .models import (
        GrammarCategory,
        PlannedAction,
        RunMode,
        RunPlan,
        RunReport,
        Skip,
        SkipReason,
    )
    from .residue import ImportResidueTag, apply_residue, apply_carrier_b
    from . import report as _report_module  # registers RunReport.build_from_plan
else:
    from models import (
        GrammarCategory,
        PlannedAction,
        RunMode,
        RunPlan,
        RunReport,
        Skip,
        SkipReason,
    )
    from residue import ImportResidueTag, apply_residue, apply_carrier_b
    import report as _report_module  # registers RunReport.build_from_plan


# ============================================================================
# Public API
# ============================================================================

def execute(plan: RunPlan, source, target, report_sink, tag: ImportResidueTag) -> RunReport:
    """Apply `plan.actions` to `target` and return a finalized RunReport.

    `report_sink` is the FlexTools-style report object exposing
    `.Info(msg)` / `.Warning(msg)` / `.Error(msg)` / `.Blank()`. We mirror
    the spike's diagnostic logging there.

    PRECONDITION (UI-enforced per contracts/module-ui.md): the caller has
    already verified that the plan was produced from the current selection.
    """
    start = time.time()

    # Build index of source actions for quick lookup of pulled-in flag.
    pulled_in_guids = frozenset(
        a.source_guid for a in plan.actions if a.pulled_in_by
    )

    # Find every POS the plan touches (as action or skip) and execute its
    # closure: POS → Templates → Slots → LexEntries(MSA-points-at-POS) →
    # Senses → MSAs → Allomorphs → PhEnvironments. Mid-run exceptions
    # bubble up to the FlexTools runner's UOW, which rolls back the entire
    # transaction (R10).
    pos_guids = _pos_guids_from_plan(plan)
    if not pos_guids:
        report_sink.Info("[Move] No POSes in plan; nothing to execute.")
    for pos_guid in pos_guids:
        _execute_verb_vertical(plan, source, target, report_sink, tag, pulled_in_guids, pos_guid)
        _execute_layer3(plan, source, target, report_sink, tag, pos_guid)

    elapsed = time.time() - start
    # Build the report from the plan. If every action ran without raising,
    # the FR-018 invariant on RunReport.__post_init__ passes by construction
    # (every PlannedAction → +1 added, every plan.Skip → +1 skipped).
    return RunReport.build_from_plan(plan, RunMode.MOVE, wall_clock_seconds=elapsed)


# ============================================================================
# Verb-vertical executor (mirrors STATUS.md Layer 1+2 parity rubric)
# ============================================================================

def _pos_guids_from_plan(plan: RunPlan) -> list:
    """Return the ordered list of source POS GUIDs the plan touches —
    union of POS PlannedActions and POS Skips, preserving plan order with
    no duplicates."""
    seen = set()
    ordered = []
    for a in plan.actions:
        if a.category == GrammarCategory.POS and a.source_guid not in seen:
            seen.add(a.source_guid)
            ordered.append(a.source_guid)
    for s in plan.skips:
        if s.category == GrammarCategory.POS and s.source_guid not in seen:
            seen.add(s.source_guid)
            ordered.append(s.source_guid)
    return ordered


def _execute_verb_vertical(
    plan: RunPlan,
    source,
    target,
    report_sink,
    tag: ImportResidueTag,
    pulled_in_guids: frozenset,
    src_pos_guid: str = None,
) -> None:
    """Apply POS + Template + Slot actions for the Verb vertical.

    Reads each PlannedAction's source GUID from `plan.actions`, resolves the
    source-side LCM object, creates the corresponding target object with the
    GUID preserved, applies syncable properties, and tags with the residue
    `tag`. Mirrors `transfer_verb_vertical()` from the pre-T-Spike monolith
    so the parity rubric passes.
    """
    # ----- POS (single action for the MVP slice) -----
    target_verb = None
    for action in _filter(plan.actions, GrammarCategory.POS):
        src_pos = _find_source_pos_by_guid(source, action.source_guid)
        if src_pos is None:
            report_sink.Warning(f"Source POS {action.source_guid} vanished; skipping")
            continue
        target_verb = _create_pos_with_guid(
            target, action.source_guid, source.POS.GetSyncableProperties(src_pos), tag, report_sink
        )

    # If POS was skipped (already in target), look up the existing target POS
    # by GUID so Template/Slot creation can owner-attach to it.
    if target_verb is None:
        # Find by any POS GUID present in either the actions OR the skips for POS
        guid = _first_pos_guid(plan)
        if guid:
            target_verb = _find_target_pos_by_guid(target, guid)

    if target_verb is None:
        report_sink.Warning("No target Verb POS available; skipping template/slot layer")
        return

    # ----- Templates -----
    target_template = None
    for action in _filter(plan.actions, GrammarCategory.TEMPLATES):
        src_template_wrap = _find_source_template_by_guid(source, action.source_guid)
        if src_template_wrap is None:
            report_sink.Warning(f"Source template {action.source_guid} vanished; skipping")
            continue
        target_template = _create_template_with_guid(
            target,
            target_verb,
            action.source_guid,
            source.MorphRules.GetSyncableProperties(src_template_wrap),
            tag,
            report_sink,
        )

    # Owner template may have been Skip-by-GUID; resolve from target.
    if target_template is None:
        guid = _first_template_guid(plan)
        if guid:
            target_template = _find_target_template_by_guid(target, target_verb, guid)

    if target_template is None:
        report_sink.Warning("No target Verb template; skipping slot layer")
        return

    # ----- Slots — preserve source order in the template's prefix/suffix ref seqs -----
    # We need the source-side template wrapper so we can read prefix_slots /
    # suffix_slots ordering. Find it scoped to the owner POS (src_pos_guid),
    # or fall back to first-template-any-POS for the backward-compat path.
    pos_lookup_guid = src_pos_guid or _first_pos_guid(plan)
    if pos_lookup_guid is None:
        report_sink.Warning("No POS in plan to scope the template lookup")
        return
    src_template_wrap = _find_source_first_template_for_pos(source, pos_lookup_guid)
    if src_template_wrap is None:
        report_sink.Warning(
            f"Source POS {pos_lookup_guid[:8]}… has no template at execute time; "
            "slot ordering lost"
        )
        return

    ordered_src_slots = []  # list of (kind, slot, slot_guid)
    for kind, slot_iter in (
        ("prefix", src_template_wrap.prefix_slots),
        ("suffix", src_template_wrap.suffix_slots),
        ("proclitic", src_template_wrap.proclitic_slots),
        ("enclitic", src_template_wrap.enclitic_slots),
    ):
        for slot in slot_iter:
            ordered_src_slots.append((kind, slot, _guid_str(slot)))

    target_template_concrete = _cast_template(target_template)
    ref_seqs = {
        "prefix": target_template_concrete.PrefixSlotsRS,
        "suffix": target_template_concrete.SuffixSlotsRS,
        "proclitic": target_template_concrete.ProcliticSlotsRS,
        "enclitic": target_template_concrete.EncliticSlotsRS,
    }

    target_slots_by_guid: dict = {}
    planned_slot_guids = {a.source_guid for a in _filter(plan.actions, GrammarCategory.SLOTS)}
    for kind, src_slot, slot_guid in ordered_src_slots:
        if slot_guid in planned_slot_guids:
            slot_name = _slot_name(src_slot)
            new_slot = _create_slot_with_guid(
                target, target_verb, slot_guid, slot_name, tag, report_sink
            )
            target_slots_by_guid[slot_guid] = new_slot
        else:
            # Slot was Skip-by-GUID; look up the existing target slot.
            existing = _find_target_slot_by_guid(target, target_verb, slot_guid)
            if existing is not None:
                target_slots_by_guid[slot_guid] = existing

        wire = target_slots_by_guid.get(slot_guid)
        if wire is not None and not _ref_seq_contains(ref_seqs[kind], wire):
            ref_seqs[kind].Add(wire)


# ============================================================================
# Per-layer create helpers (extracted verbatim from the pre-T-Spike monolith
# so the parity rubric in tasks.md T-Spike step 3 passes byte-for-byte on
# created objects)
# ============================================================================

def _create_pos_with_guid(target, src_guid: str, src_props, tag: ImportResidueTag, report_sink):
    """Create a Part-of-Speech in the target with `src_guid` preserved."""
    from SIL.LCModel import IPartOfSpeechFactory, ICmPossibilityList
    from System import Guid as DotNetGuid

    factory = IPartOfSpeechFactory(target.GetFactory(IPartOfSpeechFactory))
    cache = getattr(target, "Cache")
    pos_list = ICmPossibilityList(cache.LangProject.PartsOfSpeechOA)
    new_pos = factory.Create(DotNetGuid.Parse(src_guid), pos_list)
    target.POS.ApplySyncableProperties(new_pos, src_props)
    apply_carrier_b(new_pos, cache.DefaultAnalWs, tag)
    report_sink.Info(f"  POS created  guid={src_guid}")
    return new_pos


def _create_template_with_guid(target, owner_pos, src_guid: str, src_props, tag: ImportResidueTag, report_sink):
    """Create an Affix Template in the target owned by `owner_pos`."""
    from SIL.LCModel import IMoInflAffixTemplateFactory
    from System import Guid as DotNetGuid

    factory = IMoInflAffixTemplateFactory(target.GetFactory(IMoInflAffixTemplateFactory))
    new_template = factory.Create(DotNetGuid.Parse(src_guid))
    owner_pos.AffixTemplatesOS.Add(new_template)
    target.MorphRules.ApplySyncableProperties(new_template, src_props)
    cache = getattr(target, "Cache")
    apply_carrier_b(new_template, cache.DefaultAnalWs, tag)
    report_sink.Info(f"  Template created  guid={src_guid}")
    return new_template


def _create_slot_with_guid(target, owner_pos, src_guid: str, slot_name: str, tag: ImportResidueTag, report_sink):
    """Create an Affix Slot in the target owned by `owner_pos`."""
    from SIL.LCModel import IMoInflAffixSlotFactory, IMoInflAffixSlot
    from SIL.LCModel.Core.Text import TsStringUtils
    from System import Guid as DotNetGuid

    factory = IMoInflAffixSlotFactory(target.GetFactory(IMoInflAffixSlotFactory))
    new_slot = factory.Create(DotNetGuid.Parse(src_guid))
    owner_pos.AffixSlotsOC.Add(new_slot)
    cache = getattr(target, "Cache")
    ws = cache.DefaultAnalWs
    IMoInflAffixSlot(new_slot).Name.set_String(ws, TsStringUtils.MakeString(slot_name, ws))
    apply_carrier_b(new_slot, ws, tag)
    report_sink.Info(f"  Slot {slot_name!r} created  guid={src_guid}")
    return new_slot


# ============================================================================
# Source/target lookups + utilities
# ============================================================================

def _filter(actions, category: GrammarCategory) -> Iterable[PlannedAction]:
    return (a for a in actions if a.category == category)


def _first_pos_guid(plan: RunPlan):
    for a in plan.actions:
        if a.category == GrammarCategory.POS:
            return a.source_guid
    for s in plan.skips:
        if s.category == GrammarCategory.POS:
            return s.source_guid
    return None


def _first_template_guid(plan: RunPlan):
    for a in plan.actions:
        if a.category == GrammarCategory.TEMPLATES:
            return a.source_guid
    for s in plan.skips:
        if s.category == GrammarCategory.TEMPLATES:
            return s.source_guid
    return None


def _find_source_pos_by_guid(source, guid_str: str):
    for pos in source.POS.GetAll(recursive=True):
        concrete = _unwrap(pos)
        if _guid_str(concrete) == guid_str:
            return concrete
    return None


def _find_source_template_by_guid(source, guid_str: str, owner_pos_guid: str = None):
    """Returns the flexlibs2 template *wrapper* (we need its prefix_slots etc.),
    not the bare LCM object. If `owner_pos_guid` is given, only searches
    that POS's templates; otherwise scans every POS."""
    candidate_poses = []
    if owner_pos_guid is not None:
        p = _find_source_pos_by_guid(source, owner_pos_guid)
        if p is not None:
            candidate_poses.append(p)
    else:
        for pos in source.POS.GetAll(recursive=True):
            candidate_poses.append(_unwrap(pos))
    for src_pos in candidate_poses:
        for t in source.MorphRules.GetAllAffixTemplatesForPOS(src_pos):
            concrete = t.concrete
            if _guid_str(concrete) == guid_str:
                return t
    return None


def _find_source_first_template_for_pos(source, owner_pos_guid: str):
    """First template under the given source POS, as flexlibs2 wrapper."""
    src_pos = _find_source_pos_by_guid(source, owner_pos_guid)
    if src_pos is None:
        return None
    for t in source.MorphRules.GetAllAffixTemplatesForPOS(src_pos):
        return t
    return None


def _find_target_pos_by_guid(target, guid_str: str):
    for pos in target.POS.GetAll(recursive=True):
        concrete = _unwrap(pos)
        if _guid_str(concrete) == guid_str:
            return _cast_pos(concrete)
    return None


def _find_target_template_by_guid(target, target_pos, guid_str: str):
    for t in target.MorphRules.GetAllAffixTemplatesForPOS(target_pos):
        concrete = _unwrap(t)
        if _guid_str(concrete) == guid_str:
            return concrete
    return None


def _find_target_slot_by_guid(target, target_pos, guid_str: str):
    for s in target.POS.GetAffixSlots(target_pos):
        concrete = _unwrap(s)
        if _guid_str(concrete) == guid_str:
            return concrete
    return None


def _cast_pos(obj):
    from SIL.LCModel import IPartOfSpeech
    return IPartOfSpeech(obj)


def _cast_template(obj):
    from SIL.LCModel import IMoInflAffixTemplate
    return IMoInflAffixTemplate(obj)


def _guid_str(obj) -> str:
    from SIL.LCModel import ICmObject
    return str(ICmObject(obj).Guid).lower()


def _unwrap(obj):
    return obj.concrete if hasattr(obj, "concrete") else obj


def _slot_name(slot) -> str:
    from SIL.LCModel import IMoInflAffixSlot
    return IMoInflAffixSlot(_unwrap(slot)).Name.BestAnalysisAlternative.Text


def _ref_seq_contains(ref_seq, obj) -> bool:
    from SIL.LCModel import ICmObject
    obj_guid = str(ICmObject(obj).Guid).lower()
    for i in range(ref_seq.Count):
        if str(ICmObject(ref_seq.get_Item(i)).Guid).lower() == obj_guid:
            return True
    return False


# ============================================================================
# Layer 3 executor — LexEntry / Sense / MSA / Allomorph / PhEnvironment
# ============================================================================

def _execute_layer3(
    plan: RunPlan,
    source,
    target,
    report_sink,
    tag: ImportResidueTag,
    src_pos_guid: str = None,
) -> None:
    """Apply ENTRY / SENSE / MSA / ALLOMORPH / PH_ENVIRONMENT actions for the
    verb closure. Mirrors STATUS.md Layer 3 outline:

      ILexEntryFactory.Create(Guid, ILexDb)      → entry, owned by LexDb
      ILexSenseFactory.Create(Guid, ILexEntry)   → sense, owned by entry
      IMoInflAffMsaFactory.Create(Guid)          → MSA;
                                                    entry.MorphoSyntaxAnalysesOC.Add(msa);
                                                    sense.MorphoSyntaxAnalysisRA = msa
      IMoAffixAllomorphFactory.Create(Guid)      → allomorph; entry.LexemeFormOA OR
                                                    entry.AlternateFormsOS.Add(...)
      IPhEnvironmentFactory.Create(Guid)         → env;
                                                    LangProject.PhonologicalDataOA
                                                       .EnvironmentsOS.Add(env)

    Residue: Carrier A (LiftResidue) on Lex*, MoForm, MoMorphSynAnalysis;
    Carrier B (Description-append) on PhEnvironment.
    """
    # Quick exits.
    has_layer3 = any(
        a.category in (
            GrammarCategory.ENTRY,
            GrammarCategory.SENSE,
            GrammarCategory.MSA,
            GrammarCategory.ALLOMORPH,
            GrammarCategory.PH_ENVIRONMENT,
        )
        for a in plan.actions
    )
    if not has_layer3:
        return

    identity_remap = dict(plan.identity_remap) if plan.identity_remap else {}

    # Locate the source POS we're executing Layer 3 for. Caller supplies
    # `src_pos_guid`; for the backward-compat path (no arg), fall back to
    # the first POS GUID in the plan.
    if src_pos_guid is None:
        src_pos_guid = _first_pos_guid(plan)
    if src_pos_guid is None:
        report_sink.Warning("[L3] No POS in plan; skipping Layer 3.")
        return
    src_verb = _find_source_pos_by_guid(source, src_pos_guid)
    if src_verb is None:
        report_sink.Warning(f"[L3] Source POS {src_pos_guid[:8]}… not found; skipping Layer 3.")
        return
    src_verb_guid = src_pos_guid
    target_verb = _find_target_pos_by_guid(target, src_verb_guid)
    if target_verb is None:
        report_sink.Warning(f"[L3] Target POS {src_pos_guid[:8]}… not present; Layer 3 needs Layer 1 first.")
        return

    # Pre-create environments (allomorphs reference them). Skipped
    # PH_ENVIRONMENTs are already in target — look them up so the allomorph
    # PhoneEnvRC wiring step can resolve them.
    env_guid_to_target = {}
    for action in _filter(plan.actions, GrammarCategory.PH_ENVIRONMENT):
        new_env = _create_environment_with_guid(target, action.source_guid, report_sink, tag)
        env_guid_to_target[action.source_guid] = new_env
    for skip in plan.skips:
        if skip.category != GrammarCategory.PH_ENVIRONMENT:
            continue
        existing = _find_target_env_by_guid(target, skip.source_guid)
        if existing is not None:
            env_guid_to_target[skip.source_guid] = existing
            report_sink.Info(f"  PhEnvironment reused (already in target)  guid={skip.source_guid}")

    # Map source slot GUIDs to target slot objects (Layer 2 created them).
    target_slot_by_guid = {}
    for s in target.POS.GetAffixSlots(target_verb):
        target_slot_by_guid[_guid_str(s)] = s

    # Group entry-related actions by entry_guid (sense + msa + allomorph
    # actions reference their entry through pulled_in_by).
    entry_action_guids = [a.source_guid for a in _filter(plan.actions, GrammarCategory.ENTRY)]

    # Index source entries by GUID for quick lookup.
    src_entry_by_guid = {}
    for entry in source.LexEntry.GetAll():
        src_entry_by_guid[_guid_str(entry)] = entry

    for entry_guid in entry_action_guids:
        src_entry = src_entry_by_guid.get(entry_guid)
        if src_entry is None:
            report_sink.Warning(f"[L3] Source entry {entry_guid[:8]} vanished")
            continue

        # 1. Create LexEntry.
        new_entry = _create_lexentry_with_guid(target, entry_guid, src_entry, source, tag, report_sink)

        # 2. Create senses + MSAs in source order.
        src_to_new_msa_by_msa_guid = {}
        for sense in source.LexEntry.GetSenses(src_entry):
            sense_guid = _guid_str(sense)
            new_sense = _create_lexsense_with_guid(target, new_entry, sense_guid, sense, source, tag, report_sink)
            msa = _lex_sense_msa(sense)
            if msa is None:
                continue
            if _classname_of(msa) != "MoInflAffMsa":
                continue
            if not _msa_points_at_verb(msa, src_verb_guid):
                continue
            msa_guid = _guid_str(msa)
            new_msa = _create_inflaff_msa_with_guid(
                target, new_entry, new_sense, msa_guid, msa, target_verb, target_slot_by_guid,
                tag, report_sink, identity_remap,
            )
            src_to_new_msa_by_msa_guid[msa_guid] = new_msa

        # 3. Create allomorphs + wire to environments. Allomorphs.GetAll
        # may yield wrapper objects; unwrap before LCM casts.
        for allo in source.Allomorphs.GetAll(src_entry):
            allo_obj = _unwrap(allo)
            allo_guid = _guid_str(allo_obj)
            new_allo = _create_allomorph_with_guid(
                target, new_entry, allo_guid, allo_obj, source, env_guid_to_target,
                tag, report_sink, identity_remap,
            )


def _find_target_morph_type_by_guid(target, morph_type_guid: str):
    """LCM morph types live under LangProject.LexDbOA.MorphTypesOA (a
    CmPossibilityList). Same GUIDs across all FW projects; just look up by
    GUID."""
    from SIL.LCModel import ICmObject
    try:
        cache = getattr(target, "Cache")
        lex_db = cache.LangProject.LexDbOA
        morph_types_list = lex_db.MorphTypesOA
        for mt in morph_types_list.PossibilitiesOS:
            if str(ICmObject(mt).Guid).lower() == morph_type_guid:
                return mt
    except Exception:
        return None
    return None


def _find_target_env_by_guid(target, env_guid: str):
    """Lookup helper used when a PhEnvironment was Skip-by-GUID."""
    from SIL.LCModel import ICmObject
    try:
        envs = target.Environments.GetAll()
    except AttributeError:
        return None
    for e in envs:
        concrete = e.concrete if hasattr(e, "concrete") else e
        if str(ICmObject(concrete).Guid).lower() == env_guid:
            return concrete
    return None


def _create_environment_with_guid(target, src_guid: str, report_sink, tag: ImportResidueTag):
    """Create IPhEnvironment in target's PhonologicalData with GUID preserved."""
    from SIL.LCModel import IPhEnvironmentFactory, IPhEnvironment
    from System import Guid as DotNetGuid

    factory = IPhEnvironmentFactory(target.GetFactory(IPhEnvironmentFactory))
    new_env = factory.Create(DotNetGuid.Parse(src_guid))
    cache = getattr(target, "Cache")
    cache.LangProject.PhonologicalDataOA.EnvironmentsOS.Add(new_env)
    # Carrier B residue (PhEnvironment has Description).
    ws = cache.DefaultAnalWs
    apply_carrier_b(new_env, ws, tag)
    report_sink.Info(f"  PhEnvironment created  guid={src_guid}")
    return new_env


def _create_lexentry_with_guid(target, src_guid: str, src_entry, source, tag: ImportResidueTag, report_sink):
    """Create ILexEntry owned by target.LexDb with GUID preserved + apply
    syncable string properties."""
    from SIL.LCModel import ILexEntryFactory, ILexDb
    from System import Guid as DotNetGuid

    factory = ILexEntryFactory(target.GetFactory(ILexEntryFactory))
    cache = getattr(target, "Cache")
    lex_db = ILexDb(cache.LangProject.LexDbOA)
    new_entry = factory.Create(DotNetGuid.Parse(src_guid), lex_db)
    src_props = source.LexEntry.GetSyncableProperties(src_entry)
    target.LexEntry.ApplySyncableProperties(new_entry, src_props)
    apply_residue(new_entry, cache.DefaultAnalWs, tag)
    report_sink.Info(f"  LexEntry created  guid={src_guid}")
    return new_entry


def _create_lexsense_with_guid(target, new_entry, src_guid: str, src_sense, source, tag: ImportResidueTag, report_sink):
    """Create ILexSense owned by new_entry with GUID preserved."""
    from SIL.LCModel import ILexSenseFactory, ICmObject
    from System import Guid as DotNetGuid

    factory = ILexSenseFactory(target.GetFactory(ILexSenseFactory))
    new_sense = factory.Create(DotNetGuid.Parse(src_guid), new_entry)
    cache = ICmObject(new_entry).Cache
    src_props = source.Senses.GetSyncableProperties(src_sense)
    target.Senses.ApplySyncableProperties(new_sense, src_props)
    apply_residue(new_sense, cache.DefaultAnalWs, tag)
    report_sink.Info(f"  LexSense created  guid={src_guid}")
    return new_sense


def _create_inflaff_msa_with_guid(target, new_entry, new_sense, src_guid: str, src_msa,
                                    target_verb, target_slot_by_guid,
                                    tag: ImportResidueTag, report_sink,
                                    identity_remap: dict):
    """Create IMoInflAffMsa via flexlibs2's MSAOperations.CreateInflAff (which
    handles the LibLCM SandboxGenericMSA dance internally).

    LCM's IMoInflAffMsaFactory only exposes `Create(ILexEntry, SandboxGenericMSA)`
    — no Guid overload — so MSA GUIDs cannot be preserved. The new GUID is
    recorded in `identity_remap[src_guid] = new_guid` per FR-012.
    """
    from SIL.LCModel import IMoInflAffMsa, ICmObject

    src_slot_objs = []
    src_ia = IMoInflAffMsa(src_msa)
    for src_slot in src_ia.SlotsRC:
        src_slot_guid = str(ICmObject(src_slot).Guid).lower()
        tgt_slot = target_slot_by_guid.get(src_slot_guid)
        if tgt_slot is not None:
            src_slot_objs.append(tgt_slot)

    new_msa = target.MSA.CreateInflAff(new_sense, target_verb, slots=src_slot_objs or None)

    # Record the GUID change (LCM doesn't permit preserve).
    new_guid = str(ICmObject(new_msa).Guid).lower()
    if new_guid != src_guid:
        identity_remap[src_guid] = new_guid

    new_ia = IMoInflAffMsa(new_msa)
    cache = getattr(target, "Cache")
    apply_residue(new_msa, cache.DefaultAnalWs, tag)
    report_sink.Info(
        f"  IMoInflAffMsa created  src={src_guid[:8]}  new={new_guid[:8]}"
        f"  slots={new_ia.SlotsRC.Count}"
    )
    return new_msa


def _create_allomorph_with_guid(target, new_entry, src_guid: str, src_allo, source,
                                  env_guid_to_target,
                                  tag: ImportResidueTag, report_sink,
                                  identity_remap: dict):
    """Create IMoAffixAllomorph via flexlibs2's LexiconAddAllomorph wrapper
    (which handles the LibLCM Create signature internally).

    GUID preservation: LCM allomorph factories don't accept a Guid; new GUID
    is recorded in `identity_remap` per FR-012.

    Phase 0 Layer 3 is structural-only — lexeme Form text content is NOT
    transferred (fork's ApplySyncableProperties has ITsString conversion
    gaps); a future Phase 0.5 task fixes the fork and re-enables string
    content preservation.
    """
    from SIL.LCModel import IMoAffixAllomorphFactory, IMoAffixAllomorph, ILexEntry, ICmObject

    # Without ApplySyncableProperties, we can't easily recover the source
    # form text; create the allomorph as a bare structural placeholder.
    # Try the factory.Create() first — works for some LCM versions.
    factory = IMoAffixAllomorphFactory(target.GetFactory(IMoAffixAllomorphFactory))
    try:
        new_allo = factory.Create()
    except TypeError:
        report_sink.Warning(
            f"  [L3] IMoAffixAllomorphFactory.Create() unavailable; skipping allomorph {src_guid[:8]}"
        )
        return None
    entry_ie = ILexEntry(new_entry)
    if entry_ie.LexemeFormOA is None:
        entry_ie.LexemeFormOA = new_allo
    else:
        entry_ie.AlternateFormsOS.Add(new_allo)

    new_guid = str(ICmObject(new_allo).Guid).lower()
    if new_guid != src_guid:
        identity_remap[src_guid] = new_guid

    # Apply syncable properties (Form multistring + scalar bools, etc.).
    # Fork's BaseOperations.ApplySyncableProperties now handles ITsString
    # wrapping for raw-str scalars via the patch landed 2026-06-19.
    src_props = source.Allomorphs.GetSyncableProperties(src_allo)
    target.Allomorphs.ApplySyncableProperties(new_allo, src_props)

    # MorphTypeRA is an object reference to a global FW morph-type list item
    # — same GUID across every FW project. ApplySyncableProperties dropped
    # it as an object-reference; resolve here explicitly by GUID lookup.
    src_morph_type = IMoAffixAllomorph(src_allo).MorphTypeRA
    if src_morph_type is not None:
        morph_type_guid = str(ICmObject(src_morph_type).Guid).lower()
        target_morph_type = _find_target_morph_type_by_guid(target, morph_type_guid)
        if target_morph_type is not None:
            IMoAffixAllomorph(new_allo).MorphTypeRA = target_morph_type
        else:
            report_sink.Warning(
                f"  [L3] Allomorph {src_guid[:8]} references MorphType "
                f"{morph_type_guid[:8]} not in target"
            )

    # Wire PhoneEnvRC by GUID lookup.
    new_ia = IMoAffixAllomorph(new_allo)
    src_ia = IMoAffixAllomorph(src_allo)
    for src_env in src_ia.PhoneEnvRC:
        env_guid = str(ICmObject(src_env).Guid).lower()
        tgt_env = env_guid_to_target.get(env_guid)
        if tgt_env is None:
            report_sink.Warning(f"  [L3] Allomorph references env {env_guid[:8]} not in target")
            continue
        new_ia.PhoneEnvRC.Add(tgt_env)
    cache = getattr(target, "Cache")
    apply_residue(new_allo, cache.DefaultAnalWs, tag)
    report_sink.Info(f"  IMoAffixAllomorph created  src={src_guid[:8]}  new={new_guid[:8]}")
    return new_allo


def _project_for_cache(cache):
    """Best-effort lookup of the FLExProject wrapper from an LcmCache. Used
    when we have a child object and need to call ApplySyncableProperties via
    the project's Operations accessors. May return None on the source-side
    cache; callers must handle that."""
    # The runner injects `project` into the namespace; module code can't
    # access it. Caller must thread the target project through if they need
    # this. For now return None and skip ApplySyncableProperties on senses;
    # syncable-props on senses are lighter than on entries anyway.
    return None


# Re-imported helpers from preview.py — kept here to avoid a circular import
# at module load time.
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

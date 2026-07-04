"""Move-mode plan executor (constitution v5.0.0 Principle III).

`execute(plan, source, target, report)` consumes a RunPlan produced by
`Lib/preview.py.build_run_plan` and applies its actions to the target.
The FlexTools runner already wraps `MainFunction` in an UndoableUnitOfWork
(research.md R10), so this module does NOT open its own UOW — the
`Ctrl+Z`-undoes-everything property comes from the outer runner unit.

The verb-vertical per-layer creators (POS, Template, Slot) preserve source
GUIDs via the LCM factories' `Create(Guid, owner)` overloads, then apply the
source's syncable properties via flexicon's `ApplySyncableProperties`
(see CLAUDE.md). Residue tagging routes through `Lib/residue.py.apply_residue`.
"""
from __future__ import annotations

import time
from typing import Iterable

if __package__:
    from .models import (
        GrammarCategory,
        MergeDecision,
        MergeDecisionLog,
        MergeResolution,
        PlannedAction,
        RunMode,
        RunPlan,
        RunReport,
        Skip,
        SkipReason,
    )
    from .residue import ImportResidueTag, apply_residue, apply_carrier_b
    from .conflict import _deterministic_merge, _MergeNotEligible
    from . import report as _report_module  # registers RunReport.build_from_plan
else:
    from models import (
        GrammarCategory,
        MergeDecision,
        MergeDecisionLog,
        MergeResolution,
        PlannedAction,
        RunMode,
        RunPlan,
        RunReport,
        Skip,
        SkipReason,
    )
    from residue import ImportResidueTag, apply_residue, apply_carrier_b
    from conflict import _deterministic_merge, _MergeNotEligible
    import report as _report_module  # registers RunReport.build_from_plan


# ============================================================================
# Public API
# ============================================================================

def execute(plan: RunPlan, source, target, report_sink, tag: ImportResidueTag,
            interactive_session=None) -> RunReport:
    """Apply `plan.actions` to `target` and return a finalized RunReport.

    `report_sink` is the FlexTools-style report object exposing
    `.Info(msg)` / `.Warning(msg)` / `.Error(msg)` / `.Blank()`. We mirror
    the spike's diagnostic logging there.

    `interactive_session` (Phase 2, optional): an InteractiveSession with
    user-resolved MergeDecisionLogs.  When supplied, each overwrite
    branch consults `session.merge_decisions_by_guid[target_guid]` and
    applies the decisions via `_apply_merge_decisions` before writing.
    When None, behaviour is bit-identical to Phase 1 (FR-109 source-wins).

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

    # Phase 1 (FR-101): apply OVERWRITE actions. Each PlannedOverwrite
    # looks up the existing target object by GUID and applies the source's
    # syncable properties. Pre-overwrite snapshots in the residue carrier
    # (FR-106) are TODO for Phase 1.1.
    extra_skips = []
    for ow in getattr(plan, "overwrites", ()):
        extra_skips.extend(
            _execute_overwrite(ow, source, target, report_sink, tag, interactive_session)
            or []
        )

    # Phase 3a leaf-category dispatch (execute side): for every
    # PlannedAction whose category is in the leaf set, route through
    # the registered execute_action callback.  Skips and overwrites
    # are handled by the existing paths above.
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
        # Phase 3c (memo steps 14-18) — same order as preview.py; required
        # by FR-333 (17.1 sub-pass) + FR-340 (post-pass A) tail-block timing.
        GrammarCategory.AFFIXES,
        GrammarCategory.ADHOC_COMPOUND_RULES,
        GrammarCategory.SLOTS,
        GrammarCategory.AFFIX_TEMPLATES,
        GrammarCategory.STEMS,
    )
    if __package__:
        from .categories import for_category as _for_category
    else:
        from categories import for_category as _for_category  # type: ignore
    # Build a synthetic RunContext for execute_action since the per-category
    # callbacks expect it (mirrors the planner's context).
    if __package__:
        from .models import RunContext as _RunContext
    else:
        from models import RunContext as _RunContext  # type: ignore
    exec_ctx = _RunContext(
        source_handle=source,
        source_project_name=plan.context.source_project_name,
        source_project_path=plan.context.source_project_path,
        target_handle=target,
        target_project_name=plan.context.target_project_name,
        target_project_path=plan.context.target_project_path,
        run_id=plan.context.run_id,
        started_at=plan.context.started_at,
    )
    # Phase 3c: thread plan reference so execute_action tail blocks
    # (AFFIX_TEMPLATES 17.1 sub-pass, STEMS post-pass A) can access
    # plan.msa_slot_bindings / plan.lexentry_ref_bindings / plan.identity_remap.
    # RunContext is frozen=True; use object.__setattr__ to attach dynamic attr.
    object.__setattr__(exec_ctx, '_run_plan', plan)
    # Phase 3c: collector for execute-time skips emitted by tail blocks
    # (AFFIX_TEMPLATES 17.1 sub-pass, STEMS post-pass A) — folded into the
    # run report's extra_skips after the leaf loop.
    _exec_skips: list = []
    object.__setattr__(exec_ctx, '_exec_skips', _exec_skips)
    leaf_count = 0
    for action in plan.actions:
        if action.category not in _LEAF_DISPATCH_CATEGORIES:
            continue
        try:
            bundle = _for_category(action.category)
        except KeyError:
            continue
        try:
            bundle["execute_action"](action, exec_ctx, plan.ws_mapping, tag)
            leaf_count += 1
        except Exception as exc:
            report_sink.Warning(
                f"  [{action.category.value}] execute_action raised "
                f"{type(exc).__name__}: {exc}; skipping {action.source_guid[:8]}"
            )
    if leaf_count:
        report_sink.Info(f"[Move] Leaf-dispatch executed {leaf_count} action(s).")
    # Fold any tail-block skips (17.1 / post-pass A) into the report.
    if _exec_skips:
        extra_skips.extend(_exec_skips)

    elapsed = time.time() - start
    # Build the report from the plan. If every action ran without raising,
    # the FR-018 invariant on RunReport.__post_init__ passes by construction
    # (every PlannedAction → +1 added, every plan.Skip → +1 skipped).
    return RunReport.build_from_plan(
        plan, RunMode.MOVE,
        wall_clock_seconds=elapsed,
        extra_skips=tuple(extra_skips),
    )


# ============================================================================
# Verb-vertical executor (mirrors STATUS.md Layer 1+2 parity rubric)
# ============================================================================

def _pos_guids_from_plan(plan: RunPlan) -> list:
    """Return the ordered list of source POS GUIDs the plan touches —
    union of POS PlannedActions, POS Overwrites (Phase 1), and POS Skips,
    preserving plan order with no duplicates."""
    seen = set()
    ordered = []
    for a in plan.actions:
        if a.category == GrammarCategory.POS and a.source_guid not in seen:
            seen.add(a.source_guid)
            ordered.append(a.source_guid)
    for ow in getattr(plan, "overwrites", ()):
        if ow.category == GrammarCategory.POS and ow.source_guid not in seen:
            seen.add(ow.source_guid)
            ordered.append(ow.source_guid)
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
    for action in _filter(plan.actions, GrammarCategory.AFFIX_TEMPLATES):
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

def _idempotency_guard(target, src_guid: str, expected_classname: str, report_sink):
    """Idempotency guard: check if an object with `src_guid` already exists.

    Called at EVERY Guid-preserving Create site BEFORE factory.Create(guid, ...).
    LCM factory.Create(existingGuid, owner) does NOT throw -- it silently creates
    a duplicate object permanently written to .fwdata on CloseProject. This guard
    prevents that corruption.

    Returns:
        (True, existing_obj) if a same-class object was found -- caller should
            return existing_obj immediately without calling Create.
        (True, None) if a WRONG-class object was found -- caller should return
            None and skip Create entirely (log WARNING).
        (False, None) if no object exists for that GUID -- proceed with Create.
    """
    try:
        existing = target.Object(src_guid)
    except Exception:
        existing = None

    if existing is None:
        return (False, None)

    # Object exists. Check ClassName.
    try:
        classname = existing.ClassName
    except Exception:
        classname = None

    if classname == expected_classname:
        return (True, existing)

    # Wrong class -- log and skip without create.
    report_sink.Warning(
        f"  [IDEMPOTENCY] GUID {src_guid[:8]}... exists as {classname!r} "
        f"(expected {expected_classname!r}); skipping Create to avoid corruption"
    )
    return (True, None)


def _cast_existing_to_pos(obj):
    """Direct cast for PartOfSpeech (not in cast_to_concrete map)."""
    from SIL.LCModel import IPartOfSpeech
    return IPartOfSpeech(obj)


def _cast_existing_to_slot(obj):
    """Direct cast for MoInflAffixSlot (not in cast_to_concrete map)."""
    from SIL.LCModel import IMoInflAffixSlot
    return IMoInflAffixSlot(obj)


def _cast_existing_to_environment(obj):
    """Direct cast for PhEnvironment (not in cast_to_concrete map)."""
    from SIL.LCModel import IPhEnvironment
    return IPhEnvironment(obj)


def _cast_existing_to_template(obj):
    """cast_to_concrete maps MoInflAffixTemplate; use IMoInflAffixTemplate directly."""
    from SIL.LCModel import IMoInflAffixTemplate
    return IMoInflAffixTemplate(obj)


def _cast_existing_to_lexentry(obj):
    """cast_to_concrete maps LexEntry; use ILexEntry directly."""
    from SIL.LCModel import ILexEntry
    return ILexEntry(obj)


def _cast_existing_to_lexsense(obj):
    """cast_to_concrete maps LexSense; use ILexSense directly."""
    from SIL.LCModel import ILexSense
    return ILexSense(obj)


def _create_pos_with_guid(target, src_guid: str, src_props, tag: ImportResidueTag, report_sink):
    """Create a Part-of-Speech in the target with `src_guid` preserved.

    Idempotency guard (P0): if a PartOfSpeech with this GUID already exists,
    return it without calling Create (prevents LCM silent-duplicate corruption).
    """
    from SIL.LCModel import IPartOfSpeechFactory, ICmPossibilityList
    from System import Guid as DotNetGuid

    found, existing = _idempotency_guard(target, src_guid, "PartOfSpeech", report_sink)
    if found:
        if existing is not None:
            report_sink.Info(f"  POS already exists (idempotency reuse)  guid={src_guid}")
            return _cast_existing_to_pos(existing)
        return None  # wrong-class object; skip

    factory = IPartOfSpeechFactory(target.GetFactory(IPartOfSpeechFactory))
    cache = getattr(target, "Cache")
    pos_list = ICmPossibilityList(cache.LangProject.PartsOfSpeechOA)
    new_pos = factory.Create(DotNetGuid.Parse(src_guid), pos_list)
    target.POS.ApplySyncableProperties(new_pos, src_props)
    apply_carrier_b(new_pos, cache.DefaultAnalWs, tag)
    report_sink.Info(f"  POS created  guid={src_guid}")
    return new_pos


def _create_template_with_guid(target, owner_pos, src_guid: str, src_props, tag: ImportResidueTag, report_sink):
    """Create an Affix Template in the target owned by `owner_pos`.

    Idempotency guard (P0): if a MoInflAffixTemplate with this GUID already
    exists, return it without calling Create.
    """
    from SIL.LCModel import IMoInflAffixTemplateFactory
    from System import Guid as DotNetGuid

    found, existing = _idempotency_guard(target, src_guid, "MoInflAffixTemplate", report_sink)
    if found:
        if existing is not None:
            report_sink.Info(f"  Template already exists (idempotency reuse)  guid={src_guid}")
            return _cast_existing_to_template(existing)
        return None  # wrong-class object; skip

    factory = IMoInflAffixTemplateFactory(target.GetFactory(IMoInflAffixTemplateFactory))
    new_template = factory.Create(DotNetGuid.Parse(src_guid))
    owner_pos.AffixTemplatesOS.Add(new_template)
    target.MorphRules.ApplySyncableProperties(new_template, src_props)
    cache = getattr(target, "Cache")
    apply_carrier_b(new_template, cache.DefaultAnalWs, tag)
    report_sink.Info(f"  Template created  guid={src_guid}")
    return new_template


def _create_slot_with_guid(target, owner_pos, src_guid: str, slot_name: str, tag: ImportResidueTag, report_sink):
    """Create an Affix Slot in the target owned by `owner_pos`.

    Idempotency guard (P0): if a MoInflAffixSlot with this GUID already
    exists, return it without calling Create.
    """
    from SIL.LCModel import IMoInflAffixSlotFactory, IMoInflAffixSlot
    from SIL.LCModel.Core.Text import TsStringUtils
    from System import Guid as DotNetGuid

    found, existing = _idempotency_guard(target, src_guid, "MoInflAffixSlot", report_sink)
    if found:
        if existing is not None:
            report_sink.Info(f"  Slot already exists (idempotency reuse)  guid={src_guid}")
            return _cast_existing_to_slot(existing)
        return None  # wrong-class object; skip

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


def _apply_merge_decisions(src_props, decisions, tgt_pre_props, run_id, category, target_guid):
    """Phase 2 (FR-202..205) -- filter `src_props` per user resolutions.

    Per research.md R3, decisions are applied as a dict-filter pass that
    mirrors `_dedupe_custom_fields`:

    - TAKE_SOURCE: leave src_props[k] unchanged (Phase 1 default).
    - KEEP_TARGET: drop src_props[k] entirely (target's value survives).
    - MERGE: replace src_props[k] with _deterministic_merge(tgt, src).
      On scalar values (_MergeNotEligible), fall back to TAKE_SOURCE +
      log a warning via the returned Skip-but-not-really mechanism
      (caller renders it via report_sink).
    - SKIP: drop src_props[k] AND emit Skip(INTERACTIVE_SKIP).
    - EDIT_CUSTOM: replace src_props[k] with decision.custom_value.

    Args:
        src_props: dict of source's syncable properties.
        decisions: iterable of MergeDecision.
        tgt_pre_props: dict of target's pre-overwrite values.
        run_id: GT-YYYYMMDD-HHMMSS for the merge separator.
        category: GrammarCategory for any Skip records emitted.
        target_guid: target object's GUID for Skip records.

    Returns:
        (filtered_src_props, skip_records: list[Skip])
    """
    if not isinstance(src_props, dict):
        return src_props, []
    out = dict(src_props)
    skips = []
    for d in decisions:
        k = d.field_name
        if d.resolution == MergeResolution.TAKE_SOURCE:
            continue  # default; src_props[k] already wins
        if d.resolution == MergeResolution.KEEP_TARGET:
            out.pop(k, None)
            continue
        if d.resolution == MergeResolution.MERGE:
            left = tgt_pre_props.get(k) if isinstance(tgt_pre_props, dict) else None
            right = out.get(k)
            try:
                out[k] = _deterministic_merge(left, right, run_id)
            except _MergeNotEligible:
                # Scalar -- silently fall back to TAKE_SOURCE per R4.
                pass
            continue
        if d.resolution == MergeResolution.SKIP:
            out.pop(k, None)
            skips.append(Skip(
                category=category,
                source_guid=target_guid,
                reason=SkipReason.INTERACTIVE_SKIP,
                detail=f"User skipped field {k!r} on {target_guid[:8]}",
            ))
            continue
        if d.resolution == MergeResolution.EDIT_CUSTOM:
            out[k] = d.custom_value
            continue
    return out, skips


def _dedupe_custom_fields(src_props, tgt_pre_props):
    """FR-107: drop custom-field keys from `src_props` whose value already
    matches the target's pre-overwrite value.  Keys not in `tgt_pre_props`
    are left in `src_props` (overwrite path).  Keys present in
    `tgt_pre_props` but not in `src_props` are preserved by virtue of
    ApplySyncableProperties only touching keys it receives.

    Custom fields are identified by name prefix "Custom" (flexicon emits
    them as "Custom_<FieldName>" in the syncable props dict).  Non-custom
    properties pass through unchanged so FR-109 (source wins) still applies.

    Returns a new dict; does not mutate inputs.
    """
    if not isinstance(src_props, dict) or not isinstance(tgt_pre_props, dict):
        return src_props
    out = {}
    for k, v in src_props.items():
        if str(k).startswith("Custom") and k in tgt_pre_props and tgt_pre_props[k] == v:
            continue  # identical custom field -- skip the no-op write
        out[k] = v
    return out


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
        if a.category == GrammarCategory.AFFIX_TEMPLATES:
            return a.source_guid
    for s in plan.skips:
        if s.category == GrammarCategory.AFFIX_TEMPLATES:
            return s.source_guid
    return None


def _find_source_pos_by_guid(source, guid_str: str):
    for pos in source.POS.GetAll(recursive=True):
        concrete = _unwrap(pos)
        if _guid_str(concrete) == guid_str:
            return concrete
    return None


def _find_source_template_by_guid(source, guid_str: str, owner_pos_guid: str = None):
    """Returns the flexicon template *wrapper* (we need its prefix_slots etc.),
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
    """First template under the given source POS, as flexicon wrapper."""
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
    layer3_cats = (
        GrammarCategory.ENTRY,
        GrammarCategory.SENSE,
        GrammarCategory.MSA,
        GrammarCategory.ALLOMORPH,
        GrammarCategory.PH_ENVIRONMENT,
    )
    has_layer3 = (
        any(a.category in layer3_cats for a in plan.actions)
        or any(o.category in layer3_cats for o in getattr(plan, "overwrites", ()))
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
    for ow in getattr(plan, "overwrites", ()):
        if ow.category != GrammarCategory.PH_ENVIRONMENT:
            continue
        existing = _find_target_env_by_guid(target, ow.target_guid)
        if existing is not None:
            env_guid_to_target[ow.source_guid] = existing

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
    """Create IPhEnvironment in target's PhonologicalData with GUID preserved.

    Idempotency guard (P0): if a PhEnvironment with this GUID already exists,
    return it without calling Create.
    """
    from SIL.LCModel import IPhEnvironmentFactory, IPhEnvironment
    from System import Guid as DotNetGuid

    found, existing = _idempotency_guard(target, src_guid, "PhEnvironment", report_sink)
    if found:
        if existing is not None:
            report_sink.Info(f"  PhEnvironment already exists (idempotency reuse)  guid={src_guid}")
            return _cast_existing_to_environment(existing)
        return None  # wrong-class object; skip

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
    syncable string properties.

    Idempotency guard (P0): if a LexEntry with this GUID already exists,
    return it without calling Create.
    """
    from SIL.LCModel import ILexEntryFactory, ILexDb
    from System import Guid as DotNetGuid

    found, existing = _idempotency_guard(target, src_guid, "LexEntry", report_sink)
    if found:
        if existing is not None:
            report_sink.Info(f"  LexEntry already exists (idempotency reuse)  guid={src_guid}")
            return _cast_existing_to_lexentry(existing)
        return None  # wrong-class object; skip

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
    """Create ILexSense owned by new_entry with GUID preserved.

    Idempotency guard (P0): if a LexSense with this GUID already exists,
    return it without calling Create.
    """
    from SIL.LCModel import ILexSenseFactory, ICmObject
    from System import Guid as DotNetGuid

    found, existing = _idempotency_guard(target, src_guid, "LexSense", report_sink)
    if found:
        if existing is not None:
            report_sink.Info(f"  LexSense already exists (idempotency reuse)  guid={src_guid}")
            return _cast_existing_to_lexsense(existing)
        return None  # wrong-class object; skip

    factory = ILexSenseFactory(target.GetFactory(ILexSenseFactory))
    new_sense = factory.Create(DotNetGuid.Parse(src_guid), new_entry)
    cache = ICmObject(new_entry).Cache
    src_props = source.Senses.GetSyncableProperties(src_sense)
    target.Senses.ApplySyncableProperties(new_sense, src_props)
    apply_residue(new_sense, cache.DefaultAnalWs, tag)
    report_sink.Info(f"  LexSense created  guid={src_guid}")
    return new_sense


def _create_inflaff_msa_null_tolerant(target, new_sense, target_verb, slot_objs, report_sink):
    """Null-tolerant IMoInflAffMsa creation.

    flexicon's MSAOperations.CreateInflAff calls _ValidateParam(pos, "pos") and
    REJECTS a None POS at the Python wrapper layer.  When `target_verb` is None
    (EXCLUDED-LOSSY: user deliberately dropped the POS dependency), we must
    bypass the wrapper and call the raw LCM factory directly, then clear
    PartOfSpeechRA = None post-creation.

    Strategy: call the factory's Create(ILexEntry, SandboxGenericMSA) with a
    SandboxGenericMSA that has a dummy sentinel POS, then immediately clear
    PartOfSpeechRA on the resulting object.  If the sentinel approach is
    unavailable (older LCM), fall back to a zero-field SandboxGenericMSA.
    """
    from SIL.LCModel import IMoInflAffMsaFactory, IMoInflAffMsa, ILexEntry
    from SIL.LCModel.DomainServices import SandboxGenericMSA, MsaType

    factory = IMoInflAffMsaFactory(target.GetFactory(IMoInflAffMsaFactory))
    sgm = SandboxGenericMSA()
    sgm.MsaType = MsaType.kInfl
    # Leave sgm.MainPOS unset (None) — CreateInflAff won't be called (it
    # validates pos != None); instead call the raw factory directly.
    # ILexEntry.MorphoSyntaxAnalysesOC is the owning OC.
    entry_ie = ILexEntry(new_sense.OwnerOfClass(ILexEntry.kClassId)
                         if hasattr(new_sense, "OwnerOfClass")
                         else target)
    try:
        new_msa = factory.Create(entry_ie, sgm)
    except Exception:
        # Last-resort: create with a real pos, then clear it post-creation.
        # This path requires a sentinel POS exists in target.  If none found,
        # give up and return None.
        report_sink.Warning(
            "  [EXCL-LOSSY] Null-POS MSA creation via raw factory failed; MSA skipped"
        )
        return None
    # Clear PartOfSpeechRA to honor the EXCLUDED-LOSSY intent (null POS).
    try:
        IMoInflAffMsa(new_msa).PartOfSpeechRA = None
    except Exception:
        pass  # LCM may refuse — leave whatever default it set.
    # Wire slots.
    new_ia = IMoInflAffMsa(new_msa)
    for slot_obj in slot_objs:
        try:
            new_ia.SlotsRC.Add(slot_obj)
        except Exception:
            pass
    return new_msa


def _create_inflaff_msa_with_guid(target, new_entry, new_sense, src_guid: str, src_msa,
                                    target_verb, target_slot_by_guid,
                                    tag: ImportResidueTag, report_sink,
                                    identity_remap: dict):
    """Create IMoInflAffMsa via flexicon's MSAOperations.CreateInflAff (which
    handles the LibLCM SandboxGenericMSA dance internally).

    LCM's IMoInflAffMsaFactory only exposes `Create(ILexEntry, SandboxGenericMSA)`
    — no Guid overload — so MSA GUIDs cannot be preserved. The new GUID is
    recorded in `identity_remap[src_guid] = new_guid` per FR-012.

    NULL-TOLERANT PATH (EXCLUDED-LOSSY): when `target_verb` is None (user
    deliberately dropped the POS dependency), `_create_inflaff_msa_null_tolerant`
    is called instead of the normal flexicon wrapper.  The resulting MSA has a
    null PartOfSpeechRA, as the user was warned about at Preview time.
    """
    from SIL.LCModel import IMoInflAffMsa, ICmObject

    src_slot_objs = []
    src_ia = IMoInflAffMsa(src_msa)
    for src_slot in src_ia.SlotsRC:
        src_slot_guid = str(ICmObject(src_slot).Guid).lower()
        tgt_slot = target_slot_by_guid.get(src_slot_guid)
        if tgt_slot is not None:
            src_slot_objs.append(tgt_slot)

    if target_verb is None:
        # EXCLUDED-LOSSY path: null-tolerant creation bypasses the flexicon
        # wrapper that validates pos != None.
        new_msa = _create_inflaff_msa_null_tolerant(
            target, new_sense, target_verb=None,
            slot_objs=src_slot_objs, report_sink=report_sink
        )
        if new_msa is None:
            return None
    else:
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
    """Create IMoAffixAllomorph via flexicon's LexiconAddAllomorph wrapper
    (which handles the LibLCM Create signature internally).

    GUID preservation: LCM allomorph factories don't accept a Guid; new GUID
    is recorded in `identity_remap` per FR-012.

    Phase 0 Layer 3 is structural-only — lexeme Form text content is NOT
    transferred (flexicon's ApplySyncableProperties had ITsString conversion
    gaps in early builds); a future Phase 0.5 task re-enables string
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
    # flexicon's BaseOperations.ApplySyncableProperties now handles ITsString
    # wrapping for raw-str scalars (landed 2026-06-19).
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


# ============================================================================
# Phase 1 overwrite executor (FR-101)
# ============================================================================

def _resolve_decisions_for(overwrite, interactive_session):
    """Look up the MergeDecisionLog for this overwrite's target_guid in the
    session, or return None if there's no session / no log for this object.
    """
    if interactive_session is None:
        return None
    return interactive_session.merge_decisions_by_guid.get(overwrite.target_guid)


def _resolve_and_tag(src_props, tgt_pre_props, tag, log, category, target_guid, run_id):
    """Apply MergeDecisionLog (if any) to src_props and stamp the tag with
    `with_merge_log(log)` when a log is present.

    Returns (filtered_src_props, tagged_tag, skip_records).
    """
    if log is None:
        return src_props, tag.with_snapshot(tgt_pre_props), []
    filtered, skips = _apply_merge_decisions(
        src_props=src_props,
        decisions=log.decisions,
        tgt_pre_props=tgt_pre_props,
        run_id=run_id,
        category=category,
        target_guid=target_guid,
    )
    tagged = tag.with_snapshot(tgt_pre_props).with_merge_log(log)
    return filtered, tagged, skips


def _execute_overwrite(overwrite, source, target, report_sink, tag: ImportResidueTag,
                       interactive_session=None):
    """Apply a single PlannedOverwrite: look up the target object by GUID,
    pull source's syncable properties, and apply them via flexicon's
    `ApplySyncableProperties`.

    Pre-overwrite snapshot in residue (FR-106) is currently NOT recorded —
    queued for Phase 1.1. The existing Carrier-A/B tag is still applied so
    the user can see the run_id that touched this object.
    """
    cat = overwrite.category
    src_guid = overwrite.source_guid
    tgt_guid = overwrite.target_guid

    # Per-category lookup + apply
    if cat == GrammarCategory.POS:
        src_obj = _find_source_pos_by_guid(source, src_guid)
        tgt_obj = _find_target_pos_by_guid(target, tgt_guid)
        if src_obj is None or tgt_obj is None:
            report_sink.Warning(f"  [OW] POS {src_guid[:8]} not found in source or target")
            return
        tgt_pre_props = target.POS.GetSyncableProperties(tgt_obj)
        src_props = _dedupe_custom_fields(
            source.POS.GetSyncableProperties(src_obj), tgt_pre_props
        )
        log = _resolve_decisions_for(overwrite, interactive_session)
        src_props, tagged, ow_skips = _resolve_and_tag(
            src_props, tgt_pre_props, tag, log,
            GrammarCategory.POS, overwrite.target_guid, tag.run_id,
        )
        target.POS.ApplySyncableProperties(tgt_obj, src_props)
        cache = getattr(target, "Cache")
        apply_residue(tgt_obj, cache.DefaultAnalWs, tagged)
        report_sink.Info(f"  POS overwritten  guid={src_guid}")
        return ow_skips

    if cat == GrammarCategory.AFFIX_TEMPLATES:
        src_tpl_wrap = _find_source_template_by_guid(source, src_guid)
        if src_tpl_wrap is None:
            report_sink.Warning(f"  [OW] Template {src_guid[:8]} vanished in source")
            return
        # owner_guid carries the POS GUID; if absent (early Phase 0 plans),
        # fall back to pulled_in_by[0].
        owner_pos_guid = getattr(overwrite, "owner_guid", "") or (
            overwrite.pulled_in_by[0] if overwrite.pulled_in_by else ""
        )
        if not owner_pos_guid:
            report_sink.Warning(f"  [OW] Template {src_guid[:8]} has no owner POS reference")
            return
        tgt_pos = _find_target_pos_by_guid(target, owner_pos_guid)
        if tgt_pos is None:
            report_sink.Warning(f"  [OW] Template owner POS {owner_pos_guid[:8]} not in target")
            return
        tgt_tpl = _find_target_template_by_guid(target, tgt_pos, tgt_guid)
        if tgt_tpl is None:
            report_sink.Warning(f"  [OW] Template {tgt_guid[:8]} not in target")
            return
        tgt_pre_props = target.MorphRules.GetSyncableProperties(tgt_tpl)
        src_props = source.MorphRules.GetSyncableProperties(src_tpl_wrap)
        target.MorphRules.ApplySyncableProperties(tgt_tpl, src_props)
        cache = getattr(target, "Cache")
        apply_residue(tgt_tpl, cache.DefaultAnalWs, tag.with_snapshot(tgt_pre_props))
        report_sink.Info(f"  Template overwritten  guid={src_guid}")
        return

    if cat == GrammarCategory.SLOTS:
        owner_pos_guid = getattr(overwrite, "owner_guid", "")
        tgt_pos = _find_target_pos_by_guid(target, owner_pos_guid) if owner_pos_guid else None
        tgt_slot = None
        if tgt_pos is not None:
            tgt_slot = _find_target_slot_by_guid(target, tgt_pos, tgt_guid)
        if tgt_slot is None:
            # Fallback: scan every POS's slots
            for pos in target.POS.GetAll(recursive=True):
                concrete = _unwrap(pos)
                for s in target.POS.GetAffixSlots(concrete):
                    if _guid_str(_unwrap(s)) == tgt_guid:
                        tgt_slot = _unwrap(s)
                        break
                if tgt_slot is not None:
                    break
        if tgt_slot is None:
            report_sink.Warning(f"  [OW] Slot {tgt_guid[:8]} not in target")
            return
        # Slot has no flexicon SyncableProperties wrapper exposed for it
        # via the MorphRules accessor on slots specifically; Phase 1.0 only
        # re-applies the residue tag here. Phase 1.1 will copy the slot
        # name + description via direct property access (Name multistring).
        cache = getattr(target, "Cache")
        apply_residue(tgt_slot, cache.DefaultAnalWs, tag)
        report_sink.Info(f"  Slot tagged (overwrite, no syncable props)  guid={src_guid}")
        return

    # ENTRY (Phase 0 verb-vertical) and the entry-shaped Phase 3c leaf
    # categories AFFIXES / STEMS (FR-338 / SC-302) share the identical
    # entry-level overwrite path — no category-specific merge code: the
    # same _dedupe_custom_fields + _resolve_and_tag generic helpers run for
    # all three, so per-field conflicts surface to Phase 2 uniformly.
    if cat in (GrammarCategory.ENTRY, GrammarCategory.AFFIXES, GrammarCategory.STEMS):
        from SIL.LCModel import ICmObject  # lazy
        tgt_entry = None
        for te in target.LexEntry.GetAll():
            if str(ICmObject(_unwrap(te)).Guid).lower() == tgt_guid:
                tgt_entry = _unwrap(te)
                break
        if tgt_entry is None:
            report_sink.Warning(f"  [OW] LexEntry {tgt_guid[:8]} not in target")
            return
        # Find the source entry to read its syncable properties.
        src_entry = None
        for se in source.LexEntry.GetAll():
            if str(ICmObject(_unwrap(se)).Guid).lower() == src_guid:
                src_entry = _unwrap(se)
                break
        if src_entry is None:
            report_sink.Warning(f"  [OW] Source LexEntry {src_guid[:8]} vanished")
            return
        tgt_pre_props = target.LexEntry.GetSyncableProperties(tgt_entry)
        src_props = _dedupe_custom_fields(
            source.LexEntry.GetSyncableProperties(src_entry), tgt_pre_props
        )
        log = _resolve_decisions_for(overwrite, interactive_session)
        src_props, tagged, ow_skips = _resolve_and_tag(
            src_props, tgt_pre_props, tag, log,
            cat, overwrite.target_guid, tag.run_id,
        )
        target.LexEntry.ApplySyncableProperties(tgt_entry, src_props)
        cache = getattr(target, "Cache")
        apply_residue(tgt_entry, cache.DefaultAnalWs, tagged)
        report_sink.Info(f"  LexEntry overwritten ({cat.value})  guid={src_guid}")
        return ow_skips

    if cat == GrammarCategory.SENSE:
        # owner_guid is the parent entry GUID; look up the entry first,
        # then iterate its senses.
        from SIL.LCModel import ICmObject  # lazy
        owner_entry_guid = getattr(overwrite, "owner_guid", "")
        if not owner_entry_guid:
            report_sink.Warning(f"  [OW] Sense {src_guid[:8]} has no owner entry reference")
            return
        tgt_entry = None
        for te in target.LexEntry.GetAll():
            if str(ICmObject(_unwrap(te)).Guid).lower() == owner_entry_guid:
                tgt_entry = _unwrap(te)
                break
        if tgt_entry is None:
            report_sink.Warning(f"  [OW] Sense owner entry {owner_entry_guid[:8]} not in target")
            return
        tgt_sense = None
        for s in target.LexEntry.GetSenses(tgt_entry):
            if str(ICmObject(_unwrap(s)).Guid).lower() == tgt_guid:
                tgt_sense = _unwrap(s)
                break
        if tgt_sense is None:
            report_sink.Warning(f"  [OW] LexSense {tgt_guid[:8]} not in target")
            return
        # Source-side lookup
        src_sense = None
        src_entry = None
        for se in source.LexEntry.GetAll():
            if str(ICmObject(_unwrap(se)).Guid).lower() == owner_entry_guid:
                src_entry = _unwrap(se)
                break
        if src_entry is not None:
            for s in source.LexEntry.GetSenses(src_entry):
                if str(ICmObject(_unwrap(s)).Guid).lower() == src_guid:
                    src_sense = _unwrap(s)
                    break
        if src_sense is None:
            report_sink.Warning(f"  [OW] Source LexSense {src_guid[:8]} vanished")
            return
        tgt_pre_props = target.Senses.GetSyncableProperties(tgt_sense)
        src_props = _dedupe_custom_fields(
            source.Senses.GetSyncableProperties(src_sense), tgt_pre_props
        )
        log = _resolve_decisions_for(overwrite, interactive_session)
        src_props, tagged, ow_skips = _resolve_and_tag(
            src_props, tgt_pre_props, tag, log,
            GrammarCategory.SENSE, overwrite.target_guid, tag.run_id,
        )
        target.Senses.ApplySyncableProperties(tgt_sense, src_props)
        cache = getattr(target, "Cache")
        apply_residue(tgt_sense, cache.DefaultAnalWs, tagged)
        report_sink.Info(f"  LexSense overwritten  guid={src_guid}")
        return ow_skips

    if cat == GrammarCategory.MSA:
        from SIL.LCModel import ICmObject, ILexEntry, IMoInflAffMsa
        owner_entry_guid = getattr(overwrite, "owner_guid", "")
        if not owner_entry_guid:
            report_sink.Warning(f"  [OW] MSA {src_guid[:8]} has no owner entry reference")
            return
        # Locate target entry, then the target MSA on its MorphoSyntaxAnalysesOC.
        tgt_entry = None
        for te in target.LexEntry.GetAll():
            if str(ICmObject(_unwrap(te)).Guid).lower() == owner_entry_guid:
                tgt_entry = _unwrap(te)
                break
        if tgt_entry is None:
            report_sink.Warning(f"  [OW] MSA owner entry {owner_entry_guid[:8]} not in target")
            return
        tgt_msa = None
        for tmsa in ILexEntry(tgt_entry).MorphoSyntaxAnalysesOC:
            if str(ICmObject(tmsa).Guid).lower() == tgt_guid:
                tgt_msa = tmsa
                break
        if tgt_msa is None:
            report_sink.Warning(f"  [OW] Target MSA {tgt_guid[:8]} not found")
            return
        # Re-sync SlotsRC (slot membership may have shifted). Source MSA
        # lookup mirrors the planner's: find source entry, then matching MSA.
        src_entry = None
        for se in source.LexEntry.GetAll():
            if str(ICmObject(_unwrap(se)).Guid).lower() == owner_entry_guid:
                src_entry = _unwrap(se)
                break
        src_msa = None
        if src_entry is not None:
            for smsa in ILexEntry(src_entry).MorphoSyntaxAnalysesOC:
                if str(ICmObject(smsa).Guid).lower() == src_guid:
                    src_msa = smsa
                    break
        # Pre-overwrite snapshot: target's current SlotsRC + PartOfSpeechRA
        tgt_pre_props = {
            "slots": sorted(str(ICmObject(sl).Guid).lower()
                            for sl in IMoInflAffMsa(tgt_msa).SlotsRC),
            "pos": (str(ICmObject(IMoInflAffMsa(tgt_msa).PartOfSpeechRA).Guid).lower()
                    if IMoInflAffMsa(tgt_msa).PartOfSpeechRA is not None else None),
        }
        if src_msa is not None:
            src_ia = IMoInflAffMsa(src_msa)
            new_ia = IMoInflAffMsa(tgt_msa)
            # Build target slot index for the owner POS once
            from SIL.LCModel import IPartOfSpeech
            pos_obj = src_ia.PartOfSpeechRA
            if pos_obj is not None:
                pos_guid = str(ICmObject(pos_obj).Guid).lower()
                tgt_pos = _find_target_pos_by_guid(target, pos_guid)
                if tgt_pos is not None:
                    target_slots_by_guid = {}
                    for sl in target.POS.GetAffixSlots(tgt_pos):
                        target_slots_by_guid[_guid_str(_unwrap(sl))] = _unwrap(sl)
                    # Clear + re-add the slot refs from source
                    new_ia.SlotsRC.Clear()
                    for src_slot in src_ia.SlotsRC:
                        src_slot_guid = str(ICmObject(src_slot).Guid).lower()
                        tgt_slot = target_slots_by_guid.get(src_slot_guid)
                        if tgt_slot is not None:
                            new_ia.SlotsRC.Add(tgt_slot)
        cache = getattr(target, "Cache")
        apply_residue(tgt_msa, cache.DefaultAnalWs, tag.with_snapshot(tgt_pre_props))
        report_sink.Info(f"  IMoInflAffMsa overwritten  src={src_guid[:8]}  tgt={tgt_guid[:8]}")
        return

    if cat == GrammarCategory.ALLOMORPH:
        from SIL.LCModel import ICmObject, IMoAffixAllomorph
        owner_entry_guid = getattr(overwrite, "owner_guid", "")
        if not owner_entry_guid:
            report_sink.Warning(f"  [OW] Allomorph {src_guid[:8]} has no owner entry reference")
            return
        tgt_entry = None
        for te in target.LexEntry.GetAll():
            if str(ICmObject(_unwrap(te)).Guid).lower() == owner_entry_guid:
                tgt_entry = _unwrap(te)
                break
        if tgt_entry is None:
            report_sink.Warning(f"  [OW] Allomorph owner entry {owner_entry_guid[:8]} not in target")
            return
        tgt_allo = None
        for tallo in target.Allomorphs.GetAll(tgt_entry):
            if _guid_str(_unwrap(tallo)) == tgt_guid:
                tgt_allo = _unwrap(tallo)
                break
        if tgt_allo is None:
            report_sink.Warning(f"  [OW] Target allomorph {tgt_guid[:8]} not found")
            return
        # Source-side lookup for ApplySyncableProperties
        src_entry = None
        for se in source.LexEntry.GetAll():
            if str(ICmObject(_unwrap(se)).Guid).lower() == owner_entry_guid:
                src_entry = _unwrap(se)
                break
        src_allo = None
        if src_entry is not None:
            for sallo in source.Allomorphs.GetAll(src_entry):
                if _guid_str(_unwrap(sallo)) == src_guid:
                    src_allo = _unwrap(sallo)
                    break
        tgt_pre_props = target.Allomorphs.GetSyncableProperties(tgt_allo)
        ow_skips = []
        tagged = tag.with_snapshot(tgt_pre_props)
        if src_allo is not None:
            src_props = _dedupe_custom_fields(
                source.Allomorphs.GetSyncableProperties(src_allo), tgt_pre_props
            )
            log = _resolve_decisions_for(overwrite, interactive_session)
            src_props, tagged, ow_skips = _resolve_and_tag(
                src_props, tgt_pre_props, tag, log,
                GrammarCategory.ALLOMORPH, overwrite.target_guid, tag.run_id,
            )
            target.Allomorphs.ApplySyncableProperties(tgt_allo, src_props)
        cache = getattr(target, "Cache")
        apply_residue(tgt_allo, cache.DefaultAnalWs, tagged)
        report_sink.Info(f"  IMoAffixAllomorph overwritten  src={src_guid[:8]}  tgt={tgt_guid[:8]}")
        return ow_skips

    if cat == GrammarCategory.PH_ENVIRONMENT:
        tgt_env = _find_target_env_by_guid(target, tgt_guid)
        if tgt_env is None:
            report_sink.Warning(f"  [OW] PhEnvironment {tgt_guid[:8]} not in target")
            return
        src_env = None
        try:
            for e in source.Environments.GetAll():
                if _guid_str(_unwrap(e)) == src_guid:
                    src_env = _unwrap(e)
                    break
        except AttributeError:
            pass
        tgt_pre_props = {}
        try:
            tgt_pre_props = target.Environments.GetSyncableProperties(tgt_env)
        except AttributeError:
            pass
        if src_env is not None:
            try:
                src_props = source.Environments.GetSyncableProperties(src_env)
                target.Environments.ApplySyncableProperties(tgt_env, src_props)
            except AttributeError:
                pass
        cache = getattr(target, "Cache")
        apply_residue(tgt_env, cache.DefaultAnalWs, tag.with_snapshot(tgt_pre_props))
        report_sink.Info(f"  PhEnvironment overwritten  guid={src_guid}")
        return

    # For other categories, Phase 1 just logs and skips the apply — the
    # extension lands as categories.py exposes ApplySyncableProperties for
    # each. The residue tag is still applied below for audit.
    report_sink.Info(f"  [OW] {cat.value} overwrite no-op  guid={src_guid}")

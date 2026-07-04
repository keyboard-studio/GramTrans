"""Phase 2 — per-field conflict detection and resolution.

This module is the seam between the Preview-phase planner
(`Lib/preview.py`) and the user-interactive resolver
(`Lib/ui/conflict_dialog.py` in production, FakeConflictResolver in
tests).  Per constitution Principle III (Preview-Before-Mutate), every
ConflictPrompt is produced during planning, BEFORE any LCM mutation.

Public surface:
- `UserCancelled`: raised by `ConflictResolver.resolve` if the user
  dismisses the dialog. The caller MUST catch this and exit before any
  `transfer.execute()` call.
- `ConflictResolver`: Protocol — the interactive prompt's contract.
  Production impl: `Lib/ui/conflict_dialog.py.ConflictDialog`.
- `detect_conflicts(...)`: producer (T017, Phase 3 / US1).
- `_deterministic_merge(...)`: research.md R4 (T018, US1).
- `load_prior_decision(...)`: US3 prior-run recall (T040).
"""
from __future__ import annotations

from typing import Optional, Protocol

if __package__:
    from .models import (
        ConflictPrompt,
        MergeDecision,
        MergeDecisionLog,
        MergeResolution,
    )
else:
    from models import (
        ConflictPrompt,
        MergeDecision,
        MergeDecisionLog,
        MergeResolution,
    )


# Property-name patterns that are NEVER merge-eligible (scalar fields
# whose "merge" semantics are not defined: ints, bools, GUID refs).
# When detected, the ConflictPrompt is emitted with merge_eligible=False
# and the UI hides the MERGE button -- only TAKE_SOURCE / KEEP_TARGET /
# SKIP / EDIT_CUSTOM remain.
_NON_MERGEABLE_TYPES = (int, bool, type(None))


class UserCancelled(Exception):
    """The user dismissed an interactive dialog without completing it.

    Phase 2 (FR-213) requires this to be raised by ConflictResolver /
    WSResolver implementations.  The outermost MainFunction catches it
    and returns before any transfer.execute() call, so the target
    project is left bit-identical.
    """


class ConflictResolver(Protocol):
    """Production: PyQt ConflictDialog.  Tests: FakeConflictResolver.

    The protocol is structural -- any object exposing a compatible
    `resolve(...)` method satisfies it.  No runtime check is performed.
    """

    def resolve(self, prompts):
        """Block until the user has answered every prompt.

        Args:
            prompts: tuple[ConflictPrompt, ...].

        Returns:
            tuple[MergeDecision, ...] of the same length and order.

        Raises:
            UserCancelled: if the user dismisses the dialog.
        """
        ...


# ============================================================================
# T017 -- detect_conflicts: produce ConflictPrompt list from a (src, tgt) pair
# ============================================================================

def _is_merge_eligible(value) -> bool:
    """research.md R4: scalars (int/bool/None) are NOT merge-eligible.
    Strings, lists, tuples, sets, dicts (multistrings live as dicts of
    ws_handle -> str), and arbitrary objects with __eq__ are eligible.
    """
    return not isinstance(value, _NON_MERGEABLE_TYPES)


def detect_conflicts(
    src_props,
    tgt_pre_props,
    target_guid: str,
    target_class_name: str,
    prior_log: Optional[MergeDecisionLog] = None,
):
    """Produce a ConflictPrompt tuple from a source/target syncable-props pair.

    Per FR-216 / contracts/conflict-prompt.md:
    - Iterate the INTERSECTION of keys (a key present only on one side
      is not a conflict; Phase 1's source-wins or target-preserved
      applies automatically).
    - Suppress identical-valued pairs (structural equality).
    - For surviving conflicts, attach `prior_log`'s matching decision
      as `prior_decision` when present (US3 recall).
    - Determine `merge_eligible` per type.
    - Return tuple ordered alphabetically by `field_name`.

    Args:
        src_props: dict of source's syncable properties.
        tgt_pre_props: dict of target's pre-overwrite syncable properties.
        target_guid: target object's GUID (string).
        target_class_name: target's LCM ClassName.
        prior_log: optional MergeDecisionLog from a prior run's residue.

    Returns:
        tuple[ConflictPrompt, ...] sorted by field_name.
    """
    if not isinstance(src_props, dict) or not isinstance(tgt_pre_props, dict):
        return ()
    # Build prior-decision lookup once.
    prior_by_field = {}
    if prior_log is not None:
        for d in prior_log.decisions:
            prior_by_field[d.field_name] = d
    prompts = []
    for key in sorted(set(src_props) & set(tgt_pre_props)):
        right = src_props[key]
        left = tgt_pre_props[key]
        if left == right:
            continue  # FR-216: identical -> no prompt
        prompts.append(
            ConflictPrompt(
                target_guid=target_guid,
                target_class_name=target_class_name,
                field_name=key,
                left_value=left,
                right_value=right,
                prior_decision=prior_by_field.get(key),
                merge_eligible=_is_merge_eligible(left) and _is_merge_eligible(right),
            )
        )
    return tuple(prompts)


# ============================================================================
# T018 -- _deterministic_merge: research.md R4 semantics
# ============================================================================

class _MergeNotEligible(Exception):
    """Raised when callers try to merge two scalars."""


def _deterministic_merge(left, right, run_id: str):
    """research.md R4 deterministic merge semantics:

    - str: <left>\\n--- merged GT-<run_id> ---\\n<right>
    - dict (multistring-shaped: {ws_handle: str}): recurse per-key,
      passing through left/right slots when only one side has them.
    - list / tuple / set: set-union preserving left order followed by
      right-only entries.
    - int / bool / None: not eligible -> raise _MergeNotEligible.

    Args:
        left: target's pre-overwrite value.
        right: source's value.
        run_id: GT-YYYYMMDD-HHMMSS run id, embedded in the separator.

    Returns:
        The merged value of the same type as the inputs.

    Raises:
        _MergeNotEligible: if either side is a scalar (int/bool/None).
    """
    if isinstance(left, _NON_MERGEABLE_TYPES) or isinstance(right, _NON_MERGEABLE_TYPES):
        raise _MergeNotEligible(
            f"cannot merge scalar values: left={type(left).__name__} "
            f"right={type(right).__name__}"
        )
    if isinstance(left, str) and isinstance(right, str):
        return f"{left}\n--- merged {run_id} ---\n{right}"
    if isinstance(left, dict) and isinstance(right, dict):
        out = {}
        for k in sorted(set(left) | set(right)):
            if k in left and k in right:
                out[k] = _deterministic_merge(left[k], right[k], run_id)
            elif k in left:
                out[k] = left[k]
            else:
                out[k] = right[k]
        return out
    if isinstance(left, (list, tuple, set, frozenset)) and isinstance(
        right, (list, tuple, set, frozenset)
    ):
        seen = set()
        out_list = []
        for item in list(left) + list(right):
            try:
                key = item
                if key in seen:
                    continue
                seen.add(key)
            except TypeError:
                # Unhashable item -- fall back to linear search.
                if item in out_list:
                    continue
            out_list.append(item)
        if isinstance(left, tuple):
            return tuple(out_list)
        if isinstance(left, (set, frozenset)):
            return type(left)(out_list)
        return out_list
    # Mixed types -- last resort: stringify and concat.
    return f"{left!r}\n--- merged {run_id} ---\n{right!r}"


# ============================================================================
# Conflict-collection helper used by MainFunction (US1 wiring)
# ============================================================================
# Per research.md R1, the planner does not itself capture tgt_pre_props
# (which would double the LCM read for every overwritten object).
# Instead, MainFunction calls this helper after build_run_plan to walk
# plan.overwrites once, capture pre-props + src_props for each, and emit
# ConflictPrompts.  The resolver then runs once on the whole tuple; the
# resolution is folded into an InteractiveSession that execute() consumes.

# Mapping from GrammarCategory.value to the Operations attribute pair
# (source-side accessor, target-side accessor, target-object lookup
# function name) used to fetch syncable properties.  For categories that
# don't have a simple ApplySyncableProperties surface (Templates / Slots /
# MSAs / PhEnvironments), we fall back to None and skip conflict detection.
_OW_OPS = {
    "pos":       ("POS",       "POS",       "_find_target_pos_by_guid"),
    "entry":     ("LexEntry",  "LexEntry",  "_find_target_entry_by_guid"),
    "sense":     ("Senses",    "Senses",    "_find_target_sense_by_guid"),
    "allomorph": ("Allomorphs", "Allomorphs", "_find_target_allo_by_guid"),
}


def _unwrap(obj):
    """flexicon sometimes returns wrapper objects with a .concrete attr
    holding the underlying LCM interface; unwrap before any ICmObject cast.
    Mirrors transfer.py._unwrap."""
    return obj.concrete if hasattr(obj, "concrete") else obj


def _find_target_entry_by_guid(target, guid):
    from SIL.LCModel import ICmObject  # lazy
    for te in target.LexEntry.GetAll():
        concrete = _unwrap(te)
        if str(ICmObject(concrete).Guid).lower() == guid.lower():
            return concrete
    return None


def _find_target_sense_by_guid(target, guid, owner_entry_guid=""):
    from SIL.LCModel import ICmObject  # lazy
    entry = _find_target_entry_by_guid(target, owner_entry_guid) if owner_entry_guid else None
    if entry is not None:
        for s in target.LexEntry.GetSenses(entry):
            concrete = _unwrap(s)
            if str(ICmObject(concrete).Guid).lower() == guid.lower():
                return concrete
    return None


def _find_target_allo_by_guid(target, guid, owner_entry_guid=""):
    from SIL.LCModel import ICmObject  # lazy
    entry = _find_target_entry_by_guid(target, owner_entry_guid) if owner_entry_guid else None
    if entry is not None:
        for a in target.Allomorphs.GetAll(entry):
            concrete = _unwrap(a)
            if str(ICmObject(concrete).Guid).lower() == guid.lower():
                return concrete
    return None


def _find_target_pos_by_guid(target, guid):
    from SIL.LCModel import ICmObject  # lazy
    for p in target.POS.GetAll(recursive=True):
        concrete = _unwrap(p)
        if str(ICmObject(concrete).Guid).lower() == guid.lower():
            return concrete
    return None


def collect_overwrite_conflicts(plan, source, target, prior_logs_by_guid=None):
    """Walk plan.overwrites; for every category whose ops surface supports
    GetSyncableProperties, capture src_props + tgt_pre_props and call
    detect_conflicts.  Returns a flat tuple of ConflictPrompt across all
    overwrites.

    `prior_logs_by_guid` (US3 recall): optional dict[str -> MergeDecisionLog]
    threaded into detect_conflicts per object.

    NOTE: this helper is for caller-side MVP collection BEFORE execute()
    runs.  It performs LCM reads but no writes; safe to call during
    Preview phase or just before Move (the user prompt happens between
    this call and execute()).
    """
    prior_logs_by_guid = prior_logs_by_guid or {}
    prompts = []
    # Build source-entry index once for entry/sense/allomorph lookups.
    src_entry_by_guid = {}
    try:
        from SIL.LCModel import ICmObject
        for se in source.LexEntry.GetAll():
            concrete = _unwrap(se)
            src_entry_by_guid[str(ICmObject(concrete).Guid).lower()] = concrete
    except (AttributeError, ImportError):
        # Outside FlexTools host -- caller is presumably running unit tests
        # with mocked source/target.  Bail.
        return ()
    for ow in getattr(plan, "overwrites", ()):
        cat = ow.category.value
        ops_info = _OW_OPS.get(cat)
        if ops_info is None:
            continue
        src_ops_name, tgt_ops_name, finder_name = ops_info
        src_ops = getattr(source, src_ops_name, None)
        tgt_ops = getattr(target, tgt_ops_name, None)
        if src_ops is None or tgt_ops is None:
            continue
        finder = globals().get(finder_name)
        if finder is None:
            continue
        # Look up source object.
        try:
            from SIL.LCModel import ICmObject
        except ImportError:
            continue
        if cat == "pos":
            tgt_obj = finder(target, ow.target_guid)
            src_obj = None
            for p in source.POS.GetAll(recursive=True):
                concrete = _unwrap(p)
                if str(ICmObject(concrete).Guid).lower() == ow.source_guid.lower():
                    src_obj = concrete
                    break
        elif cat == "entry":
            tgt_obj = finder(target, ow.target_guid)
            src_obj = src_entry_by_guid.get(ow.source_guid.lower())
        elif cat == "sense":
            tgt_obj = finder(target, ow.target_guid, ow.owner_guid)
            src_entry = src_entry_by_guid.get(ow.owner_guid.lower())
            src_obj = None
            if src_entry is not None:
                for s in source.LexEntry.GetSenses(src_entry):
                    concrete = _unwrap(s)
                    if str(ICmObject(concrete).Guid).lower() == ow.source_guid.lower():
                        src_obj = concrete
                        break
        elif cat == "allomorph":
            tgt_obj = finder(target, ow.target_guid, ow.owner_guid)
            src_entry = src_entry_by_guid.get(ow.owner_guid.lower())
            src_obj = None
            if src_entry is not None:
                for a in source.Allomorphs.GetAll(src_entry):
                    concrete = _unwrap(a)
                    if str(ICmObject(concrete).Guid).lower() == ow.source_guid.lower():
                        src_obj = concrete
                        break
        else:
            continue
        if src_obj is None or tgt_obj is None:
            continue
        try:
            src_props = src_ops.GetSyncableProperties(src_obj)
            tgt_pre_props = tgt_ops.GetSyncableProperties(tgt_obj)
        except (AttributeError, TypeError):
            continue
        prior_log = prior_logs_by_guid.get(ow.target_guid)
        for p in detect_conflicts(
            src_props=src_props,
            tgt_pre_props=tgt_pre_props,
            target_guid=ow.target_guid,
            target_class_name=cat,
            prior_log=prior_log,
        ):
            prompts.append(p)
    return tuple(prompts)


def load_prior_log(tgt_object):
    """T040 / US3 -- read the target object's residue tag and recover the
    MergeDecisionLog from its `merge=` segment, or None if absent /
    unparseable.

    Per FR-215 graceful degradation: a corrupted tag returns None so
    the caller falls back to fresh-prompt behaviour for that field.

    Args:
        tgt_object: an LCM object exposing `LiftResidue` (str-typed on
            ILexEntry / IMoAffixAllomorph / IMoInflAffMsa per Phase 1.3c)
            or `Description` (multistring on Carrier-B objects).

    Returns:
        MergeDecisionLog or None.
    """
    if __package__:
        from .residue import ImportResidueTag
    else:
        from residue import ImportResidueTag
    if tgt_object is None:
        return None
    # Try LiftResidue first (Carrier A); fall back to Description (Carrier B).
    lift = getattr(tgt_object, "LiftResidue", None)
    text = None
    if isinstance(lift, str) and lift:
        text = lift
    elif lift is not None and hasattr(lift, "get_String"):
        # Multistring LiftResidue: pull best-available text.
        try:
            ts = lift.BestAnalysisAlternative
            text = (ts.Text or "") if ts is not None else ""
        except (AttributeError, TypeError):
            text = ""
    if not text:
        desc = getattr(tgt_object, "Description", None)
        if desc is not None:
            try:
                ts = desc.BestAnalysisAlternative
                text = (ts.Text or "") if ts is not None else ""
            except (AttributeError, TypeError):
                text = ""
    if not text:
        return None
    tag = ImportResidueTag.parse(text)
    if tag is None:
        return None
    return tag.decode_merge_log()


def load_prior_decision(tgt_object, field_name: str):
    """T040 / US3 -- recover the prior-run MergeDecision for `field_name`
    on `tgt_object`, or None if absent.

    Convenience wrapper around `load_prior_log` for callers that want a
    per-field lookup.
    """
    log = load_prior_log(tgt_object)
    if log is None:
        return None
    for d in log.decisions:
        if d.field_name == field_name:
            return d
    return None


def build_session_from_resolutions(prompts, decisions):
    """Helper: given a tuple of ConflictPrompts and the matching tuple of
    MergeDecisions returned by a ConflictResolver, build an
    InteractiveSession with merge_decisions_by_guid populated.

    Args:
        prompts: tuple[ConflictPrompt, ...] -- the input the resolver received.
        decisions: tuple[MergeDecision, ...] -- same length, same order.

    Returns:
        InteractiveSession.

    Raises:
        ValueError: if lengths differ.
    """
    if __package__:
        from .models import InteractiveSession
    else:
        from models import InteractiveSession
    if len(prompts) != len(decisions):
        raise ValueError(
            f"prompts/decisions length mismatch: {len(prompts)} vs {len(decisions)}"
        )
    decisions_by_guid = {}
    for p, d in zip(prompts, decisions):
        log = decisions_by_guid.setdefault(p.target_guid, [])
        log.append(d)
    # Build MergeDecisionLog per target_guid.
    if __package__:
        from .models import MergeDecisionLog
    else:
        from models import MergeDecisionLog
    out = {
        guid: MergeDecisionLog(target_guid=guid, decisions=tuple(decs))
        for guid, decs in decisions_by_guid.items()
    }
    return InteractiveSession(merge_decisions_by_guid=out)

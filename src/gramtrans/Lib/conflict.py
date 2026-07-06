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


# ============================================================================
# 022-disposition-model: per-item disposition computation (T015-T017, T020-T022)
# ============================================================================

import enum as _enum


class ItemDisposition(_enum.Enum):
    """Per-item outcome computed during the Preview / plan phase (022 FR-005).

    IGNORE   : item was never selected by the user; it never enters the plan.
    SKIP     : selected, present in target, all user-editable fields in sync
               (2-way: source == target; or 3-way: baseline unchanged too).
               No write occurs.
    ADD      : not present in target; will be added regardless of intent.
    UPDATE   : present; >=1 diverged field; UPDATE intent governs write
               (non-destructive: source wins where diverged, preserves where
               source is empty).
    OVERWRITE: present; >=1 diverged field; OVERWRITE intent governs write
               (destructive: source wins unconditionally, may blank target).
    """
    IGNORE = "ignore"
    SKIP = "skip"
    ADD = "add"
    UPDATE = "update"
    OVERWRITE = "overwrite"


def _is_empty(value) -> bool:
    """Return True if `value` is semantically empty for UPDATE skip-write decisions.

    Empty means:
    - None
    - str: empty or whitespace-only, OR the flexicon empty-sentinel "***" (after
      strip).  A value that strips to "***" is treated as unset (FR-003 P1-1/P1-2).
    - dict (multistring): empty dict, OR every value is itself _is_empty (all-empty
      multistring like {"en":"","fr":""} must be treated as empty — P1-1).
    - list/tuple/set/frozenset: zero-length.
    Non-empty scalars (int 0, bool False) are considered non-empty because they
    carry intentional data.
    """
    _EMPTY_SENTINEL = "***"
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return stripped == "" or stripped == _EMPTY_SENTINEL
    if isinstance(value, dict):
        if len(value) == 0:
            return True
        # Multistring: empty iff every value is itself empty (P1-1).
        return all(_is_empty(v) for v in value.values())
    if isinstance(value, (list, tuple, set, frozenset)):
        return len(value) == 0
    return False


def compute_field_diff(src_props: dict, tgt_props: dict) -> dict:
    """Return a dict of {field_name: (src_value, tgt_value)} for fields that differ.

    Only keys present in BOTH dicts are compared (intersection).  A key absent
    from one side is not a conflict (source-wins or target-preserved by caller).
    """
    if not isinstance(src_props, dict) or not isinstance(tgt_props, dict):
        return {}
    diff = {}
    for key in sorted(set(src_props) & set(tgt_props)):
        if src_props[key] != tgt_props[key]:
            diff[key] = (src_props[key], tgt_props[key])
    return diff


def compute_disposition(
    src_props,
    tgt_props,
    intent,
    prior_baseline=None,
) -> "ItemDisposition":
    """Compute the per-item ItemDisposition (022 FR-005, T015, T020, T022).

    Args:
        src_props: dict of source's syncable properties (or None if item is
            new / not-yet-fetched).  None -> ADD.
        tgt_props: dict of target's syncable properties.  None -> ADD (not
            present in target).
        intent: ConflictMode — the user's chosen transfer intent for the
            category (LINK / UPDATE / OVERWRITE / ADD_NEW).
        prior_baseline: optional dict of the target's props at the time of the
            PRIOR run (from residue snapshot).  When provided, enables 3-way
            comparison: a field that matches *both* the baseline and the current
            target is "untouched" and contributes no divergence (auto-SKIP).
            When absent, 2-way comparison only (first-run behaviour, T022).

    Returns:
        ItemDisposition.

    Note: IGNORE is NOT computed here -- IGNORE is the disposition for items
    that were never selected and thus never enter the plan.  Callers that
    enumerate unselected items must assign IGNORE themselves.
    """
    # Lazy import to avoid a top-level circular dependency.
    if __package__:
        from .models import ConflictMode as _ConflictMode
    else:
        from models import ConflictMode as _ConflictMode  # type: ignore

    # Item not present in target -> ADD (regardless of intent).
    if tgt_props is None or src_props is None:
        return ItemDisposition.ADD

    # Compute effective diff.
    if prior_baseline is not None:
        # 3-way: suppress fields where target matches baseline (untouched, T020).
        # A field is "diverged" only if it changed since the prior run in the
        # source direction, i.e. src != tgt AND (tgt changed since baseline OR
        # src changed since baseline).  Simplest safe interpretation: exclude
        # fields where tgt == baseline (no change in target since last run).
        raw_diff = compute_field_diff(src_props, tgt_props)
        diff = {
            k: v
            for k, v in raw_diff.items()
            if prior_baseline.get(k) != tgt_props.get(k)  # target drifted from baseline
            or src_props.get(k) != prior_baseline.get(k)   # source changed since baseline
        }
    else:
        # 2-way: any src != tgt is diverged (first-run behaviour, T022).
        diff = compute_field_diff(src_props, tgt_props)

    if not diff:
        # Zero diverged fields -> SKIP (no write needed).
        return ItemDisposition.SKIP

    # >=1 diverged field: disposition follows intent.
    if intent in (_ConflictMode.LINK, _ConflictMode.ADD_NEW):
        # LINK / ADD_NEW: no field-level writes to existing items -> SKIP
        # (the item IS present; LINK writes nothing to it).
        return ItemDisposition.SKIP
    if intent == _ConflictMode.UPDATE:
        return ItemDisposition.UPDATE
    if intent == _ConflictMode.OVERWRITE:
        return ItemDisposition.OVERWRITE
    # Unknown intent: conservative SKIP.
    return ItemDisposition.SKIP


def apply_update_semantic(src_props: dict, tgt_props: dict, ops, tgt_obj) -> int:
    """Apply the non-destructive UPDATE write semantic (022 FR-003, T011).

    Iterates the syncable-property keys present in both src_props and tgt_props.
    For each key:
    - If the source value is empty (None / "" / {} / []) -> SKIP write (never
      blank a target field from an empty source).
    - Otherwise write the source value to the target field via
      ``ops.ApplySyncableProperties(tgt_obj, {key: src_value})``.

    Args:
        src_props: dict returned by GetSyncableProperties on the source object.
        tgt_props: dict returned by GetSyncableProperties on the target object.
        ops: the Operations instance (must expose ApplySyncableProperties).
        tgt_obj: the target LCM object to write to.

    Returns:
        int: number of fields written (0 if all-identical or all-empty-source).
    """
    written = 0
    for key in sorted(set(src_props) & set(tgt_props)):
        src_val = src_props[key]
        tgt_val = tgt_props[key]
        if src_val == tgt_val:
            continue  # identical -> skip
        if _is_empty(src_val):
            continue  # non-destructive: never blank from empty source
        # Source differs and is non-empty -> write.
        try:
            ops.ApplySyncableProperties(tgt_obj, {key: src_val})
            written += 1
        except (AttributeError, TypeError):
            pass  # best-effort; caller's error handling covers the rest
    return written


# ============================================================================
# 022 T014: Flexicon version gate for Phoneme/Environment field-diff promotion
# ============================================================================

# When pyflexicon ships the ITsString.get_String guard fix for
# EnvironmentOperations (~:694-698) and PhonemeOperations (~:1309-1319),
# bump this constant to the fix release version.
# TODO(Ruling-Y): update _FLEXICON_ITSTRING_FIX_VERSION when the
# flexicon ITsString.get_String patch ships.
_FLEXICON_ITSTRING_FIX_VERSION = "999.0.0"  # placeholder; no fix yet


def _phoneme_env_field_diff_enabled() -> bool:
    """Return True if the installed pyflexicon version supports
    GetSyncableProperties on Phoneme and PH_ENVIRONMENT objects without
    the ITsString.get_String defect (022 T014 / Ruling Y).

    Until the fix ships, Phoneme and PH_ENVIRONMENT stay SELECTOR-ONLY
    (Tier C).  When the fix ships, update _FLEXICON_ITSTRING_FIX_VERSION.
    """
    try:
        import importlib.metadata as _meta
        installed = _meta.version("pyflexicon")
        from packaging.version import Version
        return Version(installed) >= Version(_FLEXICON_ITSTRING_FIX_VERSION)
    except Exception:
        return False  # fail-closed: stay SELECTOR-ONLY if version unreadable

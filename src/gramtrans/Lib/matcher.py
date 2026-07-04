"""Phase 1 match-by-GUID-first / fingerprint-fallback lookup.

Pure-Python module. No LCM / flexicon imports at module level; all LCM
surface is injected by the caller (target project handle, source object,
fingerprint functions) so this module is fully testable without an LCM host.

Public surface
--------------
Match              frozen dataclass returned by lookup_target()
lookup_target()    FR-102 / FR-103 / FR-104 three-step matcher
FINGERPRINT_FNS    per-category registry: GrammarCategory -> callable
fingerprint_for_msa(msa, ws_handle=None) -> Tuple
fingerprint_for_allomorph(allo, ws_handle=None) -> Tuple

Fingerprint definitions per FR-104.

lookup_target() contract
------------------------
The caller passes both the *source* object (so the source fingerprint can be
computed) and the *target* project handle (so target objects can be iterated).
Step 3 computes the source fingerprint once, then iterates target objects in the
same category computing each one's fingerprint; first equality wins.

Target project protocol (duck-typed, no import required)
---------------------------------------------------------
The `target` argument must expose at least one of:

    target.get_object_by_guid(guid: str, category: GrammarCategory) -> obj | None
        O(1) indexed lookup. Preferred when available.

    target.iter_objects(category: GrammarCategory) -> Iterable[obj]
        Linear scan fallback. Each `obj` must have a `.Guid` attribute whose
        str() gives the GUID string.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

_log = logging.getLogger(__name__)

if __package__:
    from .models import GrammarCategory
else:
    from models import GrammarCategory  # loaded via site.addsitedir("Lib")


# ---------------------------------------------------------------------------
# Match result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Match:
    """Result of a lookup_target() call.

    Attributes:
        source_guid:     GUID of the source object being matched.
        target_obj:      The LCM object found in the target, or None when
                         via == "none".
        via:             Which path produced the match:
                           "guid"           - direct GUID lookup
                           "identity_remap" - hit via prior-run remap dict
                           "fingerprint"    - hit via per-category fingerprint
                           "none"           - no match; item is an Add
        fingerprint_key: Computed fingerprint tuple when via=="fingerprint";
                         None otherwise.
    """
    source_guid: str
    target_obj: object  # LCM object or None
    via: str            # "guid" | "identity_remap" | "fingerprint" | "none"
    fingerprint_key: Optional[Tuple] = None

    _VALID_VIA = frozenset({"guid", "identity_remap", "fingerprint", "none"})

    def __post_init__(self) -> None:
        if self.via not in self._VALID_VIA:
            raise ValueError(
                f"Match.via must be one of {self._VALID_VIA!r}, got {self.via!r}"
            )
        if self.via == "none" and self.target_obj is not None:
            raise ValueError("Match.via='none' requires target_obj=None")
        if self.via != "fingerprint" and self.fingerprint_key is not None:
            raise ValueError(
                "fingerprint_key must be None when via != 'fingerprint'"
            )
        if self.via == "fingerprint" and self.fingerprint_key is None:
            raise ValueError(
                "fingerprint_key must be set when via == 'fingerprint'"
            )


# ---------------------------------------------------------------------------
# Fingerprint functions (FR-104)
# ---------------------------------------------------------------------------

def fingerprint_for_msa(msa, ws_handle=None) -> Tuple:
    """Fingerprint for IMoInflAffMsa (FR-104).

    Returns:
        (GrammarCategory.MSA,
         owner_entry_guid: str,
         "MoInflAffMsa",
         pos_guid: str,
         frozenset(slot_guids))

    owner_entry_guid: GUID string of the owning ILexEntry, "" if unavailable.
    pos_guid:         GUID string of PartOfSpeechRA, "" if unset.
    slot_guids:       frozenset of GUID strings from SlotsRC.

    ws_handle is accepted for API symmetry but not used; MSA identity is
    language-independent.
    """
    try:
        if msa.Owner is not None:
            owner_class = type(msa.Owner).__name__
            if owner_class not in ("LexEntry", "ILexEntry"):
                _log.warning(
                    "fingerprint_for_msa: .Owner is %s (expected LexEntry), "
                    "msa GUID=%s; fingerprint owner_guid may be wrong. "
                    "Affix MSA path is unverified -- check ownership.",
                    owner_class,
                    getattr(msa, "Guid", "?"),
                )
                owner_guid = str(getattr(msa.Owner, "Guid", "") or "")
            else:
                owner_guid = str(msa.Owner.Guid)
        else:
            owner_guid = ""
    except AttributeError:
        owner_guid = ""

    try:
        pos_guid = (
            str(msa.PartOfSpeechRA.Guid)
            if msa.PartOfSpeechRA is not None
            else ""
        )
    except AttributeError:
        pos_guid = ""

    try:
        # ILcmReferenceCollection: iterate directly, never use ElementAt()
        slot_guids = frozenset(str(sl.Guid) for sl in msa.SlotsRC)
    except (AttributeError, TypeError):
        slot_guids = frozenset()

    return (GrammarCategory.MSA, owner_guid, "MoInflAffMsa", pos_guid, slot_guids)


def fingerprint_for_allomorph(allo, ws_handle=None) -> Tuple:
    """Fingerprint for IMoAffixAllomorph (FR-104).

    Returns:
        (GrammarCategory.ALLOMORPH,
         owner_entry_guid: str,
         lexeme_form_text: str,
         morph_type_guid: str)

    lexeme_form_text: the string of allo.Form for ws_handle, or "" if
                      ws_handle is None or the Form is unreadable.
    morph_type_guid:  GUID string of MorphTypeRA, "" if unset.

    ws_handle should be the default-vernacular writing-system handle for best
    match quality; passing None degrades fingerprint precision to
    (owner, "", morphtype), which may cause false negatives on entries with
    multiple allomorphs of the same morphtype.
    """
    try:
        if allo.Owner is not None:
            owner_class = type(allo.Owner).__name__
            if owner_class not in ("LexEntry", "ILexEntry"):
                _log.warning(
                    "fingerprint_for_allomorph: .Owner is %s (expected LexEntry), "
                    "allo GUID=%s; fingerprint owner_guid may be wrong. "
                    "Affix allomorph path is unverified -- check ownership.",
                    owner_class,
                    getattr(allo, "Guid", "?"),
                )
                owner_guid = str(getattr(allo.Owner, "Guid", "") or "")
            else:
                owner_guid = str(allo.Owner.Guid)
        else:
            owner_guid = ""
    except AttributeError:
        owner_guid = ""

    lexeme_form_text = ""
    if ws_handle is not None:
        try:
            ts_string = allo.Form.get_String(ws_handle)
            lexeme_form_text = ts_string.Text or ""
        except (AttributeError, TypeError):
            lexeme_form_text = ""

    try:
        morph_type_guid = (
            str(allo.MorphTypeRA.Guid) if allo.MorphTypeRA is not None else ""
        )
    except AttributeError:
        morph_type_guid = ""

    return (GrammarCategory.ALLOMORPH, owner_guid, lexeme_form_text, morph_type_guid)


def fingerprint_with_owner(fn, obj, owner_guid_override, ws_handle=None):
    """Return the fingerprint produced by fn(obj, ws_handle) with tuple
    index 1 (owner_guid) replaced by owner_guid_override.

    Used by the merge-into planner path to evaluate source fingerprints
    against a resolved target entry (different GUID than the source entry),
    so that fingerprint matching correctly identifies already-present
    children under the resolved target.

    NOTE: If .Owner is not an ILexEntry, fingerprint_for_msa / fingerprint_for_allomorph
    will return "" for owner_guid. Callers must supply a valid owner_guid_override in
    that case. Any unexpected ownership will be logged by the caller (S2 residual risk).
    """
    fp = fn(obj, ws_handle)
    return (fp[0], owner_guid_override) + fp[2:]


# ---------------------------------------------------------------------------
# Per-category fingerprint registry (FR-104)
# ---------------------------------------------------------------------------

FINGERPRINT_FNS: Dict[GrammarCategory, Callable] = {
    GrammarCategory.MSA: fingerprint_for_msa,
    GrammarCategory.ALLOMORPH: fingerprint_for_allomorph,
    # POS, SLOTS, AFFIX_TEMPLATES, INFLECTION_FEATURES fingerprints (FR-104 table)
    # will be added here as Phase 1 category planners are implemented.
    # Each entry is (obj, ws_handle=None) -> hashable tuple.
}


# ---------------------------------------------------------------------------
# Main lookup entry point
# ---------------------------------------------------------------------------

def lookup_target(
    source_guid: str,
    category: GrammarCategory,
    target,
    *,
    source_obj=None,
    identity_remap: Optional[Dict[str, str]] = None,
    fingerprint_fn: Optional[Callable] = None,
) -> Match:
    """Look up the target object that matches source_guid (FR-102/103/104).

    Three-step fallback:

    1. Direct GUID match (FR-102):
       Queries the target for an object whose GUID == source_guid.
       Most LCM classes preserve source GUIDs via factory.Create(Guid, owner),
       so this is the dominant path for POS / Template / Slot / LexEntry /
       LexSense / PhEnvironment.

    2. identity_remap lookup (FR-103):
       Looks up source_guid in identity_remap (dict[str, str] from a prior
       Phase 0 RunReport: source_guid -> target_guid). Used for IMoInflAffMsa
       and IMoAffixAllomorph, whose LCM factories do not accept a GUID override
       so Phase 0 recorded the remapping explicitly.

    3. Fingerprint match (FR-104):
       Computes source_obj's fingerprint via fingerprint_fn (or the registry
       entry for category), then iterates all target objects in that category
       comparing fingerprints. First equality wins.
       Requires source_obj to be passed; skipped if source_obj is None and no
       fingerprint_fn is resolvable.

    Parameters:
        source_guid:    GUID string of the source LCM object.
        category:       GrammarCategory enum member.
        target:         Target project handle (duck-typed; see module docstring).
        source_obj:     The source LCM object. Required for step 3. Optional for
                        steps 1 and 2.
        identity_remap: Optional dict[str, str] (source GUID -> target GUID)
                        from a prior RunReport. Pass None when unavailable.
        fingerprint_fn: Optional (obj, ws_handle=None) -> tuple callable.
                        If None and source_obj is not None, FINGERPRINT_FNS is
                        consulted. If the category has no registered fingerprint
                        function, step 3 is skipped.

    Returns:
        Match(.via in {"guid", "identity_remap", "fingerprint", "none"}).
    """
    # ------------------------------------------------------------------
    # Step 1: Direct GUID match (FR-102)
    # ------------------------------------------------------------------
    obj = _find_by_guid(target, source_guid, category)
    if obj is not None:
        return Match(source_guid=source_guid, target_obj=obj, via="guid")

    # ------------------------------------------------------------------
    # Step 2: identity_remap (FR-103)
    # ------------------------------------------------------------------
    if identity_remap:
        remapped_guid = identity_remap.get(source_guid)
        if remapped_guid:
            obj = _find_by_guid(target, remapped_guid, category)
            if obj is not None:
                return Match(
                    source_guid=source_guid,
                    target_obj=obj,
                    via="identity_remap",
                )

    # ------------------------------------------------------------------
    # Step 3: Fingerprint (FR-104)
    # ------------------------------------------------------------------
    fn = fingerprint_fn or FINGERPRINT_FNS.get(category)
    if fn is not None and source_obj is not None:
        try:
            source_fp = fn(source_obj)
        except Exception:  # noqa: BLE001
            source_fp = None

        if source_fp is not None:
            result = _find_by_fingerprint(target, category, fn, source_fp)
            if result is not None:
                target_obj, fp_key = result
                return Match(
                    source_guid=source_guid,
                    target_obj=target_obj,
                    via="fingerprint",
                    fingerprint_key=fp_key,
                )

    # ------------------------------------------------------------------
    # No match — treat as Add
    # ------------------------------------------------------------------
    return Match(source_guid=source_guid, target_obj=None, via="none")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_by_guid(target, guid: str, category: GrammarCategory):
    """Return the target object whose str(Guid) == guid, or None.

    Tries target.get_object_by_guid(guid, category) first (O(1) if the
    target implements an index), then falls back to target.iter_objects(
    category) with a linear scan.
    """
    getter = getattr(target, "get_object_by_guid", None)
    if callable(getter):
        return getter(guid, category)

    iterator = getattr(target, "iter_objects", None)
    if callable(iterator):
        for obj in iterator(category):
            try:
                if str(obj.Guid) == guid:
                    return obj
            except AttributeError:
                continue

    return None


def _find_by_fingerprint(
    target,
    category: GrammarCategory,
    fp_fn: Callable,
    source_fp: Tuple,
) -> Optional[Tuple[object, Tuple]]:
    """Iterate target objects in category and return (obj, fp_key) for the
    first object whose fingerprint equals source_fp, or None.

    Gracefully skips any object for which fp_fn raises (FR-018 no-silent-drop
    principle: skip the individual comparison, not the whole search).
    """
    iterator = getattr(target, "iter_objects", None)
    if not callable(iterator):
        return None

    for obj in iterator(category):
        try:
            fp_key = fp_fn(obj)
        except Exception:  # noqa: BLE001
            continue
        if fp_key == source_fp:
            return (obj, fp_key)

    return None

"""Writing-system mapping validation (T036, spec.md FR-011 / Clarification Q3).

Pure-Python validation: given a set of source WS IDs (with kind) that the
current Selection requires, and a user-supplied `WSMapping`, decide whether
the mapping is complete and 1:1.

Mapping materialization into the target (creating WSs flagged
`create_in_target=True`) is implemented at runtime in `Lib/transfer.py`'s
pre-step; this module is the read-only validator and stays import-safe
without flexicon / pythonnet.
"""
from __future__ import annotations

from typing import FrozenSet, Iterable, Tuple

if __package__:
    from .models import WSKind, WSMapping
else:
    from models import WSKind, WSMapping


# ============================================================================
# Exceptions
# ============================================================================

class WSMappingError(Exception):
    """Base class for WS-mapping errors surfaced by `validate`."""


class WSMappingIncomplete(WSMappingError):
    """Raised when the user-provided WSMapping doesn't cover every required
    source writing system. The missing set is exposed via the `.missing`
    attribute as a frozenset of (source_ws_id, WSKind) pairs."""

    def __init__(self, missing: FrozenSet[Tuple[str, WSKind]]) -> None:
        self.missing = missing
        formatted = ", ".join(
            f"{ws_id!r} ({kind.value})" for ws_id, kind in sorted(missing, key=lambda x: x[0])
        )
        super().__init__(f"WS mapping incomplete: missing {formatted}")


class WSMappingOverspecified(WSMappingError):
    """Raised when the user-provided WSMapping carries entries for WSs that
    the current Selection doesn't reference. Not a hard error in production
    (the extras are simply ignored), but tests use it to verify the WSs the
    user is asked to map are exactly the ones actually needed."""

    def __init__(self, extras: FrozenSet[Tuple[str, WSKind]]) -> None:
        self.extras = extras
        super().__init__(f"WS mapping overspecified: extras {sorted(extras)}")


# ============================================================================
# Public API
# ============================================================================

def required_ws_set(pairs: Iterable[Tuple[str, WSKind]]) -> FrozenSet[Tuple[str, WSKind]]:
    """Build a frozenset of (source_ws_id, kind) pairs from an arbitrary
    iterable. Caller is the closure walker — it asks each selected piece for
    its `required_writing_systems()` and feeds the union here.
    """
    return frozenset(pairs)


def validate(ws_mapping: WSMapping,
             required: FrozenSet[Tuple[str, WSKind]],
             *, strict_overspec: bool = False) -> None:
    """Verify that `ws_mapping` covers every (source_ws_id, kind) pair in
    `required`. Raises `WSMappingIncomplete` listing the missing entries
    otherwise.

    If `strict_overspec=True`, also raise `WSMappingOverspecified` when the
    mapping carries entries the Selection doesn't reference. Default is
    permissive — production runs ignore extras (the user may have mapped
    extra WSs in anticipation of future selections).
    """
    provided = frozenset(
        (e.source_ws_id, e.source_ws_kind) for e in ws_mapping.entries
    )
    missing = required - provided
    if missing:
        raise WSMappingIncomplete(missing)
    if strict_overspec:
        extras = provided - required
        if extras:
            raise WSMappingOverspecified(extras)


def is_complete(ws_mapping: WSMapping,
                required: FrozenSet[Tuple[str, WSKind]]) -> bool:
    """Predicate form of `validate` — True iff `ws_mapping` covers every
    required pair. Use this in UI gating (Move button stays disabled until
    the WS mapping is complete)."""
    try:
        validate(ws_mapping, required, strict_overspec=False)
        return True
    except WSMappingIncomplete:
        return False


# ============================================================================
# Phase 2 (US2 / FR-209..212) -- writing-system mismatch wizard support
# ============================================================================

from typing import Protocol

if __package__:
    from .models import WSMismatch
else:
    from models import WSMismatch


class WSResolver(Protocol):
    """Phase 2 -- the interactive WS wizard's contract.

    Production: PyQt `Lib/ui/ws_wizard.py.WSWizard` (deferred).
    Tests: FakeWSResolver in tests/unit/conftest.py.
    """

    def resolve(self, mismatches):
        """Block until the user has resolved every mismatch.

        Args:
            mismatches: tuple[WSMismatch, ...].

        Returns:
            tuple[WSMappingChoice, ...] of the same length and order.

        Raises:
            UserCancelled: if the user dismisses the wizard.
        """
        ...


def _enumerate_ws(project):
    """Return tuple of WS descriptor dicts {id, kind, handle} for a
    flexicon project.  Tolerates several accessor shapes; uses
    WritingSystems.GetAll() per the flexicon API."""
    if project is None:
        return ()
    out = []
    try:
        ws_defs = list(project.WritingSystems.GetAll())
    except (AttributeError, TypeError):
        return ()
    for wd in ws_defs:
        try:
            ws_id = wd.Id
        except AttributeError:
            ws_id = getattr(wd, "id", None) or ""
        try:
            handle = wd.Handle
        except AttributeError:
            handle = getattr(wd, "handle", None)
        # WS kind: best-effort.  flexicon descriptors carry IsVernacular;
        # default to VERNACULAR when unavailable.
        kind = WSKind.VERNACULAR
        try:
            if not wd.IsVernacular:
                kind = WSKind.ANALYSIS
        except AttributeError:
            pass
        if ws_id:
            out.append({"id": str(ws_id), "kind": kind, "handle": handle})
    return tuple(out)


def _similarity_rank(source_id: str, candidate_id: str) -> int:
    """Lower rank = better match. Used to sort target_ws_candidates so
    the most likely "did you mean" appears first in the wizard.

    Ranks:
        0: exact (won't show in mismatches but kept for symmetry)
        1: same primary language tag prefix (ko-* vs ko-*)
        2: same first-3 chars (koh-x-Latn ~ koh-Hang)
        3: any other target WS
    """
    if source_id == candidate_id:
        return 0
    s_lang = source_id.split("-", 1)[0]
    c_lang = candidate_id.split("-", 1)[0]
    if s_lang == c_lang:
        return 1
    # Same first 2 chars (ko vs koh, etc.) -- close-enough match.
    if len(s_lang) >= 2 and len(c_lang) >= 2 and s_lang[:2] == c_lang[:2]:
        return 2
    return 3


def detect_ws_mismatches(source, target):
    """T031 / FR-209 -- enumerate every source WS whose Id is NOT in the
    target project's WS list, returning similarity-sorted candidates.

    Args:
        source: flexicon FLExProject (read-only).
        target: flexicon FLExProject (read-only here).

    Returns:
        tuple[WSMismatch, ...] sorted by source_ws_id.  Empty when
        every source WS is already in the target.
    """
    src_ws = _enumerate_ws(source)
    tgt_ws = _enumerate_ws(target)
    tgt_ids = {w["id"] for w in tgt_ws}
    tgt_id_list = [w["id"] for w in tgt_ws]
    out = []
    for sw in src_ws:
        if sw["id"] in tgt_ids:
            continue
        candidates = sorted(
            tgt_id_list, key=lambda c: (_similarity_rank(sw["id"], c), c)
        )
        out.append(WSMismatch(
            source_ws_id=sw["id"],
            source_ws_kind=sw["kind"],
            target_ws_candidates=tuple(candidates),
        ))
    out.sort(key=lambda m: m.source_ws_id)
    return tuple(out)


def fold_choices_into_ws_mapping(choices, base_mapping):
    """T036 / FR-210 -- convert WSMappingChoice tuple into WSMappingEntry
    rows and merge into `base_mapping`.

    Per FR-211, SKIP choices are NOT folded into the WSMapping (they have
    no target_ws_id).  Callers must thread the original choice tuple
    through Selection.ws_mapping_choices so the planner can detect SKIP
    and emit Skip(UNMAPPED_WS_USER_CHOSE_SKIP).

    Per FR-212, CREATE choices assume the new WS has ALREADY been created
    in the target before this function is called.  An identity mapping
    (source_id -> source_id) is registered with create_in_target=True
    for audit.
    """
    if __package__:
        from .models import WSMappingEntry, WSChoice
    else:
        from models import WSMappingEntry, WSChoice
    existing = list(base_mapping.entries) if base_mapping is not None else []
    seen = {(e.source_ws_id, e.source_ws_kind) for e in existing}
    for c in choices:
        key = (c.source_ws_id, c.source_ws_kind)
        if key in seen:
            continue
        if c.choice == WSChoice.MAP:
            existing.append(WSMappingEntry(
                source_ws_id=c.source_ws_id,
                source_ws_kind=c.source_ws_kind,
                target_ws_id=c.target_ws_id,
                create_in_target=False,
            ))
            seen.add(key)
        elif c.choice == WSChoice.CREATE:
            existing.append(WSMappingEntry(
                source_ws_id=c.source_ws_id,
                source_ws_kind=c.source_ws_kind,
                target_ws_id=c.source_ws_id,
                create_in_target=True,
            ))
            seen.add(key)
        # WSChoice.SKIP intentionally not folded.
    return WSMapping(entries=tuple(existing))

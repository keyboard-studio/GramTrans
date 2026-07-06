"""Merge-Preview Diff Engine & HTML Rendering (feature 012).

Three layers, one Qt-free module:

1. **Pure diff core** -- ``diff_props`` / ``DiffSegment`` / ``FieldDiff`` /
   ``MergePreview``.  Mirrors (never imports) the ``_deterministic_merge``
   taxonomy from ``conflict.py`` across four conflict modes and five value
   shapes.  No I/O; no registry.

2. **LCM props fetch + category registry** -- ``props_for`` / ``ws_role_map``.
   Pulls a comparable ``{field: value}`` dict per transfer category via
   ``GetSyncableProperties``, with direct-read fallbacks for the three
   gap categories (Slots, Phonological Features, Stem Names).  flexicon
   imports are lazy/guarded inside these functions so the pure core stays
   importable without LCM.

3. **HTML rendering + caching service** -- ``to_html`` / ``MergePreviewService``.
   Renders a computed preview using ``WsFontRegistry`` / ``WsFont`` / ``WsRole``
   from ``ws_fonts.py``.  Memoizes on the **4-tuple**
   ``(category, source_guid, target_guid, mode)`` (SC-006, A1).

HARD CONSTRAINTS
----------------
- Qt-free (SC-007): this module MUST NOT import PyQt / PySide at any level.
- py38 target: ``from __future__ import annotations`` + typing generics only.
- Mirror-not-import: ``_deterministic_merge`` taxonomy is re-implemented here;
  ``conflict._deterministic_merge`` is NEVER imported.
- ``rtl`` is resolved at render time in ``to_html`` from ``WsFontRegistry``
  (A2), NOT stored on ``DiffSegment``.
- Cache key is the 4-tuple ``(category, source_guid, target_guid, mode)`` (A1).
- Coverage: 4 covered / 8 finder-needed / 3 gaps (A3, research.md R4).
"""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

# Reused from ws_fonts.py (confirmed Qt-free).
if __package__:
    from .ws_fonts import WsFont, WsFontRegistry, WsRole  # noqa: F401
else:
    from ws_fonts import WsFont, WsFontRegistry, WsRole  # type: ignore  # noqa: F401


# ============================================================================
# Segment kind
# ============================================================================


class SegmentKind(str, Enum):
    """Tag for a run of diff text (FR-001)."""

    ADDED = "added"
    UNCHANGED = "unchanged"
    REMOVED = "removed"
    NOTE = "note"


# ============================================================================
# Pure value types  (FR-001)
# ============================================================================


@dataclass(frozen=True)
class DiffSegment:
    """Atom of the diff: one run of text with a kind and optional WS role.

    ``rtl`` is NOT stored here (A2, lex-simplify cycle 1): script direction
    is resolved at render time by ``to_html`` from the ``WsFontRegistry``.
    This keeps ``diff_props`` pure against plain dicts (no registry needed).
    """

    text: str
    kind: SegmentKind
    ws_role: WsRole | None = None


@dataclass(frozen=True)
class FieldDiff:
    """One field's ordered segments plus display hints for nested children.

    ``field_name`` is the machine key (fingerprint-based join key for nested
    children; property name for entry scalars).  It drives dict-keyed diff
    pairing and is never shown directly when ``display_name`` is non-empty.

    ``display_name`` (new, spec-023): human label shown in the pane, e.g.
    ``"Allomorph 1 > Comment"``.  Empty string causes the renderer to fall
    back to ``field_name`` (preserves existing scalar rendering).

    ``sort_key`` (new, spec-023): ``(group_order, field_order)`` ordering
    hint.  Empty tuple -> alphabetical by ``field_name`` (SC-003 for scalars).
    Non-empty on ANY FieldDiff in a list causes the whole list to sort by
    ``sort_key`` (tie-break ``field_name``).

    ``indent`` (existing): nesting depth (0 = entry-level, 1 = child).
    """

    field_name: str
    segments: tuple[DiffSegment, ...]
    indent: int = 0
    display_name: str = ""
    sort_key: tuple = ()


@dataclass(frozen=True)
class MergePreview:
    """Full computed diff for one item.

    ``status`` is an opaque pass-through (011 row-status vocabulary); it is
    stored in the cached *value*, never in the cache *key*.
    ``fields`` is ALWAYS sorted alphabetically by ``field_name`` (SC-003).
    """

    status: str
    fields: tuple[FieldDiff, ...]
    notes: tuple[str, ...] = field(default_factory=tuple)


# ============================================================================
# Conflict modes (FR-002 – FR-004a, R2)
# ============================================================================

NEW = "new"
"""Every value is ``added`` (no target / create-new).  (FR-002)"""

LINK_ONLY = "link_only"
"""Target fields ``unchanged``; source-only fields get a ``note``.  (FR-003)"""

OVERWRITE = "overwrite"
"""Source wins on every differing value.  (FR-004)"""

MERGE_KEEP = "merge_keep"
"""Target-preserving fill-gaps: source fills only empty target slots.  (FR-004a)"""


# ============================================================================
# Value-shape taxonomy (mirrors _deterministic_merge — never imports it)
# ============================================================================

_NON_MERGEABLE_TYPES = (int, bool, type(None))
_SET_TYPES = (list, tuple, set, frozenset)


def _is_empty_ms_value(v: Any) -> bool:
    """Return True if a multistring value is absent or empty-string."""
    return v is None or (isinstance(v, str) and v == "")


def _segments_for_overwrite_ms(
    src_ms: dict[str, str],
    tgt_ms: dict[str, str],
    ws_role_of: Callable[[str], WsRole | None],
) -> list[DiffSegment]:
    """Recurse per ws-key for OVERWRITE multistring dispatch."""
    segs: list[DiffSegment] = []
    all_keys = sorted(set(src_ms) | set(tgt_ms))
    for wid in all_keys:
        role = ws_role_of(wid)
        label = f"[{wid}] "
        if wid in src_ms and wid in tgt_ms:
            sv, tv = src_ms[wid], tgt_ms[wid]
            if sv == tv:
                segs.append(DiffSegment(text=label + sv, kind=SegmentKind.UNCHANGED, ws_role=role))
            else:
                # target-side removed, source-side added
                segs.append(DiffSegment(text=label + tv, kind=SegmentKind.REMOVED, ws_role=role))
                segs.append(DiffSegment(text=label + sv, kind=SegmentKind.ADDED, ws_role=role))
        elif wid in src_ms:
            # source-only: added
            segs.append(DiffSegment(text=label + src_ms[wid], kind=SegmentKind.ADDED, ws_role=role))
        else:
            # target-only: unchanged (target-only keys pass through, no deletion implied)
            segs.append(
                DiffSegment(text=label + tgt_ms[wid], kind=SegmentKind.UNCHANGED, ws_role=role)
            )
    return segs


def _segments_for_merge_keep_ms(
    src_ms: dict[str, str],
    tgt_ms: dict[str, str],
    ws_role_of: Callable[[str], WsRole | None],
) -> list[DiffSegment]:
    """Recurse per ws-key for MERGE-KEEP multistring dispatch (FR-004a, R3)."""
    segs: list[DiffSegment] = []
    all_keys = sorted(set(src_ms) | set(tgt_ms))
    for wid in all_keys:
        role = ws_role_of(wid)
        label = f"[{wid}] "
        src_val = src_ms.get(wid, "")
        tgt_val = tgt_ms.get(wid, "")

        # "empty target ws" = ws key absent OR value is empty string (lex-domain constraint 1)
        tgt_empty = _is_empty_ms_value(tgt_val)

        if wid not in src_ms:
            # target-only key: unchanged
            segs.append(DiffSegment(text=label + tgt_val, kind=SegmentKind.UNCHANGED, ws_role=role))
        elif tgt_empty:
            # source fills the gap
            segs.append(DiffSegment(text=label + src_val, kind=SegmentKind.ADDED, ws_role=role))
        elif src_val == tgt_val:
            segs.append(DiffSegment(text=label + tgt_val, kind=SegmentKind.UNCHANGED, ws_role=role))
        else:
            # differing, non-empty target: target wins, source noted
            segs.append(DiffSegment(text=label + tgt_val, kind=SegmentKind.UNCHANGED, ws_role=role))
            segs.append(
                DiffSegment(
                    text=f"(source [{wid}] not applied: {src_val!r})",
                    kind=SegmentKind.NOTE,
                    ws_role=None,
                )
            )
    return segs


def _segments_for_value(
    src_val: Any,
    tgt_val: Any,
    mode: str,
    ws_role_of: Callable[[str], WsRole | None],
) -> list[DiffSegment]:
    """Return diff segments for a single field value.

    Dispatch order (mirrors _deterministic_merge taxonomy, conflict.py L176+):
    1. multistring dict {ws_id: str}
    2. plain str
    3. list / tuple / set / frozenset  (union: common unchanged, src-only added, tgt-only unchanged)
    4. scalar int / bool / None        (removed + added)
    5. other object                    (repr() then treat as str)

    For NEW mode, tgt_val is None; callers pass ``None`` and we return all-added.
    For LINK_ONLY, callers short-circuit before reaching here.

    Two intentional preview-vs-merge divergences (display-only; documented per
    the cycle-2 domain review):
    - **Sequences (shape 3)** collapse every member to a flat ``DiffSegment``
      list; the real merge preserves the original collection type
      (tuple/set/frozenset).  The type distinction is not user-visible in the
      rendered diff, so the preview does not carry it.
    - **Other objects (shape 5)** are ``repr()``-ed on each side and rendered as
      a removed+added *replacement*; the real ``_deterministic_merge`` would
      concat the two reprs with its run-id separator.  The preview correctly
      shows "source wins" without leaking the run-id marker -- it does not
      reproduce the concatenated string.  Low-risk given real FLEx value shapes.
    """
    # -- NEW: tgt is None, everything is added ---------------------------------
    if tgt_val is None and mode == NEW:
        return _added_segments(src_val, ws_role_of)

    # -- multistring dict -------------------------------------------------------
    if isinstance(src_val, dict) and isinstance(tgt_val, dict):
        if mode == OVERWRITE:
            return _segments_for_overwrite_ms(src_val, tgt_val, ws_role_of)
        if mode == MERGE_KEEP:
            return _segments_for_merge_keep_ms(src_val, tgt_val, ws_role_of)
        # Fallback: treat as unchanged (shouldn't happen in normal flow)
        return [DiffSegment(text=repr(src_val), kind=SegmentKind.UNCHANGED, ws_role=None)]

    if isinstance(src_val, dict) and tgt_val is None:
        # source-only multistring in non-NEW context: added
        return _added_segments(src_val, ws_role_of)

    # -- plain str -------------------------------------------------------------
    if isinstance(src_val, str) and isinstance(tgt_val, str):
        if src_val == tgt_val:
            return [DiffSegment(text=src_val, kind=SegmentKind.UNCHANGED, ws_role=None)]
        return [
            DiffSegment(text=tgt_val, kind=SegmentKind.REMOVED, ws_role=None),
            DiffSegment(text=src_val, kind=SegmentKind.ADDED, ws_role=None),
        ]

    # -- list / tuple / set / frozenset ----------------------------------------
    if isinstance(src_val, _SET_TYPES) or isinstance(tgt_val, _SET_TYPES):
        src_seq = list(src_val) if src_val is not None else []
        tgt_seq = list(tgt_val) if tgt_val is not None else []
        return _segments_for_sequence(src_seq, tgt_seq)

    # -- scalar (int / bool / None) --------------------------------------------
    if isinstance(src_val, _NON_MERGEABLE_TYPES) or isinstance(tgt_val, _NON_MERGEABLE_TYPES):
        if src_val == tgt_val:
            return [DiffSegment(text=repr(src_val), kind=SegmentKind.UNCHANGED, ws_role=None)]
        segs: list[DiffSegment] = []
        if tgt_val is not None:
            segs.append(DiffSegment(text=repr(tgt_val), kind=SegmentKind.REMOVED, ws_role=None))
        segs.append(DiffSegment(text=repr(src_val), kind=SegmentKind.ADDED, ws_role=None))
        return segs

    # -- other object: repr then treat as str ----------------------------------
    return _segments_for_value(repr(src_val), repr(tgt_val), mode, ws_role_of)


def _ws_dict_to_segments(
    d: dict[str, str],
    kind: SegmentKind,
    ws_role_of: Callable[[str], WsRole | None],
) -> list[DiffSegment]:
    """Convert a ``{ws_id: text}`` multistring dict into segments of the given kind."""
    return [
        DiffSegment(text=f"[{wid}] {d[wid]}", kind=kind, ws_role=ws_role_of(wid))
        for wid in sorted(d)
    ]


def _added_segments(val: Any, ws_role_of: Callable[[str], WsRole | None]) -> list[DiffSegment]:
    """Convert any value into all-added segments (NEW mode, or source-only)."""
    if isinstance(val, dict):
        return _ws_dict_to_segments(val, SegmentKind.ADDED, ws_role_of)
    if isinstance(val, (list, tuple, set, frozenset)):
        return [DiffSegment(text=repr(item), kind=SegmentKind.ADDED, ws_role=None) for item in val]
    return [DiffSegment(text=repr(val), kind=SegmentKind.ADDED, ws_role=None)]


def _segments_for_sequence(src_seq: list[Any], tgt_seq: list[Any]) -> list[DiffSegment]:
    """Union of two sequences: common unchanged, src-only added, tgt-only unchanged."""
    segs: list[DiffSegment] = []
    # Determine membership using hashability check with linear fallback.
    try:
        src_set = set(src_seq)
        tgt_set = set(tgt_seq)
        hashable = True
    except TypeError:
        hashable = False

    # Emit common (in left/src order), then src-only, then tgt-only
    for item in src_seq:
        in_tgt = item in tgt_set if hashable else item in tgt_seq
        kind = SegmentKind.UNCHANGED if in_tgt else SegmentKind.ADDED
        segs.append(DiffSegment(text=repr(item), kind=kind, ws_role=None))

    for item in tgt_seq:
        in_src = item in src_set if hashable else item in src_seq
        if not in_src:
            segs.append(DiffSegment(text=repr(item), kind=SegmentKind.UNCHANGED, ws_role=None))

    return segs


# ============================================================================
# diff_props — public pure API
# ============================================================================


def diff_props(
    src_props: dict[str, Any],
    tgt_props: dict[str, Any] | None,
    mode: str,
    ws_role_of: Callable[[str], WsRole | None],
    *,
    status: str = "",
    meta: dict[str, Any] | None = None,
) -> MergePreview:
    """Compute a field-by-field diff of source vs target properties.

    Pure — no I/O, no Qt, no LCM.  ``ws_role_of`` maps a ws-id string to
    an optional ``WsRole`` (from ``ws_role_map``).

    ``meta`` (spec-023, optional): ``{machine_key: (display_name, sort_key,
    indent)}`` produced by ``_gather_entry_nested``.  When present, stamps
    ``display_name``/``sort_key``/``indent`` onto each emitted ``FieldDiff``
    for that key.  When ``None`` behavior is identical to today (G8).

    Guarantees (FR-002 – FR-006):
    - ``tgt_props is None`` -> every field/value ``added`` (SC-001, FR-002).
    - ``LINK_ONLY`` -> target fields ``unchanged``; source-only fields ``note``.
    - ``OVERWRITE`` -> per union key: equal unchanged; source-only added;
      target-only unchanged; differing -> value-shape dispatch, source wins.
    - ``MERGE_KEEP`` -> per union key: equal unchanged; source-only/empty-target
      added; target-only unchanged; differing-with-nonempty-target -> target
      unchanged + note.
    - When any FieldDiff has non-empty sort_key, list sorted by sort_key
      (tie-break field_name); otherwise alphabetical by field_name (SC-003).
    - Mirrors, never imports, ``conflict._deterministic_merge`` (FR-006).
    """
    field_diffs: list[FieldDiff] = []
    notes: list[str] = []

    def _make_fd(key: str, segs: list[DiffSegment]) -> FieldDiff:
        """Build a FieldDiff, stamping meta if present."""
        if meta and key in meta:
            dn, sk, ind = meta[key]
            return FieldDiff(
                field_name=key,
                segments=tuple(segs),
                indent=ind,
                display_name=dn,
                sort_key=sk,
            )
        return FieldDiff(field_name=key, segments=tuple(segs))

    def _sort_field_diffs(fds: list[FieldDiff]) -> list[FieldDiff]:
        """Sort by sort_key if any non-empty; else alphabetical."""
        if any(fd.sort_key for fd in fds):
            return sorted(fds, key=lambda fd: (fd.sort_key, fd.field_name))
        return sorted(fds, key=lambda fd: fd.field_name)

    if tgt_props is None or mode == NEW:
        # NEW: every source field is added
        for key in sorted(src_props):
            segs = _added_segments(src_props[key], ws_role_of)
            if segs:
                field_diffs.append(_make_fd(key, segs))
        field_diffs = _sort_field_diffs(field_diffs)
        return MergePreview(status=status, fields=tuple(field_diffs), notes=tuple(notes))

    if mode == LINK_ONLY:
        # Target fields unchanged; source-only fields get a note
        for key in sorted(set(tgt_props)):
            tval = tgt_props[key]
            segs = _value_to_unchanged(tval, ws_role_of)
            field_diffs.append(_make_fd(key, segs))
        for key in sorted(set(src_props) - set(tgt_props)):
            note_seg = DiffSegment(
                text=f"{key}: not transferred -- links without field update",
                kind=SegmentKind.NOTE,
                ws_role=None,
            )
            field_diffs.append(_make_fd(key, [note_seg]))
        field_diffs = _sort_field_diffs(field_diffs)
        return MergePreview(status=status, fields=tuple(field_diffs), notes=tuple(notes))

    if mode in (OVERWRITE, MERGE_KEEP):
        all_keys = sorted(set(src_props) | set(tgt_props))
        for key in all_keys:
            src_val = src_props.get(key)
            tgt_val = tgt_props.get(key)

            if key not in src_props:
                # target-only: unchanged (never implies deletion)
                segs = _value_to_unchanged(tgt_val, ws_role_of)
                field_diffs.append(_make_fd(key, segs))
                continue

            if key not in tgt_props:
                # source-only: added
                segs = _added_segments(src_val, ws_role_of)
                field_diffs.append(_make_fd(key, segs))
                continue

            if src_val == tgt_val:
                segs = _value_to_unchanged(tgt_val, ws_role_of)
                field_diffs.append(_make_fd(key, segs))
                continue

            # differing values: dispatch by mode and shape
            if mode == MERGE_KEEP:
                segs = _segments_merge_keep_field(src_val, tgt_val, ws_role_of)
            else:  # OVERWRITE
                segs = _segments_for_value(src_val, tgt_val, OVERWRITE, ws_role_of)
            field_diffs.append(_make_fd(key, segs))

        field_diffs = _sort_field_diffs(field_diffs)
        return MergePreview(status=status, fields=tuple(field_diffs), notes=tuple(notes))

    # Unknown mode: fallback — treat all as added
    for key in sorted(src_props):
        segs = _added_segments(src_props[key], ws_role_of)
        field_diffs.append(_make_fd(key, segs))
    field_diffs = _sort_field_diffs(field_diffs)
    return MergePreview(status=status, fields=tuple(field_diffs), notes=tuple(notes))


def _segments_merge_keep_field(
    src_val: Any,
    tgt_val: Any,
    ws_role_of: Callable[[str], WsRole | None],
) -> list[DiffSegment]:
    """MERGE-KEEP semantics for one differing field (FR-004a)."""
    # multistring: per-ws dispatch already handles per-ws emptiness
    if isinstance(src_val, dict) and isinstance(tgt_val, dict):
        return _segments_for_merge_keep_ms(src_val, tgt_val, ws_role_of)
    if isinstance(src_val, dict) and tgt_val is None:
        return _added_segments(src_val, ws_role_of)

    # sequence: source fills gaps (items absent from target are added)
    if isinstance(src_val, _SET_TYPES) or isinstance(tgt_val, _SET_TYPES):
        src_seq = list(src_val) if src_val is not None else []
        tgt_seq = list(tgt_val) if tgt_val is not None else []
        return _segments_for_sequence(src_seq, tgt_seq)

    # plain str / scalar / other: target non-empty → target wins, note source
    tgt_empty = tgt_val is None or (isinstance(tgt_val, str) and tgt_val == "")
    if tgt_empty:
        return _added_segments(src_val, ws_role_of)
    # target holds a value: target unchanged + note
    tgt_text = tgt_val if isinstance(tgt_val, str) else repr(tgt_val)
    src_text = src_val if isinstance(src_val, str) else repr(src_val)
    return [
        DiffSegment(text=tgt_text, kind=SegmentKind.UNCHANGED, ws_role=None),
        DiffSegment(
            text=f"(source value not applied: {src_text!r})",
            kind=SegmentKind.NOTE,
            ws_role=None,
        ),
    ]


def _value_to_unchanged(val: Any, ws_role_of: Callable[[str], WsRole | None]) -> list[DiffSegment]:
    """Render an existing value as all-unchanged segments."""
    if isinstance(val, dict):
        return _ws_dict_to_segments(val, SegmentKind.UNCHANGED, ws_role_of)
    if isinstance(val, (list, tuple, set, frozenset)):
        return [
            DiffSegment(text=repr(item), kind=SegmentKind.UNCHANGED, ws_role=None) for item in val
        ]
    return [DiffSegment(text=repr(val), kind=SegmentKind.UNCHANGED, ws_role=None)]


# ============================================================================
# HTML rendering  (FR-010, SC-004)
# ============================================================================

_KIND_STYLE: dict[SegmentKind, str] = {
    SegmentKind.ADDED: "color:#1a7f1a;",
    SegmentKind.UNCHANGED: "",
    SegmentKind.REMOVED: "color:#cc0000;text-decoration:line-through;",
    SegmentKind.NOTE: "color:#888888;font-style:italic;",
}


def to_html(preview: MergePreview, registry: WsFontRegistry) -> str:
    """Render a ``MergePreview`` to escaped, colorized, font-aware HTML.

    Guarantees (FR-010, SC-004):
    - 100% of text is HTML-escaped.
    - added green; removed red + strike-through; note gray italic.
    - Each value span uses the registry's font-family + point-size for its role.
    - ``dir="rtl"`` where the role's ``WsFont.rtl`` is True (A2 -- resolved here,
      NOT stored on DiffSegment).
    - Indentation reflects ``FieldDiff.indent``; field names bold.
    - A segment with ``ws_role is None`` renders in the default font (chrome).
    """
    parts: list[str] = ["<div class='merge-preview'>"]

    for fd in preview.fields:
        indent_px = fd.indent * 16
        label = fd.display_name if fd.display_name else fd.field_name
        parts.append(
            f"<div style='margin-left:{indent_px}px;margin-bottom:4px;'>"
            f"<b>{html.escape(label)}</b>: "
        )
        for seg in fd.segments:
            parts.append(_render_segment(seg, registry))
        parts.append("</div>")

    if preview.notes:
        parts.append("<div class='preview-notes'>")
        for note in preview.notes:
            parts.append(f"<div style='color:#888888;font-style:italic;'>{html.escape(note)}</div>")
        parts.append("</div>")

    parts.append("</div>")
    return "".join(parts)


def _render_segment(seg: DiffSegment, registry: WsFontRegistry) -> str:
    """Render one ``DiffSegment`` as an HTML span."""
    kind_style = _KIND_STYLE.get(seg.kind, "")

    # Resolve font from role via registry (A2: rtl resolved here)
    font: WsFont | None = registry.font_for(seg.ws_role)
    font_style = ""
    dir_attr = ""
    if font is not None:
        font_style = f"font-family:'{html.escape(font.font_name)}';font-size:{font.size_pt}pt;"
        if font.rtl:
            dir_attr = " dir='rtl'"

    style = kind_style + font_style
    escaped = html.escape(seg.text)
    if style or dir_attr:
        return f"<span style='{style}'{dir_attr}>{escaped}</span>"
    return f"<span>{escaped}</span>"


# ============================================================================
# WS role classification  (FR-009, R5)
# ============================================================================


def ws_role_map(project: Any) -> dict[str, WsRole]:
    """Classify each ws-id in the project as VERNACULAR / IPA / ANALYSIS.

    Every accessor is guarded; a missing or edge ws does not crash.
    Reuses the ``"fonipa" in wid.split("-")`` heuristic from ``ws_fonts.py``
    (R5).  Returns an empty dict if the project is None or exposes no
    writing-system surface.

    The returned dict is used to build a ``ws_role_of`` callable:
    ``role_map.get`` can be passed directly (returns None for unknown ids).
    """
    result: dict[str, WsRole] = {}
    if project is None:
        return result

    try:
        ws_ops = getattr(project, "WritingSystems", None)
        if ws_ops is None:
            return result

        # Vernacular list
        try:
            vern_ws = _safe_call(ws_ops, "GetVernacular") or []
            vern_ids = set()
            for ws in vern_ws:
                wid = _safe_ws_id(ws)
                if wid:
                    vern_ids.add(wid.lower())
        except Exception:
            vern_ids = set()

        # All writing systems
        try:
            all_ws = _safe_call(ws_ops, "GetAll") or []
        except Exception:
            all_ws = []

        for ws in all_ws:
            try:
                wid = _safe_ws_id(ws)
                if not wid:
                    continue
                wid_lower = wid.lower()
                if "fonipa" in wid_lower.split("-"):
                    result[wid] = WsRole.IPA
                elif wid_lower in vern_ids:
                    result[wid] = WsRole.VERNACULAR
                else:
                    result[wid] = WsRole.ANALYSIS
            except Exception as _exc:
                logging.debug("ws_role_map: skipping unreadable ws %r: %s", ws, _exc)
                continue

    except Exception as _exc:
        logging.debug("ws_role_map: no writing-system surface on project: %s", _exc)

    return result


def _safe_call(obj: Any, method: str, *args: Any) -> Any:
    """Call obj.method(*args) returning None on any failure."""
    fn = getattr(obj, method, None)
    if fn is None:
        return None
    try:
        return fn(*args)
    except Exception:
        return None


def _safe_ws_id(ws: Any) -> str:
    """Extract ws id string from a ws object."""
    if ws is None:
        return ""
    for attr in ("Id", "id"):
        val = getattr(ws, attr, None)
        if val:
            return str(val)
    return ""


# ============================================================================
# Per-category props table  (FR-007, data-model.md)
# ============================================================================
# Coverage: 4 fully covered / 8 finder-needed (net-new) / 3 gaps (direct-read)
# (A3, research.md R4)
#
# _OW_OPS finders reused from conflict.py (4 covered):
#   _find_target_pos_by_guid, _find_target_entry_by_guid,
#   _find_target_sense_by_guid, _find_target_allo_by_guid
#
# Net-new finders (8, T023/T024): implemented below.
# Gap categories (3, T026): direct-read fallback paths.


def _unwrap(obj: Any) -> Any:
    """Unwrap flexicon wrapper objects (mirrors conflict.py._unwrap)."""
    return obj.concrete if hasattr(obj, "concrete") else obj


def _guid_eq(a: str, b: str) -> bool:
    return a.lower() == b.lower()


def _obj_guid(obj: Any) -> str:
    """Extract GUID string from an LCM object; returns '' on failure."""
    try:
        from SIL.LCModel import ICmObject  # lazy

        concrete = _unwrap(obj)
        return str(ICmObject(concrete).Guid).lower()
    except Exception:
        # Duck-typed fake in tests
        for attr in ("guid", "Guid"):
            v = getattr(obj, attr, None)
            if v is not None:
                return str(v).lower()
        return ""


# ---- Covered finders (reuse conflict._OW_OPS pattern) ----------------------


def _find_target_pos_by_guid(target: Any, guid: str) -> Any:
    """Locate a POS in target by GUID (recursive)."""
    for p in target.POS.GetAll(recursive=True):
        if _guid_eq(_obj_guid(p), guid):
            return _unwrap(p)
    return None


def _find_target_entry_by_guid(target: Any, guid: str) -> Any:
    """Locate a LexEntry in target by GUID."""
    for te in target.LexEntry.GetAll():
        if _guid_eq(_obj_guid(te), guid):
            return _unwrap(te)
    return None


def _find_target_sense_by_guid(target: Any, guid: str, owner_entry_guid: str = "") -> Any:
    """Locate a Sense in target by GUID (scoped to owner entry when given)."""
    if owner_entry_guid:
        entry = _find_target_entry_by_guid(target, owner_entry_guid)
        if entry is not None:
            for s in target.LexEntry.GetSenses(entry):
                if _guid_eq(_obj_guid(s), guid):
                    return _unwrap(s)
        return None
    for te in target.LexEntry.GetAll():
        for s in target.LexEntry.GetSenses(te):
            if _guid_eq(_obj_guid(s), guid):
                return _unwrap(s)
    return None


def _find_target_allo_by_guid(target: Any, guid: str, owner_entry_guid: str = "") -> Any:
    """Locate an Allomorph in target by GUID (scoped to owner entry)."""
    if owner_entry_guid:
        entry = _find_target_entry_by_guid(target, owner_entry_guid)
        if entry is not None:
            for a in target.Allomorphs.GetAll(entry):
                if _guid_eq(_obj_guid(a), guid):
                    return _unwrap(a)
        return None
    for te in target.LexEntry.GetAll():
        for a in target.Allomorphs.GetAll(te):
            if _guid_eq(_obj_guid(a), guid):
                return _unwrap(a)
    return None


# ---- Net-new finders (8 finder-needed categories, T023/T024) ---------------
# NOTE: these finders do NOT yet exist in conflict._OW_OPS; they are net-new.


def _find_target_phoneme_by_guid(target: Any, guid: str) -> Any:
    """T023 — locate a Phoneme in target by GUID."""
    for p in target.Phonemes.GetAll():
        if _guid_eq(_obj_guid(p), guid):
            return _unwrap(p)
    return None


def _find_target_natural_class_by_guid(target: Any, guid: str) -> Any:
    """T023 — locate a NaturalClass in target by GUID."""
    for nc in target.NaturalClasses.GetAll():
        if _guid_eq(_obj_guid(nc), guid):
            return _unwrap(nc)
    return None


def _find_target_environment_by_guid(target: Any, guid: str) -> Any:
    """T023 — locate an Environment in target by GUID.

    Accessor confirmed: ``Environments`` (GrammarCategory.PH_ENVIRONMENT).
    """
    for env in target.Environments.GetAll():
        if _guid_eq(_obj_guid(env), guid):
            return _unwrap(env)
    return None


def _find_target_phon_rule_by_guid(target: Any, guid: str) -> Any:
    """T023 — locate a PhonologicalRule in target by GUID.

    Accessor confirmed: ``PhonRules`` (GrammarCategory.PHONOLOGICAL_RULES).
    """
    for pr in target.PhonRules.GetAll():
        if _guid_eq(_obj_guid(pr), guid):
            return _unwrap(pr)
    return None


def _find_target_stratum_by_guid(target: Any, guid: str) -> Any:
    """T023 — locate a Stratum in target by GUID.

    Accessor confirmed: ``Strata`` (GrammarCategory.STRATA).
    """
    for st in target.Strata.GetAll():
        if _guid_eq(_obj_guid(st), guid):
            return _unwrap(st)
    return None


def _find_target_gram_cat_by_guid(target: Any, guid: str) -> Any:
    """T023 — locate a GrammaticalCategory (IPartOfSpeech) in target by GUID.

    Accessor: ``POS`` (IPartOfSpeech), NOT ``GramCat`` (IFsFeatStrucType).
    categories.py:gram_categories_enumerate_source (L343-348) and
    gram_categories_plan_action (L367-370) both use target.POS.GetAll();
    the transfer path creates/enumerates IPartOfSpeech objects, so the
    preview finder must use the same subsystem or GUIDs will never match
    and the preview pane will be blank for every GRAM_CATEGORIES edit-copy.
    Uses recursive=True because POS has SubPossibilitiesOS sub-categories.
    """
    for gc in target.POS.GetAll(recursive=True):
        if _guid_eq(_obj_guid(gc), guid):
            return _unwrap(gc)
    return None


def _find_target_variant_type_by_guid(target: Any, guid: str) -> Any:
    """Locate a variant-entry type in target by GUID.

    MCP-confirmed accessor: ``handle.Cache.LangProject.LexDbOA.VariantEntryTypesOA``
    (ICmPossibilityList).  GramTrans categories.py uses the same path via
    ``_walk_possibilities_via_lexdb(target, "VariantEntryTypesOA")``.
    There is no ``project.VariantTypes`` or ``project.Variants`` accessor;
    the variant-type list lives under LexDbOA, not under a top-level ops attr.
    We reach it defensively via ``Cache.LangProject.LexDbOA``.
    """
    try:
        lex_db = target.Cache.LangProject.LexDbOA
        variant_list = getattr(lex_db, "VariantEntryTypesOA", None)
        if variant_list is None:
            return None
        # Recursive walk (mirrors categories._walk_possibilities)
        stack = list(getattr(variant_list, "PossibilitiesOS", []) or [])
        while stack:
            node = stack.pop(0)
            if _guid_eq(_obj_guid(node), guid):
                return _unwrap(node)
            subs = getattr(node, "SubPossibilitiesOS", None)
            if subs:
                for child in subs:
                    stack.append(child)
    except Exception:
        pass
    return None


def _find_target_inflection_feature_by_guid(target: Any, guid: str) -> Any:
    """Locate an IFsClosedFeature (inflection feature) in target by GUID.

    DEFECT FIX (spec 017): previously called InflectionClassGetAll() which
    returns IMoInflClass objects (inflection CLASSES), not IFsClosedFeature
    objects (inflection FEATURES).  The correct accessor is FeatureGetAll(),
    consistent with inflection_features_enumerate_source in categories.py.

    categories.py:inflection_features_enumerate_source uses FeatureGetAll();
    merge-preview must use the same iterator or the GUID lookup always misses.
    """
    try:
        for feat in target.InflectionFeatures.FeatureGetAll():
            if _guid_eq(_obj_guid(feat), guid):
                return _unwrap(feat)
    except Exception:
        pass
    return None


def _find_target_template_by_guid(target: Any, guid: str, owner_pos_guid: str) -> Any:
    """T024 — two-level owner-required finder for affix templates (R4a).

    The ONLY finder requiring a mandatory owner argument.  Locates the
    owner POS by GUID first, then scans its ``AffixTemplatesOS``.
    """
    owner_pos = _find_target_pos_by_guid(target, owner_pos_guid)
    if owner_pos is None:
        return None
    try:
        for tmpl in owner_pos.AffixTemplatesOS:
            if _guid_eq(_obj_guid(tmpl), guid):
                return _unwrap(tmpl)
    except Exception:
        pass
    return None


# ---- Direct-read fallbacks for gap categories (T026) -----------------------


def _direct_read_gap(obj: Any, include_optional_bool: bool = False) -> dict[str, Any] | None:
    """Read Name / Abbreviation / Description from a gap-category object.

    Returns ``{field: {ws_id: text}}`` shape (FR-008), or None on hard failure.
    Optional slot bool (``IMoAffixSlot.Optional``) is included when
    ``include_optional_bool=True``.
    """
    if obj is None:
        return None
    result: dict[str, Any] = {}
    try:
        for field_name in ("Name", "Abbreviation", "Description"):
            prop = getattr(obj, field_name, None)
            if prop is None:
                continue
            ws_dict: dict[str, str] = {}
            # Try get_String(ws_handle) approach first; fall back to StringCount
            try:
                count = getattr(prop, "StringCount", None)
                if count is not None:
                    for i in range(count):
                        try:
                            tss = prop.GetStringFromIndex(i)
                            ws_obj = (
                                getattr(tss, "WritingSystem", None)
                                or getattr(tss, "get_WritingSystem", lambda: None)()
                            )
                            if ws_obj is not None:
                                wid = _safe_ws_id(ws_obj)
                                if wid:
                                    ws_dict[wid] = str(getattr(tss, "Text", "") or "")
                        except Exception:
                            continue
                else:
                    # Duck-typed: try dict-like access
                    if hasattr(prop, "items"):
                        for k, v in prop.items():
                            ws_dict[str(k)] = str(v)
            except Exception:
                if hasattr(prop, "items"):
                    try:
                        for k, v in prop.items():
                            ws_dict[str(k)] = str(v)
                    except Exception:
                        pass
            if ws_dict:
                result[field_name] = ws_dict

        if include_optional_bool:
            opt_val = getattr(obj, "Optional", None)
            if opt_val is not None:
                result["Optional"] = bool(opt_val)

    except Exception as _exc:  # noqa: BLE001 — LCM exception types not statically known
        logging.debug("_direct_read_gap: hard failure reading gap object %r: %s", obj, _exc)
        return None

    return result if result else None


# ---- Per-category ops table (T022, module-level injectable) -----------------

# Each entry: (ops_attr, finder_fn, needs_owner, is_gap)
# ops_attr: attribute name on the project handle (flexicon project accessor).
# finder_fn: callable(target, guid[, owner_guid]) -> obj | None
# needs_owner: True for template (two-level finder).
# is_gap: True for Slots / PhonologicalFeatures / StemNames (direct-read fallback).
#
# Accessor names flagged "confirm" in data-model.md are CONFIRMED from the
# GrammarCategory enum in models.py and the prompt's confirmed accessors:
#   Environments -> .Environments  (PH_ENVIRONMENT, confirmed)
#   PhonRules    -> .PhonRules     (PHONOLOGICAL_RULES, confirmed)
#   Strata       -> .Strata        (STRATA, confirmed)
#   GramCat      -> .GramCat       (GRAM_CATEGORIES, confirmed)

_PROPS_TABLE: dict[str, tuple[Any, ...]] = {
    # (ops_attr, finder_fn, needs_owner, is_gap)
    "pos": ("POS", _find_target_pos_by_guid, False, False),
    "entry": ("LexEntry", _find_target_entry_by_guid, False, False),
    "sense": ("Senses", _find_target_sense_by_guid, True, False),
    "allomorph": ("Allomorphs", _find_target_allo_by_guid, True, False),
    # Finder-needed categories (T023) — net-new finders, NOT in conflict._OW_OPS
    "phoneme": ("Phonemes", _find_target_phoneme_by_guid, False, False),
    "natural_class": ("NaturalClasses", _find_target_natural_class_by_guid, False, False),
    "environment": ("Environments", _find_target_environment_by_guid, False, False),
    "phon_rule": ("PhonRules", _find_target_phon_rule_by_guid, False, False),
    "stratum": ("Strata", _find_target_stratum_by_guid, False, False),
    "gram_cat": ("GramCat", _find_target_gram_cat_by_guid, False, False),
    "inflection_feature": (
        "InflectionFeatures",
        _find_target_inflection_feature_by_guid,
        False,
        False,
    ),
    # Two-level owner-POS-dependent finder (T024) — GAP: no GetSyncableProperties.
    # IMoInflAffixTemplate exposes Name + Description only; direct-read via _find_gap_object.
    "template": (None, _find_target_template_by_guid, True, True),
    # Gap categories — direct-read fallback (T026)
    "slot": (None, None, True, True),
    "phon_feature": (None, None, False, True),
    "stem_name": (None, None, False, True),
    # variant_type: gap direct-read.  ICmPossibility/ILexEntryType exposes
    # Name + Abbreviation + Description (all IMultiUnicode/IMultiString).
    # ReverseName/ReverseAbbr exist only on ILexEntryInflType (subtype);
    # _direct_read_gap reads Name/Abbreviation/Description which covers both.
    # Accessor confirmed via categories.py: LexDbOA.VariantEntryTypesOA walk.
    "variant_type": (None, _find_target_variant_type_by_guid, False, True),
}


# Maps GrammarCategory.value (enum-value form the wizard emits) to the singular
# ops-key form used by _PROPS_TABLE. Values NOT in this map are assumed to already
# BE table keys (pos/entry/sense/allomorph pass through as identity). Values mapped
# to None have no standalone per-item preview (crew-validated: msa is an entry
# sub-object; inflection_classes/exception_features/variant_types/complex_form_types/
# adhoc_compound_rules/semantic_domains/custom_fields/writing_systems_check have no
# per-item diff path). None-mapped values return None gracefully (intended blank pane),
# which is now EXPLICIT rather than an accidental table-miss fallthrough.
_CATEGORY_VALUE_TO_KEY: dict[str, "str | None"] = {
    "affixes": "entry",
    "stems": "entry",
    "phonemes": "phoneme",
    "natural_classes": "natural_class",
    "phonological_rules": "phon_rule",
    "inflection_features": "inflection_feature",
    "slots": "slot",
    "affix_templates": "template",
    "gram_categories": "gram_cat",
    "strata": "stratum",
    "ph_environment": "environment",
    "phonological_features": "phon_feature",
    "stem_names": "stem_name",
    # variant_types: gap direct-read (ICmPossibility / ILexEntryType; Name +
    # Abbreviation + Description are all IMultiUnicode/IMultiString — the gap
    # direct-read path already handles these via _direct_read_gap).
    "variant_types": "variant_type",
    # explicit None — no standalone per-item preview:
    "msa": None,
    "writing_systems_check": None,
    "inflection_classes": None,
    "exception_features": None,
    "complex_form_types": None,
    "adhoc_compound_rules": None,
    "semantic_domains": None,
    "custom_fields": None,
}


def _resolve_category_key(category: str) -> "str | None":
    """Translate a GrammarCategory.value to its _PROPS_TABLE key.

    - Value present in _CATEGORY_VALUE_TO_KEY -> mapped key (may be None:
      the category has no standalone per-item preview).
    - Value absent from the map -> assumed already a table key (identity);
      pos/entry/sense/allomorph and the singular finder keys pass through.
    """
    if category in _CATEGORY_VALUE_TO_KEY:
        return _CATEGORY_VALUE_TO_KEY[category]
    return category


# ============================================================================
# props_for — LCM props fetch (FR-007, FR-008, T025 injectable seam)
# ============================================================================


def props_for(
    handle: Any,
    category: str,
    guid: str,
    *,
    index: dict[str, Any] | None = None,
    owner_guid: str = "",
    ops_table: dict[str, tuple[Any, ...]] | None = None,
    meta_out: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return a comparable ``{field: value}`` dict for an object of any category.

    ``handle`` is the flexicon project handle for the project containing the
    object.  ``category`` is the category key string (mirrors
    ``GrammarCategory.value`` style, e.g. ``"pos"``, ``"entry"``, ``"slot"``).

    The ``ops_table`` parameter is an injection seam (R6a, B5) for testing
    without LCM: pass a fake table to drive the covered-category path headlessly.
    When ``None``, the module-level ``_PROPS_TABLE`` is used.

    ``meta_out`` (spec-023, optional): if supplied and category resolves to
    ``"entry"``, the nested-gather meta ``{machine_key: (display_name,
    sort_key, indent)}`` is written into this dict in-place so the caller
    can pass it to ``diff_props(meta=...)``.

    Guarantees (FR-007, FR-008, SC-005):
    - Covered category: returns ``GetSyncableProperties(obj)`` dict; builds the
      GUID index once and reuses it.
    - Template category: uses ``owner_guid`` (owning POS GUID) for the two-level finder.
    - Gap category (slot / phon_feature / stem_name / variant_type): direct-read
      ``{field: {ws_id: text}}`` shape; ``None`` + note on hard failure (never raises).
    - Never raises to the caller.
    """
    table = ops_table if ops_table is not None else _PROPS_TABLE
    resolved = _resolve_category_key(category)
    if resolved is None:
        return None
    entry = table.get(resolved)
    if entry is None:
        return None

    ops_attr, finder_fn, needs_owner, is_gap = entry

    # -- Gap category: direct-read fallback -----------------------------------
    if is_gap:
        include_bool = resolved == "slot"
        try:
            obj = _find_gap_object(handle, resolved, guid, owner_guid)
            raw = _direct_read_gap(obj, include_optional_bool=include_bool)
            if raw is None:
                return None
            # R-b + R-c filtering applied after direct-read; custom fields not
            # applicable to gap categories (no GetAllFields equivalent).
            return _filter_props(raw)
        except Exception as _exc:
            logging.warning(
                "props_for: gap direct-read failed for category=%r guid=%r: %s: %s",
                resolved, guid, type(_exc).__name__, _exc,
            )
            return None

    # -- Covered / finder-needed categories via GetSyncableProperties ---------
    try:
        if needs_owner and resolved == "template":
            obj = finder_fn(handle, guid, owner_guid)
        elif needs_owner:
            obj = finder_fn(handle, guid, owner_guid) if owner_guid else finder_fn(handle, guid)
        else:
            obj = finder_fn(handle, guid)

        if obj is None:
            return None

        # GetSyncableProperties is on the ops accessor, not the object itself.
        # Resolve the ops wrapper from the handle.
        ops = _get_ops(handle, ops_attr, resolved)
        if ops is None:
            return None

        raw = ops.GetSyncableProperties(obj)
        if raw is None:
            return None

        # R-a: append custom fields (never replaces standard fields; exception-safe)
        _append_custom_fields(handle, obj, resolved, raw)

        # R-b + R-c: suppress empty fields and exclude bookkeeping keys.
        # Custom-field keys always pass R-c (_is_excluded_key never matches
        # "CustomField.*" / "Sense.*" / "Allomorph.*" / "Example.*" prefixes).
        filtered = _filter_props(raw)

        # spec-023: nested gather for entry category (affixes + stems).
        # Child machine keys (fingerprint-derived, contain \x1f) never collide
        # with scalar property names.
        if resolved == "entry" and meta_out is not None:
            try:
                child_notes: list[str] = []
                child_props, child_meta = _gather_entry_nested(handle, obj, child_notes)
                filtered.update(child_props)
                meta_out.update(child_meta)
                if child_notes:
                    for cn in child_notes:
                        logging.debug("_gather_entry_nested note: %s", cn)
            except Exception as _ne:
                logging.warning(
                    "props_for: _gather_entry_nested failed for guid=%r: %s: %s",
                    guid, type(_ne).__name__, _ne,
                )
        return filtered
    except Exception as _exc:
        logging.warning(
            "props_for: GetSyncableProperties failed for category=%r guid=%r: %s: %s",
            resolved, guid, type(_exc).__name__, _exc,
        )
        return None


def _get_ops(handle: Any, ops_attr: str | None, category: str) -> Any:
    """Resolve the operations wrapper from the project handle."""
    if ops_attr is None:
        return None
    return getattr(handle, ops_attr, None)


def _find_gap_object(handle: Any, category: str, guid: str, owner_guid: str) -> Any:
    """Attempt to locate a gap-category object by GUID using duck-typed traversal."""
    # For duck-typed fakes in tests, try direct GUID lookup on a dict-like handle
    if hasattr(handle, "get_gap_object"):
        return handle.get_gap_object(category, guid)
    # Template: locate via owner POS then AffixTemplatesOS (T024 gap path)
    if category == "template":
        try:
            owner_pos = _find_target_pos_by_guid(handle, owner_guid) if owner_guid else None
            if owner_pos is None:
                # Fallback: scan all POS
                for pos in handle.POS.GetAll(recursive=True):
                    for tmpl in getattr(pos, "AffixTemplatesOS", ()):
                        if _guid_eq(_obj_guid(tmpl), guid):
                            return _unwrap(tmpl)
            else:
                for tmpl in getattr(owner_pos, "AffixTemplatesOS", ()):
                    if _guid_eq(_obj_guid(tmpl), guid):
                        return _unwrap(tmpl)
        except Exception:
            pass
        return None
    # For real LCM: traverse appropriate collection
    if category == "slot":
        # Slots are owned by templates within a POS; owner_guid is template or POS GUID
        try:
            for pos in handle.POS.GetAll(recursive=True):
                for tmpl in getattr(pos, "AffixTemplatesOS", ()):
                    for slot_attr in ("PrefixSlotsRS", "SuffixSlotsRS"):
                        for sl in getattr(tmpl, slot_attr, ()):
                            if _guid_eq(_obj_guid(sl), guid):
                                return _unwrap(sl)
        except Exception:
            pass
        return None
    if category == "phon_feature":
        # PhonologicalFeatures: IFsClosedFeature in the feature system
        try:
            fs = getattr(handle, "PhonologicalFeatureSystem", None) or getattr(
                handle, "FeatureSystem", None
            )
            if fs is None:
                return None
            for feat in getattr(fs, "FeaturesOC", ()):
                if _guid_eq(_obj_guid(feat), guid):
                    return _unwrap(feat)
        except Exception:
            pass
        return None
    if category == "stem_name":
        try:
            for pos in handle.POS.GetAll(recursive=True):
                for sn in getattr(pos, "StemNamesOC", ()):
                    if _guid_eq(_obj_guid(sn), guid):
                        return _unwrap(sn)
        except Exception:
            pass
        return None
    if category == "variant_type":
        # Delegate to the dedicated finder (uses Cache.LangProject.LexDbOA path)
        return _find_target_variant_type_by_guid(handle, guid)
    return None


# ============================================================================
# R-c: User-editable field filter — system/bookkeeping key exclusion
# ============================================================================
# Justification per key (or pattern):
#  - Keys ending "Guid" (FeaturesGuid, PhonemeGuids, StratumGuid, etc.):
#    internal object-reference handles — not user-editable text.
#  - "Hvo", "Guid": raw database identity values — not user-facing.
#  - "DateCreated", "DateModified", and any key containing "DateModified":
#    system timestamps maintained by LCM.
#  - "HomographNumber": auto-assigned homograph disambiguator — not user-edited.
#  - "DoNotPublishInRC", "DoNotShowMainEntryInRC": publishing flags —
#    bookkeeping, not displayable content.
#  - "ImportResidue": raw import artifact string — not user-edited content.
#  - "Direction": for phonological rules this is an internal enum int
#    (0/1/2) with no user-meaningful label in the diff pane; excluded.
#    (If a future category exposes Direction as a user string, revisit here.)

_EXCLUDED_KEYS_EXACT: frozenset[str] = frozenset(
    {
        "Hvo",
        "Guid",
        "DateCreated",
        "DateModified",
        "HomographNumber",
        "DoNotPublishInRC",
        "DoNotShowMainEntryInRC",
        "ImportResidue",
        "Direction",
    }
)


def _is_excluded_key(key: str) -> bool:
    """Return True if the field key is a system/bookkeeping key (R-c)."""
    if key in _EXCLUDED_KEYS_EXACT:
        return True
    # Pattern: any key ending in "Guid" (covers FeaturesGuid, PhonemeGuids,
    # StratumGuid, etc.) — these are internal object-reference handles.
    if key.endswith("Guid") or key.endswith("Guids"):
        return True
    # Pattern: any key containing "DateModified" (timestamp variants)
    if "DateModified" in key:
        return True
    return False


# R-a normalization: custom-field values may arrive as raw COM string carriers.
#
# The installed flexicon build's ``CustomFieldOperations.GetValue`` returns a
# live ``ITsString`` COM object for String-type custom fields (contrary to its
# docstring, which claims a plain ``str``). Storing that object raw makes the
# diff pane render Python's default repr, e.g.
# ``<SIL.LCModel.Core.KernelInterfaces.ITsString object at 0x...>``, instead of
# the field text. Standard fields don't hit this because they flow through
# flexicon's ``GetSyncableProperties`` (already text-normalized).
def _coerce_cf_value(value: Any) -> Any:
    """Normalize a raw ``GetValue`` result to a comparable/displayable value.

    - ``ITsString`` single-string carriers -> ``.Text`` (may be None/empty).
    - Multi-string carriers -> best analysis alternative text.
    - ``str``/``int``/``float``/``bool``/``list``/``tuple``/``dict`` -> unchanged
      (already normalized by flexicon for Integer/Reference/MultiString fields).

    Never raises; unrecognized objects pass through untouched.
    """
    if value is None or isinstance(value, (str, int, float, bool, list, tuple, dict)):
        return value
    try:
        # ITsString exposes .Text directly (empty ITsString -> None/"").
        if hasattr(value, "Text"):
            return value.Text
        # Multi-string carrier fallback: reduce to the best analysis alternative.
        best = getattr(value, "BestAnalysisAlternative", None)
        if best is not None:
            return getattr(best, "Text", None)
    except Exception as _e:
        logging.debug("_coerce_cf_value: could not normalize %r: %s", type(value), _e)
    return value


# R-b: Empty-value suppression helpers
def _is_empty_value(v: Any) -> bool:
    """Return True if v is None, empty string, empty dict, or all-whitespace multistring."""
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == ""
    if isinstance(v, dict):
        if len(v) == 0:
            return True
        # multistring: all ws values empty/whitespace
        return all(
            (val is None or (isinstance(val, str) and val.strip() == ""))
            for val in v.values()
        )
    return False


def _filter_props(props: dict[str, Any]) -> dict[str, Any]:
    """Apply R-b (suppress empty) and R-c (exclude bookkeeping) to a props dict.

    Custom fields always pass R-c; R-b suppression still applies to them.
    """
    return {
        k: v
        for k, v in props.items()
        if not _is_excluded_key(k) and not _is_empty_value(v)
    }


# ============================================================================
# R-a: Custom-field extraction
# ============================================================================
# Namespacing scheme:
#   - Object-level custom fields (e.g. LexEntry): key = "CustomField.<FieldName>"
#     (prefixed to avoid collisions with standard props such as "Name")
#   - Child-object custom fields:
#       LexSense children  -> "Sense.<FieldName>"
#       MoForm children    -> "Allomorph.<FieldName>"
#       LexExampleSentence -> "Example.<FieldName>"
# Custom fields always pass R-c (user-editable by definition); R-b still applies.

# Maps category key -> owner_class string for GetAllFields
_CUSTOM_FIELD_OWNER_CLASS: dict[str, str] = {
    "entry": "LexEntry",
    "sense": "LexSense",
    "allomorph": "MoForm",
    "phoneme": "PhPhoneme",
    "natural_class": "PhNaturalClass",
    "environment": "PhEnvironment",
    "phon_rule": "PhRegularRule",
    "gram_cat": "FsFeatStrucType",
    "inflection_feature": "FsClosedFeature",
    "pos": "PartOfSpeech",
}


def _read_custom_fields(handle: Any, obj: Any, owner_class: str, prefix: str) -> dict[str, Any]:
    """Read custom fields for one object, returning namespaced dict entries.

    Never raises — all exceptions are caught and logged at DEBUG.
    """
    result: dict[str, Any] = {}
    try:
        cf_ops = getattr(handle, "CustomFields", None)
        if cf_ops is None:
            return result
        fields_iter = cf_ops.GetAllFields(owner_class)
        if fields_iter is None:
            return result
        for item in fields_iter:
            try:
                # GetAllFields may return (flid, field_name) tuples or just names
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    _flid, field_name = item[0], item[1]
                else:
                    field_name = str(item)
                value = _coerce_cf_value(cf_ops.GetValue(obj, field_name))
                if not _is_empty_value(value):
                    result[prefix + field_name] = value
            except Exception as _e:
                logging.debug("_read_custom_fields: skipping field %r: %s", item, _e)
    except Exception as _exc:
        logging.debug(
            "_read_custom_fields: failed reading custom fields for %r/%r: %s",
            owner_class, obj, _exc
        )
    return result


# ============================================================================
# spec-023: Nested entry gather
# ============================================================================
# KeyMeta = (display_name: str, sort_key: tuple, indent: int)
# Returned in the meta dict alongside props so diff_props can stamp FieldDiffs.
#
# Kind rank for sort_key[0]: entry=0, sense=1, msa=2, allomorph=3
# (matches FLEx top-to-bottom layout per data-model.md §3).
# ============================================================================

_KIND_RANK: dict[str, int] = {"entry": 0, "sense": 1, "msa": 2, "allomorph": 3}


def _ms_to_dict(prop: Any) -> dict[str, str]:
    """Coerce an IMultiUnicode / IMultiString prop to {ws_id: text} dict.

    Returns {} on any failure.  Same strategy as _direct_read_gap but
    returns a plain dict rather than nesting under a field name.
    """
    ws_dict: dict[str, str] = {}
    if prop is None:
        return ws_dict
    # Duck-typed dict (test fakes)
    if isinstance(prop, dict):
        return {str(k): str(v) for k, v in prop.items() if v}
    try:
        count = getattr(prop, "StringCount", None)
        if count is not None:
            for i in range(count):
                try:
                    tss = prop.GetStringFromIndex(i)
                    ws_obj = (
                        getattr(tss, "WritingSystem", None)
                        or getattr(tss, "get_WritingSystem", lambda: None)()
                    )
                    if ws_obj is not None:
                        wid = _safe_ws_id(ws_obj)
                        if wid:
                            text = str(getattr(tss, "Text", "") or "")
                            if text:
                                ws_dict[wid] = text
                except Exception:
                    continue
        elif hasattr(prop, "items"):
            for k, v in prop.items():
                if v:
                    ws_dict[str(k)] = str(v)
    except Exception:
        if hasattr(prop, "items"):
            try:
                for k, v in prop.items():
                    if v:
                        ws_dict[str(k)] = str(v)
            except Exception:
                pass
    return ws_dict


def _best_analysis_text(prop: Any) -> str:
    """Extract single best-analysis text from IMultiUnicode/IMultiString."""
    if prop is None:
        return ""
    if isinstance(prop, str):
        return prop
    if isinstance(prop, dict):
        return next(iter(prop.values()), "") if prop else ""
    try:
        best = getattr(prop, "BestAnalysisAlternative", None)
        if best is not None:
            return getattr(best, "Text", None) or ""
    except Exception:
        pass
    try:
        best = getattr(prop, "BestVernacularAlternative", None)
        if best is not None:
            return getattr(best, "Text", None) or ""
    except Exception:
        pass
    return ""


def _default_vern_ws(handle: Any) -> Any:
    """Return DefaultVernWs handle from project Cache, or None."""
    try:
        return handle.Cache.DefaultVernWs
    except Exception:
        return None


def _morph_type_label(allo: Any) -> str:
    """Morph type abbreviation for an allomorph (e.g. 'prefix')."""
    try:
        mt = getattr(allo, "MorphTypeRA", None)
        if mt is None:
            return ""
        abbr = getattr(mt, "Abbreviation", None) or getattr(mt, "Name", None)
        if abbr is None:
            return ""
        return _best_analysis_text(abbr)
    except Exception:
        return ""


def _env_labels(allo: Any) -> list[str]:
    """Collect environment strings from EnvironmentsRC as list[str]."""
    out: list[str] = []
    try:
        envs = getattr(allo, "EnvironmentsRC", None)
        if envs is None:
            return out
        for env in envs:
            try:
                str_rep = getattr(env, "StringRepresentation", None)
                if str_rep is not None:
                    text = _best_analysis_text(str_rep)
                    if not text:
                        text = str(str_rep)
                    if text:
                        out.append(text)
            except Exception:
                continue
    except Exception:
        pass
    return out


def _msa_label_for_gather(msa: Any) -> str:
    """POS abbrev + slot names label for a sense's MSA (e.g. 'n:NC').

    Uses the same logic as fingerprints.msa_label_from_obj without importing
    that module here (to keep the import chain simple).
    """
    if __package__:
        from .fingerprints import msa_label_from_obj  # lazy; Qt-free
    else:
        from fingerprints import msa_label_from_obj  # type: ignore
    return msa_label_from_obj(msa)


def _gather_entry_nested(
    handle: Any,
    obj: Any,
    notes_out: list[str],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Gather nested entry fields (senses, allomorphs, MSAs) into flat dicts.

    Returns
    -------
    props:
        Flat ``{machine_key: value}`` dict of child fields to MERGE with the
        entry-scalar props already gathered by GetSyncableProperties.
    meta:
        ``{machine_key: (display_name, sort_key, indent)}`` — consumed by
        ``diff_props`` to stamp FieldDiff ordering/labeling.

    Guarantees:
    - G1: non-empty sense, allomorph, MSA fields are included.
    - G2: join keys are fingerprint-derived (content-only) so source/target
      counterparts land on the same key.
    - G4: empty fields and empty child groups contribute nothing.
    - G6: single-field/child read failures are contained; notes_out receives a
      visible notice; the rest of the entry still gathers.
    - G7: no live LCM objects in the returned dicts.
    """
    if __package__:
        from .fingerprints import (  # lazy; Qt-free
            allomorph_token_from_obj,
            sense_token,
            msa_token,
            machine_key,
        )
    else:
        from fingerprints import (  # type: ignore
            allomorph_token_from_obj,
            sense_token,
            msa_token,
            machine_key,
        )

    props: dict[str, Any] = {}
    meta: dict[str, Any] = {}
    ws_handle = _default_vern_ws(handle)

    # ------------------------------------------------------------------
    # Helper: register one child field
    # ------------------------------------------------------------------
    def _add_child(
        kind: str,
        tok: tuple,
        field_label: str,
        value: Any,
        kind_rank: int,
        ordinal: int,
        field_order: int,
        display_prefix: str,
    ) -> None:
        if _is_empty_value(value):
            return
        mk = machine_key(kind, tok, field_label)
        props[mk] = value
        dn = f"{display_prefix} > {field_label}"
        sk = ((kind_rank, ordinal), field_order)
        meta[mk] = (dn, sk, 1)

    # ------------------------------------------------------------------
    # Senses
    # ------------------------------------------------------------------
    senses = []
    try:
        senses = list(getattr(obj, "SensesOS", []) or [])
    except Exception as _e:
        notes_out.append(f"Senses: could not read sense list ({type(_e).__name__})")

    # Collect gloss texts first to detect collisions
    sense_gloss_raw: list[str] = []
    for sense in senses:
        try:
            gloss_prop = getattr(sense, "Gloss", None)
            sense_gloss_raw.append(_best_analysis_text(gloss_prop) if gloss_prop is not None else "")
        except Exception:
            sense_gloss_raw.append("")

    # Assign ordinal suffixes for colliding glosses
    gloss_counts: dict[str, int] = {}
    gloss_ordinals: list[str] = []
    for g in sense_gloss_raw:
        gloss_counts[g] = gloss_counts.get(g, 0) + 1
    gloss_seen: dict[str, int] = {}
    for g in sense_gloss_raw:
        gloss_seen[g] = gloss_seen.get(g, 0) + 1
        suffix = f"#{gloss_seen[g]}" if gloss_counts[g] > 1 else ""
        gloss_ordinals.append(suffix)

    for s_idx, sense in enumerate(senses):
        ordinal = s_idx + 1
        gloss_text = sense_gloss_raw[s_idx]
        tok = sense_token(gloss_text, gloss_ordinals[s_idx])
        display_prefix = f"Sense {ordinal}"

        # Gloss
        try:
            gloss_prop = getattr(sense, "Gloss", None)
            if gloss_prop is not None:
                _add_child("sense", tok, "Gloss", _ms_to_dict(gloss_prop), 1, ordinal, 0, display_prefix)
        except Exception as _e:
            notes_out.append(f"Sense {ordinal} Gloss: could not read ({type(_e).__name__})")

        # Definition
        try:
            def_prop = getattr(sense, "Definition", None)
            if def_prop is not None:
                _add_child("sense", tok, "Definition", _ms_to_dict(def_prop), 1, ordinal, 1, display_prefix)
        except Exception as _e:
            notes_out.append(f"Sense {ordinal} Definition: could not read ({type(_e).__name__})")

        # MSA label
        try:
            msa_obj = getattr(sense, "MorphoSyntaxAnalysisRA", None)
            if msa_obj is not None:
                label = _msa_label_for_gather(msa_obj)
                if label:
                    msa_tok = msa_token(label)
                    _add_child("msa", msa_tok, "GramInfo", label, 2, ordinal, 0, f"{display_prefix} > Gram. Info")
        except Exception as _e:
            notes_out.append(f"Sense {ordinal} GramInfo: could not read ({type(_e).__name__})")

    # ------------------------------------------------------------------
    # Allomorphs (LexemeForm + AlternateForms)
    # ------------------------------------------------------------------
    allos: list[Any] = []
    try:
        lf = getattr(obj, "LexemeFormOA", None)
        if lf is not None:
            allos.append(lf)
    except Exception as _e:
        notes_out.append(f"LexemeForm: could not read ({type(_e).__name__})")
    try:
        alt_forms = list(getattr(obj, "AlternateFormsOS", []) or [])
        allos.extend(alt_forms)
    except Exception as _e:
        notes_out.append(f"AlternateForms: could not read list ({type(_e).__name__})")

    for a_idx, allo in enumerate(allos):
        ordinal = a_idx + 1
        display_prefix = f"Allomorph {ordinal}"
        try:
            tok = allomorph_token_from_obj(allo, ws_handle)
        except Exception:
            tok = ("allomorph", "", "")

        # Form (multi-WS dict)
        try:
            form_prop = getattr(allo, "Form", None)
            if form_prop is not None:
                _add_child("allomorph", tok, "Form", _ms_to_dict(form_prop), 3, ordinal, 0, display_prefix)
        except Exception as _e:
            notes_out.append(f"Allomorph {ordinal} Form: could not read ({type(_e).__name__})")

        # Morph type
        try:
            mt_label = _morph_type_label(allo)
            if mt_label:
                _add_child("allomorph", tok, "MorphType", mt_label, 3, ordinal, 1, display_prefix)
        except Exception as _e:
            notes_out.append(f"Allomorph {ordinal} MorphType: could not read ({type(_e).__name__})")

        # Environments
        try:
            envs = _env_labels(allo)
            if envs:
                _add_child("allomorph", tok, "Environments", envs, 3, ordinal, 2, display_prefix)
        except Exception as _e:
            notes_out.append(f"Allomorph {ordinal} Environments: could not read ({type(_e).__name__})")

        # Comment (IMultiString)
        try:
            comment_prop = getattr(allo, "Comment", None)
            if comment_prop is not None:
                _add_child("allomorph", tok, "Comment", _ms_to_dict(comment_prop), 3, ordinal, 3, display_prefix)
        except Exception as _e:
            notes_out.append(f"Allomorph {ordinal} Comment: could not read ({type(_e).__name__})")

    return props, meta


def _append_custom_fields(handle: Any, obj: Any, category: str, props: dict[str, Any]) -> None:
    """Append custom fields (and child custom fields for entry) to props in-place.

    Never raises. Silently skips if the category has no known owner_class.
    """
    try:
        owner_class = _CUSTOM_FIELD_OWNER_CLASS.get(category)
        if owner_class is None:
            return

        # Object-level custom fields — prefix "CustomField."
        obj_cf = _read_custom_fields(handle, obj, owner_class, "CustomField.")
        props.update(obj_cf)

        # Child walks: only for "entry" (LexEntry children)
        if category == "entry":
            # Senses -> "Sense.<FieldName>"
            try:
                for sense in getattr(obj, "SensesOS", ()):
                    cf = _read_custom_fields(handle, sense, "LexSense", "Sense.")
                    for k, v in cf.items():
                        if k not in props:  # first sense wins on collision
                            props[k] = v
            except Exception as _e:
                logging.debug("_append_custom_fields: SensesOS walk error: %s", _e)
            # AlternateForms -> "Allomorph.<FieldName>"
            try:
                for form in getattr(obj, "AlternateFormsOS", ()):
                    cf = _read_custom_fields(handle, form, "MoForm", "Allomorph.")
                    for k, v in cf.items():
                        if k not in props:
                            props[k] = v
            except Exception as _e:
                logging.debug("_append_custom_fields: AlternateFormsOS walk error: %s", _e)
            # Examples (via senses) -> "Example.<FieldName>"
            try:
                for sense in getattr(obj, "SensesOS", ()):
                    for ex in getattr(sense, "ExamplesOS", ()):
                        cf = _read_custom_fields(handle, ex, "LexExampleSentence", "Example.")
                        for k, v in cf.items():
                            if k not in props:
                                props[k] = v
            except Exception as _e:
                logging.debug("_append_custom_fields: ExamplesOS walk error: %s", _e)
    except Exception as _exc:
        logging.debug("_append_custom_fields: outer failure: %s", _exc)


# ============================================================================
# MergePreviewService  (FR-011, FR-012)
# ============================================================================


class MergePreviewService:
    """Qt-free cache/orchestrator for merge previews.

    Holds source/target project handles, the ws-role classifier (from
    ``ws_role_map``), a lazy target-GUID index, a props-dict cache, and a
    preview cache keyed by the **4-tuple** ``(category, source_guid,
    target_guid, mode)`` (A1, SC-006, FR-011).

    All cached values are plain Python dicts or ``MergePreview`` instances;
    no live LCM objects are retained (FR-012, constitution I).
    """

    def __init__(
        self,
        source_handle: Any,
        target_handle: Any,
        ws_role_of: Callable[[str], WsRole | None] | None = None,
        *,
        ops_table: dict[str, tuple[Any, ...]] | None = None,
    ) -> None:
        """Initialise the service.

        ``ws_role_of`` is a callable ``ws_id -> Optional[WsRole]`` built from
        ``ws_role_map(source_project).get`` or equivalent.  Defaults to a
        no-role function when omitted.

        ``ops_table`` is the injectable seam (R6a/B5) for testing without LCM.
        """
        self._source = source_handle
        self._target = target_handle
        self._ws_role_of: Callable[[str], WsRole | None] = (
            ws_role_of if ws_role_of is not None else lambda _wid: None
        )
        self._ops_table = ops_table  # None -> module default
        # Preview cache: (category, source_guid, target_guid, mode) -> MergePreview
        self._preview_cache: dict[tuple[str, str, str, str], MergePreview] = {}
        # Props-dict cache: (side, category, guid, owner_guid) -> Optional[dict]
        self._props_cache: dict[tuple[str, str, str, str], dict[str, Any] | None] = {}
        # Meta cache (spec-023): same key -> Optional[dict] of nested-child meta
        self._meta_cache: dict[tuple[str, str, str, str], dict[str, Any] | None] = {}

    # -- Public API -----------------------------------------------------------

    def preview_for(
        self,
        category: str,
        source_guid: str,
        target_guid: str,
        status: str,
        mode: str,
        owner_guid: str = "",
    ) -> MergePreview:
        """Compute or return cached preview for the given 4-tuple key (A1).

        Re-link (different ``target_guid``) and a resolution change (different
        ``mode``) are each distinct cache keys so both produce one new entry.
        ``status`` is part of the **value**, not the key (FR-011).

        Caches property dicts, never LCM objects (FR-012).
        """
        key: tuple[str, str, str, str] = (category, source_guid, target_guid, mode)
        if key in self._preview_cache:
            return self._preview_cache[key]

        src_props = self._fetch_props("source", category, source_guid, owner_guid)
        tgt_props: dict[str, Any] | None
        if mode == NEW or not target_guid:
            tgt_props = None
        else:
            tgt_props = self._fetch_props("target", category, target_guid, owner_guid)

        # spec-023: pass source-side meta (nested child ordering/labels) to diff_props.
        # Target meta is not needed — diff_props uses the source meta to label all
        # matched keys (both source-only and matched pairs share the same key).
        src_meta = self._meta_cache.get(("source", category, source_guid, owner_guid))

        preview = diff_props(
            src_props or {},
            tgt_props,
            mode,
            self._ws_role_of,
            status=status,
            meta=src_meta if src_meta else None,
        )
        self._preview_cache[key] = preview
        return preview

    def invalidate(self) -> None:
        """Clear all caches for wizard page re-entry (SC-006, US4)."""
        self._preview_cache.clear()
        self._props_cache.clear()
        self._meta_cache.clear()

    # -- Internal helpers -----------------------------------------------------

    def _fetch_props(
        self, side: str, category: str, guid: str, owner_guid: str
    ) -> dict[str, Any] | None:
        """Fetch and cache a property dict (dicts only, never LCM objects).

        For entry-category fetches, also populates ``_meta_cache`` with the
        nested-gather meta (spec-023, G3).
        """
        cache_key: tuple[str, str, str, str] = (side, category, guid, owner_guid)
        if cache_key in self._props_cache:
            return self._props_cache[cache_key]

        handle = self._source if side == "source" else self._target
        # For entry category, collect nested-child meta alongside props.
        resolved = _resolve_category_key(category)
        collect_meta = resolved == "entry"
        meta_buf: dict[str, Any] = {} if collect_meta else {}  # always a new dict
        result = props_for(
            handle,
            category,
            guid,
            owner_guid=owner_guid,
            ops_table=self._ops_table,
            meta_out=meta_buf if collect_meta else None,
        )
        # Cache dicts only; never retain LCM handles (FR-012)
        self._props_cache[cache_key] = result
        if collect_meta:
            self._meta_cache[cache_key] = meta_buf if meta_buf else None
        return result

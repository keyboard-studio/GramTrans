"""Writing-system font registry (spec 011 -- app-wide per-WS rendering).

The GramTrans wizard shows *source*-project data: phoneme graphemes and lexeme
forms in the vernacular WS, glosses / feature names in the analysis WS, IPA
symbols in the phonology (fonipa) WS.  FLEx stores a font per writing system;
this module reads those fonts once from a flexicon FLExProject and exposes them
by *role* so the UI can render each run of a label in the font FLEx defines for
that WS.

Deliberately Qt-free: the registry is plain data (``WsFont`` dicts keyed by
``WsRole``) so it is unit-testable headless.  The UI layer
(``Lib/ui/ws_font_delegate``) turns a ``WsFont`` into a ``QFont`` and paints it.

Labels carry per-run WS provenance as a ``tuple[LabelRun, ...]`` where each
``LabelRun`` is ``(text, role)`` and ``role is None`` means "no WS -- use the
widget's default font" (chrome, separators, guid fallbacks).  ``"".join(text
for text, _ in runs)`` always reconstructs the flat label string, so every
existing casefold / target-match path keeps working unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple


class WsRole(Enum):
    """Semantic role a run of display text plays, resolved to a concrete WS.

    Labels are built from "best alternative" accessors (not a specific ws_id),
    so provenance is captured as a role and the registry resolves the role to
    the source project's default WS for that role (IPA -> the fonipa WS).
    """

    VERNACULAR = "vernacular"
    ANALYSIS = "analysis"
    IPA = "ipa"


# (text, role) -- role None => render in the widget's default font.
LabelRun = Tuple[str, Optional[WsRole]]

_DEFAULT_SIZE_PT = 10.0


@dataclass(frozen=True)
class WsFont:
    """FLEx-defined font for one writing system."""

    ws_id: str
    font_name: str
    size_pt: float = _DEFAULT_SIZE_PT
    rtl: bool = False


def runs_to_text(runs: Tuple[LabelRun, ...]) -> str:
    """Reconstruct the flat label string from its runs."""
    return "".join(text for text, _role in runs)


class WsFontRegistry:
    """Maps ``WsRole`` -> ``WsFont`` for one project.

    Construct via :meth:`from_project` (tolerant of a missing / partial
    flexicon surface -- any failure degrades to an empty registry, and the UI
    then renders in its default font).  :meth:`empty` yields a registry that
    resolves every role to ``None``.
    """

    def __init__(self, fonts: Dict[WsRole, WsFont]):
        self._fonts: Dict[WsRole, WsFont] = dict(fonts)

    def __bool__(self) -> bool:
        return bool(self._fonts)

    def font_for(self, role: Optional[WsRole]) -> Optional[WsFont]:
        """Return the ``WsFont`` for a role, or ``None`` (role unset / unknown).

        IPA falls back to the vernacular font when the project has no fonipa WS,
        because IPA glyphs need a Unicode-rich font the vernacular WS is far more
        likely to supply than the UI default.
        """
        if role is None:
            return None
        font = self._fonts.get(role)
        if font is None and role is WsRole.IPA:
            return self._fonts.get(WsRole.VERNACULAR)
        return font

    # -- construction -----------------------------------------------------
    @classmethod
    def empty(cls) -> "WsFontRegistry":
        return cls({})

    @classmethod
    def from_project(cls, project) -> "WsFontRegistry":
        """Read default-vernacular, default-analysis and IPA fonts from a project.

        Every accessor is guarded: a project that lacks ``WritingSystems`` (or a
        accessors that raise) yields an empty registry rather than crashing
        the wizard.  Mirrors the defensive posture of ``ws_mapping._enumerate_ws``.
        """
        if project is None:
            return cls.empty()
        ws_ops = getattr(project, "WritingSystems", None)
        if ws_ops is None:
            return cls.empty()

        fonts: Dict[WsRole, WsFont] = {}

        vern_ws = _call(ws_ops, "GetDefaultVernacular")
        anal_ws = _call(ws_ops, "GetDefaultAnalysis")

        vf = _ws_font(ws_ops, vern_ws)
        if vf is not None:
            fonts[WsRole.VERNACULAR] = vf
        af = _ws_font(ws_ops, anal_ws)
        if af is not None:
            fonts[WsRole.ANALYSIS] = af

        ipa_ws = _find_ipa_ws(ws_ops, prefer_id=vf.ws_id if vf else None)
        ipf = _ws_font(ws_ops, ipa_ws)
        if ipf is not None:
            fonts[WsRole.IPA] = ipf

        return cls(fonts)


# ---------------------------------------------------------------------------
# Internal helpers -- all tolerant of the flexicon surface being absent.
# ---------------------------------------------------------------------------

def _call(obj, method: str, *args):
    """Invoke ``obj.method(*args)``; return None on any failure."""
    fn = getattr(obj, method, None)
    if fn is None:
        return None
    try:
        return fn(*args)
    except Exception:  # noqa: BLE001 -- flexicon accessor / LCM cast may raise
        return None


def _ws_id(ws) -> str:
    if ws is None:
        return ""
    for attr in ("Id", "id"):
        val = getattr(ws, attr, None)
        if val:
            return str(val)
    return ""


def _ws_font(ws_ops, ws) -> Optional[WsFont]:
    """Build a WsFont from a WS object via GetFontName/Size/RightToLeft."""
    if ws is None:
        return None
    ws_id = _ws_id(ws)
    name = _call(ws_ops, "GetFontName", ws)
    if not name:
        return None
    size = _call(ws_ops, "GetFontSize", ws)
    try:
        size_pt = float(size) if size else _DEFAULT_SIZE_PT
    except (TypeError, ValueError):
        size_pt = _DEFAULT_SIZE_PT
    rtl = bool(_call(ws_ops, "GetRightToLeft", ws))
    return WsFont(ws_id=ws_id, font_name=str(name), size_pt=size_pt, rtl=rtl)


def _find_ipa_ws(ws_ops, *, prefer_id: Optional[str]):
    """Return the vernacular WS whose tag marks it IPA (BCP-47 ``fonipa``).

    Prefers a fonipa WS sharing the default vernacular's language prefix (e.g.
    ``koh-fonipa`` when the default vernacular is ``koh``); otherwise the first
    fonipa WS found.  Returns None when the project has no IPA WS.
    """
    candidates = _call(ws_ops, "GetVernacular") or _call(ws_ops, "GetAll") or ()
    fonipa = []
    try:
        for ws in candidates:
            wid = _ws_id(ws).lower()
            if "fonipa" in wid.split("-"):
                fonipa.append(ws)
    except TypeError:
        return None
    if not fonipa:
        return None
    if prefer_id:
        prefix = prefer_id.split("-", 1)[0].lower()
        for ws in fonipa:
            if _ws_id(ws).split("-", 1)[0].lower() == prefix:
                return ws
    return fonipa[0]

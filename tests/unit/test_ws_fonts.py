"""WsFontRegistry -- reads FLEx per-WS fonts by role (spec 011).

Fakes mirror the flexlibs2 fork's WritingSystems surface: GetDefaultVernacular /
GetDefaultAnalysis / GetVernacular return WS objects, and GetFontName /
GetFontSize / GetRightToLeft take a WS and return its FLEx-defined font.
"""
from __future__ import annotations

from gramtrans.Lib.ws_fonts import (
    WsFont,
    WsFontRegistry,
    WsRole,
    runs_to_text,
)


class _WS:
    def __init__(self, id_, font="", size=0, rtl=False, vernacular=True):
        self.Id = id_
        self._font = font
        self._size = size
        self._rtl = rtl
        self.IsVernacular = vernacular


class _WSOps:
    """Duck-types the fork's project.WritingSystems accessor."""

    def __init__(self, *, default_vern, default_anal, all_ws):
        self._dv = default_vern
        self._da = default_anal
        self._all = list(all_ws)

    def GetDefaultVernacular(self):
        return self._dv

    def GetDefaultAnalysis(self):
        return self._da

    def GetAll(self):
        return list(self._all)

    def GetVernacular(self):
        return [w for w in self._all if getattr(w, "IsVernacular", True)]

    def GetFontName(self, ws):
        return ws._font

    def GetFontSize(self, ws):
        return ws._size

    def GetRightToLeft(self, ws):
        return ws._rtl


class _Project:
    def __init__(self, ws_ops):
        self.WritingSystems = ws_ops


def _project(*, dv, da, all_ws):
    return _Project(_WSOps(default_vern=dv, default_anal=da, all_ws=all_ws))


# --- happy path ------------------------------------------------------------

def test_reads_vernacular_and_analysis_fonts_by_role():
    vern = _WS("koh", font="Charis SIL", size=14)
    anal = _WS("en", font="Calibri", size=11, vernacular=False)
    reg = WsFontRegistry.from_project(_project(dv=vern, da=anal, all_ws=[vern, anal]))

    v = reg.font_for(WsRole.VERNACULAR)
    assert v == WsFont(ws_id="koh", font_name="Charis SIL", size_pt=14.0, rtl=False)
    a = reg.font_for(WsRole.ANALYSIS)
    assert a.font_name == "Calibri" and a.size_pt == 11.0


def test_rtl_flag_is_captured():
    vern = _WS("ar", font="Scheherazade", size=16, rtl=True)
    anal = _WS("en", font="Calibri", size=11, vernacular=False)
    reg = WsFontRegistry.from_project(_project(dv=vern, da=anal, all_ws=[vern, anal]))
    assert reg.font_for(WsRole.VERNACULAR).rtl is True


# --- IPA detection ---------------------------------------------------------

def test_ipa_role_resolves_to_fonipa_ws():
    vern = _WS("koh", font="Charis SIL", size=14)
    ipa = _WS("koh-fonipa", font="Doulos SIL", size=14)
    anal = _WS("en", font="Calibri", vernacular=False)
    reg = WsFontRegistry.from_project(
        _project(dv=vern, da=anal, all_ws=[vern, ipa, anal])
    )
    assert reg.font_for(WsRole.IPA).font_name == "Doulos SIL"


def test_ipa_prefers_fonipa_matching_default_vernacular_prefix():
    vern = _WS("koh", font="Charis SIL")
    other_ipa = _WS("qaa-fonipa", font="Andika")
    koh_ipa = _WS("koh-fonipa", font="Doulos SIL")
    anal = _WS("en", font="Calibri", vernacular=False)
    reg = WsFontRegistry.from_project(
        _project(dv=vern, da=anal, all_ws=[vern, other_ipa, koh_ipa, anal])
    )
    assert reg.font_for(WsRole.IPA).ws_id == "koh-fonipa"


def test_ipa_falls_back_to_vernacular_font_when_no_fonipa_ws():
    vern = _WS("koh", font="Charis SIL", size=14)
    anal = _WS("en", font="Calibri", vernacular=False)
    reg = WsFontRegistry.from_project(_project(dv=vern, da=anal, all_ws=[vern, anal]))
    ipa = reg.font_for(WsRole.IPA)
    assert ipa is not None and ipa.font_name == "Charis SIL"


# --- tolerance / degradation ----------------------------------------------

def test_none_project_yields_empty_registry():
    reg = WsFontRegistry.from_project(None)
    assert not reg
    assert reg.font_for(WsRole.VERNACULAR) is None


def test_project_without_writing_systems_degrades_gracefully():
    reg = WsFontRegistry.from_project(object())
    assert not reg


def test_blank_font_name_is_skipped():
    vern = _WS("koh", font="", size=14)  # font unset in FLEx
    anal = _WS("en", font="Calibri", vernacular=False)
    reg = WsFontRegistry.from_project(_project(dv=vern, da=anal, all_ws=[vern, anal]))
    assert reg.font_for(WsRole.VERNACULAR) is None
    assert reg.font_for(WsRole.ANALYSIS).font_name == "Calibri"


def test_accessor_that_raises_does_not_crash():
    class _Boom:
        def GetDefaultVernacular(self):
            raise RuntimeError("LCM cast failed")

        def GetDefaultAnalysis(self):
            raise RuntimeError("LCM cast failed")

    reg = WsFontRegistry.from_project(_Project(_Boom()))
    assert not reg


def test_role_none_returns_no_font():
    reg = WsFontRegistry.empty()
    assert reg.font_for(None) is None


# --- runs_to_text ----------------------------------------------------------

def test_runs_to_text_reconstructs_flat_label():
    runs = (("y", WsRole.VERNACULAR), (" ", None), ("/j/", WsRole.IPA))
    assert runs_to_text(runs) == "y /j/"

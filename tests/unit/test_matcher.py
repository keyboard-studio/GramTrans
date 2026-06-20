"""Unit tests for Lib/matcher.py — Phase 1 three-step lookup.

Coverage:
  T-M01  GUID direct hit -> Match.via == "guid"
  T-M02  identity_remap fallback hit -> Match.via == "identity_remap"
  T-M03  Fingerprint fallback hit -> Match.via == "fingerprint"
  T-M04  via == "none" when nothing matches
  T-M05  FINGERPRINT_FNS registry has entries for MSA and ALLOMORPH
  T-M06  Match.__post_init__ rejects invalid via values
  T-M07  fingerprint_for_msa returns correct tuple shape on a fake MSA
  T-M08  fingerprint_for_allomorph returns correct tuple shape on a fake allomorph
"""
from __future__ import annotations

import pytest

from gramtrans.Lib.matcher import (
    FINGERPRINT_FNS,
    Match,
    fingerprint_for_allomorph,
    fingerprint_for_msa,
    lookup_target,
)
from gramtrans.Lib.models import GrammarCategory


# ---------------------------------------------------------------------------
# Fake helpers — no LCM imports needed
# ---------------------------------------------------------------------------

class _Guid:
    """Minimal GUID stand-in whose str() returns the guid string."""
    def __init__(self, value: str) -> None:
        self._value = value
    def __str__(self) -> str:
        return self._value


class _FakeObj:
    """Minimal LCM object stand-in carrying a Guid attribute."""
    def __init__(self, guid: str) -> None:
        self.Guid = _Guid(guid)


class _FakeTarget:
    """Target project double that stores objects keyed by GUID.

    Supports both lookup protocols used by _find_by_guid:
      - get_object_by_guid(guid, category) -> obj | None
      - iter_objects(category) -> Iterable[obj]  (for fingerprint scan)
    """
    def __init__(self, objects: list) -> None:
        self._by_guid = {str(o.Guid): o for o in objects}
        self._objects = objects

    def get_object_by_guid(self, guid: str, category) -> object:
        return self._by_guid.get(guid)

    def iter_objects(self, category) -> list:
        return self._objects


class _IterOnlyTarget:
    """Target that exposes iter_objects but NOT get_object_by_guid.

    Used to exercise the linear-scan path in _find_by_guid.
    """
    def __init__(self, objects: list) -> None:
        self._objects = objects

    def iter_objects(self, category) -> list:
        return self._objects


# ---------------------------------------------------------------------------
# Fake MSA and Allomorph for fingerprint tests
# ---------------------------------------------------------------------------

class _FakeMSA(_FakeObj):
    def __init__(self, guid, owner_guid, pos_guid="", slot_guids=()):
        super().__init__(guid)
        self.Owner = _FakeObj(owner_guid)
        self.PartOfSpeechRA = _FakeObj(pos_guid) if pos_guid else None
        # Simulate SlotsRC as a plain list of objects with Guid attributes
        self.SlotsRC = [_FakeObj(sg) for sg in slot_guids]


class _TsString:
    def __init__(self, text: str) -> None:
        self.Text = text


class _FakeForm:
    def __init__(self, text: str) -> None:
        self._text = text
    def get_String(self, ws_handle) -> _TsString:
        return _TsString(self._text)


class _FakeAllomorph(_FakeObj):
    def __init__(self, guid, owner_guid, form_text="", morph_type_guid=""):
        super().__init__(guid)
        self.Owner = _FakeObj(owner_guid)
        self.Form = _FakeForm(form_text)
        self.MorphTypeRA = _FakeObj(morph_type_guid) if morph_type_guid else None


# ---------------------------------------------------------------------------
# T-M01: GUID direct hit
# ---------------------------------------------------------------------------

def test_guid_direct_hit():
    """lookup_target returns via='guid' when source GUID exists in target."""
    target_obj = _FakeObj("aaaaaaaa-0000-0000-0000-000000000001")
    target = _FakeTarget([target_obj])

    m = lookup_target(
        "aaaaaaaa-0000-0000-0000-000000000001",
        GrammarCategory.POS,
        target,
    )

    assert m.via == "guid"
    assert m.target_obj is target_obj
    assert m.fingerprint_key is None


# ---------------------------------------------------------------------------
# T-M02: identity_remap fallback
# ---------------------------------------------------------------------------

def test_identity_remap_hit():
    """When source GUID is not in target but remap maps it to a target GUID."""
    source_guid = "src-guid-0000-0000-0000-000000000001"
    target_guid = "tgt-guid-0000-0000-0000-000000000099"
    target_obj = _FakeObj(target_guid)
    target = _FakeTarget([target_obj])

    remap = {source_guid: target_guid}

    m = lookup_target(
        source_guid,
        GrammarCategory.MSA,
        target,
        identity_remap=remap,
    )

    assert m.via == "identity_remap"
    assert m.target_obj is target_obj
    assert m.source_guid == source_guid


# ---------------------------------------------------------------------------
# T-M03: Fingerprint fallback hit
# ---------------------------------------------------------------------------

def test_fingerprint_hit():
    """Fingerprint match when GUID and remap both miss."""
    owner_guid = "entry-0000-0000-0000-000000000001"
    pos_guid = "pos-0000-0000-0000-000000000001"
    slot_guid = "slot-0000-0000-0000-000000000001"

    source_msa = _FakeMSA(
        "src-msa-guid",
        owner_guid,
        pos_guid=pos_guid,
        slot_guids=(slot_guid,),
    )
    # Target MSA has a DIFFERENT guid but the same fingerprint
    target_msa = _FakeMSA(
        "tgt-msa-guid-different",
        owner_guid,
        pos_guid=pos_guid,
        slot_guids=(slot_guid,),
    )
    target = _IterOnlyTarget([target_msa])

    m = lookup_target(
        "src-msa-guid",
        GrammarCategory.MSA,
        target,
        source_obj=source_msa,
    )

    assert m.via == "fingerprint"
    assert m.target_obj is target_msa
    assert m.fingerprint_key is not None
    assert m.fingerprint_key[0] == GrammarCategory.MSA


# ---------------------------------------------------------------------------
# T-M04: via="none" when nothing matches
# ---------------------------------------------------------------------------

def test_no_match_returns_none_via():
    """All three steps miss -> Match.via == 'none', target_obj is None."""
    target = _FakeTarget([])  # empty target

    m = lookup_target(
        "unknown-guid",
        GrammarCategory.MSA,
        target,
        identity_remap={},
        source_obj=None,
    )

    assert m.via == "none"
    assert m.target_obj is None
    assert m.fingerprint_key is None


# ---------------------------------------------------------------------------
# T-M05: FINGERPRINT_FNS registry entries
# ---------------------------------------------------------------------------

def test_fingerprint_fns_registry_has_msa_and_allomorph():
    """FINGERPRINT_FNS must contain entries for MSA and ALLOMORPH."""
    assert GrammarCategory.MSA in FINGERPRINT_FNS
    assert GrammarCategory.ALLOMORPH in FINGERPRINT_FNS
    assert callable(FINGERPRINT_FNS[GrammarCategory.MSA])
    assert callable(FINGERPRINT_FNS[GrammarCategory.ALLOMORPH])


# ---------------------------------------------------------------------------
# T-M06: Match.__post_init__ validation
# ---------------------------------------------------------------------------

def test_match_rejects_invalid_via():
    with pytest.raises(ValueError, match="Match.via must be one of"):
        Match(source_guid="g", target_obj=None, via="bad_value")


def test_match_rejects_target_obj_with_none_via():
    with pytest.raises(ValueError, match="target_obj=None"):
        Match(source_guid="g", target_obj=object(), via="none")


def test_match_rejects_fingerprint_key_without_fingerprint_via():
    with pytest.raises(ValueError, match="fingerprint_key must be None"):
        Match(
            source_guid="g",
            target_obj=object(),
            via="guid",
            fingerprint_key=("x",),
        )


# ---------------------------------------------------------------------------
# T-M07: fingerprint_for_msa tuple shape
# ---------------------------------------------------------------------------

def test_fingerprint_for_msa_shape():
    msa = _FakeMSA(
        "msa-guid",
        "owner-guid",
        pos_guid="pos-guid",
        slot_guids=("slot-a", "slot-b"),
    )
    fp = fingerprint_for_msa(msa)

    assert fp[0] == GrammarCategory.MSA
    assert fp[1] == "owner-guid"
    assert fp[2] == "MoInflAffMsa"
    assert fp[3] == "pos-guid"
    assert fp[4] == frozenset({"slot-a", "slot-b"})


def test_fingerprint_for_msa_unbound_slot():
    """Unbound MSA (SlotsRC empty) produces frozenset()."""
    msa = _FakeMSA("msa-guid", "owner-guid", pos_guid="", slot_guids=())
    fp = fingerprint_for_msa(msa)
    assert fp[4] == frozenset()


# ---------------------------------------------------------------------------
# T-M08: fingerprint_for_allomorph tuple shape
# ---------------------------------------------------------------------------

def test_fingerprint_for_allomorph_shape():
    allo = _FakeAllomorph(
        "allo-guid",
        "owner-guid",
        form_text="n~-",
        morph_type_guid="mtype-guid",
    )
    fp = fingerprint_for_allomorph(allo, ws_handle=1)

    assert fp[0] == GrammarCategory.ALLOMORPH
    assert fp[1] == "owner-guid"
    assert fp[2] == "n~-"
    assert fp[3] == "mtype-guid"


def test_fingerprint_for_allomorph_no_ws_handle():
    """Without ws_handle, lexeme_form_text is empty string."""
    allo = _FakeAllomorph("allo-guid", "owner-guid", form_text="n~-")
    fp = fingerprint_for_allomorph(allo, ws_handle=None)
    assert fp[2] == ""

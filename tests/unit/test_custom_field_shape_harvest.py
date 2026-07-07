"""Unit tests for the custom-field shape harvest and the fail-loud type guard.

Root cause these defend against (diagnosed live from managed stacks): the
shipping flexicon ``CustomFields.GetAllFields`` returns bare 2-tuples
``(flid, label)``, GramTrans defaulted the missing type to 0
(CellarPropertyType.Nil), ``AddCustomField`` accepted it, and LibLCM's commit
serializer then threw in ``GetFlidTypeAsString`` -- whose catch path
(ReportProblem -> WinForms Control.Invoke) wedges a headless host forever.
The whole "custom field deadlock" was this delayed detonation.

Two layers of defense, both tested here with injected fake SIL modules:

1. ``categories._harvest_field_shape`` pulls the REAL type / wsSelector /
   list root from the metadata cache when flexicon yields 2-tuples.
2. ``api._ensure_custom_fields`` refuses any field whose type LibLCM cannot
   serialize (esp. 0/Nil) BEFORE mutating the schema.
"""
from __future__ import annotations

import sys
import types

import pytest

from gramtrans.Lib import categories as cat_mod
from gramtrans.Lib.api import _ensure_custom_fields
from gramtrans.Lib.models import CreateDefinitionAction, GrammarCategory


@pytest.fixture()
def fake_sil(monkeypatch):
    """Inject fake SIL.LCModel.Infrastructure with a pass-through managed cast."""
    infra = types.ModuleType("SIL.LCModel.Infrastructure")
    infra.IFwMetaDataCacheManaged = lambda mdc: mdc  # identity "cast"
    lcm = types.ModuleType("SIL.LCModel")
    sil = types.ModuleType("SIL")
    sil.LCModel = lcm
    lcm.Infrastructure = infra
    monkeypatch.setitem(sys.modules, "SIL", sil)
    monkeypatch.setitem(sys.modules, "SIL.LCModel", lcm)
    monkeypatch.setitem(sys.modules, "SIL.LCModel.Infrastructure", infra)


class _FakeMdc:
    """Metadata-cache fake: field 5002500 is a MultiUnicode(16) analysis field."""

    def GetFieldType(self, flid):  # noqa: N802
        assert flid == 5002500
        return 16 | 0x20  # extra flag bit above the type nibble must be masked

    def GetFieldWs(self, flid):  # noqa: N802
        return -3  # kwsAnals

    def GetFieldListRoot(self, flid):  # noqa: N802
        return "00000000-0000-0000-0000-000000000000"  # Guid.Empty -> no list


class _FakeProject:
    def __init__(self, rows):
        self._rows = rows
        self.Cache = types.SimpleNamespace(MetaDataCacheAccessor=_FakeMdc())
        proj = self

        class _CfOps:
            def GetAllFields(self, cls):  # noqa: N802
                return proj._rows.get(cls, [])

        self.CustomFields = _CfOps()


def test_two_tuple_rows_are_enriched_from_the_mdc(fake_sil):
    """The shipping-flexicon 2-tuple shape must yield the REAL field type
    (flag bits masked), wsSelector, and no list root for Guid.Empty."""
    project = _FakeProject({"MoForm": [(5002500, "Allomorph Comment")]})
    records = list(cat_mod._enumerate_custom_fields(project))
    rec = next(r for r in records if r.name == "Allomorph Comment")
    assert rec.field_type == 16          # MultiUnicode, 0x20 flag masked off
    assert rec.ws_selector == -3
    assert rec.list_root_guid == ""


def test_four_tuple_rows_keep_the_fake_contract(fake_sil):
    project = _FakeProject({"LexSense": [(5016001, "Target Equivalent", 13, "")]})
    records = list(cat_mod._enumerate_custom_fields(project))
    rec = next(r for r in records if r.name == "Target Equivalent")
    assert rec.field_type == 13
    assert rec.ws_selector == 0


def test_harvest_returns_zeros_without_live_lcm():
    """Host-free (no fake SIL): the harvest degrades to (0, 0, '') instead of
    raising -- the api-side guard is then responsible for refusing type 0."""
    project = _FakeProject({"LexEntry": [(5002001, "Plain")]})
    assert cat_mod._harvest_field_shape(project, 5002001) == (0, 0, "")


def _action(field_type: int) -> CreateDefinitionAction:
    return CreateDefinitionAction(
        category=GrammarCategory.CUSTOM_FIELDS,
        source_guid="cf:LexEntry:Bad",
        owner_class="LexEntry",
        field_name="Bad",
        field_type=field_type,
        list_root_guid="",
        summary="test",
    )


class _GuardProj:
    """Minimal handle for _ensure_custom_fields up to the guard."""

    def __init__(self):
        self.Cache = types.SimpleNamespace(MetaDataCacheAccessor=object())
        self.CustomFields = types.SimpleNamespace(
            FindField=lambda cls, name: None  # field is new -> reach the guard
        )


def test_ensure_custom_fields_refuses_nil_type(fake_sil):
    """A Nil(0)-typed create must fail loud BEFORE AddCustomField -- letting
    it through wedges the commit writer at serialization time."""
    with pytest.raises(RuntimeError, match="not serializable"):
        _ensure_custom_fields(_GuardProj(), [_action(0)])


def test_ensure_custom_fields_refuses_unknown_type(fake_sil):
    with pytest.raises(RuntimeError, match="not serializable"):
        _ensure_custom_fields(_GuardProj(), [_action(99)])

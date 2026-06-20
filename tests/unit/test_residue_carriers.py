"""T024: Regression tests for apply_carrier_b direct-attribute access.

Bug fixed 2026-06-19: the old code cast obj to ICmPossibility before accessing
.Description, which raises TypeError for IMoInflAffixTemplate and other
grammar-piece interfaces that expose .Description directly but are not
ICmPossibility-castable. Fix uses getattr(obj, "Description") instead.

These tests exercise apply_carrier_b without any LCM/FlexTools imports by
using duck-typed fakes.
"""
from __future__ import annotations

import pytest

from gramtrans.Lib.residue import ImportResidueTag, apply_carrier_b


TAG = ImportResidueTag.make(
    run_id="GT-20260619-140000",
    source_project_name="Ejagham Mini",
    timestamp="2026-06-19T14:00:00",
)
WS = "ws-handle"


class _FakeMultiString:
    """Fake LCM multistring that records set_String calls."""

    def __init__(self, initial_text: str = "") -> None:
        self._text = initial_text
        self.set_calls: list[tuple] = []

    def get_String(self, ws):  # noqa: N802 — mirrors LCM naming
        return self

    @property
    def Text(self) -> str:
        return self._text

    def set_String(self, ws, value: str) -> None:  # noqa: N802
        self.set_calls.append((ws, value))
        self._text = value


class _FakeObjWithDescription:
    """Duck-typed stand-in for an LCM object that exposes .Description."""

    def __init__(self, initial_text: str = "") -> None:
        self.Description = _FakeMultiString(initial_text)


class _FakeObjWithoutDescription:
    """Duck-typed stand-in for an LCM object that has no .Description."""

    pass


# ---------------------------------------------------------------------------
# Test 1: direct attribute access — no ICmPossibility cast required
# ---------------------------------------------------------------------------

def test_apply_carrier_b_writes_to_obj_description_via_direct_attribute() -> None:
    """apply_carrier_b writes via direct .Description access, not ICmPossibility cast."""
    fake = _FakeObjWithDescription()
    apply_carrier_b(fake, ws=WS, tag=TAG)

    ms = fake.Description
    assert len(ms.set_calls) == 1, "set_String should be called exactly once"

    _, written_value = ms.set_calls[0]
    expected_suffix = f"[GT-Tag]: {TAG.serialize()}"
    assert written_value.endswith(expected_suffix), (
        f"Written value should end with tag line; got: {written_value!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: TypeError when object has no Description attribute
# ---------------------------------------------------------------------------

def test_apply_carrier_b_raises_typeerror_when_obj_has_no_description() -> None:
    """apply_carrier_b raises TypeError for objects without .Description."""
    fake = _FakeObjWithoutDescription()
    with pytest.raises(TypeError, match="has no Description attribute"):
        apply_carrier_b(fake, ws=WS, tag=TAG)


# ---------------------------------------------------------------------------
# Test 3: existing prose is preserved, tag appended after blank-line separator
# ---------------------------------------------------------------------------

def test_apply_carrier_b_preserves_existing_description_prose() -> None:
    """Existing Description text is kept; tag is appended after a blank line."""
    existing_prose = "Existing prose here."
    fake = _FakeObjWithDescription(initial_text=existing_prose)
    apply_carrier_b(fake, ws=WS, tag=TAG)

    _, written_value = fake.Description.set_calls[0]
    expected = f"Existing prose here.\n\n[GT-Tag]: {TAG.serialize()}"
    assert written_value == expected, (
        f"Expected exact value {expected!r}, got {written_value!r}"
    )


# ===========================================================================
# T025: apply_carrier_a -- five observable LiftResidue shapes (FR-106 fix)
# ===========================================================================
# TsStringUtils.MakeString is monkeypatched on the residue module so tests
# run without pythonnet / LCM on the path.
# ===========================================================================

from gramtrans.Lib.residue import apply_carrier_a
import gramtrans.Lib.residue as _residue_mod


@pytest.fixture()
def patch_ts(monkeypatch):
    """Inject fake SIL.LCM.Core.Text.TsStringUtils so tests run without pythonnet."""

    class _FakeTsStringUtils:
        @staticmethod
        def MakeString(text, ws):
            return text  # identity -- val_arg == TAG.serialize() in assertions

    import sys, types
    fake_pkg    = types.ModuleType("SIL")
    fake_lcmodel = types.ModuleType("SIL.LCModel")
    fake_core   = types.ModuleType("SIL.LCModel.Core")
    fake_text   = types.ModuleType("SIL.LCModel.Core.Text")
    fake_text.TsStringUtils = _FakeTsStringUtils
    fake_core.Text    = fake_text
    fake_lcmodel.Core = fake_core
    fake_pkg.LCModel  = fake_lcmodel
    monkeypatch.setitem(sys.modules, "SIL",                    fake_pkg)
    monkeypatch.setitem(sys.modules, "SIL.LCModel",            fake_lcmodel)
    monkeypatch.setitem(sys.modules, "SIL.LCModel.Core",       fake_core)
    monkeypatch.setitem(sys.modules, "SIL.LCModel.Core.Text",  fake_text)
    yield _FakeTsStringUtils


# Shape 1: attribute absent -> False, no write
def test_carrier_a_absent_attribute_returns_false(patch_ts):
    """LiftResidue absent: returns False without touching the object."""
    class _NoLift:
        pass
    obj = _NoLift()
    result = apply_carrier_a(obj, WS, TAG)
    assert result is False
    assert not hasattr(obj, "LiftResidue")


# Shape 2: attribute is None -> False, no write
def test_carrier_a_none_attribute_returns_false(patch_ts):
    """LiftResidue=None: returns False (uninitialized multistring path)."""
    class _NullLift:
        LiftResidue = None
    obj = _NullLift()
    result = apply_carrier_a(obj, WS, TAG)
    assert result is False
    assert obj.LiftResidue is None  # unchanged


# Shape 3: attribute is empty str -> setattr path, returns True
def test_carrier_a_empty_str_uses_setattr(patch_ts):
    """LiftResidue='' (plain Unicode): setattr path writes serialized tag."""
    class _StrLift:
        LiftResidue = ""
    obj = _StrLift()
    result = apply_carrier_a(obj, WS, TAG)
    assert result is True
    assert obj.LiftResidue == TAG.serialize()


# Shape 4: attribute is populated str -> setattr overwrites, returns True
def test_carrier_a_populated_str_overwrites(patch_ts):
    """LiftResidue already has a value (plain Unicode): overwritten, returns True."""
    class _StrLift:
        LiftResidue = "GT|GT-20200101-000000|old-proj|2020-01-01T00:00:00"
    obj = _StrLift()
    result = apply_carrier_a(obj, WS, TAG)
    assert result is True
    assert obj.LiftResidue == TAG.serialize()


# Shape 5: attribute is ITsMultiString (has set_String) -> set_String path, returns True
def test_carrier_a_multistring_calls_set_string(patch_ts):
    """LiftResidue is ITsMultiString: set_String is called with MakeString output."""
    class _FakeMultiStringLift:
        def __init__(self):
            self.calls = []

        def set_String(self, ws, value):
            self.calls.append((ws, value))

    class _MultiLift:
        def __init__(self):
            self.LiftResidue = _FakeMultiStringLift()

    obj = _MultiLift()
    result = apply_carrier_a(obj, WS, TAG)
    assert result is True
    assert len(obj.LiftResidue.calls) == 1
    ws_arg, val_arg = obj.LiftResidue.calls[0]
    assert ws_arg == WS
    # patch_ts.MakeString is identity, so val_arg == TAG.serialize()
    assert val_arg == TAG.serialize()

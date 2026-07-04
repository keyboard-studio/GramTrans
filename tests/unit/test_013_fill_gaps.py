"""T-S3a: Unit tests for _apply_props_loop fill-gaps mode (FR-013).

Calls _apply_props_loop directly (T-R2c extraction) with fabricated item
objects and a fake target_ws_by_id dict -- no live LCM fixture needed.

Import path: flexicon.code.BaseOperations (installed editable package).
Install: pip install -e D:/Github/_Projects/_LEX/flexlibs2

All tests are NOT marked integration so they run in the default suite.
"""
import pytest

try:
    from flexicon.code.BaseOperations import _apply_props_loop
    _IMPORT_OK = True
except ImportError as _import_err:
    _IMPORT_OK = False
    _import_err_msg = str(_import_err)


# ---------------------------------------------------------------------------
# Fake helpers
# ---------------------------------------------------------------------------

class _FakeTsString:
    """Minimal ITsString fake with RunCount and Text."""
    def __init__(self, text=""):
        self._text = text

    @property
    def Text(self):
        # LCM returns None for empty ITsString; mirror that here.
        return self._text if self._text else None

    @property
    def RunCount(self):
        return 1 if self._text else 0


class _FakeMultiString:
    """Fake multistring property with get_String / set_String."""
    def __init__(self, existing_by_handle=None):
        self._data = dict(existing_by_handle or {})
        self.set_calls = []

    def get_String(self, handle):
        return _FakeTsString(self._data.get(handle, ""))

    def set_String(self, handle, ts_string):
        self.set_calls.append((handle, ts_string))


class _FakeTsStringUtils:
    @staticmethod
    def MakeString(text, handle):
        return f"TS:{text}@{handle}"


class _FakeItem:
    """Fake LCM item with settable attributes and call tracking."""
    def __init__(self, **kwargs):
        # Use object.__setattr__ to bypass tracking during __init__
        object.__setattr__(self, "_setattr_calls", [])
        for k, v in kwargs.items():
            object.__setattr__(self, k, v)

    def __setattr__(self, name, value):
        if not name.startswith("_"):
            self._setattr_calls.append((name, value))
        object.__setattr__(self, name, value)


# ---------------------------------------------------------------------------
# Skip marker if import failed
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.skipif(
    not _IMPORT_OK,
    reason=f"flexlibs2 not installed editable: {_import_err_msg if not _IMPORT_OK else ''}",
)

HANDLE_EN = 100
HANDLE_FR = 200


# ---------------------------------------------------------------------------
# Multistring fill-gaps
# ---------------------------------------------------------------------------

class TestMultistringFillGaps:
    def test_nonempty_target_alt_skipped_when_fill_gaps(self):
        """fill_gaps=True: WS alt with RunCount>0 must NOT be overwritten."""
        ms = _FakeMultiString(existing_by_handle={HANDLE_EN: "existing text"})
        item = _FakeItem(Name=ms)
        props = {"Name": {"en": "new value"}}
        _apply_props_loop(item, props, {"en": HANDLE_EN}, fill_gaps=True,
                          _ts_string_utils=_FakeTsStringUtils)
        assert ms.set_calls == [], "set_String must not be called for non-empty target alt"

    def test_empty_target_alt_filled_when_fill_gaps(self):
        """fill_gaps=True: WS alt with RunCount==0 (empty) MUST be written."""
        ms = _FakeMultiString(existing_by_handle={})  # no content
        item = _FakeItem(Name=ms)
        props = {"Name": {"en": "new value"}}
        _apply_props_loop(item, props, {"en": HANDLE_EN}, fill_gaps=True,
                          _ts_string_utils=_FakeTsStringUtils)
        assert len(ms.set_calls) == 1, "set_String must be called for empty target alt"

    def test_overwrite_mode_always_writes(self):
        """fill_gaps=False (default): non-empty target alt IS overwritten."""
        ms = _FakeMultiString(existing_by_handle={HANDLE_EN: "existing"})
        item = _FakeItem(Name=ms)
        props = {"Name": {"en": "replacement"}}
        _apply_props_loop(item, props, {"en": HANDLE_EN}, fill_gaps=False,
                          _ts_string_utils=_FakeTsStringUtils)
        assert len(ms.set_calls) == 1, "set_String must be called in overwrite mode"


# ---------------------------------------------------------------------------
# Plain str fill-gaps
# ---------------------------------------------------------------------------

class TestPlainStrFillGaps:
    def test_nonempty_attr_skipped_when_fill_gaps(self):
        """fill_gaps=True: plain str attr that is already non-empty must not be set."""
        item = _FakeItem(CatalogSourceId="existing")
        props = {"CatalogSourceId": "new"}
        _apply_props_loop(item, props, {}, fill_gaps=True)
        writes = [c for c in item._setattr_calls if c == ("CatalogSourceId", "new")]
        assert writes == [], "setattr must not be called for non-empty plain str attr"

    def test_none_attr_filled_when_fill_gaps(self):
        """fill_gaps=True: plain str attr that is None MUST be filled."""
        item = _FakeItem(CatalogSourceId=None)
        props = {"CatalogSourceId": "new"}
        _apply_props_loop(item, props, {}, fill_gaps=True)
        writes = [c for c in item._setattr_calls if c == ("CatalogSourceId", "new")]
        assert writes, "setattr must be called for None plain str attr"


# ---------------------------------------------------------------------------
# Bool/int fill-gaps
# ---------------------------------------------------------------------------

class TestBoolIntFillGaps:
    def test_bool_skipped_when_fill_gaps(self):
        """fill_gaps=True: bool/int attrs are ALWAYS skipped (False is a real choice)."""
        item = _FakeItem(Disabled=False)
        props = {"Disabled": True}
        _apply_props_loop(item, props, {}, fill_gaps=True)
        writes = [c for c in item._setattr_calls if c == ("Disabled", True)]
        assert writes == [], "bool attr must not be written in fill-gaps mode"

    def test_bool_written_when_overwrite(self):
        """fill_gaps=False: bool/int attrs ARE written."""
        item = _FakeItem(Disabled=False)
        props = {"Disabled": True}
        _apply_props_loop(item, props, {}, fill_gaps=False)
        writes = [c for c in item._setattr_calls if c == ("Disabled", True)]
        assert writes, "bool attr must be written in overwrite mode"


# ---------------------------------------------------------------------------
# TEST 1 (P2-C): whitespace-only multistring alt treated as empty in fill_gaps
# ---------------------------------------------------------------------------

class TestWhitespaceOnlyAltFillGaps:
    def test_whitespace_only_alt_treated_as_empty_and_filled(self):
        """fill_gaps=True: a multistring alt with only whitespace (RunCount>0
        but no real text) MUST be overwritten from source -- FIX 1 (P1-B)."""
        # Whitespace-only: RunCount==1 in real LCM; our fake mirrors that.
        ms = _FakeMultiString(existing_by_handle={HANDLE_EN: "   "})
        item = _FakeItem(Name=ms)
        props = {"Name": {"en": "real content"}}
        _apply_props_loop(item, props, {"en": HANDLE_EN}, fill_gaps=True,
                          _ts_string_utils=_FakeTsStringUtils)
        assert len(ms.set_calls) == 1, (
            "set_String must be called: whitespace-only alt must be treated as empty"
        )


# ---------------------------------------------------------------------------
# TEST 2 (P2-D): pure int fill-gaps semantics; bool False always preserved
# ---------------------------------------------------------------------------

class TestIntFillGaps:
    def test_int_zero_target_gets_filled(self):
        """fill_gaps=True: int attr with value 0 (unset) MUST be filled from source."""
        item = _FakeItem(HomographNumber=0)
        props = {"HomographNumber": 3}
        _apply_props_loop(item, props, {}, fill_gaps=True)
        writes = [c for c in item._setattr_calls if c == ("HomographNumber", 3)]
        assert writes, "int attr with value 0 must be filled in fill-gaps mode"

    def test_int_nonzero_target_preserved(self):
        """fill_gaps=True: int attr already non-zero must NOT be overwritten."""
        item = _FakeItem(HomographNumber=2)
        props = {"HomographNumber": 5}
        _apply_props_loop(item, props, {}, fill_gaps=True)
        writes = [c for c in item._setattr_calls if c == ("HomographNumber", 5)]
        assert writes == [], "non-zero int attr must be preserved in fill-gaps mode"

    def test_bool_false_always_preserved_in_fill_gaps(self):
        """fill_gaps=True: bool False is a deliberate choice and must never be
        overwritten -- even though isinstance(False, int) is True."""
        item = _FakeItem(Disabled=False)
        props = {"Disabled": True}
        _apply_props_loop(item, props, {}, fill_gaps=True)
        writes = [c for c in item._setattr_calls if c == ("Disabled", True)]
        assert writes == [], "bool False must always be preserved in fill-gaps mode"

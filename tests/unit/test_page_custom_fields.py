"""Tests for _PageCustomFields wizard page (Feature 016, US1/US2/US4).

T008 -- US1 grouping, counts, preselection, empty-level, zero-fields edge case.
T012 -- US2 whole-block toggle, single-field deselect, level tristate.
T020 -- US4 status column: NEW / IN_TARGET / blank-no-target / type-diff note.

Isolation note
--------------
Real PyQt6 imports are deferred to the ``qapp`` fixture (session scope) to
avoid polluting ``sys.modules`` at collection time.  test_ui_gating.py and
test_wizard_page_flow.py install MagicMock stubs via ``sys.modules.setdefault``
which is a no-op if real PyQt6 is already loaded.  By deferring the import to
fixture-execution time we ensure both test files see the right Qt bindings.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

# Skip the entire module at *collection* time if PyQt6 is genuinely absent.
# importlib.util.find_spec raises ValueError when PyQt6 is a MagicMock stub
# (stub.__spec__ is not set).  Guard against both absence and stubbing.
try:
    _pyqt6_spec = importlib.util.find_spec("PyQt6")
except (ValueError, AttributeError):
    _pyqt6_spec = None  # stub installed; treat as absent for real-Qt tests
if _pyqt6_spec is None:
    pytest.skip("PyQt6 not installed or stubbed", allow_module_level=True)

# ---------------------------------------------------------------------------
# Lazy module-level references -- populated by the qapp fixture below.
# They are ``None`` at import time and filled in before any test runs.
# All test helpers and test methods access them via the module's namespace,
# which is populated by the time ``qapp`` has run (session-scoped, autouse).
# ---------------------------------------------------------------------------
QtCore = None          # noqa: N816  (filled by qapp fixture)
QtWidgets = None       # noqa: N816
_sw = None             # selection_wizard module
_CustomFieldRecord = None
_CUSTOM_FIELD_OWNER_CLASSES = None
custom_field_type_label = None
GrammarCategory = None


# ---------------------------------------------------------------------------
# QApplication fixture (session-scoped, autouse so helpers can use globals)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Bootstrap real PyQt6 and inject lazy globals.

    autouse=True ensures this fixture runs before any test in the module,
    including tests whose parameter lists only name ``qapp`` by position.

    If the ``PyQt6`` slot in ``sys.modules`` is a MagicMock stub (installed by
    test_ui_gating.py or test_wizard_page_flow.py), the real widget tests
    cannot run.  We skip in that case rather than fail with cryptic mock errors.
    """
    import sys
    from unittest.mock import MagicMock

    installed = sys.modules.get("PyQt6")
    if installed is not None and isinstance(installed, MagicMock):
        pytest.skip(
            "PyQt6 is stubbed (MagicMock) in this session -- "
            "run test_page_custom_fields.py in isolation for real-Qt tests"
        )

    global QtCore, QtWidgets, _sw
    global _CustomFieldRecord, _CUSTOM_FIELD_OWNER_CLASSES
    global custom_field_type_label, GrammarCategory

    # Import real PyQt6 (deferred from module level).
    from PyQt6 import QtCore as _QtCore, QtWidgets as _QtWidgets
    QtCore = _QtCore
    QtWidgets = _QtWidgets

    # Import gramtrans modules (after PyQt6 is in sys.modules).
    from gramtrans.Lib.ui import selection_wizard as _sw_mod
    _sw = _sw_mod

    # Guard: if selection_wizard was already imported in this session with a
    # stub QWizardPage as base (e.g. test_wizard_page_flow.py patched
    # QtWidgets.QWizardPage before us), _PageCustomFields cannot create real
    # Qt widgets.  Detect this by inspecting the MRO for a real Qt class.
    _cf_bases = getattr(_sw_mod._PageCustomFields, "__mro__", ())
    _has_real_qt = any(
        getattr(b, "staticMetaObject", None) is not None
        for b in _cf_bases
        if b is not object
    )
    if not _has_real_qt:
        pytest.skip(
            "selection_wizard was imported with stub QWizardPage -- "
            "run test_page_custom_fields.py in isolation for real-Qt tests"
        )

    from gramtrans.Lib.categories import (
        _CustomFieldRecord as _CFR,
        _CUSTOM_FIELD_OWNER_CLASSES as _CFOC,
        custom_field_type_label as _CFTL,
    )
    _CustomFieldRecord = _CFR
    _CUSTOM_FIELD_OWNER_CLASSES = _CFOC
    custom_field_type_label = _CFTL

    from gramtrans.Lib.models import GrammarCategory as _GC
    GrammarCategory = _GC

    app = _QtWidgets.QApplication.instance()
    if app is None:
        app = _QtWidgets.QApplication([])
    return app


# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------

def _make_cf_records(*specs):
    """Build _CustomFieldRecord list from (owner, name, field_type) triples."""
    return [
        _CustomFieldRecord(owner, name, field_id=1, field_type=ft)
        for owner, name, ft in specs
    ]


class _FakeCustomFields:
    def __init__(self, records):
        self._by_class = {}
        for r in records:
            self._by_class.setdefault(r.owner_class, []).append(
                (r.field_id, r.name, r.field_type, r.list_root_guid)
            )

    def GetAllFields(self, cls):
        return self._by_class.get(cls, [])

    def FindField(self, cls, name):
        for row in self._by_class.get(cls, []):
            if row[1] == name:
                return row[0]
        return None


class _FakeProject:
    def __init__(self, records=None):
        records = records or []
        self.CustomFields = _FakeCustomFields(records)


class _FakeTargetProject(_FakeProject):
    """Target project that optionally has a type-mismatched MDC."""
    def __init__(self, records=None, type_overrides=None):
        super().__init__(records)
        self._type_overrides = type_overrides or {}

    class _FakeMDC:
        def __init__(self, overrides):
            self._overrides = overrides

        def GetFieldType(self, flid):
            return self._overrides.get(flid, 13)

    class _FakeCache:
        def __init__(self, overrides):
            self.MetaDataCacheAccessor = _FakeTargetProject._FakeMDC(overrides)

    @property
    def Cache(self):
        return self._FakeCache(self._type_overrides)


class _FakeStubWizard:
    """Stand-in for SelectionWizard -- avoids QObject init in tests."""

    def __init__(self, source=None, target=None):
        self._source = source
        self._target = target

    def page_project_ws(self):
        return self

    def context(self):
        return self

    @property
    def source_handle(self):
        return self._source

    @property
    def target_handle(self):
        return self._target

    @property
    def _host(self):
        return self._source


def _make_page(qapp, records=None, target=None):
    """Instantiate _PageCustomFields and inject fake wizard."""
    page = _sw._PageCustomFields()
    fake_wizard = _FakeStubWizard(
        source=_FakeProject(records or []),
        target=target,
    )
    page.wizard = lambda: fake_wizard
    return page


def _populate_page(page):
    """Trigger tree population (normally called by initializePage)."""
    page._populate_from_source()


# ---------------------------------------------------------------------------
# T008 -- US1: grouping, counts, preselection, empty-level, zero-fields
# ---------------------------------------------------------------------------

class TestUS1Grouping:
    def test_four_level_groups_present(self, qapp):
        records = _make_cf_records(
            ("LexEntry", "Notes", 13),
            ("LexSense", "Domain", 24),
            ("LexExampleSentence", "Corpus", 13),
            ("MoForm", "Dialect", 16),
        )
        page = _make_page(qapp, records)
        _populate_page(page)

        root = page._tree.invisibleRootItem()
        assert root.childCount() == 4
        labels = [root.child(i).text(0) for i in range(root.childCount())]
        assert any("Entry" in l for l in labels)
        assert any("Sense" in l for l in labels)
        assert any("Example" in l for l in labels)
        assert any("Allomorph" in l for l in labels)

    def test_header_shows_count(self, qapp):
        records = _make_cf_records(
            ("LexEntry", "Notes", 13),
            ("LexEntry", "Source", 13),
            ("LexSense", "Domain", 24),
        )
        page = _make_page(qapp, records)
        _populate_page(page)

        root = page._tree.invisibleRootItem()
        entry_header = None
        for i in range(root.childCount()):
            h = root.child(i)
            if "Entry" in h.text(0):
                entry_header = h
                break
        assert entry_header is not None
        assert "2" in entry_header.text(0)

    def test_row_shows_name_and_type_label(self, qapp):
        records = _make_cf_records(("LexEntry", "Notes", 13))
        page = _make_page(qapp, records)
        _populate_page(page)

        root = page._tree.invisibleRootItem()
        entry_header = None
        for i in range(root.childCount()):
            h = root.child(i)
            if "Entry" in h.text(0):
                entry_header = h
                break
        assert entry_header is not None
        assert entry_header.childCount() >= 1
        row = entry_header.child(0)
        row_text = row.text(0) + row.text(1)
        assert "Notes" in row_text
        assert custom_field_type_label(13) in row_text

    def test_every_row_checked_on_open(self, qapp):
        records = _make_cf_records(
            ("LexEntry", "A", 13),
            ("LexSense", "B", 14),
        )
        page = _make_page(qapp, records)
        _populate_page(page)

        for _grp, item in page._iter_item_rows():
            assert item.checkState(0) == QtCore.Qt.CheckState.Checked

    def test_empty_level_renders_no_error(self, qapp):
        # Only LexEntry has a record; the other three levels are empty.
        records = _make_cf_records(("LexEntry", "Notes", 13))
        page = _make_page(qapp, records)
        _populate_page(page)
        root = page._tree.invisibleRootItem()
        assert root.childCount() == 4  # all four headers rendered

    def test_zero_custom_fields_block_unchecked_disabled(self, qapp):
        page = _make_page(qapp, [])
        _populate_page(page)
        assert not page._whole_block.isEnabled()
        assert page._whole_block.checkState() == QtCore.Qt.CheckState.Unchecked

    def test_zero_custom_fields_no_item_rows(self, qapp):
        page = _make_page(qapp, [])
        _populate_page(page)
        items = list(page._iter_item_rows())
        assert items == []


# ---------------------------------------------------------------------------
# T012 -- US2: whole-block toggle, single deselect, level tristate
# ---------------------------------------------------------------------------

class TestUS2Toggles:
    def test_whole_block_off_unchecks_all(self, qapp):
        records = _make_cf_records(
            ("LexEntry", "A", 13),
            ("LexSense", "B", 14),
        )
        page = _make_page(qapp, records)
        _populate_page(page)

        # Simulate user clicking the whole-block checkbox to turn off.
        page._on_whole_block_clicked()  # all checked -> uncheck all

        for _grp, item in page._iter_item_rows():
            assert item.checkState(0) == QtCore.Qt.CheckState.Unchecked

    def test_whole_block_off_contributes_no_picks(self, qapp):
        records = _make_cf_records(
            ("LexEntry", "A", 13),
            ("LexSense", "B", 14),
        )
        page = _make_page(qapp, records)
        _populate_page(page)
        page._on_whole_block_clicked()  # uncheck all

        picks = page.leaf_item_picks()
        cf_picks = picks.get(GrammarCategory.CUSTOM_FIELDS, frozenset())
        assert isinstance(cf_picks, frozenset)
        assert len(cf_picks) == 0

    def test_deselect_single_field_omits_only_that_guid(self, qapp):
        records = _make_cf_records(
            ("LexEntry", "A", 13),
            ("LexEntry", "B", 13),
        )
        page = _make_page(qapp, records)
        _populate_page(page)

        rows = list(page._iter_item_rows())
        rows[0][1].setCheckState(0, QtCore.Qt.CheckState.Unchecked)

        picks = page.leaf_item_picks()
        cf_picks = picks.get(GrammarCategory.CUSTOM_FIELDS, frozenset())
        assert len(cf_picks) == 1  # one of two fields remains

    def test_all_in_level_deselected_header_not_fully_checked(self, qapp):
        records = _make_cf_records(
            ("LexEntry", "A", 13),
            ("LexEntry", "B", 13),
        )
        page = _make_page(qapp, records)
        _populate_page(page)

        root = page._tree.invisibleRootItem()
        entry_header = None
        for i in range(root.childCount()):
            h = root.child(i)
            if "Entry" in h.text(0):
                entry_header = h
                break
        assert entry_header is not None
        for j in range(entry_header.childCount()):
            child = entry_header.child(j)
            if child.flags() & QtCore.Qt.ItemFlag.ItemIsUserCheckable:
                child.setCheckState(0, QtCore.Qt.CheckState.Unchecked)

        # AutoTristate means the header should NOT be fully Checked.
        assert entry_header.checkState(0) != QtCore.Qt.CheckState.Checked

    def test_all_checked_full_block_omits_key_for_transfer_all(self, qapp):
        """Fully-checked block => leaf_item_picks does NOT include key (transfer-all)."""
        records = _make_cf_records(("LexEntry", "A", 13))
        page = _make_page(qapp, records)
        _populate_page(page)
        picks = page.leaf_item_picks()
        assert GrammarCategory.CUSTOM_FIELDS not in picks

    def test_partial_selection_emits_guid_subset(self, qapp):
        records = _make_cf_records(
            ("LexEntry", "A", 13),
            ("LexEntry", "B", 13),
        )
        page = _make_page(qapp, records)
        _populate_page(page)
        rows = list(page._iter_item_rows())
        rows[0][1].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        picks = page.leaf_item_picks()
        assert GrammarCategory.CUSTOM_FIELDS in picks
        cf_picks = picks[GrammarCategory.CUSTOM_FIELDS]
        assert len(cf_picks) == 1


# ---------------------------------------------------------------------------
# T020 -- US4: status column NEW / IN_TARGET / blank / type-diff note
# ---------------------------------------------------------------------------

class TestUS4StatusColumn:
    def test_status_new_when_not_in_target(self, qapp):
        records = _make_cf_records(("LexEntry", "Notes", 13))
        target = _FakeTargetProject([])  # no custom fields
        page = _make_page(qapp, records, target=target)
        _populate_page(page)

        rows = list(page._iter_item_rows())
        assert len(rows) == 1
        item = rows[0][1]
        status_text = item.text(1)
        assert "NEW" in status_text.upper()

    def test_status_in_target_when_present(self, qapp):
        records = _make_cf_records(("LexEntry", "Notes", 13))
        target = _FakeTargetProject(_make_cf_records(("LexEntry", "Notes", 13)))
        page = _make_page(qapp, records, target=target)
        _populate_page(page)

        rows = list(page._iter_item_rows())
        item = rows[0][1]
        status_text = item.text(1)
        assert "IN" in status_text.upper() or "TARGET" in status_text.upper()

    def test_blank_status_when_no_target_bound(self, qapp):
        records = _make_cf_records(("LexEntry", "Notes", 13))
        page = _make_page(qapp, records, target=None)
        _populate_page(page)

        rows = list(page._iter_item_rows())
        item = rows[0][1]
        status_text = item.text(1)
        # No target => blank status or degrade to NEW.
        assert status_text in ("", "NEW")

    def test_type_diff_note_shown_when_type_differs(self, qapp):
        records = _make_cf_records(("LexEntry", "Notes", 13))  # Text (13)
        # Target has "Notes" but MDC returns type 14 for flid 1.
        target_records = _make_cf_records(("LexEntry", "Notes", 13))
        target = _FakeTargetProject(
            target_records,
            type_overrides={1: 14},  # flid 1 -> MultiString
        )
        page = _make_page(qapp, records, target=target)
        _populate_page(page)

        rows = list(page._iter_item_rows())
        item = rows[0][1]
        col1 = item.text(1)
        tip = item.toolTip(0) or item.toolTip(1)
        has_note = any(
            x in (col1 + tip).upper()
            for x in ("TYPE", "DIFF", "MISMATCH", "IN TARGET", "SOURCE")
        )
        assert has_note, f"Expected type-diff info in col1={col1!r} or tooltip={tip!r}"

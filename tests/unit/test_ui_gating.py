"""UI gating logic tests (T058).

Tests the pure-Python state-machine helpers inside the Qt dialog classes
without rendering any widgets.  Strategy: install MagicMock stubs for
PyQt6 in sys.modules *before* importing the UI modules, then bypass
__init__ via __new__() and wire internal state manually.

Four tests land:
  1. target_picker  — selected_candidate() returns None with no selection
  2. target_picker  — selected_candidate() returns the right candidate after
                      simulated selection
  3. ws_mapping_dialog — selected_mapping() skips unmapped rows
  4. affix_tree_picker — picker_state() collapses tree checks to PickerState
  5. main_window       — _collect_selection() translates toggle dict to Selection

Tests for ws_mapping_dialog and main_window are straightforward because their
logic never touches Qt check-state integer comparisons.  The affix_tree_picker
test requires careful sentinel setup so that the == comparisons inside
picker_state() resolve correctly.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Install Qt stubs BEFORE any gramtrans.Lib.ui import happens.
# We must do this at module level so that the module-level code in each UI
# file (e.g. `_GUID_ROLE = QtCore.Qt.UserRole + 1`) resolves with our values.
#
# Critical constraint: the widget base classes (QDialog, QWidget, etc.) must
# be real Python classes, not MagicMock instances.  If they are MagicMocks,
# `class TargetPickerDialog(QtWidgets.QDialog)` produces another MagicMock
# rather than a real class, and `__new__` bypassing breaks.  We define plain
# stub base classes explicitly and attach them as attributes of a MagicMock
# namespace object.
# ---------------------------------------------------------------------------

# Concrete sentinel values that picker_state() compares against.
# PyQt6 fully scopes its enums (Qt.CheckState.Checked, Qt.ItemDataRole.UserRole,
# Qt.ItemFlag.*), so the stub mirrors that nesting. The values must be real
# ints because module-level code evaluates `Qt.ItemDataRole.UserRole + 1`.
_QT_CHECKED = 2          # Qt.CheckState.Checked == 2
_QT_USER_ROLE = 0x0100   # Qt.ItemDataRole.UserRole == 256


class _QDialog:
    """Minimal QDialog stub — just enough for subclassing."""


class _QWidget:
    """Minimal QWidget stub."""


_qtcore_stub = MagicMock()
# Scoped-enum shape (PyQt6). Concrete ints so arithmetic/comparison resolve.
_qtcore_stub.Qt.CheckState.Checked = _QT_CHECKED
_qtcore_stub.Qt.CheckState.Unchecked = 0
_qtcore_stub.Qt.ItemDataRole.UserRole = _QT_USER_ROLE
_qtcore_stub.Qt.Orientation.Horizontal = 1
_qtcore_stub.Qt.ItemFlag.ItemIsUserCheckable = 16
_qtcore_stub.Qt.ItemFlag.ItemIsAutoTristate = 64
_qtcore_stub.Qt.ItemFlag.ItemIsEditable = 2

_qtwidgets_stub = MagicMock()
# Attach real classes so subclasses defined in the UI modules are also real.
_qtwidgets_stub.QDialog = _QDialog
_qtwidgets_stub.QWidget = _QWidget

sys.modules.setdefault("PyQt6", MagicMock(QtCore=_qtcore_stub, QtWidgets=_qtwidgets_stub))
sys.modules.setdefault("PyQt6.QtCore", _qtcore_stub)
sys.modules.setdefault("PyQt6.QtWidgets", _qtwidgets_stub)

# ---------------------------------------------------------------------------
# Now safe to import the UI modules and the model types they depend on.
# ---------------------------------------------------------------------------
from gramtrans.Lib.models import GrammarCategory, WSKind, WSMapping, WSMappingEntry
from gramtrans.Lib.selection import PickerState
from gramtrans.Lib.api import TargetCandidate
from gramtrans.Lib.ui import target_picker as _tp_mod
from gramtrans.Lib.ui import ws_mapping_dialog as _wsd_mod
from gramtrans.Lib.ui import affix_tree_picker as _atp_mod
from gramtrans.Lib.ui import main_window as _mw_mod

TargetPickerDialog = _tp_mod.TargetPickerDialog
WSMappingDialog = _wsd_mod.WSMappingDialog
AffixTreePicker = _atp_mod.AffixTreePicker
MainWindow = _mw_mod.MainWindow

# The GUID/KIND role constants baked into affix_tree_picker at import time.
_GUID_ROLE = _QT_USER_ROLE + 1   # 257
_KIND_ROLE = _QT_USER_ROLE + 2   # 258


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candidate(name: str, path: str = "/tmp/test") -> TargetCandidate:
    return TargetCandidate(project_name=name, project_path=path)


def _bypass(cls):
    """Return a bare instance of *cls* without calling __init__."""
    return cls.__new__(cls)


# ---------------------------------------------------------------------------
# 1. target_picker — no selection → None
# ---------------------------------------------------------------------------

class TestTargetPickerNoSelection:
    def test_returns_none_when_nothing_selected(self):
        """selected_candidate() must return None when _selected_index is None."""
        dlg = _bypass(TargetPickerDialog)
        dlg._candidates = [_make_candidate("Alpha"), _make_candidate("Beta"), _make_candidate("Gamma")]
        dlg._selected_index = None

        result = dlg.selected_candidate()

        assert result is None


# ---------------------------------------------------------------------------
# 2. target_picker — index set → correct candidate returned
# ---------------------------------------------------------------------------

class TestTargetPickerWithSelection:
    def test_returns_correct_candidate_when_index_set(self):
        """selected_candidate() must return candidates[_selected_index]."""
        candidates = [_make_candidate("Alpha"), _make_candidate("Beta"), _make_candidate("Gamma")]
        dlg = _bypass(TargetPickerDialog)
        dlg._candidates = candidates
        dlg._selected_index = 1

        result = dlg.selected_candidate()

        assert result is candidates[1]
        assert result.project_name == "Beta"


# ---------------------------------------------------------------------------
# 3. ws_mapping_dialog — selected_mapping() skips unmapped rows
# ---------------------------------------------------------------------------

class TestWSMappingDialogSelectedMapping:
    def _make_row_mock(self, combo_text: str, checked: bool) -> tuple:
        """Return (combo_mock, check_mock) pair simulating one table row."""
        combo = MagicMock()
        combo.currentText.return_value = combo_text
        check = MagicMock()
        check.isChecked.return_value = checked
        return combo, check

    def test_skips_unmapped_rows_and_includes_mapped(self):
        """Only rows where _row_target_id() returns a non-empty, non-placeholder
        string should appear in selected_mapping().entries."""
        dlg = _bypass(WSMappingDialog)

        # Two required pairs: row 0 mapped, row 1 unmapped (still "(choose…)").
        dlg._required = [
            ("en", WSKind.ANALYSIS),
            ("seh", WSKind.VERNACULAR),
        ]

        combo_mapped, check_mapped = self._make_row_mock("en-gb", False)
        combo_unmapped, check_unmapped = self._make_row_mock("(choose…)", False)

        table = MagicMock()
        table.rowCount.return_value = 2

        def cell_widget(row, col):
            if col == 2:
                return combo_mapped if row == 0 else combo_unmapped
            if col == 3:
                return check_mapped if row == 0 else check_unmapped
            return MagicMock()

        table.cellWidget.side_effect = cell_widget
        dlg._table = table

        mapping = dlg.selected_mapping()

        assert isinstance(mapping, WSMapping)
        assert len(mapping.entries) == 1
        entry = mapping.entries[0]
        assert entry.source_ws_id == "en"
        assert entry.target_ws_id == "en-gb"
        assert entry.source_ws_kind == WSKind.ANALYSIS
        assert entry.create_in_target is False

    def test_create_flag_propagated(self):
        """create_in_target must be True when the checkbox is checked."""
        dlg = _bypass(WSMappingDialog)
        dlg._required = [("seh", WSKind.VERNACULAR)]

        combo, check = self._make_row_mock("seh-new", True)
        table = MagicMock()
        table.rowCount.return_value = 1
        table.cellWidget.side_effect = lambda row, col: combo if col == 2 else check
        dlg._table = table

        mapping = dlg.selected_mapping()

        assert mapping.entries[0].create_in_target is True
        assert mapping.entries[0].target_ws_id == "seh-new"


# ---------------------------------------------------------------------------
# 4. affix_tree_picker — picker_state() collapses checked tree items
# ---------------------------------------------------------------------------

def _make_affix_item(guid: str, checked: bool) -> MagicMock:
    item = MagicMock()
    item.childCount.return_value = 0

    def data(col, role):
        if role == _GUID_ROLE:
            return guid
        if role == _KIND_ROLE:
            return "affix"
        return None

    item.data.side_effect = data
    item.checkState.return_value = _QT_CHECKED if checked else 0
    return item


def _make_slot_item(guid: str, affix_items: list, checked: bool) -> MagicMock:
    item = MagicMock()
    item.childCount.return_value = len(affix_items)
    item.child.side_effect = lambda k: affix_items[k]

    def data(col, role):
        if role == _GUID_ROLE:
            return guid
        if role == _KIND_ROLE:
            return "slot"
        return None

    item.data.side_effect = data
    item.checkState.return_value = _QT_CHECKED if checked else 0
    return item


def _make_template_item(guid: str, slot_items: list, checked: bool) -> MagicMock:
    item = MagicMock()
    item.childCount.return_value = len(slot_items)
    item.child.side_effect = lambda j: slot_items[j]

    def data(col, role):
        if role == _GUID_ROLE:
            return guid
        if role == _KIND_ROLE:
            return "template"
        return None

    item.data.side_effect = data
    item.checkState.return_value = _QT_CHECKED if checked else 0
    return item


class TestAffixTreePickerState:
    def test_fully_checked_template_records_template_slot_and_affixes(self):
        """A fully-checked template → template GUID in checked_templates,
        slot GUID in checked_slots, both leaf affixes in checked_affixes."""
        affix_a = _make_affix_item("affix-A", checked=True)
        affix_b = _make_affix_item("affix-B", checked=True)
        slot1 = _make_slot_item("slot-1", [affix_a, affix_b], checked=True)
        tpl1 = _make_template_item("tpl-1", [slot1], checked=True)

        root = MagicMock()
        root.childCount.return_value = 1
        root.child.side_effect = lambda i: tpl1

        dlg = _bypass(AffixTreePicker)
        tree = MagicMock()
        tree.invisibleRootItem.return_value = root
        dlg._tree = tree

        state = dlg.picker_state()

        assert isinstance(state, PickerState)
        assert state.checked_templates == frozenset({"tpl-1"})
        assert state.checked_slots == frozenset({"slot-1"})
        assert state.checked_affixes == frozenset({"affix-A", "affix-B"})

    def test_partial_check_omits_template_includes_affix(self):
        """Partial check: only one affix checked, template and slot unchecked."""
        affix_a = _make_affix_item("affix-A", checked=True)
        affix_b = _make_affix_item("affix-B", checked=False)
        slot1 = _make_slot_item("slot-1", [affix_a, affix_b], checked=False)
        tpl1 = _make_template_item("tpl-1", [slot1], checked=False)

        root = MagicMock()
        root.childCount.return_value = 1
        root.child.side_effect = lambda i: tpl1

        dlg = _bypass(AffixTreePicker)
        tree = MagicMock()
        tree.invisibleRootItem.return_value = root
        dlg._tree = tree

        state = dlg.picker_state()

        assert state.checked_templates == frozenset()
        assert state.checked_slots == frozenset()
        assert state.checked_affixes == frozenset({"affix-A"})

    def test_empty_tree_returns_empty_picker_state(self):
        """No checked items → all frozensets empty."""
        root = MagicMock()
        root.childCount.return_value = 0

        dlg = _bypass(AffixTreePicker)
        tree = MagicMock()
        tree.invisibleRootItem.return_value = root
        dlg._tree = tree

        state = dlg.picker_state()

        assert state == PickerState()


# ---------------------------------------------------------------------------
# 5. main_window — _collect_selection() translates toggles to Selection
# ---------------------------------------------------------------------------

class TestMainWindowCollectSelection:
    def _make_toggle(self, checked: bool) -> MagicMock:
        cb = MagicMock()
        cb.isChecked.return_value = checked
        return cb

    def test_checked_categories_appear_in_selection(self):
        """Only categories whose toggle isChecked()==True appear in
        Selection.categories with value True."""
        dlg = _bypass(MainWindow)

        on_cats = {GrammarCategory.POS, GrammarCategory.AFFIXES}
        off_cats = {GrammarCategory.SLOTS, GrammarCategory.AFFIX_TEMPLATES}

        dlg._toggles = {
            **{cat: self._make_toggle(True) for cat in on_cats},
            **{cat: self._make_toggle(False) for cat in off_cats},
        }
        closure_cb = MagicMock()
        closure_cb.isChecked.return_value = True
        dlg._closure_cb = closure_cb

        sel = dlg._collect_selection()

        assert sel.categories == {GrammarCategory.POS: True, GrammarCategory.AFFIXES: True}
        assert sel.include_closure is True

    def test_no_checked_categories_gives_empty_dict(self):
        """All toggles off → Selection.categories is empty."""
        dlg = _bypass(MainWindow)

        dlg._toggles = {
            GrammarCategory.POS: self._make_toggle(False),
            GrammarCategory.SLOTS: self._make_toggle(False),
        }
        closure_cb = MagicMock()
        closure_cb.isChecked.return_value = False
        dlg._closure_cb = closure_cb

        sel = dlg._collect_selection()

        assert sel.categories == {}
        assert sel.include_closure is False

    def test_closure_off_propagates(self):
        """include_closure mirrors the closure checkbox state."""
        dlg = _bypass(MainWindow)

        dlg._toggles = {GrammarCategory.POS: self._make_toggle(True)}
        closure_cb = MagicMock()
        closure_cb.isChecked.return_value = False
        dlg._closure_cb = closure_cb

        sel = dlg._collect_selection()

        assert sel.include_closure is False
        assert sel.categories == {GrammarCategory.POS: True}

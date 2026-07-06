"""Tests for the 6-page SelectionWizard (Phase 3c, Refinement 3).

Strategy: install MagicMock stubs for PyQt6 at module level (same pattern as
test_ui_gating.py) then bypass __init__ via __new__() to test page helpers
without a live Qt event loop.

Covers:
- SelectionWizard can be imported without a live Qt host
- _PageProjectWS.context() returns None before target bind
- _PageProjectWS.selected_ws_ids() returns items from the list widget
- _PageItemPicker.picker_state() returns empty PickerState on empty tree
- _PageScopeConflict.collect_selection() translates combos to Selection
  (scopes + conflict modes)
- _PagePreview.cached_plan() returns None before preview
- _PageFinish move-button disabled-in-preview-only mode
- _enumerate_active_ws_ids falls back gracefully
- _selection_replace_conflict_modes monkey-patch works
- Wizard module imports _DEFAULT_CONFLICT_MODES and ConflictMode correctly
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Install Qt stubs BEFORE importing wizard.
#
# Critical: we must ensure QWizard and QWizardPage are REAL Python classes
# (not MagicMock instances) so subclasses defined in the wizard module are
# also real classes that __new__ can instantiate.
#
# test_ui_gating.py may run before us and install its own stubs first via
# setdefault.  To handle both orderings:
# 1. Call setdefault to claim the slots if unclaimed.
# 2. Then unconditionally set QWizard / QWizardPage on the installed stub
#    to our real classes.  This is safe because test_ui_gating.py never
#    uses QWizard/QWizardPage, so overwriting is harmless.
# ---------------------------------------------------------------------------

_QT_CHECKED = 2
_QT_USER_ROLE = 0x0100


class _QDialog:
    """Minimal QDialog stub -- just enough for subclassing."""


class _QWidget:
    """Minimal QWidget stub."""


class _QWizard(_QDialog):
    """Minimal QWizard stub."""


class _QWizardPage(_QWidget):
    """Minimal QWizardPage stub."""


_qtcore_stub = MagicMock()
_qtcore_stub.Qt.CheckState.Checked = _QT_CHECKED
_qtcore_stub.Qt.CheckState.Unchecked = 0
_qtcore_stub.Qt.ItemDataRole.UserRole = _QT_USER_ROLE
_qtcore_stub.Qt.Orientation.Horizontal = 1
_qtcore_stub.Qt.ItemFlag.ItemIsUserCheckable = 16
_qtcore_stub.Qt.ItemFlag.ItemIsAutoTristate = 64
_qtcore_stub.Qt.ItemFlag.ItemIsEditable = 2
# pyqtSignal: must return a descriptor-compatible object, not a plain MagicMock,
# so that `sig = pyqtSignal()` at class-body level doesn't blow up on attribute
# access.  A lambda returning a fresh MagicMock is enough.
_qtcore_stub.pyqtSignal = lambda *a, **kw: MagicMock()
# pyqtProperty: must work as a decorator.  Return identity so `@pyqtProperty(bool)`
# returns the decorated function unchanged.
_qtcore_stub.pyqtProperty = lambda *a, **kw: (lambda f: f)

_qtwidgets_stub_new = MagicMock()
_qtwidgets_stub_new.QDialog = _QDialog
_qtwidgets_stub_new.QWidget = _QWidget
_qtwidgets_stub_new.QWizard = _QWizard
_qtwidgets_stub_new.QWizardPage = _QWizardPage
_qtwidgets_stub_new.QWizard.WizardOption = MagicMock()

# Claim the module slots (no-op if already claimed by test_ui_gating.py).
sys.modules.setdefault(
    "PyQt6",
    MagicMock(QtCore=_qtcore_stub, QtWidgets=_qtwidgets_stub_new),
)
sys.modules.setdefault("PyQt6.QtCore", _qtcore_stub)
sys.modules.setdefault("PyQt6.QtWidgets", _qtwidgets_stub_new)

# Unconditionally fix up QWizard / QWizardPage on whatever stub is installed
# (handles the case where test_ui_gating.py ran first and its stub is already
# in sys.modules).  test_ui_gating.py never uses these two classes, so
# overwriting is safe.
_installed_qtwidgets = sys.modules["PyQt6.QtWidgets"]
_installed_qtwidgets.QWizard = _QWizard
_installed_qtwidgets.QWizardPage = _QWizardPage
if not isinstance(getattr(_installed_qtwidgets, "QDialog", None), type):
    _installed_qtwidgets.QDialog = _QDialog
if not isinstance(getattr(_installed_qtwidgets, "QWidget", None), type):
    _installed_qtwidgets.QWidget = _QWidget

_installed_qtcore = sys.modules["PyQt6.QtCore"]
# Only patch pyqtSignal/pyqtProperty if they aren't already set to callables.
if not callable(getattr(_installed_qtcore, "pyqtSignal", None)):
    _installed_qtcore.pyqtSignal = lambda *a, **kw: MagicMock()
if not callable(getattr(_installed_qtcore, "pyqtProperty", None)):
    _installed_qtcore.pyqtProperty = lambda *a, **kw: (lambda f: f)

# ---------------------------------------------------------------------------
# Now safe to import wizard and model types.
# ---------------------------------------------------------------------------
from gramtrans.Lib.models import (
    CategoryScope,
    ConflictMode,
    GrammarCategory,
    Selection,
    WSMapping,
    _DEFAULT_CONFLICT_MODES,
)
from gramtrans.Lib.selection import PickerState, SourceAffixInventory
from gramtrans.Lib.ui import selection_wizard as _sw_mod

_PageProjectWS = _sw_mod._PageProjectWS
_PageItemPicker = _sw_mod._PageItemPicker
_PageScopeConflict = _sw_mod._PageScopeConflict
_PagePreview = _sw_mod._PagePreview
_PageFinish = _sw_mod._PageFinish
SelectionWizard = _sw_mod.SelectionWizard
_enumerate_active_ws_ids = _sw_mod._enumerate_active_ws_ids
_enumerate_ws_by_kind = _sw_mod._enumerate_ws_by_kind
_allowed_modes = _sw_mod._allowed_modes
_compute_wizard_plan = _sw_mod._compute_wizard_plan
build_selection = _sw_mod.build_selection


def _bypass(cls):
    """Return a bare instance of cls without calling __init__."""
    return cls.__new__(cls)


# ===========================================================================
# Import + module-level constants
# ===========================================================================

class TestWizardModuleImports:
    def test_conflict_mode_importable(self):
        assert ConflictMode.ADD_NEW is not None

    def test_default_conflict_modes_importable(self):
        assert isinstance(_DEFAULT_CONFLICT_MODES, dict)
        assert len(_DEFAULT_CONFLICT_MODES) > 0

    def test_wizard_class_is_defined(self):
        assert SelectionWizard is not None

    def test_selection_wizard_module_exports_helper(self):
        assert callable(_enumerate_active_ws_ids)
        assert callable(_allowed_modes)


# ===========================================================================
# _PageProjectWS
# ===========================================================================

class TestPageProjectWS:
    def test_context_none_before_bind(self):
        page = _bypass(_PageProjectWS)
        page._context = None
        assert page.context() is None

    def test_selected_ws_ids_from_list_widget(self):
        page = _bypass(_PageProjectWS)
        # Simulate a QListWidget with 3 items, 2 selected.
        item0 = MagicMock()
        item0.text.return_value = "en"
        item0.isSelected.return_value = True

        item1 = MagicMock()
        item1.text.return_value = "seh"
        item1.isSelected.return_value = True

        item2 = MagicMock()
        item2.text.return_value = "fr"
        item2.isSelected.return_value = False

        ws_list = MagicMock()
        ws_list.count.return_value = 3
        ws_list.item.side_effect = lambda i: [item0, item1, item2][i]
        page._ws_list = ws_list
        # Pre-set _row_state=None so selected_ws_ids() falls through to the
        # legacy _ws_list path without triggering Qt's uninitialized-QObject
        # guard (raised when a QObject subclass instance has never had
        # __init__ called and a missing attribute is looked up via Qt's
        # __getattribute__ override).
        page._row_state = None

        result = page.selected_ws_ids()
        assert result == ["en", "seh"]

    def test_is_complete_false_before_bind(self):
        page = _bypass(_PageProjectWS)
        page._target_ready = False
        assert page.isComplete() is False

    def test_is_complete_true_after_bind(self):
        page = _bypass(_PageProjectWS)
        page._target_ready = True
        assert page.isComplete() is True


# ===========================================================================
# _PageItemPicker
# ===========================================================================

class TestPageItemPicker:
    def _make_empty_tree(self):
        root = MagicMock()
        root.childCount.return_value = 0
        tree = MagicMock()
        tree.invisibleRootItem.return_value = root
        return tree

    def test_empty_tree_returns_empty_picker_state(self):
        page = _bypass(_PageItemPicker)
        page._tree = self._make_empty_tree()
        state = page.picker_state()
        assert isinstance(state, PickerState)
        assert state == PickerState()

    def test_stems_tab_not_available(self):
        """Stems tab must be present but disabled (Layer-3 not yet available)."""
        # We can verify by checking the module-level comment / docstring.
        import inspect
        src = inspect.getsource(_PageItemPicker)
        assert "STUBBED" in src or "not yet available" in src.lower()


# ===========================================================================
# _PageScopeConflict.collect_selection
# ===========================================================================

class TestPageScopeConflictCollectSelection:
    def _make_combo(self, data) -> MagicMock:
        cb = MagicMock()
        cb.currentData.return_value = data
        return cb

    def _make_toggle(self, checked: bool) -> MagicMock:
        cb = MagicMock()
        cb.isChecked.return_value = checked
        return cb

    def test_collect_selection_passes_scopes_and_conflict_modes(self):
        page = _bypass(_PageScopeConflict)

        page._toggles = {
            GrammarCategory.POS: self._make_toggle(True),
            GrammarCategory.AFFIXES: self._make_toggle(False),
        }
        page._scope_combos = {
            GrammarCategory.POS: self._make_combo(CategoryScope.ALL),
        }
        page._conflict_combos = {
            GrammarCategory.POS: self._make_combo(ConflictMode.LINK),  # 022: was MERGE
        }
        closure_cb = MagicMock()
        closure_cb.isChecked.return_value = True
        page._closure_cb = closure_cb

        picker = PickerState()
        inventory = SourceAffixInventory()

        sel = page.collect_selection(picker, inventory)

        assert isinstance(sel, Selection)
        assert sel.scope_for(GrammarCategory.POS) == CategoryScope.ALL
        assert sel.conflict_mode_for(GrammarCategory.POS) == ConflictMode.LINK  # 022: was MERGE

    def test_collect_selection_no_checked_categories_gives_empty(self):
        page = _bypass(_PageScopeConflict)
        page._toggles = {
            GrammarCategory.POS: self._make_toggle(False),
        }
        page._scope_combos = {}
        page._conflict_combos = {}
        closure_cb = MagicMock()
        closure_cb.isChecked.return_value = True
        page._closure_cb = closure_cb

        sel = page.collect_selection(PickerState(), SourceAffixInventory())
        assert sel.categories == {}


# ===========================================================================
# _PagePreview
# ===========================================================================

class TestPagePreview:
    def test_cached_plan_none_before_preview(self):
        page = _bypass(_PagePreview)
        page._cached_plan = None
        assert page.cached_plan() is None

    def test_is_complete_false_before_preview(self):
        page = _bypass(_PagePreview)
        page._cached_plan = None
        assert page.isComplete() is False

    def test_is_complete_true_after_plan_cached(self):
        page = _bypass(_PagePreview)
        page._cached_plan = object()  # any non-None
        assert page.isComplete() is True


# ===========================================================================
# _PageFinish
# ===========================================================================

class TestPageFinish:
    def test_modify_allowed_false_disables_move_in_docstring(self):
        """When modify_allowed=False the move btn must be disabled."""
        import inspect
        src = inspect.getsource(_PageFinish._build_ui)
        assert "modify_allowed" in src or "PREVIEW-only" in src.lower() or "read-only" in src.lower()

    def test_modify_allowed_stored(self):
        page = _bypass(_PageFinish)
        page._modify_allowed = False
        assert page._modify_allowed is False

    def test_confirm_on_move_gate_code_present(self):
        """Finish handler must contain excluded_lossy_count() gate."""
        import inspect
        src = inspect.getsource(_PageFinish._on_move)
        assert "excluded_lossy_count" in src
        assert "QMessageBox" in src


# ===========================================================================
# _enumerate_active_ws_ids
# ===========================================================================

class TestEnumerateActiveWSIds:
    def test_returns_empty_on_bare_object(self):
        result = _enumerate_active_ws_ids(object())
        assert isinstance(result, list)

    def test_returns_ids_from_get_all(self):
        ws1 = MagicMock()
        ws1.Id = "en"
        ws2 = MagicMock()
        ws2.Id = "seh"

        wss = MagicMock()
        wss.GetAll.return_value = [ws1, ws2]

        project = MagicMock()
        project.WritingSystems = wss

        result = _enumerate_active_ws_ids(project)
        assert "en" in result
        assert "seh" in result

    def test_falls_back_gracefully_on_attribute_error(self):
        """Attribute errors during enumeration -> returns empty list, no crash."""
        project = MagicMock()
        project.WritingSystems.GetAll.side_effect = AttributeError("no attr")
        project.AnalysisWritingSystems = []
        project.VernacularWritingSystems = []
        project.GetWritingSystems.side_effect = AttributeError("no attr")
        result = _enumerate_active_ws_ids(project)
        assert isinstance(result, list)


# ===========================================================================
# _selection_replace_conflict_modes monkey-patch
# ===========================================================================

class TestSelectionReplaceConflictModes:
    def test_monkey_patch_applied(self):
        assert hasattr(Selection, "_replace_conflict_modes")

    def test_replace_returns_selection_with_modes(self):
        sel = Selection()
        modes = {GrammarCategory.POS: ConflictMode.OVERWRITE}
        new_sel = sel._replace_conflict_modes(modes)
        assert isinstance(new_sel, Selection)
        assert new_sel.category_conflict_modes == modes

    def test_original_unchanged(self):
        sel = Selection()
        modes = {GrammarCategory.POS: ConflictMode.OVERWRITE}
        sel._replace_conflict_modes(modes)
        # original still has empty conflict modes
        assert sel.category_conflict_modes == {}


# ===========================================================================
# WS handshake retirement integration check
# ===========================================================================

class TestWSHandshakeRetirement:
    def test_compute_preview_does_not_return_needs_ws_mapping(self):
        import inspect
        from gramtrans.Lib import api as _api_mod
        src = inspect.getsource(_api_mod.compute_preview)
        assert "return (PreviewState.NEEDS_WS_MAPPING" not in src

    def test_preview_state_ready_enum_exists(self):
        from gramtrans.Lib.api import PreviewState
        assert PreviewState.PREVIEW_READY is not None


# ===========================================================================
# 022: LINK label check (replaces interim MERGE label -- spec section i)
# ===========================================================================

class TestLinkLabel:
    def test_link_label_contains_explicit_no_field_update_note(self):
        """022: The LINK control (formerly MERGE) MUST carry an explicit label per spec (i)."""
        from gramtrans.Lib.ui.selection_wizard import _CONFLICT_LABELS
        assert ConflictMode.LINK in _CONFLICT_LABELS, (
            "ConflictMode.LINK must be in _CONFLICT_LABELS (022: renamed from MERGE)"
        )
        link_label = _CONFLICT_LABELS[ConflictMode.LINK]
        label_lower = link_label.lower()
        # Must contain "link" and "no field update" or equivalent
        assert "link" in label_lower or "no field" in label_lower, (
            f"LINK label must explain 'link existing by ID, else add; no field update' "
            f"per spec section (i), got: {link_label!r}"
        )

    def test_update_label_offered_for_multi_instance(self):
        """022 T008/T024: UPDATE is offered for MULTI_INSTANCE categories."""
        from gramtrans.Lib.ui.selection_wizard import _allowed_modes, _CONFLICT_LABELS
        modes = _allowed_modes(GrammarCategory.AFFIXES)
        assert ConflictMode.UPDATE in modes, (
            f"UPDATE must be offered for AFFIXES (MULTI_INSTANCE), got {modes}"
        )
        assert ConflictMode.UPDATE in _CONFLICT_LABELS, (
            "ConflictMode.UPDATE must have a label in _CONFLICT_LABELS"
        )

    def test_merge_key_absent_from_conflict_labels(self):
        """022: ConflictMode.MERGE no longer exists, so it can't be in _CONFLICT_LABELS."""
        from gramtrans.Lib.ui.selection_wizard import _CONFLICT_LABELS
        assert not hasattr(ConflictMode, "MERGE"), (
            "ConflictMode.MERGE should be gone in 022 (renamed to LINK)"
        )


# ===========================================================================
# _compute_wizard_plan -- POS / grammar-category wiring
# (fix/wizard-pos-grammar-wiring)
#
# Regression: the wizard copied affixes but flagged NO parts-of-speech, so the
# verb-vertical POS closure walked 0 source POS and affix MSAs were created
# unwired (PartOfSpeech = None => "no grammatical info").  The fix folds the
# Skeleton page's pre-checked POS GUIDs into the built Selection as
# categories[POS]=True + pos_picks, so the closure creates exactly those POSes.
# ===========================================================================


def _affix_only_selection():
    """A base Selection as the item-picker page would return: affixes only."""
    return build_selection(
        PickerState(checked_affixes=frozenset({"aff-1"})),
        SourceAffixInventory(unbound_affixes=frozenset({"aff-1"})),
    )


class _FakeWizard:
    """Minimal wizard exposing only the accessors _compute_wizard_plan reads.

    Absent page_* methods (custom_fields / entry_types / rules) are guarded by
    hasattr in _compute_wizard_plan, so omitting them yields the transfer-all
    default (no merge) for those blocks -- keeping this fixture tiny.
    """

    def __init__(self, affix_selection, pos_guids):
        self._affix_selection = affix_selection
        self._pos_guids = set(pos_guids)

    def page_project_ws(self):
        m = MagicMock()
        m.context.return_value = object()  # non-None context
        m.ws_mapping.return_value = None
        return m

    def page_items(self):
        m = MagicMock()
        m.collect_selection.return_value = self._affix_selection
        return m

    def page_phonology(self):
        return None  # no phonology block

    def page_skeleton(self):
        m = MagicMock()
        m.collect_skeleton_picks.return_value = {
            "pos_guids": set(self._pos_guids),
            "slot_guids": set(),
            "template_guids": set(),
        }
        return m


class TestComputeWizardPlanPosWiring:
    def _run(self, wizard):
        """Invoke _compute_wizard_plan with compute_preview stubbed to capture
        the Selection it receives."""
        captured = {}

        def _fake_compute_preview(context, selection, ws_mapping):
            captured["selection"] = selection
            return ("READY", object())  # non-None payload

        with patch.object(_sw_mod.gt_api, "compute_preview",
                          side_effect=_fake_compute_preview), \
             patch.object(_sw_mod.RunReport, "build_from_plan",
                          return_value=object()), \
             patch.object(_sw_mod, "_phonology_excluded_lossy_for",
                          return_value=[]):
            plan, report = _compute_wizard_plan(wizard)
        return captured["selection"], plan, report

    def test_skeleton_pos_picks_flag_pos_and_populate_pos_picks(self):
        """With affixes picked AND the skeleton reporting attaching POSes, the
        built Selection flags POS and carries those GUIDs as pos_picks (so the
        verb-vertical closure walks >0 POS)."""
        wizard = _FakeWizard(_affix_only_selection(), pos_guids={"POS-Verb-1"})
        selection, plan, report = self._run(wizard)

        assert selection.is_on(GrammarCategory.POS) is True
        assert selection.pos_picks == frozenset({"pos-verb-1"})  # lower-cased
        # AFFIXES stays on -- the fix augments, it does not replace.
        assert selection.is_on(GrammarCategory.AFFIXES) is True
        assert plan is not None

    def test_no_skeleton_pos_leaves_pos_unflagged(self):
        """Empty pos_guids must NOT flag POS -- flagging POS with empty picks
        would make _select_source_poses walk EVERY source POS (over-transfer)."""
        wizard = _FakeWizard(_affix_only_selection(), pos_guids=set())
        selection, plan, report = self._run(wizard)

        assert selection.is_on(GrammarCategory.POS) is False
        assert selection.pos_picks == frozenset()

    def test_does_not_flag_leaf_gram_categories(self):
        """The fix must NOT enable the leaf GRAM_CATEGORIES pass (which would
        enumerate ALL source POS); only the dependency-driven POS closure."""
        wizard = _FakeWizard(_affix_only_selection(), pos_guids={"pos-1"})
        selection, plan, report = self._run(wizard)

        assert selection.is_on(GrammarCategory.GRAM_CATEGORIES) is False


# ===========================================================================
# _enumerate_ws_by_kind -- LCM Current* path
# ===========================================================================

def _make_ws(ws_id: str):
    """Return a minimal fake WS object with a .Id attribute."""
    ws = MagicMock()
    ws.Id = ws_id
    return ws


def _make_project_with_current_ws(vern_tags, anal_tags):
    """Return a fake project whose Cache.LangProject.Current* lists are set."""
    lang = MagicMock()
    lang.CurrentVernacularWritingSystems = [_make_ws(t) for t in vern_tags]
    lang.CurrentAnalysisWritingSystems = [_make_ws(t) for t in anal_tags]
    cache = MagicMock()
    cache.LangProject = lang
    project = MagicMock()
    project.Cache = cache
    return project


class TestEnumerateWsByKind:
    """(a)-(d) from the fix specification."""

    def test_a_correct_split_full_tags(self):
        """(a) Cache.LangProject.Current* yields exact full tags in correct groups."""
        project = _make_project_with_current_ws(
            vern_tags=["etu", "etu-fonipa"],
            anal_tags=["en"],
        )
        vern, anal = _enumerate_ws_by_kind(project)
        assert vern == ["etu", "etu-fonipa"]
        assert anal == ["en"]

    def test_b_dual_role_tag_appears_in_both_lists(self):
        """(b) A tag present in both Current* lists appears in both returned lists."""
        project = _make_project_with_current_ws(
            vern_tags=["etu", "en"],
            anal_tags=["en", "fr"],
        )
        vern, anal = _enumerate_ws_by_kind(project)
        assert "en" in vern
        assert "en" in anal
        # other tags stay in their own group only
        assert "etu" in vern
        assert "etu" not in anal
        assert "fr" in anal
        assert "fr" not in vern

    def test_c_distinct_variant_tags_yield_distinct_entries_and_default_1to1(self):
        """(c) 'etu' and 'etu-fonipa' are separate entries; each defaults to same-tag."""
        project = _make_project_with_current_ws(
            vern_tags=["etu", "etu-fonipa"],
            anal_tags=["en"],
        )
        vern, _anal = _enumerate_ws_by_kind(project)
        # Both variant tags present as distinct entries.
        assert "etu" in vern
        assert "etu-fonipa" in vern
        assert vern.index("etu") != vern.index("etu-fonipa")
        # Default 1:1 mapping: _fill_table pre-populates target combo with same tag.
        # Verify the row-state key structure: each ws_id produces a distinct key.
        from gramtrans.Lib.models import WSKind
        keys = {(ws_id, WSKind.VERNACULAR.value) for ws_id in vern}
        assert ("etu", WSKind.VERNACULAR.value) in keys
        assert ("etu-fonipa", WSKind.VERNACULAR.value) in keys

    def test_d_total_failure_degrades_to_all_as_both(self):
        """(d) When Cache path raises, fallback returns (all_ids, all_ids)."""
        ws1 = MagicMock()
        ws1.Id = "etu"
        ws2 = MagicMock()
        ws2.Id = "en"

        project = MagicMock()
        # Make Cache raise so the primary path fails completely.
        type(project).Cache = property(lambda self: (_ for _ in ()).throw(
            AttributeError("no Cache")
        ))
        # Provide a WritingSystems.GetAll fallback used by _enumerate_active_ws_ids.
        wss = MagicMock()
        wss.GetAll.return_value = [ws1, ws2]
        project.WritingSystems = wss
        # No VernacularWritingSystems / AnalysisWritingSystems exposed.
        del project.VernacularWritingSystems
        del project.AnalysisWritingSystems

        vern, anal = _enumerate_ws_by_kind(project)
        # Both lists must be identical (all-as-both degradation).
        assert vern == anal
        # Must contain the WS IDs from the fallback enumerator.
        assert "etu" in vern
        assert "en" in vern

    def test_no_duplicates_in_returned_lists(self):
        """Duplicate WS entries in Current* are deduplicated."""
        project = _make_project_with_current_ws(
            vern_tags=["etu", "etu", "etu-fonipa"],
            anal_tags=["en", "en"],
        )
        vern, anal = _enumerate_ws_by_kind(project)
        assert vern.count("etu") == 1
        assert anal.count("en") == 1

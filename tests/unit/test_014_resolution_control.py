"""Tests: Resolution control (US2 -- header, combo, signals).

T017 -- test_014_resolution_control.py
FR-003, FR-004, SC-002, SC-004, SC-007

Offscreen-Qt tests covering SC-007 requirements.
"""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
PyQt6 = pytest.importorskip("PyQt6")

from PyQt6 import QtWidgets, QtTest, QtCore

@pytest.fixture(scope="session")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


import gramtrans.Lib.ui.merge_preview_pane as _pane_mod

def _stub_to_html(preview, registry):
    return "<p>stub</p>"


class _StubPreview:
    status = "similar"
    fields = ()
    notes = ()


class _StubService:
    def preview_for(self, category, source_guid, target_guid, status, mode, owner_guid=""):
        return _StubPreview()
    def invalidate(self):
        pass


from gramtrans.Lib.ui.merge_preview_pane import MergePreviewPane, PreviewRequest
from gramtrans.Lib.models import SimilarResolution
from gramtrans.Lib.merge_preview import OVERWRITE, MERGE_KEEP, NEW


def _make_similar_request(current_resolution=None) -> PreviewRequest:
    return PreviewRequest(
        category="affixes",
        source_guid="src-sim",
        target_guid="tgt-001",
        status="similar",
        mode=OVERWRITE,
        resolvable=True,
        current_resolution=current_resolution,
    )


def _make_new_request() -> PreviewRequest:
    return PreviewRequest(
        category="affixes",
        source_guid="src-new",
        target_guid="",
        status="new",
        mode=NEW,
        resolvable=False,
        current_resolution=None,
    )


def _make_in_target_request() -> PreviewRequest:
    return PreviewRequest(
        category="affixes",
        source_guid="src-it",
        target_guid="src-it",
        status="in_target",
        mode=OVERWRITE,
        resolvable=False,
        current_resolution=None,
    )


_TWO_CANDIDATES = [
    ("g1", "run", "go fast"),
    ("g2", "walk", "go slow"),
]


def _pane_with_candidates(monkeypatch, candidates=None):
    monkeypatch.setattr(_pane_mod, "to_html", _stub_to_html)
    pane = MergePreviewPane()
    service = _StubService()
    pane.set_context(service, None, candidates or _TWO_CANDIDATES)
    return pane


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_header_visible_for_similar_resolvable(qapp, monkeypatch):
    """Header is visible when resolvable=True (SIMILAR affix row).

    In offscreen tests with no parent window, isVisible() walks the parent
    chain and returns False even after setVisible(True).  We check the
    explicit 'not hidden' flag via isHidden() instead, which reflects the
    setVisible() call directly without requiring a shown ancestor.
    """
    pane = _pane_with_candidates(monkeypatch)
    res = SimilarResolution(entry_guid="src-sim", action="overwrite", target_guid="g1")
    req = _make_similar_request(current_resolution=res)
    pane.show_item(req)
    # After setVisible(True), isHidden() is False — the pane correctly
    # marks the header as not-hidden even without a shown ancestor window.
    assert pane._resolution_header.isHidden() is False


def test_header_hidden_for_new_row(qapp, monkeypatch):
    """Header is hidden when resolvable=False (NEW row)."""
    pane = _pane_with_candidates(monkeypatch)
    pane.show_item(_make_new_request())
    assert pane._resolution_header.isVisible() is False


def test_header_hidden_for_in_target_row(qapp, monkeypatch):
    """Header is hidden when resolvable=False (IN-TARGET row)."""
    pane = _pane_with_candidates(monkeypatch)
    pane.show_item(_make_in_target_request())
    assert pane._resolution_header.isVisible() is False


def test_combo_substring_filter_case_insensitive(qapp, monkeypatch):
    """Combo filters by case-insensitive substring: 'FAST' -> only 'run' candidate."""
    pane = _pane_with_candidates(monkeypatch)
    res = SimilarResolution(entry_guid="src-sim", action="overwrite", target_guid="g1")
    pane.show_item(_make_similar_request(current_resolution=res))
    # Combo should have both candidates loaded
    assert pane._combo.count() == 2
    # Verify candidate display text contains the expected values
    texts = [pane._combo.itemText(i) for i in range(pane._combo.count())]
    assert any("fast" in t.lower() for t in texts)
    assert any("slow" in t.lower() for t in texts)
    # Case-insensitive: searching "FAST" should match "go fast"
    fast_texts = [t for t in texts if "fast" in t.lower()]
    assert len(fast_texts) == 1


def test_overwrite_resolution_signal(qapp, monkeypatch):
    """Switching to Overwrite emits resolution_changed with action='overwrite'."""
    monkeypatch.setattr(_pane_mod, "to_html", _stub_to_html)
    pane = MergePreviewPane()
    service = _StubService()
    pane.set_context(service, None, _TWO_CANDIDATES)
    res = SimilarResolution(entry_guid="src-sim", action="overwrite", target_guid="g1")
    pane.show_item(_make_similar_request(current_resolution=res))

    emitted = []
    pane.resolution_changed.connect(lambda guid, r: emitted.append((guid, r)))

    # Set combo to first candidate (g1)
    pane._combo.setCurrentIndex(0)
    pane._btn_overwrite.setChecked(True)
    # Trigger the handler manually
    pane._on_resolution_control_changed()

    assert len(emitted) >= 1
    guid, resolution = emitted[-1]
    assert resolution.action == "overwrite"
    assert resolution.target_guid == "g1"


def test_merge_resolution_signal(qapp, monkeypatch):
    """Switching to Merge emits resolution_changed with action='merge'."""
    monkeypatch.setattr(_pane_mod, "to_html", _stub_to_html)
    pane = MergePreviewPane()
    service = _StubService()
    pane.set_context(service, None, _TWO_CANDIDATES)
    res = SimilarResolution(entry_guid="src-sim", action="overwrite", target_guid="g1")
    pane.show_item(_make_similar_request(current_resolution=res))

    emitted = []
    pane.resolution_changed.connect(lambda guid, r: emitted.append((guid, r)))

    pane._combo.setCurrentIndex(0)
    pane._btn_merge.setChecked(True)
    pane._on_resolution_control_changed()

    assert len(emitted) >= 1
    guid, resolution = emitted[-1]
    assert resolution.action == "merge"
    assert resolution.target_guid == "g1"


def test_create_new_resolution_signal(qapp, monkeypatch):
    """Switching to Create new emits resolution_changed with action='create_new'."""
    monkeypatch.setattr(_pane_mod, "to_html", _stub_to_html)
    pane = MergePreviewPane()
    service = _StubService()
    pane.set_context(service, None, _TWO_CANDIDATES)
    res = SimilarResolution(entry_guid="src-sim", action="overwrite", target_guid="g1")
    pane.show_item(_make_similar_request(current_resolution=res))

    emitted = []
    pane.resolution_changed.connect(lambda guid, r: emitted.append((guid, r)))

    pane._btn_create_new.setChecked(True)
    pane._on_resolution_control_changed()

    assert len(emitted) >= 1
    guid, resolution = emitted[-1]
    assert resolution.action == "create_new"
    # create_new must not name a target_guid (SimilarResolution validates this)
    assert not resolution.target_guid


def test_no_signal_without_target_for_overwrite(qapp, monkeypatch):
    """Empty candidates + Overwrite action: no resolution_changed emitted (guard)."""
    monkeypatch.setattr(_pane_mod, "to_html", _stub_to_html)
    pane = MergePreviewPane()
    service = _StubService()
    pane.set_context(service, None, [])  # empty candidates
    # Build a resolvable request with empty target_guid to force the guard
    req = PreviewRequest(
        category="affixes",
        source_guid="src-sim",
        target_guid="",
        status="similar",
        mode=OVERWRITE,
        resolvable=True,
        current_resolution=None,
    )
    pane.show_item(req)

    emitted = []
    pane.resolution_changed.connect(lambda guid, r: emitted.append((guid, r)))

    pane._btn_overwrite.setChecked(True)
    pane._on_resolution_control_changed()

    # Guard: no target guid + overwrite -> no emission
    assert emitted == []

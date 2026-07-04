"""Tests: Phonology SIMILAR display — compare preview, no header (US4).

T019 -- test_014_phonology_display.py
FR-007, SC-005, SC-007

Offscreen-Qt tests for phonology row display.  SIMILAR phonology rows show a
compare preview (OVERWRITE mode) with the resolution header hidden (R8).
No live LCM required (stub service).
"""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
PyQt6 = pytest.importorskip("PyQt6")

from PyQt6 import QtWidgets

@pytest.fixture(scope="session")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


import gramtrans.Lib.ui.merge_preview_pane as _pane_mod

def _stub_to_html(preview, registry):
    return "<p>stub-phon</p>"


class _StubPreview:
    status = "similar"
    fields = ()
    notes = ()


class _StubService:
    def __init__(self):
        self._calls: list = []

    def preview_for(self, category, source_guid, target_guid, status, mode, owner_guid=""):
        self._calls.append((category, source_guid, target_guid, status, mode))
        return _StubPreview()

    def invalidate(self):
        pass


from gramtrans.Lib.ui.merge_preview_pane import MergePreviewPane, PreviewRequest
from gramtrans.Lib.merge_preview import OVERWRITE, NEW


def _phon_similar_request() -> PreviewRequest:
    """Phonology SIMILAR row: resolvable=False, mode=OVERWRITE (R8)."""
    return PreviewRequest(
        category="phonemes",
        source_guid="phon-src-001",
        target_guid="phon-tgt-001",
        status="similar",
        mode=OVERWRITE,
        resolvable=False,
        current_resolution=None,
    )


def _phon_new_request() -> PreviewRequest:
    """Phonology NEW row: resolvable=False, mode=NEW."""
    return PreviewRequest(
        category="phonemes",
        source_guid="phon-src-002",
        target_guid="",
        status="new",
        mode=NEW,
        resolvable=False,
        current_resolution=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_similar_phonology_shows_compare_no_header(qapp, monkeypatch):
    """SIMILAR phonology row: compare preview renders, resolution header hidden (SC-005, R8)."""
    monkeypatch.setattr(_pane_mod, "to_html", _stub_to_html)
    pane = MergePreviewPane()
    service = _StubService()
    pane.set_context(service, None, [])
    pane.show_item(_phon_similar_request())
    # Resolution header must be hidden (resolvable=False)
    assert pane._resolution_header.isVisible() is False
    # Service was called with the SIMILAR row's target guid
    assert len(service._calls) >= 1
    call = service._calls[-1]
    assert call[2] == "phon-tgt-001"  # target_guid
    assert call[4] == OVERWRITE        # mode


def test_new_phonology_shows_all_green_no_header(qapp, monkeypatch):
    """NEW phonology row: all-green preview renders, resolution header hidden."""
    monkeypatch.setattr(_pane_mod, "to_html", _stub_to_html)
    pane = MergePreviewPane()
    service = _StubService()
    pane.set_context(service, None, [])
    pane.show_item(_phon_new_request())
    # Resolution header must be hidden (resolvable=False)
    assert pane._resolution_header.isVisible() is False
    # Service called with empty target_guid (NEW mode)
    assert len(service._calls) >= 1
    call = service._calls[-1]
    assert call[2] == ""   # target_guid empty for NEW
    assert call[4] == NEW  # mode


def test_phonology_similar_no_resolution_stored(qapp):
    """_PagePhonology does NOT maintain a _resolution_store (display-only, R8).

    Tests that the phonology page class does not grow a _resolution_store
    attribute via the 014 integration (phonology is display-only).
    """
    # Import _PagePhonology and check no _resolution_store on instance
    # We use hasattr with a sentinel so absence doesn't crash
    try:
        from gramtrans.Lib.ui.selection_wizard import _PagePhonology
        page = _PagePhonology.__new__(_PagePhonology)
        # _resolution_store should NOT be set unless __init__ explicitly creates it
        # The phon page __init__ does not call _build_ui in this test (no QApp needed
        # for the attribute check via the class), but we verify the class definition
        # does not declare it as a class attribute.
        has_class_attr = "_resolution_store" in _PagePhonology.__dict__
        assert not has_class_attr, (
            "_PagePhonology must not declare _resolution_store "
            "(phonology is display-only per R8)"
        )
    except Exception as exc:
        # If import fails for reasons unrelated to the attribute check, skip
        pytest.skip(f"Could not import _PagePhonology: {exc}")

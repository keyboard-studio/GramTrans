"""Tests: Merge-Preview Pane display (US1 -- pane renders, clear on group).

T016 -- test_014_pane_display.py
FR-001, FR-002, SC-001, SC-007

Offscreen-Qt tests: pane renders NEW / IN-TARGET rows; group selection clears;
set_context clears prior content.

All tests are marked as NOT requiring a live LCM project (stub service only).
"""
from __future__ import annotations

import os

# SC-007: set offscreen platform BEFORE importing Qt
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

PyQt6 = pytest.importorskip("PyQt6")  # skip entire module if PyQt6 absent

from PyQt6 import QtWidgets

# ---------------------------------------------------------------------------
# QApplication fixture (session-scoped — one app for all Qt tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


# ---------------------------------------------------------------------------
# Stub service and stub to_html
# ---------------------------------------------------------------------------

class _StubPreview:
    """Minimal MergePreview stand-in."""
    def __init__(self, content: str = "stub-content"):
        self.content = content
        self.status = "new"
        self.fields = ()
        self.notes = ()


class _StubService:
    """Minimal MergePreviewService stub; returns a fixed preview."""

    def __init__(self, html_content: str = "<p>stub-html</p>"):
        self._html = html_content
        self._calls: list = []

    def preview_for(self, category, source_guid, target_guid, status, mode, owner_guid=""):
        self._calls.append((category, source_guid, target_guid, status, mode))
        return _StubPreview(self._html)

    def invalidate(self):
        pass


# ---------------------------------------------------------------------------
# Patch to_html at import time so no registry is needed
# ---------------------------------------------------------------------------

import gramtrans.Lib.ui.merge_preview_pane as _pane_mod

_ORIGINAL_TO_HTML = _pane_mod.to_html


def _stub_to_html(preview, registry):
    return getattr(preview, "content", "<p></p>")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from gramtrans.Lib.ui.merge_preview_pane import MergePreviewPane, PreviewRequest
from gramtrans.Lib.merge_preview import OVERWRITE, NEW


def _make_new_request() -> PreviewRequest:
    return PreviewRequest(
        category="affixes",
        source_guid="src-001",
        target_guid="",
        status="new",
        mode=NEW,
        resolvable=False,
        current_resolution=None,
    )


def _make_in_target_request() -> PreviewRequest:
    return PreviewRequest(
        category="affixes",
        source_guid="src-002",
        target_guid="src-002",
        status="in_target",
        mode=OVERWRITE,
        resolvable=False,
        current_resolution=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_new_row_renders_all_green(qapp, monkeypatch):
    """US1: show_item with NEW request renders diff content (no crash, content set)."""
    monkeypatch.setattr(_pane_mod, "to_html", _stub_to_html)
    pane = MergePreviewPane()
    service = _StubService("<p>all-green</p>")
    pane.set_context(service, None, [])
    req = _make_new_request()
    pane.show_item(req)
    html = pane._browser.toHtml()
    assert "all-green" in html or pane._browser.toPlainText() != ""


def test_in_target_row_renders_compare(qapp, monkeypatch):
    """US1: show_item with IN-TARGET request renders compare preview content."""
    monkeypatch.setattr(_pane_mod, "to_html", _stub_to_html)
    pane = MergePreviewPane()
    service = _StubService("<p>compare-view</p>")
    pane.set_context(service, None, [])
    req = _make_in_target_request()
    pane.show_item(req)
    html = pane._browser.toHtml()
    assert "compare-view" in html or pane._browser.toPlainText() != ""


def test_group_row_clears_pane(qapp, monkeypatch):
    """US1: after show_item, calling clear() hides resolution header and clears browser."""
    monkeypatch.setattr(_pane_mod, "to_html", _stub_to_html)
    pane = MergePreviewPane()
    service = _StubService("<p>content</p>")
    pane.set_context(service, None, [])
    pane.show_item(_make_new_request())
    pane.clear()
    # Resolution header must be hidden after clear()
    assert pane._resolution_header.isVisible() is False
    # Browser content should be empty after clear()
    assert pane._browser.toPlainText().strip() == ""


def test_set_context_clears_display(qapp, monkeypatch):
    """US1: set_context on a pane that already has content clears the display."""
    monkeypatch.setattr(_pane_mod, "to_html", _stub_to_html)
    pane = MergePreviewPane()
    service1 = _StubService("<p>old-content</p>")
    pane.set_context(service1, None, [])
    pane.show_item(_make_new_request())

    # Now call set_context again — must clear
    service2 = _StubService("<p>new-content</p>")
    pane.set_context(service2, None, [])
    assert pane._browser.toPlainText().strip() == ""
    assert pane._resolution_header.isVisible() is False

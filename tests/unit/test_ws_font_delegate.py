"""WsFontDelegate wiring smoke tests (spec 011).

Painting is exercised in the live GUI harness (needs a QPainter + QApplication);
here we guard the pure wiring contract: the data-role constant and the
``set_ws_runs`` fast-path guards, using a capturing fake item so no QApplication
is created (mirrors the repo's no-QApplication test policy).
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6 import QtCore  # noqa: E402

from gramtrans.Lib.ui.ws_font_delegate import WS_RUNS_ROLE, set_ws_runs  # noqa: E402
from gramtrans.Lib.ws_fonts import WsRole  # noqa: E402


class _CapturingItem:
    def __init__(self):
        self.calls = []

    def setData(self, column, role, value):
        self.calls.append((column, role, value))


def test_runs_role_is_a_high_user_role():
    assert WS_RUNS_ROLE > int(QtCore.Qt.ItemDataRole.UserRole)


def test_set_ws_runs_stores_multi_ws_runs():
    item = _CapturingItem()
    runs = (("y", WsRole.VERNACULAR), (" ", None), ("/j/", WsRole.IPA))
    set_ws_runs(item, 0, runs)
    assert item.calls == [(0, WS_RUNS_ROLE, runs)]


def test_set_ws_runs_noop_for_empty_runs():
    item = _CapturingItem()
    set_ws_runs(item, 0, ())
    assert item.calls == []


def test_set_ws_runs_noop_for_single_ws_less_run():
    # A lone None-role run gains nothing over the default font -> skip the
    # delegate's slow path entirely.
    item = _CapturingItem()
    set_ws_runs(item, 0, (("(unnamed)", None),))
    assert item.calls == []


def test_set_ws_runs_stores_single_vernacular_run():
    item = _CapturingItem()
    runs = (("r", WsRole.VERNACULAR),)
    set_ws_runs(item, 0, runs)
    assert item.calls == [(0, WS_RUNS_ROLE, runs)]

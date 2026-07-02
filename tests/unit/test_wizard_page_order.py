"""T006 — wizard named-accessor plumbing + no-literal-index guard (spec 010 P-1/P-2).

Inserting the Phonology page at index 1 shifts every literal `wizard.page(N)`.
The fix (spec 010) routes all cross-page lookups through named accessors. These
tests guard that: (a) each accessor returns its stored `_page_*` attribute, and
(b) no literal `.page(<int>)` call survives in the wizard source — a mis-index
would otherwise silently return the wrong page with no crash.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from gramtrans.Lib.ui import selection_wizard as _sw

SelectionWizard = _sw.SelectionWizard

_ACCESSORS = [
    ("page_project_ws", "_page_project_ws"),
    ("page_phonology", "_page_phonology"),
    ("page_items", "_page_items"),
    ("page_skeleton", "_page_skeleton"),
    ("page_gram_deps", "_page_gram_deps"),
    ("page_preview", "_page_preview"),
    ("page_finish", "_page_finish"),
]


class _StubWizard:
    """Plain object standing in for `self` — avoids creating an uninitialized
    PyQt6 QObject (which pollutes sip state across the test session)."""


def _stub_with_pages():
    w = _StubWizard()
    for _, attr in _ACCESSORS:
        setattr(w, attr, object())  # unique sentinel per page
    return w


def test_accessors_return_stored_attributes():
    w = _stub_with_pages()
    for accessor, attr in _ACCESSORS:
        fn = getattr(SelectionWizard, accessor)  # real unbound accessor
        assert fn(w) is getattr(w, attr), accessor


def test_accessors_are_distinct():
    w = _stub_with_pages()
    got = [getattr(SelectionWizard, acc)(w) for acc, _ in _ACCESSORS]
    assert len(set(map(id, got))) == len(_ACCESSORS)  # no accessor aliases another


def test_no_literal_page_index_calls_in_wizard_source():
    """Regression guard: cross-page lookups must not use literal .page(<int>)."""
    src = Path(_sw.__file__).read_text(encoding="utf-8")
    offenders = re.findall(r"\.page\(\d+\)", src)
    assert offenders == [], f"literal page-index calls found: {offenders}"

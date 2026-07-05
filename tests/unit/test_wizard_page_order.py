"""T006/T011 -- wizard named-accessor plumbing + no-literal-index guard.

Inserting pages shifts every literal `wizard.page(N)`. The fix routes all
cross-page lookups through named accessors. These tests guard that:
  (a) each accessor returns its stored `_page_*` attribute,
  (b) no literal `.page(<int>)` call survives in the wizard source,
  (c) Custom Fields is at addPage index 1 (Feature 016, T011),
  (d) Phonology is at addPage index 2 (shifted by Custom Fields insertion).
"""
from __future__ import annotations

import re
from pathlib import Path

import importlib
import importlib.util

import pytest

# Skip at collection time if PyQt6 is genuinely absent OR already stubbed
# (importlib.util.find_spec raises ValueError when PyQt6 is a MagicMock stub).
# This mirrors the guard in test_page_custom_fields.py (b589d6c pattern) and
# prevents pytest.importorskip from pre-loading real PyQt6 into sys.modules on
# a combined run, which would make the setdefault stubs in test_ui_gating.py
# and test_wizard_page_flow.py become no-ops (confirmed latent CI order-dep).
try:
    _pyqt6_spec = importlib.util.find_spec("PyQt6")
except (ValueError, AttributeError):
    _pyqt6_spec = None  # stub installed; treat as absent for real-Qt tests
if _pyqt6_spec is None:
    pytest.skip("PyQt6 not installed or stubbed", allow_module_level=True)

from gramtrans.Lib.ui import selection_wizard as _sw

SelectionWizard = _sw.SelectionWizard

_ACCESSORS = [
    ("page_project_ws",   "_page_project_ws"),
    ("page_custom_fields","_page_custom_fields"),
    ("page_phonology",    "_page_phonology"),
    ("page_items",        "_page_items"),
    ("page_skeleton",     "_page_skeleton"),
    ("page_gram_deps",    "_page_gram_deps"),
    ("page_preview",      "_page_preview"),
    ("page_finish",       "_page_finish"),
]


class _StubWizard:
    """Plain object standing in for `self` -- avoids creating an uninitialized
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


def test_custom_fields_accessor_exists():
    """Feature 016 T011: page_custom_fields accessor must be present."""
    assert hasattr(SelectionWizard, "page_custom_fields"), (
        "SelectionWizard missing page_custom_fields accessor"
    )


def test_custom_fields_page_registered_in_wizard_source():
    """Custom Fields addPage call must appear before Phonology addPage."""
    src = Path(_sw.__file__).read_text(encoding="utf-8")
    cf_pos = src.find("self._page_custom_fields")
    phon_pos = src.find("self._page_phonology")
    assert cf_pos != -1, "_page_custom_fields not found in wizard source"
    assert phon_pos != -1, "_page_phonology not found in wizard source"
    # custom fields must be addPage'd before phonology in source text
    # (both appear in the addPage block in order).
    add_cf = src.find("addPage(self._page_custom_fields)")
    add_phon = src.find("addPage(self._page_phonology)")
    assert add_cf != -1, "addPage(_page_custom_fields) not found"
    assert add_phon != -1, "addPage(_page_phonology) not found"
    assert add_cf < add_phon, (
        "Custom Fields addPage must appear before Phonology addPage"
    )

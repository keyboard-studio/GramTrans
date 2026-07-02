"""Unit tests for Phase 3c leaf-dispatch wiring.

T027: AFFIXES appears in _LEAF_DISPATCH_CATEGORIES in both preview.py and
transfer.py, before ADHOC_COMPOUND_RULES, in the correct Phase 3c order
(AFFIXES → ADHOC_COMPOUND_RULES → SLOTS → AFFIX_TEMPLATES → STEMS).
"""
from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

from gramtrans.Lib.models import GrammarCategory


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PREVIEW_PY = REPO_ROOT / "src" / "gramtrans" / "Lib" / "preview.py"
TRANSFER_PY = REPO_ROOT / "src" / "gramtrans" / "Lib" / "transfer.py"

_PHASE3C_ORDER = [
    GrammarCategory.AFFIXES,
    GrammarCategory.ADHOC_COMPOUND_RULES,
    GrammarCategory.SLOTS,
    GrammarCategory.AFFIX_TEMPLATES,
    GrammarCategory.STEMS,
]


def _extract_leaf_dispatch_categories(filepath: Path) -> list:
    """Parse the file and extract the value names from _LEAF_DISPATCH_CATEGORIES tuple.

    Returns a flat list of GrammarCategory member names (strings) as they appear
    in the assignment.  Handles multiple assignments by returning the last one
    (transfer.py redefines the tuple inside execute()).
    """
    src = filepath.read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "_LEAF_DISPATCH_CATEGORIES":
                # Collect attribute names from the tuple: GrammarCategory.XXX
                for elt in ast.walk(node.value):
                    if isinstance(elt, ast.Attribute) and isinstance(elt.value, ast.Name):
                        if elt.value.id == "GrammarCategory":
                            names.append(elt.attr)
    return names


# ============================================================================
# T027 — AFFIXES in dispatch tuple (both preview.py and transfer.py)
# ============================================================================

@pytest.mark.parametrize("filepath", [PREVIEW_PY, TRANSFER_PY])
def test_affixes_in_dispatch_tuple(filepath: Path) -> None:
    names = _extract_leaf_dispatch_categories(filepath)
    assert "AFFIXES" in names, (
        f"AFFIXES not found in _LEAF_DISPATCH_CATEGORIES in {filepath.name}"
    )


@pytest.mark.parametrize("filepath", [PREVIEW_PY, TRANSFER_PY])
def test_affixes_before_adhoc_compound_rules(filepath: Path) -> None:
    names = _extract_leaf_dispatch_categories(filepath)
    assert "AFFIXES" in names
    assert "ADHOC_COMPOUND_RULES" in names
    assert names.index("AFFIXES") < names.index("ADHOC_COMPOUND_RULES"), (
        f"AFFIXES must precede ADHOC_COMPOUND_RULES in {filepath.name}"
    )


@pytest.mark.parametrize("filepath", [PREVIEW_PY, TRANSFER_PY])
def test_phase3c_order_in_dispatch_tuple(filepath: Path) -> None:
    """Full Phase 3c order: AFFIXES → ADHOC_COMPOUND_RULES → SLOTS → AFFIX_TEMPLATES → STEMS."""
    names = _extract_leaf_dispatch_categories(filepath)
    phase3c_positions = []
    for cat in _PHASE3C_ORDER:
        assert cat.value in names or cat.name in names, (
            f"{cat.name} not found in _LEAF_DISPATCH_CATEGORIES in {filepath.name}"
        )
        # Names list contains attribute names like "AFFIXES", "SLOTS" etc.
        pos = names.index(cat.name) if cat.name in names else names.index(cat.value)
        phase3c_positions.append(pos)
    assert phase3c_positions == sorted(phase3c_positions), (
        f"Phase 3c categories not in correct order in {filepath.name}: "
        f"{[_PHASE3C_ORDER[i].name for i in range(len(_PHASE3C_ORDER))]}"
    )


@pytest.mark.parametrize("filepath", [PREVIEW_PY, TRANSFER_PY])
def test_all_five_phase3c_categories_present(filepath: Path) -> None:
    names = _extract_leaf_dispatch_categories(filepath)
    for cat in _PHASE3C_ORDER:
        assert cat.name in names, (
            f"{cat.name} missing from _LEAF_DISPATCH_CATEGORIES in {filepath.name}"
        )

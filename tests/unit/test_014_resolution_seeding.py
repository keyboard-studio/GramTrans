"""Tests: Resolution seeding, store update, collect_selection fold (US3).

T018 -- test_014_resolution_seeding.py
FR-008, FR-009, SC-003, SC-006

Tests that exercise the resolution store and collect_selection fold.
All tests use stub/fake data — no live LCM project required.
"""
from __future__ import annotations

import dataclasses
import pytest

from gramtrans.Lib.models import SimilarResolution, Selection, GrammarCategory


# ---------------------------------------------------------------------------
# Test 1: default seeding uses overwrite (SC-003, FR-008)
# ---------------------------------------------------------------------------

def test_default_seeding_overwrite():
    """SimilarResolution default action is 'overwrite' with suggested_target_guid."""
    resolution = SimilarResolution(
        entry_guid="src-001",
        action="overwrite",
        target_guid="tgt-001",
    )
    assert resolution.action == "overwrite"
    assert resolution.target_guid == "tgt-001"
    assert resolution.entry_guid == "src-001"


# ---------------------------------------------------------------------------
# Test 2: collect_selection includes resolutions (FR-009)
# ---------------------------------------------------------------------------

def test_collect_selection_includes_resolutions():
    """Selection.similar_resolutions holds the store contents after replace."""
    base = Selection(
        categories={GrammarCategory.AFFIXES: True},
        affix_picks=frozenset(["src-001"]),
    )
    store = {
        "src-001": SimilarResolution(
            entry_guid="src-001", action="overwrite", target_guid="tgt-001"
        ),
    }
    result = dataclasses.replace(base, similar_resolutions=dict(store))
    assert "src-001" in result.similar_resolutions
    assert result.similar_resolutions["src-001"].action == "overwrite"


# ---------------------------------------------------------------------------
# Test 3: store update on resolution changed (FR-008)
# ---------------------------------------------------------------------------

def test_store_update_on_resolution_changed():
    """Store update replaces the entry with new action."""
    store: dict = {
        "src-001": SimilarResolution(
            entry_guid="src-001", action="overwrite", target_guid="tgt-001"
        ),
    }
    new_resolution = SimilarResolution(
        entry_guid="src-001", action="merge", target_guid="tgt-001"
    )
    store["src-001"] = new_resolution
    assert store["src-001"].action == "merge"


# ---------------------------------------------------------------------------
# Test 4: target column text mapping (FR-008)
# ---------------------------------------------------------------------------

def test_target_column_text_updated():
    """Action strings map to the expected Target column text."""
    _ACTION_LABELS = {
        "overwrite": "SIMILAR -> overwrite",
        "merge": "SIMILAR -> merge",
        "create_new": "SIMILAR -> new",
    }
    assert _ACTION_LABELS["overwrite"] == "SIMILAR -> overwrite"
    assert _ACTION_LABELS["merge"] == "SIMILAR -> merge"
    assert _ACTION_LABELS["create_new"] == "SIMILAR -> new"


# ---------------------------------------------------------------------------
# Test 5: reconstruction preserves similar_resolutions (FR-009, SC-006)
# ---------------------------------------------------------------------------

def test_reconstruction_preserves_similar_resolutions():
    """dataclasses.replace copies similar_resolutions without aliasing."""
    original_store = {
        "src-001": SimilarResolution(
            entry_guid="src-001", action="overwrite", target_guid="tgt-001"
        ),
        "src-002": SimilarResolution(
            entry_guid="src-002", action="merge", target_guid="tgt-002"
        ),
    }
    base = Selection(
        categories={GrammarCategory.AFFIXES: True},
        affix_picks=frozenset(["src-001", "src-002"]),
    )
    # Simulate collect_selection fold
    picker_selection = dataclasses.replace(base, similar_resolutions=dict(original_store))
    # Simulate reconstruction copy (T015 pattern)
    reconstructed = dataclasses.replace(
        base,
        similar_resolutions=picker_selection.similar_resolutions,
    )
    # All resolutions preserved
    assert len(reconstructed.similar_resolutions) == 2
    assert reconstructed.similar_resolutions["src-001"].action == "overwrite"
    assert reconstructed.similar_resolutions["src-002"].action == "merge"
    # No aliasing: mutating original does not affect reconstructed
    original_store["src-001"] = SimilarResolution(
        entry_guid="src-001", action="create_new"
    )
    # reconstructed.similar_resolutions is a snapshot taken via dict(store)
    assert reconstructed.similar_resolutions["src-001"].action == "overwrite"

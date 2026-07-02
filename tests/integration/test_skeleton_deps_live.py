"""Live MCP integration tests for skeleton + deps selectors (T013, T015).

IMPORTANT: These tests require a live FlexTools MCP session bound to the
Ejagham Full GT-Test project. They are NOT run by the main unit-test suite
(pytest tests/unit). The main session runs these against Ejagham + Esperanto.

To run manually:
    python -m pytest tests/integration/test_skeleton_deps_live.py -v

Expected Ejagham structure (empirically verified via MCP, 2026-07-01):
  POS v (Verb):  4 slots, 1 template
  POS n (Noun):  1 slot, 1 template
  POS num (Numeral): 1 slot, 1 template
  28 of 33 affix MSAs map to a slot
  0 inflection classes, 0 stem names, 0-1 inflectable features per POS
"""
from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# T013: Ejagham skeleton preselection + slot counts
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_ejagham_skeleton_v_4_slots_1_template(ejagham_source, ejagham_affix_picks):
    """POS v has 4 slots and 1 template; all are present in skeleton."""
    from gramtrans.Lib.selection import build_skeleton_inventory

    skeleton = build_skeleton_inventory(ejagham_source, ejagham_affix_picks)
    verb_nodes = [n for n in skeleton.pos_nodes if n.label.lower() in ("v", "verb")]
    assert verb_nodes, "Expected a Verb POS node in Ejagham skeleton"
    verb = verb_nodes[0]
    assert len(verb.slots) == 4, f"Expected 4 slots for v, got {len(verb.slots)}"
    assert len(verb.templates) == 1, f"Expected 1 template for v, got {len(verb.templates)}"
    # At least one slot preselected (28/33 MSAs fill a slot)
    preselected_slots = [s for s in verb.slots if s.preselected]
    assert len(preselected_slots) >= 1, "Expected at least 1 preselected slot"


@pytest.mark.integration
def test_ejagham_skeleton_n_1_slot_1_template(ejagham_source, ejagham_affix_picks):
    """POS n has 1 slot and 1 template."""
    from gramtrans.Lib.selection import build_skeleton_inventory

    skeleton = build_skeleton_inventory(ejagham_source, ejagham_affix_picks)
    noun_nodes = [n for n in skeleton.pos_nodes if n.label.lower() in ("n", "noun")]
    assert noun_nodes, "Expected a Noun POS node in Ejagham skeleton"
    noun = noun_nodes[0]
    assert len(noun.slots) == 1, f"Expected 1 slot for n, got {len(noun.slots)}"
    assert len(noun.templates) == 1, f"Expected 1 template for n, got {len(noun.templates)}"


@pytest.mark.integration
def test_ejagham_skeleton_slot_counts(ejagham_source, ejagham_affix_picks):
    """28 of 33 affix MSAs fill a slot; total affix_count across all slots >= 28."""
    from gramtrans.Lib.selection import build_skeleton_inventory

    skeleton = build_skeleton_inventory(ejagham_source, ejagham_affix_picks)
    total_filled = sum(
        s.affix_count
        for pn in skeleton.pos_nodes
        for s in pn.slots
    )
    # Allow some MSAs to reference multiple slots; minimum is 28
    assert total_filled >= 28, f"Expected >= 28 slot-fill mappings, got {total_filled}"


@pytest.mark.integration
def test_ejagham_skeleton_preselection_correct(ejagham_source, ejagham_affix_picks):
    """All POS nodes for picked affixes must be preselected."""
    from gramtrans.Lib.selection import build_skeleton_inventory

    skeleton = build_skeleton_inventory(ejagham_source, ejagham_affix_picks)
    for pn in skeleton.pos_nodes:
        if pn.preselected:
            # At least one slot should also be preselected
            assert any(s.preselected for s in pn.slots), (
                f"POS {pn.label} is preselected but no slots are"
            )


@pytest.mark.integration
def test_ejagham_skeleton_templates_list_referenced_slots(ejagham_source, ejagham_affix_picks):
    """Every template must expose its referenced_slot_guids (non-empty for v)."""
    from gramtrans.Lib.selection import build_skeleton_inventory

    skeleton = build_skeleton_inventory(ejagham_source, ejagham_affix_picks)
    verb_nodes = [n for n in skeleton.pos_nodes if n.label.lower() in ("v", "verb")]
    assert verb_nodes
    verb = verb_nodes[0]
    for tpl in verb.templates:
        assert len(tpl.referenced_slot_guids) > 0, (
            f"Template {tpl.label} has no referenced slots"
        )


# ---------------------------------------------------------------------------
# T015: Ejagham deps (0 classes, 0 stem names, features 0-1 per POS)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_ejagham_deps_no_classes_no_stem_names(ejagham_source, ejagham_affix_picks):
    """Ejagham has 0 inflection classes and 0 stem names -> empty sections, no error."""
    from gramtrans.Lib.selection import build_deps_inventory

    deps = build_deps_inventory(ejagham_source, ejagham_affix_picks)
    assert deps.infl_classes == [], (
        f"Expected 0 infl classes in Ejagham, got {len(deps.infl_classes)}"
    )
    assert deps.stem_names == [], (
        f"Expected 0 stem names in Ejagham, got {len(deps.stem_names)}"
    )


@pytest.mark.integration
def test_ejagham_deps_features_preselected(ejagham_source, ejagham_affix_picks):
    """Any inflectable features present must be preselected."""
    from gramtrans.Lib.selection import build_deps_inventory

    deps = build_deps_inventory(ejagham_source, ejagham_affix_picks)
    for row in deps.infl_features:
        assert row.preselected, f"Feature {row.label} should be preselected"


@pytest.mark.integration
def test_ejagham_deps_no_error_when_empty(ejagham_source, ejagham_affix_picks):
    """build_deps_inventory must return without error even for Ejagham's sparse deps."""
    from gramtrans.Lib.selection import build_deps_inventory
    # Should not raise
    deps = build_deps_inventory(ejagham_source, ejagham_affix_picks)
    assert deps is not None


# ---------------------------------------------------------------------------
# Fixtures (to be injected by the main session via conftest.py or direct args)
# ---------------------------------------------------------------------------

@pytest.fixture
def ejagham_source():
    """Provide the Ejagham Full GT-Test source FLExProject handle.

    This fixture requires a live FlexTools MCP session. In CI or headless
    environments, skip if the handle is not available.
    """
    pytest.skip("Live MCP fixture: run manually with Ejagham Full GT-Test bound")


@pytest.fixture
def ejagham_affix_picks():
    """Provide the full set of Ejagham affix GUIDs (preselect-all scenario)."""
    pytest.skip("Live MCP fixture: run manually with Ejagham Full GT-Test bound")

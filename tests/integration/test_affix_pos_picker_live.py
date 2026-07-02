"""Live MCP integration tests for the POS-grouped affix inventory builder.

T013 (US1): Ejagham Full GT-Test count anchors.
T019 (US3): Esperanto derivational/unclassified/multi-POS anchors.
T021 (US4): Esperanto and Ejagham junk drawer counts.

These tests require the FlexTools MCP server with live FLEx projects open:
  - "Ejagham Full GT-Test"
  - "Esperanto"

Run with:
    python -m pytest tests/integration/test_affix_pos_picker_live.py -m integration -v

Skip with:
    python -m pytest -m "not integration"

All count anchors come from specs/008-affix-pos-picker/contracts/pos-grouped-inventory.md
(validated live via MCP on 2026-07-01).

STATUS: Written, not executed (MCP / live FLEx projects not available in the
automated test environment). Verification runs must be performed in a session
with the FlexTools MCP active and the named projects open.
"""
from __future__ import annotations

import pytest

from gramtrans.Lib.selection import (
    PosGroupedAffixInventory,
    build_pos_grouped_inventory,
)


# ============================================================================
# Helpers
# ============================================================================

def _get_source(project_name: str):
    """Open the named FLEx project via the FlexTools MCP and return a source handle.

    In live runs the MCP provides `open_project(project_name)` which returns
    a handle with `.Cache.LangProject.*` attributes.  Adjust this import /
    call to match the actual MCP session API available in this environment.
    """
    try:
        import flexlibs  # type: ignore
        project = flexlibs.FLExProject()
        project.OpenProject(project_name, writeEnabled=False)
        return project
    except Exception as e:
        pytest.skip(f"Cannot open project '{project_name}': {e}")


def _count_affix_rows_by_msa_kind(inv: PosGroupedAffixInventory, kind: str) -> int:
    """Count distinct entry GUIDs whose primary kind matches `kind`."""
    guids = set()

    def _walk_node(node) -> None:
        for row in node.inflectional:
            if row.msa_kind == kind:
                guids.add(row.entry_guid)
        for row in node.deriv_attaches:
            if row.msa_kind == kind:
                guids.add(row.entry_guid)
        for row in node.deriv_produces:
            if row.msa_kind == kind:
                guids.add(row.entry_guid)
        for child in node.children:
            _walk_node(child)

    for root in inv.roots:
        _walk_node(root)
    return len(guids)


def _attaches_count_for_label(inv: PosGroupedAffixInventory, label: str) -> int:
    """Count distinct affix GUIDs in attaches-to lists for the named POS node."""
    guids: set = set()

    def _walk(node) -> None:
        if node.label == label:
            for row in node.inflectional:
                guids.add(row.entry_guid)
            for row in node.deriv_attaches:
                guids.add(row.entry_guid)
        for child in node.children:
            _walk(child)

    for root in inv.roots:
        _walk(root)
    return len(guids)


def _produces_count_for_label(inv: PosGroupedAffixInventory, label: str) -> int:
    """Count distinct affix GUIDs in produces lists for the named POS node."""
    guids: set = set()

    def _walk(node) -> None:
        if node.label == label:
            for row in node.deriv_produces:
                guids.add(row.entry_guid)
        for child in node.children:
            _walk(child)

    for root in inv.roots:
        _walk(root)
    return len(guids)


def _count_multi_pos(inv: PosGroupedAffixInventory) -> int:
    """Count affix GUIDs that appear in more than one attaches-to POS group."""
    from collections import Counter
    ctr: Counter = Counter()

    def _walk(node) -> None:
        seen_here: set = set()
        for row in node.inflectional:
            seen_here.add(row.entry_guid)
        for row in node.deriv_attaches:
            seen_here.add(row.entry_guid)
        for guid in seen_here:
            ctr[guid] += 1
        for child in node.children:
            _walk(child)

    for root in inv.roots:
        _walk(root)
    return sum(1 for g, c in ctr.items() if c > 1)


# ============================================================================
# T013 - Ejagham Full GT-Test (US1: inflectional baseline)
# ============================================================================

@pytest.mark.integration
class TestEjaghamInventory:
    """Contract anchors for Ejagham Full GT-Test (inflectional-only baseline).

    From contracts/pos-grouped-inventory.md:
      affixes: 33 | infl: 33 / deriv: 0 / uncl: 0
      attaches-to: v:14, n:11, num:6, pro:1
      multi-POS: 0 | junk no_pos: 1
    """

    @pytest.fixture(scope="class")
    def ejagham_inv(self):
        source = _get_source("Ejagham Full GT-Test")
        return build_pos_grouped_inventory(source)

    def test_total_affix_count(self, ejagham_inv):
        total = len(ejagham_inv.all_affix_guids())
        assert total == 33, f"Expected 33 affixes, got {total}"

    def test_all_inflectional(self, ejagham_inv):
        infl_count = _count_affix_rows_by_msa_kind(ejagham_inv, "infl")
        assert infl_count == 33, f"Expected 33 inflectional, got {infl_count}"

    def test_no_derivational(self, ejagham_inv):
        deriv = _count_affix_rows_by_msa_kind(ejagham_inv, "deriv")
        assert deriv == 0, f"Expected 0 derivational, got {deriv}"

    def test_no_unclassified(self, ejagham_inv):
        uncl = _count_affix_rows_by_msa_kind(ejagham_inv, "uncl")
        assert uncl == 0, f"Expected 0 unclassified, got {uncl}"

    def test_attaches_verb_14(self, ejagham_inv):
        c = _attaches_count_for_label(ejagham_inv, "v")
        assert c == 14, f"Expected 14 verb-attaching, got {c}"

    def test_attaches_noun_11(self, ejagham_inv):
        c = _attaches_count_for_label(ejagham_inv, "n")
        assert c == 11, f"Expected 11 noun-attaching, got {c}"

    def test_attaches_num_6(self, ejagham_inv):
        c = _attaches_count_for_label(ejagham_inv, "num")
        assert c == 6, f"Expected 6 num-attaching, got {c}"

    def test_attaches_pro_1(self, ejagham_inv):
        c = _attaches_count_for_label(ejagham_inv, "pro")
        assert c == 1, f"Expected 1 pro-attaching, got {c}"

    def test_zero_multi_pos(self, ejagham_inv):
        m = _count_multi_pos(ejagham_inv)
        assert m == 0, f"Expected 0 multi-POS, got {m}"

    # T021 - Ejagham junk
    def test_junk_no_pos_1(self, ejagham_inv):
        c = len(ejagham_inv.junk.no_pos)
        assert c == 1, f"Expected 1 no-POS junk entry, got {c}"

    def test_junk_no_analysis_0(self, ejagham_inv):
        c = len(ejagham_inv.junk.no_analysis)
        assert c == 0, f"Expected 0 no-analysis junk, got {c}"


# ============================================================================
# T019 - Esperanto (US3: derivational + unclassified + multi-POS)
# ============================================================================

@pytest.mark.integration
class TestEsperantoInventory:
    """Contract anchors for Esperanto.

    From contracts/pos-grouped-inventory.md:
      affixes: 68 | infl: 41 / deriv: 31 / uncl: 12
      attaches-to: Root:43, v:12, VRoot:9, ARoot:3, n:3, NRoot:2, adj:2
      produces: n:14, v:10, adj:5, adv:1
      multi-POS: 13 | junk no_pos: 7 / no_analysis: 0
    """

    @pytest.fixture(scope="class")
    def esp_inv(self):
        source = _get_source("Esperanto")
        return build_pos_grouped_inventory(source)

    def test_total_affix_count(self, esp_inv):
        total = len(esp_inv.all_affix_guids())
        assert total == 68, f"Expected 68 affixes, got {total}"

    def test_inflectional_41(self, esp_inv):
        c = _count_affix_rows_by_msa_kind(esp_inv, "infl")
        assert c == 41, f"Expected 41 inflectional, got {c}"

    def test_derivational_31(self, esp_inv):
        c = _count_affix_rows_by_msa_kind(esp_inv, "deriv")
        assert c == 31, f"Expected 31 derivational, got {c}"

    def test_unclassified_12(self, esp_inv):
        c = _count_affix_rows_by_msa_kind(esp_inv, "uncl")
        assert c == 12, f"Expected 12 unclassified, got {c}"

    # Attaches-to counts
    def test_attaches_root_43(self, esp_inv):
        c = _attaches_count_for_label(esp_inv, "Root")
        assert c == 43, f"Expected Root:43, got {c}"

    def test_attaches_v_12(self, esp_inv):
        c = _attaches_count_for_label(esp_inv, "v")
        assert c == 12, f"Expected v:12, got {c}"

    def test_attaches_vroot_9(self, esp_inv):
        c = _attaches_count_for_label(esp_inv, "VRoot")
        assert c == 9, f"Expected VRoot:9, got {c}"

    def test_attaches_aroot_3(self, esp_inv):
        c = _attaches_count_for_label(esp_inv, "ARoot")
        assert c == 3, f"Expected ARoot:3, got {c}"

    def test_attaches_n_3(self, esp_inv):
        c = _attaches_count_for_label(esp_inv, "n")
        assert c == 3, f"Expected n:3, got {c}"

    def test_attaches_nroot_2(self, esp_inv):
        c = _attaches_count_for_label(esp_inv, "NRoot")
        assert c == 2, f"Expected NRoot:2, got {c}"

    def test_attaches_adj_2(self, esp_inv):
        c = _attaches_count_for_label(esp_inv, "adj")
        assert c == 2, f"Expected adj:2, got {c}"

    # Produces counts
    def test_produces_n_14(self, esp_inv):
        c = _produces_count_for_label(esp_inv, "n")
        assert c == 14, f"Expected n produces:14, got {c}"

    def test_produces_v_10(self, esp_inv):
        c = _produces_count_for_label(esp_inv, "v")
        assert c == 10, f"Expected v produces:10, got {c}"

    def test_produces_adj_5(self, esp_inv):
        c = _produces_count_for_label(esp_inv, "adj")
        assert c == 5, f"Expected adj produces:5, got {c}"

    def test_produces_adv_1(self, esp_inv):
        c = _produces_count_for_label(esp_inv, "adv")
        assert c == 1, f"Expected adv produces:1, got {c}"

    def test_multi_pos_13(self, esp_inv):
        m = _count_multi_pos(esp_inv)
        assert m == 13, f"Expected 13 multi-POS, got {m}"

    # T021 - Esperanto junk drawer
    def test_junk_no_pos_7(self, esp_inv):
        c = len(esp_inv.junk.no_pos)
        assert c == 7, f"Expected 7 no-POS junk, got {c}"

    def test_junk_no_analysis_0(self, esp_inv):
        c = len(esp_inv.junk.no_analysis)
        assert c == 0, f"Expected 0 no-analysis junk, got {c}"

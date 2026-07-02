"""Prune-empty-POS + unnamed-label tests (008 follow-up).

Covers the two UI defects reported after the first live render:
1. POS nodes with no affixes anywhere in their subtree must not appear.
2. A blank-named POS ('***'/'***') must not surface its raw GUID as a label;
   if it survives pruning (because it holds affixes) it reads "(unnamed POS)".
"""
from __future__ import annotations

from gramtrans.Lib.selection import build_pos_grouped_inventory  # type: ignore
from _fakes_affix import (  # type: ignore
    make_source,
    make_infl_entry,
    make_deriv_entry,
    FakePos,
    make_pos,
)


def _labels(roots):
    """Flatten all node labels in the hierarchy."""
    out = []

    def walk(n):
        out.append(n.label)
        for c in n.children:
            walk(c)

    for r in roots:
        walk(r)
    return out


def _find(roots, pos_guid):
    def walk(n):
        if n.pos_guid == pos_guid:
            return n
        for c in n.children:
            hit = walk(c)
            if hit is not None:
                return hit
        return None

    for r in roots:
        hit = walk(r)
        if hit is not None:
            return hit
    return None


def test_prune_removes_pos_with_no_affixes():
    verb = make_pos("v-guid", "v", "Verb")
    prep = make_pos("prep-guid", "prep", "Preposition")  # no affixes attach
    entries = [make_infl_entry("aff1", "-s", ["plural"], verb)]
    inv = build_pos_grouped_inventory(make_source(entries, [verb, prep]))
    labels = _labels(inv.roots)
    assert "v" in labels
    assert "prep" not in labels
    assert _find(inv.roots, "prep-guid") is None


def test_prune_keeps_ancestor_of_populated_subpos():
    sub = make_pos("tv-guid", "tv", "Transitive Verb")
    parent = make_pos("v-guid", "v", "Verb", children=[sub])
    # Affix attaches to the SUB-POS only; parent has no rows of its own.
    entries = [make_infl_entry("aff1", "-s", ["plural"], sub)]
    inv = build_pos_grouped_inventory(make_source(entries, [parent]))
    parent_node = _find(inv.roots, "v-guid")
    assert parent_node is not None, "ancestor path to populated sub-POS must survive"
    assert _find(inv.roots, "tv-guid") is not None


def test_prune_keeps_produces_only_node():
    root_pos = make_pos("root-guid", "Root", "Root")
    noun = make_pos("n-guid", "n", "Noun")  # only PRODUCED, nothing attaches
    entries = [make_deriv_entry("d1", "-er", ["agentive"], root_pos, noun)]
    inv = build_pos_grouped_inventory(make_source(entries, [root_pos, noun]))
    noun_node = _find(inv.roots, "n-guid")
    assert noun_node is not None
    assert len(noun_node.deriv_produces) == 1


def test_prune_removes_blank_unnamed_pos_with_no_affixes():
    verb = make_pos("v-guid", "v", "Verb")
    blank = FakePos("blank-guid", "***", "***")  # user-created empty POS
    entries = [make_infl_entry("aff1", "-s", ["plural"], verb)]
    inv = build_pos_grouped_inventory(make_source(entries, [verb, blank]))
    assert _find(inv.roots, "blank-guid") is None
    # And its raw guid never appears as a label.
    assert all("blank-guid" not in lbl for lbl in _labels(inv.roots))


def test_blank_named_pos_with_affixes_reads_unnamed():
    blank = FakePos("blank-guid", "***", "***")
    entries = [make_infl_entry("aff1", "-x", ["thing"], blank)]
    inv = build_pos_grouped_inventory(make_source(entries, [blank]))
    node = _find(inv.roots, "blank-guid")
    assert node is not None, "a blank-named POS that holds affixes must survive"
    assert node.label == "(unnamed POS)"

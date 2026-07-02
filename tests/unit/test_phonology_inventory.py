"""T007/T008/T016/T023 — build_phonology_inventory + collapse_phonology (spec 010)."""
from __future__ import annotations

from _fakes_phonology import (
    FakeEnv, FakeFeature, FakeNC, FakePhoneme, FakePhonSource, FakeRule,
    FakeStratum, make_rhs,
)

from gramtrans.Lib.models import GrammarCategory as GC
from gramtrans.Lib.selection import (
    build_phonology_inventory, collapse_phonology,
)


def _rich_source():
    f1 = FakeFeature("f1", "voiced")
    p1 = FakePhoneme("ph1", "p", feature_refs=[f1])
    p2 = FakePhoneme("ph2", "t")
    nc1 = FakeNC("nc1", "C", segments=[p1, p2])
    env1 = FakeEnv("env1", "_#")
    strat = FakeStratum("s1", "stratum")
    rule1 = FakeRule("r1", "devoicing", struc_refs=[nc1],
                     rhs=[make_rhs(left=p1)], stratum=strat)
    return FakePhonSource(
        features=[f1], phonemes=[p1, p2], ncs=[nc1], envs=[env1],
        rules=[rule1], strata=[strat],
    )


def test_five_groups_in_order_with_counts():
    inv = build_phonology_inventory(_rich_source())
    cats = [g.category for g in inv.groups]
    assert cats == [
        GC.PHONOLOGICAL_FEATURES, GC.PHONEMES, GC.NATURAL_CLASSES,
        GC.PH_ENVIRONMENT, GC.PHONOLOGICAL_RULES,
    ]
    counts = {g.category: g.count for g in inv.groups}
    assert counts[GC.PHONEMES] == 2
    assert counts[GC.NATURAL_CLASSES] == 1
    assert counts[GC.PHONOLOGICAL_RULES] == 1
    # No strata group is ever surfaced (FR-009 / FR-002).
    assert GC.STRATA not in cats


def test_all_rows_preselected():
    inv = build_phonology_inventory(_rich_source())
    assert all(r.preselected for g in inv.groups for r in g.rows)


def test_empty_category_renders_not_errors():
    src = FakePhonSource(phonemes=[FakePhoneme("ph1", "p")])  # only phonemes
    inv = build_phonology_inventory(src)
    rules = inv.group_for(GC.PHONOLOGICAL_RULES)
    assert rules is not None and rules.count == 0  # empty, no error
    assert inv.has_rules is False


def test_reference_maps_populated():
    inv = build_phonology_inventory(_rich_source())
    assert inv.nc_referenced_phoneme_guids["nc1"] == frozenset({"ph1", "ph2"})
    assert inv.phoneme_referenced_feature_guids["ph1"] == frozenset({"f1"})
    assert inv.rule_referenced_nc_guids["r1"] == frozenset({"nc1"})
    assert inv.rule_referenced_phoneme_guids["r1"] == frozenset({"ph1"})


def test_target_status_new_and_in_target():
    src = _rich_source()
    # target has the same phonemes -> in_target; fresh categories -> new
    tgt = FakePhonSource(phonemes=[FakePhoneme("ph1", "p"), FakePhoneme("ph2", "t")])
    inv = build_phonology_inventory(src, target=tgt)
    ph = {r.guid: r.status for r in inv.group_for(GC.PHONEMES).rows}
    assert ph == {"ph1": "in_target", "ph2": "in_target"}
    nc = inv.group_for(GC.NATURAL_CLASSES).rows[0]
    assert nc.status == "new"


def test_target_none_status_blank():
    inv = build_phonology_inventory(_rich_source(), target=None)
    assert all(r.status is None for g in inv.groups for r in g.rows)


# ---- collapse_phonology --------------------------------------------------

def _all_checked(inv):
    return {g.category: {r.guid for r in g.rows} for g in inv.groups}


def test_collapse_all_checked_no_leaf_keys():
    inv = build_phonology_inventory(_rich_source())
    out = collapse_phonology(inv, _all_checked(inv))
    # every populated category on
    assert out["categories"][GC.PHONEMES] is True
    assert out["categories"][GC.PHONOLOGICAL_RULES] is True
    # all-checked => transfer-all => NO leaf_item_picks keys
    assert out["leaf_item_picks"] == {}
    # rule kept => strata on (FR-009)
    assert out["categories"].get(GC.STRATA) is True


def test_collapse_trim_records_subset():
    inv = build_phonology_inventory(_rich_source())
    checked = _all_checked(inv)
    checked[GC.PHONEMES] = {"ph1"}  # trim one of two
    out = collapse_phonology(inv, checked)
    assert out["leaf_item_picks"][GC.PHONEMES] == frozenset({"ph1"})


def test_collapse_whole_block_off():
    inv = build_phonology_inventory(_rich_source())
    out = collapse_phonology(inv, {c: set() for c in
                                   (GC.PHONEMES, GC.NATURAL_CLASSES,
                                    GC.PHONOLOGICAL_RULES)})
    assert out["categories"] == {}
    assert out["leaf_item_picks"] == {}


# ---- T016 (US1): preselect-all => 5 cats on, no picks; no conflict control --

def test_us1_preselect_all_five_categories_on_no_picks():
    """SC-001/SC-002: the page opens ALL preselected; collapsing that state
    turns every one of the five populated categories on with no trim keys."""
    inv = build_phonology_inventory(_rich_source())
    out = collapse_phonology(inv, _all_checked(inv))
    for cat in (GC.PHONOLOGICAL_FEATURES, GC.PHONEMES, GC.NATURAL_CLASSES,
                GC.PH_ENVIRONMENT, GC.PHONOLOGICAL_RULES):
        assert out["categories"][cat] is True, cat
    assert out["leaf_item_picks"] == {}  # transfer-all, no GUID lists


def test_us1_no_conflict_mode_control_on_phonology_page():
    """SC-008 / FR-012 (analyze finding G1): _PagePhonology must render NO
    ADD_NEW/MERGE/OVERWRITE conflict-mode control. Verified by source scan
    (instantiating the QWizardPage pollutes sip state across the suite)."""
    import ast
    from pathlib import Path

    from gramtrans.Lib.ui import selection_wizard as _sw

    src = Path(_sw.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    page_cls = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "_PagePhonology"
    )
    # Collect referenced identifiers (Name ids + Attribute attrs) — ignores
    # docstrings/comments, which legitimately spell out FR-012 by name.
    identifiers = set()
    for node in ast.walk(page_cls):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
    for banned in ("ConflictMode", "_CONFLICT_LABELS", "_allowed_modes",
                   "OVERWRITE", "ADD_NEW", "MERGE"):
        assert banned not in identifiers, (
            f"phonology page must not reference {banned}"
        )

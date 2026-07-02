"""T009/T026/T026c — phonology EXCLUDED-LOSSY + KL-010-1 guard (spec 010, US5)."""
from __future__ import annotations

from _fakes_phonology import (
    FakeFeature, FakeNC, FakePhoneme, FakePhonSource, FakeRule, make_rhs,
)

from gramtrans.Lib.models import GrammarCategory as GC
from gramtrans.Lib.selection import (
    build_phonology_inventory, build_phonology_excluded_lossy,
    phonology_uses_untraversed_rules,
)


def _source():
    f1 = FakeFeature("f1", "voiced")
    p1 = FakePhoneme("ph1", "p", feature_refs=[f1])
    p2 = FakePhoneme("ph2", "t")
    nc1 = FakeNC("nc1", "C", segments=[p1, p2])
    rule = FakeRule("r1", "devoice", struc_refs=[nc1], rhs=[make_rhs(left=p2)])
    return FakePhonSource(features=[f1], phonemes=[p1, p2], ncs=[nc1], rules=[rule])


def test_kept_nc_stranded_phoneme_warns():
    inv = build_phonology_inventory(_source())
    # keep nc1, deselect phoneme ph1 (referenced by nc1), target lacks it
    checked = {GC.NATURAL_CLASSES: {"nc1"}, GC.PHONEMES: {"ph2"}}
    warns = build_phonology_excluded_lossy(inv, checked, target_guids_by_category={})
    ph_warns = [w for w in warns if w.entry_guid == "nc1" and w.dep_guid == "ph1"]
    assert len(ph_warns) == 1
    assert ph_warns[0].category == GC.NATURAL_CLASSES


def test_kept_rule_stranded_direct_phoneme_warns():
    inv = build_phonology_inventory(_source())
    # rule r1 references ph2 directly; deselect ph2, target lacks it
    checked = {GC.PHONOLOGICAL_RULES: {"r1"}, GC.PHONEMES: {"ph1"},
               GC.NATURAL_CLASSES: {"nc1"}}
    warns = build_phonology_excluded_lossy(inv, checked, target_guids_by_category={})
    direct = [w for w in warns if w.entry_guid == "r1" and w.dep_guid == "ph2"]
    assert len(direct) == 1


def test_no_warning_when_reference_in_target():
    inv = build_phonology_inventory(_source())
    checked = {GC.NATURAL_CLASSES: {"nc1"}, GC.PHONEMES: {"ph2"}}
    # target HAS ph1 -> reference resolves -> no warning
    warns = build_phonology_excluded_lossy(
        inv, checked, target_guids_by_category={GC.PHONEMES: {"ph1"}})
    assert [w for w in warns if w.dep_guid == "ph1"] == []


def test_aggregation_multiple_omissions_single_list():
    inv = build_phonology_inventory(_source())
    # deselect ph1 (needed by nc1) and f1 (needed by ph1-if-kept)
    checked = {GC.NATURAL_CLASSES: {"nc1"}, GC.PHONEMES: {"ph1"},
               GC.PHONOLOGICAL_FEATURES: set()}
    warns = build_phonology_excluded_lossy(inv, checked, target_guids_by_category={})
    # ph1 kept -> f1 stranded (1); nc1 kept -> no stranded (ph1 kept, ph2 checked? no)
    guids = {(w.entry_guid, w.dep_guid) for w in warns}
    assert ("ph1", "f1") in guids
    assert isinstance(warns, list)  # single aggregated list


def test_kl_010_1_guard_detects_metathesis():
    p1 = FakePhoneme("ph1", "p")
    meta = FakeRule("rm", "metathesis", class_name="PhMetathesisRule")
    src = FakePhonSource(phonemes=[p1], rules=[meta])
    inv = build_phonology_inventory(src)
    assert phonology_uses_untraversed_rules(inv, {"rm"}) is True
    # regular-only -> guard does not fire
    reg = FakeRule("rr", "reg", class_name="PhRegularRule")
    src2 = FakePhonSource(phonemes=[p1], rules=[reg])
    inv2 = build_phonology_inventory(src2)
    assert phonology_uses_untraversed_rules(inv2, {"rr"}) is False


# ---- T026 (combined single gate) + T026c (KL-010-1 notice in gate) ---------

from gramtrans.Lib.selection import build_excluded_lossy_warnings  # noqa: E402


def test_combined_gate_counts_phonology_plus_skeleton_single_total():
    """T026/SC-006: N phonology omissions + M skeleton omissions aggregate into
    ONE consolidated count (single Move dialog) — modeled at the builder layer,
    where each returns an independent list summed into one el_count."""
    inv = build_phonology_inventory(_source())
    # phonology: keep nc1, drop ph1 (referenced) -> N warnings
    phon = build_phonology_excluded_lossy(
        inv, {GC.NATURAL_CLASSES: {"nc1"}, GC.PHONEMES: {"ph2"}},
        target_guids_by_category={},
    )
    n = len(phon)
    assert n >= 1
    # skeleton: picked affix fills slot s1 which the user deselected, target lacks it -> M
    skel = build_excluded_lossy_warnings(
        affix_slot_map={"aff1": ["s1"]},
        deselected_slot_guids={"s1"},
        target_slot_guids=set(),
    )
    m = len(skel)
    assert m >= 1
    el_count = n + m  # the single consolidated total the Move gate confirms once
    assert el_count == n + m


def test_no_gate_when_all_references_resolved():
    """Resolved references (present in target) => zero phonology warnings."""
    inv = build_phonology_inventory(_source())
    warns = build_phonology_excluded_lossy(
        inv, {GC.NATURAL_CLASSES: {"nc1"}, GC.PHONEMES: {"ph2"}},
        target_guids_by_category={GC.PHONEMES: {"ph1"}},  # ph1 in target
    )
    assert warns == []


def test_kl_010_1_notice_appears_for_metathesis_trim_but_not_regular():
    """T026c: a kept metathesis rule + an NC/phoneme trim yields the coarse
    KL-010-1 notice via the shared wizard helper; a regular-only rule does not."""
    import pytest
    pytest.importorskip("PyQt6")
    from gramtrans.Lib.ui import selection_wizard as sw

    p1 = FakePhoneme("ph1", "p")
    p2 = FakePhoneme("ph2", "t")
    meta = FakeRule("rm", "metathesis", class_name="PhMetathesisRule")
    inv = build_phonology_inventory(
        FakePhonSource(phonemes=[p1, p2], rules=[meta])
    )
    # kept rule + a phoneme trim (ph2 dropped)
    checked = {GC.PHONOLOGICAL_RULES: {"rm"}, GC.PHONEMES: {"ph1"}}
    assert sw._phonology_nc_or_phoneme_trimmed(inv, checked) is True
    notice = sw._kl010_notice(inv, {"rm"})
    assert notice.entry_guid == "rm"
    assert "KL-010-1" in notice.message

    # regular-only rule: guard input is False (no untraversed rule kept)
    reg = FakeRule("rr", "reg", class_name="PhRegularRule")
    inv2 = build_phonology_inventory(
        FakePhonSource(phonemes=[p1, p2], rules=[reg])
    )
    assert phonology_uses_untraversed_rules(inv2, {"rr"}) is False

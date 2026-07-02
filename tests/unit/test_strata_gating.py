"""T021 — strata gated on kept phonological rule (spec 010, FR-009/US3)."""
from __future__ import annotations

from _fakes_phonology import (
    FakeNC, FakePhoneme, FakePhonSource, FakeRule, FakeStratum,
)

from gramtrans.Lib.models import GrammarCategory as GC
from gramtrans.Lib.selection import build_phonology_inventory, collapse_phonology


def _source_with_rule():
    p1 = FakePhoneme("ph1", "p")
    nc1 = FakeNC("nc1", "C", segments=[p1])
    strat = FakeStratum("s1", "stratum")
    rule = FakeRule("r1", "rule", struc_refs=[nc1], stratum=strat)
    return FakePhonSource(phonemes=[p1], ncs=[nc1], rules=[rule], strata=[strat])


def test_strata_on_when_rule_kept():
    inv = build_phonology_inventory(_source_with_rule())
    out = collapse_phonology(inv, {
        GC.PHONEMES: {"ph1"}, GC.NATURAL_CLASSES: {"nc1"},
        GC.PHONOLOGICAL_RULES: {"r1"},
    })
    assert out["categories"].get(GC.STRATA) is True


def test_no_strata_when_rules_off_but_phonemes_on():
    inv = build_phonology_inventory(_source_with_rule())
    out = collapse_phonology(inv, {
        GC.PHONEMES: {"ph1"}, GC.NATURAL_CLASSES: {"nc1"},
        GC.PHONOLOGICAL_RULES: set(),  # no rule kept
    })
    assert GC.STRATA not in out["categories"]
    assert out["categories"][GC.PHONEMES] is True


def test_no_strata_when_block_off():
    inv = build_phonology_inventory(_source_with_rule())
    out = collapse_phonology(inv, {})
    assert GC.STRATA not in out["categories"]


def test_no_strata_group_ever_surfaced():
    inv = build_phonology_inventory(_source_with_rule())
    assert all(g.category != GC.STRATA for g in inv.groups)

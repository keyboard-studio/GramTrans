"""T002 — engine leaf_item_picks filter + back-compat (spec 010, R1/P0)."""
from __future__ import annotations

from _fakes_phonology import FakeContext, FakePhonSource, FakePhoneme

from gramtrans.Lib.categories import phonemes_enumerate_source
from gramtrans.Lib.models import GrammarCategory, Selection


def _src():
    return FakePhonSource(phonemes=[
        FakePhoneme("p1", "p"),
        FakePhoneme("p2", "t"),
        FakePhoneme("p3", "k"),
    ])


def test_absent_key_transfers_all():
    """Back-compat: no leaf_item_picks key => every item enumerated."""
    ctx = FakeContext(source=_src())
    sel = Selection(categories={GrammarCategory.PHONEMES: True})
    out = phonemes_enumerate_source(ctx, sel)
    assert {p.guid for p in out} == {"p1", "p2", "p3"}


def test_subset_key_transfers_subset():
    ctx = FakeContext(source=_src())
    sel = Selection(
        categories={GrammarCategory.PHONEMES: True},
        leaf_item_picks={GrammarCategory.PHONEMES: frozenset({"p1", "p3"})},
    )
    out = phonemes_enumerate_source(ctx, sel)
    assert {p.guid for p in out} == {"p1", "p3"}


def test_empty_frozenset_transfers_none():
    ctx = FakeContext(source=_src())
    sel = Selection(
        categories={GrammarCategory.PHONEMES: True},
        leaf_item_picks={GrammarCategory.PHONEMES: frozenset()},
    )
    assert list(phonemes_enumerate_source(ctx, sel)) == []


def test_guid_normalization_required_both_sides():
    """Raw uppercase GUID in picks MISSES; normalized matches (P0 invariant)."""
    src = FakePhonSource(phonemes=[FakePhoneme("a1", "p", raw_guid="A1-BRACED")])
    ctx = FakeContext(source=src)
    # Un-normalized pick (uppercase) -> no match (filtered out).
    miss = phonemes_enumerate_source(ctx, Selection(
        categories={GrammarCategory.PHONEMES: True},
        leaf_item_picks={GrammarCategory.PHONEMES: frozenset({"A1"})},
    ))
    assert miss == []
    # Normalized pick (as the builder would store it) -> match.
    hit = phonemes_enumerate_source(ctx, Selection(
        categories={GrammarCategory.PHONEMES: True},
        leaf_item_picks={GrammarCategory.PHONEMES: frozenset({"a1"})},
    ))
    assert {p.guid for p in hit} == {"a1"}


def test_pick_for_off_category_is_inert_at_dispatch():
    """A leaf_item_picks key is harmless when the category is not enabled.

    The enumerate filter itself still applies (it is category-scoped), but the
    leaf-dispatch `is_on` gate would skip the category entirely. Here we assert
    the Selection accepts the key with the category off (no __post_init__ raise).
    """
    sel = Selection(
        categories={},  # PHONEMES not on
        leaf_item_picks={GrammarCategory.PHONEMES: frozenset({"p1"})},
    )
    assert sel.is_on(GrammarCategory.PHONEMES) is False
    assert sel.leaf_picks_for(GrammarCategory.PHONEMES) == frozenset({"p1"})


# ---- T019 (US2): collapse trims to leaf_item_picks; all-checked omits key ---

def _phon_inv():
    from _fakes_phonology import FakeNC, FakeRule, make_rhs
    from gramtrans.Lib.selection import build_phonology_inventory
    p1 = FakePhoneme("p1", "p")
    p2 = FakePhoneme("p2", "t")
    p3 = FakePhoneme("p3", "k")
    nc1 = FakeNC("nc1", "C", segments=[p1, p2, p3])
    rule1 = FakeRule("r1", "rule", struc_refs=[nc1], rhs=[make_rhs(left=p1)])
    return build_phonology_inventory(
        FakePhonSource(phonemes=[p1, p2, p3], ncs=[nc1], rules=[rule1])
    )


def test_whole_block_off_yields_empty_collapse():
    """SC-003: toggling the whole block off => nothing planned."""
    from gramtrans.Lib.selection import collapse_phonology
    inv = _phon_inv()
    out = collapse_phonology(inv, {})  # nothing checked
    assert out["categories"] == {}
    assert out["leaf_item_picks"] == {}


def test_trim_3_of_n_records_subset_pick():
    """Deselecting some (not all) phonemes => leaf_item_picks subset."""
    from gramtrans.Lib.selection import collapse_phonology
    inv = _phon_inv()
    checked = {g.category: {r.guid for r in g.rows} for g in inv.groups}
    checked[GrammarCategory.PHONEMES] = {"p1", "p2"}  # drop p3 (2 of 3)
    out = collapse_phonology(inv, checked)
    assert out["categories"][GrammarCategory.PHONEMES] is True
    assert out["leaf_item_picks"][GrammarCategory.PHONEMES] == frozenset({"p1", "p2"})


def test_category_all_checked_omits_key():
    """SC-003: a fully-checked category omits its leaf_item_picks key (transfer-all)."""
    from gramtrans.Lib.selection import collapse_phonology
    inv = _phon_inv()
    checked = {g.category: {r.guid for r in g.rows} for g in inv.groups}
    out = collapse_phonology(inv, checked)
    assert GrammarCategory.PHONEMES not in out["leaf_item_picks"]
    assert GrammarCategory.NATURAL_CLASSES not in out["leaf_item_picks"]

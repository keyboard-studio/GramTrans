"""Phoneme label: vernacular grapheme + IPA-in-slashes (spec 010).

Verified against live data: 'Ejagham Full GT-Test' phonemes carry their
grapheme only in the *vernacular* Name alternative (analysis alternative is
FLEx's '***' sentinel, which was leaking to the UI), and 'Mbugwe LizzieHC
practice' has 35/42 phonemes with a BasicIPASymbol set — the (vern, ipa) pairs
below are taken verbatim from that project.
"""
from __future__ import annotations

from _fakes_phonology import FakePhoneme, FakePhonSource

from gramtrans.Lib.models import GrammarCategory as GC
from gramtrans.Lib.selection import _phon_label, build_phonology_inventory


# --- unit: _phon_label(phoneme=True) --------------------------------------

def test_vernacular_only_renders_grapheme_not_sentinel():
    # Analysis alt is '***'; the grapheme lives in the vernacular alt.
    ph = FakePhoneme("ph1", vernacular="e")
    assert _phon_label(ph, phoneme=True) == "e"


def test_vernacular_plus_ipa_concatenated_with_slashes():
    # Real Mbugwe pairs: ('y','j'), ('oo','oː'), ('sh','ç').
    assert _phon_label(FakePhoneme("a", vernacular="y", ipa="j"),
                       phoneme=True) == "y /j/"
    assert _phon_label(FakePhoneme("b", vernacular="oo", ipa="oː"),
                       phoneme=True) == "oo /oː/"
    assert _phon_label(FakePhoneme("c", vernacular="sh", ipa="ç"),
                       phoneme=True) == "sh /ç/"


def test_identical_vernacular_and_ipa_still_shows_both():
    # ('s','s') in Mbugwe — literal concat per the requested format.
    assert _phon_label(FakePhoneme("s", vernacular="s", ipa="s"),
                       phoneme=True) == "s /s/"


def test_ipa_only_when_grapheme_blank():
    # name='***' models a phoneme with no grapheme in either WS (the analysis
    # alternative is the empty sentinel), only an IPA symbol.
    ph = FakePhoneme("ph1", name="***", ipa="j")
    assert _phon_label(ph, phoneme=True) == "/j/"


def test_empty_sentinel_ipa_ignored():
    # BasicIPASymbol carrying the '***' sentinel is treated as unset.
    ph = FakePhoneme("ph1", vernacular="e", ipa="***")
    assert _phon_label(ph, phoneme=True) == "e"


def test_description_used_when_no_grapheme_or_ipa():
    # 'Refer to as' (Name) and 'IPA Symbol' both empty, but 'Description' set.
    ph = FakePhoneme("ph1", name="***", description="low central unrounded vowel")
    assert _phon_label(ph, phoneme=True) == "low central unrounded vowel"


def test_fully_blank_phoneme_shows_placeholder_not_guid():
    # Nothing in any field -> defensive placeholder (builder skips these rows).
    ph = FakePhoneme("abcdef0123456789", name="***")
    assert _phon_label(ph, phoneme=True) == "(unnamed phoneme)"


def test_non_phoneme_stays_analysis_and_filters_sentinel():
    # A feature-like object named via analysis WS: phoneme=False, no slashes.
    from _fakes_phonology import FakeFeature
    assert _phon_label(FakeFeature("f1", "voiced")) == "voiced"


# --- integration: inventory rows use the phoneme labeller ------------------

def test_inventory_phoneme_rows_carry_vern_plus_ipa():
    src = FakePhonSource(phonemes=[
        FakePhoneme("ph1", vernacular="y", ipa="j"),
        FakePhoneme("ph2", vernacular="r"),          # no IPA
    ])
    inv = build_phonology_inventory(src)
    grp = inv.group_for(GC.PHONEMES)
    labels = [r.label for r in grp.rows]
    assert labels == ["y /j/", "r"]


def test_inventory_silently_skips_fully_empty_phonemes():
    # Two real phonemes flanking a dangling empty (no refer-to-as, no IPA,
    # no description) -> the empty is dropped, not shown as a placeholder row.
    src = FakePhonSource(phonemes=[
        FakePhoneme("ph1", vernacular="a"),
        FakePhoneme("empty", name="***"),            # empty in all fields
        FakePhoneme("ph2", vernacular="e", ipa="e"),
    ])
    inv = build_phonology_inventory(src)
    grp = inv.group_for(GC.PHONEMES)
    assert grp.count == 2
    assert [r.label for r in grp.rows] == ["a", "e /e/"]


def test_phoneme_kept_when_only_description_present():
    # Has a Description but no grapheme/IPA -> NOT empty in all fields; kept.
    src = FakePhonSource(phonemes=[
        FakePhoneme("ph1", name="***", description="glottal stop"),
    ])
    inv = build_phonology_inventory(src)
    grp = inv.group_for(GC.PHONEMES)
    assert [r.label for r in grp.rows] == ["glottal stop"]

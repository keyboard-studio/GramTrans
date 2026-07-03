"""Label runs carry WS provenance and always join back to the flat label.

Spec 011: `_phon_runs` / `affix_label_runs` tag each substring with the WS role
that should render it. The invariant guarded here is that the runs are a faithful
decomposition of the flat label string, so nothing downstream (casefold match,
target-status compare) is affected by the added provenance.
"""
from __future__ import annotations

from _fakes_phonology import FakeFeature, FakePhoneme, FakePhonSource

from gramtrans.Lib.models import GrammarCategory as GC
from gramtrans.Lib.selection import (
    _phon_label,
    _phon_runs,
    affix_label_runs,
    build_phonology_inventory,
)
from gramtrans.Lib.ws_fonts import WsRole, runs_to_text


# --- _phon_runs: role tagging ---------------------------------------------

def test_phoneme_grapheme_is_vernacular_ipa_is_ipa():
    runs = _phon_runs(FakePhoneme("a", vernacular="y", ipa="j"), phoneme=True)
    assert runs == (("y", WsRole.VERNACULAR), (" ", None), ("/j/", WsRole.IPA))
    assert runs_to_text(runs) == "y /j/"


def test_phoneme_grapheme_only_is_single_vernacular_run():
    runs = _phon_runs(FakePhoneme("a", vernacular="r"), phoneme=True)
    assert runs == (("r", WsRole.VERNACULAR),)


def test_phoneme_ipa_only_is_single_ipa_run():
    runs = _phon_runs(FakePhoneme("a", name="***", ipa="j"), phoneme=True)
    assert runs == (("/j/", WsRole.IPA),)


def test_phoneme_description_fallback_is_analysis():
    runs = _phon_runs(
        FakePhoneme("a", name="***", description="glottal stop"), phoneme=True
    )
    assert runs == (("glottal stop", WsRole.ANALYSIS),)


def test_unnamed_phoneme_placeholder_has_no_ws():
    runs = _phon_runs(FakePhoneme("abcdef0123456789", name="***"), phoneme=True)
    assert runs == (("(unnamed phoneme)", None),)


def test_non_phoneme_name_is_analysis():
    runs = _phon_runs(FakeFeature("f1", "voiced"))
    assert runs == (("voiced", WsRole.ANALYSIS),)


# --- runs join to label for every code path -------------------------------

def test_runs_join_equals_phon_label_across_shapes():
    cases = [
        (FakePhoneme("a", vernacular="y", ipa="j"), True),
        (FakePhoneme("b", vernacular="oo", ipa="oː"), True),
        (FakePhoneme("c", vernacular="r"), True),
        (FakePhoneme("d", name="***", ipa="j"), True),
        (FakePhoneme("e", name="***", description="low vowel"), True),
        (FakePhoneme("f0123456", name="***"), True),
        (FakeFeature("g1", "voiced"), False),
    ]
    for obj, phoneme in cases:
        assert runs_to_text(_phon_runs(obj, phoneme=phoneme)) == _phon_label(
            obj, phoneme=phoneme
        )


# --- inventory rows carry runs --------------------------------------------

def test_inventory_phoneme_rows_carry_runs():
    src = FakePhonSource(phonemes=[FakePhoneme("ph1", vernacular="y", ipa="j")])
    grp = build_phonology_inventory(src).group_for(GC.PHONEMES)
    row = grp.rows[0]
    assert row.label == "y /j/"
    assert runs_to_text(row.runs) == row.label
    assert row.runs[0] == ("y", WsRole.VERNACULAR)
    assert row.runs[-1] == ("/j/", WsRole.IPA)


# --- affix_label_runs ------------------------------------------------------

def test_affix_runs_split_form_and_gloss():
    runs = affix_label_runs("na-", "PST")
    assert runs[0] == ("na-", WsRole.VERNACULAR)
    assert runs[-1] == ("PST", WsRole.ANALYSIS)
    assert runs_to_text(runs) == "na-  ->  PST"


def test_affix_runs_tolerate_blank_gloss():
    runs = affix_label_runs("na-", "")
    assert runs_to_text(runs) == "na-  ->  "
    assert runs[0] == ("na-", WsRole.VERNACULAR)

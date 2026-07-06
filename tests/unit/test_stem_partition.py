"""T004/T005: stem/affix partition (_partition_entries).

Covers the highest-risk correctness point of feature 019 — the null-guard
INVERSION (FR-002). The affix filter skips on exception; the stem side must
INCLUDE on exception so an entry with a null lexeme form, a null morphtype, or
an uncastable morphtype lands in the STEM bucket rather than being dropped from
both tabs.

Also asserts the partition is complete and disjoint over LexDbOA.Entries
(SC-001).

Note on clitics: proclitics/enclitics have IsAffixType == False and therefore
land in the STEM bucket. That is expected behaviour, not a failure — the
feature only treats an entry as an affix when IsAffixType is explicitly True.
"""
from __future__ import annotations

from _fakes_affix import make_infl_entry, make_pos, make_non_affix_entry
from _fakes_stem import (
    make_null_form_entry,
    make_null_morphtype_entry,
    make_stem_entry,
    make_uncastable_morphtype_entry,
)

from gramtrans.Lib.selection import _partition_entries


def _guids(entries):
    return [e.Guid for e in entries]


# ---------------------------------------------------------------------------
# Explicit IsAffixType classification
# ---------------------------------------------------------------------------

class TestExplicitClassification:

    def test_is_affix_true_goes_to_affix(self):
        pos = make_pos("pv", "v", "Verb")
        affix = make_infl_entry("a1", "-s", ["3sg"], pos)
        affix_entries, stem_entries = _partition_entries([affix])
        assert _guids(affix_entries) == ["a1"]
        assert stem_entries == []

    def test_is_affix_false_goes_to_stem(self):
        pos = make_pos("pn", "n", "Noun")
        stem = make_stem_entry("s1", "dog", pos, glosses=["dog"])
        affix_entries, stem_entries = _partition_entries([stem])
        assert affix_entries == []
        assert _guids(stem_entries) == ["s1"]

    def test_bare_non_affix_entry_is_stem(self):
        # make_non_affix_entry: IsAffixType=False, no MSAs.
        entry = make_non_affix_entry("r1", "root")
        affix_entries, stem_entries = _partition_entries([entry])
        assert _guids(stem_entries) == ["r1"]
        assert affix_entries == []


# ---------------------------------------------------------------------------
# Null-guard INVERSION (FR-002) — include-on-exception -> STEM
# ---------------------------------------------------------------------------

class TestNullGuardInversion:

    def test_null_lexeme_form_is_stem(self):
        entry = make_null_form_entry("n1")
        affix_entries, stem_entries = _partition_entries([entry])
        assert _guids(stem_entries) == ["n1"], "null LexemeFormOA must be STEM"
        assert affix_entries == []

    def test_null_morphtype_is_stem(self):
        entry = make_null_morphtype_entry("n2", "root")
        affix_entries, stem_entries = _partition_entries([entry])
        assert _guids(stem_entries) == ["n2"], "null MorphTypeRA must be STEM"
        assert affix_entries == []

    def test_uncastable_morphtype_is_stem(self):
        entry = make_uncastable_morphtype_entry("n3", "root")
        affix_entries, stem_entries = _partition_entries([entry])
        assert _guids(stem_entries) == ["n3"], (
            "uncastable morphtype (AttributeError on IsAffixType) must be STEM"
        )
        assert affix_entries == []

    def test_no_null_guard_entry_is_dropped(self):
        # All three edge entries must survive in the stem partition.
        edges = [
            make_null_form_entry("n1"),
            make_null_morphtype_entry("n2"),
            make_uncastable_morphtype_entry("n3"),
        ]
        affix_entries, stem_entries = _partition_entries(edges)
        assert set(_guids(stem_entries)) == {"n1", "n2", "n3"}
        assert affix_entries == []


# ---------------------------------------------------------------------------
# Complete + disjoint over LexDbOA.Entries (SC-001)
# ---------------------------------------------------------------------------

class TestCompleteAndDisjoint:

    def _mixed(self):
        pv = make_pos("pv", "v", "Verb")
        pn = make_pos("pn", "n", "Noun")
        return [
            make_infl_entry("a1", "-s", ["3sg"], pv),
            make_stem_entry("s1", "dog", pn, glosses=["dog"]),
            make_infl_entry("a2", "-ed", ["past"], pv),
            make_null_form_entry("s2"),
            make_stem_entry("s3", "cat", pn, glosses=["cat"]),
            make_uncastable_morphtype_entry("s4"),
        ]

    def test_partition_is_complete(self):
        entries = self._mixed()
        affix_entries, stem_entries = _partition_entries(entries)
        total = set(_guids(affix_entries)) | set(_guids(stem_entries))
        assert total == {e.Guid for e in entries}
        assert len(affix_entries) + len(stem_entries) == len(entries)

    def test_partition_is_disjoint(self):
        entries = self._mixed()
        affix_entries, stem_entries = _partition_entries(entries)
        assert set(_guids(affix_entries)).isdisjoint(set(_guids(stem_entries)))

    def test_expected_buckets(self):
        entries = self._mixed()
        affix_entries, stem_entries = _partition_entries(entries)
        assert set(_guids(affix_entries)) == {"a1", "a2"}
        assert set(_guids(stem_entries)) == {"s1", "s2", "s3", "s4"}

    def test_iteration_order_preserved(self):
        entries = self._mixed()
        affix_entries, stem_entries = _partition_entries(entries)
        # Affixes keep source order a1 before a2; stems keep s1,s2,s3,s4.
        assert _guids(affix_entries) == ["a1", "a2"]
        assert _guids(stem_entries) == ["s1", "s2", "s3", "s4"]

    def test_empty_input(self):
        affix_entries, stem_entries = _partition_entries([])
        assert affix_entries == []
        assert stem_entries == []

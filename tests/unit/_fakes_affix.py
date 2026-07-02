"""Fake duck-typed handles for affix / MSA / POS tests (T002).

Provides lightweight stubs for the LCM object graph used by
`build_pos_grouped_inventory`.  No live LCM or Qt required.

Usage::

    from tests.unit._fakes_affix import (
        make_source,
        make_infl_entry,
        make_deriv_entry,
        make_uncl_entry,
        make_no_pos_entry,
        make_no_analysis_entry,
        make_pos,
    )
"""
from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------------
# POS node fakes
# ---------------------------------------------------------------------------

class FakePosAbbrev:
    def __init__(self, text: str):
        self.Text = text


class FakePos:
    """Fake ICmPossibility-compatible POS handle."""

    def __init__(self, guid: str, abbrev: str, name: str,
                 children: Optional[list] = None):
        self.Guid = guid
        self._abbrev = abbrev
        self._name = name
        self.SubPossibilitiesOS = children or []
        # Support cast pattern: ICmPossibility(pos).Abbreviation.BestAnalysisAlternative
        self.Abbreviation = type("_Abbrev", (), {
            "BestAnalysisAlternative": FakePosAbbrev(abbrev)
        })()
        self.Name = type("_Name", (), {
            "BestAnalysisAlternative": FakePosAbbrev(name)
        })()


def make_pos(guid: str, abbrev: str = "", name: str = "",
             children: Optional[list] = None) -> FakePos:
    """Create a FakePos; abbrev defaults to guid abbreviation."""
    return FakePos(guid, abbrev or guid, name or guid, children)


# ---------------------------------------------------------------------------
# Form / gloss fakes
# ---------------------------------------------------------------------------

class FakeText:
    def __init__(self, text: str):
        self.Text = text


class FakeMultiStr:
    def __init__(self, text: str):
        self.BestVernacularAlternative = FakeText(text)
        self.BestAnalysisAlternative = FakeText(text)


class FakeForm:
    def __init__(self, text: str):
        self.Form = FakeMultiStr(text)


class FakeMorphType:
    def __init__(self, is_affix: bool):
        self.IsAffixType = is_affix


class FakeLexemeForm:
    def __init__(self, text: str, is_affix: bool):
        self._text = text
        self.MorphTypeRA = FakeMorphType(is_affix)
        self.Form = FakeMultiStr(text)


# ---------------------------------------------------------------------------
# MSA fakes
# ---------------------------------------------------------------------------

class FakeInflMsa:
    ClassName = "MoInflAffMsa"

    def __init__(self, pos: Optional[FakePos]):
        self.PartOfSpeechRA = pos


class FakeDerivMsa:
    ClassName = "MoDerivAffMsa"

    def __init__(self, from_pos: Optional[FakePos], to_pos: Optional[FakePos]):
        self.FromPartOfSpeechRA = from_pos
        self.ToPartOfSpeechRA = to_pos


class FakeUnclMsa:
    ClassName = "MoUnclassifiedAffixMsa"

    def __init__(self, pos: Optional[FakePos]):
        self.PartOfSpeechRA = pos


class FakeUnknownMsa:
    ClassName = "MoStemMsa"  # not an affix MSA class


# ---------------------------------------------------------------------------
# Sense fakes
# ---------------------------------------------------------------------------

class FakeSense:
    def __init__(self, gloss: str, msa=None):
        self.Gloss = type("_Gloss", (), {
            "BestAnalysisAlternative": FakeText(gloss)
        })()
        self.MorphoSyntaxAnalysisRA = msa


# ---------------------------------------------------------------------------
# Entry fakes
# ---------------------------------------------------------------------------

class FakeEntry:
    """Fake ILexEntry-compatible handle."""

    def __init__(self, guid: str, form: str, is_affix: bool,
                 senses: Optional[list] = None,
                 msas: Optional[list] = None):
        self.Guid = guid
        self.LexemeFormOA = FakeLexemeForm(form, is_affix)
        self.SensesOS = senses or []
        self.MorphoSyntaxAnalysesOC = msas or []


def make_infl_entry(guid: str, form: str, glosses: list[str],
                    pos: Optional[FakePos]) -> FakeEntry:
    """Inflectional affix with one sense per gloss, all with the same POS."""
    msa = FakeInflMsa(pos)
    senses = [FakeSense(g, msa) for g in glosses]
    return FakeEntry(guid, form, True, senses=senses, msas=[msa])


def make_deriv_entry(guid: str, form: str, glosses: list[str],
                     from_pos: Optional[FakePos],
                     to_pos: Optional[FakePos]) -> FakeEntry:
    """Derivational affix."""
    msa = FakeDerivMsa(from_pos, to_pos)
    senses = [FakeSense(g, msa) for g in glosses]
    return FakeEntry(guid, form, True, senses=senses, msas=[msa])


def make_uncl_entry(guid: str, form: str, glosses: list[str],
                    pos: Optional[FakePos]) -> FakeEntry:
    """Unclassified affix MSA."""
    msa = FakeUnclMsa(pos)
    senses = [FakeSense(g, msa) for g in glosses]
    return FakeEntry(guid, form, True, senses=senses, msas=[msa])


def make_no_pos_entry(guid: str, form: str) -> FakeEntry:
    """Affix with an inflectional MSA but null POS -> junk.no_pos."""
    msa = FakeInflMsa(None)
    return FakeEntry(guid, form, True, senses=[FakeSense("gloss", msa)], msas=[msa])


def make_no_analysis_entry(guid: str, form: str) -> FakeEntry:
    """Affix with no senses and no MSAs -> junk.no_analysis."""
    return FakeEntry(guid, form, True, senses=[], msas=[])


def make_non_affix_entry(guid: str, form: str) -> FakeEntry:
    """Root/stem entry (IsAffixType=False) -- should be filtered out."""
    return FakeEntry(guid, form, False, senses=[], msas=[])


# ---------------------------------------------------------------------------
# Source handle fake
# ---------------------------------------------------------------------------

class FakePosOA:
    def __init__(self, possibilities: list):
        self.PossibilitiesOS = possibilities


class FakeLexDb:
    def __init__(self, entries: list):
        self.Entries = entries


class FakeLangProject:
    def __init__(self, entries: list, pos_list: list):
        self.LexDbOA = FakeLexDb(entries)
        self.PartsOfSpeechOA = FakePosOA(pos_list)


class FakeCache:
    def __init__(self, entries: list, pos_list: list):
        self.LangProject = FakeLangProject(entries, pos_list)


class FakeSource:
    def __init__(self, entries: list, pos_list: list):
        self.Cache = FakeCache(entries, pos_list)


def make_source(entries: list, pos_list: list) -> FakeSource:
    """Build a fake source handle from entries and top-level POS list."""
    return FakeSource(entries, pos_list)

"""Fake duck-typed handles for the 019 stem item-picker tests.

Reuses the affix fake infrastructure (POS / form / source handles) from
``_fakes_affix`` and adds the stem-specific pieces:

- ``FakeStemMsa`` — an ``MoStemMsa`` carrying ``PartOfSpeechRA``,
  ``MsFeaturesOA`` (a SINGLE ``IFsFeatStruc``), and ``InflectionClassRA``.
  Its ``SlotsRC`` is a tripwire that raises if the engine ever reads it
  (FR-013: a stem MSA must never be treated as an affix slot member).
- helpers to build stem entries and the null-guard edge cases the partition
  must classify as STEM (null lexeme form, null morphtype, uncastable
  morphtype).

No pythonnet / Qt required: ``selection._cast`` returns objects unchanged when
pythonnet is absent, so attribute access falls through to these fakes.
"""
from __future__ import annotations

from typing import Optional

from _fakes_affix import (  # re-export the shared pieces tests need
    FakeEntry,
    FakeMultiStr,
    FakeMultiUnicode,
    FakePos,
    FakeSense,
    make_pos,
    make_source,
)


# ---------------------------------------------------------------------------
# Stem MSA + feature / inflection-class stubs
# ---------------------------------------------------------------------------

class FakeFeatStruc:
    """Duck-typed IFsFeatStruc (MoStemMsa.MsFeaturesOA is a single one)."""

    def __init__(self, guid: str, name: str = "feat"):
        self.Guid = guid
        self.Name = FakeMultiUnicode(name)
        self.ClassName = "FsFeatStruc"


class FakeStemInflClass:
    """Duck-typed IMoInflClass reachable via MoStemMsa.InflectionClassRA."""

    def __init__(self, guid: str, name: str = "class"):
        self.Guid = guid
        self.Name = FakeMultiUnicode(name)
        self.ClassName = "MoInflClass"
        self.Abbreviation = FakeMultiUnicode(name)


class _SlotsTripwire:
    """SlotsRC exists on IMoStemMsa but MUST NEVER be read (FR-013).

    Reading it (iterate or len) raises loudly so a test proves the stem walk
    never touches it.
    """

    def __iter__(self):
        raise AssertionError("FR-013: SlotsRC must never be read on a stem MSA")

    def __len__(self):
        raise AssertionError("FR-013: SlotsRC must never be read on a stem MSA")


class FakeStemMsa:
    """Duck-typed IMoStemMsa."""

    ClassName = "MoStemMsa"

    def __init__(self, pos: Optional[FakePos] = None,
                 ms_features: Optional[FakeFeatStruc] = None,
                 infl_class: Optional[FakeStemInflClass] = None):
        self.PartOfSpeechRA = pos
        self.MsFeaturesOA = ms_features       # single IFsFeatStruc or None
        self.InflectionClassRA = infl_class   # IMoInflClass or None
        self.SlotsRC = _SlotsTripwire()       # forbidden read tripwire


class FakeInflAffMsaOnStem:
    """A non-MoStemMsa MSA that might sit on a stem-partitioned entry.

    Used to prove FR-013: on a stem entry a non-MoStemMsa arm is skipped, never
    recast. Reading PartOfSpeechRA is allowed to succeed, but if the engine ever
    routed it through the affix arm it would try SlotsRC (tripwire).
    """

    ClassName = "MoInflAffMsa"

    def __init__(self, pos: Optional[FakePos] = None):
        self.PartOfSpeechRA = pos
        self.SlotsRC = _SlotsTripwire()


# ---------------------------------------------------------------------------
# Stem entry builders
# ---------------------------------------------------------------------------

def make_stem_entry(guid: str, form: str,
                    pos: Optional[FakePos] = None,
                    glosses: Optional[list] = None,
                    ms_features: Optional[FakeFeatStruc] = None,
                    infl_class: Optional[FakeStemInflClass] = None,
                    extra_msas: Optional[list] = None) -> FakeEntry:
    """A stem entry (IsAffixType=False) with a single MoStemMsa."""
    msa = FakeStemMsa(pos, ms_features, infl_class)
    msas = [msa] + list(extra_msas or [])
    senses = [FakeSense(g, msa) for g in (glosses or [])]
    return FakeEntry(guid, form, False, senses=senses, msas=msas)


class FakeNullMorphForm:
    """A lexeme form whose MorphTypeRA is null -> entry classified STEM."""

    def __init__(self, text: str):
        self.MorphTypeRA = None
        self.Form = FakeMultiStr(text)


class FakeUncastableMorphType:
    """A morphtype object with no IsAffixType attribute.

    Reading ``.IsAffixType`` raises AttributeError -> include-on-exception ->
    STEM bucket (FR-002).
    """


class FakeUncastableMorphForm:
    def __init__(self, text: str):
        self.MorphTypeRA = FakeUncastableMorphType()
        self.Form = FakeMultiStr(text)


def make_null_form_entry(guid: str, msas: Optional[list] = None) -> FakeEntry:
    """Entry whose LexemeFormOA is None -> STEM (include-on-exception)."""
    entry = FakeEntry(guid, "x", False, senses=[], msas=msas or [])
    entry.LexemeFormOA = None
    return entry


def make_null_morphtype_entry(guid: str, form: str = "root",
                              msas: Optional[list] = None) -> FakeEntry:
    """Entry whose MorphTypeRA is None -> STEM (include-on-exception)."""
    entry = FakeEntry(guid, form, False, senses=[], msas=msas or [])
    entry.LexemeFormOA = FakeNullMorphForm(form)
    return entry


def make_uncastable_morphtype_entry(guid: str, form: str = "root",
                                    msas: Optional[list] = None) -> FakeEntry:
    """Entry whose morphtype raises on IsAffixType -> STEM."""
    entry = FakeEntry(guid, form, False, senses=[], msas=msas or [])
    entry.LexemeFormOA = FakeUncastableMorphForm(form)
    return entry

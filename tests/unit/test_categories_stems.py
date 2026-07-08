"""Unit tests for Phase 3c US3 stems leaf-category functions (T046-T055).

Stems are ILexEntry objects whose LexemeFormOA.MorphTypeRA.IsAffixType is
False (the affix/stem partition, mirroring US1 affixes). This file covers the
planning layer only -- host-free, no LCM/pythonnet -- exercising:

- stems_enumerate_source: the affix/stem partition + GOLD exclusion + the
  Selection.leaf_picks_for(STEMS) per-item subset (None => ALL).
- stems_dependencies: the E4/E10/FR-336 closure -- (GRAM_CATEGORIES, pos) per
  MSA POS, (STRATA, stratum) per MSA.StratumRA (FR-336), and
  (SEMANTIC_DOMAINS, domain) per sense.SemanticDomainsRC (FR-335).
- stems_required_writing_systems: () for stems.
- stems_plan_action: PlannedAction (GUID preserved), GOLD_INVIOLABLE skip,
  ALREADY_PRESENT_BY_GUID collision skip, and the _stash_entry_bindings side
  effect (MSA->slot + EntryRef component bindings; empty SlotsRC => no binding).

execute_action is LCM-bound (imports SIL.LCModel lazily) and is covered by the
integration suite; it is not exercised here.
"""
from __future__ import annotations

import sys
import types

import pytest

from gramtrans.Lib import categories
import gramtrans.Lib.categories as _cat_mod
from gramtrans.Lib.models import (
    GrammarCategory,
    PlannedAction,
    RunContext,
    Selection,
    Skip,
    SkipReason,
    WSMapping,
)


# ============================================================================
# Fakes (duck-typed LexEntry / MSA / sense surfaces with lowercase .guid)
#
# Phase 3c callbacks extract GUIDs via categories._guid_str_from, which
# host-free reads the LOWERCASE .guid attribute. We build fakes with lowercase
# .guid AND patch _guid_str_from (see _patch_guid fixture) so a leftover fake
# SIL.LCModel installed by a sibling test cannot perturb GUID extraction.
# ============================================================================

class _FakeMorphType:
    def __init__(self, is_affix: bool) -> None:
        self.IsAffixType = is_affix


class _FakeLexemeForm:
    def __init__(self, morphtype) -> None:
        self.MorphTypeRA = morphtype


class _FakeStratum:
    def __init__(self, guid: str) -> None:
        self.guid = guid


class _FakePOS:
    def __init__(self, guid: str) -> None:
        self.guid = guid


class _FakeSemDomain:
    def __init__(self, guid: str) -> None:
        self.guid = guid


class _FakeSense:
    def __init__(self, guid: str, domains=()) -> None:
        self.guid = guid
        self.SemanticDomainsRC = list(domains)


class _FakeStemMSA:
    """A MoStemMsa-shaped analysis: carries a POS + optional stratum + slots."""

    ClassName = "MoStemMsa"

    def __init__(self, guid: str, pos=None, stratum=None, slots=()) -> None:
        self.guid = guid
        self.PartOfSpeechRA = pos
        self.StratumRA = stratum
        self.SlotsRC = list(slots)


class _FakeEntryRef:
    def __init__(self, components=(), primaries=()) -> None:
        self.ComponentLexemesRS = list(components)
        self.PrimaryLexemesRS = list(primaries)


class _FakeEntry:
    """A stem (or affix) ILexEntry stand-in."""

    def __init__(self, guid, *, is_affix=False, has_form=True, msas=(),
                 senses=(), entry_refs=(), catalog_source_id=None) -> None:
        self.guid = guid
        if has_form:
            self.LexemeFormOA = _FakeLexemeForm(_FakeMorphType(is_affix))
        else:
            self.LexemeFormOA = None
        self.MorphoSyntaxAnalysesOC = list(msas)
        self.SensesOS = list(senses)
        self.EntryRefsOS = list(entry_refs)
        if catalog_source_id is not None:
            self.CatalogSourceId = catalog_source_id


class _FakeLexDb:
    def __init__(self, entries) -> None:
        self.EntriesOC = list(entries)


class _FakeLangProject:
    def __init__(self, entries) -> None:
        self.LexDbOA = _FakeLexDb(entries)


class _FakeHandle:
    """Source/target handle exposing the contract nav shape used by
    categories._iter_lex_entries (handle.LangProject.LexDbOA.EntriesOC)."""

    def __init__(self, entries=()) -> None:
        self.LangProject = _FakeLangProject(entries)


def _ctx(source, target) -> RunContext:
    return RunContext(
        source_handle=source,
        source_project_name="Src",
        source_project_path="/src",
        target_handle=target,
        target_project_name="Tgt",
        target_project_path="/tgt",
        run_id="GT-20260706-010000",
        started_at="2026-07-06T01:00:00",
    )


def _ctx_with_stash(source, target):
    """RunContext with the empty binding dicts preview.build_run_plan attaches,
    plus references so tests can inspect what plan_action stashed."""
    ctx = _ctx(source, target)
    msa_bindings: dict = {}
    ref_bindings: dict = {}
    object.__setattr__(ctx, "_msa_slot_bindings", msa_bindings)
    object.__setattr__(ctx, "_lexentry_ref_bindings", ref_bindings)
    return ctx, msa_bindings, ref_bindings


_BUNDLE = categories.for_category(GrammarCategory.STEMS)


@pytest.fixture(autouse=True)
def _patch_guid(monkeypatch):
    """Host-free GUID extraction from the lowercase .guid attribute."""
    monkeypatch.setattr(
        _cat_mod, "_guid_str_from",
        lambda obj: str(getattr(obj, "guid", "")).lower(),
    )
    # Guard against a leftover fake SIL.LCModel installed by a sibling test:
    # the patched _guid_str_from never imports it, but keep the environment
    # clean/deterministic regardless.
    fake_lcm = types.ModuleType("SIL.LCModel")
    sys.modules.setdefault("SIL", types.ModuleType("SIL"))
    original = sys.modules.get("SIL.LCModel")
    sys.modules["SIL.LCModel"] = fake_lcm
    yield
    if original is None:
        sys.modules.pop("SIL.LCModel", None)
    else:
        sys.modules["SIL.LCModel"] = original


# ============================================================================
# Bundle registration
# ============================================================================

def test_bundle_registered_with_all_callback_keys() -> None:
    assert set(_BUNDLE) >= {
        "enumerate_source", "dependencies", "required_writing_systems",
        "plan_action", "execute_action",
    }
    for key in ("enumerate_source", "dependencies", "required_writing_systems",
                "plan_action", "execute_action"):
        assert callable(_BUNDLE[key])


# ============================================================================
# T046-T047 — stems_enumerate_source (affix/stem partition + GOLD + picks)
# ============================================================================

def test_enumerate_yields_only_stems() -> None:
    """Non-affix entries with a lexeme form are yielded; affixes are excluded."""
    stem = _FakeEntry("stem-1", is_affix=False)
    affix = _FakeEntry("affix-1", is_affix=True)
    src = _FakeHandle([stem, affix])
    ctx = _ctx(src, _FakeHandle())

    items = list(_BUNDLE["enumerate_source"](ctx, None))
    assert {i.guid for i in items} == {"stem-1"}


def test_enumerate_excludes_degenerate_entries_without_form() -> None:
    """An entry with no LexemeFormOA (no morphtype) is neither affix nor stem."""
    stem = _FakeEntry("stem-1", is_affix=False)
    degenerate = _FakeEntry("no-form", has_form=False)
    src = _FakeHandle([stem, degenerate])
    ctx = _ctx(src, _FakeHandle())

    items = list(_BUNDLE["enumerate_source"](ctx, None))
    assert {i.guid for i in items} == {"stem-1"}


def test_enumerate_excludes_gold_stems() -> None:
    """A stem carrying a non-empty CatalogSourceId is GOLD and excluded."""
    plain = _FakeEntry("stem-1", is_affix=False)
    gold = _FakeEntry("stem-gold", is_affix=False, catalog_source_id="MGA:xyz")
    src = _FakeHandle([plain, gold])
    ctx = _ctx(src, _FakeHandle())

    items = list(_BUNDLE["enumerate_source"](ctx, None))
    assert {i.guid for i in items} == {"stem-1"}


def test_enumerate_none_selection_transfers_all_stems() -> None:
    stems = [_FakeEntry(f"stem-{i}", is_affix=False) for i in range(3)]
    src = _FakeHandle(stems)
    ctx = _ctx(src, _FakeHandle())

    items = list(_BUNDLE["enumerate_source"](ctx, None))
    assert {i.guid for i in items} == {"stem-0", "stem-1", "stem-2"}


def test_enumerate_selection_subset_filters_by_leaf_picks() -> None:
    """A non-None leaf_picks_for(STEMS) subset filters to the picked GUIDs."""
    stems = [_FakeEntry(f"stem-{i}", is_affix=False) for i in range(3)]
    src = _FakeHandle(stems)
    ctx = _ctx(src, _FakeHandle())
    selection = Selection(
        categories={GrammarCategory.STEMS: True},
        leaf_item_picks={GrammarCategory.STEMS: frozenset({"stem-0", "stem-2"})},
    )

    items = list(_BUNDLE["enumerate_source"](ctx, selection))
    assert {i.guid for i in items} == {"stem-0", "stem-2"}


def test_enumerate_selection_without_stem_picks_transfers_all() -> None:
    """A Selection with no STEMS entry in leaf_item_picks => ALL (subset None)."""
    stems = [_FakeEntry(f"stem-{i}", is_affix=False) for i in range(2)]
    src = _FakeHandle(stems)
    ctx = _ctx(src, _FakeHandle())
    selection = Selection(categories={GrammarCategory.STEMS: True})

    items = list(_BUNDLE["enumerate_source"](ctx, selection))
    assert {i.guid for i in items} == {"stem-0", "stem-1"}


def test_enumerate_empty_pick_subset_transfers_none() -> None:
    stems = [_FakeEntry("stem-0", is_affix=False)]
    src = _FakeHandle(stems)
    ctx = _ctx(src, _FakeHandle())
    selection = Selection(
        categories={GrammarCategory.STEMS: True},
        leaf_item_picks={GrammarCategory.STEMS: frozenset()},
    )

    assert list(_BUNDLE["enumerate_source"](ctx, selection)) == []


def test_enumerate_source_none_handle_yields_nothing() -> None:
    ctx = _ctx(object(), object())
    assert list(_BUNDLE["enumerate_source"](ctx, None)) == []


def test_enumerate_callable_positional_and_keyword() -> None:
    stem = _FakeEntry("stem-1", is_affix=False)
    ctx = _ctx(_FakeHandle([stem]), _FakeHandle())
    positional = list(_BUNDLE["enumerate_source"](ctx, None))
    keyword = list(_BUNDLE["enumerate_source"](context=ctx, selection=None))
    assert {i.guid for i in positional} == {i.guid for i in keyword} == {"stem-1"}


# ============================================================================
# T048-T050 — stems_dependencies (POS + STRATA + SEMANTIC_DOMAINS closure)
# ============================================================================

def test_dependencies_pos_edge_per_msa() -> None:
    """(GRAM_CATEGORIES, pos_guid) per MSA POS (E4; repo convention uses
    GRAM_CATEGORIES for the owning-POS edge, not POS)."""
    msa = _FakeStemMSA("msa-1", pos=_FakePOS("pos-noun"))
    entry = _FakeEntry("stem-1", msas=[msa])
    deps = tuple(_BUNDLE["dependencies"](piece=entry))
    assert (GrammarCategory.GRAM_CATEGORIES, "pos-noun") in deps


def test_dependencies_stratum_edge_per_msa_fr336() -> None:
    """FR-336: (STRATA, stratum_guid) per MoStemMsa.StratumRA."""
    msa = _FakeStemMSA("msa-1", pos=_FakePOS("pos-noun"),
                       stratum=_FakeStratum("stratum-1"))
    entry = _FakeEntry("stem-1", msas=[msa])
    deps = tuple(_BUNDLE["dependencies"](piece=entry))
    assert (GrammarCategory.STRATA, "stratum-1") in deps


def test_dependencies_semantic_domain_edge_per_sense_fr335() -> None:
    """FR-335: (SEMANTIC_DOMAINS, domain_guid) per sense.SemanticDomainsRC."""
    sense = _FakeSense("sense-1", domains=[_FakeSemDomain("dom-1"),
                                           _FakeSemDomain("dom-2")])
    entry = _FakeEntry("stem-1", senses=[sense])
    deps = tuple(_BUNDLE["dependencies"](piece=entry))
    dom_deps = {g for (c, g) in deps if c == GrammarCategory.SEMANTIC_DOMAINS}
    assert dom_deps == {"dom-1", "dom-2"}


def test_dependencies_full_closure_pos_stratum_and_domains() -> None:
    msa = _FakeStemMSA("msa-1", pos=_FakePOS("pos-noun"),
                       stratum=_FakeStratum("stratum-1"))
    sense = _FakeSense("sense-1", domains=[_FakeSemDomain("dom-1")])
    entry = _FakeEntry("stem-1", msas=[msa], senses=[sense])
    deps = tuple(_BUNDLE["dependencies"](piece=entry))
    assert (GrammarCategory.GRAM_CATEGORIES, "pos-noun") in deps
    assert (GrammarCategory.STRATA, "stratum-1") in deps
    assert (GrammarCategory.SEMANTIC_DOMAINS, "dom-1") in deps


def test_dependencies_deduplicated() -> None:
    """Two MSAs sharing a POS + stratum, two senses sharing a domain => one
    edge each (dedupe)."""
    pos = _FakePOS("pos-noun")
    stratum = _FakeStratum("stratum-1")
    dom = _FakeSemDomain("dom-1")
    entry = _FakeEntry(
        "stem-1",
        msas=[_FakeStemMSA("m1", pos=pos, stratum=stratum),
              _FakeStemMSA("m2", pos=pos, stratum=stratum)],
        senses=[_FakeSense("s1", domains=[dom]),
                _FakeSense("s2", domains=[dom])],
    )
    deps = tuple(_BUNDLE["dependencies"](piece=entry))
    assert deps.count((GrammarCategory.GRAM_CATEGORIES, "pos-noun")) == 1
    assert deps.count((GrammarCategory.STRATA, "stratum-1")) == 1
    assert deps.count((GrammarCategory.SEMANTIC_DOMAINS, "dom-1")) == 1


def test_dependencies_bare_entry_returns_empty() -> None:
    entry = _FakeEntry("stem-bare")
    assert tuple(_BUNDLE["dependencies"](piece=entry)) == ()


def test_dependencies_no_stratum_no_strata_edge() -> None:
    """A MoStemMsa with StratumRA=None emits no STRATA edge."""
    msa = _FakeStemMSA("msa-1", pos=_FakePOS("pos-noun"), stratum=None)
    entry = _FakeEntry("stem-1", msas=[msa])
    deps = tuple(_BUNDLE["dependencies"](piece=entry))
    assert not any(c == GrammarCategory.STRATA for (c, _g) in deps)


def test_dependencies_returns_tuple() -> None:
    entry = _FakeEntry("stem-1", msas=[_FakeStemMSA("m", pos=_FakePOS("p"))])
    assert isinstance(_BUNDLE["dependencies"](entry), tuple)


# ============================================================================
# required_writing_systems
# ============================================================================

def test_required_writing_systems_empty() -> None:
    entry = _FakeEntry("stem-1", is_affix=False)
    assert tuple(_BUNDLE["required_writing_systems"](piece=entry)) == ()


# ============================================================================
# T051-T053 — stems_plan_action
# ============================================================================

def test_plan_action_emits_guid_preserving_planned_action() -> None:
    stem = _FakeEntry("stem-1", is_affix=False)
    ctx, _m, _r = _ctx_with_stash(_FakeHandle([stem]), _FakeHandle())

    result = _BUNDLE["plan_action"](piece=stem, context=ctx, ws_mapping=WSMapping())

    assert isinstance(result, PlannedAction)
    assert result.category == GrammarCategory.STEMS
    assert result.source_guid == "stem-1"
    assert result.intended_target_guid == "stem-1"


def test_plan_action_callable_positional() -> None:
    stem = _FakeEntry("stem-1", is_affix=False)
    ctx, _m, _r = _ctx_with_stash(_FakeHandle([stem]), _FakeHandle())
    result = _BUNDLE["plan_action"](stem, ctx, WSMapping())
    assert isinstance(result, PlannedAction)
    assert result.source_guid == "stem-1"


def test_plan_action_gold_stem_transfers() -> None:
    """v7.0.0 GOLD unlock: a GOLD stem is an ordinary item. With its GUID absent
    from the target the plan_action's defense-in-depth GOLD_INVIOLABLE skip is
    gone, so it transfers like any stem (PlannedAction, GUID preserved)."""
    gold = _FakeEntry("stem-gold", is_affix=False, catalog_source_id="MGA:xyz")
    ctx, _m, _r = _ctx_with_stash(_FakeHandle([gold]), _FakeHandle())

    result = _BUNDLE["plan_action"](piece=gold, context=ctx, ws_mapping=WSMapping())

    assert isinstance(result, PlannedAction)
    assert result.category == GrammarCategory.STEMS
    assert result.source_guid == "stem-gold"
    assert result.intended_target_guid == "stem-gold"


def test_plan_action_collision_already_present_by_guid() -> None:
    """Stem GUID already in target => Skip(ALREADY_PRESENT_BY_GUID)."""
    stem = _FakeEntry("stem-dup", is_affix=False)
    tgt = _FakeHandle([_FakeEntry("stem-dup", is_affix=False)])
    ctx, _m, _r = _ctx_with_stash(_FakeHandle([stem]), tgt)

    result = _BUNDLE["plan_action"](piece=stem, context=ctx, ws_mapping=WSMapping())

    assert isinstance(result, Skip)
    assert result.reason == SkipReason.ALREADY_PRESENT_BY_GUID
    assert result.source_guid == "stem-dup"


# ============================================================================
# T053 — _stash_entry_bindings side effect (17.1 + post-pass A deferral)
# ============================================================================

def test_plan_action_stashes_entryref_component_bindings() -> None:
    """A stem entry with EntryRef component/primary lexemes stashes into
    plan.lexentry_ref_bindings for post-pass A (FR-340)."""
    ref = _FakeEntryRef(
        components=[_FakeEntry("comp-a", is_affix=False),
                    _FakeEntry("comp-b", is_affix=False)],
        primaries=[_FakeEntry("prim-a", is_affix=False)],
    )
    stem = _FakeEntry("stem-1", is_affix=False, entry_refs=[ref])
    ctx, _msa, ref_bindings = _ctx_with_stash(_FakeHandle([stem]), _FakeHandle())

    result = _BUNDLE["plan_action"](piece=stem, context=ctx, ws_mapping=WSMapping())

    assert isinstance(result, PlannedAction)
    assert ref_bindings == {
        "stem-1": {
            "ComponentLexemesRS": ["comp-a", "comp-b"],
            "PrimaryLexemesRS": ["prim-a"],
        }
    }


def test_plan_action_stashes_msa_slot_bindings_when_nonempty() -> None:
    """An MSA with a non-empty SlotsRC stashes a binding for the 17.1 sub-pass."""
    slot_a = types.SimpleNamespace(guid="slot-a")
    slot_b = types.SimpleNamespace(guid="slot-b")
    msa = _FakeStemMSA("msa-1", pos=_FakePOS("pos-noun"), slots=[slot_a, slot_b])
    stem = _FakeEntry("stem-1", is_affix=False, msas=[msa])
    ctx, msa_bindings, _r = _ctx_with_stash(_FakeHandle([stem]), _FakeHandle())

    _BUNDLE["plan_action"](piece=stem, context=ctx, ws_mapping=WSMapping())

    assert msa_bindings == {"msa-1": ["slot-a", "slot-b"]}


def test_plan_action_empty_slotsrc_stashes_no_binding() -> None:
    """T040 invariant: an MSA with an empty SlotsRC produces NO binding."""
    msa = _FakeStemMSA("msa-1", pos=_FakePOS("pos-noun"), slots=[])
    stem = _FakeEntry("stem-1", is_affix=False, msas=[msa])
    ctx, msa_bindings, _r = _ctx_with_stash(_FakeHandle([stem]), _FakeHandle())

    _BUNDLE["plan_action"](piece=stem, context=ctx, ws_mapping=WSMapping())

    assert msa_bindings == {}


def test_plan_action_no_entryrefs_stashes_no_ref_binding() -> None:
    stem = _FakeEntry("stem-1", is_affix=False)
    ctx, _m, ref_bindings = _ctx_with_stash(_FakeHandle([stem]), _FakeHandle())

    _BUNDLE["plan_action"](piece=stem, context=ctx, ws_mapping=WSMapping())

    assert ref_bindings == {}


# ============================================================================
# execute_action is LCM-bound; covered by the integration suite.
# ============================================================================

@pytest.mark.integration
def test_stem_execute_requires_lcm() -> None:
    pytest.skip("LCM required; live stem closure covered by integration suite.")

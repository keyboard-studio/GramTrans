"""Unit tests for Phase 3c US1 Affixes leaf-category functions (T021-T028).

Covers the AFFIXES function bundle (`categories.for_category(GrammarCategory.AFFIXES)`)
at the host-free PLANNING layer:

- enumerate_source: filters source LexEntries to affixes
  (LexemeFormOA.MorphTypeRA.IsAffixType == True), excludes GOLD, honours
  selection.leaf_picks_for(AFFIXES) (None subset => ALL), empty source => ().
- dependencies: (GRAM_CATEGORIES, pos_guid) per MSA POS edge (E4), deduped,
  empty when no POS; uses GRAM_CATEGORIES (repo convention) not POS.
- required_writing_systems: () for the affix bundle.
- plan_action: PlannedAction (GUID-preserving) for MoInflAffMsa + MoStemMsa
  affixes; Skip(GOLD_INVIOLABLE) for GOLD; Skip(ALREADY_PRESENT_BY_GUID) on a
  target GUID collision; stashes MSA->slot + EntryRef bindings (unbound affix
  with empty SlotsRC => no binding, T040 invariant).
- _dispatch_msa_subclass / _dispatch_allomorph_subclass: MVP live-path gating.
- _walk_lex_entry_closure: shared owned-child closure helper is exposed.

execute_action + _walk_lex_entry_closure are LCM-bound (lazy `import SIL.LCModel`)
and are exercised only under a live host / the integration suite; these tests
assert on the planning path and the two pure-Python subclass dispatchers.

GUID handling: `categories._guid_str_from` reads a lowercase `.guid` attribute
host-free, so the fakes below expose lowercase `.guid` directly (matching the
pattern in the sibling Phase 3c test files) — no monkeypatch is required.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from gramtrans.Lib import categories
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
# Fakes (duck-typed, lowercase .guid so _guid_str_from works host-free)
# ============================================================================

class _MorphType:
    def __init__(self, is_affix: bool = True) -> None:
        self.IsAffixType = is_affix


class _LexForm:
    def __init__(self, is_affix: bool = True, with_morphtype: bool = True) -> None:
        self.MorphTypeRA = _MorphType(is_affix) if with_morphtype else None


class _POS:
    def __init__(self, guid: str) -> None:
        self.guid = guid


class _Slot:
    def __init__(self, guid: str) -> None:
        self.guid = guid


class _MSA:
    """Affix MSA fake. `slots` populates SlotsRC; POS fields drive deps."""

    def __init__(self, guid: str, class_name: str = "MoInflAffMsa",
                 pos: "_POS | None" = None, from_pos=None, to_pos=None,
                 slots=()) -> None:
        self.guid = guid
        self.ClassName = class_name
        self.PartOfSpeechRA = pos
        self.FromPartOfSpeechRA = from_pos
        self.ToPartOfSpeechRA = to_pos
        self.SlotsRC = list(slots)


class _EntryRef:
    def __init__(self, comp=(), prim=()) -> None:
        self.ComponentLexemesRS = list(comp)
        self.PrimaryLexemesRS = list(prim)


class _Entry:
    """Duck-typed ILexEntry fake."""

    def __init__(self, guid: str, is_affix: bool = True,
                 with_morphtype: bool = True, msas=(), refs=(),
                 catalog_source_id=None) -> None:
        self.guid = guid
        self.LexemeFormOA = _LexForm(is_affix, with_morphtype)
        self.MorphoSyntaxAnalysesOC = list(msas)
        self.EntryRefsOS = list(refs)
        self.SensesOS = []
        if catalog_source_id is not None:
            self.CatalogSourceId = catalog_source_id


def _handle(entries=()):
    """Build a source/target handle whose entries live at
    Cache.LangProject.LexDbOA.EntriesOC (the shape _iter_lex_entries walks)."""
    return SimpleNamespace(
        Cache=SimpleNamespace(
            LangProject=SimpleNamespace(
                LexDbOA=SimpleNamespace(EntriesOC=list(entries))
            )
        )
    )


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


def _attach_binding_maps(ctx):
    """Mirror preview.build_run_plan: attach empty stash dicts and return them."""
    msa_map: dict = {}
    ref_map: dict = {}
    object.__setattr__(ctx, "_msa_slot_bindings", msa_map)
    object.__setattr__(ctx, "_lexentry_ref_bindings", ref_map)
    return msa_map, ref_map


_BUNDLE = categories.for_category(GrammarCategory.AFFIXES)


# ============================================================================
# Bundle shape
# ============================================================================

def test_bundle_exposes_five_callbacks() -> None:
    assert set(_BUNDLE) == {
        "enumerate_source", "dependencies", "required_writing_systems",
        "plan_action", "execute_action",
    }
    for key in _BUNDLE:
        assert callable(_BUNDLE[key])


# ============================================================================
# T021 — enumerate_source
# ============================================================================

def test_enumerate_source_returns_only_affix_entries() -> None:
    aff1 = _Entry("aff-1", is_affix=True)
    aff2 = _Entry("aff-2", is_affix=True)
    stem = _Entry("stem-1", is_affix=False)
    src = _handle([aff1, stem, aff2])
    ctx = _ctx(src, _handle([]))

    items = list(_BUNDLE["enumerate_source"](ctx, None))

    assert [e.guid for e in items] == ["aff-1", "aff-2"]


def test_enumerate_source_skips_entries_without_morphtype() -> None:
    good = _Entry("aff-1", is_affix=True)
    degenerate = _Entry("aff-nomt", is_affix=True, with_morphtype=False)
    src = _handle([good, degenerate])
    ctx = _ctx(src, _handle([]))

    items = list(_BUNDLE["enumerate_source"](ctx, None))

    assert [e.guid for e in items] == ["aff-1"]


def test_enumerate_source_excludes_gold_affixes() -> None:
    user_aff = _Entry("aff-user", is_affix=True)
    gold_aff = _Entry("aff-gold", is_affix=True, catalog_source_id="msa:xyz")
    src = _handle([user_aff, gold_aff])
    ctx = _ctx(src, _handle([]))

    items = list(_BUNDLE["enumerate_source"](ctx, None))

    assert [e.guid for e in items] == ["aff-user"]


def test_enumerate_source_none_selection_transfers_all() -> None:
    src = _handle([_Entry("a"), _Entry("b")])
    ctx = _ctx(src, _handle([]))

    items = list(_BUNDLE["enumerate_source"](ctx, None))

    assert {e.guid for e in items} == {"a", "b"}


def test_enumerate_source_selection_picks_filter_subset() -> None:
    src = _handle([_Entry("a"), _Entry("b"), _Entry("c")])
    ctx = _ctx(src, _handle([]))
    sel = Selection(
        categories={GrammarCategory.AFFIXES: True},
        leaf_item_picks={GrammarCategory.AFFIXES: frozenset({"b"})},
    )

    items = list(_BUNDLE["enumerate_source"](ctx, sel))

    assert [e.guid for e in items] == ["b"]


def test_enumerate_source_empty_picks_transfers_none() -> None:
    src = _handle([_Entry("a"), _Entry("b")])
    ctx = _ctx(src, _handle([]))
    sel = Selection(
        categories={GrammarCategory.AFFIXES: True},
        leaf_item_picks={GrammarCategory.AFFIXES: frozenset()},
    )

    assert list(_BUNDLE["enumerate_source"](ctx, sel)) == []


def test_enumerate_source_none_source_returns_empty() -> None:
    ctx = _ctx(None, _handle([]))
    assert list(_BUNDLE["enumerate_source"](ctx, None)) == []


# ============================================================================
# T022 — dependencies
# ============================================================================

def test_dependencies_yields_pos_edge_for_infl_affix() -> None:
    entry = _Entry("aff-1", msas=[_MSA("m-1", pos=_POS("pos-verb"))])
    deps = tuple(_BUNDLE["dependencies"](entry))
    assert deps == ((GrammarCategory.GRAM_CATEGORIES, "pos-verb"),)


def test_dependencies_uses_gram_categories_not_pos() -> None:
    entry = _Entry("aff-1", msas=[_MSA("m-1", pos=_POS("pos-verb"))])
    cats = {c for (c, _g) in _BUNDLE["dependencies"](entry)}
    assert cats == {GrammarCategory.GRAM_CATEGORIES}
    assert GrammarCategory.POS not in cats


def test_dependencies_covers_from_and_to_pos_of_deriv_msa() -> None:
    entry = _Entry(
        "aff-deriv",
        msas=[_MSA("m-d", class_name="MoDerivAffMsa",
                   from_pos=_POS("pos-noun"), to_pos=_POS("pos-verb"))],
    )
    deps = list(_BUNDLE["dependencies"](entry))
    assert (GrammarCategory.GRAM_CATEGORIES, "pos-noun") in deps
    assert (GrammarCategory.GRAM_CATEGORIES, "pos-verb") in deps


def test_dependencies_dedupes_repeated_pos() -> None:
    pos = _POS("pos-verb")
    entry = _Entry("aff-1", msas=[_MSA("m-1", pos=pos), _MSA("m-2", pos=pos)])
    deps = list(_BUNDLE["dependencies"](entry))
    assert deps == [(GrammarCategory.GRAM_CATEGORIES, "pos-verb")]


def test_dependencies_empty_when_no_pos() -> None:
    entry = _Entry("aff-nopos", msas=[_MSA("m-1", pos=None)])
    assert tuple(_BUNDLE["dependencies"](entry)) == ()


# ============================================================================
# T023 — required_writing_systems
# ============================================================================

def test_required_writing_systems_is_empty() -> None:
    entry = _Entry("aff-1", msas=[_MSA("m-1", pos=_POS("pos-verb"))])
    assert tuple(_BUNDLE["required_writing_systems"](entry)) == ()


# ============================================================================
# T024-T026 — plan_action
# ============================================================================

def test_plan_action_planned_for_infl_aff_msa() -> None:
    entry = _Entry("aff-1", msas=[_MSA("m-1", "MoInflAffMsa", pos=_POS("pos-verb"))])
    ctx = _ctx(_handle([entry]), _handle([]))
    _attach_binding_maps(ctx)

    result = _BUNDLE["plan_action"](entry, ctx, WSMapping())

    assert isinstance(result, PlannedAction)
    assert result.category == GrammarCategory.AFFIXES
    assert result.source_guid == "aff-1"
    # GUID preserved (E2 entry created via Create(Guid)).
    assert result.intended_target_guid == "aff-1"


def test_plan_action_planned_for_stem_msa_affix() -> None:
    """An affix entry whose MSA is a MoStemMsa still yields a PlannedAction
    (MoStemMsa is the second MVP live path)."""
    entry = _Entry("aff-stem", msas=[_MSA("m-s", "MoStemMsa", pos=_POS("pos-noun"))])
    ctx = _ctx(_handle([entry]), _handle([]))
    _attach_binding_maps(ctx)

    result = _BUNDLE["plan_action"](entry, ctx, WSMapping())

    assert isinstance(result, PlannedAction)
    assert result.intended_target_guid == "aff-stem"


def test_plan_action_can_be_called_positionally_and_by_keyword() -> None:
    entry = _Entry("aff-kw", msas=[_MSA("m-1", pos=_POS("pos-verb"))])
    ctx = _ctx(_handle([entry]), _handle([]))
    _attach_binding_maps(ctx)

    kw = _BUNDLE["plan_action"](piece=entry, context=ctx, ws_mapping=WSMapping())
    assert isinstance(kw, PlannedAction)
    assert kw.source_guid == "aff-kw"


def test_plan_action_gold_affix_skipped() -> None:
    entry = _Entry("aff-gold", catalog_source_id="msa:catalog",
                   msas=[_MSA("m-1", pos=_POS("pos-verb"))])
    ctx = _ctx(_handle([entry]), _handle([]))
    _attach_binding_maps(ctx)

    result = _BUNDLE["plan_action"](entry, ctx, WSMapping())

    assert isinstance(result, Skip)
    assert result.reason == SkipReason.GOLD_INVIOLABLE
    assert result.source_guid == "aff-gold"


def test_plan_action_already_present_by_guid_skipped() -> None:
    src_entry = _Entry("aff-dup", msas=[_MSA("m-1", pos=_POS("pos-verb"))])
    tgt_entry = _Entry("aff-dup", msas=[_MSA("m-1", pos=_POS("pos-verb"))])
    ctx = _ctx(_handle([src_entry]), _handle([tgt_entry]))
    _attach_binding_maps(ctx)

    result = _BUNDLE["plan_action"](src_entry, ctx, WSMapping())

    assert isinstance(result, Skip)
    assert result.reason == SkipReason.ALREADY_PRESENT_BY_GUID
    assert result.source_guid == "aff-dup"


# ============================================================================
# T024 stash — MSA->slot + EntryRef binding side effects
# ============================================================================

def test_plan_action_stashes_msa_slot_binding() -> None:
    msa = _MSA("m-bound", pos=_POS("pos-verb"),
               slots=[_Slot("slot-a"), _Slot("slot-b")])
    entry = _Entry("aff-bound", msas=[msa])
    ctx = _ctx(_handle([entry]), _handle([]))
    msa_map, _ref_map = _attach_binding_maps(ctx)

    result = _BUNDLE["plan_action"](entry, ctx, WSMapping())

    assert isinstance(result, PlannedAction)
    assert msa_map == {"m-bound": ["slot-a", "slot-b"]}


def test_plan_action_unbound_affix_stashes_no_binding() -> None:
    """T040 invariant: an MSA with an empty SlotsRC produces NO binding."""
    entry = _Entry("aff-unbound",
                   msas=[_MSA("m-ro", pos=_POS("pos-verb"), slots=[])])
    ctx = _ctx(_handle([entry]), _handle([]))
    msa_map, _ref_map = _attach_binding_maps(ctx)

    result = _BUNDLE["plan_action"](entry, ctx, WSMapping())

    assert isinstance(result, PlannedAction)
    assert msa_map == {}


def test_plan_action_stashes_entry_ref_bindings() -> None:
    ref = _EntryRef(comp=[_Slot("comp-1")], prim=[_Slot("prim-1")])
    entry = _Entry("aff-ref", msas=[_MSA("m-1", pos=_POS("pos-verb"))], refs=[ref])
    ctx = _ctx(_handle([entry]), _handle([]))
    _msa_map, ref_map = _attach_binding_maps(ctx)

    result = _BUNDLE["plan_action"](entry, ctx, WSMapping())

    assert isinstance(result, PlannedAction)
    assert ref_map == {
        "aff-ref": {"ComponentLexemesRS": ["comp-1"], "PrimaryLexemesRS": ["prim-1"]}
    }


def test_plan_action_entry_ref_with_empty_seqs_stashes_no_binding() -> None:
    entry = _Entry("aff-emptyref", msas=[_MSA("m-1", pos=_POS("pos-verb"))],
                   refs=[_EntryRef(comp=[], prim=[])])
    ctx = _ctx(_handle([entry]), _handle([]))
    _msa_map, ref_map = _attach_binding_maps(ctx)

    _BUNDLE["plan_action"](entry, ctx, WSMapping())

    assert ref_map == {}


# ============================================================================
# T028 — MSA / allomorph subclass dispatch (execute-time gating, host-free)
# ============================================================================

def test_dispatch_msa_subclass_mvp_live_paths() -> None:
    assert categories._dispatch_msa_subclass("MoInflAffMsa") == "MoInflAffMsa"
    assert categories._dispatch_msa_subclass("MoStemMsa") == "MoStemMsa"


def test_dispatch_msa_subclass_recognised_deferred_paths() -> None:
    # Recognised (wired) but unverified against a live corpus.
    assert categories._dispatch_msa_subclass("MoDerivAffMsa") == "MoDerivAffMsa"
    assert (categories._dispatch_msa_subclass("MoUnclassifiedAffixMsa")
            == "MoUnclassifiedAffixMsa")


def test_dispatch_msa_subclass_unknown_returns_none() -> None:
    assert categories._dispatch_msa_subclass("MoSomethingElse") is None
    assert categories._dispatch_msa_subclass(None) is None


def test_dispatch_allomorph_subclass() -> None:
    assert categories._dispatch_allomorph_subclass("MoAffixAllomorph") == "MoAffixAllomorph"
    assert categories._dispatch_allomorph_subclass("MoStemAllomorph") == "MoStemAllomorph"
    assert categories._dispatch_allomorph_subclass("MoWhatever") is None
    assert categories._dispatch_allomorph_subclass(None) is None


# ============================================================================
# T024 — closure helper is exposed (LCM-bound; live write covered by integration)
# ============================================================================

def test_walk_lex_entry_closure_is_exposed_helper() -> None:
    assert callable(categories._walk_lex_entry_closure)


def test_execute_action_returns_none_when_source_entry_missing() -> None:
    """execute_action re-resolves the source entry by GUID; when it is absent
    the closure is never reached (no SIL.LCModel import) and it returns None."""
    action = PlannedAction(
        category=GrammarCategory.AFFIXES,
        source_guid="does-not-exist",
        intended_target_guid="does-not-exist",
        summary="x",
    )
    ctx = _ctx(_handle([]), _handle([]))
    assert _BUNDLE["execute_action"](action, ctx, WSMapping(), tag=None) is None


@pytest.mark.integration
def test_affix_execute_requires_lcm() -> None:
    pytest.skip("LCM required; live affix closure covered by integration suite.")

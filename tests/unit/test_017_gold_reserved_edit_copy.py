"""Unit tests for spec 017: GOLD_RESERVED edit-copy (fill-gaps on APBG items).

Test matrix per spec:
  (a) GOLD -> Skip(GOLD_INVIOLABLE)
  (b) present + equal -> Skip(ALREADY_PRESENT_BY_GUID)
  (c) present + edited -> PlannedOverwrite(write_mode="merge")
  (d) absent -> PlannedAction (ADD, unchanged from today)
  (e) present + conflict (all non-empty-differ, no gaps) -> Skip(ALREADY_PRESENT_BY_GUID) + conflict detail
  (f) present + mixed (gap + conflict) -> PlannedOverwrite for gap slots, conflict in summary
  (g) IsProtected + non-GOLD -> Skip(ALREADY_PRESENT_BY_GUID) with IsProtected note

Coverage: 7 GOLD_RESERVED categories x 7 cases = 49 cells minimum.
Shared helper _plan_gold_reserved_edit is exercised through each category's
plan_action function.

Phonological_features is tested separately because it routes through
_phonology_simple_plan (filtered to GOLD_RESERVED branch only).
"""
from __future__ import annotations

import pytest

from gramtrans.Lib import categories
from gramtrans.Lib.models import (
    GrammarCategory,
    PlannedAction,
    PlannedOverwrite,
    RunContext,
    Selection,
    Skip,
    SkipReason,
    WSMapping,
)


# ============================================================================
# Fake multistring + WS helpers
# ============================================================================

class _FakeTsString:
    def __init__(self, text):
        self.Text = text or None


class _FakeMultiString:
    """Fake ICmMultiString: per-handle text storage."""
    def __init__(self, data: dict):
        # data: {ws_handle: text_or_None}
        self._data = dict(data)

    def get_String(self, ws_handle):
        return _FakeTsString(self._data.get(ws_handle))


class _FakeWsObj:
    def __init__(self, ws_id, handle):
        self.Id = ws_id
        self.Handle = handle


class _FakeWritingSystems:
    def __init__(self, ws_list):
        self._ws = list(ws_list)

    def GetAll(self):
        return list(self._ws)


# Writing-system handles used throughout.
WS_EN = 100
WS_FR = 101
WS_DE = 102

_WS_LIST = [
    _FakeWsObj("en", WS_EN),
    _FakeWsObj("fr", WS_FR),
]


# ============================================================================
# Fake LCM objects with multistring fields
# ============================================================================

class _FakeItem:
    """CmPossibility-shaped item with Name/Abbreviation/Description multistrings."""
    def __init__(self, guid, catalog_source_id="", is_protected=False,
                 name_data=None, abbr_data=None, desc_data=None):
        self.guid = guid
        self.Guid = guid
        self.CatalogSourceId = catalog_source_id
        self.IsProtected = is_protected
        self.Name = _FakeMultiString(name_data or {})
        self.Abbreviation = _FakeMultiString(abbr_data or {})
        self.Description = _FakeMultiString(desc_data or {})

    @property
    def concrete(self):
        return self


def _make_item(guid, catalog_source_id="", is_protected=False,
               name_en=None, name_fr=None, abbr_en=None, desc_en=None):
    return _FakeItem(
        guid=guid,
        catalog_source_id=catalog_source_id,
        is_protected=is_protected,
        name_data={WS_EN: name_en, WS_FR: name_fr} if (name_en or name_fr) else {},
        abbr_data={WS_EN: abbr_en} if abbr_en else {},
        desc_data={WS_EN: desc_en} if desc_en else {},
    )


# ============================================================================
# Fake project helpers
# ============================================================================

class _FakeGramCatOps:
    def __init__(self, items=()):
        self._items = list(items)

    def GetAll(self, recursive=True):
        return list(self._items)


class _FakeInflFeatureOps:
    def __init__(self, features=()):
        self._features = list(features)

    def FeatureGetAll(self):
        return list(self._features)


class _FakeList:
    """CmPossibilityList-shaped owning collection."""
    def __init__(self, items=()):
        self.PossibilitiesOS = list(items)
        for i in items:
            i.Owner = self


class _FakeLexDb:
    def __init__(self, variants=(), complex_forms=()):
        vl = _FakeList(variants)
        cl = _FakeList(complex_forms)
        self.VariantEntryTypesOA = vl
        self.ComplexEntryTypesOA = cl


class _FakeLangProject:
    def __init__(self, lex_db=None, sem_dom_list=None):
        self.LexDbOA = lex_db or _FakeLexDb()
        self.SemanticDomainListOA = sem_dom_list or _FakeList()


class _FakeCache:
    def __init__(self, lp=None):
        self.LangProject = lp or _FakeLangProject()


class _FakePhonFeatOps:
    def __init__(self, items=()):
        self._items = list(items)

    def GetAll(self):
        return list(self._items)


class _FakeSrcProject:
    """Source project with WritingSystems.GetAll() support."""
    def __init__(self, gram_cats=(), infl_feats=(), variants=(), complex_forms=(),
                 sem_doms=(), phon_feats=(), ws_list=None):
        self.POS = _FakeGramCatOps(gram_cats)
        self.InflectionFeatures = _FakeInflFeatureOps(infl_feats)
        lex_db = _FakeLexDb(variants=variants, complex_forms=complex_forms)
        lp = _FakeLangProject(lex_db=lex_db, sem_dom_list=_FakeList(sem_doms))
        self.Cache = _FakeCache(lp)
        self.PhonFeatures = _FakePhonFeatOps(phon_feats)
        self.WritingSystems = _FakeWritingSystems(ws_list or _WS_LIST)


class _FakeTgtProject:
    """Target project WITHOUT WritingSystems (targets don't need WS for plan)."""
    def __init__(self, gram_cats=(), infl_feats=(), variants=(), complex_forms=(),
                 sem_doms=(), phon_feats=()):
        self.POS = _FakeGramCatOps(gram_cats)
        self.InflectionFeatures = _FakeInflFeatureOps(infl_feats)
        lex_db = _FakeLexDb(variants=variants, complex_forms=complex_forms)
        lp = _FakeLangProject(lex_db=lex_db, sem_dom_list=_FakeList(sem_doms))
        self.Cache = _FakeCache(lp)
        self.PhonFeatures = _FakePhonFeatOps(phon_feats)


def _ctx(src, tgt) -> RunContext:
    return RunContext(
        source_handle=src, source_project_name="Src", source_project_path="/s",
        target_handle=tgt, target_project_name="Tgt", target_project_path="/t",
        run_id="GT-017-TEST", started_at="2026-07-05T01:00:00",
    )


WSM = WSMapping(entries=())


# ============================================================================
# Fixture: patch _guid_str_from to use .guid on fakes
# ============================================================================

@pytest.fixture(autouse=True)
def _patch_guid(monkeypatch):
    monkeypatch.setattr(categories, "_guid_str_from", lambda o: o.guid)


# ============================================================================
# Helper: call plan_action for each category
# ============================================================================

def _plan_gram_cat(piece, src, tgt):
    return categories.gram_categories_plan_action(
        piece, _ctx(src, tgt), WSM
    )


def _plan_infl_feat(piece, src, tgt):
    return categories.inflection_features_plan_action(
        piece, _ctx(src, tgt), WSM
    )


def _plan_variant(piece, src, tgt):
    return categories.variant_types_plan_action(
        piece, _ctx(src, tgt), WSM
    )


def _plan_complex(piece, src, tgt):
    return categories.complex_form_types_plan_action(
        piece, _ctx(src, tgt), WSM
    )


def _plan_sem_dom(piece, src, tgt):
    return categories.semantic_domains_plan_action(
        piece, _ctx(src, tgt), WSM
    )


def _plan_phon_feat(piece, src, tgt):
    return categories.phonological_features_plan_action(
        piece, _ctx(src, tgt), WSM
    )


# Map category to (plan_fn, src_kwarg, tgt_kwarg)
_CATEGORY_PLAN_FNS = [
    (GrammarCategory.GRAM_CATEGORIES, _plan_gram_cat, "gram_cats", "gram_cats"),
    (GrammarCategory.INFLECTION_FEATURES, _plan_infl_feat, "infl_feats", "infl_feats"),
    (GrammarCategory.VARIANT_TYPES, _plan_variant, "variants", "variants"),
    (GrammarCategory.COMPLEX_FORM_TYPES, _plan_complex, "complex_forms", "complex_forms"),
    (GrammarCategory.SEMANTIC_DOMAINS, _plan_sem_dom, "sem_doms", "sem_doms"),
    (GrammarCategory.PHONOLOGICAL_FEATURES, _plan_phon_feat, "phon_feats", "phon_feats"),
]


def _make_src_with(kwarg, items):
    return _FakeSrcProject(**{kwarg: items})


def _make_tgt_with(kwarg, items):
    return _FakeTgtProject(**{kwarg: items})


# ============================================================================
# (a) GOLD -> Skip(GOLD_INVIOLABLE)
# ============================================================================

@pytest.mark.parametrize("category,plan_fn,src_kw,tgt_kw", _CATEGORY_PLAN_FNS)
def test_a_gold_item_skips_inviolable(category, plan_fn, src_kw, tgt_kw):
    """Case (a): GOLD item (non-empty CatalogSourceId) present in target ->
    GOLD_INVIOLABLE (never edited). Item placed IN the target so GRAM_CATEGORIES,
    which now materializes ABSENT GOLD dependencies (2026-07-06), still skips a
    PRESENT one; the absent-materialize case is covered in
    test_categories_gram_categories."""
    item = _make_item("gold-001", catalog_source_id="fPerson")
    src = _make_src_with(src_kw, [item])
    tgt = _make_tgt_with(tgt_kw, [item])
    result = plan_fn(item, src, tgt)
    assert isinstance(result, Skip), f"{category}: expected Skip, got {result!r}"
    assert result.reason == SkipReason.GOLD_INVIOLABLE
    assert result.category == category


# ============================================================================
# (b) present + equal -> Skip(ALREADY_PRESENT_BY_GUID)
# ============================================================================

@pytest.mark.parametrize("category,plan_fn,src_kw,tgt_kw", _CATEGORY_PLAN_FNS)
def test_b_present_equal_skips_apbg(category, plan_fn, src_kw, tgt_kw):
    """Case (b): present in target, all WS slots equal -> ALREADY_PRESENT_BY_GUID."""
    src_item = _make_item("eq-001", name_en="Verb", abbr_en="v", desc_en="A verb")
    tgt_item = _make_item("eq-001", name_en="Verb", abbr_en="v", desc_en="A verb")
    src = _make_src_with(src_kw, [src_item])
    tgt = _make_tgt_with(tgt_kw, [tgt_item])
    result = plan_fn(src_item, src, tgt)
    assert isinstance(result, Skip), f"{category}: expected Skip, got {result!r}"
    assert result.reason == SkipReason.ALREADY_PRESENT_BY_GUID


# ============================================================================
# (c) present + edited (gap) -> PlannedOverwrite(write_mode="merge")
# ============================================================================

@pytest.mark.parametrize("category,plan_fn,src_kw,tgt_kw", _CATEGORY_PLAN_FNS)
def test_c_present_with_gap_emits_planned_overwrite(category, plan_fn, src_kw, tgt_kw):
    """Case (c): present in target; source has WS slot target is missing -> PlannedOverwrite(merge)."""
    # Source has FR name, target is missing FR name.
    src_item = _make_item("gap-001", name_en="Verb", name_fr="Verbe")
    tgt_item = _make_item("gap-001", name_en="Verb")  # FR slot empty
    src = _make_src_with(src_kw, [src_item])
    tgt = _make_tgt_with(tgt_kw, [tgt_item])
    result = plan_fn(src_item, src, tgt)
    assert isinstance(result, PlannedOverwrite), (
        f"{category}: expected PlannedOverwrite, got {result!r}"
    )
    assert result.write_mode == "merge"
    assert result.source_guid == "gap-001"
    assert result.target_guid == "gap-001"
    assert result.match_via == "guid"
    assert result.category == category


# ============================================================================
# (d) absent -> PlannedAction (ADD)
# ============================================================================

@pytest.mark.parametrize("category,plan_fn,src_kw,tgt_kw", _CATEGORY_PLAN_FNS)
def test_d_absent_emits_planned_action(category, plan_fn, src_kw, tgt_kw):
    """Case (d): GUID not in target -> PlannedAction (ADD), unchanged behavior."""
    item = _make_item("new-001")
    src = _make_src_with(src_kw, [item])
    tgt = _make_tgt_with(tgt_kw, [])
    result = plan_fn(item, src, tgt)
    assert isinstance(result, PlannedAction), f"{category}: expected PlannedAction, got {result!r}"
    assert result.source_guid == "new-001"
    assert result.category == category


# ============================================================================
# (e) present + conflict (no gaps) -> Skip(ALREADY_PRESENT_BY_GUID) + detail
# ============================================================================

@pytest.mark.parametrize("category,plan_fn,src_kw,tgt_kw", _CATEGORY_PLAN_FNS)
def test_e_present_conflict_no_gaps_skips(category, plan_fn, src_kw, tgt_kw):
    """Case (e): source and target both have EN name, but different text -> conflict -> Skip."""
    src_item = _make_item("conf-001", name_en="Verb")
    tgt_item = _make_item("conf-001", name_en="VerbDifferent")
    src = _make_src_with(src_kw, [src_item])
    tgt = _make_tgt_with(tgt_kw, [tgt_item])
    result = plan_fn(src_item, src, tgt)
    assert isinstance(result, Skip), f"{category}: expected Skip for all-conflict, got {result!r}"
    assert result.reason == SkipReason.ALREADY_PRESENT_BY_GUID
    # Detail should mention conflicts.
    assert "conflict" in result.detail.lower() or "vs" in result.detail.lower(), (
        f"{category}: conflict detail missing from {result.detail!r}"
    )


# ============================================================================
# (f) present + mixed (gap + conflict) -> PlannedOverwrite + conflict noted
# ============================================================================

@pytest.mark.parametrize("category,plan_fn,src_kw,tgt_kw", _CATEGORY_PLAN_FNS)
def test_f_present_mixed_gap_conflict_emits_overwrite_with_note(
    category, plan_fn, src_kw, tgt_kw
):
    """Case (f): EN name conflicts (both non-empty, differ); FR name is gap (empty in target).
    -> PlannedOverwrite for the FR gap; EN conflict noted in summary.
    """
    src_item = _make_item("mix-001", name_en="Verb", name_fr="Verbe")
    # Target has EN (different) but no FR.
    tgt_item = _make_item("mix-001", name_en="VerbDifferent")
    src = _make_src_with(src_kw, [src_item])
    tgt = _make_tgt_with(tgt_kw, [tgt_item])
    result = plan_fn(src_item, src, tgt)
    assert isinstance(result, PlannedOverwrite), (
        f"{category}: expected PlannedOverwrite for mixed case, got {result!r}"
    )
    assert result.write_mode == "merge"
    # Conflict should appear in summary.
    assert "conflict" in result.summary.lower() or "vs" in result.summary.lower(), (
        f"{category}: conflict note absent from summary {result.summary!r}"
    )
    # Gap fill should appear in summary.
    assert "Verbe" in result.summary or "fr" in result.summary.lower(), (
        f"{category}: gap fill (FR name) absent from summary {result.summary!r}"
    )


# ============================================================================
# (g) IsProtected + non-GOLD -> Skip(ALREADY_PRESENT_BY_GUID) with note
# ============================================================================

@pytest.mark.parametrize("category,plan_fn,src_kw,tgt_kw", _CATEGORY_PLAN_FNS)
def test_g_is_protected_non_gold_skips_with_note(category, plan_fn, src_kw, tgt_kw):
    """Case (g): non-GOLD item in target with IsProtected=True -> Skip + IsProtected note."""
    src_item = _make_item("prot-001", name_en="Verb", name_fr="Verbe")  # has gap
    tgt_item = _make_item("prot-001", is_protected=True, name_en="Verb")
    src = _make_src_with(src_kw, [src_item])
    tgt = _make_tgt_with(tgt_kw, [tgt_item])
    result = plan_fn(src_item, src, tgt)
    assert isinstance(result, Skip), (
        f"{category}: expected Skip for IsProtected, got {result!r}"
    )
    assert result.reason == SkipReason.ALREADY_PRESENT_BY_GUID
    assert "isprotected" in result.detail.lower() or "protected" in result.detail.lower(), (
        f"{category}: IsProtected note absent from {result.detail!r}"
    )


# ============================================================================
# Phonological_features specific: other phonology cats NOT affected
# ============================================================================

def test_phonemes_plan_action_apbg_unchanged():
    """PHONEMES is MULTI_INSTANCE; _phonology_simple_plan must NOT route through edit helper."""
    class _FakePhonemes:
        def GetAll(self):
            return [_make_item("ph-001")]

    src = type("Src", (), {
        "Phonemes": _FakePhonemes(),
        "WritingSystems": _FakeWritingSystems(_WS_LIST),
    })()
    tgt = type("Tgt", (), {
        "Phonemes": _FakePhonemes(),
    })()
    result = categories.phonemes_plan_action(_make_item("ph-001"), _ctx(src, tgt), WSM)
    # Should be plain ALREADY_PRESENT_BY_GUID skip (not a merge overwrite).
    assert isinstance(result, Skip)
    assert result.reason == SkipReason.ALREADY_PRESENT_BY_GUID
    # The detail should NOT mention conflicts or gaps.
    assert "conflict" not in result.detail.lower()


def test_phon_feat_gold_skips_before_edit_check():
    """PHONOLOGICAL_FEATURES: GOLD item skips before any edit-detection."""
    item = _make_item("phf-gold", catalog_source_id="fVoiced", name_en="Voiced", name_fr="Voise")
    src = _FakeSrcProject(phon_feats=[item])
    tgt = _FakeTgtProject(phon_feats=[_make_item("phf-gold", name_en="Voiced")])
    result = categories.phonological_features_plan_action(item, _ctx(src, tgt), WSM)
    assert isinstance(result, Skip)
    assert result.reason == SkipReason.GOLD_INVIOLABLE


def test_phon_feat_present_with_gap_emits_overwrite():
    """PHONOLOGICAL_FEATURES: present custom item with FR gap -> PlannedOverwrite(merge)."""
    item = _make_item("phf-001", name_en="Voiced", name_fr="Voise")
    src = _FakeSrcProject(phon_feats=[item])
    tgt_item = _make_item("phf-001", name_en="Voiced")  # FR gap
    tgt = _FakeTgtProject(phon_feats=[tgt_item])
    result = categories.phonological_features_plan_action(item, _ctx(src, tgt), WSM)
    assert isinstance(result, PlannedOverwrite)
    assert result.write_mode == "merge"
    assert result.category == GrammarCategory.PHONOLOGICAL_FEATURES


# ============================================================================
# Idempotency: absent item with no WS gap = Skip (not spurious merge)
# ============================================================================

def test_no_ws_info_falls_back_to_skip():
    """When source has no WritingSystems.GetAll(), helper returns conservative Skip."""
    item = _make_item("nows-001")
    # Source without WritingSystems attribute at all.
    src_no_ws = type("SrcNoWS", (), {"POS": _FakeGramCatOps([item])})()
    tgt_item = _make_item("nows-001")
    tgt = _FakeTgtProject(gram_cats=[tgt_item])
    result = categories.gram_categories_plan_action(item, _ctx(src_no_ws, tgt), WSM)
    assert isinstance(result, Skip)
    assert result.reason == SkipReason.ALREADY_PRESENT_BY_GUID


# ============================================================================
# Helper isolation: _plan_gold_reserved_edit directly
# ============================================================================

def test_helper_gold_check_first():
    """_plan_gold_reserved_edit: GOLD check fires before target lookup."""
    gold = _make_item("g-001", catalog_source_id="fX", name_en="Foo")
    # Target iter would find the item — but GOLD check must fire first.
    def _target_iter(tgt):
        return [_make_item("g-001")]

    src = _FakeSrcProject()
    result = categories._plan_gold_reserved_edit(
        gold, GrammarCategory.GRAM_CATEGORIES, _ctx(src, object()), _target_iter
    )
    assert isinstance(result, Skip)
    assert result.reason == SkipReason.GOLD_INVIOLABLE


def test_helper_absent_returns_none():
    """_plan_gold_reserved_edit: absent item returns None (caller emits Add)."""
    item = _make_item("new-999")
    def _target_iter(tgt):
        return []

    src = _FakeSrcProject()
    result = categories._plan_gold_reserved_edit(
        item, GrammarCategory.GRAM_CATEGORIES, _ctx(src, object()), _target_iter
    )
    assert result is None


def test_helper_equal_slots_returns_skip():
    """_plan_gold_reserved_edit: all WS slots equal -> Skip(ALREADY_PRESENT_BY_GUID)."""
    item = _make_item("eq-999", name_en="Verb", name_fr="Verbe")
    tgt_item = _make_item("eq-999", name_en="Verb", name_fr="Verbe")

    def _target_iter(tgt):
        return [tgt_item]

    src = _FakeSrcProject(gram_cats=[item])
    result = categories._plan_gold_reserved_edit(
        item, GrammarCategory.GRAM_CATEGORIES, _ctx(src, object()), _target_iter
    )
    assert isinstance(result, Skip)
    assert result.reason == SkipReason.ALREADY_PRESENT_BY_GUID
    assert "equal" in result.detail.lower()


def test_helper_gap_returns_planned_overwrite():
    """_plan_gold_reserved_edit: gap slots -> PlannedOverwrite(merge)."""
    item = _make_item("gp-999", name_en="Verb", name_fr="Verbe")
    tgt_item = _make_item("gp-999", name_en="Verb")  # FR gap

    def _target_iter(tgt):
        return [tgt_item]

    src = _FakeSrcProject(gram_cats=[item])
    result = categories._plan_gold_reserved_edit(
        item, GrammarCategory.GRAM_CATEGORIES, _ctx(src, object()), _target_iter
    )
    assert isinstance(result, PlannedOverwrite)
    assert result.write_mode == "merge"
    assert "Verbe" in result.summary


def test_helper_all_conflict_no_gaps_returns_skip_with_conflict():
    """_plan_gold_reserved_edit: all slots differ, none empty -> Skip + conflict detail."""
    item = _make_item("cf-999", name_en="NewVerb")
    tgt_item = _make_item("cf-999", name_en="OldVerb")

    def _target_iter(tgt):
        return [tgt_item]

    src = _FakeSrcProject(gram_cats=[item])
    result = categories._plan_gold_reserved_edit(
        item, GrammarCategory.GRAM_CATEGORIES, _ctx(src, object()), _target_iter
    )
    assert isinstance(result, Skip)
    assert result.reason == SkipReason.ALREADY_PRESENT_BY_GUID
    assert "conflict" in result.detail.lower()


def test_helper_mixed_gap_and_conflict():
    """_plan_gold_reserved_edit: EN conflicts + FR gap -> merge action with conflict note."""
    item = _make_item("mx-999", name_en="NewVerb", name_fr="Verbe")
    tgt_item = _make_item("mx-999", name_en="OldVerb")  # EN conflict, FR gap

    def _target_iter(tgt):
        return [tgt_item]

    src = _FakeSrcProject(gram_cats=[item])
    result = categories._plan_gold_reserved_edit(
        item, GrammarCategory.GRAM_CATEGORIES, _ctx(src, object()), _target_iter
    )
    assert isinstance(result, PlannedOverwrite)
    assert result.write_mode == "merge"
    assert "conflict" in result.summary.lower()
    assert "Verbe" in result.summary  # gap fill present


# ============================================================================
# merge_preview defect fix: _find_target_inflection_feature_by_guid
# ============================================================================

def test_merge_preview_inflection_feature_finder_uses_feature_get_all():
    """Regression: merge_preview._find_target_inflection_feature_by_guid must
    call FeatureGetAll(), not InflectionClassGetAll() (spec 017 MUST-FIX DEFECT).

    The function body (non-docstring) must call FeatureGetAll().
    The docstring may reference InflectionClassGetAll() for historical context.
    """
    import ast
    import inspect
    from gramtrans.Lib import merge_preview
    src = inspect.getsource(merge_preview._find_target_inflection_feature_by_guid)
    assert "FeatureGetAll" in src, (
        "Defect: _find_target_inflection_feature_by_guid must use FeatureGetAll() "
        "to locate inflection features, not InflectionClassGetAll() (which returns "
        "inflection CLASSES)."
    )
    # Parse the AST to find all .InflectionClassGetAll() calls in actual code
    # (not the docstring text).
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "InflectionClassGetAll":
                raise AssertionError(
                    "Regression: InflectionClassGetAll() is called in the function body "
                    "of _find_target_inflection_feature_by_guid. Must use FeatureGetAll()."
                )

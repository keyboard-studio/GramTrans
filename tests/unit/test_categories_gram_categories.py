"""Unit tests for gram_categories leaf-category functions.

Covers:
- dependencies() returns empty tuple (leaf)
- plan_action() GOLD-aware skip
- plan_action() ALREADY_PRESENT_BY_GUID skip
- plan_action() returns PlannedAction for non-GOLD, new GUID
- execute_action() is LCM-bound — marked integration only
"""
from __future__ import annotations

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
# Fake objects
# ============================================================================

class _FakeCat:
    """Minimal duck-typed gram-category object."""
    def __init__(self, guid: str, catalog_source_id: str = "") -> None:
        self.guid = guid
        self.CatalogSourceId = catalog_source_id

    @property
    def concrete(self):
        return self


class _FakeGramCatOps:
    def __init__(self, items=()) -> None:
        self._items = list(items)

    def GetAll(self, recursive=True):
        return list(self._items)


class _FakeProject:
    def __init__(self, name: str, gram_cats=()) -> None:
        self.name = name
        self.GramCat = _FakeGramCatOps(gram_cats)

    def ProjectName(self):
        return self.name


def _ctx(source, target) -> RunContext:
    return RunContext(
        source_handle=source,
        source_project_name="SrcProj",
        source_project_path="/src",
        target_handle=target,
        target_project_name="TgtProj",
        target_project_path="/tgt",
        run_id="GT-20260620-010000",
        started_at="2026-06-20T01:00:00",
    )


_BUNDLE = categories.for_category(GrammarCategory.GRAM_CATEGORIES)


# ============================================================================
# Tests
# ============================================================================

def test_dependencies_returns_empty_tuple() -> None:
    cat = _FakeCat("aaa-111")
    assert tuple(_BUNDLE["dependencies"](piece=cat)) == ()


def test_plan_action_gold_object_yields_skip() -> None:
    """A gram category with non-empty CatalogSourceId IS a GOLD object."""
    gold_cat = _FakeCat("aaa-111", catalog_source_id="fPerson")
    src = _FakeProject("src", gram_cats=(gold_cat,))
    tgt = _FakeProject("tgt")
    ctx = _ctx(src, tgt)

    result = _BUNDLE["plan_action"](piece=gold_cat, context=ctx, ws_mapping=WSMapping())

    assert isinstance(result, Skip)
    assert result.reason == SkipReason.GOLD_INVIOLABLE
    assert result.category == GrammarCategory.GRAM_CATEGORIES


def test_plan_action_empty_catalog_source_id_is_not_gold() -> None:
    """An empty CatalogSourceId means user-created — not GOLD."""
    user_cat = _FakeCat("bbb-222", catalog_source_id="")
    src = _FakeProject("src", gram_cats=(user_cat,))
    tgt = _FakeProject("tgt")
    ctx = _ctx(src, tgt)

    result = _BUNDLE["plan_action"](piece=user_cat, context=ctx, ws_mapping=WSMapping())

    assert isinstance(result, PlannedAction)
    assert result.category == GrammarCategory.GRAM_CATEGORIES
    assert result.source_guid == "bbb-222"


def test_plan_action_already_present_by_guid_yields_skip() -> None:
    """Target already has the same GUID → ALREADY_PRESENT_BY_GUID."""
    cat = _FakeCat("ccc-333", catalog_source_id="")
    src = _FakeProject("src", gram_cats=(cat,))
    tgt_cat = _FakeCat("ccc-333")  # same GUID in target
    tgt = _FakeProject("tgt", gram_cats=(tgt_cat,))
    ctx = _ctx(src, tgt)

    result = _BUNDLE["plan_action"](piece=cat, context=ctx, ws_mapping=WSMapping())

    assert isinstance(result, Skip)
    assert result.reason == SkipReason.ALREADY_PRESENT_BY_GUID
    assert result.source_guid == "ccc-333"


def test_plan_action_new_guid_not_in_target_yields_planned_action() -> None:
    cat = _FakeCat("ddd-444", catalog_source_id="")
    src = _FakeProject("src", gram_cats=(cat,))
    tgt = _FakeProject("tgt", gram_cats=())
    ctx = _ctx(src, tgt)

    result = _BUNDLE["plan_action"](piece=cat, context=ctx, ws_mapping=WSMapping())

    assert isinstance(result, PlannedAction)
    assert result.intended_target_guid == "ddd-444"


def test_enumerate_source_returns_all_cats() -> None:
    cat_a = _FakeCat("e-001")
    cat_b = _FakeCat("e-002")
    src = _FakeProject("src", gram_cats=(cat_a, cat_b))
    tgt = _FakeProject("tgt")
    ctx = _ctx(src, tgt)
    sel = Selection(categories={GrammarCategory.GRAM_CATEGORIES: True})

    items = list(_BUNDLE["enumerate_source"](context=ctx, selection=sel))
    assert cat_a in items
    assert cat_b in items


@pytest.mark.integration
def test_execute_action_requires_lcm() -> None:
    """execute_action creates an LCM object — only runs under FlexTools host."""
    pytest.skip("LCM required; run as integration test with FlexTools host.")

"""Unit tests for inflection_features leaf-category functions.

Covers:
- dependencies() returns empty tuple (values co-created in execute_action)
- plan_action() GOLD-aware skip (CatalogSourceId non-empty)
- plan_action() ALREADY_PRESENT_BY_GUID skip
- plan_action() PlannedAction for non-GOLD new feature
- execute_action() is LCM-bound — integration only
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

class _FakeFeature:
    def __init__(self, guid: str, catalog_source_id: str = "") -> None:
        self.guid = guid
        self.CatalogSourceId = catalog_source_id


class _FakeInflFeatureOps:
    def __init__(self, features=()) -> None:
        self._features = list(features)

    def FeatureGetAll(self):
        return list(self._features)


class _FakeProject:
    def __init__(self, name: str, features=()) -> None:
        self.name = name
        self.InflectionFeatures = _FakeInflFeatureOps(features)

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


_BUNDLE = categories.for_category(GrammarCategory.INFLECTION_FEATURES)


# ============================================================================
# Tests
# ============================================================================

def test_dependencies_returns_empty_tuple() -> None:
    feat = _FakeFeature("f-001")
    assert tuple(_BUNDLE["dependencies"](piece=feat)) == ()


def test_plan_action_gold_feature_yields_gold_inviolable_skip() -> None:
    gold_feat = _FakeFeature("f-001", catalog_source_id="fDeg")
    src = _FakeProject("src", features=(gold_feat,))
    tgt = _FakeProject("tgt")
    ctx = _ctx(src, tgt)

    result = _BUNDLE["plan_action"](piece=gold_feat, context=ctx, ws_mapping=WSMapping())

    assert isinstance(result, Skip)
    assert result.reason == SkipReason.GOLD_INVIOLABLE
    assert result.category == GrammarCategory.INFLECTION_FEATURES
    assert "fDeg" in result.detail


def test_plan_action_none_catalog_source_id_is_not_gold() -> None:
    """CatalogSourceId=None should NOT trigger GOLD skip."""
    feat = _FakeFeature("f-002", catalog_source_id="")
    feat.CatalogSourceId = None  # explicitly None
    src = _FakeProject("src", features=(feat,))
    tgt = _FakeProject("tgt")
    ctx = _ctx(src, tgt)

    result = _BUNDLE["plan_action"](piece=feat, context=ctx, ws_mapping=WSMapping())

    assert isinstance(result, PlannedAction)


def test_plan_action_already_present_yields_skip() -> None:
    feat = _FakeFeature("f-003")
    src = _FakeProject("src", features=(feat,))
    tgt_feat = _FakeFeature("f-003")
    tgt = _FakeProject("tgt", features=(tgt_feat,))
    ctx = _ctx(src, tgt)

    result = _BUNDLE["plan_action"](piece=feat, context=ctx, ws_mapping=WSMapping())

    assert isinstance(result, Skip)
    assert result.reason == SkipReason.ALREADY_PRESENT_BY_GUID


def test_plan_action_new_guid_yields_planned_action() -> None:
    feat = _FakeFeature("f-004")
    src = _FakeProject("src", features=(feat,))
    tgt = _FakeProject("tgt")
    ctx = _ctx(src, tgt)

    result = _BUNDLE["plan_action"](piece=feat, context=ctx, ws_mapping=WSMapping())

    assert isinstance(result, PlannedAction)
    assert result.source_guid == "f-004"


def test_enumerate_source_returns_all_features() -> None:
    f1 = _FakeFeature("f-100")
    f2 = _FakeFeature("f-101")
    src = _FakeProject("src", features=(f1, f2))
    tgt = _FakeProject("tgt")
    ctx = _ctx(src, tgt)
    sel = Selection(categories={GrammarCategory.INFLECTION_FEATURES: True})

    items = list(_BUNDLE["enumerate_source"](context=ctx, selection=sel))
    assert f1 in items
    assert f2 in items


@pytest.mark.integration
def test_execute_action_requires_lcm() -> None:
    pytest.skip("LCM required; run as integration test with FlexTools host.")

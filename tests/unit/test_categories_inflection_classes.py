"""Unit tests for inflection_classes leaf-category functions.

Covers:
- dependencies() returns empty tuple (leaf — no POS wiring in Phase 0)
- plan_action() ALREADY_PRESENT_BY_GUID skip
- plan_action() PlannedAction for new GUID
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

class _FakeInflClass:
    def __init__(self, guid: str) -> None:
        self.guid = guid


class _FakeInflFeatureOps:
    def __init__(self, infl_classes=()) -> None:
        self._classes = list(infl_classes)

    def InflectionClassGetAll(self):
        return list(self._classes)


class _FakeProject:
    def __init__(self, name: str, infl_classes=()) -> None:
        self.name = name
        self.InflectionFeature = _FakeInflFeatureOps(infl_classes)

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


_BUNDLE = categories.for_category(GrammarCategory.INFLECTION_CLASSES)


# ============================================================================
# Tests
# ============================================================================

def test_dependencies_returns_empty_tuple() -> None:
    ic = _FakeInflClass("ic-001")
    assert tuple(_BUNDLE["dependencies"](piece=ic)) == ()


def test_plan_action_already_present_yields_skip() -> None:
    ic = _FakeInflClass("ic-002")
    src = _FakeProject("src", infl_classes=(ic,))
    tgt_ic = _FakeInflClass("ic-002")
    tgt = _FakeProject("tgt", infl_classes=(tgt_ic,))
    ctx = _ctx(src, tgt)

    result = _BUNDLE["plan_action"](piece=ic, context=ctx, ws_mapping=WSMapping())

    assert isinstance(result, Skip)
    assert result.reason == SkipReason.ALREADY_PRESENT_BY_GUID
    assert result.source_guid == "ic-002"


def test_plan_action_new_guid_yields_planned_action() -> None:
    ic = _FakeInflClass("ic-003")
    src = _FakeProject("src", infl_classes=(ic,))
    tgt = _FakeProject("tgt")
    ctx = _ctx(src, tgt)

    result = _BUNDLE["plan_action"](piece=ic, context=ctx, ws_mapping=WSMapping())

    assert isinstance(result, PlannedAction)
    assert result.category == GrammarCategory.INFLECTION_CLASSES
    assert result.source_guid == "ic-003"


def test_plan_action_different_guid_not_present() -> None:
    ic_a = _FakeInflClass("ic-010")
    ic_b = _FakeInflClass("ic-011")
    src = _FakeProject("src", infl_classes=(ic_a,))
    tgt = _FakeProject("tgt", infl_classes=(ic_b,))
    ctx = _ctx(src, tgt)

    result = _BUNDLE["plan_action"](piece=ic_a, context=ctx, ws_mapping=WSMapping())

    assert isinstance(result, PlannedAction)
    assert result.source_guid == "ic-010"


def test_enumerate_source_returns_all_classes() -> None:
    ic1 = _FakeInflClass("ic-100")
    ic2 = _FakeInflClass("ic-101")
    src = _FakeProject("src", infl_classes=(ic1, ic2))
    tgt = _FakeProject("tgt")
    ctx = _ctx(src, tgt)
    sel = Selection(categories={GrammarCategory.INFLECTION_CLASSES: True})

    items = list(_BUNDLE["enumerate_source"](context=ctx, selection=sel))
    assert ic1 in items
    assert ic2 in items


@pytest.mark.integration
def test_execute_action_requires_lcm() -> None:
    pytest.skip("LCM required; run as integration test with FlexTools host.")

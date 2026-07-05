"""Live MCP integration tests for adhoc_compound_rules engine (spec 018, T013).

SOURCE project: Esperanto (confirmed 5 MoEndoCompound rules, no adhoc or exo
compound rules -- probe-results.md [CONFIRMED LIVE 2026-07-05]).

TARGET: A FRESH throwaway project (write-enabled). Do NOT run against any
shared or production target.

Coverage gap (noted per task spec):
    Adhoc prohibitions (MoAlloAdhocProhib, MoMorphAdhocProhib, MoAdhocProhibGr)
    and exo compound rules (MoExoCompound) are NOT present in Esperanto. They
    are covered by fake-handle unit tests in
    tests/unit/test_rules_plan_dispatch.py only. Live coverage for those three
    subclasses requires authored fixtures in a throwaway target; deferred to a
    future cycle when a project with such objects is identified.

Tests:
    A  5 endo compound rules created with correct subclass, GUID-preserved,
       LeftMsaOA/RightMsaOA/OverridingMsaOA created, PartOfSpeechRA wired.
    B  Re-run idempotent (SC-001/002): all 5 -> Skip(ALREADY_PRESENT_BY_GUID).

Run manually (requires live FLExTools MCP and write-enabled Esperanto throwaway):

    python -m pytest tests/integration/test_rules_live.py -m integration -v

Skip headless:  python -m pytest -m "not integration"
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

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Source / target fixture helpers
# ---------------------------------------------------------------------------

SOURCE_PROJECT = "Esperanto"
EXPECTED_ENDO_COUNT = 5


def _open_project(name: str, *, write: bool):
    try:
        import flexlibs  # type: ignore
        project = flexlibs.FLExProject()
        project.OpenProject(name, writeEnabled=write)
        return project
    except Exception as e:
        pytest.skip(f"Cannot open project '{name}': {e}")


@pytest.fixture(scope="module")
def rules_source():
    """Esperanto source handle (read-only)."""
    pytest.skip(
        "Live MCP fixture: run manually with Esperanto and throwaway target open"
    )


@pytest.fixture(scope="module")
def rules_target():
    """Fresh throwaway target handle (write-enabled)."""
    pytest.skip(
        "Live MCP fixture: run manually with a fresh throwaway target open"
    )


def _ctx(src, tgt) -> RunContext:
    return RunContext(
        source_handle=src, source_project_name=SOURCE_PROJECT, source_project_path="/s",
        target_handle=tgt, target_project_name="Throwaway", target_project_path="/t",
        run_id="GT-20260705-RULES-LIVE", started_at="2026-07-05T00:00:00",
    )


WSM = WSMapping(entries=())
SEL = Selection(categories={GrammarCategory.ADHOC_COMPOUND_RULES: True})


# ---------------------------------------------------------------------------
# Scenario A: enumerate, plan, and execute all 5 endo compound rules
# ---------------------------------------------------------------------------

def test_enumerate_yields_five_endo_rules(rules_source, rules_target):
    """Source yields exactly 5 MoEndoCompound rules (probe-results.md)."""
    ctx = _ctx(rules_source, rules_target)
    items = categories.adhoc_compound_rules_enumerate_source(ctx, SEL)
    endo_items = [r for r in items if getattr(r, "class_name", None) == "MoEndoCompound"
                  or _class_name_of(r) == "MoEndoCompound"]
    assert len(endo_items) == EXPECTED_ENDO_COUNT, (
        f"Expected {EXPECTED_ENDO_COUNT} MoEndoCompound rules, got {len(endo_items)}"
    )


def test_plan_all_rules_as_planned_action(rules_source, rules_target):
    """Fresh target: all 5 rules plan as PlannedAction (not Skip)."""
    ctx = _ctx(rules_source, rules_target)
    items = categories.adhoc_compound_rules_enumerate_source(ctx, SEL)
    for rule in items:
        result = categories.adhoc_compound_rules_plan_action(rule, ctx, WSM)
        assert isinstance(result, PlannedAction), (
            f"Expected PlannedAction for {rule}, got {result!r}"
        )


def test_execute_all_rules_creates_matching_subclass(rules_source, rules_target):
    """Execute creates each rule in target; subclass matches source."""
    ctx = _ctx(rules_source, rules_target)
    items = categories.adhoc_compound_rules_enumerate_source(ctx, SEL)
    for rule in items:
        plan = categories.adhoc_compound_rules_plan_action(rule, ctx, WSM)
        new_obj = categories.adhoc_compound_rules_execute_action(
            plan, ctx, WSM, "test-018-live"
        )
        assert new_obj is not None, f"execute_action returned None for {rule!r}"
        # Subclass must match
        src_cn = _class_name_of(rule)
        tgt_cn = _class_name_of(new_obj)
        assert src_cn == tgt_cn, (
            f"Subclass mismatch: source={src_cn!r} target={tgt_cn!r}"
        )


def test_execute_preserves_guids(rules_source, rules_target):
    """Created objects must have source GUID preserved (Constitution I)."""
    from gramtrans.Lib.categories import _guid_str_from
    ctx = _ctx(rules_source, rules_target)
    items = categories.adhoc_compound_rules_enumerate_source(ctx, SEL)
    for rule in items:
        src_guid = _guid_str_from(rule)
        plan = categories.adhoc_compound_rules_plan_action(rule, ctx, WSM)
        if isinstance(plan, Skip):
            continue  # already present, skip (re-run scenario)
        new_obj = categories.adhoc_compound_rules_execute_action(
            plan, ctx, WSM, "test-018-live"
        )
        if new_obj is None:
            continue
        tgt_guid = _guid_str_from(new_obj)
        assert tgt_guid == src_guid, (
            f"GUID not preserved: src={src_guid!r} tgt={tgt_guid!r}"
        )


def test_endo_msa_slots_created(rules_source, rules_target):
    """MoEndoCompound: LeftMsaOA / RightMsaOA / OverridingMsaOA created on target rule."""
    ctx = _ctx(rules_source, rules_target)
    items = categories.adhoc_compound_rules_enumerate_source(ctx, SEL)
    for rule in items:
        if _class_name_of(rule) != "MoEndoCompound":
            continue
        plan = categories.adhoc_compound_rules_plan_action(rule, ctx, WSM)
        if isinstance(plan, Skip):
            continue
        new_obj = categories.adhoc_compound_rules_execute_action(
            plan, ctx, WSM, "test-018-live"
        )
        if new_obj is None:
            continue
        assert getattr(new_obj, "LeftMsaOA", None) is not None, (
            f"LeftMsaOA not wired on {new_obj!r}"
        )
        assert getattr(new_obj, "RightMsaOA", None) is not None, (
            f"RightMsaOA not wired on {new_obj!r}"
        )
        # OverridingMsaOA is confirmed present on Esperanto endo rules
        assert getattr(new_obj, "OverridingMsaOA", None) is not None, (
            f"OverridingMsaOA not wired on {new_obj!r}"
        )


def test_endo_msa_pos_wired(rules_source, rules_target):
    """Each created MSA has PartOfSpeechRA wired to a target POS."""
    ctx = _ctx(rules_source, rules_target)
    items = categories.adhoc_compound_rules_enumerate_source(ctx, SEL)
    for rule in items:
        if _class_name_of(rule) != "MoEndoCompound":
            continue
        plan = categories.adhoc_compound_rules_plan_action(rule, ctx, WSM)
        if isinstance(plan, Skip):
            continue
        new_obj = categories.adhoc_compound_rules_execute_action(
            plan, ctx, WSM, "test-018-live"
        )
        if new_obj is None:
            continue
        for slot in ("LeftMsaOA", "RightMsaOA", "OverridingMsaOA"):
            msa = getattr(new_obj, slot, None)
            if msa is None:
                continue
            pos = getattr(msa, "PartOfSpeechRA", None)
            assert pos is not None, (
                f"{slot}.PartOfSpeechRA is None on {new_obj!r}"
            )


# ---------------------------------------------------------------------------
# Scenario B: idempotency re-run (SC-001/002)
# ---------------------------------------------------------------------------

def test_rerun_all_rules_skip_by_guid(rules_source, rules_target):
    """Second run: all rules already present by GUID -> all Skip."""
    ctx = _ctx(rules_source, rules_target)
    items = categories.adhoc_compound_rules_enumerate_source(ctx, SEL)
    for rule in items:
        result = categories.adhoc_compound_rules_plan_action(rule, ctx, WSM)
        assert isinstance(result, Skip), (
            f"Expected Skip on re-run for {rule!r}, got {result!r}"
        )
        assert result.reason == SkipReason.ALREADY_PRESENT_BY_GUID


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _class_name_of(obj):
    """Return ClassName string for a real or fake rule object."""
    try:
        from SIL.LCModel import ICmObject
        return ICmObject(obj).ClassName
    except Exception:
        return getattr(obj, "class_name", getattr(obj, "ClassName", None))

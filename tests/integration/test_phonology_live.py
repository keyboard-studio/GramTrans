"""Live MCP integration tests for the Phonology selector (spec 010, T027).

IMPORTANT: These tests require a live FlexTools MCP session with the source
project **Ejagham Mini** and a freshly-restored target **Ejagham Full GT-Test**
(quickstart.md prerequisites). They are NOT run by the unit suite
(`pytest tests/unit`). Run manually:

    python -m pytest tests/integration/test_phonology_live.py -m integration -v

Skip with:  python -m pytest -m "not integration"

Scenarios A–E mirror specs/010-phonology-selector/quickstart.md:
  A  Whole block, all preselected (US1)         -> counts + strata + zero warnings
  B  Whole-block off (US2)                       -> zero phonology / strata actions
  C  Per-item trim (US2 / FR-005 + US5)          -> subset transfers; stranded ref warns
  D  Rule-gated strata (US3 / FR-009)            -> rules off => no strata; no strata row
  E  Idempotency regression (spec-005 FR-307)    -> re-run skips by-GUID; no duplicates

STATUS: Written, not executed here. The count anchors below come from
quickstart.md (32 phonemes, 5 natural classes, 2+ environments). Verify /
adjust them in the live session before trusting a green run.
"""
from __future__ import annotations

import pytest

from gramtrans.Lib.models import GrammarCategory as GC
from gramtrans.Lib.selection import (
    build_phonology_excluded_lossy,
    build_phonology_inventory,
    collapse_phonology,
    phonology_uses_untraversed_rules,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures (injected by the main session; skip by default in headless runs)
# ---------------------------------------------------------------------------

def _open_project(name: str, *, write: bool):
    try:
        import flexlibs  # type: ignore
        project = flexlibs.FLExProject()
        project.OpenProject(name, writeEnabled=write)
        return project
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Cannot open project '{name}': {e}")


@pytest.fixture
def phon_source():
    """Ejagham Mini source handle (read-only)."""
    pytest.skip("Live MCP fixture: run manually with Ejagham Mini open")


@pytest.fixture
def phon_target():
    """Freshly-restored Ejagham Full GT-Test target handle."""
    pytest.skip("Live MCP fixture: run manually with a fresh Ejagham Full GT-Test")


def _all_checked(inv):
    return {g.category: {r.guid for r in g.rows} for g in inv.groups}


def _target_guids_by_cat(target):
    tinv = build_phonology_inventory(target)
    return {g.category: {r.guid for r in g.rows} for g in tinv.groups}


# ---------------------------------------------------------------------------
# Scenario A — Whole block, all preselected (US1)
# ---------------------------------------------------------------------------

def test_scenario_a_whole_block_counts_and_strata(phon_source, phon_target):
    inv = build_phonology_inventory(phon_source, target=phon_target)
    counts = {g.category: g.count for g in inv.groups}
    # quickstart.md anchors (adjust live if the corpus changes):
    assert counts[GC.PHONEMES] == 32
    assert counts[GC.NATURAL_CLASSES] == 5
    assert counts[GC.PH_ENVIRONMENT] >= 2
    # All rows preselected.
    assert all(r.preselected for g in inv.groups for r in g.rows)

    out = collapse_phonology(inv, _all_checked(inv))
    for cat in (GC.PHONOLOGICAL_FEATURES, GC.PHONEMES, GC.NATURAL_CLASSES,
                GC.PH_ENVIRONMENT, GC.PHONOLOGICAL_RULES):
        assert out["categories"].get(cat) is True
    assert out["leaf_item_picks"] == {}          # transfer-all, no trims (SC-002)
    assert out["categories"].get(GC.STRATA) is True  # rules present => strata (FR-009)
    # No stranded references when nothing is trimmed.
    warns = build_phonology_excluded_lossy(
        inv, _all_checked(inv), _target_guids_by_cat(phon_target))
    assert warns == []


# ---------------------------------------------------------------------------
# Scenario B — Whole-block off (US2)
# ---------------------------------------------------------------------------

def test_scenario_b_whole_block_off(phon_source, phon_target):
    inv = build_phonology_inventory(phon_source, target=phon_target)
    out = collapse_phonology(inv, {})  # user toggled the block off
    assert out["categories"] == {}      # zero phonology actions (SC-003)
    assert GC.STRATA not in out["categories"]  # and zero strata


# ---------------------------------------------------------------------------
# Scenario C — Per-item trim (US2 / FR-005) + stranded ref (US5)
# ---------------------------------------------------------------------------

def test_scenario_c_trim_unreferenced_phonemes(phon_source, phon_target):
    inv = build_phonology_inventory(phon_source, target=phon_target)
    checked = _all_checked(inv)
    all_ph = sorted(checked[GC.PHONEMES])
    # Drop 3 phonemes NO kept NC/rule references (pick from the tail; verify live).
    checked[GC.PHONEMES] = set(all_ph[:-3])
    out = collapse_phonology(inv, checked)
    assert out["leaf_item_picks"][GC.PHONEMES] == frozenset(all_ph[:-3])
    # No warning when the dropped phonemes are unreferenced by kept items.
    warns = build_phonology_excluded_lossy(
        inv, checked, _target_guids_by_cat(phon_target))
    assert warns == []


def test_scenario_c_trim_referenced_phoneme_warns(phon_source, phon_target):
    inv = build_phonology_inventory(phon_source, target=phon_target)
    # Find a natural class and one phoneme it references.
    nc_refs = inv.nc_referenced_phoneme_guids
    assert nc_refs, "Expected at least one NC->phoneme reference in Ejagham"
    nc_guid = next(iter(nc_refs))
    stranded_ph = next(iter(nc_refs[nc_guid]))
    checked = _all_checked(inv)
    checked[GC.PHONEMES] = checked[GC.PHONEMES] - {stranded_ph}  # deselect it
    # target must LACK it for a warning (fresh restore lacks source phonemes)
    tgt = _target_guids_by_cat(phon_target)
    tgt.setdefault(GC.PHONEMES, set()).discard(stranded_ph)
    warns = build_phonology_excluded_lossy(inv, checked, tgt)
    naming_nc = [w for w in warns
                 if w.entry_guid == nc_guid and w.dep_guid == stranded_ph]
    assert len(naming_nc) == 1  # one entry-centric warning naming the NC (US5)


# ---------------------------------------------------------------------------
# Scenario D — Rule-gated strata (US3 / FR-009)
# ---------------------------------------------------------------------------

def test_scenario_d_rules_off_no_strata(phon_source, phon_target):
    inv = build_phonology_inventory(phon_source, target=phon_target)
    checked = _all_checked(inv)
    checked[GC.PHONOLOGICAL_RULES] = set()  # deselect all rules; keep phonemes/NCs
    out = collapse_phonology(inv, checked)
    assert GC.STRATA not in out["categories"]  # no strata (SC-004)
    # Strata is never a user-facing group.
    assert all(g.category != GC.STRATA for g in inv.groups)


# ---------------------------------------------------------------------------
# Scenario E — Idempotency regression (spec-005 FR-307)
# ---------------------------------------------------------------------------

def test_scenario_e_idempotent_rerun(phon_source, phon_target):
    """After a whole-block Move, a target now containing every source phoneme
    by GUID must classify all rows in_target (=> the re-run skips, no dupes).

    This asserts the *classification* the leaf-dispatch relies on; the actual
    no-duplicate-create assertion is exercised by executing the Move twice in
    the live session and confirming the second run's added count is 0.
    """
    inv = build_phonology_inventory(phon_source, target=phon_source)  # target == source
    ph_rows = inv.group_for(GC.PHONEMES).rows
    assert ph_rows and all(r.status == "in_target" for r in ph_rows)
    # No untraversed-rule surprises for the Ejagham corpus (PhRegularRule only).
    assert phonology_uses_untraversed_rules(
        inv, {r.guid for r in inv.group_for(GC.PHONOLOGICAL_RULES).rows}) is False

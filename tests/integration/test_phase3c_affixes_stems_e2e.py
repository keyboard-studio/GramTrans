"""Phase 3c US1 integration smoke tests.

T028: test_us1_affix_round_trip — fake-LCM-surface planning pass asserting
13 PlannedActions are produced for an Ejagham-Mini-shaped 13-entry affix
fixture. The full execute_action pass is gated behind the FlexTools host
(requires SIL.LCModel + pythonnet).

Phase 3c integration tests are marked `integration` and skipped in unit-only
pytest runs (`pytest -m 'not integration'`).  The planning-side smoke test
below can run without a host since it exercises only enumerate_source and
plan_action (no SIL.LCModel imports).
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


# ============================================================================
# Ejagham-Mini-shaped fixture (13 verb-affix entries)
# ============================================================================

class _FakeMorphType:
    IsAffixType = True


class _FakeForm:
    MorphTypeRA = _FakeMorphType()
    ClassName = "MoAffixAllomorph"
    guid = "form-placeholder"


class _FakeMSA:
    def __init__(self, guid: str) -> None:
        self.guid = guid
        self.ClassName = "MoInflAffMsa"
        self.PartOfSpeechRA = _FakePOS("pos-verb-guid")
        self.SlotsRC = []


class _FakePOS:
    def __init__(self, guid: str) -> None:
        self.guid = guid


class _FakeSense:
    def __init__(self, guid: str, msa_guid: str) -> None:
        self.guid = guid
        self.MorphoSyntaxAnalysisRA = _FakeMSA(msa_guid)
        self.ExamplesOS = []
        self.SemanticDomainsRC = []


class _FakeEntry:
    def __init__(self, entry_num: int) -> None:
        self.guid = f"entry-{entry_num:03d}"
        self.LexemeFormOA = _FakeForm()
        msa_guid = f"msa-{entry_num:03d}"
        self.MorphoSyntaxAnalysesOC = [_FakeMSA(msa_guid)]
        self.SensesOS = [_FakeSense(f"sense-{entry_num:03d}", msa_guid)]
        self.AlternateFormsOS = []
        self.PronunciationsOS = []
        self.EtymologyOS = []
        self.EntryRefsOS = []


def _make_ejagham_mini_fixture(n_affix_entries: int = 13):
    """Build a fake source project with `n_affix_entries` affix entries."""
    entries = [_FakeEntry(i) for i in range(1, n_affix_entries + 1)]
    return entries


class _FakeLexDb:
    def __init__(self, entries) -> None:
        self.EntriesOC = list(entries)


class _FakeLangProject:
    def __init__(self, entries, tgt_entries=()) -> None:
        self.LexDbOA = _FakeLexDb(entries)


class _FakeSrcCache:
    def __init__(self, entries) -> None:
        self.LangProject = _FakeLangProject(entries)


class _FakeTgtCache:
    def __init__(self, entries=()) -> None:
        self.LangProject = _FakeLangProject(list(entries))


class _FakeSrcProject:
    def __init__(self, entries) -> None:
        self._cache = _FakeSrcCache(entries)

    @property
    def Cache(self):
        return self._cache


class _FakeTgtProject:
    def __init__(self, entries=()) -> None:
        self._cache = _FakeTgtCache(entries)

    @property
    def Cache(self):
        return self._cache


def _make_ctx(src_entries, tgt_entries=()):
    src = _FakeSrcProject(src_entries)
    tgt = _FakeTgtProject(tgt_entries)
    return RunContext(
        source_handle=src,
        source_project_name="Ejagham Mini",
        source_project_path="C:/ProgramData/SIL/FieldWorks/Projects/Ejagham Mini",
        target_handle=tgt,
        target_project_name="Ejagham Full GT-Test",
        target_project_path="C:/ProgramData/SIL/FieldWorks/Projects/Ejagham Full GT-Test",
        run_id="GT-20260627-080000",
        started_at="2026-06-27T08:00:00",
    )


def _ws_map():
    return WSMapping(entries=())


# ============================================================================
# T028 — US1 affix round-trip (fake-LCM planning side)
# ============================================================================

def test_us1_affix_round_trip_planning_produces_13_actions() -> None:
    """Ejagham-Mini-shaped 13-entry affix fixture → 13 PlannedActions from AFFIXES.

    This exercises enumerate_source + plan_action without SIL.LCModel imports.
    The full execute_action pass requires the FlexTools host (live LCM).
    """
    fixture_entries = _make_ejagham_mini_fixture(n_affix_entries=13)
    ctx = _make_ctx(fixture_entries)
    msa_slot_bindings: dict = {}
    lexentry_ref_bindings: dict = {}
    object.__setattr__(ctx, '_msa_slot_bindings', msa_slot_bindings)
    object.__setattr__(ctx, '_lexentry_ref_bindings', lexentry_ref_bindings)

    bundle = categories.for_category(GrammarCategory.AFFIXES)

    # enumerate_source should yield all 13 entries.
    pieces = list(bundle["enumerate_source"](ctx, None))
    assert len(pieces) == 13, f"Expected 13 affix entries, got {len(pieces)}"

    # plan_action should produce 13 PlannedActions (target is empty).
    actions = []
    skips = []
    ws = _ws_map()
    for piece in pieces:
        result = bundle["plan_action"](piece, ctx, ws)
        if isinstance(result, PlannedAction):
            actions.append(result)
        elif isinstance(result, Skip):
            skips.append(result)

    assert len(actions) == 13, (
        f"Expected 13 PlannedActions for affix entries, got {len(actions)}. "
        f"Skips: {[(s.source_guid, s.reason) for s in skips]}"
    )
    assert len(skips) == 0, f"Unexpected skips: {[(s.source_guid, s.reason, s.detail) for s in skips]}"

    # All actions should be for AFFIXES category.
    for action in actions:
        assert action.category == GrammarCategory.AFFIXES

    # All source GUIDs are distinct.
    src_guids = {a.source_guid for a in actions}
    assert len(src_guids) == 13

    # MSA slot bindings: all 13 MSAs with empty SlotsRC → nothing stashed.
    assert msa_slot_bindings == {}, (
        f"No affix MSAs have slots in Ejagham Mini fixture; "
        f"expected empty bindings, got: {msa_slot_bindings}"
    )


def test_us1_affix_round_trip_empty_source_produces_no_actions() -> None:
    """Empty source → 0 PlannedActions, 0 skips (FR-308 empty-source UX)."""
    ctx = _make_ctx([])
    object.__setattr__(ctx, '_msa_slot_bindings', {})
    object.__setattr__(ctx, '_lexentry_ref_bindings', {})

    bundle = categories.for_category(GrammarCategory.AFFIXES)
    pieces = list(bundle["enumerate_source"](ctx, None))
    assert len(pieces) == 0


def test_us1_affix_already_present_skips_on_rerun() -> None:
    """Re-run over a pre-populated target → all 13 entries skip as ALREADY_PRESENT_BY_GUID."""
    fixture_entries = _make_ejagham_mini_fixture(n_affix_entries=13)
    # Target has the same GUIDs as source.
    ctx = _make_ctx(fixture_entries, tgt_entries=fixture_entries)
    object.__setattr__(ctx, '_msa_slot_bindings', {})
    object.__setattr__(ctx, '_lexentry_ref_bindings', {})

    bundle = categories.for_category(GrammarCategory.AFFIXES)
    pieces = list(bundle["enumerate_source"](ctx, None))

    skips = []
    actions = []
    ws = _ws_map()
    for piece in pieces:
        result = bundle["plan_action"](piece, ctx, ws)
        if isinstance(result, Skip):
            skips.append(result)
        elif isinstance(result, PlannedAction):
            actions.append(result)

    assert len(actions) == 0, f"Expected no PlannedActions on re-run, got {actions}"
    assert len(skips) == 13
    for skip in skips:
        assert skip.reason == SkipReason.ALREADY_PRESENT_BY_GUID


# ============================================================================
# Live FlexTools host test — skipped unless MCP / host is wired
# ============================================================================

# ============================================================================
# T041 — US2 slots + templates + 17.1 MSA-slot wiring (fake-surface)
# ============================================================================

class _FakeRefColl:
    def __init__(self, initial=()) -> None:
        self._items = list(initial)
        self.add_log = []

    def Add(self, obj):
        self._items.append(obj)
        self.add_log.append(obj)

    def __iter__(self):
        return iter(self._items)

    @property
    def Count(self):
        return len(self._items)


class _FakeWiredMSA:
    def __init__(self, guid: str) -> None:
        self.guid = guid
        self.SlotsRC = _FakeRefColl()


class _FakeSlotObj:
    def __init__(self, guid: str) -> None:
        self.guid = guid


class _FakeWiringTarget:
    def __init__(self, objs) -> None:
        self._objs = dict(objs)

    def get_object_by_guid(self, guid):
        return self._objs.get(guid)


def test_us2_slots_templates_171() -> None:
    """Ejagham-Mini-shaped: 13 MSAs, 4 slots; 12 MSAs bound to a slot, the
    13th (`ro~-`) unbound. After the 17.1 sub-pass: 12 MSA-slot wires, the
    unbound MSA stays empty, and no skips (all bound slots resolve)."""
    import types

    msas = {f"msa-{i:03d}": _FakeWiredMSA(f"msa-{i:03d}") for i in range(1, 14)}
    slots = {f"slot-{i}": _FakeSlotObj(f"slot-{i}") for i in range(1, 5)}
    registry = {}
    registry.update(msas)
    registry.update(slots)
    target = _FakeWiringTarget(registry)

    # 12 of 13 MSAs carry a slot binding; msa-013 (ro~-) is unbound.
    bindings = {
        f"msa-{i:03d}": [f"slot-{(i % 4) + 1}"]
        for i in range(1, 13)
    }
    assert "msa-013" not in bindings  # the unbound ro~- case

    ctx = RunContext(
        source_handle=object(),
        source_project_name="Ejagham Mini",
        source_project_path="/src",
        target_handle=object(),
        target_project_name="Ejagham Full GT-Test",
        target_project_path="/tgt",
        run_id="GT-20260628-090000",
        started_at="2026-06-28T09:00:00",
    )
    plan = types.SimpleNamespace(msa_slot_bindings=bindings, identity_remap={})
    object.__setattr__(ctx, "_run_plan", plan)

    skips = categories._run_171_subpass(ctx, target, tag=None)

    total_wires = sum(m.SlotsRC.Count for m in msas.values())
    assert total_wires == 12, f"expected 12 MSA-slot wires, got {total_wires}"
    assert msas["msa-013"].SlotsRC.Count == 0, "ro~- must remain unbound"
    assert skips == [], f"unexpected 17.1 skips: {[(s.source_guid, s.detail) for s in skips]}"


def test_us2_171_unbound_count_matches_phase0() -> None:
    """SC: exactly one MSA unbound (matches Phase 0 Layer 3's `ro~-` case)."""
    import types

    msas = {f"msa-{i:03d}": _FakeWiredMSA(f"msa-{i:03d}") for i in range(1, 14)}
    slots = {"slot-1": _FakeSlotObj("slot-1")}
    target = _FakeWiringTarget({**msas, **slots})
    bindings = {f"msa-{i:03d}": ["slot-1"] for i in range(1, 13)}

    ctx = RunContext(
        source_handle=object(), source_project_name="s", source_project_path="/s",
        target_handle=object(), target_project_name="t", target_project_path="/t",
        run_id="GT-1", started_at="t",
    )
    object.__setattr__(ctx, "_run_plan",
                       types.SimpleNamespace(msa_slot_bindings=bindings, identity_remap={}))

    categories._run_171_subpass(ctx, target, tag=None)

    unbound = [g for g, m in msas.items() if m.SlotsRC.Count == 0]
    assert unbound == ["msa-013"]


def test_us1_affix_round_trip_live_lcm() -> None:
    """Full execute pass (SIL.LCModel): 13 entries created, 13 senses, 13 MSAs.

    Requires:
    - FlexTools host with pythonnet + SIL.LCModel 9.x
    - Ejagham Mini at C:/ProgramData/SIL/FieldWorks/Projects/Ejagham Mini
    - Ejagham Full GT-Test freshly restored from backups/Ejagham Full.fwbackup

    Run via: flextools_run_module or under the FlexTools host directly.
    """
    pytest.skip(
        "Live LCM test — requires FlexTools host with pythonnet + SIL.LCModel. "
        "Run via flextools_run_module or under the FlexTools host directly."
    )

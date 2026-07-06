"""Unit tests for Phase 3c post-pass A (LexEntryRef wiring) + the 17.1
MSA-slot sub-pass — the two pure-Python tail sub-passes of feature 007.

Both helpers are module-level in categories.py and run host-free over a
duck-typed target exposing `get_object_by_guid(guid)`:

- ``categories._run_post_pass_a(context, target, tag=None)`` — reads
  ``context._run_plan.lexentry_ref_bindings`` (``{src_entry_guid:
  {"ComponentLexemesRS": [...], "PrimaryLexemesRS": [...]}}``) plus
  ``plan.in_plan_entries``, then wires each target entry-ref's
  ComponentLexemesRS / PrimaryLexemesRS in source order. Idempotent via a
  membership guard; emits one Skip(DEPENDENCY_UNRESOLVED) per unresolved
  target entry (detail ``entry_guid=<g>``) and per unresolved lexeme
  (detail ``<field> component <guid> unresolved``). See
  contracts/post-pass-a.md.

- ``categories._run_171_subpass(context, target, tag=None)`` — reads
  ``context._run_plan.msa_slot_bindings`` (``{src_msa_guid: [src_slot_guid,
  ...]}``) plus ``plan.identity_remap``, then wires each MSA's SlotsRC in
  source order. See contracts/msa-slot-wiring.md.

Fakes expose the LOWERCASE ``.guid`` attribute that ``categories._guid_str_from``
reads host-free, and record every RS/RC ``Add`` so ordering can be asserted.
"""
from __future__ import annotations

import types

import pytest

from gramtrans.Lib import categories
from gramtrans.Lib.models import (
    GrammarCategory,
    RunContext,
    Skip,
    SkipReason,
)


# ============================================================================
# Fakes (inline, lowercase .guid so _guid_str_from resolves host-free)
# ============================================================================

class _FakeRefSeq:
    """LCM reference sequence/collection stand-in: records Add calls in order."""

    def __init__(self, initial=()) -> None:
        self._items = list(initial)
        self.add_log = []  # ordered list of added objects

    def Add(self, obj):
        self._items.append(obj)
        self.add_log.append(obj)

    def __iter__(self):
        return iter(self._items)

    @property
    def Count(self):
        return len(self._items)


class _FakeObj:
    """Anything addressed by GUID (lexeme entry, slot, MSA target)."""

    def __init__(self, guid: str) -> None:
        self.guid = guid


class _FakeEntryRef:
    def __init__(self, components=(), primaries=()) -> None:
        self.ComponentLexemesRS = _FakeRefSeq(initial=components)
        self.PrimaryLexemesRS = _FakeRefSeq(initial=primaries)


class _FakeTargetEntry:
    def __init__(self, guid: str, entry_refs=()) -> None:
        self.guid = guid
        self.EntryRefsOS = list(entry_refs)


class _FakeTargetMSA:
    def __init__(self, guid: str, prewired=()) -> None:
        self.guid = guid
        self.SlotsRC = _FakeRefSeq(initial=prewired)


class _FakeTarget:
    """Target project handle exposing get_object_by_guid over a registry."""

    def __init__(self, objects_by_guid=None) -> None:
        self._objs = dict(objects_by_guid or {})

    def get_object_by_guid(self, guid):
        return self._objs.get(guid)


def _make_ctx() -> RunContext:
    return RunContext(
        source_handle=object(),
        source_project_name="Src",
        source_project_path="/src",
        target_handle=object(),
        target_project_name="Tgt",
        target_project_path="/tgt",
        run_id="GT-20260706-000000",
        started_at="2026-07-06T00:00:00",
    )


def _ctx_post_pass_a(lexentry_ref_bindings, in_plan_entries=None) -> RunContext:
    ctx = _make_ctx()
    plan = types.SimpleNamespace(
        lexentry_ref_bindings=dict(lexentry_ref_bindings),
        in_plan_entries=dict(in_plan_entries or {}),
    )
    object.__setattr__(ctx, "_run_plan", plan)
    return ctx


def _ctx_171(msa_slot_bindings, identity_remap=None) -> RunContext:
    ctx = _make_ctx()
    plan = types.SimpleNamespace(
        msa_slot_bindings=dict(msa_slot_bindings),
        identity_remap=dict(identity_remap or {}),
    )
    object.__setattr__(ctx, "_run_plan", plan)
    return ctx


# ============================================================================
# post-pass A — LexEntryRef component/primary lexeme wiring
# ============================================================================

def test_post_pass_a_wires_component_lexemes_in_order() -> None:
    """Two component lexemes → 2 ComponentLexemesRS.Add in source order."""
    ref = _FakeEntryRef()
    entry = _FakeTargetEntry("entry-1", entry_refs=[ref])
    lex_a, lex_b = _FakeObj("lex-a"), _FakeObj("lex-b")
    target = _FakeTarget({"entry-1": entry, "lex-a": lex_a, "lex-b": lex_b})
    ctx = _ctx_post_pass_a(
        {"entry-1": {"ComponentLexemesRS": ["lex-a", "lex-b"]}}
    )

    skips = categories._run_post_pass_a(ctx, target, tag=None)

    assert skips == []
    assert ref.ComponentLexemesRS.add_log == [lex_a, lex_b]
    assert ref.PrimaryLexemesRS.add_log == []


def test_post_pass_a_wires_both_fields() -> None:
    """ComponentLexemesRS and PrimaryLexemesRS both wired from the binding."""
    ref = _FakeEntryRef()
    entry = _FakeTargetEntry("entry-1", entry_refs=[ref])
    comp, prim = _FakeObj("comp"), _FakeObj("prim")
    target = _FakeTarget({"entry-1": entry, "comp": comp, "prim": prim})
    ctx = _ctx_post_pass_a({
        "entry-1": {
            "ComponentLexemesRS": ["comp"],
            "PrimaryLexemesRS": ["prim"],
        }
    })

    skips = categories._run_post_pass_a(ctx, target, tag=None)

    assert skips == []
    assert ref.ComponentLexemesRS.add_log == [comp]
    assert ref.PrimaryLexemesRS.add_log == [prim]


def test_post_pass_a_resolves_via_in_plan_entries_first() -> None:
    """A lexeme in the in-plan creation list is used before target lookup."""
    ref = _FakeEntryRef()
    entry = _FakeTargetEntry("entry-1", entry_refs=[ref])
    in_plan_lex = _FakeObj("lex-x")
    # Deliberately absent from the target registry: must resolve via in_plan.
    target = _FakeTarget({"entry-1": entry})
    ctx = _ctx_post_pass_a(
        {"entry-1": {"ComponentLexemesRS": ["lex-x"]}},
        in_plan_entries={"lex-x": in_plan_lex},
    )

    skips = categories._run_post_pass_a(ctx, target, tag=None)

    assert skips == []
    assert ref.ComponentLexemesRS.add_log == [in_plan_lex]


def test_post_pass_a_unresolved_target_entry() -> None:
    """Target entry missing → 1 Skip with entry_guid=<g> detail, no writes."""
    target = _FakeTarget({})  # entry-missing absent
    ctx = _ctx_post_pass_a(
        {"entry-missing": {"ComponentLexemesRS": ["lex-a"]}}
    )

    skips = categories._run_post_pass_a(ctx, target, tag=None)

    assert len(skips) == 1
    assert skips[0].reason == SkipReason.DEPENDENCY_UNRESOLVED
    assert "entry_guid=entry-missing" in skips[0].detail


def test_post_pass_a_unresolved_component_lexeme() -> None:
    """One component missing → 1 Add + 1 Skip('<field> component <guid> unresolved')."""
    ref = _FakeEntryRef()
    entry = _FakeTargetEntry("entry-1", entry_refs=[ref])
    present = _FakeObj("present")
    target = _FakeTarget({"entry-1": entry, "present": present})  # "gone" absent
    ctx = _ctx_post_pass_a(
        {"entry-1": {"ComponentLexemesRS": ["present", "gone"]}}
    )

    skips = categories._run_post_pass_a(ctx, target, tag=None)

    assert ref.ComponentLexemesRS.add_log == [present]
    assert len(skips) == 1
    assert skips[0].reason == SkipReason.DEPENDENCY_UNRESOLVED
    assert skips[0].detail == "ComponentLexemesRS component gone unresolved"


def test_post_pass_a_idempotent_rerun() -> None:
    """Pre-wired ref + same binding → 0 net writes, 0 skips (membership guard)."""
    lex_a = _FakeObj("lex-a")
    ref = _FakeEntryRef(components=[lex_a])  # already wired
    entry = _FakeTargetEntry("entry-1", entry_refs=[ref])
    target = _FakeTarget({"entry-1": entry, "lex-a": lex_a})
    ctx = _ctx_post_pass_a(
        {"entry-1": {"ComponentLexemesRS": ["lex-a"]}}
    )

    skips = categories._run_post_pass_a(ctx, target, tag=None)

    assert skips == []
    assert ref.ComponentLexemesRS.add_log == []  # no re-Add
    assert ref.ComponentLexemesRS.Count == 1


def test_post_pass_a_empty_bindings_noop() -> None:
    """Empty plan bindings → no work, empty skip list."""
    ctx = _ctx_post_pass_a({})
    assert categories._run_post_pass_a(ctx, _FakeTarget({}), tag=None) == []


def test_post_pass_a_falls_back_to_context_attrs_without_run_plan() -> None:
    """No _run_plan → reads context._lexentry_ref_bindings + _in_plan_entries."""
    ref = _FakeEntryRef()
    entry = _FakeTargetEntry("entry-1", entry_refs=[ref])
    lex_a = _FakeObj("lex-a")
    target = _FakeTarget({"entry-1": entry, "lex-a": lex_a})
    ctx = _make_ctx()  # no _run_plan attached
    object.__setattr__(
        ctx, "_lexentry_ref_bindings",
        {"entry-1": {"ComponentLexemesRS": ["lex-a"]}},
    )

    skips = categories._run_post_pass_a(ctx, target, tag=None)

    assert skips == []
    assert ref.ComponentLexemesRS.add_log == [lex_a]


def test_post_pass_a_preserves_source_order_across_fields() -> None:
    """Multiple components in a field keep source order."""
    ref = _FakeEntryRef()
    entry = _FakeTargetEntry("entry-1", entry_refs=[ref])
    l1, l2, l3 = _FakeObj("l1"), _FakeObj("l2"), _FakeObj("l3")
    target = _FakeTarget(
        {"entry-1": entry, "l1": l1, "l2": l2, "l3": l3}
    )
    ctx = _ctx_post_pass_a(
        {"entry-1": {"ComponentLexemesRS": ["l3", "l1", "l2"]}}
    )

    categories._run_post_pass_a(ctx, target, tag=None)

    assert ref.ComponentLexemesRS.add_log == [l3, l1, l2]


# ============================================================================
# 17.1 MSA-slot sub-pass
# ============================================================================

def test_171_wires_slots_in_order() -> None:
    """MSA with 3 slot bindings → 3 SlotsRC.Add in source order."""
    msa = _FakeTargetMSA("msa-1")
    s1, s2, s3 = _FakeObj("a"), _FakeObj("b"), _FakeObj("c")
    target = _FakeTarget({"msa-1": msa, "a": s1, "b": s2, "c": s3})
    ctx = _ctx_171({"msa-1": ["a", "b", "c"]})

    skips = categories._run_171_subpass(ctx, target, tag=None)

    assert skips == []
    assert msa.SlotsRC.add_log == [s1, s2, s3]


def test_171_resolves_msa_via_identity_remap() -> None:
    """Source MSA guid remapped to the created target MSA guid."""
    msa = _FakeTargetMSA("msa-new")
    slot = _FakeObj("slot-1")
    target = _FakeTarget({"msa-new": msa, "slot-1": slot})
    ctx = _ctx_171({"msa-src": ["slot-1"]}, identity_remap={"msa-src": "msa-new"})

    skips = categories._run_171_subpass(ctx, target, tag=None)

    assert skips == []
    assert msa.SlotsRC.add_log == [slot]


def test_171_unresolved_msa() -> None:
    """MSA absent from target → 1 Skip carrying msa_guid=<g> detail."""
    slot = _FakeObj("slot-1")
    target = _FakeTarget({"slot-1": slot})  # msa absent
    ctx = _ctx_171({"msa-missing": ["slot-1"]})

    skips = categories._run_171_subpass(ctx, target, tag=None)

    assert len(skips) == 1
    assert skips[0].reason == SkipReason.DEPENDENCY_UNRESOLVED
    assert "msa_guid=msa-missing" in skips[0].detail


def test_171_unresolved_slot() -> None:
    """One slot missing → 1 Add + 1 Skip carrying the slot guid."""
    msa = _FakeTargetMSA("msa-1")
    present = _FakeObj("present")
    target = _FakeTarget({"msa-1": msa, "present": present})  # "missing" absent
    ctx = _ctx_171({"msa-1": ["present", "missing"]})

    skips = categories._run_171_subpass(ctx, target, tag=None)

    assert msa.SlotsRC.add_log == [present]
    assert len(skips) == 1
    assert skips[0].reason == SkipReason.DEPENDENCY_UNRESOLVED
    assert "missing" in skips[0].detail


def test_171_idempotent_rerun() -> None:
    """Pre-wired MSA + same plan → 0 net writes, 0 skips."""
    slot = _FakeObj("slot-1")
    msa = _FakeTargetMSA("msa-1", prewired=[slot])
    target = _FakeTarget({"msa-1": msa, "slot-1": slot})
    ctx = _ctx_171({"msa-1": ["slot-1"]})

    skips = categories._run_171_subpass(ctx, target, tag=None)

    assert skips == []
    assert msa.SlotsRC.add_log == []
    assert msa.SlotsRC.Count == 1


def test_171_empty_bindings_noop() -> None:
    """Empty plan bindings → no work, empty skip list."""
    ctx = _ctx_171({})
    assert categories._run_171_subpass(ctx, _FakeTarget({}), tag=None) == []


def test_171_skips_are_skip_instances() -> None:
    """Returned skips are model Skip objects (not tuples/strings)."""
    ctx = _ctx_171({"msa-missing": ["slot-1"]})
    skips = categories._run_171_subpass(ctx, _FakeTarget({}), tag=None)
    assert skips and all(isinstance(s, Skip) for s in skips)

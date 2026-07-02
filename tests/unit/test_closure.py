"""T027: dependency-closure BFS (data-model.md / research.md R8).

Pure-Python tests against `Lib/closure.py` using fake `dependencies()`
callables — no LCM / flexlibs2 required.
"""
from __future__ import annotations

from typing import Dict, Iterable, Tuple

import pytest

from gramtrans.Lib.closure import topological, walk
from gramtrans.Lib.models import GrammarCategory

GC = GrammarCategory
Ref = Tuple[GrammarCategory, str]


def _dep_fn_from(graph: Dict[Ref, Tuple[Ref, ...]]):
    """Build a `dependencies(cat, guid)` callable from a fixed graph."""
    def fn(cat: GrammarCategory, guid: str) -> Iterable[Ref]:
        return graph.get((cat, guid), ())
    return fn


def test_leaf_seed_yields_only_itself() -> None:
    seeds = ((GC.INFLECTION_FEATURES, "f1"),)
    graph: Dict[Ref, Tuple[Ref, ...]] = {}
    order, parents = walk(seeds, _dep_fn_from(graph))
    assert order == ((GC.INFLECTION_FEATURES, "f1"),)
    assert parents == {(GC.INFLECTION_FEATURES, "f1"): ()}


def test_simple_chain_template_to_slot_to_affix() -> None:
    seeds = ((GC.AFFIX_TEMPLATES, "t1"),)
    graph = {
        (GC.AFFIX_TEMPLATES, "t1"): ((GC.SLOTS, "s1"),),
        (GC.SLOTS, "s1"): ((GC.AFFIXES, "a1"),),
        (GC.AFFIXES, "a1"): (),
    }
    order, parents = walk(seeds, _dep_fn_from(graph))
    assert order == (
        (GC.AFFIX_TEMPLATES, "t1"),
        (GC.SLOTS, "s1"),
        (GC.AFFIXES, "a1"),
    )
    # Seed has no parent; non-seed nodes record the BFS predecessor.
    assert parents[(GC.AFFIX_TEMPLATES, "t1")] == ()
    assert parents[(GC.SLOTS, "s1")] == ((GC.AFFIX_TEMPLATES, "t1"),)
    assert parents[(GC.AFFIXES, "a1")] == ((GC.SLOTS, "s1"),)


def test_diamond_dependency_dedups_to_single_visit() -> None:
    """Edge Case 'same item appears via two paths' — the shared item is
    transferred exactly once but parents records BOTH ancestors."""
    seeds = ((GC.AFFIXES, "a1"),)
    graph = {
        (GC.AFFIXES, "a1"): (
            (GC.INFLECTION_CLASSES, "ic1"),
            (GC.INFLECTION_FEATURES, "if1"),
        ),
        (GC.INFLECTION_CLASSES, "ic1"): ((GC.GRAM_CATEGORIES, "verb"),),
        (GC.INFLECTION_FEATURES, "if1"): ((GC.GRAM_CATEGORIES, "verb"),),
        (GC.GRAM_CATEGORIES, "verb"): (),
    }
    order, parents = walk(seeds, _dep_fn_from(graph))
    # The shared "verb" GramCategory appears once.
    verb_count = sum(1 for ref in order if ref == (GC.GRAM_CATEGORIES, "verb"))
    assert verb_count == 1
    # Both ancestors are recorded.
    assert set(parents[(GC.GRAM_CATEGORIES, "verb")]) == {
        (GC.INFLECTION_CLASSES, "ic1"),
        (GC.INFLECTION_FEATURES, "if1"),
    }


def test_multiple_seeds_preserve_input_order_first() -> None:
    seeds = (
        (GC.AFFIXES, "a1"),
        (GC.AFFIX_TEMPLATES, "t1"),
    )
    graph = {
        (GC.AFFIXES, "a1"): (),
        (GC.AFFIX_TEMPLATES, "t1"): (),
    }
    order, _ = walk(seeds, _dep_fn_from(graph))
    assert order == ((GC.AFFIXES, "a1"), (GC.AFFIX_TEMPLATES, "t1"))


def test_seed_that_appears_as_dependency_of_another_seed_dedups() -> None:
    """If the user explicitly selects an item AND it would have been pulled
    in as a closure dep, it appears exactly once with seed semantics
    (no parent)."""
    seeds = (
        (GC.AFFIX_TEMPLATES, "t1"),
        (GC.SLOTS, "s1"),  # explicit pick; also dep of t1
    )
    graph = {
        (GC.AFFIX_TEMPLATES, "t1"): ((GC.SLOTS, "s1"),),
        (GC.SLOTS, "s1"): (),
    }
    order, parents = walk(seeds, _dep_fn_from(graph))
    assert order == ((GC.AFFIX_TEMPLATES, "t1"), (GC.SLOTS, "s1"))
    # Because it was a seed, its parents stay empty (seed semantics win).
    assert parents[(GC.SLOTS, "s1")] == ()


def test_cycle_is_handled_without_infinite_loop() -> None:
    """LCM doesn't normally produce cycles in dependency closures, but the
    walker MUST be robust against them (defensive)."""
    seeds = ((GC.AFFIXES, "a1"),)
    graph = {
        (GC.AFFIXES, "a1"): ((GC.AFFIXES, "a2"),),
        (GC.AFFIXES, "a2"): ((GC.AFFIXES, "a1"),),  # cycle
    }
    order, _ = walk(seeds, _dep_fn_from(graph))
    assert set(order) == {(GC.AFFIXES, "a1"), (GC.AFFIXES, "a2")}


def test_topological_reverses_visit_order_for_dependencies_first() -> None:
    """`topological(order, parents)` returns dependencies before dependents
    so the executor can owner-attach safely."""
    seeds = ((GC.AFFIX_TEMPLATES, "t1"),)
    graph = {
        (GC.AFFIX_TEMPLATES, "t1"): ((GC.SLOTS, "s1"),),
        (GC.SLOTS, "s1"): ((GC.AFFIXES, "a1"),),
        (GC.AFFIXES, "a1"): (),
    }
    order, parents = walk(seeds, _dep_fn_from(graph))
    topo = topological(order, parents)
    assert topo == (
        (GC.AFFIXES, "a1"),
        (GC.SLOTS, "s1"),
        (GC.AFFIX_TEMPLATES, "t1"),
    )


def test_topological_dag_with_shared_leaf_orders_leaf_before_both_seeds() -> None:
    """The old 'just reverse visit_order' impl was WRONG for DAGs: two seeds
    pulling in a shared leaf could land before the leaf. Kahn's algorithm
    correctly puts the leaf first."""
    seeds = ((GC.AFFIXES, "a1"), (GC.AFFIXES, "a2"))
    # Both a1 and a2 depend on the same inflection feature f1.
    graph = {
        (GC.AFFIXES, "a1"): ((GC.INFLECTION_FEATURES, "f1"),),
        (GC.AFFIXES, "a2"): ((GC.INFLECTION_FEATURES, "f1"),),
        (GC.INFLECTION_FEATURES, "f1"): (),
    }
    order, parents = walk(seeds, _dep_fn_from(graph))
    topo = topological(order, parents)
    # f1 must precede both a1 and a2.
    pos_f1 = topo.index((GC.INFLECTION_FEATURES, "f1"))
    pos_a1 = topo.index((GC.AFFIXES, "a1"))
    pos_a2 = topo.index((GC.AFFIXES, "a2"))
    assert pos_f1 < pos_a1
    assert pos_f1 < pos_a2


def test_topological_seed_with_no_deps_emits_in_visit_order() -> None:
    """Two independent seeds with no deps emit in their original visit order."""
    seeds = ((GC.AFFIXES, "a"), (GC.AFFIX_TEMPLATES, "t"))
    graph = {(GC.AFFIXES, "a"): (), (GC.AFFIX_TEMPLATES, "t"): ()}
    order, parents = walk(seeds, _dep_fn_from(graph))
    topo = topological(order, parents)
    assert topo == ((GC.AFFIXES, "a"), (GC.AFFIX_TEMPLATES, "t"))


def test_topological_cycle_returns_all_nodes_without_infinite_loop() -> None:
    """If a cycle sneaks in, topological must still terminate and emit every
    node exactly once (cycle members appended after the acyclic prefix)."""
    seeds = ((GC.AFFIXES, "a"),)
    graph = {
        (GC.AFFIXES, "a"): ((GC.AFFIXES, "b"),),
        (GC.AFFIXES, "b"): ((GC.AFFIXES, "a"),),
    }
    order, parents = walk(seeds, _dep_fn_from(graph))
    topo = topological(order, parents)
    assert set(topo) == {(GC.AFFIXES, "a"), (GC.AFFIXES, "b")}
    assert len(topo) == 2


def test_seed_iterable_is_consumed_once() -> None:
    """`walk` must work with a one-shot generator, not require a list."""
    seeds = ((GC.AFFIXES, f"a{i}") for i in range(3))
    graph: Dict[Ref, Tuple[Ref, ...]] = {
        (GC.AFFIXES, "a0"): (),
        (GC.AFFIXES, "a1"): (),
        (GC.AFFIXES, "a2"): (),
    }
    order, _ = walk(seeds, _dep_fn_from(graph))
    assert order == (
        (GC.AFFIXES, "a0"),
        (GC.AFFIXES, "a1"),
        (GC.AFFIXES, "a2"),
    )


# ============================================================================
# Edge cases — tests 1-6 from the extension task
# ============================================================================

def test_empty_seeds_returns_empty_order_and_empty_parents() -> None:
    """walk((), dep_fn) with no seeds yields an empty order and empty parents dict."""
    order, parents = walk((), _dep_fn_from({}))
    assert order == ()
    assert parents == {}


def test_single_seed_self_cycle_no_infinite_loop() -> None:
    """A node whose only dependency is itself must not cause an infinite loop
    and must appear exactly once in the result."""
    seeds = ((GC.AFFIXES, "a1"),)
    graph = {
        (GC.AFFIXES, "a1"): ((GC.AFFIXES, "a1"),),
    }
    order, parents = walk(seeds, _dep_fn_from(graph))
    assert order == ((GC.AFFIXES, "a1"),)
    # Self-cycle: the back-edge is from seed to itself, seed semantics win.
    assert parents[(GC.AFFIXES, "a1")] == ()


def test_multi_branch_fanout_bfs_order() -> None:
    """Seed A depends on siblings B, C, D (none related to each other).
    BFS visit order must be A then B, C, D in the order they are listed."""
    seeds = ((GC.AFFIX_TEMPLATES, "A"),)
    graph = {
        (GC.AFFIX_TEMPLATES, "A"): (
            (GC.SLOTS, "B"),
            (GC.SLOTS, "C"),
            (GC.SLOTS, "D"),
        ),
        (GC.SLOTS, "B"): (),
        (GC.SLOTS, "C"): (),
        (GC.SLOTS, "D"): (),
    }
    order, _ = walk(seeds, _dep_fn_from(graph))
    assert order == (
        (GC.AFFIX_TEMPLATES, "A"),
        (GC.SLOTS, "B"),
        (GC.SLOTS, "C"),
        (GC.SLOTS, "D"),
    )


def test_topological_on_empty_input_returns_empty() -> None:
    """`topological((), {})` on empty visit_order returns ()."""
    assert topological((), {}) == ()


def test_topological_on_single_item_returns_same() -> None:
    """Single-item visit_order round-trips through topological unchanged."""
    ref = (GC.AFFIXES, "a1")
    assert topological((ref,), {ref: ()}) == (ref,)


def test_parent_tracking_is_order_stable() -> None:
    """If X is reached from Y first and then from Z, parents[X] records
    (Y, Z) in that encounter order — not reversed, not a set."""
    seeds = ((GC.AFFIXES, "y"), (GC.AFFIXES, "z"))
    graph = {
        (GC.AFFIXES, "y"): ((GC.GRAM_CATEGORIES, "x"),),
        (GC.AFFIXES, "z"): ((GC.GRAM_CATEGORIES, "x"),),
        (GC.GRAM_CATEGORIES, "x"): (),
    }
    order, parents = walk(seeds, _dep_fn_from(graph))
    # X appears once in visit order.
    assert (GC.GRAM_CATEGORIES, "x") in order
    # Y is encountered first (first seed), so Y must come before Z in parents.
    p = parents[(GC.GRAM_CATEGORIES, "x")]
    assert p == ((GC.AFFIXES, "y"), (GC.AFFIXES, "z"))

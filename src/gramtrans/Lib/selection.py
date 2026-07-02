"""Selection helpers (T073, spec.md FR-007 / Clarification Q4).

Pure-Python translation between the affix-tree picker's output (template /
slot / affix node toggles) and the `Selection.affix_picks` /
`Selection.template_picks` frozenset that the closure walker consumes.

The tree-picker UI emits a `PickerState` describing which template, slot,
and individual affix nodes are checked. This module collapses that state
into the canonical Selection shape — selecting a template implicitly
selects every affix under it via slot membership, etc.

POS-Grouped Affix Inventory (specs/008-affix-pos-picker):
    - AffixRow, PosNode, JunkDrawer, PosGroupedAffixInventory: pure frozen
      dataclasses (no LCM handles retained after build).
    - build_pos_grouped_inventory(source): enumerates LexDbOA.Entries,
      dispatches on msa.ClassName, builds POS hierarchy.
    - collapse_pos_grouped(checked_guids, inventory): returns Selection.
    - mirror_check_state(items, new_state): pure helper for Qt itemChanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

if __package__:
    from .models import CategoryScope, GrammarCategory, Selection
else:
    from models import CategoryScope, GrammarCategory, Selection  # type: ignore


# ---------------------------------------------------------------------------
# pythonnet cast helper
# ---------------------------------------------------------------------------

def _cast(obj, interface_name: str):
    """Cast obj to a concrete LCM interface by name (pythonnet pattern).

    Imports the interface lazily so unit tests using fake handles never
    require pythonnet.  If the import fails (no pythonnet in scope) or
    the cast raises, returns obj unchanged -- the caller's guarded
    try/except then handles AttributeError gracefully.

    Parameters
    ----------
    obj:
        The LCM object to cast.
    interface_name:
        Dotted import path OR just the simple name of the interface in
        ``SIL.LCModel``.  For example ``"ILexEntry"`` resolves to
        ``SIL.LCModel.ILexEntry``.

    Returns
    -------
    The cast object, or ``obj`` unchanged when pythonnet is unavailable.
    """
    try:
        import importlib
        lcm = importlib.import_module("SIL.LCModel")
        iface = getattr(lcm, interface_name)
        return iface(obj)
    except Exception:  # noqa: BLE001 -- pythonnet absent or cast failed
        return obj


# ============================================================================
# POS-Grouped Affix Inventory (specs/008-affix-pos-picker, T008-T010)
# ============================================================================

@dataclass(frozen=True)
class AffixRow:
    """One affix as shown in one group appearance (data-model.md).

    Row identity within a group: (entry_guid, pos_guid, role).
    Multiple senses/MSAs of the same entry landing in the same (pos_guid, role)
    collapse into one row with glosses merged.
    """
    entry_guid: str
    form: str
    glosses: str
    msa_kind: str          # "infl" | "deriv" | "uncl"
    from_pos: Optional[str]  # attaches-to POS label for this appearance
    to_pos: Optional[str]    # produces POS label (deriv only)
    role: str              # "attaches" | "produces"


@dataclass(frozen=True)
class PosNode:
    """A node in the POS hierarchy carrying the affixes attached to / produced by it."""
    pos_guid: str
    label: str
    children: Tuple["PosNode", ...]
    inflectional: Tuple[AffixRow, ...]    # infl + uncl attaches-to rows
    deriv_attaches: Tuple[AffixRow, ...]  # deriv From = this POS
    deriv_produces: Tuple[AffixRow, ...]  # deriv To = this POS (NOT swept by header)


@dataclass(frozen=True)
class JunkDrawer:
    """Affixes that could not be placed in any POS group."""
    no_pos: Tuple[AffixRow, ...]      # has >= 1 MSA but no readable POS
    no_analysis: Tuple[AffixRow, ...]  # no sense / no MSA


@dataclass(frozen=True)
class PosGroupedAffixInventory:
    """Top-level result of build_pos_grouped_inventory."""
    roots: Tuple[PosNode, ...]
    junk: JunkDrawer

    def all_affix_guids(self) -> FrozenSet[str]:
        """Return all affix GUIDs in the inventory, deduplicated."""
        guids: Set[str] = set()

        def _collect_node(node: PosNode) -> None:
            for row in node.inflectional:
                guids.add(row.entry_guid)
            for row in node.deriv_attaches:
                guids.add(row.entry_guid)
            for row in node.deriv_produces:
                guids.add(row.entry_guid)
            for child in node.children:
                _collect_node(child)

        for root in self.roots:
            _collect_node(root)
        for row in self.junk.no_pos:
            guids.add(row.entry_guid)
        for row in self.junk.no_analysis:
            guids.add(row.entry_guid)
        return frozenset(guids)


# ---------------------------------------------------------------------------
# Internal builder helpers
# ---------------------------------------------------------------------------

def _pos_label(pos) -> str:
    """Extract label from a POS object: Abbreviation preferred, then Name.

    Casts to ICmPossibility before accessing .Abbreviation / .Name so
    pythonnet resolves against the declared concrete interface, not ICmObject.
    """
    pos_c = _cast(pos, "ICmPossibility")
    try:
        abbrev = pos_c.Abbreviation.BestAnalysisAlternative.Text
        if abbrev and abbrev not in ("***", ""):
            return abbrev
    except (AttributeError, TypeError):
        pass
    try:
        name = pos_c.Name.BestAnalysisAlternative.Text
        if name and name not in ("***", ""):
            return name
    except (AttributeError, TypeError):
        pass
    # Both Abbreviation and Name are empty ('***'/blank). Do NOT fall back to the
    # raw GUID (unreadable in the UI); a genuinely blank-named POS reads as
    # "(unnamed POS)". Such nodes are usually pruned anyway when they hold no
    # affixes, but a blank-named POS that DOES carry affixes still needs a label.
    return "(unnamed POS)"


def _pos_guid(pos) -> Optional[str]:
    """Return the GUID string of a POS object, or None.

    Casts to ICmPossibility for consistency (Guid is on ICmObject, but
    keeping the cast uniform ensures any subclass re-dispatch is stable).
    """
    pos_c = _cast(pos, "ICmPossibility")
    try:
        g = pos_c.Guid
        if g is None:
            return None
        return str(g).lower()
    except (AttributeError, TypeError):
        pass
    # Fallback: try raw obj in case cast returned obj unchanged
    try:
        g = pos.Guid
        if g is None:
            return None
        return str(g).lower()
    except (AttributeError, TypeError):
        return None


def _best_form(entry) -> str:
    """Best-vernacular lexeme form of an entry.

    Casts entry to ILexEntry before accessing .LexemeFormOA, then casts
    the form to IMultiAccessorBase before reading .BestVernacularAlternative.
    """
    entry_c = _cast(entry, "ILexEntry")
    try:
        form_obj = entry_c.LexemeFormOA
        form_c = _cast(form_obj.Form, "IMultiAccessorBase")
        text = form_c.BestVernacularAlternative.Text
        if text and text not in ("***", ""):
            return text
    except (AttributeError, TypeError):
        pass
    return "?"


def _collect_glosses(entry) -> str:
    """Collect deduplicated glosses from all senses, joined with '; '.

    Casts entry to ILexEntry before iterating .SensesOS, and each sense
    to ILexSense before reading .Gloss.
    """
    entry_c = _cast(entry, "ILexEntry")
    seen: List[str] = []
    try:
        for sense in entry_c.SensesOS:
            sense_c = _cast(sense, "ILexSense")
            try:
                text = sense_c.Gloss.BestAnalysisAlternative.Text
                if text and text not in ("***", "", "(no gloss)") and text not in seen:
                    seen.append(text)
            except (AttributeError, TypeError):
                pass
    except (AttributeError, TypeError):
        pass
    return "; ".join(seen) if seen else "(no gloss)"


def _build_pos_tree(possibilities) -> Tuple[List[PosNode], Dict[str, "_PosAccumulator"]]:
    """Recursively build PosNode stubs and an accumulator dict keyed by pos_guid."""
    accumulators: Dict[str, "_PosAccumulator"] = {}

    def _build(pos_list) -> List[PosNode]:
        result = []
        for pos in pos_list:
            try:
                guid = _pos_guid(pos)
                if guid is None:
                    continue
                label = _pos_label(pos)
                sub = []
                try:
                    sub = list(pos.SubPossibilitiesOS)
                except (AttributeError, TypeError):
                    pass
                child_nodes = _build(sub)
                acc = _PosAccumulator(guid, label)
                accumulators[guid] = acc
                # Link children accumulators (already built)
                acc.child_accs = [accumulators[cn.pos_guid] for cn in child_nodes
                                  if cn.pos_guid in accumulators]
                acc.child_nodes_ordered = child_nodes
                result.append(acc)
            except Exception:  # noqa: BLE001 - defensive per-object skip
                pass
        return result  # type: ignore[return-value]

    roots = _build(list(possibilities))
    return roots, accumulators  # type: ignore[return-value]


class _PosAccumulator:
    """Mutable accumulator for rows during the build phase."""
    __slots__ = ("pos_guid", "label", "inflectional", "deriv_attaches",
                 "deriv_produces", "child_accs", "child_nodes_ordered")

    def __init__(self, pos_guid: str, label: str):
        self.pos_guid = pos_guid
        self.label = label
        self.inflectional: List[AffixRow] = []
        self.deriv_attaches: List[AffixRow] = []
        self.deriv_produces: List[AffixRow] = []
        self.child_accs: List["_PosAccumulator"] = []
        self.child_nodes_ordered: List["_PosAccumulator"] = []

    def freeze(self) -> PosNode:
        return PosNode(
            pos_guid=self.pos_guid,
            label=self.label,
            children=tuple(c.freeze() for c in self.child_nodes_ordered),
            inflectional=tuple(sorted(self.inflectional, key=lambda r: r.form)),
            deriv_attaches=tuple(sorted(self.deriv_attaches, key=lambda r: r.form)),
            deriv_produces=tuple(sorted(self.deriv_produces, key=lambda r: r.form)),
        )


def build_pos_grouped_inventory(source) -> PosGroupedAffixInventory:
    """Build a PosGroupedAffixInventory from the source project.

    Parameters
    ----------
    source:
        Duck-typed source handle exposing:
        - source.Cache.LangProject.LexDbOA.Entries
        - source.Cache.LangProject.PartsOfSpeechOA.PossibilitiesOS (recursive)

    Returns
    -------
    PosGroupedAffixInventory
        Pure frozen result; retains no LCM handles.
    """
    # --- Build POS hierarchy ---
    try:
        pos_possibilities = list(
            source.Cache.LangProject.PartsOfSpeechOA.PossibilitiesOS
        )
    except (AttributeError, TypeError):
        pos_possibilities = []

    root_accs, acc_by_guid = _build_pos_tree(pos_possibilities)

    # --- Collect and filter entries ---
    try:
        entries = list(source.Cache.LangProject.LexDbOA.Entries)
    except (AttributeError, TypeError):
        entries = []

    no_pos_rows: List[AffixRow] = []
    no_analysis_rows: List[AffixRow] = []

    for entry in entries:
        # Filter to affix entries; cast to ILexEntry before reading LexemeFormOA
        entry_c = _cast(entry, "ILexEntry")
        try:
            form_obj = entry_c.LexemeFormOA
            morph_type = _cast(form_obj.MorphTypeRA, "IMoMorphType")
            is_affix = morph_type.IsAffixType
            if not is_affix:
                continue
        except (AttributeError, TypeError):
            continue

        try:
            guid = str(entry.Guid).lower()
        except (AttributeError, TypeError):
            continue

        form = _best_form(entry)
        glosses = _collect_glosses(entry)

        # Collect MSAs
        try:
            msas = list(entry.MorphoSyntaxAnalysesOC)
        except (AttributeError, TypeError):
            msas = []

        if not msas:
            # No MSA -> no_analysis junk
            no_analysis_rows.append(AffixRow(
                entry_guid=guid, form=form, glosses=glosses,
                msa_kind="uncl", from_pos=None, to_pos=None, role="attaches",
            ))
            continue

        # Track which (pos_guid, role) combos this entry contributes to
        placed: Set[Tuple[str, str]] = set()
        any_placed = False

        for msa in msas:
            try:
                class_name = msa.ClassName
            except (AttributeError, TypeError):
                class_name = None

            if class_name == "MoInflAffMsa":
                try:
                    msa_c = _cast(msa, "IMoInflAffMsa")
                    pos = msa_c.PartOfSpeechRA
                    if pos is None:
                        continue
                    pg = _pos_guid(pos)
                    if pg is None:
                        continue
                    pl = _pos_label(pos)
                    key = (pg, "attaches")
                    if key in placed:
                        # Merge glosses into existing row
                        if pg in acc_by_guid:
                            acc = acc_by_guid[pg]
                            _merge_row_glosses(acc.inflectional, guid, glosses)
                        continue
                    placed.add(key)
                    row = AffixRow(guid, form, glosses, "infl", pl, None, "attaches")
                    if pg in acc_by_guid:
                        acc_by_guid[pg].inflectional.append(row)
                        any_placed = True
                    else:
                        # Defensive: create a root node for unknown POS guid
                        new_acc = _PosAccumulator(pg, pl)
                        acc_by_guid[pg] = new_acc
                        root_accs.append(new_acc)
                        new_acc.inflectional.append(row)
                        any_placed = True
                except (AttributeError, TypeError):
                    pass

            elif class_name == "MoUnclassifiedAffixMsa":
                try:
                    msa_c = _cast(msa, "IMoUnclassifiedAffixMsa")
                    pos = msa_c.PartOfSpeechRA
                    # IMoUnclassifiedAffixMsa.PartOfSpeechRA CAN be null -> junk
                    if pos is None:
                        continue
                    pg = _pos_guid(pos)
                    if pg is None:
                        continue
                    pl = _pos_label(pos)
                    key = (pg, "attaches")
                    if key in placed:
                        if pg in acc_by_guid:
                            _merge_row_glosses(acc_by_guid[pg].inflectional, guid, glosses)
                        continue
                    placed.add(key)
                    row = AffixRow(guid, form, glosses, "uncl", pl, None, "attaches")
                    if pg in acc_by_guid:
                        acc_by_guid[pg].inflectional.append(row)
                        any_placed = True
                    else:
                        new_acc = _PosAccumulator(pg, pl)
                        acc_by_guid[pg] = new_acc
                        root_accs.append(new_acc)
                        new_acc.inflectional.append(row)
                        any_placed = True
                except (AttributeError, TypeError):
                    pass

            elif class_name == "MoDerivAffMsa":
                try:
                    msa_c = _cast(msa, "IMoDerivAffMsa")
                    from_pos = msa_c.FromPartOfSpeechRA
                    to_pos = msa_c.ToPartOfSpeechRA
                    from_pg = _pos_guid(from_pos) if from_pos is not None else None
                    to_pg = _pos_guid(to_pos) if to_pos is not None else None
                    from_pl = _pos_label(from_pos) if from_pos is not None else None
                    to_pl = _pos_label(to_pos) if to_pos is not None else None

                    if from_pg is not None:
                        key = (from_pg, "attaches")
                        if key not in placed:
                            placed.add(key)
                            row = AffixRow(guid, form, glosses, "deriv",
                                          from_pl, to_pl, "attaches")
                            if from_pg in acc_by_guid:
                                acc_by_guid[from_pg].deriv_attaches.append(row)
                            else:
                                new_acc = _PosAccumulator(from_pg, from_pl or from_pg)
                                acc_by_guid[from_pg] = new_acc
                                root_accs.append(new_acc)
                                new_acc.deriv_attaches.append(row)
                            any_placed = True

                    if to_pg is not None:
                        key = (to_pg, "produces")
                        if key not in placed:
                            placed.add(key)
                            row = AffixRow(guid, form, glosses, "deriv",
                                          from_pl, to_pl, "produces")
                            if to_pg in acc_by_guid:
                                acc_by_guid[to_pg].deriv_produces.append(row)
                            else:
                                new_acc = _PosAccumulator(to_pg, to_pl or to_pg)
                                acc_by_guid[to_pg] = new_acc
                                root_accs.append(new_acc)
                                new_acc.deriv_produces.append(row)
                            any_placed = True

                except (AttributeError, TypeError):
                    pass

            else:
                # Unrecognized ClassName -> treat as no-POS junk below
                pass

        if not any_placed:
            # Entry has MSAs but none contributed to any POS group
            no_pos_rows.append(AffixRow(
                entry_guid=guid, form=form, glosses=glosses,
                msa_kind="uncl", from_pos=None, to_pos=None, role="attaches",
            ))

    # --- Freeze the hierarchy, then prune POS nodes that hold no affixes ---
    # A node is kept iff it carries affix rows itself OR has a surviving
    # descendant (so the hierarchy path to a populated sub-POS is preserved).
    # This drops parts of speech with nothing to transfer -- including blank /
    # unnamed POSes the user never populated.
    frozen_roots = tuple(
        n for n in (_prune_empty(acc.freeze()) for acc in root_accs) if n is not None
    )
    junk = JunkDrawer(
        no_pos=tuple(sorted(no_pos_rows, key=lambda r: r.form)),
        no_analysis=tuple(sorted(no_analysis_rows, key=lambda r: r.form)),
    )
    result = PosGroupedAffixInventory(roots=frozen_roots, junk=junk)

    # Guard: if every affix landed in the junk drawer (placed==0) warn rather
    # than silently returning an empty grouping -- this surfaces cast failures
    # that would otherwise produce false confidence.
    import logging as _logging
    placed_total = sum(
        len(nd.inflectional) + len(nd.deriv_attaches) + len(nd.deriv_produces)
        for nd in frozen_roots
    ) + sum(len(c.inflectional) + len(c.deriv_attaches) + len(c.deriv_produces)
            for nd in frozen_roots for c in nd.children)
    junk_total = len(junk.no_pos) + len(junk.no_analysis)
    if placed_total == 0 and junk_total > 0:
        _logging.getLogger(__name__).warning(
            "build_pos_grouped_inventory: every affix (%d) landed in the junk "
            "drawer (placed=0). This may indicate pythonnet cast failures or a "
            "malformed source. Check LCM interface availability.",
            junk_total,
        )

    return result


def _prune_empty(node: PosNode) -> Optional[PosNode]:
    """Return `node` with empty descendant POS nodes removed, or None if the
    whole subtree carries no affixes.

    A node survives iff it holds any affix row (inflectional, deriv_attaches, or
    deriv_produces) OR at least one descendant survives -- so an intermediate POS
    with no affixes of its own is kept only as a path to a populated sub-POS.
    """
    kept_children = tuple(
        c for c in (_prune_empty(ch) for ch in node.children) if c is not None
    )
    has_rows = bool(node.inflectional or node.deriv_attaches or node.deriv_produces)
    if not has_rows and not kept_children:
        return None
    if kept_children == node.children:
        return node
    return PosNode(
        pos_guid=node.pos_guid,
        label=node.label,
        children=kept_children,
        inflectional=node.inflectional,
        deriv_attaches=node.deriv_attaches,
        deriv_produces=node.deriv_produces,
    )


def _merge_row_glosses(rows: List[AffixRow], entry_guid: str, new_glosses: str) -> None:
    """Merge new_glosses into an existing row for entry_guid (in-place on mutable list)."""
    for i, row in enumerate(rows):
        if row.entry_guid == entry_guid:
            # Merge glosses: combine, dedup
            existing = [g.strip() for g in row.glosses.split(";")
                       if g.strip() and g.strip() != "(no gloss)"]
            new_parts = [g.strip() for g in new_glosses.split(";")
                        if g.strip() and g.strip() != "(no gloss)"]
            merged: List[str] = []
            for g in existing + new_parts:
                if g not in merged:
                    merged.append(g)
            combined = "; ".join(merged) if merged else "(no gloss)"
            rows[i] = AffixRow(
                entry_guid=row.entry_guid,
                form=row.form,
                glosses=combined,
                msa_kind=row.msa_kind,
                from_pos=row.from_pos,
                to_pos=row.to_pos,
                role=row.role,
            )
            return


# ---------------------------------------------------------------------------
# collapse_pos_grouped  (T010)
# ---------------------------------------------------------------------------

def collapse_pos_grouped(
    checked_guids: Iterable[str],
    inventory: PosGroupedAffixInventory,
) -> Selection:
    """Collapse checked leaf-row entry GUIDs into a Selection.

    Parameters
    ----------
    checked_guids:
        The set of entry_guids that are checked in the picker tree.
    inventory:
        The PosGroupedAffixInventory built for the current source.

    Returns
    -------
    Selection
        affix_picks = deduped intersection with inventory.all_affix_guids();
        template_picks = frozenset(); categories populated when picks non-empty.
    """
    all_known = inventory.all_affix_guids()
    deduped = frozenset(checked_guids) & all_known
    picker = PickerState(checked_affixes=deduped)
    # Build a dummy SourceAffixInventory so we can reuse build_selection.
    dummy_inv = SourceAffixInventory(unbound_affixes=deduped)
    return build_selection(picker, dummy_inv)


# ---------------------------------------------------------------------------
# mirror_check_state  (T010)
# ---------------------------------------------------------------------------

def mirror_check_state(all_items_for_guid: list, new_state) -> list:
    """Pure helper: return list of (item, new_state) for every appearance.

    The Qt itemChanged handler applies these assignments under a _mirroring
    re-entrancy guard to prevent signal recursion.

    Parameters
    ----------
    all_items_for_guid:
        All tree items (any type) that share the same entry_guid.
    new_state:
        The newly-set check state to propagate to every appearance.

    Returns
    -------
    list of (item, new_state)
    """
    return [(item, new_state) for item in all_items_for_guid]


# ============================================================================
# Source inventory shape (the tree picker's input)
# ============================================================================

@dataclass(frozen=True)
class SourceAffixInventory:
    """A flattened view of the source's affix tree used by both the UI tree
    picker and these selection helpers.

    `template_to_slots` maps template GUID → tuple of slot GUIDs.
    `slot_to_affixes` maps slot GUID → tuple of affix GUIDs filling that slot.
    `unbound_affixes` is the set of affix GUIDs not attached to any template.
    """
    template_to_slots: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    slot_to_affixes: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    unbound_affixes: FrozenSet[str] = field(default_factory=frozenset)

    def all_affix_guids(self) -> FrozenSet[str]:
        affixes: Set[str] = set(self.unbound_affixes)
        for slot_affixes in self.slot_to_affixes.values():
            affixes.update(slot_affixes)
        return frozenset(affixes)

    def all_template_guids(self) -> FrozenSet[str]:
        return frozenset(self.template_to_slots.keys())


# ============================================================================
# Picker state (the UI's checked-node bag)
# ============================================================================

@dataclass(frozen=True)
class PickerState:
    """What the tree picker reports back: three sets of explicitly-checked
    node GUIDs at different tree levels. The semantic 'selecting a template
    selects all its affixes' is collapsed in `compute_required_affixes`."""
    checked_templates: FrozenSet[str] = field(default_factory=frozenset)
    checked_slots: FrozenSet[str] = field(default_factory=frozenset)
    checked_affixes: FrozenSet[str] = field(default_factory=frozenset)


# ============================================================================
# Public helpers (T073)
# ============================================================================

def compute_required_affixes(
    picker: PickerState,
    inventory: SourceAffixInventory,
) -> FrozenSet[str]:
    """Collapse picker state to the affix GUID set the closure walker needs.

    Resolution rules (Q4):
    1. Every explicitly-checked affix is included.
    2. Every affix under an explicitly-checked slot is included.
    3. Every affix under any slot of an explicitly-checked template is included.
    4. Unknown GUIDs (in `checked_*` but not in `inventory`) are ignored —
       the picker can't render them, so it shouldn't emit them, but the
       collapse is defensive.
    """
    affixes: Set[str] = set()

    affixes.update(picker.checked_affixes & inventory.all_affix_guids())

    for slot_guid in picker.checked_slots:
        affixes.update(inventory.slot_to_affixes.get(slot_guid, ()))

    for tpl_guid in picker.checked_templates:
        for slot_guid in inventory.template_to_slots.get(tpl_guid, ()):
            affixes.update(inventory.slot_to_affixes.get(slot_guid, ()))

    return frozenset(affixes)


def compute_required_templates(picker: PickerState,
                               inventory: SourceAffixInventory) -> FrozenSet[str]:
    """The set of template GUIDs that should land in `Selection.template_picks`.

    Currently a pass-through of `picker.checked_templates` filtered against the
    inventory (defensive). Slot- or affix-level checks do NOT pull templates
    in — templates are only transferred when explicitly selected at that level.
    """
    return frozenset(picker.checked_templates & inventory.all_template_guids())


def build_selection(picker: PickerState,
                    inventory: SourceAffixInventory,
                    *,
                    include_closure: bool = True,
                    extra_categories: Iterable[GrammarCategory] = (),
                    category_scopes: Optional[Dict[GrammarCategory, CategoryScope]] = None,
                    excluded_deps: Optional[FrozenSet[str]] = None) -> Selection:
    """Build a `Selection` from the picker state + inventory.

    `extra_categories` is the list of FR-004 categories the user toggled on
    OUTSIDE the affix tree (e.g., custom fields, inflection features). These
    land in `Selection.categories` with True values; AFFIXES/AFFIX_TEMPLATES are
    set True automatically iff the picker yields non-empty picks for them.

    Phase 3c Selection UI additions:
    - `category_scopes`: per-category three-scope map (NONE / AS_NEEDED / ALL).
      When supplied, the old `include_closure` bool is still accepted for
      back-compat but explicit scopes take precedence per `Selection.scope_for`.
    - `excluded_deps`: frozenset of source GUIDs the user per-item deselected.
    """
    affix_picks = compute_required_affixes(picker, inventory)
    template_picks = compute_required_templates(picker, inventory)

    categories: Dict[GrammarCategory, bool] = {cat: True for cat in extra_categories}
    if affix_picks:
        categories[GrammarCategory.AFFIXES] = True
    if template_picks:
        categories[GrammarCategory.AFFIX_TEMPLATES] = True

    return Selection(
        categories=categories,
        include_closure=include_closure,
        affix_picks=affix_picks,
        template_picks=template_picks,
        category_scopes=dict(category_scopes) if category_scopes else {},
        excluded_deps=excluded_deps if excluded_deps is not None else frozenset(),
    )

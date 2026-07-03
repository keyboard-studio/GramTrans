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

import logging as _logging
from dataclasses import dataclass, field
from typing import Callable, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

from gramtrans.Lib.ws_fonts import LabelRun, WsRole, runs_to_text

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
    status: Optional[str] = None  # FR-018: "new" | "in_target" | "similar" | None


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


# Separator between an affix's vernacular form and its analysis gloss in the
# item-picker tree. Kept here (not in the UI) so the WS-run split and the flat
# label stay defined together. `runs_to_text(affix_label_runs(...))` == the old
# `f"{form}  ->  {glosses}"` label.
_AFFIX_FORM_GLOSS_SEP = "  ->  "


def affix_label_runs(form: str, glosses: str) -> Tuple[LabelRun, ...]:
    """WS-tagged runs for an affix row label (spec 011).

    The lexeme form is vernacular; the gloss is analysis; the ' -> ' separator
    carries no WS. Rendered per-run so the form shows in the vernacular font and
    the gloss in the analysis font within the same tree cell.
    """
    return (
        (form or "", WsRole.VERNACULAR),
        (_AFFIX_FORM_GLOSS_SEP, None),
        (glosses or "", WsRole.ANALYSIS),
    )


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


def _build_target_sets(target) -> Tuple[Set[str], Set[str]]:
    """Build (target_guids, target_forms) from the target project for FR-018.

    Both sets are built by enumerating the TARGET's affix entries with the
    same IsAffixType filter + casts used for source entries.

    Returns
    -------
    target_guids : set of lower-cased entry GUID strings
    target_forms : set of stripped/casefold best-vernacular lexeme forms
    """
    target_guids: Set[str] = set()
    target_forms: Set[str] = set()
    try:
        entries = list(target.Cache.LangProject.LexDbOA.Entries)
    except (AttributeError, TypeError):
        return target_guids, target_forms

    for entry in entries:
        entry_c = _cast(entry, "ILexEntry")
        try:
            form_obj = entry_c.LexemeFormOA
            morph_type = _cast(form_obj.MorphTypeRA, "IMoMorphType")
            if not morph_type.IsAffixType:
                continue
        except (AttributeError, TypeError):
            continue
        try:
            g = str(entry.Guid).lower()
            target_guids.add(g)
        except (AttributeError, TypeError):
            pass
        f = _best_form(entry)
        if f and f != "?":
            target_forms.add(f.strip().casefold())

    return target_guids, target_forms


def _entry_status(entry_guid: str, form: str,
                  target_guids: Set[str], target_forms: Set[str]) -> str:
    """Compute FR-018 status for one source affix entry."""
    if entry_guid in target_guids:
        return "in_target"
    normalized = form.strip().casefold()
    if normalized and normalized in target_forms:
        return "similar"
    return "new"


def _build_skeleton_target_sets(target) -> Tuple[Set[str], Set[str], Set[str]]:
    """Build (target_pos_guids, target_slot_guids, target_template_guids) for FR-009.

    Enumerates the TARGET project's POS hierarchy to collect per-kind GUID sets
    for POS, IMoInflAffixSlot, and IMoInflAffixTemplate objects.  Used by
    build_skeleton_inventory to classify skeleton rows by GUID membership in the
    matching per-kind set rather than against the affix-entry set.

    Returns
    -------
    target_pos_guids : set of lower-cased POS GUID strings
    target_slot_guids : set of lower-cased slot GUID strings
    target_template_guids : set of lower-cased template GUID strings
    """
    target_pos_guids: Set[str] = set()
    target_slot_guids: Set[str] = set()
    target_template_guids: Set[str] = set()

    try:
        pos_possibilities = list(
            target.Cache.LangProject.PartsOfSpeechOA.PossibilitiesOS
        )
    except (AttributeError, TypeError):
        return target_pos_guids, target_slot_guids, target_template_guids

    def _walk_pos_skeleton(pos_list):
        for pos in pos_list:
            pg = _pos_guid(pos)
            if pg:
                target_pos_guids.add(pg)
            pos_c = _cast(pos, "IPartOfSpeech")
            # Slots
            try:
                for sl in pos_c.AffixSlotsOC:
                    sl_c = _cast(sl, "IMoInflAffixSlot")
                    try:
                        sg = str(sl_c.Guid).lower()
                    except (AttributeError, TypeError):
                        try:
                            sg = str(sl.Guid).lower()
                        except (AttributeError, TypeError):
                            continue
                    target_slot_guids.add(sg)
            except (AttributeError, TypeError):
                pass
            # Templates
            try:
                for tpl in pos_c.AffixTemplatesOS:
                    tpl_c = _cast(tpl, "IMoInflAffixTemplate")
                    try:
                        tg = str(tpl_c.Guid).lower()
                    except (AttributeError, TypeError):
                        try:
                            tg = str(tpl.Guid).lower()
                        except (AttributeError, TypeError):
                            continue
                    target_template_guids.add(tg)
            except (AttributeError, TypeError):
                pass
            # Recurse into sub-POS
            try:
                children = list(pos.SubPossibilitiesOS)
                _walk_pos_skeleton(children)
            except (AttributeError, TypeError):
                pass

    _walk_pos_skeleton(pos_possibilities)
    return target_pos_guids, target_slot_guids, target_template_guids


def _build_deps_target_sets(
    target,
) -> Tuple[Set[str], Set[str], Set[str]]:
    """Build per-kind target GUID sets for deps rows (FR-009).

    Enumerates the TARGET project's POS hierarchy to collect:
      - target_feat_guids   : IFsFeatStruc from InflectableFeatsRC
      - target_class_guids  : IMoInflClass from InflectionClassesOC
      - target_stem_guids   : IMoStemName from StemNamesOC

    Note: ExceptionFeaturesOC (IPartOfSpeech) does not exist on the live LCM
    runtime (hasattr False). Exception-features are a per-entry concern
    (IMoStemMsa.MsFeaturesOA) and are out of scope for this POS-level inventory.

    Returns
    -------
    (target_feat_guids, target_class_guids, target_stem_guids)
    """
    target_feat_guids: Set[str] = set()
    target_class_guids: Set[str] = set()
    target_stem_guids: Set[str] = set()

    try:
        pos_possibilities = list(
            target.Cache.LangProject.PartsOfSpeechOA.PossibilitiesOS
        )
    except (AttributeError, TypeError):
        return (target_feat_guids, target_class_guids, target_stem_guids)

    def _walk_pos_deps(pos_list):
        for pos in pos_list:
            pos_c = _cast(pos, "IPartOfSpeech")
            # InflectableFeatsRC
            try:
                for feat in pos_c.InflectableFeatsRC:
                    feat_c = _cast(feat, "IFsFeatStruc")
                    try:
                        fg = str(feat_c.Guid).lower()
                    except (AttributeError, TypeError):
                        try:
                            fg = str(feat.Guid).lower()
                        except (AttributeError, TypeError):
                            continue
                    target_feat_guids.add(fg)
            except (AttributeError, TypeError):
                pass
            # InflectionClassesOC
            try:
                for cls in pos_c.InflectionClassesOC:
                    cls_c = _cast(cls, "IMoInflClass")
                    try:
                        cg = str(cls_c.Guid).lower()
                    except (AttributeError, TypeError):
                        try:
                            cg = str(cls.Guid).lower()
                        except (AttributeError, TypeError):
                            continue
                    target_class_guids.add(cg)
            except (AttributeError, TypeError):
                pass
            # StemNamesOC
            try:
                for sn in pos_c.StemNamesOC:
                    sn_c = _cast(sn, "IMoStemName")
                    try:
                        sg = str(sn_c.Guid).lower()
                    except (AttributeError, TypeError):
                        try:
                            sg = str(sn.Guid).lower()
                        except (AttributeError, TypeError):
                            continue
                    target_stem_guids.add(sg)
            except (AttributeError, TypeError):
                pass
            # Recurse
            try:
                _walk_pos_deps(list(pos.SubPossibilitiesOS))
            except (AttributeError, TypeError):
                pass

    _walk_pos_deps(pos_possibilities)
    return (target_feat_guids, target_class_guids, target_stem_guids)


def build_pos_grouped_inventory(source, target=None) -> PosGroupedAffixInventory:
    """Build a PosGroupedAffixInventory from the source project.

    Parameters
    ----------
    source:
        Duck-typed source handle exposing:
        - source.Cache.LangProject.LexDbOA.Entries
        - source.Cache.LangProject.PartsOfSpeechOA.PossibilitiesOS (recursive)
    target:
        Optional duck-typed target handle with the same LCM shape.
        When supplied, each AffixRow.status is populated as "new" |
        "in_target" | "similar" (FR-018).  When None, status is None for
        every row (back-compat; all existing tests pass unchanged).

    Returns
    -------
    PosGroupedAffixInventory
        Pure frozen result; retains no LCM handles.
    """
    # --- FR-018: build target lookup sets once (empty when target=None) ---
    if target is not None:
        target_guids, target_forms = _build_target_sets(target)
    else:
        target_guids = set()
        target_forms = set()

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

        # FR-018: compute status once per entry (shared by all its rows)
        if target is not None:
            entry_st: Optional[str] = _entry_status(guid, form, target_guids, target_forms)
        else:
            entry_st = None

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
                status=entry_st,
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
                    row = AffixRow(guid, form, glosses, "infl", pl, None, "attaches",
                                  status=entry_st)
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
                    row = AffixRow(guid, form, glosses, "uncl", pl, None, "attaches",
                                  status=entry_st)
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
                                          from_pl, to_pl, "attaches",
                                          status=entry_st)
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
                                          from_pl, to_pl, "produces",
                                          status=entry_st)
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
                status=entry_st,
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
                status=row.status,
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


# ============================================================================
# Skeleton + Deps Inventory (specs/009-skeleton-deps-selectors, T006-T008)
# ============================================================================

# ---------------------------------------------------------------------------
# Skeleton dataclasses (pure frozen; no LCM handles retained)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SlotNode:
    """One affix slot in the skeleton inventory."""
    slot_guid: str
    label: str
    preselected: bool          # True iff a picked affix fills this slot
    affix_count: int           # count of picked affixes that fill this slot
    status: Optional[str] = None  # "new" | "in_target" | "similar" | None
    optional: bool = False     # IMoInflAffixSlot.Optional; an empty optional
                               # slot is benign, an empty required slot would
                               # break the template on transfer


@dataclass(frozen=True)
class TemplateNode:
    """One affix template in the skeleton inventory."""
    template_guid: str
    label: str
    preselected: bool          # True iff any referenced slot is filled by a pick
    referenced_slot_guids: Tuple[str, ...]  # read-only list (FR-006)
    status: Optional[str] = None


@dataclass(frozen=True)
class SkeletonPosNode:
    """One POS node in the skeleton inventory (POS-rooted per FR-006)."""
    pos_guid: str
    label: str
    preselected: bool          # True iff a picked affix attaches to this POS
    slots: Tuple[SlotNode, ...]
    templates: Tuple[TemplateNode, ...]
    status: Optional[str] = None


@dataclass(frozen=True)
class SkeletonInventory:
    """Top-level result of build_skeleton_inventory.

    `affix_fills` maps slot_guid -> frozenset[entry_guid] of picked affixes
    that fill it. Used for EXCLUDED-LOSSY checks.
    `affix_picks` is the frozenset passed in (preserved for T003 affix-unchanged
    test; callers must not expand it).
    """
    pos_nodes: Tuple[SkeletonPosNode, ...]
    affix_fills: Dict[str, FrozenSet[str]] = field(default_factory=dict)
    affix_picks: FrozenSet[str] = field(default_factory=frozenset)

    def affix_filled_slot_guids(self) -> FrozenSet[str]:
        """Return the set of slot GUIDs that at least one picked affix fills."""
        return frozenset(sg for sg, affixes in self.affix_fills.items() if affixes)


# ---------------------------------------------------------------------------
# Deps dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DepRow:
    """One grammatical-dependency item (feature / class / stem-name / exception-feat)."""
    guid: str
    label: str
    preselected: bool = True   # all deps preselected by default (AS-NEEDED)
    status: Optional[str] = None


@dataclass(frozen=True)
class DepsInventory:
    """Result of build_deps_inventory.

    Three dep-kinds: inflectable features, inflection classes, stem names.
    ExceptionFeaturesOC does not exist on the live LCM runtime; that dep-kind
    is tracked under a separate shared-bug ticket.
    """
    infl_features: List[DepRow] = field(default_factory=list)
    infl_classes: List[DepRow] = field(default_factory=list)
    stem_names: List[DepRow] = field(default_factory=list)


# ---------------------------------------------------------------------------
# build_skeleton_inventory
# ---------------------------------------------------------------------------

def build_skeleton_inventory(
    source,
    affix_picks: FrozenSet[str],
    target=None,
) -> SkeletonInventory:
    """Derive the morphology skeleton from the source and the affix picks.

    Walks source.Cache.LangProject.PartsOfSpeechOA (same POS enumeration as
    build_pos_grouped_inventory).  For each POS:
      - Reads AffixSlotsOC (cast to IPartOfSpeech) for the POS's slots.
      - Reads each entry's MSA.SlotsRC (cast to IMoInflAffMsa) to map
        slot_guid -> {picking entry_guids}.
      - Reads AffixTemplatesOS (cast to IPartOfSpeech) for templates; each
        template's PrefixSlotsRS + SuffixSlotsRS (cast to IMoInflAffixTemplate)
        yield the referenced slots.

    CAST DISCIPLINE: every LCM collection is accessed via _cast against its
    declared base interface even when fakes pass through unchanged (the cast is
    a no-op on fakes but REQUIRED for live LCM objects per the spec).

    Parameters
    ----------
    source:
        Duck-typed source handle.
    affix_picks:
        frozenset of entry_guid strings the user has selected.
    target:
        Optional target handle for target-status computation.

    Returns
    -------
    SkeletonInventory
    """
    if target is not None:
        _tgt_pos_guids, _tgt_slot_guids, _tgt_tpl_guids = \
            _build_skeleton_target_sets(target)
    else:
        _tgt_pos_guids = set()
        _tgt_slot_guids = set()
        _tgt_tpl_guids = set()

    # Build a map: slot_guid -> set[entry_guid] of picked affixes filling it.
    # Walk all affix entries, filter to affix_picks, read MSA.SlotsRC.
    slot_affix_map: Dict[str, Set[str]] = {}

    try:
        entries = list(source.Cache.LangProject.LexDbOA.Entries)
    except (AttributeError, TypeError):
        entries = []

    for entry in entries:
        entry_c = _cast(entry, "ILexEntry")
        # Filter to affix entries
        try:
            form_obj = entry_c.LexemeFormOA
            morph_type = _cast(form_obj.MorphTypeRA, "IMoMorphType")
            if not morph_type.IsAffixType:
                continue
        except (AttributeError, TypeError):
            continue
        try:
            guid = str(entry.Guid).lower()
        except (AttributeError, TypeError):
            continue
        if guid not in affix_picks:
            continue

        try:
            msas = list(entry.MorphoSyntaxAnalysesOC)
        except (AttributeError, TypeError):
            msas = []

        for msa in msas:
            try:
                class_name = msa.ClassName
            except (AttributeError, TypeError):
                continue
            if class_name != "MoInflAffMsa":
                continue
            msa_c = _cast(msa, "IMoInflAffMsa")
            # CAST DISCIPLINE: read SlotsRC from the cast MSA, then cast
            # each slot in the collection to IMoInflAffixSlot individually.
            try:
                slots_iter = list(msa_c.SlotsRC)
            except (AttributeError, TypeError):
                slots_iter = []
            for sl in slots_iter:
                sl_c = _cast(sl, "IMoInflAffixSlot")
                try:
                    sl_guid = str(sl_c.Guid).lower()
                except (AttributeError, TypeError):
                    try:
                        sl_guid = str(sl.Guid).lower()
                    except (AttributeError, TypeError):
                        continue
                if sl_guid not in slot_affix_map:
                    slot_affix_map[sl_guid] = set()
                slot_affix_map[sl_guid].add(guid)

    # Enumerate POS hierarchy; build SkeletonPosNode for each POS that has
    # at least one affix (from the full source, not just affix_picks).
    try:
        pos_possibilities = list(
            source.Cache.LangProject.PartsOfSpeechOA.PossibilitiesOS
        )
    except (AttributeError, TypeError):
        pos_possibilities = []

    # We need the full set of (pos_guid -> set[entry_guid]) for determining
    # which POSes have picked affixes. Walk entries again.
    pos_affix_map: Dict[str, Set[str]] = {}
    for entry in entries:
        entry_c = _cast(entry, "ILexEntry")
        try:
            form_obj = entry_c.LexemeFormOA
            morph_type = _cast(form_obj.MorphTypeRA, "IMoMorphType")
            if not morph_type.IsAffixType:
                continue
        except (AttributeError, TypeError):
            continue
        try:
            guid = str(entry.Guid).lower()
        except (AttributeError, TypeError):
            continue
        if guid not in affix_picks:
            continue
        try:
            msas = list(entry.MorphoSyntaxAnalysesOC)
        except (AttributeError, TypeError):
            msas = []
        for msa in msas:
            try:
                class_name = msa.ClassName
            except (AttributeError, TypeError):
                continue
            if class_name not in ("MoInflAffMsa", "MoUnclassifiedAffixMsa"):
                continue
            msa_c = _cast(msa, "IMoInflAffMsa") if class_name == "MoInflAffMsa" \
                    else _cast(msa, "IMoUnclassifiedAffixMsa")
            try:
                pos = msa_c.PartOfSpeechRA
                if pos is None:
                    continue
                pg = _pos_guid(pos)
                if pg is None:
                    continue
                if pg not in pos_affix_map:
                    pos_affix_map[pg] = set()
                pos_affix_map[pg].add(guid)
            except (AttributeError, TypeError):
                pass

    # Also track which POS has ANY affix entries (for pruning: POS with no
    # entries at all is excluded entirely).
    pos_any_affixes: Set[str] = set()
    for entry in entries:
        entry_c = _cast(entry, "ILexEntry")
        try:
            form_obj = entry_c.LexemeFormOA
            morph_type = _cast(form_obj.MorphTypeRA, "IMoMorphType")
            if not morph_type.IsAffixType:
                continue
        except (AttributeError, TypeError):
            continue
        try:
            msas = list(entry.MorphoSyntaxAnalysesOC)
        except (AttributeError, TypeError):
            msas = []
        for msa in msas:
            try:
                cn = msa.ClassName
            except (AttributeError, TypeError):
                continue
            if cn not in ("MoInflAffMsa", "MoUnclassifiedAffixMsa"):
                continue
            mc = _cast(msa, "IMoInflAffMsa") if cn == "MoInflAffMsa" \
                 else _cast(msa, "IMoUnclassifiedAffixMsa")
            try:
                pos = mc.PartOfSpeechRA
                if pos is None:
                    continue
                pg = _pos_guid(pos)
                if pg:
                    pos_any_affixes.add(pg)
            except (AttributeError, TypeError):
                pass

    def _build_skeleton_pos_node(pos) -> Optional[SkeletonPosNode]:
        """Build a SkeletonPosNode for one POS object."""
        pg = _pos_guid(pos)
        if pg is None:
            return None
        pl = _pos_label(pos)

        # Prune: POS with no affix entries is excluded
        if pg not in pos_any_affixes:
            return None

        # CAST DISCIPLINE: read AffixSlotsOC via IPartOfSpeech cast
        pos_c = _cast(pos, "IPartOfSpeech")
        try:
            slots_oc = pos_c.AffixSlotsOC
            slot_objs = list(slots_oc)
        except (AttributeError, TypeError):
            slot_objs = []

        slot_nodes: List[SlotNode] = []
        for sl in slot_objs:
            sl_c = _cast(sl, "IMoInflAffixSlot")
            try:
                sl_guid = str(sl_c.Guid).lower()
            except (AttributeError, TypeError):
                try:
                    sl_guid = str(sl.Guid).lower()
                except (AttributeError, TypeError):
                    continue
            try:
                sl_label = sl_c.Name.BestAnalysisAlternative.Text
            except (AttributeError, TypeError):
                sl_label = sl_guid
            # IMoInflAffixSlot.Optional (Boolean on the live LCM runtime).
            # Default False (treat as required) when unreadable so an
            # unreadable slot errs toward "required" -- the case worth surfacing.
            try:
                sl_optional = bool(sl_c.Optional)
            except (AttributeError, TypeError):
                sl_optional = False
            fills = slot_affix_map.get(sl_guid, set())
            slot_presel = len(fills) > 0
            sl_status: Optional[str] = None
            if target is not None:
                # FR-009: classify by GUID membership in target's slot set
                sl_status = "in_target" if sl_guid in _tgt_slot_guids else "new"
            slot_nodes.append(SlotNode(
                slot_guid=sl_guid,
                label=sl_label,
                preselected=slot_presel,
                affix_count=len(fills),
                status=sl_status,
                optional=sl_optional,
            ))

        # CAST DISCIPLINE: read AffixTemplatesOS via IPartOfSpeech cast
        try:
            templates_os = pos_c.AffixTemplatesOS
            template_objs = list(templates_os)
        except (AttributeError, TypeError):
            template_objs = []

        template_nodes: List[TemplateNode] = []
        for tpl in template_objs:
            tpl_c = _cast(tpl, "IMoInflAffixTemplate")
            try:
                tpl_guid = str(tpl_c.Guid).lower()
            except (AttributeError, TypeError):
                try:
                    tpl_guid = str(tpl.Guid).lower()
                except (AttributeError, TypeError):
                    continue
            try:
                tpl_label = tpl_c.Name.BestAnalysisAlternative.Text
                if not tpl_label or tpl_label.strip() in ("***", ""):
                    tpl_label = "(unnamed template)"
            except (AttributeError, TypeError):
                tpl_label = "(unnamed template)"

            # Collect referenced slot GUIDs from PrefixSlotsRS + SuffixSlotsRS
            # CAST DISCIPLINE: cast tpl to IMoInflAffixTemplate before reading slots
            ref_slot_guids: List[str] = []
            for slot_seq_attr in ("PrefixSlotsRS", "SuffixSlotsRS"):
                try:
                    slot_seq = getattr(tpl_c, slot_seq_attr)
                    for tsl in slot_seq:
                        tsl_c = _cast(tsl, "IMoInflAffixSlot")
                        try:
                            tsl_guid = str(tsl_c.Guid).lower()
                        except (AttributeError, TypeError):
                            try:
                                tsl_guid = str(tsl.Guid).lower()
                            except (AttributeError, TypeError):
                                continue
                        if tsl_guid not in ref_slot_guids:
                            ref_slot_guids.append(tsl_guid)
                except (AttributeError, TypeError):
                    pass

            # Template is preselected if any of its referenced slots is filled
            tpl_presel = any(
                len(slot_affix_map.get(sg, set())) > 0 for sg in ref_slot_guids
            )
            tpl_status: Optional[str] = None
            if target is not None:
                # FR-009: classify by GUID membership in target's template set
                tpl_status = "in_target" if tpl_guid in _tgt_tpl_guids else "new"
            template_nodes.append(TemplateNode(
                template_guid=tpl_guid,
                label=tpl_label,
                preselected=tpl_presel,
                referenced_slot_guids=tuple(ref_slot_guids),
                status=tpl_status,
            ))

        # POS is preselected if any picked affix attaches to it
        pos_presel = pg in pos_affix_map and bool(pos_affix_map[pg])
        pos_status: Optional[str] = None
        if target is not None:
            # FR-009: classify by GUID membership in target's POS set
            pos_status = "in_target" if pg in _tgt_pos_guids else "new"

        return SkeletonPosNode(
            pos_guid=pg,
            label=pl,
            preselected=pos_presel,
            slots=tuple(slot_nodes),
            templates=tuple(template_nodes),
            status=pos_status,
        )

    def _collect_skeleton_nodes(pos_list) -> List[SkeletonPosNode]:
        """Recursively collect SkeletonPosNodes from a POS list + sub-POS."""
        nodes: List[SkeletonPosNode] = []
        for pos in pos_list:
            node = _build_skeleton_pos_node(pos)
            if node is not None:
                nodes.append(node)
            # Always recurse into sub-POS regardless of pruning outcome
            try:
                children = list(pos.SubPossibilitiesOS)
                nodes.extend(_collect_skeleton_nodes(children))
            except (AttributeError, TypeError):
                pass
        return nodes

    pos_nodes: List[SkeletonPosNode] = _collect_skeleton_nodes(pos_possibilities)

    # Build affix_fills map: slot_guid -> frozenset[entry_guid]
    affix_fills_frozen: Dict[str, FrozenSet[str]] = {
        sg: frozenset(guids) for sg, guids in slot_affix_map.items()
    }

    return SkeletonInventory(
        pos_nodes=tuple(pos_nodes),
        affix_fills=affix_fills_frozen,
        affix_picks=affix_picks,
    )


# ---------------------------------------------------------------------------
# build_deps_inventory
# ---------------------------------------------------------------------------

def build_deps_inventory(
    source,
    affix_picks: FrozenSet[str],
    target=None,
) -> DepsInventory:
    """Derive grammatical dependencies from the source and the affix picks.

    For each POS a picked affix attaches to, reads:
      - InflectableFeatsRC  (cast to IPartOfSpeech)
      - InflectionClassesOC (cast to IPartOfSpeech)
      - StemNamesOC         (cast to IPartOfSpeech)

    ExceptionFeaturesOC is NOT read: that property does not exist on the live
    LCM runtime (hasattr False). Exception-features are per-entry (IMoStemMsa)
    and are tracked under a separate shared-bug ticket.

    CAST DISCIPLINE: every LCM collection access goes through _cast against the
    declared base interface.  Fakes pass through unchanged; live LCM objects
    get properly dispatched.

    Parameters
    ----------
    source:
        Duck-typed source handle.
    affix_picks:
        frozenset of entry_guid strings.
    target:
        Optional target handle for target-status computation.

    Returns
    -------
    DepsInventory
    """
    if target is not None:
        _tgt_feat_guids, _tgt_class_guids, _tgt_stem_guids = \
            _build_deps_target_sets(target)
    else:
        _tgt_feat_guids = set()
        _tgt_class_guids = set()
        _tgt_stem_guids = set()

    # Find which POSes the picked affixes attach to.
    picked_pos_guids: Set[str] = set()
    picked_pos_objects: Dict[str, object] = {}  # guid -> pos obj

    try:
        entries = list(source.Cache.LangProject.LexDbOA.Entries)
    except (AttributeError, TypeError):
        entries = []

    for entry in entries:
        entry_c = _cast(entry, "ILexEntry")
        try:
            form_obj = entry_c.LexemeFormOA
            morph_type = _cast(form_obj.MorphTypeRA, "IMoMorphType")
            if not morph_type.IsAffixType:
                continue
        except (AttributeError, TypeError):
            continue
        try:
            guid = str(entry.Guid).lower()
        except (AttributeError, TypeError):
            continue
        if guid not in affix_picks:
            continue
        try:
            msas = list(entry.MorphoSyntaxAnalysesOC)
        except (AttributeError, TypeError):
            msas = []
        for msa in msas:
            try:
                class_name = msa.ClassName
            except (AttributeError, TypeError):
                continue
            if class_name not in ("MoInflAffMsa", "MoUnclassifiedAffixMsa"):
                continue
            msa_c = _cast(msa, "IMoInflAffMsa") if class_name == "MoInflAffMsa" \
                    else _cast(msa, "IMoUnclassifiedAffixMsa")
            try:
                pos = msa_c.PartOfSpeechRA
                if pos is None:
                    continue
                pg = _pos_guid(pos)
                if pg and pg not in picked_pos_guids:
                    picked_pos_guids.add(pg)
                    picked_pos_objects[pg] = pos
            except (AttributeError, TypeError):
                pass

    # Collect dep items, deduplicating by GUID.
    seen_feats: Set[str] = set()
    seen_classes: Set[str] = set()
    seen_stems: Set[str] = set()

    infl_features: List[DepRow] = []
    infl_classes: List[DepRow] = []
    stem_names: List[DepRow] = []

    def _dep_status_feat(guid: str) -> Optional[str]:
        """FR-009: classify an infl feature by GUID membership in target's feat set."""
        if target is None:
            return None
        return "in_target" if guid in _tgt_feat_guids else "new"

    def _dep_status_class(guid: str) -> Optional[str]:
        """FR-009: classify an infl class by GUID membership in target's class set."""
        if target is None:
            return None
        return "in_target" if guid in _tgt_class_guids else "new"

    def _dep_status_stem(guid: str) -> Optional[str]:
        """FR-009: classify a stem name by GUID membership in target's stem set."""
        if target is None:
            return None
        return "in_target" if guid in _tgt_stem_guids else "new"

    for pg, pos in picked_pos_objects.items():
        # CAST DISCIPLINE: cast to IPartOfSpeech before reading dep collections
        pos_c = _cast(pos, "IPartOfSpeech")

        # InflectableFeatsRC
        try:
            feats_rc = pos_c.InflectableFeatsRC
            for feat in feats_rc:
                feat_c = _cast(feat, "IFsFeatStruc")
                try:
                    fg = str(feat_c.Guid).lower()
                except (AttributeError, TypeError):
                    try:
                        fg = str(feat.Guid).lower()
                    except (AttributeError, TypeError):
                        continue
                if fg in seen_feats:
                    continue
                seen_feats.add(fg)
                try:
                    fl = feat_c.Name.BestAnalysisAlternative.Text
                except (AttributeError, TypeError):
                    fl = fg
                infl_features.append(DepRow(guid=fg, label=fl,
                                            status=_dep_status_feat(fg)))
        except (AttributeError, TypeError):
            pass

        # InflectionClassesOC
        try:
            classes_oc = pos_c.InflectionClassesOC
            for cls in classes_oc:
                cls_c = _cast(cls, "IMoInflClass")
                try:
                    cg = str(cls_c.Guid).lower()
                except (AttributeError, TypeError):
                    try:
                        cg = str(cls.Guid).lower()
                    except (AttributeError, TypeError):
                        continue
                if cg in seen_classes:
                    continue
                seen_classes.add(cg)
                try:
                    cl = cls_c.Name.BestAnalysisAlternative.Text
                except (AttributeError, TypeError):
                    cl = cg
                infl_classes.append(DepRow(guid=cg, label=cl,
                                           status=_dep_status_class(cg)))
        except (AttributeError, TypeError):
            pass

        # StemNamesOC
        try:
            stems_oc = pos_c.StemNamesOC
            for sn in stems_oc:
                sn_c = _cast(sn, "IMoStemName")
                try:
                    sg = str(sn_c.Guid).lower()
                except (AttributeError, TypeError):
                    try:
                        sg = str(sn.Guid).lower()
                    except (AttributeError, TypeError):
                        continue
                if sg in seen_stems:
                    continue
                seen_stems.add(sg)
                try:
                    sl = sn_c.Name.BestAnalysisAlternative.Text
                except (AttributeError, TypeError):
                    sl = sg
                stem_names.append(DepRow(guid=sg, label=sl,
                                         status=_dep_status_stem(sg)))
        except (AttributeError, TypeError):
            pass

    return DepsInventory(
        infl_features=infl_features,
        infl_classes=infl_classes,
        stem_names=stem_names,
    )


# ---------------------------------------------------------------------------
# build_excluded_lossy_warnings (T008)
# ---------------------------------------------------------------------------

def build_excluded_lossy_warnings(
    affix_slot_map: Dict[str, List[str]],
    deselected_slot_guids: Set[str],
    target_slot_guids: Set[str],
    *,
    deselected_pos_guids: Optional[Set[str]] = None,
    target_pos_guids: Optional[Set[str]] = None,
    affix_pos_map: Optional[Dict[str, str]] = None,
    deps_by_affix: Optional[Dict[str, Dict[str, List[str]]]] = None,
    deselected_dep_guids: Optional[Set[str]] = None,
    target_dep_guids: Optional[Set[str]] = None,
    dep_labels: Optional[Dict[str, str]] = None,
    dep_category: Optional["GrammarCategory"] = None,
) -> List:
    """Build EXCLUDED-LOSSY warning list for deselected slots, POS, and deps.

    All warnings are aggregated into a SINGLE returned list; the Move dialog
    shows the total count as ONE consolidated confirmation, never per-item.

    Parameters (required)
    ---------------------
    affix_slot_map:
        Dict mapping affix_guid -> [slot_guid, ...] (slots the affix fills).
    deselected_slot_guids:
        Set of slot GUIDs the user has deselected.
    target_slot_guids:
        Set of slot GUIDs already in the target (LINK; no warning needed).

    Parameters (optional -- POS omissions)
    ----------------------------------------
    deselected_pos_guids:
        Set of POS GUIDs the user has deselected.
    target_pos_guids:
        Set of POS GUIDs already in the target (LINK; no warning needed).
    affix_pos_map:
        Dict mapping affix_guid -> pos_guid (the POS the affix attaches to).

    Parameters (optional -- deps omissions, per-dep-kind)
    -------------------------------------------------------
    deps_by_affix:
        Dict mapping affix_guid -> {dep_guid: [dep_guid, ...]} listing the dep
        GUIDs (features / classes / stem-names / exception-features) that each
        affix's POS carries and that the affix therefore needs.
        Simpler caller shape: ``{affix_guid: {"dep_guid1": [], ...}}``.
    deselected_dep_guids:
        Set of dep GUIDs the user has deselected (across all dep kinds).
    target_dep_guids:
        Set of dep GUIDs already in the target (LINK; no warning needed).
    dep_labels:
        Dict mapping dep_guid -> human-readable label.
    dep_category:
        GrammarCategory constant for the dep kind (e.g. INFLECTION_FEATURES).

    Returns
    -------
    List of ExcludedLossy objects.
    """
    if __package__:
        from .models import ExcludedLossy, GrammarCategory
    else:
        from models import ExcludedLossy, GrammarCategory  # type: ignore

    warnings: List = []

    # --- Slot omissions (original behaviour) ---
    absent_deselected_slots = deselected_slot_guids - target_slot_guids
    for affix_guid, slots in affix_slot_map.items():
        for slot_guid in slots:
            if slot_guid in absent_deselected_slots:
                warnings.append(ExcludedLossy(
                    category=GrammarCategory.AFFIXES,
                    entry_guid=affix_guid,
                    entry_label=affix_guid,
                    dep_category=GrammarCategory.SLOTS,
                    dep_guid=slot_guid,
                    dep_label=f"slot {slot_guid[:8]}",
                    message=(
                        f"Affix '{affix_guid}' will have no slot "
                        f"(slot '{slot_guid[:8]}' deselected and absent from target)."
                    ),
                ))

    # --- POS omissions ---
    if (deselected_pos_guids is not None and
            target_pos_guids is not None and
            affix_pos_map is not None):
        absent_deselected_pos = deselected_pos_guids - target_pos_guids
        for affix_guid, pos_guid in affix_pos_map.items():
            if pos_guid in absent_deselected_pos:
                pos_short = pos_guid[:8]
                warnings.append(ExcludedLossy(
                    category=GrammarCategory.AFFIXES,
                    entry_guid=affix_guid,
                    entry_label=affix_guid,
                    dep_category=GrammarCategory.POS,
                    dep_guid=pos_guid,
                    dep_label=f"POS {pos_short}",
                    message=(
                        f"Affix '{affix_guid}' will have no Part of Speech "
                        f"(POS '{pos_short}' deselected and absent from target)."
                    ),
                ))

    # --- Deps omissions (features / classes / stem-names / exception-feats) ---
    if (deps_by_affix is not None and
            deselected_dep_guids is not None and
            target_dep_guids is not None and
            dep_category is not None):
        absent_deselected_deps = deselected_dep_guids - target_dep_guids
        _labels = dep_labels or {}
        for affix_guid, dep_guid_map in deps_by_affix.items():
            for dep_guid in dep_guid_map:
                if dep_guid in absent_deselected_deps:
                    lbl = _labels.get(dep_guid, dep_guid[:8])
                    warnings.append(ExcludedLossy(
                        category=GrammarCategory.AFFIXES,
                        entry_guid=affix_guid,
                        entry_label=affix_guid,
                        dep_category=dep_category,
                        dep_guid=dep_guid,
                        dep_label=lbl,
                        message=(
                            f"Affix '{affix_guid}' needs dep '{lbl}' "
                            f"(deselected and absent from target)."
                        ),
                    ))

    return warnings


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


# ===========================================================================
# Phonology Selector — Model-B independent block (spec 010)
# ===========================================================================

def _phon_guid(obj) -> str:
    """Lower-cased GUID for a phonology object.

    IDENTICAL normalization to categories.py `_guid_str_from` so the builder
    (which stores `row.guid`) and the leaf-dispatch trim filter (which compares
    `_guid_str_from(item)`) agree on both sides (spec 010 GUID-normalization
    invariant, P0). Real LCM path via ICmObject; fake fallback via `.guid`.
    """
    try:
        from SIL.LCModel import ICmObject  # lazy — absent in unit tests
        return str(ICmObject(obj).Guid).lower()
    except Exception:  # noqa: BLE001
        return str(getattr(obj, "guid", "")).lower()


def _phon_ipa(obj) -> str:
    """Bare IPA symbol of a phoneme (IPhPhoneme.BasicIPASymbol), or ''.

    Unset renders as None or the '***' empty sentinel; both map to ''. The
    symbol is stored bare (e.g. 'j', 'oː'); callers wrap it in slashes.
    """
    sym = getattr(obj, "BasicIPASymbol", None)
    if sym is None:
        return ""
    try:
        t = sym.Text
    except Exception:  # noqa: BLE001
        return ""
    if t and t not in ("***", ""):
        return str(t).strip()
    return ""


def _phon_description(obj) -> str:
    """Phoneme Description field (analysis WS), or ''.

    In FLEx's phoneme editor 'Description' is a field distinct from 'Refer to
    as' (the Name / grapheme, read by `_phon_name_text`) and 'IPA Symbol'. It
    is used here only as a last-resort label when a phoneme carries neither a
    grapheme nor an IPA symbol, in preference to an anonymous placeholder.
    """
    desc = getattr(obj, "Description", None)
    if desc is None:
        return ""
    alt = getattr(desc, "BestAnalysisAlternative", None)
    try:
        t = alt.Text if alt is not None else None
    except Exception:  # noqa: BLE001
        return ""
    if t and t not in ("***", ""):
        return str(t).strip()
    return ""


def _phon_name_text(obj, *, phoneme: bool) -> str:
    """Best Name alternative for a phonology object; '' when only the sentinel.

    For a phoneme this is FLEx's 'Refer to as' field. Phonemes store their
    grapheme in the *vernacular* alternative — the analysis
    alternative is FLEx's '***' empty-multistring sentinel — so they are read
    vernacular-first, then analysis as a fallback. Every other phonology
    category names itself in the analysis WS. The '***' sentinel is filtered at
    every step so it never leaks to the UI, then a fake's `.name` attr, else ''.
    """
    name = getattr(obj, "Name", None)
    if name is not None:
        accessors = (("BestVernacularAlternative", "BestAnalysisAlternative")
                     if phoneme else ("BestAnalysisAlternative",))
        for acc in accessors:
            alt = getattr(name, acc, None)
            if alt is None:
                continue
            try:
                t = alt.Text
            except Exception:  # noqa: BLE001
                continue
            if t and t not in ("***", ""):
                return str(t)
    n = getattr(obj, "name", None)
    if n and n not in ("***", ""):
        return str(n)
    return ""


def _phon_runs(obj, *, phoneme: bool = False):
    """WS-tagged runs for a phonology label (spec 011 per-WS rendering).

    Returns ``tuple[LabelRun, ...]`` where each run is ``(text, WsRole|None)``.
    This is the single source of truth for the label: `_phon_label` joins these
    runs, so the flat string and the per-WS rendering can never diverge.

    Phoneme runs split the grapheme (VERNACULAR) from the IPA symbol (IPA):
    'y /j/' -> [('y', VERN), (' ', None), ('/j/', IPA)]. The Description
    fallback is analysis text; the '(unnamed phoneme)' placeholder and the
    non-phoneme guid fallback carry no WS (None -> default UI font).
    """
    base = _phon_name_text(obj, phoneme=phoneme)
    if phoneme:
        ipa = _phon_ipa(obj)
        if base and ipa:
            return ((base, WsRole.VERNACULAR), (" ", None),
                    (f"/{ipa}/", WsRole.IPA))
        if ipa:
            return ((f"/{ipa}/", WsRole.IPA),)
        if base:
            return ((base, WsRole.VERNACULAR),)
        # No grapheme and no IPA — fall back to the Description ('refer to as'),
        # which a well-formed phoneme always carries. A fully empty phoneme is
        # skipped by the builder (see `_phon_is_empty`); the placeholder below
        # is only a defensive last resort if such a row is ever labelled direct.
        desc = _phon_description(obj)
        if desc:
            return ((desc, WsRole.ANALYSIS),)
        return (("(unnamed phoneme)", None),)
    if base:
        return ((base, WsRole.ANALYSIS),)
    g = _phon_guid(obj)
    return ((g[:8] if g else "?", None),)


def _phon_label(obj, *, phoneme: bool = False) -> str:
    """Best display label for a phonology object; degrades to guid prefix.

    For phonemes the label concatenates the vernacular grapheme with the IPA
    symbol (when set) as '<vern> /<ipa>/' — e.g. 'y /j/', 'oo /oː/'. Either
    part is omitted when blank ('r' with no IPA -> 'r'; blank grapheme with IPA
    -> '/j/'); a phoneme with neither degrades to its guid prefix.

    Derived from `_phon_runs` so the flat label always equals the concatenated
    per-WS runs shown in the UI.
    """
    return runs_to_text(_phon_runs(obj, phoneme=phoneme))


def _phon_is_empty(obj, *, phoneme: bool) -> bool:
    """True when a phonology item has no usable content in any field.

    Such items — typically dangling phonemes left behind by a BasicIPAInfo
    catalog import (observed as 32 unreferenced empties in the Ejagham Full
    GT-Test target) — are silently skipped from the inventory. For a phoneme,
    'content' spans the grapheme (Name in any WS), the IPA symbol, and the
    Description ('refer to as'); for every other category only the Name applies.
    """
    if _phon_name_text(obj, phoneme=phoneme):
        return False
    if phoneme and (_phon_ipa(obj) or _phon_description(obj)):
        return False
    return True


# The five user-facing phonology categories, in page display order, paired with
# the flexlibs2 Operations accessor attribute each enumerates.
_PHON_CATEGORY_ACCESSORS = (
    (GrammarCategory.PHONOLOGICAL_FEATURES, "PhonFeatures", "Phonological Features"),
    (GrammarCategory.PHONEMES, "Phonemes", "Phonemes"),
    (GrammarCategory.NATURAL_CLASSES, "NaturalClasses", "Natural Classes"),
    (GrammarCategory.PH_ENVIRONMENT, "Environments", "Environments"),
    (GrammarCategory.PHONOLOGICAL_RULES, "PhonRules", "Phonological Rules"),
)

# Concrete LCM rule types whose reference part-sequences the builder does NOT
# traverse (KL-010-1). Presence of one triggers the Principle-V guard.
_UNTRAVERSED_RULE_CLASSES = frozenset({"PhMetathesisRule", "PhReduplicationRule"})


@dataclass(frozen=True)
class PhonologyRow:
    """One selectable phonology item."""
    guid: str
    label: str
    category: "GrammarCategory"
    preselected: bool = True
    status: Optional[str] = None  # "new" | "in_target" | None (no target)
    # spec 011: per-WS runs backing `label` (grapheme VERN + IPA split for
    # phonemes; single ANALYSIS run otherwise). `runs_to_text(runs) == label`.
    runs: Tuple[LabelRun, ...] = ()


@dataclass(frozen=True)
class PhonologyCategoryGroup:
    category: "GrammarCategory"
    label: str
    rows: Tuple[PhonologyRow, ...] = ()

    @property
    def count(self) -> int:
        return len(self.rows)


@dataclass(frozen=True)
class PhonologyInventory:
    """Result of build_phonology_inventory (data-model.md).

    Reference maps are all `dict[guid -> frozenset[guid]]` so an EXCLUDED-LOSSY
    warning can be attributed to the specific KEPT item (entry-centric SC-006).
    """
    groups: Tuple[PhonologyCategoryGroup, ...] = ()
    rule_referenced_nc_guids: Dict[str, FrozenSet[str]] = field(default_factory=dict)
    rule_referenced_phoneme_guids: Dict[str, FrozenSet[str]] = field(default_factory=dict)
    nc_referenced_phoneme_guids: Dict[str, FrozenSet[str]] = field(default_factory=dict)
    phoneme_referenced_feature_guids: Dict[str, FrozenSet[str]] = field(default_factory=dict)
    has_rules: bool = False
    # rule_guid -> True when the rule is a type whose refs we do NOT traverse
    # (metathesis / reduplication) — KL-010-1 guard input.
    untraversed_rule_guids: FrozenSet[str] = field(default_factory=frozenset)

    def group_for(self, category) -> Optional[PhonologyCategoryGroup]:
        for g in self.groups:
            if g.category == category:
                return g
        return None


def _phon_target_sets(target, accessor: str, *,
                      phoneme: bool = False) -> Tuple[Set[str], Set[str]]:
    """Return (guids, labels) for one category in the target, or empties.

    Mirrors 008/009 `_build_target_sets`: GUID identity drives IN TARGET,
    casefolded label match drives SIMILAR (a same-name item with a different
    GUID). Labels use the same `_phon_label` the source rows display, so the
    phoneme vernacular+IPA labelling must match on both sides — hence `phoneme`.
    """
    guids: Set[str] = set()
    labels: Set[str] = set()
    if target is None or not hasattr(target, accessor):
        return guids, labels
    try:
        for obj in getattr(target, accessor).GetAll():
            if _phon_is_empty(obj, phoneme=phoneme):
                continue  # dangling empty — never a match source
            guids.add(_phon_guid(obj))
            lbl = _phon_label(obj, phoneme=phoneme)
            if lbl and lbl != "?":
                labels.add(lbl.strip().casefold())
    except (AttributeError, TypeError):
        pass
    return guids, labels


def _rule_context_refs(rule) -> List[object]:
    """Best-effort gather of the objects a rule's contexts reference.

    Covers PhRegularRule shapes: StrucDescOS[*].FeatureStructureRA and
    RightHandSidesOS[*].{Left,Right}ContextOA.FeatureStructureRA. Metathesis /
    reduplication part-sequences are NOT traversed (KL-010-1).
    """
    refs: List[object] = []

    def _add_ctx(ctx):
        if ctx is None:
            return
        ref = getattr(ctx, "FeatureStructureRA", None)
        if ref is not None:
            refs.append(ref)

    try:
        for ctx in getattr(rule, "StrucDescOS", ()) or ():
            _add_ctx(ctx)
    except TypeError:
        pass
    try:
        for rhs in getattr(rule, "RightHandSidesOS", ()) or ():
            _add_ctx(getattr(rhs, "LeftContextOA", None))
            _add_ctx(getattr(rhs, "RightContextOA", None))
    except TypeError:
        pass
    return refs


def build_phonology_inventory(source, target=None) -> PhonologyInventory:
    """Enumerate the five phonology categories + reference maps (data-model.md).

    Pure/read-only. All items preselected. Target-status is by-GUID
    (in_target) else new; None when no target bound. Reference maps classify
    each reference by membership in the phoneme/NC/feature GUID sets, so no
    LCM type-checks are needed and the logic works for fakes and live objects.
    """
    # 1. Enumerate rows per category + collect per-category GUID sets.
    groups: List[PhonologyCategoryGroup] = []
    guid_sets: Dict[object, Set[str]] = {}
    objs_by_cat: Dict[object, List[object]] = {}
    for category, accessor, label in _PHON_CATEGORY_ACCESSORS:
        is_phoneme = category == GrammarCategory.PHONEMES
        tgt_guids, tgt_labels = _phon_target_sets(target, accessor,
                                                  phoneme=is_phoneme)
        rows: List[PhonologyRow] = []
        cat_guids: Set[str] = set()
        objs: List[object] = []
        if source is not None and hasattr(source, accessor):
            try:
                items = list(getattr(source, accessor).GetAll())
            except (AttributeError, TypeError):
                items = []
            for obj in items:
                if _phon_is_empty(obj, phoneme=is_phoneme):
                    continue  # empty in all fields — silently skip (FR: dangling)
                g = _phon_guid(obj)
                cat_guids.add(g)
                objs.append(obj)
                runs = _phon_runs(obj, phoneme=is_phoneme)
                lbl = runs_to_text(runs)
                status = None
                if target is not None:
                    if g in tgt_guids:
                        status = "in_target"
                    elif lbl.strip().casefold() in tgt_labels:
                        status = "similar"
                    else:
                        status = "new"
                rows.append(PhonologyRow(
                    guid=g, label=lbl, runs=runs,
                    category=category, preselected=True, status=status,
                ))
        guid_sets[category] = cat_guids
        objs_by_cat[category] = objs
        groups.append(PhonologyCategoryGroup(
            category=category, label=label, rows=tuple(rows)))

    phoneme_guids = guid_sets.get(GrammarCategory.PHONEMES, set())
    nc_guids = guid_sets.get(GrammarCategory.NATURAL_CLASSES, set())
    feature_guids = guid_sets.get(GrammarCategory.PHONOLOGICAL_FEATURES, set())

    # 2. phoneme -> feature refs (FeaturesOA.FeatureSpecsOC[*].FeatureRA)
    phoneme_feats: Dict[str, FrozenSet[str]] = {}
    for ph in objs_by_cat.get(GrammarCategory.PHONEMES, []):
        refs: Set[str] = set()
        feat_struc = getattr(ph, "FeaturesOA", None)
        if feat_struc is not None:
            try:
                for spec in getattr(feat_struc, "FeatureSpecsOC", ()) or ():
                    fref = getattr(spec, "FeatureRA", None)
                    if fref is not None:
                        fg = _phon_guid(fref)
                        if fg in feature_guids:
                            refs.add(fg)
            except TypeError:
                pass
        if refs:
            phoneme_feats[_phon_guid(ph)] = frozenset(refs)

    # 3. nc -> phoneme refs (SegmentsRC)
    nc_phonemes: Dict[str, FrozenSet[str]] = {}
    for nc in objs_by_cat.get(GrammarCategory.NATURAL_CLASSES, []):
        refs = set()
        try:
            for seg in getattr(nc, "SegmentsRC", ()) or ():
                sg = _phon_guid(seg)
                if sg in phoneme_guids:
                    refs.add(sg)
        except TypeError:
            pass
        if refs:
            nc_phonemes[_phon_guid(nc)] = frozenset(refs)

    # 4. rule -> NC / phoneme refs; flag untraversed rule types.
    rule_ncs: Dict[str, FrozenSet[str]] = {}
    rule_phonemes: Dict[str, FrozenSet[str]] = {}
    untraversed: Set[str] = set()
    rules = objs_by_cat.get(GrammarCategory.PHONOLOGICAL_RULES, [])
    for rule in rules:
        rg = _phon_guid(rule)
        if getattr(rule, "ClassName", "") in _UNTRAVERSED_RULE_CLASSES:
            untraversed.add(rg)
        ncs: Set[str] = set()
        phs: Set[str] = set()
        for ref in _rule_context_refs(rule):
            g = _phon_guid(ref)
            if g in nc_guids:
                ncs.add(g)
            elif g in phoneme_guids:
                phs.add(g)
        if ncs:
            rule_ncs[rg] = frozenset(ncs)
        if phs:
            rule_phonemes[rg] = frozenset(phs)

    return PhonologyInventory(
        groups=tuple(groups),
        rule_referenced_nc_guids=rule_ncs,
        rule_referenced_phoneme_guids=rule_phonemes,
        nc_referenced_phoneme_guids=nc_phonemes,
        phoneme_referenced_feature_guids=phoneme_feats,
        has_rules=bool(rules),
        untraversed_rule_guids=frozenset(untraversed),
    )


def collapse_phonology(inventory: PhonologyInventory,
                       checked_by_category: Dict[object, Set[str]]) -> dict:
    """Fold the page's checked GUIDs into Selection fragments (data-model.md).

    Returns ``{"categories": {...}, "leaf_item_picks": {...}}``:
      - categories[cat] = True for each category with >=1 checked row.
      - categories[STRATA] = True iff PHONOLOGICAL_RULES on with >=1 checked
        rule (FR-009 — strata are rule-scoped, never user-facing).
      - leaf_item_picks[cat] = frozenset(checked) ONLY when the category is
        trimmed (checked is a proper subset of its rows); omitted when all
        rows are checked (=> transfer-all) or none are.
    """
    categories: Dict[object, bool] = {}
    leaf_item_picks: Dict[object, FrozenSet[str]] = {}
    for group in inventory.groups:
        checked = {g for g in checked_by_category.get(group.category, set())}
        all_guids = {r.guid for r in group.rows}
        checked &= all_guids  # ignore stray guids
        if not checked:
            continue
        categories[group.category] = True
        if checked != all_guids:  # trimmed -> record the subset
            leaf_item_picks[group.category] = frozenset(checked)

    # FR-009: strata travel iff at least one phonological rule is kept.
    rules_checked = checked_by_category.get(GrammarCategory.PHONOLOGICAL_RULES, set())
    rule_guids = set()
    rg = inventory.group_for(GrammarCategory.PHONOLOGICAL_RULES)
    if rg is not None:
        rule_guids = {r.guid for r in rg.rows}
    if categories.get(GrammarCategory.PHONOLOGICAL_RULES) and (rules_checked & rule_guids):
        categories[GrammarCategory.STRATA] = True

    return {"categories": categories, "leaf_item_picks": leaf_item_picks}


def phonology_uses_untraversed_rules(inventory: PhonologyInventory,
                                     checked_rule_guids: Set[str]) -> bool:
    """True iff any KEPT rule is a metathesis/reduplication type (KL-010-1)."""
    return bool(inventory.untraversed_rule_guids & set(checked_rule_guids))


def build_phonology_excluded_lossy(
    inventory: PhonologyInventory,
    checked_by_category: Dict[object, Set[str]],
    target_guids_by_category: Optional[Dict[object, Set[str]]] = None,
) -> List:
    """Entry-centric EXCLUDED-LOSSY warnings for intra-phonology trims (FR-010).

    A kept item whose reference is (a) deselected on this page AND (b) absent
    from the target yields ONE warning attributed to the kept item. Aggregated
    into a single list for the shared Move gate (FR-011). Chains:
      rule -> NC / phoneme-direct ; NC -> phoneme ; phoneme -> feature.
    """
    if __package__:
        from .models import ExcludedLossy, GrammarCategory as _GC
    else:
        from models import ExcludedLossy, GrammarCategory as _GC  # type: ignore

    target_guids_by_category = target_guids_by_category or {}
    warnings: List = []

    def _checked(cat) -> Set[str]:
        return set(checked_by_category.get(cat, set()))

    def _label_for(cat, guid) -> str:
        grp = inventory.group_for(cat)
        if grp is not None:
            for r in grp.rows:
                if r.guid == guid:
                    return r.label
        return guid[:8]

    def _stranded(ref_guid, ref_cat) -> bool:
        """True iff ref is deselected AND absent from target."""
        if ref_guid in _checked(ref_cat):
            return False
        return ref_guid not in target_guids_by_category.get(ref_cat, set())

    def _emit(kept_cat, kept_guid, dep_cat, dep_guid):
        warnings.append(ExcludedLossy(
            category=kept_cat,
            entry_guid=kept_guid,
            entry_label=_label_for(kept_cat, kept_guid),
            dep_category=dep_cat,
            dep_guid=dep_guid,
            dep_label=_label_for(dep_cat, dep_guid),
            message=(
                f"'{_label_for(kept_cat, kept_guid)}' references "
                f"'{_label_for(dep_cat, dep_guid)}' which will be missing "
                f"(deselected and absent from target)."
            ),
        ))

    # Kept rules -> NC / phoneme
    for rule_guid in _checked(_GC.PHONOLOGICAL_RULES):
        for nc_guid in inventory.rule_referenced_nc_guids.get(rule_guid, ()):  # noqa
            if _stranded(nc_guid, _GC.NATURAL_CLASSES):
                _emit(_GC.PHONOLOGICAL_RULES, rule_guid, _GC.NATURAL_CLASSES, nc_guid)
        for ph_guid in inventory.rule_referenced_phoneme_guids.get(rule_guid, ()):
            if _stranded(ph_guid, _GC.PHONEMES):
                _emit(_GC.PHONOLOGICAL_RULES, rule_guid, _GC.PHONEMES, ph_guid)

    # Kept NCs -> phoneme
    for nc_guid in _checked(_GC.NATURAL_CLASSES):
        for ph_guid in inventory.nc_referenced_phoneme_guids.get(nc_guid, ()):
            if _stranded(ph_guid, _GC.PHONEMES):
                _emit(_GC.NATURAL_CLASSES, nc_guid, _GC.PHONEMES, ph_guid)

    # Kept phonemes -> feature
    for ph_guid in _checked(_GC.PHONEMES):
        for feat_guid in inventory.phoneme_referenced_feature_guids.get(ph_guid, ()):
            if _stranded(feat_guid, _GC.PHONOLOGICAL_FEATURES):
                _emit(_GC.PHONEMES, ph_guid, _GC.PHONOLOGICAL_FEATURES, feat_guid)

    return warnings

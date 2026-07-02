"""Template + slot category transfer surface (T051, FR-006).

Templates pull their slots and the affixes filling those slots. Slot
transfer is inline here (no separate `categories_slots.py` — per
[plan.md](../../specs/001-phase0-additive-transfer/plan.md) v5.0.0).

The Phase 0 verb-vertical implementation already lives in
`Lib/preview.py._plan_verb_vertical` and `Lib/transfer.py._execute_verb_vertical`
(extracted from the T-Spike). This module exposes the same surface for the
engine's category dispatch once the generic Phase 0 walker replaces the
verb-vertical hard-coding.
"""
from __future__ import annotations

from typing import Iterable, Tuple

if __package__:
    from .models import GrammarCategory, WSKind
    from .residue import ImportResidueTag
else:
    from models import GrammarCategory, WSKind  # type: ignore
    from residue import ImportResidueTag  # type: ignore


CATEGORY = GrammarCategory.AFFIX_TEMPLATES


def enumerate_source(context, selection):
    raise NotImplementedError("T051: source.MorphRules.GetAllAffixTemplatesForPOS(...) over selected POSes")


def dependencies(piece) -> Iterable[Tuple[GrammarCategory, str]]:
    """FR-006: a template's deps are its slots and the affixes filling them."""
    raise NotImplementedError("T051: yield (SLOTS, slot_guid) for each slot + (AFFIXES, ...) for fillers")


def required_writing_systems(piece) -> Iterable[Tuple[str, WSKind]]:
    raise NotImplementedError("T051: template Name + Description WSs")


def plan_action(piece, context, ws_mapping):
    """Phase 0 verb-vertical path is already handled in
    `Lib/preview.py._plan_verb_vertical`. T051 generalizes it to any POS."""
    raise NotImplementedError("T051: PlannedAction; check owner POS exists in target")


def execute_action(action, context, ws_mapping, tag: ImportResidueTag):
    """Phase 0 verb-vertical path is already handled in
    `Lib/transfer.py._execute_verb_vertical._create_template_with_guid`.
    T051 generalizes."""
    raise NotImplementedError("T051: IMoInflAffixTemplateFactory.Create(Guid)")


BUNDLE = {
    "enumerate_source": enumerate_source,
    "dependencies": dependencies,
    "required_writing_systems": required_writing_systems,
    "plan_action": plan_action,
    "execute_action": execute_action,
}

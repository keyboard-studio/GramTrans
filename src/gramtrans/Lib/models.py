"""GramTrans in-module data model (data-model.md E1-E6).

Pure-Python dataclasses + enums. No flexlibs2 / LCM imports — these types
are flavor-agnostic and survive into the LibLCM-fork sibling repo unchanged.

Module name is `models.py` (not `types.py`) to avoid shadowing the Python
stdlib `types` module when `site.addsitedir(Lib)` puts these files on
sys.path as top-level imports per the FLExTrans convention.

Per constitution v5.0.0 Principle II there is no Flavor enum; every action
in this repo is flexlibs2 by construction.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional


# ============================================================================
# Enums
# ============================================================================

class GrammarCategory(enum.Enum):
    """FR-004 enumerated category list."""
    WRITING_SYSTEMS_CHECK = "writing_systems_check"
    GRAM_CATEGORIES = "gram_categories"
    INFLECTION_FEATURES = "inflection_features"
    CUSTOM_FIELDS = "custom_fields"
    INFLECTION_CLASSES = "inflection_classes"
    STEM_NAMES = "stem_names"
    EXCEPTION_FEATURES = "exception_features"
    VARIANT_TYPES = "variant_types"
    COMPLEX_FORM_TYPES = "complex_form_types"
    ADHOC_RULES = "adhoc_rules"
    COMPOUND_RULES = "compound_rules"
    AFFIXES = "affixes"
    SLOTS = "slots"
    TEMPLATES = "templates"
    # Phase 0 MVP slice — surface categories used by transfer_verb_vertical:
    POS = "pos"
    ENTRY = "entry"
    SENSE = "sense"
    MSA = "msa"
    ALLOMORPH = "allomorph"
    PH_ENVIRONMENT = "ph_environment"


class WSKind(enum.Enum):
    VERNACULAR = "vernacular"
    ANALYSIS = "analysis"


class RunMode(enum.Enum):
    PREVIEW = "preview"
    MOVE = "move"


class SkipReason(enum.Enum):
    UNMAPPED_WS = "unmapped_ws"
    DEPENDENCY_UNRESOLVED = "dependency_unresolved"
    GOLD_INVIOLABLE = "gold_inviolable"
    GUID_CONFLICT_NO_OVERRIDE = "guid_conflict_no_override"  # Phase 1+ only
    UNSUPPORTED_LCM_TYPE = "unsupported_lcm_type"
    BARE_BONES_MISSING_CLOSURE = "bare_bones_missing_closure"
    ALREADY_PRESENT_BY_GUID = "already_present_by_guid"  # FR-009 informational


# ============================================================================
# Run-scope context (E1)
# ============================================================================

@dataclass(frozen=True)
class RunContext:
    """E1 — built once at module launch from the FlexTools host's open
    project plus the user's target picker choice.

    The handles are kept opaque (Any) at the type level because they are
    flexlibs2 FLExProject instances at runtime; this module avoids importing
    flexlibs2 to stay testable without an LCM host.
    """
    source_handle: object
    source_project_name: str
    source_project_path: str
    target_handle: object
    target_project_name: str
    target_project_path: str
    run_id: str  # GT-YYYYMMDD-HHMMSS
    started_at: str  # ISO-8601

    def __post_init__(self) -> None:
        if self.source_handle is self.target_handle:
            raise ValueError("FR-019: source and target must differ")
        if not self.run_id.startswith("GT-"):
            raise ValueError(f"run_id must start with 'GT-', got {self.run_id!r}")


# ============================================================================
# Selection (E2)
# ============================================================================

@dataclass(frozen=True)
class Selection:
    """E2 — the user's category and per-item choices.

    `categories` is a dict[GrammarCategory, bool]: key present-and-True means
    the category is on; key absent or False means off.
    """
    categories: dict = field(default_factory=dict)  # dict[GrammarCategory, bool]
    include_closure: bool = True
    affix_picks: frozenset = field(default_factory=frozenset)  # frozenset[str]
    template_picks: frozenset = field(default_factory=frozenset)  # frozenset[str]
    pos_picks: frozenset = field(default_factory=frozenset)  # frozenset[str] — POS GUIDs

    def __post_init__(self) -> None:
        if self.affix_picks and self.categories.get(GrammarCategory.AFFIXES) is not True:
            raise ValueError(
                "affix_picks non-empty requires categories[AFFIXES] to be True"
            )
        if self.template_picks and self.categories.get(GrammarCategory.TEMPLATES) is not True:
            raise ValueError(
                "template_picks non-empty requires categories[TEMPLATES] to be True"
            )
        if self.pos_picks and self.categories.get(GrammarCategory.POS) is not True:
            raise ValueError(
                "pos_picks non-empty requires categories[POS] to be True"
            )

    def is_on(self, category: GrammarCategory) -> bool:
        """Return True iff the category is explicitly enabled."""
        return self.categories.get(category) is True


# ============================================================================
# Writing-system mapping (E3)
# ============================================================================

@dataclass(frozen=True)
class WSMappingEntry:
    source_ws_id: str
    source_ws_kind: WSKind
    target_ws_id: str
    create_in_target: bool = False


@dataclass(frozen=True)
class WSMapping:
    entries: tuple = ()  # tuple[WSMappingEntry, ...]

    def __post_init__(self) -> None:
        # 1:1: no two entries share target_ws_id unless they share source_ws_id
        by_target: dict = {}
        for e in self.entries:
            prev = by_target.get(e.target_ws_id)
            if prev is not None and prev != e.source_ws_id:
                raise ValueError(
                    f"WS mapping not 1:1: {prev!r} and {e.source_ws_id!r} "
                    f"both map to {e.target_ws_id!r}"
                )
            by_target[e.target_ws_id] = e.source_ws_id

    def required(self) -> frozenset:
        return frozenset((e.source_ws_id, e.source_ws_kind) for e in self.entries)

    def required_for(self, source_ws_id: str) -> Optional["WSMappingEntry"]:
        """Lookup helper: return the WSMappingEntry for `source_ws_id`, or None."""
        for e in self.entries:
            if e.source_ws_id == source_ws_id:
                return e
        return None


# ============================================================================
# Plan + actions (E4)
# ============================================================================

@dataclass(frozen=True)
class PlannedAction:
    category: GrammarCategory
    source_guid: str
    intended_target_guid: str
    summary: str
    pulled_in_by: tuple = ()  # tuple[str, ...] of source GUIDs


@dataclass(frozen=True)
class Skip:
    category: GrammarCategory
    source_guid: str
    reason: SkipReason
    detail: str

    def __post_init__(self) -> None:
        if not self.detail:
            raise ValueError("Skip.detail must be non-empty")


@dataclass(frozen=True)
class RunPlan:
    context: RunContext
    selection: Selection
    ws_mapping: WSMapping
    actions: tuple = ()  # tuple[PlannedAction, ...]
    skips: tuple = ()  # tuple[Skip, ...]
    identity_remap: dict = field(default_factory=dict)  # str -> str

    def category_count(self, category: GrammarCategory) -> int:
        return sum(1 for a in self.actions if a.category == category)


# ============================================================================
# Run report (E6)
# ============================================================================

@dataclass(frozen=True)
class CategoryReport:
    added: int = 0
    skipped: int = 0
    closure_pulled_in: int = 0


@dataclass(frozen=True)
class RunReport:
    """E6 — output of a Preview or Move run.

    Immutable by design (frozen=True). Build via `RunReport.build_from_plan`
    in Lib/report.py; do not construct manually except in tests.

    FR-018 invariant (enforced in __post_init__):
    - total_added + total_skipped == sum of per_category[*].added + skipped
    - sum of per_category[*].skipped == len(skips)
    """
    context: RunContext
    mode: RunMode
    per_category: dict = field(default_factory=dict)  # GrammarCategory -> CategoryReport
    skips: tuple = ()  # tuple[Skip, ...]
    identity_remap: dict = field(default_factory=dict)
    wall_clock_seconds: float = 0.0

    def __post_init__(self) -> None:
        # FR-018: sum of per_category[*].skipped must equal len(skips)
        cat_skipped_total = sum(r.skipped for r in self.per_category.values())
        if cat_skipped_total != len(self.skips):
            raise ValueError(
                f"FR-018 violation: sum(per_category[*].skipped)={cat_skipped_total} "
                f"!= len(skips)={len(self.skips)}"
            )

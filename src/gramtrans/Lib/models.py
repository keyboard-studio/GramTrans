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
    # Phase 3a (memo steps 2-5 + 5b) -- phonology block + strata.
    PHONOLOGICAL_FEATURES = "phonological_features"
    PHONEMES = "phonemes"
    NATURAL_CLASSES = "natural_classes"
    PHONOLOGICAL_RULES = "phonological_rules"
    STRATA = "strata"


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
    INTERACTIVE_SKIP = "interactive_skip"  # Phase 2 (FR-204): user picked SKIP
    UNMAPPED_WS_USER_CHOSE_SKIP = "unmapped_ws_user_chose_skip"  # Phase 2 (FR-211)


class MergeResolution(enum.Enum):
    """Phase 2 (FR-202) — per-field user resolution for a conflict prompt."""
    TAKE_SOURCE = "take_source"
    KEEP_TARGET = "keep_target"
    MERGE = "merge"
    SKIP = "skip"
    EDIT_CUSTOM = "edit_custom"


class WSChoice(enum.Enum):
    """Phase 2 (FR-209) — user resolution for a writing-system mismatch."""
    MAP = "map"
    CREATE = "create"
    SKIP = "skip"


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
    enable_overwrite: bool = False  # Phase 1 (FR-101/FR-108): when True,
    # already-present-by-GUID items become PlannedOverwrites instead of skips.
    interactive_merge: bool = False  # Phase 2 (FR-201): when True, per-field
    # conflicts on overwrite-candidate objects raise a ConflictPrompt instead
    # of falling through to FR-109 source-wins.
    ws_mapping_choices: tuple = ()  # Phase 2 (FR-209): tuple[WSMappingChoice, ...]
    # populated by the WSWizard before plan build.

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
        if self.interactive_merge and not self.enable_overwrite:
            raise ValueError(
                "interactive_merge=True requires enable_overwrite=True "
                "(interactive merge only fires on overwrite candidates)"
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
    """ADD — create a brand-new object in target with the source's GUID
    preserved (where possible).  Phase 0's primary action verb."""
    category: GrammarCategory
    source_guid: str
    intended_target_guid: str
    summary: str
    pulled_in_by: tuple = ()  # tuple[str, ...] of source GUIDs


@dataclass(frozen=True)
class PlannedOverwrite:
    """OVERWRITE — target already has an object matching the source; update
    its syncable properties from source.  Phase 1 (FR-101 onward).

    `match_via` records which strategy yielded this overwrite
    ("guid" | "identity_remap" | "fingerprint"). Phase 2 may inspect it to
    apply different conflict-resolution policy per-match-type.

    `owner_guid` is the parent reference the executor needs to scope its
    lookup (e.g. for a Slot overwrite, owner_guid is the template's GUID;
    for a Template overwrite, it's the owning POS's GUID). Empty for
    top-level objects (POS, PhEnvironment).
    """
    category: GrammarCategory
    source_guid: str
    target_guid: str  # the existing target GUID (may differ from source for fingerprint matches)
    summary: str
    match_via: str = "guid"  # "guid" | "identity_remap" | "fingerprint"
    pulled_in_by: tuple = ()
    owner_guid: str = ""  # parent reference for the executor's lookup


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
    overwrites: tuple = ()  # tuple[PlannedOverwrite, ...] — Phase 1 (FR-101)
    conflicts: tuple = ()  # tuple[ConflictPrompt, ...] — Phase 2 (FR-201)

    def category_count(self, category: GrammarCategory) -> int:
        return sum(1 for a in self.actions if a.category == category)


# ============================================================================
# Phase 2 — Interactive Merge entities (E11–E16)
# ============================================================================

@dataclass(frozen=True)
class MergeDecision:
    """E11 — one user resolution for a single conflicted field."""
    field_name: str
    resolution: MergeResolution
    left_value: object = None   # target's pre-overwrite value
    right_value: object = None  # source's value
    custom_value: object = None  # only set when resolution == EDIT_CUSTOM
    prior_run_id: str = ""

    def __post_init__(self) -> None:
        if not self.field_name:
            raise ValueError("MergeDecision.field_name must be non-empty")
        if self.resolution == MergeResolution.EDIT_CUSTOM:
            if self.custom_value is None:
                raise ValueError("EDIT_CUSTOM requires custom_value to be non-None")
        else:
            if self.custom_value is not None:
                raise ValueError(
                    f"custom_value must be None for resolution={self.resolution.value}"
                )


@dataclass(frozen=True)
class MergeDecisionLog:
    """E12 — ordered set of MergeDecisions for one target object.

    Serialized into the residue tag's `merge=` segment as base64(json).
    """
    target_guid: str
    decisions: tuple = ()  # tuple[MergeDecision, ...]

    def __post_init__(self) -> None:
        seen = set()
        for d in self.decisions:
            if d.field_name in seen:
                raise ValueError(
                    f"duplicate MergeDecision for field {d.field_name!r}"
                )
            seen.add(d.field_name)

    def to_json(self) -> str:
        import json
        payload = {
            "target_guid": self.target_guid,
            "decisions": [
                {
                    "field_name": d.field_name,
                    "resolution": d.resolution.value,
                    "left_value": d.left_value,
                    "right_value": d.right_value,
                    "custom_value": d.custom_value,
                    "prior_run_id": d.prior_run_id,
                }
                for d in self.decisions
            ],
        }
        return json.dumps(payload, sort_keys=True, default=repr)

    @classmethod
    def from_json(cls, s: str) -> "MergeDecisionLog":
        import json
        data = json.loads(s)
        decs = tuple(
            MergeDecision(
                field_name=d["field_name"],
                resolution=MergeResolution(d["resolution"]),
                left_value=d.get("left_value"),
                right_value=d.get("right_value"),
                custom_value=d.get("custom_value"),
                prior_run_id=d.get("prior_run_id", ""),
            )
            for d in data["decisions"]
        )
        return cls(target_guid=data["target_guid"], decisions=decs)


@dataclass(frozen=True)
class ConflictPrompt:
    """E13 — one pending per-field conflict surfaced during planning."""
    target_guid: str
    target_class_name: str
    field_name: str
    left_value: object = None
    right_value: object = None
    prior_decision: object = None  # Optional[MergeDecision]
    merge_eligible: bool = True

    def __post_init__(self) -> None:
        if not self.target_guid:
            raise ValueError("ConflictPrompt.target_guid must be non-empty")
        if not self.target_class_name:
            raise ValueError("ConflictPrompt.target_class_name must be non-empty")
        if not self.field_name:
            raise ValueError("ConflictPrompt.field_name must be non-empty")


@dataclass(frozen=True)
class WSMismatch:
    """E14 — one source-WS-not-in-target detected at wizard launch."""
    source_ws_id: str
    source_ws_kind: WSKind
    target_ws_candidates: tuple = ()  # tuple[str, ...] similarity-sorted

    def __post_init__(self) -> None:
        if not self.source_ws_id:
            raise ValueError("WSMismatch.source_ws_id must be non-empty")


@dataclass(frozen=True)
class WSMappingChoice:
    """E15 — user resolution for one WSMismatch."""
    source_ws_id: str
    source_ws_kind: WSKind
    choice: WSChoice
    target_ws_id: str = ""

    def __post_init__(self) -> None:
        if self.choice == WSChoice.MAP:
            if not self.target_ws_id:
                raise ValueError("WSChoice.MAP requires target_ws_id")
        else:
            if self.target_ws_id:
                raise ValueError(
                    f"target_ws_id must be empty for choice={self.choice.value}"
                )


@dataclass(frozen=True)
class InteractiveSession:
    """E16 — user-interactive state for one Move run."""
    ws_mapping_choices: tuple = ()  # tuple[WSMappingChoice, ...]
    merge_decisions_by_guid: dict = field(default_factory=dict)  # str -> MergeDecisionLog
    cancelled: bool = False


# ============================================================================
# Run report (E6)
# ============================================================================

@dataclass(frozen=True)
class CategoryReport:
    added: int = 0
    skipped: int = 0
    closure_pulled_in: int = 0
    overwritten: int = 0  # Phase 1 (FR-110)
    interactive_resolved: int = 0  # Phase 2 (FR-208): non-default user resolutions
    interactive_skipped: int = 0   # Phase 2 (FR-204): SKIP resolutions
    ws_mapped: int = 0             # Phase 2
    ws_created: int = 0
    ws_skipped: int = 0


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

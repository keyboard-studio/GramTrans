"""GramTrans in-module data model (data-model.md E1-E6).

Pure-Python dataclasses + enums. No flexicon / LCM imports — these types
are flavor-agnostic and survive into the LibLCM-direct sibling repo unchanged.

Module name is `models.py` (not `types.py`) to avoid shadowing the Python
stdlib `types` module when `site.addsitedir(Lib)` puts these files on
sys.path as top-level imports per the FLExTrans convention.

Per constitution v5.0.0 Principle II there is no Flavor enum; every action
in this repo is flexicon by construction.
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
    ADHOC_COMPOUND_RULES = "adhoc_compound_rules"  # Phase 3c: unified per FR-341 (per-subclass dispatch on IMoCompoundRule + IMoAdhocProhibition)
    AFFIXES = "affixes"
    SLOTS = "slots"
    AFFIX_TEMPLATES = "affix_templates"
    STEMS = "stems"  # Phase 3c: memo step 18
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
    # Phase 3b (memo step 13b) -- semantic domains; other 8 Phase 3b
    # categories already declared above.
    SEMANTIC_DOMAINS = "semantic_domains"


class CategoryScope(enum.Enum):
    """Per-category three-scope selector (Selection UI, plan.md revised 2026-07-01).

    NONE      : do not transfer this category at all -- not even what the picked
                items' closure needs.  A referencing entry becomes EXCLUDED-LOSSY
                if the target lacks the dependency.
    AS_NEEDED : (default) transfer exactly the closure the picked items require,
                minus any per-item exclusions in `excluded_deps`.
    ALL       : transfer the entire source category, including items nothing the
                user picked references.
    """
    NONE = "none"
    AS_NEEDED = "as_needed"
    ALL = "all"


class ConflictMode(enum.Enum):
    """Per-category conflict mode (Selection UI, plan.md revised 2026-07-01 section h).

    Determines what happens when a closure item from the source meets an
    object already present in the target.

    ADD_NEW   : always create a new copy, even if a matching object exists.
    MERGE     : link-if-present-by-GUID else ADD (interim MERGE, Option b).
                No field-level update is performed -- the page-3 control
                MUST label this explicitly so users are not misled.
    OVERWRITE : overwrite the target's existing object with source values
                (only offered when structurally possible and not forbidden
                by Layer-1 kind or Layer-2 IsProtected gating).
    """
    ADD_NEW = "add_new"
    MERGE = "merge"
    OVERWRITE = "overwrite"


# ---------------------------------------------------------------------------
# Layer-1 category-kind defaults (section h, plan.md revised 2026-07-01).
# Maps each GrammarCategory to its default ConflictMode per kind:
#   MULTI_INSTANCE     -> ADD_NEW (all three modes offered)
#   SINGLETON_NONDELETABLE -> MERGE (ADD_NEW hidden)
#   GOLD_RESERVED      -> MERGE (ADD_NEW hidden, OVERWRITE forbidden)
#   CUSTOM_FIELDS      -> MERGE (ADD_NEW hidden, OVERWRITE forbidden, conservative default)
# ---------------------------------------------------------------------------

def _build_default_conflict_modes() -> dict:
    """Return the default ConflictMode for every GrammarCategory per Layer-1."""
    # MULTI_INSTANCE categories (all three modes offered; default ADD_NEW)
    multi_instance = {
        GrammarCategory.AFFIXES,
        GrammarCategory.STEMS,
        GrammarCategory.SLOTS,
        GrammarCategory.AFFIX_TEMPLATES,
        GrammarCategory.INFLECTION_CLASSES,
        GrammarCategory.STEM_NAMES,
        GrammarCategory.EXCEPTION_FEATURES,
        GrammarCategory.ADHOC_COMPOUND_RULES,
        GrammarCategory.PHONEMES,
        GrammarCategory.NATURAL_CLASSES,
        GrammarCategory.PHONOLOGICAL_RULES,
        GrammarCategory.PH_ENVIRONMENT,
        # STRATA reclassified to MULTI_INSTANCE (StrataOS is an Owning SEQUENCE)
        GrammarCategory.STRATA,
        # Phase 0 / entry-level categories
        GrammarCategory.ENTRY,
        GrammarCategory.SENSE,
        GrammarCategory.MSA,
        GrammarCategory.ALLOMORPH,
    }
    # GOLD_RESERVED categories (ADD_NEW hidden, OVERWRITE forbidden -> MERGE default)
    gold_reserved = {
        GrammarCategory.GRAM_CATEGORIES,
        GrammarCategory.INFLECTION_FEATURES,
        GrammarCategory.VARIANT_TYPES,
        GrammarCategory.COMPLEX_FORM_TYPES,
        GrammarCategory.POS,
        GrammarCategory.PHONOLOGICAL_FEATURES,
        GrammarCategory.SEMANTIC_DOMAINS,
    }
    # SINGLETON_NONDELETABLE (ADD_NEW hidden -> MERGE default)
    singleton = {
        GrammarCategory.WRITING_SYSTEMS_CHECK,
    }
    # CUSTOM_FIELDS: conservative default (ADD hidden, OVERWRITE forbidden, MERGE no-op-if-identical)
    custom_fields = {
        GrammarCategory.CUSTOM_FIELDS,
    }
    result: dict = {}
    for cat in GrammarCategory:
        if cat in multi_instance:
            result[cat] = ConflictMode.ADD_NEW
        elif cat in gold_reserved:
            result[cat] = ConflictMode.MERGE
        elif cat in singleton:
            result[cat] = ConflictMode.MERGE
        elif cat in custom_fields:
            result[cat] = ConflictMode.MERGE
        else:
            # Fallback for any newly-added category: safest default
            result[cat] = ConflictMode.MERGE
    return result


_DEFAULT_CONFLICT_MODES: dict = _build_default_conflict_modes()


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
    # Phase 3b US2: emitted when a category requires a manual user step
    # that GramTrans cannot perform automatically (e.g. custom-field
    # schema creation, blocked by LCM at the flexicon layer). Detail
    # string MUST cite the specific user action required.
    NEEDS_MANUAL = "needs_manual"
    # Phase 3b US2: identity-tuple match for entities lacking a real
    # LCM Guid (e.g. custom fields keyed by (class_id, name)). Distinct
    # from ALREADY_PRESENT_BY_GUID so sync-report readers don't infer
    # a Guid identity check occurred when none did.
    ALREADY_PRESENT_BY_IDENTITY = "already_present_by_identity"
    # Phase 3c Selection UI: deliberate, informed omission of a dependency
    # that a copied entry DOES reference and that the target does not already
    # have.  Distinct from DEPENDENCY_UNRESOLVED (which is accidental and
    # hard-fails); EXCLUDED_LOSSY is a soft warn+allow disposition -- the
    # entry transfers with a null reference after explicit user confirmation.
    EXCLUDED_LOSSY = "excluded_lossy"


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
    flexicon FLExProject instances at runtime; this module avoids importing
    flexicon to stay testable without an LCM host.
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
# Similar-candidate capture & per-item resolution (spec 011)
# ============================================================================

@dataclass(frozen=True)
class SimilarCandidate:
    """FR-001 — one target entry a SIMILAR source item could correspond to.

    Immutable ``(target_guid, form, gloss)``. ``target_guid`` is the identity
    (GUID-first, constitution Principle I); ``form`` carries display identity
    even when ``gloss`` is empty ("(no gloss)").

    Ordering contract (spec 011 research D2): SimilarCandidate carries no
    ordering key of its own. Candidate tuples are pre-sorted HVO-ascending at
    construction time in the builder, and *tuple position is the contract* —
    consumers MUST treat order as canonical and MUST NOT re-sort.
    """
    target_guid: str
    form: str
    gloss: str


# Allowed SimilarResolution actions (spec 011 FR-007, three-way split).
#   overwrite  -> source wins on every field (import golden); the seeded default
#                 so the vocabulary change does not alter an un-touched SIMILAR row.
#   merge      -> target-preserving fill-the-gaps (source written only where the
#                 target field is empty).
#   create_new -> a fresh entry, no link.
# Execution of each action is 013's concern; 011 defines + validates only.
_SIMILAR_ACTIONS_NEED_TARGET = frozenset({"overwrite", "merge"})
_SIMILAR_ACTIONS = _SIMILAR_ACTIONS_NEED_TARGET | {"create_new"}


@dataclass(frozen=True)
class SimilarResolution:
    """FR-007 — a per-source-entry overwrite / merge / create decision.

    The typed contract the preview pane emits and the 013 planner reads.
    Validated at construction; carried inertly on ``Selection`` until 013
    consumes it (FR-010).
    """
    entry_guid: str
    action: str  # "overwrite" | "merge" | "create_new"
    target_guid: Optional[str] = None

    def __post_init__(self) -> None:
        if self.action not in _SIMILAR_ACTIONS:
            raise ValueError(
                f"SimilarResolution.action must be one of "
                f"{sorted(_SIMILAR_ACTIONS)}, got {self.action!r}"
            )
        if self.action in _SIMILAR_ACTIONS_NEED_TARGET:
            if not self.target_guid:
                raise ValueError(
                    f"SimilarResolution action {self.action!r} requires a "
                    f"non-empty target_guid"
                )
        else:  # create_new
            if self.target_guid:
                raise ValueError(
                    "SimilarResolution action 'create_new' must not name a "
                    "target_guid"
                )


# ============================================================================
# Selection (E2)
# ============================================================================

@dataclass(frozen=True)
class Selection:
    """E2 — the user's category and per-item choices.

    `categories` is a dict[GrammarCategory, bool]: key present-and-True means
    the category is on; key absent or False means off.

    Phase 3c Selection UI additions (plan.md revised 2026-07-01):
    - `category_scopes`: per-category three-scope map (NONE / AS_NEEDED / ALL).
      When absent for a category that is on, the effective scope is AS_NEEDED.
      The old `include_closure=True` corresponds to every schema category
      AS_NEEDED; `include_closure=False` corresponds to every schema category
      NONE.  Both are preserved for backward compatibility (existing 324 tests).
    - `excluded_deps`: frozenset of source GUIDs the user explicitly deselected
      inside an AS_NEEDED category (per-item exclusion).  Excluded deps that a
      copied entry references and that the target lacks become EXCLUDED-LOSSY
      warnings.

    BACK-COMPAT: callers that pass `include_closure=<bool>` continue to work.
    The effective scope for any category not in `category_scopes` is derived
    from `include_closure` (True -> AS_NEEDED, False -> NONE) so the existing
    test suite requires no changes.
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
    # Phase 3c Selection UI (plan.md revised 2026-07-01):
    category_scopes: dict = field(default_factory=dict)  # dict[GrammarCategory, CategoryScope]
    excluded_deps: frozenset = field(default_factory=frozenset)  # frozenset[str] source GUIDs
    # Per-category conflict mode (section h).  When absent for a category, the
    # Layer-1 default from `_DEFAULT_CONFLICT_MODES` is used via `conflict_mode_for`.
    category_conflict_modes: dict = field(default_factory=dict)  # dict[GrammarCategory, ConflictMode]
    # Phase 010 (Phonology Model-B): per-category item-pick subset for LEAF
    # categories.  dict[GrammarCategory, frozenset[str]] of source GUIDs.
    # Semantics: key PRESENT => transfer ONLY those GUIDs within the category;
    # key ABSENT => transfer ALL (unchanged behavior for every prior caller);
    # empty frozenset => transfer none of that category.  Consulted by the
    # phonology `enumerate_source` helpers via `leaf_picks_for`.
    #
    # DELIBERATE no-coupling exemption: unlike affix_picks/template_picks/
    # pos_picks (which __post_init__ guards against a disabled category), a
    # leaf_item_picks entry for an off category is simply inert -- the
    # leaf-dispatch `is_on(cat)` gate fires first, so a stale key is harmless.
    # No __post_init__ validation is added for it by design.
    leaf_item_picks: dict = field(default_factory=dict)  # dict[GrammarCategory, frozenset[str]]
    # Spec 011 (Similar-resolution model): per-source-entry overwrite/merge/
    # create decisions.  dict[source entry GUID -> SimilarResolution].
    # Follows the SAME inert-when-off pattern as leaf_item_picks: NO
    # __post_init__ guard by design -- nothing in this feature reads the map,
    # so a resolution recorded for an unselected entry is simply inert
    # (FR-010 inert guarantee / SC-004 byte-identical plans).  Consumed by 013.
    similar_resolutions: dict = field(default_factory=dict)  # dict[str, SimilarResolution]

    def __post_init__(self) -> None:
        if self.affix_picks and self.categories.get(GrammarCategory.AFFIXES) is not True:
            raise ValueError(
                "affix_picks non-empty requires categories[AFFIXES] to be True"
            )
        if self.template_picks and self.categories.get(GrammarCategory.AFFIX_TEMPLATES) is not True:
            raise ValueError(
                "template_picks non-empty requires categories[AFFIX_TEMPLATES] to be True"
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

    def scope_for(self, category: "GrammarCategory") -> "CategoryScope":
        """Return the effective CategoryScope for `category`.

        Lookup order:
        1. Explicit entry in `category_scopes`.
        2. Fall back to the legacy `include_closure` bool:
           True  -> AS_NEEDED (current behaviour)
           False -> NONE (bare-bones / closure off)

        This means old callers that never set `category_scopes` continue to
        behave exactly as before.
        """
        explicit = self.category_scopes.get(category)
        if explicit is not None:
            return explicit
        return CategoryScope.AS_NEEDED if self.include_closure else CategoryScope.NONE

    def is_dep_excluded(self, dep_guid: str) -> bool:
        """Return True iff `dep_guid` is in the per-item exclusion set."""
        return dep_guid in self.excluded_deps

    def leaf_picks_for(self, category: "GrammarCategory"):
        """Return the per-item GUID subset for a leaf `category`, or None.

        None (key absent) ⇒ transfer ALL items in the category (default,
        back-compatible). A frozenset ⇒ transfer only those GUIDs; an empty
        frozenset ⇒ transfer none. See `leaf_item_picks`.
        """
        return self.leaf_item_picks.get(category)

    def similar_resolution_for(self, guid: str) -> "Optional[SimilarResolution]":
        """FR-008 — return the SimilarResolution for source `guid`, or None.

        Mirrors ``leaf_picks_for``: returns None when no resolution is recorded
        (the model layer fabricates no default; the page state seeds defaults,
        per spec 011 Assumptions).
        """
        return self.similar_resolutions.get(guid)

    def conflict_mode_for(self, category: "GrammarCategory") -> "ConflictMode":
        """Return the effective ConflictMode for `category`.

        Lookup order:
        1. Explicit entry in `category_conflict_modes`.
        2. Layer-1 default from `_DEFAULT_CONFLICT_MODES`.
        3. MERGE as ultimate fallback (safest, non-destructive).
        """
        explicit = self.category_conflict_modes.get(category)
        if explicit is not None:
            return explicit
        return _DEFAULT_CONFLICT_MODES.get(category, ConflictMode.MERGE)

    def _replace_conflict_modes(self, category_conflict_modes: dict) -> "Selection":
        """Return a new Selection with `category_conflict_modes` set.

        `dataclasses.replace` is fully compatible with `frozen=True` (it builds a
        new instance rather than mutating in place). Defined here on the dataclass
        itself — not monkey-patched from the wizard — so headless/API callers have
        the method regardless of whether the Qt UI module was ever imported.
        """
        import dataclasses
        return dataclasses.replace(
            self, category_conflict_modes=category_conflict_modes
        )


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
class ExcludedLossy:
    """EXCLUDED-LOSSY disposition (Selection UI, plan.md revised 2026-07-01).

    The user deliberately dropped a dependency (via NONE scope or per-item
    deselect) that a copied entry DOES reference, and the target does not
    already have the dependency.  The entry will transfer with a null
    reference.  This is warn+allow, never a hard block.

    `entry_guid`    : source GUID of the payload entry that loses the link.
    `entry_label`   : human-readable headword / name for the warning message.
    `dep_category`  : which schema category the missing dep belongs to.
    `dep_guid`      : source GUID of the dropped dependency.
    `dep_label`     : human-readable name of the dropped dep.
    `message`       : entry-centric warning text, e.g.
                      "Entry '-PL' will have no Part of Speech."
    """
    category: "GrammarCategory"  # category of the ENTRY (not the dep)
    entry_guid: str
    entry_label: str
    dep_category: "GrammarCategory"
    dep_guid: str
    dep_label: str
    message: str

    def __post_init__(self) -> None:
        if not self.entry_guid:
            raise ValueError("ExcludedLossy.entry_guid must be non-empty")
        if not self.message:
            raise ValueError("ExcludedLossy.message must be non-empty")


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
    # Phase 3c (FR-333): in-plan binding mappings populated during
    # AFFIXES/STEMS plan_action and consumed by tail blocks on
    # AFFIX_TEMPLATES.execute_action (17.1 sub-pass) and
    # STEMS.execute_action (post-pass A). Ephemeral per run; not
    # serialised into the run snapshot.
    msa_slot_bindings: dict = field(default_factory=dict)  # Guid -> list[Guid]
    # Phase 3c (FR-340): LexEntryRef component-lexeme bindings deferred
    # to post-pass A. Shape: {src_entry_guid: {"ComponentLexemesRS": [...],
    # "PrimaryLexemesRS": [...]}}.
    lexentry_ref_bindings: dict = field(default_factory=dict)
    # Phase 3c Selection UI: EXCLUDED-LOSSY dispositions — deliberate, informed
    # omissions that generate entry-centric warnings but never hard-block Move.
    excluded_lossy: tuple = ()  # tuple[ExcludedLossy, ...]

    def category_count(self, category: GrammarCategory) -> int:
        return sum(1 for a in self.actions if a.category == category)

    def excluded_lossy_count(self) -> int:
        """Number of EXCLUDED-LOSSY warnings in the plan."""
        return len(self.excluded_lossy)


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
    excluded_lossy: int = 0        # Phase 3c Selection UI: deliberate warn+allow omissions


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
    empty_categories: tuple = ()  # Phase 3a FR-308: categories selected
    # but with zero items in source. Used by render_text_summary to emit
    # "[skip] no items in source for X" lines.
    # Phase 3c Selection UI: EXCLUDED-LOSSY warning channel.
    excluded_lossy: tuple = ()  # tuple[ExcludedLossy, ...]

    def __post_init__(self) -> None:
        # FR-018: sum of per_category[*].skipped must equal len(skips)
        cat_skipped_total = sum(r.skipped for r in self.per_category.values())
        if cat_skipped_total != len(self.skips):
            raise ValueError(
                f"FR-018 violation: sum(per_category[*].skipped)={cat_skipped_total} "
                f"!= len(skips)={len(self.skips)}"
            )

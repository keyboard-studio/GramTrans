# Phase 0 Research: Phonology Selector (Model-B)

All unknowns resolved by direct code inspection of the shipped engine + wizard and by the
LEX crew's cycle-1 domain review. No `NEEDS CLARIFICATION` remain.

## R1 — Does the engine support per-item trim within a leaf category? (load-bearing)

**Decision**: No, not today — add a contained extension. The spec-005 leaf-dispatch transfers
**every** item in an enabled category.

**Evidence**:
- `Lib/categories.py` `_phonology_simple_enumerate(context, ops_attr)` returns
  `list(getattr(source, ops_attr).GetAll())` — all items, `selection` never consulted. All
  six phonology `enumerate_source` helpers route through it (or the strata equivalent).
- `Lib/preview.py` leaf-dispatch: `for cat in _LEAF_DISPATCH_CATEGORIES: if not selection.is_on(cat): continue` — category is a **binary toggle** (`Selection.is_on`).
- `Selection` (models.py) per-item fields are `affix_picks`, `template_picks`, `pos_picks`
  (morphology only) and `excluded_deps` (dependency-referenced items, not leaf categories).
  There is **no** leaf-category per-item pick field, and the phonology enumerate helpers do
  not read `excluded_deps`.

**Chosen approach** (user-confirmed, "full spec + minimal engine touch"):
1. Add `Selection.leaf_item_picks: dict[GrammarCategory, frozenset[str]]` — for a category
   key present, only those source GUIDs transfer; **absent key ⇒ transfer all** (preserves
   every existing caller's behavior, all 324+ tests unchanged).
2. Extend `_phonology_simple_enumerate` (and the strata enumerate) to filter by
   `selection.leaf_item_picks.get(cat)` when present. One helper change covers 5 of 6
   categories; strata gets the same guard.

**Alternatives rejected**:
- *Reuse `excluded_deps`*: semantically it's the "referenced-by-a-picked-entry but deselected"
  exclusion set feeding EXCLUDED-LOSSY; overloading it for leaf-category inclusion muddies two
  concepts and risks the dep-warning logic. A dedicated inclusion field is clearer.
- *Whole-block-only, defer trim*: rejected by user — per-item trim is the defining Model-B
  affordance (US2/FR-005 are P1).

## R2 — Intra-phonology reference chain (for FR-010 EXCLUDED-LOSSY)

**Decision**: Honor `rules → (inline context: natural classes and/or phonemes directly) →
phonemes → phonological features`, plus `natural classes → phonemes → features` and
`phonemes → features`. Environments are **allomorph-side** (`IMoAffixAllomorph.PhoneEnvRC`),
not rule-side — excluded from the rule chain.

**Evidence** (lex-domain cycle-1 review): rules reference NCs via `IPhSimpleContextNC` and
phonemes directly via `IPhSimpleContextSeg` in `StrucDescOS` / `rhs.LeftContextOA` /
`RightContextOA`; NCs reference phonemes via `SegmentsRC`
(`NaturalClassOperations.GetPhonemes` → `list(nc.SegmentsRC)`); phonemes reference features
via `IPhPhoneme.FeaturesOA`.

**Rationale**: the missing-reference check must catch a kept rule stranded against a
deselected NC *or* a deselected phoneme (direct segment), and a kept NC stranded against a
deselected phoneme. Matches spec US5 scenarios 1 + 3.

## R3 — Strata dependency gating

**Decision**: Include strata iff at least one phonological **rule** is in the plan (rules
carry `StratumRA`; no other phonology object references a stratum). Strata never user-facing.

**Evidence**: `Lib/categories.py` strata enumerate + `PhonologicalRuleOperations` accesses
`project.lp.MorphologicalDataOA.StrataOS` and each rule's `StratumRA`. Strata is an
independent leaf category in the engine, so the page turns `categories[STRATA] = True` when
(and only when) `phon_rules` is on with ≥1 selected rule, then lets the existing closure walk
pull the referenced strata.

**Rationale**: transferring 32 phonemes + 5 NCs with zero rules needs zero strata (spec FR-009
corrected in cycle-1 review).

## R4 — Wizard page insertion & cross-page index coupling

**Decision**: Insert `_PagePhonology` at **index 1** (Project+WS=0, Phonology=1, Affixes=2,
Skeleton=3, GramDeps=4, Preview=5, Finish=6) and **replace hardcoded `wizard.page(N)` lookups
with named-attribute / role-based lookups**.

**Evidence**: `selection_wizard.py` cross-references pages by literal index —
`_PageSkeleton._get_affix_picks` reads `w.page(1)`; `_PagePreview._on_preview` reads
`wizard.page(1)`; `_PageFinish._on_move` reads `wizard.page(4)` and `wizard.page(2)`. Inserting
a page at index 1 shifts all of these. The wizard already stores each page as an attribute
(`self._page_items`, `self._page_skeleton`, `self._page_preview`, …).

**Chosen approach**: add a small accessor on `SelectionWizard` (e.g. `page_items()`,
`page_preview()`, `page_skeleton()`, `page_phonology()`) returning the stored attribute, and
have pages call those instead of `wizard.page(N)`. Removes the index fragility permanently
and is the minimal safe way to insert a page.

**Alternatives rejected**: *bump every literal index by one* — brittle, silently breaks on the
next insertion, and the review already flagged page-order drift (Explore DIFFER vs 009).

## R5 — Selection wiring for whole-block + preview integration

**Decision**: The Phonology page contributes to the same `Selection` the Preview page builds.
`_PagePreview._on_preview` currently constructs a Selection from affix picks only; extend it to
merge phonology category toggles (`categories[PHON_*] = True`), `leaf_item_picks` (trimmed
GUIDs per category), and the rule-gated `categories[STRATA]`.

**Evidence**: `_PagePreview._on_preview` builds `build_selection(...)._replace_conflict_modes(...)`;
`build_selection` accepts `extra_categories`. Phonology categories map to existing
`GrammarCategory` members (`PHONOLOGICAL_FEATURES`, `PHONEMES`, `NATURAL_CLASSES`,
`PH_ENVIRONMENT`/`ph_environment`, `PHONOLOGICAL_RULES`, `STRATA`) already present in the enum
(confirmed: `_GOLD_RESERVED` references `PHONOLOGICAL_FEATURES`).

## R6 — Target-status (NEW / IN TARGET / SIMILAR) for phonology rows

**Decision**: Reuse the 008/009 status logic. The phonology inventory builder computes each
row's status against the bound target by GUID (IN TARGET) with fingerprint fallback (SIMILAR),
else NEW; blank when target is None.

**Evidence**: affix/skeleton/deps rows already carry `.status` set by `build_*_inventory(..., target=...)`; the phonology builder follows the same pattern (`_STATUS_LABELS` in the wizard is shared).

## R7 — Testability strategy

**Decision**: Pure builder + fake-handle unit tests (mirrors 009). `build_phonology_inventory(source, target=None)` is a pure function over duck-typed source/target handles → fake handles in `tests/unit/`; live MCP validation in `tests/integration/` against Ejagham Mini → Ejagham Full GT-Test (32 phonemes, 5 NCs, 2+ envs) per quickstart.

**Rationale**: the engine leaf callbacks are already live-verified (spec 005); 010's new logic
is the builder + selection wiring + the enumerate filter, all fake-handle testable.

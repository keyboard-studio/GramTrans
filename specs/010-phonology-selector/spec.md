# Feature Specification: Phonology Selector (Model-B Independent Block)

**Feature Branch**: `feature/007-selection-ui` (continuation; spec dir `010-phonology-selector`)

**Created**: 2026-07-02

**Status**: Draft

**Input**: User description: "Phonology page (Model-B independent block) for the transfer wizard — feature 010. Adds the Phonology wizard page defined as build-sequence step 2 in specs/wizard-selection-roadmap.md."

## Context

Feature 009 delivered the two Model-A (item-derived) wizard pages — morphology skeleton and
grammatical dependencies — that hang off the affix picks. This feature adds the first
**Model-B (independent block)** page: **Phonology**. Per the two-selection-model framing in
[../wizard-selection-roadmap.md](../wizard-selection-roadmap.md), a Model-B block is
self-contained grammar transferred wholesale (all-on with per-item trim, or whole-block
off) rather than derived from a lexical/affix pick.

The transfer **engine** for every phonology data type already ships and is live-verified:
spec 005 (`005-phonology-block`) implemented the six category callbacks
(`phon_features`, `phonemes`, `natural_classes`, `ph_environment`, `phon_rules`, `strata`)
in `Lib/categories.py`, wired through the leaf-dispatch loop in `Lib/preview.py` /
`Lib/transfer.py`, and verified them end-to-end (Ejagham Mini → Ejagham Full GT-Test: 32
phonemes + 5 natural classes + 2 environments created; FR-307 idempotency held). This
feature is **primarily UI/selection** — it surfaces those categories as a wizard page and
feeds the user's picks into the existing plan/closure engine. It adds **no new engine
categories** and changes no callback behavior beyond one contained extension: because the
spec-005 leaf-dispatch currently transfers every item in an enabled category
(all-or-nothing), per-item trim (FR-005) requires a small, localized change — a per-category
item-pick subset on the `Selection` that the phonology `enumerate_source` helpers honor. See
the plan's Constitution Check / Complexity Tracking for the scope of that touch.

The Phonology page sits **before** the Model-A pages because phonology is a foundational
independent block the morphology hangs off. Page order becomes:
Project+WS → **Phonology** → Affixes → Skeleton → Grammatical deps → Preview → Finish.

Consistent with 009: no conflict-mode UI this phase (Layer-1 category defaults apply
automatically); the NEW / IN TARGET / SIMILAR target-status column carries collision
information; nothing on the page writes to the target (the only write remains at Move).

Grounded live via FlexTools MCP on Ejagham Mini → Ejagham Full GT-Test (spec 005 probe
results: 32 phonemes, 5 natural classes referencing 22/4/4/7/7 phonemes via SegmentsRC, 2+
environments, phonological features and rules present).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Transfer the whole phonology block (Priority: P1)

Arriving at the Phonology page, the user sees every phonology data type already selected —
phonological features, phonemes, natural classes, environments, and phonological rules —
grouped by category with counts, and can advance with a single click to bring the entire
block across.

**Why this priority**: "Bring the toy project's phonology wholesale" is the dominant case
for a Model-B block and the reason the engine exists; all-selected-by-default delivers it
with zero interaction. This is the MVP slice.

**Independent Test**: Bind Ejagham Mini as source; open the Phonology page; confirm all
five categories render preselected with correct counts (32 phonemes, 5 natural classes,
etc.) and the collapsed selection includes every phonology item before any interaction.

**Acceptance Scenarios**:

1. **Given** a bound source with phonology data, **When** the Phonology page is shown,
   **Then** every category and every item row is checked and the whole-block toggle reads
   fully-selected.
2. **Given** the fully-selected page, **When** the user advances without interacting,
   **Then** the transfer plan includes all phonology items in each category.
3. **Given** a source with no phonology data in some category (e.g. 0 phonological rules),
   **When** the page renders, **Then** that category shows as empty (not an error) and the
   page still advances.

---

### User Story 2 - Toggle the whole block off, or trim individual items (Priority: P1)

The user can turn the entire phonology block off with one control (transfer no phonology),
or keep the block on and deselect individual items within any category for a leaner
transfer.

**Why this priority**: The whole point of a Model-B block is wholesale-with-opt-out;
without a whole-block toggle and per-item trim the "NONE" and "bare-bones" cases are
impossible. Small and independently testable on top of US1.

**Independent Test**: On the Phonology page, click the whole-block toggle off; confirm the
plan contains zero phonology items. Toggle back on, deselect three phonemes; confirm the
plan contains all phonemes except those three.

**Acceptance Scenarios**:

1. **Given** the fully-selected page, **When** the user toggles the whole block off,
   **Then** all category and item rows read unchecked and the plan contains no phonology
   items.
2. **Given** the block on, **When** the user deselects a single natural class, **Then** the
   plan contains every phonology item except that natural class.
3. **Given** all items in a category deselected individually, **When** the page state is
   read, **Then** that category's group toggle reads fully-unchecked (tristate consistency).

---

### User Story 3 - Strata travel automatically and invisibly (Priority: P2)

When any phonological rule is being transferred, the strata those rules reference (via
`StratumRA`) are carried along automatically; the user never sees or picks strata on the
page.

**Why this priority**: Spec 005 US2 established strata as an auto/never-user-picked
dependency. Among the five phonology categories only phonological rules reference a stratum,
so strata travel with rules; correctness of transferred rules depends on it, but it requires
no UI — so it ranks below the visible selection stories.

**Independent Test**: Bind a strata-bearing source, keep at least one phonological rule
selected, and confirm the plan includes the strata actions even though no strata row appears
on the page; deselect all phonological rules and confirm no strata actions are planned on
account of phonology.

**Acceptance Scenarios**:

1. **Given** at least one phonological rule is selected, **When** the plan is computed,
   **Then** the strata those rules reference are included as automatic (non-user-facing)
   actions.
2. **Given** no phonological rules are selected (or the whole block is off), **When** the
   plan is computed, **Then** no strata actions are planned on account of phonology — even if
   phonemes, natural classes, or environments are selected.
3. **Given** the Phonology page is rendered, **When** the user inspects it, **Then** no
   strata row, toggle, or count is shown.

---

### User Story 4 - Know what already exists in the target (Priority: P2)

Every selectable phonology row shows whether it is NEW, IN TARGET, or SIMILAR against the
early-bound target, so the user sees what will collide before transferring.

**Why this priority**: Reuses the 008/009 target-status logic; informs decisions but does
not gate them (conflict handling is deferred).

**Independent Test**: Bind source=target; confirm every phonology row reads IN TARGET. Bind
a fresh target; confirm rows read NEW.

**Acceptance Scenarios**:

1. **Given** a bound target, **When** the Phonology page renders, **Then** each selectable
   row shows NEW / IN TARGET / SIMILAR computed against that target.
2. **Given** no target bound, **When** the page renders, **Then** the target-status column
   is blank and the page does not crash.

---

### User Story 5 - Trimming a needed item is reported, not silent (Priority: P1)

If the user deselects a phonology item that another kept phonology item depends on, and the
target lacks it, the transfer is not silently broken — the user is warned once, in
aggregate, and must confirm at Move.

**Why this priority**: Constitution V (Referential Completeness) is non-negotiable. The
intra-phonology reference chain (phonological rules → natural classes and/or phonemes
directly → phonemes → phonological features) means a careless trim can strand a kept rule
against a missing class or phoneme. Allowing per-item trim obliges us to surface unmet
references.

**Independent Test**: Keep a phonological rule that references natural class C; deselect C
against a target that lacks C; confirm Preview shows an aggregated warning naming the kept
rule and that Move requires a single confirmation.

**Acceptance Scenarios**:

1. **Given** a kept natural class that references phoneme P, **When** the user deselects P
   and the target lacks P, **Then** Preview shows an entry-centric warning ("Natural class
   'X' references phoneme 'P' which will be missing") and Move pops one consolidated
   confirmation before writing.
2. **Given** several such omissions across categories, **When** the user reaches Move,
   **Then** they see a SINGLE dialog summarizing the count, not one prompt per stranded
   reference.
3. **Given** a kept phonological rule that references phoneme P directly as an input/output
   segment (not via a natural class), **When** the user deselects P and the target lacks P,
   **Then** Preview shows an entry-centric warning naming the rule and Move requires the same
   single consolidated confirmation.
4. **Given** a deselected item that no kept item references (or that the target already
   has), **When** the plan is computed, **Then** no missing-reference warning is raised for
   it.

---

### Edge Cases

- **Source with no phonology at all** (all five categories empty): the page renders every
  category empty and advances without error; the whole-block toggle reads unchecked/disabled
  (NOT vacuously fully-selected); no phonology or strata actions are planned.
- **Category empty but others populated** (e.g. 0 phonological rules, 32 phonemes): the
  empty category shows as empty; populated categories behave normally.
- **Phonemes / natural classes / environments selected but zero phonological rules**: no
  strata actions are planned — strata are rule-scoped (referenced only via a rule's
  `StratumRA`).
- **Whole-block-off then re-navigate**: returning to the page after toggling off re-derives
  the source inventory; re-toggling on restores all-selected (selection state is per the
  current page visit, not sticky beyond it — see Assumptions).
- **Deselecting a phoneme referenced by a kept natural class, target already has the
  phoneme**: no warning (the reference resolves in target); the phoneme simply isn't
  re-transferred.
- **Target already contains an item (IN TARGET)**: shown with IN TARGET status; Layer-1
  default governs add/skip (no conflict UI this phase).
- **No target bound**: target-status blank; missing-reference checks that need target data
  degrade gracefully (treated as if the target lacks the reference, per the safe default) —
  no crash.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The wizard MUST present a Phonology page positioned after Project+WS and
  before the Affixes page; the wizard order MUST be Project+WS → Phonology → Affixes →
  Skeleton → Grammatical deps → Preview → Finish.
- **FR-002**: The Phonology page MUST surface these categories, grouped and individually
  itemized: phonological features, phonemes, natural classes, environments, and
  phonological rules. It MUST NOT surface strata as a user-facing row (see FR-009).
- **FR-003**: The page MUST open with the whole phonology block preselected — every category
  group and every item row checked — so advancing without interaction transfers the entire
  block.
- **FR-004**: The page MUST provide a single whole-block toggle that selects or deselects
  all phonology categories and items at once; its state MUST reflect the aggregate of the
  category selections (tristate: all / none / partial).
- **FR-005**: Within each category, the user MUST be able to deselect (and re-select)
  individual items; category group toggles MUST reflect the tristate of their items.
- **FR-006**: Each category group MUST display the count of items it contains; a category
  with zero source items MUST render as empty (not an error) and MUST NOT block advancing.
- **FR-007**: Every selectable phonology row MUST display its target presence
  (NEW / IN TARGET / SIMILAR) against the bound target, using the same logic as the affix
  picker and 009 pages; blank when no target is bound.
- **FR-008**: The page's selections MUST feed the existing transfer plan and closure engine
  (`Lib/preview.py` / `Lib/transfer.py`) via the spec-005 category callbacks; nothing on the
  page writes to the target (the only write remains at Move). This feature adds no new engine
  categories; the sole engine change is a contained extension enabling per-item filtering
  (a per-category item-pick subset on `Selection`, honored by the phonology `enumerate_source`
  helpers) so FR-005 per-item trim is possible — the spec-005 leaf-dispatch otherwise
  transfers whole categories. This is a scope constraint recorded in Assumptions.
- **FR-009**: Strata MUST be transferred automatically and MUST NOT appear as a user-facing
  selectable row, toggle, or count. Strata actions MUST be included in the plan whenever any
  phonological RULE is being transferred (strata are referenced only by rules, via
  `StratumRA`); if no phonological rules are selected, no strata MUST be planned on account
  of phonology — even when phonemes, natural classes, or environments are selected.
- **FR-010**: Deselecting a phonology item that a kept phonology item references, when the
  target lacks that item, MUST be reported as an entry-centric missing-reference warning in
  Preview (one warning per kept item with an unresolvable reference) and MUST NOT be silently
  transferred broken (Referential Completeness). The intra-phonology reference chain to honor
  is: phonological rules → (inline rule context: natural classes and/or phonemes directly) →
  phonemes → phonological features; natural classes → phonemes → phonological features;
  phonemes → phonological features. Environments (`IPhEnvironment`) are referenced by
  allomorphs, not by phonological rules, and are NOT part of the rule-side chain.
- **FR-011**: Missing-reference warnings MUST be aggregated: Preview shows a consolidated
  list and Move presents a SINGLE confirmation dialog covering all phonology
  missing-reference omissions, never one prompt per stranded reference. These warnings MUST
  feed the shared cross-page aggregated Move gate (see Assumptions) so the user sees one
  combined confirmation dialog across all wizard pages, not a separate phonology dialog.
- **FR-012**: This phase MUST NOT present conflict-mode (ADD_NEW / MERGE / OVERWRITE)
  controls on the Phonology page; the per-category Layer-1 default MUST be applied
  automatically.

### Key Entities *(include if feature involves data)*

- **Phonology block selection**: the set of chosen phonology items across the five
  user-facing categories (phonological features, phonemes, natural classes, environments,
  phonological rules), each with a checked state and a target-presence status; plus the
  implicit whole-block toggle state.
- **Auto strata set**: the strata carried automatically whenever any phonology transfers;
  derived, never user-facing.
- **Missing-reference warning**: a (kept-item, stranded-reference) pair produced when a
  needed phonology item is deselected and absent from the target; aggregated for the shared
  Move gate.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On opening the Phonology page against a phonology-bearing source, 100% of
  source phonology items across all five categories are checked with zero user actions.
  (Ejagham Mini: 32 phonemes, 5 natural classes, 2+ environments all checked.)
- **SC-002**: Advancing the page unchanged produces a plan whose phonology item counts per
  category exactly equal the source inventory counts shown on the page.
- **SC-003**: Toggling the whole block off yields a plan with zero phonology items and zero
  strata actions attributable to phonology; toggling back on restores all items.
- **SC-004**: With at least one phonological rule kept, the plan includes the strata those
  rules reference, and no strata row/toggle/count is ever visible on the page.
- **SC-005**: Every phonology row shows a target-presence status; with source=target, 100%
  read IN TARGET; with a fresh target, rows read NEW.
- **SC-006**: Deselecting a needed, target-absent phonology item produces exactly one
  aggregated warning entry per kept item with an unresolvable reference (entry-centric,
  consistent with FR-010 and 009's SC-006) and a single Move confirmation dialog — never
  per-item prompts — and no warning is raised when the reference resolves in the target.
- **SC-007**: The wizard renders the Phonology page in position 2, immediately after
  Project+WS and before Affixes, in the order Project+WS → Phonology → Affixes → Skeleton →
  Grammatical deps → Preview → Finish.
- **SC-008**: The Phonology page presents no ADD_NEW / MERGE / OVERWRITE conflict-mode
  control; the per-category Layer-1 default is applied without user input.

## Assumptions

- The target project is bound before this page (Project+WS page), so target presence and
  missing-reference checks have live target data — same early-bind assumption as 008/009.
- **Default selection is ALL-preselected** (resolved during specification): the block opens
  fully checked and the user deselects to trim, consistent with the Model-A preselect
  pattern in 009 and Constitution V closure-by-default. "NONE" is reachable via the
  whole-block toggle.
- The spec-005 engine callbacks (`phon_features`, `phonemes`, `natural_classes`,
  `ph_environment`, `phon_rules`, `strata`) are complete and live-verified. This feature
  adds **no new categories** and no callback behavior change beyond a single contained
  extension: the leaf-dispatch today transfers every item in an enabled category, so
  delivering FR-005 per-item trim requires a per-category item-pick subset on `Selection`
  that the six phonology `enumerate_source` helpers filter by (absent subset = transfer all,
  preserving existing behavior for all other callers). Whole-block on/off and strata-gating
  need no engine change.
- The transfer unit for phonology is the individual LCM object (phoneme, natural class,
  etc.); there is no sub-object fragment selection.
- Selection state is derived from the current source inventory on each page visit; the
  wizard's cross-page selection persistence follows the existing 008/009 pattern (not
  redefined here).
- Conflict handling beyond Layer-1 defaults (field-level merge, per-category modes) is a
  later phase and OUT OF SCOPE.
- Variant/complex form types, ad-hoc/compound rules, custom fields, stems, and semantic
  domains are separate later roadmap increments and are OUT OF SCOPE.
- The missing-reference check reasons over the intra-phonology reference chain only; broader
  cross-block closure (e.g. a morphology item such as an affix template or allomorph
  referencing a deselected phoneme/environment) is NOT caught by FR-010's phonology-only
  check and is governed by the existing engine closure elsewhere.
- **Shared Move gate (dependency on 009):** the single aggregated confirm-on-Move dialog is
  owned by the existing wizard Move gate that feature 009's pages feed. This feature routes
  its phonology missing-reference warnings into that same gate (FR-011); it does not create a
  phonology-specific dialog. This is a dependency on 009's implementation, not re-specified
  here.
- **No target bound:** the missing-reference check treats the target as lacking every
  reference (safe default), so with no target bound a deselected needed item will raise a
  warning. This is a deliberate policy (surface-rather-than-hide); it is not a bug.

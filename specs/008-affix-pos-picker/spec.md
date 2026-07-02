# Feature Specification: Affixes-by-POS Item Picker

**Feature Branch**: `feature/007-selection-ui` (continuation; spec dir `008-affix-pos-picker`)

**Created**: 2026-07-01

**Status**: Draft

**Input**: User description: "Affixes-by-POS item picker (replaces the non-functioning 'Affixes by Template' section on wizard page 2). Build the missing inventory feed and group affixes by the part of speech they attach to."

## Context

The affix item-picker on wizard page 2 currently displays nothing. Investigation
established the root cause: **no code builds a source inventory and nothing invokes
the tree-population routine** — the one reference to the inventory constructs an
empty placeholder. The picker widget is fully wired but has never been connected to
live source-project data.

Rather than restore the original template-based grouping (which only covers
inflectional affixes that happen to be slotted into a template — a small subset in
toy/production projects), this feature reorganizes the picker around the part of
speech each affix **attaches to**, which is the grouping a linguist actually reasons
with. Template-based grouping is deferred to a later phase.

The design below was locked through a structured design interview and validated
against two live projects via the FlexTools MCP (read-only): **Ejagham Full GT-Test**
(inflectional-only baseline) and **Esperanto** (derivational + unclassified +
multi-POS affixes).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See affixes grouped by the POS they attach to (Priority: P1)

A user binds a source project and opens the item picker. Instead of an empty pane,
they see every affix in the source, organized under the part(s) of speech it attaches
to, each affix shown by its form and glosses. They can scan "what attaches to Verb?"
and immediately see the relevant affixes, deduplicated.

**Why this priority**: This is the core fix — without it the picker is unusable
(loads nothing) and the entire transfer flow is blocked at page 2. Delivers the MVP.

**Independent Test**: Bind Ejagham Full GT-Test, open page 2, confirm 33 affix
entries appear grouped under `v`, `n`, `num`, `pro`, plus one entry in the
Unattached drawer. No template grouping is shown.

**Acceptance Scenarios**:

1. **Given** a bound source project with affixes, **When** the item-picker page is
   entered, **Then** the tree populates with POS-grouped affixes (no manual refresh).
2. **Given** an affix whose sense MSA references Verb, **When** the tree renders,
   **Then** the affix appears once under the Verb group as `form → glosses`.
3. **Given** the same affix reached via two senses that both attach to Verb, **When**
   the tree renders, **Then** it appears as a single deduplicated row with glosses
   concatenated.

---

### User Story 2 - Select affixes by group and refine per item (Priority: P1)

A user checks a POS group to select all affixes that attach to it, then unchecks a
few individual affixes they don't want. The resulting selection feeds the transfer
plan.

**Why this priority**: Selection is the picker's purpose; grouping without selection
delivers no transfer value. Ships with P1.

**Independent Test**: Check the Verb group, confirm all verb-attaching affixes become
checked; uncheck one; confirm the collapsed selection contains every verb-attaching
affix GUID except the deselected one.

**Acceptance Scenarios**:

1. **Given** a POS group, **When** the user checks the group header, **Then** all
   affixes in its attaches-to subgroups become checked (but not affixes shown only
   because they *produce* that POS).
2. **Given** a checked group, **When** the user unchecks one affix, **Then** the
   selection excludes exactly that affix and retains the rest.
3. **Given** a nested sub-POS, **When** the user checks the parent POS, **Then**
   affixes under descendant POS nodes are also selected.

---

### User Story 3 - Handle derivational affixes by direction (Priority: P2)

A user working with a language that has derivational morphology sees each
derivational affix under both the POS it attaches to and the POS it produces, clearly
labeled by direction, so they can reason about derivation in either direction.
Checking or unchecking the affix in one place reflects everywhere it appears.

**Why this priority**: Essential for derivational languages (e.g. Esperanto) but
absent from the inflectional-only baseline project; correctness of the primary flow
does not depend on it.

**Independent Test**: Bind Esperanto, open page 2, confirm a derivational affix such
as `igi (From=Root, To=v)` appears under both the Root group (attaches-to) and the
Verb group (produces) with direction annotation; toggling it in one place toggles the
other.

**Acceptance Scenarios**:

1. **Given** a derivational affix with From=Root and To=Verb, **When** the tree
   renders, **Then** it appears in Root's "Derivation — attaches to" subgroup and in
   Verb's "Derivation — produces" subgroup, each annotated with the counterpart POS.
2. **Given** a derivational affix shown in two groups, **When** the user unchecks it
   in one, **Then** its checkbox clears in the other appearance too.
3. **Given** a POS group header is checked, **When** the group collapses to a
   selection, **Then** affixes shown only in that group's "produces" subgroup are NOT
   swept in by the header check.

---

### User Story 4 - Find affixes that cannot be grouped (Priority: P2)

A user sees affixes that have no part of speech (or no analysis at all) collected in a
clearly labeled drawer, split by reason, so nothing is silently dropped and they know
what needs fixing in FLEx.

**Why this priority**: Prevents silent omission of data; important for data hygiene
but affects a minority of affixes.

**Independent Test**: Bind Esperanto, confirm 7 affixes appear in the Unattached
drawer under the "no part of speech" subgroup.

**Acceptance Scenarios**:

1. **Given** an affix whose MSA has a null POS, **When** the tree renders, **Then**
   it appears in the Unattached drawer under "Affixes with no part of speech".
2. **Given** an affix with no sense or no MSA, **When** the tree renders, **Then** it
   appears under "Affixes with no sense / no analysis".
3. **Given** the Unattached drawer, **When** the user checks it, **Then** its affixes
   are selectable like any group.

---

### Edge Cases

- **Affix attaching to multiple POS**: appears under each relevant group; selection
  deduplicates by affix identity so it is transferred once. (13 such affixes in
  Esperanto.)
- **Empty gloss**: rendered as `(no gloss)` rather than a blank row.
- **Multiple senses with identical glosses**: glosses deduplicated before joining.
- **Nested POS hierarchy**: rendered nested; no roll-up of sub-POS into parents.
- **Source with zero affixes**: picker shows an empty-but-labeled tree, not an error.
- **MSA type the dispatch does not recognize**: affix routed to the Unattached drawer
  rather than dropped.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The item picker MUST populate from the bound source project when the
  item-picker page is entered, with no manual refresh step.
- **FR-002**: The system MUST enumerate affix entries from the source lexicon,
  identified as entries whose lexeme-form morph type is an affix type.
- **FR-003**: For each affix, the system MUST determine its attachment POS(es) by
  reading each of its morpho-syntactic analyses: inflectional and unclassified
  analyses contribute an "attaches-to" POS; derivational analyses contribute an
  "attaches-to" POS (the From-POS) and a "produces" POS (the To-POS).
- **FR-004**: Affixes MUST be grouped under the POS they attach to, rendered as a
  nested POS hierarchy without rolling sub-POS into their parents.
- **FR-005**: Within each POS group, affixes MUST be split into subgroups:
  Inflectional, Derivation — attaches to, and Derivation — produces.
- **FR-006**: Each affix MUST be rendered as a single row per (affix, group), showing
  its form and its concatenated, deduplicated glosses, with columns indicating type
  (inflectional/derivational/unclassified) and the From/To POS where applicable.
- **FR-007**: A derivational affix MUST appear under both its From-POS group and its
  To-POS "produces" subgroup, each annotated with the counterpart POS.
- **FR-008**: Checking a POS group MUST select the affixes in its two attaches-to
  subgroups (Inflectional and Derivation — attaches to) but MUST NOT select affixes
  shown only because they produce that POS.
- **FR-009**: Checking a parent POS MUST select affixes under its descendant POS nodes.
- **FR-010**: Users MUST be able to deselect individual affixes within a selected group.
- **FR-011**: When an affix appears in more than one place, toggling its checkbox in
  one place MUST toggle it in all appearances (consistent per-affix selection state).
- **FR-012**: The resolved selection MUST contain each selected affix once
  (deduplicated by affix identity), regardless of how many groups it appears in.
- **FR-013**: The system MUST collect affixes that cannot be grouped into an
  "Unattached affixes" drawer, split into "no part of speech" (has an analysis but no
  POS) and "no sense / no analysis" subgroups; the drawer MUST be selectable like any
  group.
- **FR-014**: POS labels MUST prefer the analysis abbreviation and fall back to the
  analysis name when no abbreviation exists.
- **FR-015**: Affix forms MUST use the best available vernacular representation;
  glosses MUST use the best available analysis representation; POS groups MUST render
  in the source's configured hierarchy order and affixes MUST render alphabetically by
  form.
- **FR-016**: Template-based grouping and template/slot selection MUST NOT appear in
  this picker (deferred to a later phase); the selection produced MUST remain
  compatible with the existing transfer plan without changes to the dependency-closure
  engine.

### Key Entities *(include if feature involves data)*

- **POS-Grouped Affix Inventory**: A snapshot of the source's affixes organized as a
  POS hierarchy. Each POS node carries the affixes that attach to it and the affixes
  that produce it; a separate bucket holds unattached affixes in two reason-labeled
  subgroups.
- **Affix Row**: One affix as shown in one group — its identity, form, concatenated
  glosses, morpho-syntactic type, and its From/To POS references.
- **Selection**: The set of chosen affix identities that feeds the transfer plan.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On binding a source project and opening the item picker, 100% of the
  source's affix entries are visible (grouped or in the Unattached drawer); none are
  silently dropped. (Ejagham: 33/33; Esperanto: 68/68.)
- **SC-002**: An affix that attaches to N parts of speech appears in N groups but
  resolves to exactly one entry in the selection. (Verified on Esperanto's 13
  multi-POS affixes.)
- **SC-003**: Every derivational affix appears under both its attaches-to and its
  produces POS with correct direction annotation. (Verified on Esperanto's 31
  derivational affixes.)
- **SC-004**: Affixes with no POS or no analysis appear in the Unattached drawer under
  the correct subgroup. (Ejagham: 1; Esperanto: 7.)
- **SC-005**: Checking a POS group and deselecting individual affixes yields a
  selection equal to the group's attaches-to affixes minus the deselected ones, with
  no produces-only affixes included.
- **SC-006**: The picker renders correctly for a project with only inflectional
  affixes and for a project with mixed inflectional/derivational/unclassified affixes.

## Assumptions

- The transfer unit is the whole affix entry; per-sense selection is intentionally not
  offered (you cannot transfer half an entry meaningfully).
- Group-level selection intent is not persisted; the resolved affix set is snapshotted,
  and the picker rebuilds from live source data on each run.
- The bound source project is available and readable when the item-picker page is
  entered (target binding and writing-system handling happen earlier in the wizard).
- Templates and slots remain in the data model for a later template-transfer phase but
  are not surfaced in this picker.
- The two previously identified transfer-engine defects (derivational dependencies not
  pulled into closure; live-lexicon enumeration accessor bug) are tracked separately as
  GramTrans issues #1 and #2 and are OUT OF SCOPE here.

# Feature Specification: Skeleton + Grammatical-Deps Selectors

**Feature Branch**: `feature/007-selection-ui` (continuation; spec dir `009-skeleton-deps-selectors`)

**Created**: 2026-07-01

**Status**: Draft

**Input**: User description: "Skeleton + Grammatical-deps selectors for the transfer wizard (feature 009). Adds two wizard pages after the affix picker, plus makes all affixes preselected."

## Context

Feature 008 delivered the affixes-by-POS picker. This feature extends the wizard down the
data-type stack (see [../wizard-selection-roadmap.md](../wizard-selection-roadmap.md))
with the two Model-A (item-derived) pages that sit between the affix picker and Preview:
the **morphology skeleton** (parts of speech, slots, templates) the picked affixes hang
off, and the **grammatical dependencies** (inflection features, inflection classes, stem
names, exception features) those POSes carry. Both are derived from the affix picks and
preselected; the user reviews, trims for a bare-bones transfer, or extends. It also flips
the affix picker to open **fully preselected**.

These two pages replace the old dense scope+conflict grid. Conflict-mode UI is deferred
(Layer-1 defaults apply automatically); the NEW/IN TARGET/SIMILAR target-status column
from 008 carries the collision information for now. Phonology and the other independent
blocks are separate later increments.

Grounded live via FlexTools MCP on Ejagham Full GT-Test (v: 4 slots / 1 template; n & num:
1 slot / 1 template each; 28 of 33 affix MSAs fill a slot; inflection classes 0, stem
names 0, inflectable features 0–1 per POS) and Esperanto.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Affixes start fully selected (Priority: P1)

Opening the affix picker, every affix is already checked; the user deselects the few they
don't want rather than hunting to check dozens.

**Why this priority**: The common case is "bring (almost) all of them"; select-by-default
removes the dominant friction. Small, independent, immediately useful.

**Independent Test**: Open the picker on Esperanto; confirm all 68 affixes and their group
tristates render checked; the collapsed selection contains all 68 before any interaction.

**Acceptance Scenarios**:

1. **Given** a bound source, **When** the affix picker page is shown, **Then** every affix
   row is checked and every POS/subgroup tristate reads fully-checked.
2. **Given** the fully-checked picker, **When** the user deselects one affix, **Then** the
   selection is all affixes except that one.

---

### User Story 2 - Review the morphology skeleton the affixes need (Priority: P1)

After picking affixes, the user sees the parts of speech, slots, and templates those
affixes require — already selected — and can trim to a bare-bones transfer or extend to
pull a whole template / all of a POS's slots.

**Why this priority**: The skeleton is what makes transferred affixes actually function in
the target; deriving and preselecting it is the core value of this feature.

**Independent Test**: Bind Ejagham, keep all affixes; on the skeleton page confirm POS
`v` (with its 4 slots and 1 template), `n`, and `num` appear preselected, each slot
annotated with the count of affixes filling it.

**Acceptance Scenarios**:

1. **Given** picked affixes attaching to Verb, **When** the skeleton page opens, **Then**
   Verb is preselected with its slots that those affixes fill checked, and slots no picked
   affix fills shown unchecked but available.
2. **Given** a slot filled by 3 picked affixes, **When** the skeleton renders, **Then** the
   slot row shows "3 affixes".
3. **Given** a template arranging referenced slots, **When** the skeleton opens, **Then**
   the template is preselected and lists its slots read-only (no duplicate checkboxes).
4. **Given** a preselected template, **When** the user checks it (or it stays checked),
   **Then** all slots it references are included even if no picked affix fills some of them
   (those extra slots may transfer empty), **and** the affix selection is unchanged.
5. **Given** a preselected template, **When** the user deselects it, **Then** only the slots
   the picked affixes fill remain (bare-bones; no template/arrangement).

---

### User Story 3 - Review the grammatical dependencies (Priority: P2)

The user sees the inflection features, inflection classes, stem names, and exception
features the picked affixes and their POSes pull in — preselected — and can deselect any
for a leaner transfer.

**Why this priority**: Completes the closure disclosure Constitution V requires; important
but often small (or empty) in practice, so lower than the skeleton itself.

**Independent Test**: Bind a source whose POSes carry inflectable features; confirm the
deps page lists them preselected and lets the user deselect one.

**Acceptance Scenarios**:

1. **Given** picked affixes whose POSes reference inflection features, **When** the deps
   page opens, **Then** those features are listed and preselected.
2. **Given** a source with no inflection classes or stem names, **When** the deps page
   opens, **Then** those sections are empty (not an error) and the page still advances.

---

### User Story 4 - Know what already exists in the target (Priority: P2)

Every selectable skeleton and deps row shows whether it is NEW, IN TARGET, or SIMILAR
against the bound target, so the user sees what will collide before transferring.

**Why this priority**: Reuses the 008 target-status logic; informs decisions but doesn't
gate them (conflict handling is deferred).

**Independent Test**: Bind source=target; confirm every skeleton/deps row reads IN TARGET.

**Acceptance Scenarios**:

1. **Given** a bound target, **When** the skeleton/deps pages render, **Then** each
   selectable row shows NEW / IN TARGET / SIMILAR computed against that target.

---

### User Story 5 - Deliberate omissions are reported, not silent (Priority: P1)

If the user deselects a skeleton or deps item that a picked affix actually needs, and the
target lacks it, the transfer is not silently broken — the user is warned once, in
aggregate, and must confirm.

**Why this priority**: Constitution V (Referential Completeness) is non-negotiable; the
whole point of allowing trims is that unmet dependencies are surfaced.

**Independent Test**: Deselect a slot that a kept affix fills against a target missing it;
confirm a warning names the affected affix and that Move requires confirmation.

**Acceptance Scenarios**:

1. **Given** a picked affix that fills slot S, **When** the user deselects S and the target
   lacks S, **Then** Preview shows an entry-centric warning ("Affix 'X' will have no slot")
   and Move pops one consolidated confirmation dialog before writing.
2. **Given** several such omissions, **When** the user reaches Move, **Then** they see a
   SINGLE dialog summarizing the count, not one prompt per affected affix.

---

### Edge Cases

- **POS/slot/template with no affixes** (e.g. an empty or unrelated POS): pruned from the
  skeleton, consistent with the affix picker's empty-POS pruning.
- **Slot on a POS that no picked affix fills**: shown unchecked (extend), not preselected.
- **Template referencing a slot that is not being transferred**: checking the template
  pulls that slot in (may transfer empty); it does not break.
- **Source with empty inflection classes / stem names**: deps sections render empty.
- **No target bound**: target-status column blank; no crash.
- **Deselecting a POS a picked affix attaches to**: EXCLUDED-LOSSY warning per US5.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The affix picker MUST open with every affix preselected (all rows checked,
  group tristates fully checked); deselection is the user's primary action.
- **FR-002**: The wizard MUST present a morphology-skeleton page after the affix picker,
  showing the parts of speech the picked affixes attach to, the slots those affixes fill,
  and the templates arranging those slots.
- **FR-003**: The skeleton MUST be preselected at the "as-needed" scope derived from the
  affix picks: a POS is preselected when a picked affix attaches to it; a slot is
  preselected when a picked affix fills it.
- **FR-004**: Slots on a preselected POS that no picked affix fills MUST be shown, unchecked
  and available to add (extend), not hidden.
- **FR-005**: Each slot row MUST be annotated with the number of picked affixes that fill it.
- **FR-006**: Templates MUST list the slots they arrange read-only (no separately-checkable
  duplicate slot nodes). The skeleton MUST render POS-rooted, with slots and templates
  nested under each POS.
- **FR-007**: A template that arranges any referenced slot MUST be preselected. Selecting a
  template MUST include its full set of referenced slots (extra slots may transfer empty)
  and MUST NOT add or remove any affix from the affix selection. Deselecting the template
  MUST leave only the slots the picked affixes fill.
- **FR-008**: The wizard MUST present a grammatical-dependencies page after the skeleton
  page, showing the inflection features, inflection classes, stem names, and exception
  features the picked affixes and their POSes require, all preselected and individually
  deselectable.
- **FR-009**: Every selectable row on the skeleton and dependencies pages MUST display its
  target presence (NEW / IN TARGET / SIMILAR) against the bound target, using the same
  logic as the affix picker; blank when no target is bound.
- **FR-010**: Deselecting a skeleton or dependency item that a kept affix requires, when the
  target lacks it, MUST be reported as an entry-centric warning in Preview and MUST NOT be
  silently transferred broken (Referential Completeness).
- **FR-011**: Such warnings MUST be aggregated: Preview shows a consolidated list and Move
  presents a SINGLE confirmation dialog covering all missing-reference omissions, never one
  prompt per affected item.
- **FR-012**: This phase MUST NOT present conflict-mode (ADD_NEW / MERGE / OVERWRITE)
  controls on any selection page; the per-category Layer-1 default MUST be applied
  automatically.
- **FR-013**: The new pages MUST replace the previous combined scope+conflict grid; the
  wizard order MUST be Project+WS → Affixes → Skeleton → Grammatical deps → Preview → Finish.
- **FR-014**: The skeleton and dependency selections MUST feed the existing transfer plan
  and closure engine; nothing on these pages writes to the target (the only write remains at
  Move).

### Key Entities *(include if feature involves data)*

- **Skeleton selection**: the set of chosen POSes, slots, and templates, derived from the
  affix picks, each with a preselected/checked state and a target-presence status.
- **Dependency selection**: the chosen inflection features, inflection classes, stem names,
  and exception features, derived from the picked affixes and their POSes.
- **Missing-reference warning**: an (affix, lost-reference) pair produced when a needed
  skeleton/dep is deselected and absent from the target; aggregated for the Move gate.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On opening the affix picker, 100% of source affixes are checked with zero user
  actions. (Ejagham 33/33; Esperanto 68/68.)
- **SC-002**: With all affixes kept, the skeleton page preselects exactly the POSes the
  affixes attach to and the slots they fill, with each slot's affix count correct. (Ejagham:
  v with 4 slots, n and num with 1 slot each; 28 of 33 affix MSAs map to a slot.)
- **SC-003**: Checking a template yields a slot set equal to all slots it references;
  deselecting it yields only the affix-filled slots — and neither changes the affix
  selection.
- **SC-004**: The dependencies page preselects exactly the features/classes/stem-names/
  exception-features reachable from the picked affixes' POSes, and renders without error when
  those collections are empty. (Ejagham: 0 classes, 0 stem names, features 0–1 per POS.)
- **SC-005**: Every skeleton/deps row shows a target-presence status; with source=target,
  100% read IN TARGET.
- **SC-006**: Deselecting a needed, target-absent item produces exactly one aggregated
  warning entry per affected affix and a single Move confirmation dialog — never per-item
  prompts.

## Assumptions

- The target project is bound before these pages (page 1), so target presence and
  EXCLUDED-LOSSY checks have live target data — same early-bind assumption as 008.
- The transfer unit remains the whole affix entry; the skeleton/deps pages select schema
  objects, not per-sense fragments.
- "AS-NEEDED" preselection derives from the current affix picks each time the page is
  entered; changing affix picks and returning re-derives the skeleton.
- Conflict handling beyond Layer-1 defaults (field-level merge, per-category modes) is a
  later phase and out of scope here.
- Phonology, variant/complex types, ad-hoc/compound rules, custom fields, and stems are
  separate later increments per the roadmap and are OUT OF SCOPE.
- GramTrans issues #1 (derivational closure) and #2 (EntriesOC) remain out of scope.

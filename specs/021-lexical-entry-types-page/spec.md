# Feature Specification: Lexical-Entry Types Page (Model-B Independent Block)

**Feature Branch**: `021-lexical-entry-types-page`

**Created**: 2026-07-05

**Status**: Draft

**Input**: User description: "Lexical-entry types wizard page (Model-B): Variant Types and
Complex Form Types selection. Engine done; no wizard spec. Roadmap build-sequence step 3."

## Context

This feature adds a **Model-B (independent block)** wizard page surfacing the two
lexical-entry-type inventories — **Variant Types** (`LexDbOA.VariantEntryTypesOA`,
roadmap #18) and **Complex Form Types** (`LexDbOA.ComplexEntryTypesOA`, roadmap #19).
Per the two-selection-model framing in
[../wizard-selection-roadmap.md](../wizard-selection-roadmap.md), a Model-B block is
self-contained grammar transferred wholesale (all-on with per-item trim, or whole-block
off) rather than derived from a lexical/affix pick. This mirrors the Phonology page
(spec 010) in structure and behavior; it is the second Model-B block to gain a UI.

The transfer **engine** for both categories already ships in
[Lib/categories.py](../../src/gramtrans/Lib/categories.py): `variant_types_*` and
`complex_form_types_*` provide `enumerate_source` (recursive walk of the owning
possibility list via `_walk_possibilities_via_lexdb`), `dependencies`, `plan_action`,
and `execute_action`. Both are **GOLD-aware** (`plan_action` skips GOLD-shipped types via
`_is_gold`) and **GUID-first**. Variant types additionally declare a cross-category
dependency (FR-327): an `ILexEntryInflType`'s `InflFeatsOA` constraint references
`IFsSymFeatVal`s, each yielded as `(INFLECTION_FEATURES, val_guid)` so the referenced
inflection-feature values travel with the variant type. This feature is therefore
**primarily UI/selection** — it surfaces the two categories as a wizard page and feeds the
user's picks into the existing plan/closure engine. It adds **no new engine categories**;
like spec 010 it needs only the contained per-item-trim extension (a per-category
item-pick subset on `Selection`, honored by the two `enumerate_source` helpers) so FR-005
per-item trim is possible.

Both categories are recursive possibility lists (types can own sub-types), so the page
must render the hierarchy, not a flat list.

Placement: this is a Model-B block whose only outward dependency (variant type →
inflection feature) points **into** the Model-A grammatical-deps selection. It is therefore
placed **after** the Model-A pages so its target-status and dependency preview reflect the
grammar already picked, and before Preview. Wizard order becomes:
Project+WS → Custom Fields → Phonology → Affixes → Skeleton → Grammatical deps →
**Lexical-entry types** → Rules → Preview → Finish. (Cross-category closure is computed at
Preview regardless of page order; placement is a UX choice — see Assumptions.)

Consistent with 010: no conflict-mode UI this phase (Layer-1 category defaults apply
automatically); the NEW / IN TARGET / SIMILAR target-status column carries collision
information; nothing on the page writes to the target (the only write remains at Move).

## Clarifications

### Session 2026-07-05

- Q: How should GOLD-shipped entry types appear on the page? → A: **Shown, cross-referenced to
  the target's GOLD by identity.** GOLD is a **matching/cross-referencing device — it links
  equivalent concepts across projects so they are not duplicated — NOT a write constraint.** The
  rule is: (1) a source GOLD type is matched to the corresponding target GOLD type by identity so
  the two link rather than a duplicate being created; (2) **field edits/clarifications** to a
  matched GOLD type (shortening a label, translating, editing the description) carry across
  freely as a field-level update — GOLD status does not lock these fields; (3) if the source has
  **redefined** a GOLD value — changed what it *means* (e.g. `n`→`adj`, `v`→`part`) — it simply
  no longer matches the target's GOLD value, so it naturally lands as a **new, user-defined
  type** rather than re-pointing the existing one. GOLD rows are therefore shown (not hidden) as
  matched/IN TARGET so the user sees the cross-reference; a redefinition surfaces as a separate
  NEW row. (Note: the field-edit handling is field-level merge, realized in the spec 020 phase;
  021 shows the rows and cross-references GOLD by identity.)
- Q: Page placement? → A: **Keep drafted order** — after Grammatical deps, before Preview.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Transfer the whole lexical-entry-type block (Priority: P1)

Arriving at the Lexical-entry types page, the user sees every user-defined variant type and
complex form type already selected, grouped by category with counts and rendered in their
owning hierarchy, and can advance with a single click to bring the block across.

**Why this priority**: "Bring the toy project's entry types wholesale" is the dominant
Model-B case and the reason the engine exists; all-selected-by-default delivers it with zero
interaction. This is the MVP slice.

**Independent Test**: Bind a source with variant/complex types; open the page; confirm both
categories render preselected with correct counts and hierarchy, and the collapsed selection
includes every user-defined type before any interaction.

**Acceptance Scenarios**:

1. **Given** a bound source with entry-type data, **When** the page is shown, **Then** every
   user-defined type row is checked and each category's group toggle reads fully-selected.
2. **Given** the fully-selected page, **When** the user advances without interacting,
   **Then** the plan includes all user-defined variant types and complex form types.
3. **Given** a category with zero user-defined types (only GOLD-shipped defaults), **When**
   the page renders, **Then** that category shows as empty (not an error) and the page still
   advances.

---

### User Story 2 - Toggle the whole block off, or trim individual types (Priority: P1)

The user can turn the entire block off with one control, or keep it on and deselect
individual types (and, for a parent type, its sub-types) for a leaner transfer.

**Why this priority**: Wholesale-with-opt-out is the defining Model-B behavior; without a
whole-block toggle and per-item trim the "NONE" and "bare-bones" cases are impossible.
Independently testable on top of US1.

**Independent Test**: Toggle the whole block off; confirm the plan contains zero entry-type
items. Toggle back on, deselect one variant type; confirm the plan contains all types except
that one.

**Acceptance Scenarios**:

1. **Given** the fully-selected page, **When** the user toggles the whole block off,
   **Then** all rows read unchecked and the plan contains no entry-type items.
2. **Given** the block on, **When** the user deselects a single variant type, **Then** the
   plan contains every entry type except that one.
3. **Given** a parent type deselected, **When** the page state is read, **Then** its
   sub-types' checked state and the category group toggle reflect the tristate consistently.

---

### User Story 3 - GOLD-shipped types are cross-referenced by identity (Priority: P2)

Types that ship with FLEx (GOLD) are matched to the target's corresponding GOLD type by
identity and shown as IN TARGET, so equivalent concepts link instead of duplicating. GOLD is a
cross-referencing device, not a write lock: field clarifications carry across freely. A GOLD
type the source has *redefined* (changed its meaning) no longer matches and naturally surfaces
as a separate NEW, user-defined row.

**Why this priority**: Cross-referencing GOLD by identity prevents duplicate concepts and is
handled by the engine's GOLD-match; it requires no bulk per-page decision, so it ranks below the
visible selection stories.

**Independent Test**: Bind a source whose lists mix GOLD defaults and user-defined types;
confirm GOLD types render matched/IN TARGET (linked, not duplicated); a source GOLD type whose
meaning diverges appears as a NEW row.

**Acceptance Scenarios**:

1. **Given** a source whose variant/complex lists contain GOLD defaults plus user-defined
   types, **When** the page renders, **Then** GOLD types are shown matched/IN TARGET to the
   target's equivalents and do not produce duplicate GOLD objects.
2. **Given** all selected user-defined types, **When** the plan is computed, **Then** matched
   GOLD types link to the target's existing GOLD objects rather than creating duplicates.
3. **Given** a source GOLD type the source has *redefined* (meaning changed, e.g. `n`→`adj`),
   **When** the plan is computed, **Then** it no longer matches and is planned as a NEW
   user-defined type.
4. **Given** a matched GOLD type differing only in minor fields (label shortening, translation,
   description), **When** field-level merge (spec 020) is engaged, **Then** those edits carry as
   a field update on the linked target object.

---

### User Story 4 - Variant-type inflection-feature dependencies travel automatically (Priority: P2)

When a kept variant type constrains inflection features (an `ILexEntryInflType` with an
`InflFeatsOA` constraint), the referenced inflection-feature values are pulled into the plan
automatically, even if they were not otherwise selected on the Grammatical-deps page.

**Why this priority**: FR-327 is already implemented in `variant_types_dependencies`;
correctness of a transferred inflection variant type depends on it. It requires no new UI, so
it ranks below the visible selection stories.

**Independent Test**: Keep an `ILexEntryInflType` referencing inflection-feature value V that
was not picked on Grammatical deps; confirm the plan includes V as a dependency action.

**Acceptance Scenarios**:

1. **Given** a kept `ILexEntryInflType` referencing inflection-feature value V, **When** the
   plan is computed, **Then** V is included as a dependency action even if V was not picked on
   the Grammatical-deps page.
2. **Given** a kept base variant type (no `InflFeatsOA`), **When** the plan is computed,
   **Then** no inflection-feature dependency is added on its account.

---

### User Story 5 - Know what already exists in the target (Priority: P2)

Every selectable type row shows whether it is NEW, IN TARGET, or SIMILAR against the
early-bound target, so the user sees what will collide before transferring.

**Why this priority**: Reuses the 008/009/010 target-status logic; informs decisions but does
not gate them (conflict handling is deferred).

**Independent Test**: Bind source=target; confirm every row reads IN TARGET. Bind a fresh
target; confirm rows read NEW.

**Acceptance Scenarios**:

1. **Given** a bound target, **When** the page renders, **Then** each selectable row shows
   NEW / IN TARGET / SIMILAR computed against that target.
2. **Given** no target bound, **When** the page renders, **Then** the target-status column is
   blank and the page does not crash.

---

### Edge Cases

- **Source with no user-defined entry types** (only GOLD defaults): both categories render
  empty; the whole-block toggle reads unchecked/disabled (NOT vacuously fully-selected); no
  entry-type actions are planned.
- **One category populated, the other empty**: the empty category shows as empty; the
  populated one behaves normally.
- **Deeply nested sub-types**: the hierarchy renders to full depth; deselecting a parent does
  not silently drop a sub-type the user still wants (per-item state is independent, with
  tristate roll-up).
- **Variant type referencing an inflection feature the target already has**: the dependency
  resolves in target; no missing-reference warning.
- **Variant type referencing an inflection-feature value that is deselected on Grammatical
  deps and absent from target**: reported as an entry-centric missing-reference warning
  routed to the shared Move gate (FR-010), never silently transferred broken.
- **No target bound**: target-status blank; missing-reference checks degrade gracefully
  (treat target as lacking the reference — safe default), no crash.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The wizard MUST present a Lexical-entry types page positioned after the
  Grammatical-deps page and before Preview.
- **FR-002**: The page MUST surface two categories, grouped and individually itemized in their
  owning hierarchy: Variant Types (`VariantEntryTypesOA`) and Complex Form Types
  (`ComplexEntryTypesOA`).
- **FR-003**: The page MUST open with all user-defined types preselected — every category
  group and every user-defined item row checked — so advancing without interaction transfers
  the block.
- **FR-004**: The page MUST provide a single whole-block toggle that selects/deselects both
  categories at once; its state MUST reflect the aggregate (tristate: all / none / partial).
- **FR-005**: Within each category, the user MUST be able to deselect (and re-select)
  individual types; category and parent-type group toggles MUST reflect the tristate of their
  descendants.
- **FR-006**: Each category group MUST display the count of user-defined types it contains; a
  category with zero user-defined types MUST render as empty (not an error) and MUST NOT block
  advancing.
- **FR-007**: Every selectable type row MUST display its target presence
  (NEW / IN TARGET / SIMILAR) against the bound target, using the same logic as the 008/009/010
  pages; blank when no target is bound.
- **FR-008**: The page's selections MUST feed the existing transfer plan and closure engine
  (`Lib/preview.py` / `Lib/transfer.py`) via the existing `variant_types_*` /
  `complex_form_types_*` callbacks; nothing on the page writes to the target (the only write
  remains at Move). This feature adds no new engine categories; the sole engine change is the
  same contained per-item-trim extension used by spec 010 (a per-category item-pick subset on
  `Selection`, honored by the two `enumerate_source` helpers; absent subset = transfer all).
- **FR-009**: GOLD-shipped types MUST be cross-referenced to the target's corresponding GOLD
  type by identity so equivalent concepts **link rather than duplicate** (GOLD is a matching
  device, not a write constraint). GOLD rows MUST be shown as matched/IN TARGET. Field
  clarifications on a matched GOLD type (label, translation, description) MAY carry as field-level
  updates (via spec 020) — GOLD status does not lock those fields. A source GOLD type whose
  meaning has been redefined no longer matches and MUST be planned as a NEW user-defined type.
- **FR-010**: A kept variant type's inflection-feature dependency (FR-327) MUST be carried into
  the plan automatically. If that referenced value is deselected on Grammatical deps AND absent
  from the target, it MUST be reported as an entry-centric missing-reference warning (one per
  kept type with an unresolvable reference), routed to the shared cross-page aggregated Move
  gate, never silently transferred broken (Referential Completeness, Constitution V).
- **FR-011**: Missing-reference warnings MUST feed the shared aggregated Move gate so the user
  sees one combined confirmation dialog across all wizard pages, never one prompt per stranded
  reference.
- **FR-012**: This phase MUST NOT present conflict-mode (ADD_NEW / MERGE / OVERWRITE) controls
  on this page; the per-category Layer-1 default MUST be applied automatically.

### Key Entities *(include if feature involves data)*

- **Entry-type block selection**: the set of chosen user-defined types across the two
  categories, each with a checked state, hierarchy position, and target-presence status; plus
  the whole-block toggle state.
- **Variant-type inflection dependency**: the `(INFLECTION_FEATURES, value_guid)` links a kept
  `ILexEntryInflType` carries via its `InflFeatsOA` constraint; derived, pulled automatically.
- **Missing-reference warning**: a (kept-type, stranded-inflection-value) pair produced when a
  needed value is deselected and absent from the target; aggregated for the shared Move gate.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On opening the page against a source with user-defined entry types, 100% of
  user-defined types across both categories are checked with zero user actions.
- **SC-002**: Advancing the page unchanged produces a plan whose per-category type counts
  exactly equal the user-defined source inventory counts shown on the page.
- **SC-003**: Toggling the whole block off yields a plan with zero entry-type items; toggling
  back on restores all types.
- **SC-004**: A matched GOLD type links to the target's existing GOLD object (no duplicate
  created); a source GOLD type whose meaning was redefined produces exactly one NEW user-defined
  type.
- **SC-005**: Every selectable row shows a target-presence status; with source=target, 100%
  read IN TARGET; with a fresh target, rows read NEW.
- **SC-006**: A kept inflection variant type whose referenced value is otherwise unselected and
  target-absent produces exactly one aggregated warning entry and a single Move confirmation —
  never per-item prompts; no warning when the reference resolves in the target.
- **SC-007**: The wizard renders the Lexical-entry types page after Grammatical deps and before
  Preview.
- **SC-008**: The page presents no ADD_NEW / MERGE / OVERWRITE control; the per-category
  Layer-1 default is applied without user input.

## Assumptions

- The target project is bound before this page (Project+WS), so target presence and
  missing-reference checks have live target data — same early-bind assumption as 008/009/010.
- **Default selection is ALL-preselected** (user-defined types only); the block opens fully
  checked and the user deselects to trim, consistent with 009/010 and Constitution V
  closure-by-default. "NONE" is reachable via the whole-block toggle.
- The `variant_types_*` and `complex_form_types_*` engine callbacks are complete and
  GOLD-aware. This feature adds **no new categories** and no callback behavior change beyond the
  same contained per-item-trim extension spec 010 introduces on `Selection` (shared, not
  re-specified here).
- The transfer unit is the individual type object; there is no sub-field fragment selection on
  this page (field-level merge is the 020 phase).
- **Page placement after Grammatical deps** is a resolved UX decision (variant-type deps point
  into inflection features): it lets target-status/closure reflect the picked grammar. Closure
  is nonetheless computed at Preview, so correctness does not depend on the exact slot.
- The shared aggregated Move gate is owned by the existing wizard Move gate (009/010); this
  feature routes its warnings into it and does not create a page-specific dialog.
- Conflict handling beyond Layer-1 defaults (field-level merge, per-category modes) is the
  later 020 phase and OUT OF SCOPE. Ad-hoc/compound rules (018), stems (019), custom fields
  (016), phonology (010), and semantic domains are separate increments and OUT OF SCOPE.
- **No target bound:** the missing-reference check treats the target as lacking every
  reference (safe default); this is deliberate surface-rather-than-hide policy, not a bug.

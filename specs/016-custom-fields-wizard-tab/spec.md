# Feature Specification: Custom Fields Wizard Tab (create-early, fill-later)

**Feature Branch**: `feature/016-custom-fields-wizard-tab`

**Created**: 2026-07-03

**Status**: Draft

**Input**: User description: "After the writing system tab, I think we need a tab listing
custom fields to copy over (grouped by their level (Entry, sense, etc.)). We would need to
create those custom fields early on so that we can fill them later."

## Context

The transfer wizard binds the target project and maps writing systems on its first page
(`_PageProjectWS`, "Project + Writing Systems"), then proceeds through the Model-B block
(Phonology, spec 010) and the Model-A pages (Affixes, Skeleton, Grammatical deps). Custom
fields are already **enumerated and grouped by owner level** by the engine
([Lib/categories.py](../../src/gramtrans/Lib/categories.py):
`_CUSTOM_FIELD_OWNER_CLASSES = ("LexEntry", "LexSense", "LexExampleSentence", "MoForm")`,
`_enumerate_custom_fields`, `custom_fields_enumerate_source`), the `CUSTOM_FIELDS` grammar
category exists in [Lib/models.py](../../src/gramtrans/Lib/models.py), and the creation
contract is specified in
[006-inflection-prep-block/contracts/custom-field-creation.md](../006-inflection-prep-block/contracts/custom-field-creation.md).
What is missing is a **wizard page** that surfaces those fields for selection and, critically,
a **plan-ordering guarantee** that the selected custom-field *definitions* are created in the
target **before** any downstream page's transfer writes *values* into them.

Custom fields are not first-class `ICmObject`s: they are virtual flids registered in the
project's meta-data cache (MDC). They have **no GUID**; their identity is the
`(owner class, field name)` tuple. Creation is a direct MDC call
(`target.Cache.MetaDataCacheAccessor.AddCustomField(class_name, field_name, field_type,
list_root_guid)`), not an `ICmObject` factory create. Because a value can only be written
into a flid that already exists, the definition MUST exist in the target before the entry /
sense / example / allomorph carrying that value is transferred — hence "create early, fill
later."

**Placement (resolved with the user):** the Custom Fields page sits **immediately after the
Writing System step** and before the Phonology page. This is deliberate: writing systems must
be mapped first (custom-field multistring values are WS-bearing), and the field definitions
must be created ahead of every grammar page that could fill them. New wizard order:
Project+WS → **Custom Fields** → Phonology → Affixes → Skeleton → Grammatical deps → Finish.
Consistent with spec 010 P-1, the page is referenced through a named accessor
(`page_custom_fields()`), never a literal index.

**Identity policy (resolved with the user):** a source custom field whose `(owner class,
field name)` matches an existing target field is treated as **already present** — the field
is reused and its values are filled; no new field is created. A **type difference** on a
same-name/same-class match is **NOT a collision** and MUST NOT block the transfer: it is
surfaced as an informational note. (This overrides the `IDENTITY_COLLISION` framing in the
006 creation contract for the wizard-driven path.)

Consistent with 009/010: no conflict-mode UI this phase (Layer-1 category default for
`CUSTOM_FIELDS` applies automatically); a NEW / IN TARGET target-status column carries
presence information; nothing on the page writes to the target (the only write remains at
Move).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See every source custom field grouped by level (Priority: P1)

Arriving at the Custom Fields page, the user sees every source custom field grouped under its
owning level — Entry, Sense, Example, Allomorph — each group showing a count and each field
showing its name and data type, all preselected, so advancing without interaction brings the
whole set across.

**Why this priority**: Enumeration grouped by level is the core ask and the MVP; the engine
already produces the grouped inventory, so surfacing it delivers immediate value with zero
interaction.

**Independent Test**: Bind a source with custom fields on multiple levels; open the Custom
Fields page; confirm the fields render grouped by level with correct counts and data-type
labels, all checked, before any interaction.

**Acceptance Scenarios**:

1. **Given** a bound source with custom fields on Entry and Sense, **When** the page is
   shown, **Then** an Entry group and a Sense group each render with their field count, every
   field row shows name + data type, and every row is checked.
2. **Given** a level with zero custom fields (e.g. no Allomorph custom fields), **When** the
   page renders, **Then** that level shows as empty (not an error) and the page still
   advances.
3. **Given** a source with no custom fields at all, **When** the page renders, **Then** all
   levels show empty, the whole-block toggle reads unchecked/disabled (not vacuously
   fully-selected), and the page advances without error.

---

### User Story 2 - Toggle the whole block off, or trim individual fields (Priority: P1)

The user can turn all custom fields off with one control, or keep the block on and deselect
individual fields within any level for a leaner transfer.

**Why this priority**: Wholesale-with-opt-out is the Model-B interaction contract (mirrors
spec 010 US2); without a whole-block toggle and per-field trim the "none" and "bare-bones"
cases are impossible.

**Independent Test**: Toggle the whole block off; confirm the plan creates and fills zero
custom fields. Toggle back on, deselect two fields; confirm the plan omits exactly those two.

**Acceptance Scenarios**:

1. **Given** the fully-selected page, **When** the user toggles the whole block off, **Then**
   all level and field rows read unchecked and the plan contains no custom-field
   creation or value-fill actions.
2. **Given** the block on, **When** the user deselects a single field, **Then** the plan
   omits that field's creation and value-fill but retains all others.
3. **Given** all fields in a level deselected individually, **When** the page state is read,
   **Then** that level's group toggle reads fully-unchecked (tristate consistency).

---

### User Story 3 - Definitions are created before values are filled (Priority: P1)

For every selected field absent from the target, the transfer plan creates the field
*definition* in the target **before** any page's value-write for that field runs, so no value
is ever written into a nonexistent flid.

**Why this priority**: This is the "create early, fill later" requirement and the correctness
core of the feature. A value written into a missing flid fails; ordering is non-negotiable.

**Independent Test**: Select a source Entry custom field absent from the target, plus source
entries carrying values in that field; run Preview; confirm the plan lists a
create-definition action ordered strictly before every fill-value action for that field, and
run Move against a fresh target to confirm the field exists and is populated.

**Acceptance Scenarios**:

1. **Given** a selected field absent from the target, **When** the plan is computed, **Then**
   it contains exactly one create-definition action for that field, ordered before all
   fill-value actions referencing it.
2. **Given** a selected field already present in the target (same class + name), **When** the
   plan is computed, **Then** no create-definition action is emitted for it and its
   fill-value actions target the existing flid.
3. **Given** Move runs, **When** it completes, **Then** every created field exists in the
   target MDC and carries the transferred values; the run reports counts of fields created
   vs reused and values filled.
4. **Given** a create-definition action fails (MDC refuses, returns flid 0), **When** Move
   runs, **Then** it fails loudly for that field (no orphan flid, no silent value drop) per
   the 006 creation contract's fail-loud discipline.

---

### User Story 4 - Know what already exists in the target (Priority: P2)

Every field row shows whether it is NEW or IN TARGET against the bound target, and a same-name
field whose data type differs from the source is flagged with an informational note — never as
a blocking conflict.

**Why this priority**: Reuses the 008/009/010 target-status pattern; informs decisions but
does not gate them. The type-difference note is a deliberate, non-blocking signal per the
resolved identity policy.

**Independent Test**: Bind source=target; confirm every field reads IN TARGET. Bind a fresh
target; confirm every field reads NEW. Create a same-name target field of a different type;
confirm the row reads IN TARGET with a type-difference note and the plan still proceeds.

**Acceptance Scenarios**:

1. **Given** a bound target, **When** the page renders, **Then** each field row shows NEW or
   IN TARGET computed by `(owner class, field name)` match; blank when no target is bound.
2. **Given** a source field matching a target field of a different data type, **When** the
   page renders, **Then** the row reads IN TARGET with an informational type-difference note
   and is treated as already-present (reused, not recreated, not blocked).
3. **Given** the type-difference case, **When** the plan is computed, **Then** no
   `IDENTITY_COLLISION` skip is emitted and no create-definition action is planned for that
   field.

---

### Edge Cases

- **Source with no custom fields**: all levels empty; whole-block toggle unchecked/disabled;
  zero create/fill actions planned; page advances.
- **Level empty but others populated**: empty level renders empty; populated levels behave
  normally.
- **Field present in target, same type**: IN TARGET, no create action, values filled into the
  existing flid.
- **Field present in target, different type**: IN TARGET + type-difference note, no create
  action, values filled into the existing flid; NOT a collision (per resolved policy).
- **List-backed field** (`ReferenceAtom` / `ReferenceCollection` pointing at a possibility
  list): the field definition carries its `list_root_guid`; whether the referenced list
  items themselves travel is governed by the existing engine closure, not re-specified here
  (see Assumptions).
- **No target bound**: target-status blank; the page does not crash; create/reuse
  classification degrades to "treat as NEW" (safe default) for preview purposes.
- **Field deselected but downstream page still selected**: values for a deselected field are
  simply not written; no error, no missing-reference warning (a custom-field value is not a
  referential dependency of its owning object).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The wizard MUST present a Custom Fields page positioned immediately after the
  Project+WS (Writing System) page and before the Phonology page; the wizard order MUST be
  Project+WS → Custom Fields → Phonology → Affixes → Skeleton → Grammatical deps → Finish.
  The page MUST be reached through a named accessor (`page_custom_fields()`), not a literal
  index (spec 010 P-1).
- **FR-002**: The page MUST list every source custom field on the supported owner classes,
  grouped by level: Entry (`LexEntry`), Sense (`LexSense`), Example (`LexExampleSentence`),
  and Allomorph (`MoForm`). Each field row MUST show the field name and its data type
  (CellarPropertyType, rendered as a human label, e.g. "String", "MultiString", "Integer",
  "List item").
- **FR-003**: The page MUST open with every field preselected — every level group and every
  field row checked — so advancing without interaction transfers the whole set.
- **FR-004**: The page MUST provide a single whole-block toggle that selects/deselects all
  levels and fields at once; its state MUST reflect the aggregate (tristate: all / none /
  partial).
- **FR-005**: Within each level, the user MUST be able to deselect and re-select individual
  fields; level group toggles MUST reflect the tristate of their fields.
- **FR-006**: Each level group MUST display its field count; a level with zero source fields
  MUST render as empty (not an error) and MUST NOT block advancing.
- **FR-007**: Every field row MUST display its target presence (NEW / IN TARGET) computed by
  `(owner class, field name)` match against the bound target; blank when no target is bound.
- **FR-008**: A source field whose `(owner class, field name)` matches a target field MUST be
  treated as already-present — reused, values filled into the existing flid, no create action.
  A data-type difference on such a match MUST be surfaced as an informational note and MUST
  NOT be treated as a collision, MUST NOT emit `IDENTITY_COLLISION`, and MUST NOT block the
  transfer.
- **FR-009**: For each selected field absent from the target, the transfer plan MUST emit
  exactly one create-definition action (via `MetaDataCacheAccessor.AddCustomField`) carrying
  the source field's type and, for list-backed types, its `list_root_guid`; help text and
  label overrides MUST be applied where the flexicon fork exposes the MDC setters (probe at
  planning time per the 006 contract).
- **FR-010**: The plan MUST order every create-definition action strictly **before** any
  value-fill action that writes into that field, across all downstream wizard pages, so no
  value is ever written into a nonexistent flid ("create early, fill later"). This is the
  non-negotiable ordering guarantee.
- **FR-011**: The page's selections MUST feed the existing transfer plan/closure engine
  (`Lib/preview.py` / `Lib/transfer.py`) via the `custom_fields` category callbacks; nothing
  on the page writes to the target — the only write remains at Move. Preview MUST list, per
  selected field, its create-vs-reuse action and the count of values to fill.
- **FR-012**: Create-definition failure (MDC returns flid 0) MUST fail loudly for that field
  (RuntimeError, no orphan flid, no silent value drop), per the 006 creation contract's
  fail-loud discipline. Re-running the same transfer MUST be idempotent: a field created on a
  prior run MUST match by `(class, name)` and emit zero new create actions.
- **FR-013**: This phase MUST NOT present conflict-mode (ADD_NEW / MERGE / OVERWRITE) controls
  on the Custom Fields page; the Layer-1 default for `CUSTOM_FIELDS` MUST be applied
  automatically.

### Key Entities *(include if feature involves data)*

- **Custom-field selection**: the set of chosen source custom fields across the four levels,
  each with a checked state, an owner class, a name, a data type, an optional list-root guid,
  and a target-presence status (NEW / IN TARGET, plus an optional type-difference note); plus
  the implicit whole-block toggle state.
- **Create-definition action**: a planned MDC `AddCustomField` for a selected, target-absent
  field, ordered before all value-fill actions for that field.
- **Value-fill action**: writing a source object's value for a custom field into the
  corresponding target flid, produced by the downstream (Entry/Sense/Example/Allomorph)
  transfer and gated on the field's definition existing.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On opening the page against a custom-field-bearing source, 100% of source
  custom fields render grouped by their correct level with correct per-level counts and
  data-type labels, all checked, with zero user actions.
- **SC-002**: Advancing unchanged produces a plan whose create + reuse counts per level
  exactly equal the source field inventory shown on the page.
- **SC-003**: Toggling the whole block off yields a plan with zero create and zero value-fill
  actions for custom fields; toggling back on restores all fields.
- **SC-004**: For every selected target-absent field, the plan orders its create-definition
  action before all value-fill actions for that field (0 violations), and a Move run leaves
  every such field present and populated in the target.
- **SC-005**: Every field row shows a target-presence status; with source=target, 100% read
  IN TARGET and 0 create actions are planned; with a fresh target, 100% read NEW.
- **SC-006**: A same-name/same-class field of differing type produces IN TARGET + a
  type-difference note, 0 `IDENTITY_COLLISION` skips, and 0 create actions — the transfer
  proceeds and fills the existing flid.
- **SC-007**: The wizard renders the Custom Fields page in position 2, immediately after
  Project+WS and before Phonology.
- **SC-008**: The page presents no ADD_NEW / MERGE / OVERWRITE conflict-mode control; the
  `CUSTOM_FIELDS` Layer-1 default is applied without user input.
- **SC-009**: Re-running the same transfer emits zero new create-definition actions (idempotent
  by `(class, name)` match).

## Assumptions

- The target project is bound and writing systems are mapped before this page (Project+WS
  page), so target presence, multistring value transfer, and WS resolution have live data —
  same early-bind assumption as 008/009/010. Placing Custom Fields after WS is required so
  WS-bearing custom-field values resolve.
- Supported owner classes are exactly the four already enumerated by the engine
  (`LexEntry`, `LexSense`, `LexExampleSentence`, `MoForm`); other owner classes are OUT OF
  SCOPE this phase.
- Custom fields have **no GUID**; identity is `(owner class, field name)`. Creation is via the
  MDC `AddCustomField` route documented in the 006 creation contract, not an `ICmObject`
  factory. The flexicon `CustomFieldOperations` wrapper's transaction-mode behavior for
  creation MUST be confirmed at planning time; if its `CreateField` wrapper is blocked in
  transaction mode, the plan uses the MDC-direct `AddCustomField` path (probe recorded in
  research.md).
- The "create early, fill later" ordering is a **plan-ordering** guarantee within Move; it is
  NOT an early/out-of-band write. All writes (definition creation included) still occur at
  Move after the user reviews the dry-run — Principle III is preserved. Custom-field
  definitions ARE schema changes to the target MDC and MUST appear in the Preview.
- A type difference on a `(class, name)` match is informational, never a collision (resolved
  with the user); the field is reused as-is. Whether a differing type can even accept the
  source value is a downstream value-write concern handled by the existing apply path
  (skip + report on incompatible write), not a page-level block.
- Whether possibility-list items referenced by list-backed custom fields travel is governed
  by the existing engine closure (Constitution V) elsewhere, not re-specified here.
- Selection state is derived from the current source inventory per page visit, following the
  existing 008/009/010 cross-page persistence pattern (not redefined here).
- Conflict handling beyond the Layer-1 default (field-level merge, per-category modes) is a
  later phase and OUT OF SCOPE.

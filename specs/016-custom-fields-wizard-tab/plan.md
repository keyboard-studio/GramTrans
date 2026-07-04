# Implementation Plan: Custom Fields Wizard Tab (create-early, fill-later)

**Feature**: `016-custom-fields-wizard-tab` | **Spec**: [spec.md](./spec.md) |
**Created**: 2026-07-03 | **Status**: Draft

## Summary

Add a **Custom Fields** wizard page immediately after the Project+WS (Writing System) page
and before Phonology. The page lists source custom fields **grouped by owner level** (Entry,
Sense, Example, Allomorph), all preselected, with a whole-block toggle, per-field trim, and a
NEW / IN TARGET status column. Selections feed the existing plan/closure engine via the
`custom_fields` category callbacks.

The one novel engine requirement is a **plan-ordering guarantee**: for every selected,
target-absent field, the Move plan emits a create-definition action (MDC `AddCustomField`)
and sequences it **strictly before** any value-fill action that writes into that field on a
downstream page. The wizard *step* is early; the *writes* still happen at Move, in the order
"definitions before content." Nothing on the page writes to the target.

## Technical Context

- **Language/runtime**: Python 3, FlexTools host; PyQt wizard (`QtWidgets.QWizardPage`).
- **Engine touch points**:
  - [Lib/categories.py](../../src/gramtrans/Lib/categories.py) — existing
    `_CUSTOM_FIELD_OWNER_CLASSES`, `_CustomFieldRecord`, `_enumerate_custom_fields`,
    `custom_fields_enumerate_source`. Extend to (a) carry data type + list-root guid on the
    record, (b) classify NEW vs IN TARGET by `(class, name)`, (c) emit create-definition
    plan actions for selected absent fields.
  - [Lib/models.py](../../src/gramtrans/Lib/models.py) — `GrammarCategory.CUSTOM_FIELDS`
    exists with Layer-1 default; add a `PlannedAction` kind for create-definition if the
    existing action model does not already express a non-`ICmObject` MDC write.
  - [Lib/preview.py](../../src/gramtrans/Lib/preview.py) /
    [Lib/transfer.py](../../src/gramtrans/Lib/transfer.py) — plan-builder / plan-executor.
    Add the definition-before-value ordering constraint (see Design Decision 3).
  - `src/gramtrans/Lib/ui/selection_wizard.py` — new `_PageCustomFields` page class + named
    accessor `page_custom_fields()`; renumber page titles ("Step N of M").
- **flexlibs2 fork surface** (`D:/Github/_Projects/_LEX/flexlibs2`):
  - `System/CustomFieldOperations.py` — `GetAllFields(owner_class)`, `FindField`,
    `GetFieldType`, `GetFieldName`. Creation route per 006 contract is MDC-direct
    `target.Cache.MetaDataCacheAccessor.AddCustomField(...)`. **Probe required**: confirm
    whether `CustomFieldOperations.CreateField` is blocked in transaction mode
    (`FP_TransactionError`) and whether MDC setters for help/label are exposed; record in
    research.md. Fork changes are avoided unless the probe shows creation is unreachable.
- **Reference specs**: 010 (Model-B page pattern, named-accessor P-1), 006 (custom-field
  identity + creation contract), 008/009 (target-status column, cross-page selection).

## Constitution Check (v5.0.0, Principles I–V)

- **I. FLEx Domain Fidelity** — PASS. Custom fields are treated as MDC virtual flids with
  `(class, name)` identity (no GUID, correctly). No GOLD/reserved data touched. WS mapping
  precedes this page so multistring custom-field values write against validated WSes.
  Create-failure fails loud (FR-012), never silently drops a value.
- **II. FlexTools-Compatible, flexlibs2-Direct** — PASS. Direct flexlibs2 /
  `Cache.MetaDataCacheAccessor` calls; no `flavors/` indirection. New page lives under
  `src/gramtrans/Lib/ui/`. Degrades gracefully (level renders empty) when a source lacks
  custom fields.
- **III. Preview-Before-Mutate (NON-NEGOTIABLE)** — PASS. The wizard *step* is early but is
  selection-only; **no page write**. Definition creation is a planned action surfaced in
  Preview and executed at Move like every other write. "Create early, fill later" is a
  *within-Move ordering* guarantee (definitions before content), not an out-of-band early
  write. Definitions, being MDC schema changes, MUST appear in the dry-run.
- **IV. Phased Merge Discipline** — PASS. Custom-field dedup + creation is a Phase-1 concern
  per the constitution ("deduplicate custom fields"; UI selects categories). Reuse-by-name,
  no overwrite of existing fields, matches additive/overwrite discipline. No Phase-2 conflict
  UI introduced.
- **V. Referential Completeness** — PASS with note. A custom-field *value* is not a
  referential dependency of its owning object, so deselecting a field strands nothing. For
  list-backed fields, the referenced possibility-list items travel (or not) via the existing
  engine closure — not re-specified here; recorded as an Assumption.

**Verdict**: No violations. One item to confirm empirically (creation route in transaction
mode) tracked in research.md.

## Key Design Decisions

1. **Grouping by level in the UI mirrors the engine's owner-class enumeration** — the four
   groups map 1:1 to `_CUSTOM_FIELD_OWNER_CLASSES` (LexEntry→Entry, LexSense→Sense,
   LexExampleSentence→Example, MoForm→Allomorph). No new grouping logic; the page renders
   what `custom_fields_enumerate_source` already yields, extended with type + status.

2. **Reuse-by-name, type-difference-is-informational** — a `(class, name)` match ⇒ reuse the
   existing flid, no create action, fill values. A type difference is a non-blocking note,
   never `IDENTITY_COLLISION` (resolved with user). This diverges from the 006 contract's
   `IDENTITY_COLLISION` framing for the wizard path; noted in the contract addendum.

3. **Definition-before-content ordering** — the core engine change. Options considered:
   - (a) A dedicated pre-pass in the plan executor that runs all custom-field create-definition
     actions first, before the leaf-dispatch that fills values. Simple, robust, matches the
     mental model. **Recommended.**
   - (b) A per-action dependency edge (each value-fill depends on its field's create action)
     resolved by a topological sort. More general but heavier; only needed if the plan model
     already does dependency ordering.
   Decision deferred to /speckit-tasks after reading the current plan-executor ordering in
   `Lib/transfer.py`; default to (a) unless the executor already sorts by dependency.

4. **Named accessor, index-agnostic wiring** — add `page_custom_fields()`; update every page
   that references neighbors by accessor; bump "Step N of M" titles. Follows spec 010 P-1 to
   avoid index fragility (this insertion shifts Phonology and everything after by one).

## Phased Task Outline (for /speckit-tasks)

- **Phase A — Research/probe**: confirm MDC `AddCustomField` reachability in transaction
  mode, help/label setter availability, and the type→label mapping (CellarPropertyType →
  "String"/"MultiString"/"Integer"/"List item"/…). Output: research.md + probe-results.md.
- **Phase B — Engine**: extend `_CustomFieldRecord` (type, list-root), NEW/IN-TARGET
  classification, create-definition plan action, and the definition-before-content ordering in
  `Lib/preview.py`/`Lib/transfer.py`. Unit tests extend
  `tests/unit/test_categories_custom_fields.py`.
- **Phase C — UI**: `_PageCustomFields` (grouped tree, whole-block toggle, per-field trim,
  tristate groups, status column), `page_custom_fields()` accessor, page insertion + title
  renumber.
- **Phase D — Integration/verify**: dry-run + Move on a source→fresh-target pair; confirm
  create-before-fill ordering, idempotent re-run, reuse-by-name, type-difference note. Attach
  pre/post artifacts per the constitution's verification gate.

## Open Questions / To Resolve in /speckit-clarify

- Data-type label set: exact CellarPropertyType → human-label mapping to display on rows.
- Ordering strategy: pre-pass (3a) vs dependency-sort (3b) — pending read of `Lib/transfer.py`.
- Whether the page should show, per field, the count of source objects carrying a value
  (informative but adds an enumeration pass) — nice-to-have, default off for MVP.

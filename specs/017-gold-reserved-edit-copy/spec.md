# Feature Specification: Copy Edits to Custom Items in GOLD_RESERVED Categories

**Feature**: `017-gold-reserved-edit-copy`

**Created**: 2026-07-05

**Status**: Final

## Problem Statement

GramTrans transfers custom (non-GOLD) items in GOLD_RESERVED categories across
FLEx projects by creating them additive-style from source to target
(Phase 0 / categories.py plan_action). Once an item has been created in the
target on a first run, subsequent runs correctly emit
`Skip(ALREADY_PRESENT_BY_GUID)` — the item is already there.

However, if the source item's display text (Name, Abbreviation, or Description)
was edited after the first transfer — for example a linguist refined the
description of a custom Variant Type or added an analysis-WS abbreviation they
had omitted — there is currently no path to propagate those edits to the
corresponding target item. The user must manually update the target item in
FLEx. With dozens of custom items spread across seven GOLD_RESERVED categories
this quickly becomes tedious and error-prone.

This feature introduces a **MERGE-per-WS edit copy**: when a non-GOLD item with
a matching GUID is already present in the target AND at least one of its three
multistring fields (Name, Abbreviation, Description) carries a target WS slot
that is empty while the source slot is non-empty, GramTrans emits a
`PlannedOverwrite(write_mode="merge")` action that fills those empty slots
without overwriting any target slot that already has content.

---

## User Stories

### US-1 — Edit copy for a custom POS or inflection feature (Priority: P1)

As a linguist whose toy project's custom Parts of Speech or Inflection Features
have evolved since the last transfer, I want GramTrans to detect that a custom
item already in my target is missing some WS slots present in the source, and
fill those slots, so that my target stays in sync without manual edits.

**Acceptance criteria:**
- For each non-GOLD ICmPossibility item already in the target by GUID, the plan
  phase inspects Name, Abbreviation, and Description WS-by-WS.
- A slot present in source but empty in target produces a
  `PlannedOverwrite(write_mode="merge")` with a descriptive summary.
- A slot that is non-empty in both source and target but carries different
  values is detected as a **per-WS conflict** and surfaced in the run report
  (conflict count; detail text identifying item GUID, field, and WS). It is NOT
  silently overwritten.
- A slot equal in source and target produces no action for that slot.
- If all slots are equal or target-non-empty, the item emits
  `Skip(ALREADY_PRESENT_BY_GUID)` exactly as today.

### US-2 — Edit copy across all seven GOLD_RESERVED categories (Priority: P1)

As a linguist, I want the same fill-gaps edit-copy behavior uniformly across all
seven GOLD_RESERVED categories — GRAM_CATEGORIES (POS), INFLECTION_FEATURES,
VARIANT_TYPES, COMPLEX_FORM_TYPES, POS, PHONOLOGICAL_FEATURES, and
SEMANTIC_DOMAINS — without having to think about which category I am in.

**Acceptance criteria:**
- All seven categories apply the guard chain and MERGE-per-WS logic identically.
- The logic is centralized in a shared helper so per-category plan_action
  functions call it rather than duplicating it.

### US-3 — GOLD items still unconditionally skipped (Priority: P1)

As a linguist, I want to be sure that GOLD items (non-empty CatalogSourceId)
remain completely untouched, even if a source GOLD item and a target GOLD item
share the same GUID. GOLD inviolability is absolute.

**Acceptance criteria:**
- `_is_gold()` is the first check in plan_action. If it returns True the
  function immediately returns `Skip(GOLD_INVIOLABLE)` — no edit-detection
  runs.
- IsProtected guard executes before MERGE-per-WS on non-GOLD items.

### US-4 — IsProtected items downgraded to link-only (Priority: P1)

As a linguist, when a custom (non-GOLD) item carries `IsProtected=True`, I want
GramTrans to respect that flag by not writing any field edits to it, consistent
with the existing Layer-2 protection policy.

**Acceptance criteria:**
- After `_is_gold()` passes (False), `apply_isprotected_layer2` is called.
- If it returns `ConflictMode.MERGE` (i.e., IsProtected is True), the item
  skips edit-detection and emits `Skip(ALREADY_PRESENT_BY_GUID)` with a note
  that edit copy was suppressed by IsProtected.

### US-5 — Per-WS conflicts surfaced, not silently overwritten (Priority: P1)

As a linguist, when a source WS slot and the corresponding target WS slot both
have content but differ, I want to see a conflict report rather than have my
target content silently replaced.

**Acceptance criteria:**
- Per-WS conflicts are collected into a list and appended to the
  `PlannedOverwrite.summary` or emitted as a separate `RunReport` conflict
  count (TBD in plan).
- If ALL differing slots are conflicts (none are genuinely empty-in-target),
  the item still produces no `PlannedOverwrite`; it emits
  `Skip(ALREADY_PRESENT_BY_GUID)` plus the conflict detail in the run log.
- Per-WS conflict resolution dialog is **Phase 2** — out of scope for this
  feature.

---

## Functional Requirements

### Guard Chain

**FR-E01 — GOLD inviolability guard (Principle I).**
`plan_action` for every GOLD_RESERVED category MUST check `_is_gold(piece)`
first (before any edit-detection). A non-empty `CatalogSourceId` causes
immediate `Skip(GOLD_INVIOLABLE)`. This guard executes before GUID lookup,
before IsProtected, and before MERGE-per-WS.

**FR-E02 — IsProtected Layer-2 guard.**
For a non-GOLD item already present in the target by GUID,
`apply_isprotected_layer2(cat, target_lcm_item, ConflictMode.MERGE)` MUST be
called. If it returns `ConflictMode.MERGE` (IsProtected=True), emit
`Skip(ALREADY_PRESENT_BY_GUID)` with detail noting "edit copy suppressed by
IsProtected". No field write is attempted.

**FR-E03 — Edit-detection only on non-GOLD, non-protected, present items.**
The MERGE-per-WS comparison (FR-E04 through FR-E07) runs only when:
1. `_is_gold(piece)` is False.
2. The item's GUID is already in the target (i.e., `_target_has_guid()` returns
   True for the category's target collection).
3. `apply_isprotected_layer2` does not downgrade to MERGE/LINK_ONLY.

### MERGE-per-WS Logic

**FR-E04 — Fields in scope.**
Edit detection and MERGE-per-WS apply to exactly three ICmPossibility
multistring fields: **Name**, **Abbreviation**, **Description**. No other field
is read, compared, or written by this feature.

**FR-E05 — Per-WS slot comparison.**
For each writing-system handle H present in the source item's multistring for a
field F, the executor compares `source.F.get_string(H)` with
`target.F.get_string(H)`:
- Source non-empty, target empty → **gap** (fill).
- Both non-empty, equal → **no-op** for that slot.
- Both non-empty, unequal → **per-WS conflict** (report, do not write).
- Source empty → skip that WS slot entirely (no write, no conflict).

**FR-E06 — PlannedOverwrite emission.**
If at least one gap exists (FR-E05 first bullet), emit:

```
PlannedOverwrite(
    category=<category>,
    source_guid=<src_guid>,
    target_guid=<src_guid>,   # same GUID — present-by-GUID match
    match_via="guid",
    write_mode="merge",
    summary=<human-readable summary listing fields/WS slots being filled>,
)
```

The `PlannedOverwrite` model at `models.py` L584-610 is reused unchanged. No
new action type is created.

**FR-E07 — All-equal / all-conflict / mixed idempotency.**
- All WS slots equal across all three fields → `Skip(ALREADY_PRESENT_BY_GUID)`
  unchanged from current behavior.
- All differing slots are conflicts (none are empty-in-target) and no gaps
  exist → `Skip(ALREADY_PRESENT_BY_GUID)` plus conflict detail in summary.
- Mixed (some gaps + some conflicts) → `PlannedOverwrite(write_mode="merge")`
  for the gap slots only; conflict slots are reported but not written.

**FR-E08 — Executor respects write_mode="merge".**
The existing `transfer.py` executor that handles `PlannedOverwrite` MUST honor
`write_mode="merge"` by filling empty target WS slots only. Implementation note:
the executor writes the three multistrings directly via `set_String` rather than
`ApplySyncableProperties`, because GOLD_RESERVED items are not accessed through a
flexicon wrapper that exposes `GetSyncableProperties`; the direct per-WS write
matches "empty slots only" exactly.

**FR-E08a — No residue tag on merge-fill writes (acceptable by design).**
Unlike sibling overwrite paths (Carrier A `LiftResidue` / Carrier B
Description-append), the merge-fill write does NOT append a carrier residue tag.
This is a ratified design decision (cycle-3 domain ruling + lead adjudication),
not an omission:
- **Idempotency does not require it.** The per-WS comparison in FR-E05 is itself
  the idempotency gate — on a second run the formerly-empty slot reads back
  non-empty and classifies as no-op (or conflict), so a fill is never repeated.
  Residue tags exist on other paths precisely because those paths lack this
  per-WS pre-write comparison.
- **A tag would pollute the field.** Name/Abbreviation/Description on a
  GOLD_RESERVED catalog item are primary user-facing display strings shown in
  FLEx's category/grammar editors. Appending provenance text to them would
  degrade the item for every target-project user. The residue-append convention
  is appropriate for `LiftResidue` and auxiliary Description slots on
  LexEntry/Sense, not for the primary display strings of shared catalog objects.

### Scope and Uniformity

**FR-E09 — All seven GOLD_RESERVED categories.**
The guard chain and MERGE-per-WS logic MUST apply uniformly to:
`GRAM_CATEGORIES`, `INFLECTION_FEATURES`, `VARIANT_TYPES`,
`COMPLEX_FORM_TYPES`, `POS`, `PHONOLOGICAL_FEATURES`, `SEMANTIC_DOMAINS`.

**FR-E10 — Shared helper.**
Implementation MUST extract a shared helper function (e.g.,
`_plan_gold_reserved_edit(piece, category, context, target_iter)`) called by
each category's `plan_action`. Per-category `plan_action` functions supply
their category enum value and their target-collection iterator; the helper
contains all guard-chain and MERGE-per-WS logic.

**FR-E11 — Absent items unaffected.**
If the source item's GUID is absent from the target, `plan_action` emits a
`PlannedAction` (ADD) exactly as today. This feature adds no new behavior for
absent items.

### Merge-Preview Integration

**FR-E12 — Merge-preview diff rendering.**
For categories already mapped to a `_CATEGORY_VALUE_TO_KEY` diff key in
`merge_preview.py` (`gram_categories` → `"gram_cat"`, `inflection_features` →
`"inflection_feature"`, `phonological_features` → `"phon_feature"`), the
existing per-item diff finder renders the Name/Abbreviation/Description
before/after automatically.

**FR-E13 — Diff rendering for unmapped categories.**
`variant_types`, `complex_form_types`, and `semantic_domains` currently map to
`None` in `_CATEGORY_VALUE_TO_KEY` (no standalone per-item diff path). For
this feature's `PlannedOverwrite(write_mode="merge")` actions on these three
categories, the acceptable fallback is rendering the edit summary text
(from `PlannedOverwrite.summary`) in the merge-preview pane without per-field
before/after columns.

A follow-up task to add proper diff-key support for these three categories
(mapping them to a `"cms_possibility"` or similar shared finder key in
`_CATEGORY_VALUE_TO_KEY` and `_PROPS_TABLE`) is noted here and tracked as a
non-blocking follow-up. Cross-reference:
[specs/012-merge-preview-diff-engine/plan.md](../012-merge-preview-diff-engine/plan.md).

---

## Non-Goals (Explicit)

The following fields on `ICmPossibility` and its LCM subclasses are explicitly
**out of scope**. They MUST NOT be read, compared, or written by this feature.

| Field / Property | LCM interface | Rationale |
|---|---|---|
| `SortSpec` / `SortField` | `ICmPossibility` | Presentation/display ordering. Overwriting would silently reorder user's target list. |
| `ForeColor` / `BackColor` / `UnderColor` / `UnderStyle` | `ICmPossibility` | Presentation styling. UI-local; partial overwrite could produce visual inconsistency with no linguistic benefit. |
| `IsProtected` | `ICmPossibility` | Protection flag itself — read for the guard (FR-E02), never written. |
| `InflFeatsOA` | `ILexEntryInflType` (Variant Types) | Structured inflection-feature assignment. Owning Atomic reference into the feature system; partial merge could corrupt the slot assignments expected by entries. |
| `MappingType` / `Asymmetric` | `ILexRefType` | Relation structural type. Changing these would silently alter the semantics of every entry that uses the relation. |
| `InflectableFeatsRC` | `IPartOfSpeech` | Reference collection into the inflection-feature system. Partial overwrite would corrupt POS-feature attachments that entries depend on. |
| `SubPossibilitiesOS` membership | all | Owner/parent structure. Adding or moving sub-possibilities changes the hierarchy; additive-transfer never restructures. |
| All GUID / hvo cross-references | all | GUID identity is read-only in this feature. Cross-references to the item from entries or other objects are not touched. |

---

## Success Criteria

**SC-E01** — A non-GOLD item present in both source and target with at least one
empty-in-target WS slot produces exactly one `PlannedOverwrite(write_mode="merge")`
in the plan output.

**SC-E02** — A GOLD item (non-empty `CatalogSourceId`) always produces
`Skip(GOLD_INVIOLABLE)` regardless of any WS comparison.

**SC-E03** — An item present in target with all three multistring fields fully
equal to source across all WS handles produces `Skip(ALREADY_PRESENT_BY_GUID)`
(idempotency — no spurious overwrites).

**SC-E04** — A per-WS conflict (both non-empty, unequal) is reported in the
run summary and does NOT produce a write of that slot. The target slot is
unchanged after Move.

**SC-E05** — An IsProtected item (IsProtected=True, non-GOLD) produces
`Skip(ALREADY_PRESENT_BY_GUID)` with a detail note; no field write.

**SC-E06** — All seven GOLD_RESERVED categories behave identically for cases
(a) through (d) in the test matrix (see below).

**SC-E07** — No field outside the three multistring scope (Name, Abbreviation,
Description) is read, compared, or written by any code path introduced by this
feature.

**SC-E08** — The existing unit test suite passes without regressions after this
feature lands (no pre-existing test broken).

---

## Constitution Compliance

**No constitutional amendment is required.**

Rationale (per Principles I–V):

- **Principle I (FLEx Domain Fidelity):** This feature touches only a custom
  item's own three multistring display fields (Name, Abbreviation, Description)
  on an item whose `CatalogSourceId` is empty — meaning it was created by the
  user, not from the FW/MGA catalog. GOLD objects are unconditionally skipped
  by the first guard (FR-E01). The feature never touches GOLD items, never
  alters parent/owner/SubPossibilitiesOS membership, never changes structural or
  relational fields (see Non-Goals), and never rewrites existing target content
  (per-WS conflict slots are reported, not overwritten). All GUID and hvo
  cross-references from entries to this item remain intact — the item's identity
  is unchanged. This is additive-within-custom, fully consistent with the
  additive-transfer principle.

- **Principle II (FlexTools-Compatible, flexicon-Direct):** Implementation uses
  existing `ApplySyncableProperties` (flexicon's `BaseOperations`) for the
  merge write. No new runtime dependencies.

- **Principle III (Preview-Before-Mutate):** The new logic lives in `plan_action`
  (plan-builder, read-only) and the existing `PlannedOverwrite` executor path
  (plan-executor). The Preview/Move boundary is fully preserved.

- **Principle IV (Phased Merge Discipline):** This feature builds on the Phase 1
  `write_mode="merge"` path already in `PlannedOverwrite` and `transfer.py`.
  No phase reordering.

- **Principle V (Referential Completeness):** Edit copy is confined to the item's
  own fields; no closure computation is introduced or changed.

*If during implementation a genuine Principle conflict is found (e.g., a case
where writing Name/Abbreviation/Description changes the identity of an object
referenced by entries in a way that corrupts cross-references), work MUST STOP
and the conflict flagged to the team lead before proceeding.*

---

## Test Matrix

Coverage MUST include per-category tests for all seven GOLD_RESERVED categories
across the four cases below. Minimum: one test per (category, case) cell =
28 unit tests. Shared-helper tests may cover multiple categories in one
parametrized suite.

| Case | Description | Expected plan output |
|---|---|---|
| **(a) GOLD → skip** | Source item has non-empty `CatalogSourceId`. | `Skip(GOLD_INVIOLABLE)` |
| **(b) present + equal → skip** | Source GUID in target; all WS slots of all 3 fields equal. | `Skip(ALREADY_PRESENT_BY_GUID)` |
| **(c) present + edited → merge action** | Source GUID in target; at least one target WS slot is empty while source slot is non-empty. | `PlannedOverwrite(write_mode="merge")` |
| **(d) absent → add** | Source GUID not in target (and not GOLD). | `PlannedAction` (ADD) — unchanged from current behavior |

Additional required cases:

| Case | Description | Expected |
|---|---|---|
| **(e) present + conflict** | Source GUID in target; a WS slot non-empty in both, unequal. No gaps. | `Skip(ALREADY_PRESENT_BY_GUID)` + conflict detail in summary |
| **(f) present + mixed (gap + conflict)** | Some WS slots empty-in-target (gap), others non-empty-and-different (conflict). | `PlannedOverwrite(write_mode="merge")` for gap slots; conflict slots reported, not written |
| **(g) IsProtected + non-GOLD** | Target item has `IsProtected=True`; not GOLD. | `Skip(ALREADY_PRESENT_BY_GUID)` with IsProtected note |

---

## Dependencies and Cross-References

- **`models.py` L584-610** — `PlannedOverwrite` dataclass, reused unchanged.
  `write_mode="merge"` field is already defined.
- **`categories.py`** — `_is_gold()`, `_guid_str_from()`, `_target_has_guid()`,
  per-category `plan_action` functions for all seven GOLD_RESERVED categories.
- **`protection.py`** — `apply_isprotected_layer2()`, `_is_protected()`.
- **`transfer.py`** — existing `PlannedOverwrite` executor with
  `write_mode="merge"` (fill-gaps) path (Phase 1, FR-013).
- **`merge_preview.py`** — `_CATEGORY_VALUE_TO_KEY` table; diff-key mapping for
  GRAM_CATEGORIES / INFLECTION_FEATURES / PHONOLOGICAL_FEATURES already present.
  VARIANT_TYPES / COMPLEX_FORM_TYPES / SEMANTIC_DOMAINS currently map to None;
  see FR-E13 and follow-up note.
  Cross-reference: [specs/012-merge-preview-diff-engine/plan.md](../012-merge-preview-diff-engine/plan.md).
- **Constitution v5.1.0** — `.specify/memory/constitution.md`. No amendment
  required (see Constitution Compliance section).

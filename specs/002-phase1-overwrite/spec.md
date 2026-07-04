# Feature Specification: Phase 1 — Overwrite by Match

**Feature Branch**: `002-phase1-overwrite`

**Created**: 2026-06-20

**Status**: Draft

**Input**: Constitution v5.0.0 Principle IV (Phase 1 scope); Phase 0 spec
(`specs/001-phase0-additive-transfer/spec.md`) as reference shape.

---

## Clarifications

*Reserved for `/speckit-clarify` outputs. Leave empty until clarification
sessions are run.*

---

## User Stories

### User Story 1 — Overwrite an Outdated Target Item from a Refined Source (Priority: P1)

A linguist has already run a Phase 0 transfer. They have since refined the
grammar in the source toy project: corrected a POS abbreviation, added a new
slot to a template, and updated an inflection feature's glosses. They want to
push those refinements into the target without duplicating items that are
already there. They run the module in Phase 1 mode, and the items present in
both source and target (matched by GUID) are overwritten with the source's
current content. Items that exist only in the source are added. Items that
exist only in the target are left untouched.

**Why this priority**: The core Phase 1 value. Without overwrite semantics the
only safe operation is "add more copies," which produces a cluttered target
after the second run. Overwrite is the natural follow-up to Phase 0 once a
project is in active refinement.

**Acceptance Scenarios**:

1. **Given** a target containing a POS object with the same GUID as a source
   POS whose abbreviation has since changed, **When** the module runs in Phase 1
   mode, **Then** the target POS abbreviation is updated to match the source,
   the pre-overwrite value is recorded in residue, and the POS is listed in the
   run report as "overwritten".
2. **Given** a source item whose GUID does not exist in the target, **When** the
   module runs, **Then** the item is added (same Add path as Phase 0), tagged in
   residue, and listed as "added" in the report.
3. **Given** a target item whose GUID exists only in the target (no source
   counterpart), **When** the module runs, **Then** that item is left untouched
   and does not appear in the report's overwrite or add lists.

---

### User Story 2 — See Which Items Were Overwritten vs Added vs Left Untouched (Priority: P1)

After a Phase 1 run the user needs a three-way breakdown: items overwritten
(source had a match in target), items added (source items new to target), and
items skipped (not transferred for a documented reason). The statistics panel
and run report surface all three buckets per grammar piece category.

**Why this priority**: Co-equal with Story 1 — without the three-way report
the user cannot verify that overwrite ran correctly or audit what changed.

**Acceptance Scenarios**:

1. **Given** a completed Phase 1 run, **When** the run finishes, **Then** the
   statistics panel shows per category: overwritten count, added count, skipped
   count, and a skip list with human-readable reasons.
2. **Given** an overwritten item, **When** the user inspects its residue carrier
   in the target, **Then** the pre-overwrite field values are recoverable from
   the snapshot embedded in the residue.

---

### User Story 3 — Match by Fingerprint When Source GUIDs Were Not Preserved (Priority: P2)

For LCM classes where the factory does not accept a GUID override (notably
`IMoInflAffMsa` and `IMoAffixAllomorph`), the source object's original GUID was
not written to the target during Phase 0. Instead, the mapping was recorded in
`RunReport.identity_remap`. When the user runs Phase 1 to refresh MSA or
Allomorph fields, the matcher consults `identity_remap` first, then falls back
to a per-category fingerprint if no remap entry exists (e.g., a fresh target
with no Phase 0 history, or a category whose identity_remap was not captured).

**Why this priority**: MSA and Allomorph are high-frequency targets for Phase 1
overwrite (slot wiring changes, morphtype corrections). Without fingerprint
fallback, Phase 1 degrades to Phase 0 for these classes — duplicates instead of
updates.

**Acceptance Scenarios**:

1. **Given** an MSA whose source GUID does not appear in the target but whose
   fingerprint (owner entry GUID + POS GUID + slot GUIDs) matches a target MSA,
   **When** the matcher runs, **Then** `Match.via == "fingerprint"` and the
   target MSA is the overwrite candidate.
2. **Given** an Allomorph with a known `identity_remap` entry mapping its source
   GUID to a target GUID, **When** the matcher runs, **Then** `Match.via ==
   "identity_remap"` and the target GUID is resolved directly.
3. **Given** an object for which no GUID match, no remap entry, and no
   fingerprint match exists, **When** the matcher runs, **Then** `Match.via ==
   "none"` and the item is treated as an Add.

---

## Functional Requirements

### Action Verbs

- **FR-101**: Phase 1 MUST introduce **OVERWRITE** as a third action verb in the
  plan alongside ADD and SKIP. It is modelled as a new discriminator value — a
  `PlannedOverwrite` dataclass parallel to `PlannedAction` (ADD) and `Skip`,
  sharing `category`, `source_guid`, and `target_guid` fields — or as a
  discriminated union if the data model is refactored to accommodate it. It MUST
  NOT reuse the `PlannedAction` shape without distinguishing the verb.

### Matching — GUID First

- **FR-102**: The matcher MUST attempt a **direct GUID match** as its first step:
  look up `source_guid` in the target project's object index for the relevant
  category. If a target object with that GUID exists, it is the overwrite
  candidate; `Match.via = "guid"`.

### Matching — identity_remap Fallback

- **FR-103**: If no direct GUID match is found, the matcher MUST consult
  `identity_remap` (the `dict[str, str]` on `RunPlan` / `RunReport` from the
  prior Phase 0 run, keyed by source GUID → target GUID). If an entry exists,
  `Match.via = "identity_remap"`.

### Matching — Fingerprint Fallback

- **FR-104**: If neither GUID nor identity_remap produces a match, the matcher
  MUST attempt a **fingerprint match** using a per-category fingerprint function.
  Fingerprint definitions:

  | Category | Fingerprint tuple |
  |---|---|
  | `MSA` (`IMoInflAffMsa`) | `(category, owner_entry_guid, "MoInflAffMsa", pos_guid, frozenset(slot_guids))` |
  | `ALLOMORPH` (`IMoAffixAllomorph`) | `(category, owner_entry_guid, lexeme_form_text, morph_type_guid)` |
  | `GRAM_CATEGORIES` / `POS` | `(category, name_in_default_ws)` |
  | `SLOTS` | `(category, owner_template_guid, name_in_default_ws)` |
  | `TEMPLATES` | `(category, owner_pos_guid, name_in_default_ws)` |
  | `INFLECTION_FEATURES` | `(category, feature_class_name, name_in_default_ws)` |

  Each fingerprint function returns a hashable tuple. `Match.via = "fingerprint"`
  and `Match.fingerprint_key` is set to the computed tuple.

### Overwrite Safety

- **FR-105**: Overwrite MUST NOT mutate GOLD objects (carries over Phase 0
  FR-022). A GOLD object that is a match candidate MUST be skipped with
  `SkipReason.GOLD_INVIOLABLE`.
- **FR-106**: Before overwriting any field, the executor MUST record a
  **pre-overwrite snapshot** of all fields being changed in the residue carrier
  for the target object. The snapshot format is a JSON-serialisable dict embedded
  in the existing `[GT-Tag]:` carrier, using a `snap=` key:
  `[GT-Tag]: GT|<run_id>|<source>|<iso_ts>|snap=<base64(json_fields)>`.
  The snapshot MUST be sufficient for the user to recover the pre-overwrite value
  without opening the source project.
- **FR-107**: When a target object has custom fields and the source object also
  has custom fields, Phase 1 MUST deduplicate: fields already present with
  identical key+value are skipped; fields with a matching key but different value
  are overwritten (source wins per FR-109); fields present only in the target are
  preserved.

### ALREADY_PRESENT_BY_GUID Semantics Change

- **FR-108**: In Phase 0, `SkipReason.ALREADY_PRESENT_BY_GUID` was an
  informational skip (FR-009 permitted duplicates). In Phase 1,
  `ALREADY_PRESENT_BY_GUID` is NOT a skip — it is an OVERWRITE candidate.
  The planner MUST reclassify any item that would have been
  `ALREADY_PRESENT_BY_GUID` as a `PlannedOverwrite` instead, unless the matched
  target object is GOLD (FR-105) or the user has deselected overwrite for that
  category.

### Conflict Policy

- **FR-109**: When source and target both carry non-empty content for the same
  field, **source wins**. No interactive prompt is presented; the pre-overwrite
  value is preserved in the residue snapshot (FR-106). Phase 2 will add
  interactive per-field merge.

### Run Report

- **FR-110**: The run report MUST distinguish three buckets per category:
  **added** (new to target), **overwritten** (matched and updated), **skipped**
  (not transferred, with reason). The `CategoryReport` dataclass (or its
  Phase 1 replacement) MUST carry an `overwritten: int` field alongside `added`
  and `skipped`. The statistics panel MUST display all three.

---

## Success Criteria

- **SC-101**: For the Ejagham benchmark (the same toy → target pair used in
  Phase 0), a Phase 1 run where the source has 5 modified objects and 3 new
  objects MUST result in exactly 5 objects overwritten, 3 objects added, and
  0 unexpected skips — verified by snapshot diff of the target before and after.
- **SC-102**: Every overwritten object MUST have a parseable pre-overwrite
  snapshot recoverable from its residue carrier. Zero data loss on overwrite:
  the pre-overwrite field values MUST be reconstructable in full from the
  residue alone.
- **SC-103**: For objects transferred through `identity_remap` or fingerprint
  fallback (MSA, Allomorph), the Phase 1 overwrite rate on a target produced
  by a Phase 0 run MUST be >= 95% (i.e., the matcher finds the target object
  via remap or fingerprint for at least 95% of the MSA/Allomorph set that was
  originally transferred by Phase 0).

---

## Assumptions

- **Residue tag schema**: The `[GT-Tag]:` schema defined in Phase 0 (FR-010) is
  reused unchanged. Phase 1 extends it with an optional `snap=` suffix field;
  existing Phase 0 tags without `snap=` remain valid.
- **flexicon fork**: The MattGyverLee/flexicon fork remains the runtime
  dependency per constitution v5.0.0 Principle II. No additional fork patches
  are assumed to be required for Phase 1 at spec time.
- **identity_remap availability**: The `identity_remap` dict from a prior Phase 0
  `RunReport` is made available to the Phase 1 planner by the caller (e.g., via
  a persisted JSON snapshot or an in-session cache). If unavailable, the matcher
  falls directly to fingerprint.
- **Phase 0 complete**: Per constitution Principle IV, Phase 0 MUST be released
  and validated (Ejagham benchmark passing end-to-end) before Phase 1
  implementation begins.

---

## Out of Scope

- **Interactive merge** (per-conflict prompt with take-left / take-right /
  skip / other): Phase 2.
- **Per-field cherry-pick** (user selects which fields to overwrite per object):
  Phase 2.
- **Writing-system mapping wizard** (SFM-import style): Phase 2.
- **Fingerprint definitions for categories not listed in FR-104**: to be
  specified in `/speckit-clarify` before the Phase 1 plan is written.

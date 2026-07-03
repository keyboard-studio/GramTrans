# Feature Specification: Similar-Candidate Capture & Per-Item Resolution Data Model

**Feature Branch**: `011-similar-resolution-datamodel`

**Created**: 2026-07-03

**Status**: Draft

**Input**: User description: "Similar-candidate capture and per-item resolution data model for the merge-preview workflow — feature 011. First of five features chunked from the per-item merge-preview + SIMILAR-resolution plan."

## Context

The wizard's selection pages classify every candidate row as NEW, IN TARGET, or SIMILAR
against the early-bound target (roadmap cross-cutting FR-018). Today SIMILAR is purely
informational: the user is told a source item resembles something in the target but has no
way to say *which* target item it corresponds to, nor to choose whether the source item
should merge into that match or be created fresh. The roadmap defers this to its final
increment: "Conflict-mode UI + field-level merge (its own phase)."

This feature is the **data-model foundation** for that phase — the first of five chunks
(011 data model → 012 diff engine → 013 transfer threading → 014 preview pane → 015 wizard
flow). It adds no UI diffing, no transfer behavior change, and no new wizard page. It
delivers exactly the typed vocabulary and capture logic the later chunks consume:

1. **Candidate capture** — while building the affix and phonology inventories, record the
   set of target entries a SIMILAR source item could correspond to (form + gloss for
   display, target GUID for identity), plus a best-guess suggested match.
2. **Per-item resolution model** — a frozen `SimilarResolution` describing, per source
   entry, one of three actions against a chosen target: `overwrite` (import is golden —
   source wins on every field), `merge` (link into the target but preserve its existing
   field values, writing source content only where the target is empty), or `create_new`
   (a fresh entry, no link), carried on `Selection` in the same inert-when-off pattern as
   existing per-item picks. "Keep the existing target unchanged" is *not* an action — the
   user expresses it by leaving the item unchecked (not transferred).

   > **Terminology note (2026-07-03):** an earlier draft had a two-way `merge` /
   > `create_new` action where `merge` executed as a source-wins entry overwrite. That
   > single write behavior is now named **`overwrite`**, and a genuinely distinct
   > **`merge`** (target-preserving, fill-the-gaps) is added. Downstream chunks (012/013/014)
   > must honor the split; see each spec's updated requirements.

Two facts from the plan's code audit shape the scope:

- **SIMILAR is not affix-only for display.** Phonology rows also earn SIMILAR via a
  casefolded label match. The data model must therefore let phonology rows carry the target
  GUID they matched (`matched_target_guid`) so a later diff can be computed — even though the
  *interactive resolution* workflow (merge-vs-create choice) stays affix-only.
- **Resolutions are keyed by source entry GUID**, not by the affix-pick set, because the
  Layer-3 walk plans every inflectional affix pointing at a walked POS regardless of picks.
  Default resolutions must therefore be seeded for every SIMILAR row (that seeding lives in
  the later page-state chunk).

Grounded in the existing selection/model code paths cited in the source plan
(`Lib/selection.py` `_build_target_sets`, `_entry_status`, `AffixRow`,
`PosGroupedAffixInventory`, `PhonologyRow`; `Lib/models.py` `Selection`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Capture the target entries a SIMILAR affix could match (Priority: P1)

When the affix inventory is built against a bound target, each SIMILAR affix row carries the
list of target entries it could correspond to (each with a display form and gloss and a
stable target GUID), plus a single suggested best match, so a later UI can offer a resolution
choice without re-querying the target.

**Why this priority**: Every downstream chunk (diff engine, pane, transfer) depends on this
capture existing. Without it there is nothing to merge into and no dropdown to populate. It
is the irreducible MVP.

**Independent Test**: Build the affix inventory from a source/target fake where a source
affix shares a form with two target entries; assert the row's candidate list contains both
target GUIDs with correct form/gloss, and the suggested match is the first candidate.

**Acceptance Scenarios**:

1. **Given** a bound target containing entries that share a normalized form with a source
   affix, **When** the affix inventory is built, **Then** that affix row is SIMILAR and
   exposes a `suggested_target_guid` equal to the first candidate's GUID for that form.
2. **Given** a source affix that is NEW (no target form match), **When** the inventory is
   built, **Then** its `suggested_target_guid` is unset (None).
3. **Given** the built inventory, **When** its searchable-candidate collection is read,
   **Then** it contains every distinct target affix candidate across the source (for a global
   dropdown), not only those matched to one row.

---

### User Story 2 - Represent a per-item overwrite / merge / create decision (Priority: P1)

A per-source-entry resolution can be expressed as "overwrite this specific target entry
(import is golden)," "merge into this specific target entry (keep its existing values, fill
gaps only)," or "create a new entry instead," validated so that both `overwrite` and `merge`
always name a target while `create_new` names none, and this resolution rides on the
`Selection` without affecting any behavior until the later transfer chunk consumes it.

**Why this priority**: This is the typed contract the pane emits and the planner reads;
defining and validating it now lets 013/014 be built against a stable type.

**Independent Test**: Construct `SimilarResolution` values directly; assert `overwrite`/`merge`
without a target GUID each raise, `overwrite`/`merge` with a target GUID and `create_new` (no
target) validate; assert a frozen `Selection` carrying `similar_resolutions` is unchanged in
all existing plan/closure behavior (regression).

**Acceptance Scenarios**:

1. **Given** the `SimilarResolution` type, **When** one is constructed with action `overwrite`
   or `merge` and no `target_guid`, **Then** construction fails validation.
2. **Given** action `overwrite` or `merge` with a `target_guid`, or action `create_new` with
   no `target_guid`, **Then** construction succeeds.
3. **Given** a `Selection` with a populated `similar_resolutions` map, **When** any existing
   planner/closure code runs, **Then** results are identical to a `Selection` without the map
   (inert-when-unused).
4. **Given** a `Selection`, **When** `similar_resolution_for(guid)` is called for a GUID with
   no recorded resolution, **Then** it returns None (no default fabricated at the model layer).

---

### User Story 3 - Phonology SIMILAR rows remember their name-match (Priority: P2)

Each SIMILAR phonology row records the target GUID it matched by label, so a later diff can
compare the two — even though phonology does not get the interactive merge/create choice.

**Why this priority**: Keeps the door open for phonology diffing (a display concern in
012/014) without committing to a phonology resolution workflow. Lower priority because no
transfer behavior depends on it.

**Independent Test**: Build the phonology inventory against a target with a label-matching
item; assert the SIMILAR phonology row carries the matched target GUID; assert a NEW phonology
row carries None.

**Acceptance Scenarios**:

1. **Given** a phonology source item whose casefolded label matches a target item, **When**
   the phonology inventory is built, **Then** that row is SIMILAR and carries the matched
   target GUID.
2. **Given** a phonology item with no target label match, **When** the inventory is built,
   **Then** the row is NEW and its matched target GUID is None.

---

### Edge Cases

- **Multiple target entries share the source form**: all become candidates, ordered
  deterministically; the suggested match is the first — no silent collapse to one.
- **SIMILAR row with an empty gloss on a candidate**: the candidate is still captured (form
  carries identity); the display gloss may be empty.
- **No target bound**: no candidates are produced, all rows resolve to NEW/None, and nothing
  crashes (same graceful-degrade contract as the existing status column).
- **Source affix walked but not affix-picked**: it can still be SIMILAR and must still get a
  default resolution seeded downstream (this feature provides the type + capture only; seeding
  for all SIMILAR rows is recorded for 013/014).
- **Frozen-dataclass back-compat**: new fields on `AffixRow` / `PosGroupedAffixInventory` /
  `PhonologyRow` are defaulted so existing constructions and tests keep working.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A frozen `SimilarCandidate` type MUST capture, for one target entry a SIMILAR
  source item could correspond to, a target GUID, a display form, and a gloss.
- **FR-002**: Building the affix target sets MUST produce, in addition to today's outputs, a
  map from normalized source form to its ordered tuple of `SimilarCandidate`s, and a flat
  ordered collection of all distinct candidates for a global searchable dropdown; the single
  existing call site MUST be updated to consume the new shape.
- **FR-003**: A helper MUST return the suggested target GUID for a given form (the first
  candidate for that form, or None when there is no match), leaving the existing status
  computation unchanged.
- **FR-004**: `AffixRow` MUST gain a defaulted `suggested_target_guid: Optional[str]`,
  populated only when the row's status is SIMILAR and unset otherwise.
- **FR-005**: The affix inventory container MUST gain a defaulted tuple of target affix
  candidates for the searchable dropdown, defaulting to empty.
- **FR-006**: `PhonologyRow` MUST gain a defaulted `matched_target_guid: Optional[str]`,
  populated for SIMILAR phonology rows from a label→GUID map kept during phonology inventory
  build, and left None otherwise.
- **FR-007**: A frozen `SimilarResolution` type MUST carry a source `entry_guid`, an action
  of exactly `overwrite`, `merge`, or `create_new`, and an optional `target_guid`, and MUST
  validate that both `overwrite` and `merge` name a `target_guid` while `create_new` does not.
  The `overwrite` action denotes source-wins-on-every-field (import golden); `merge` denotes
  target-preserving fill-the-gaps (source written only where the target field is empty).
- **FR-008**: `Selection` MUST gain a `similar_resolutions` mapping (source entry GUID →
  `SimilarResolution`) defaulting to empty, following the same inert-when-off pattern as
  existing per-item pick fields, plus a `similar_resolution_for(guid)` accessor returning the
  resolution or None.
- **FR-009**: All new dataclass fields MUST be defaulted so existing constructors, call
  sites, and tests remain valid without modification (back-compat).
- **FR-010**: This feature MUST NOT change any transfer planning, closure, or execution
  behavior; `similar_resolutions` MUST be inert until a later feature consumes it. It MUST NOT
  add a wizard page, widget, or diff rendering.

### Key Entities *(include if feature involves data)*

- **SimilarCandidate**: an immutable `(target_guid, form, gloss)` describing one target entry
  a SIMILAR source item could be merged into; the unit populating the resolution dropdown.
- **Candidate index (affix)**: form→candidates map plus the flat all-candidates collection,
  built once per target-set build and carried on the affix inventory.
- **SimilarResolution**: an immutable per-source-entry decision — `overwrite` a named target
  GUID (source wins), `merge` into a named target GUID (target-preserving, fill-gaps), or
  `create_new` — validated at construction, carried inertly on `Selection`.
- **Row-level match hints**: `AffixRow.suggested_target_guid` and
  `PhonologyRow.matched_target_guid`, the per-row seeds a later UI reads.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a source/target fixture with N SIMILAR affix forms, building the inventory
  yields exactly N rows with a suggested match set, and 0 suggested matches on NEW rows.
- **SC-002**: The inventory's global candidate collection contains every distinct target affix
  candidate exactly once (deduplicated), covering 100% of the candidates referenced by
  individual rows.
- **SC-003**: `SimilarResolution` rejects 100% of `overwrite`-without-target and
  `merge`-without-target constructions and accepts all valid
  `overwrite`/`merge`/`create_new` constructions.
- **SC-004**: A `Selection` carrying `similar_resolutions` produces byte-identical plans to
  the same `Selection` without it across the existing planner regression suite (inert
  guarantee).
- **SC-005**: Every SIMILAR phonology row carries a matched target GUID; every NEW phonology
  row carries None; with no target bound, all rows carry None and no error is raised.
- **SC-006**: The existing selection/model test suite passes unmodified (back-compat via
  defaulted fields).

## Assumptions

- The target project is bound before the selection pages (early-bind, as in 008/009/010), so
  candidate capture and match hints have live target data; with no target bound the safe
  default is "no candidates / NEW / None."
- "Default resolves into the suggested match" is a live-store concern (the page picker seeds
  a resolution for each SIMILAR affix row). The default action is **`overwrite`** — it
  preserves today's source-wins execution exactly, so introducing the three-way vocabulary
  does not silently change what an un-touched SIMILAR row does. The model layer intentionally
  does **not** fabricate a default in `similar_resolution_for`; it returns None when nothing is
  recorded. Seeding lives with the page state consumed in 014.
- Candidate ordering is deterministic (first candidate = suggested match); no ranking/scoring
  heuristic beyond source-form match is in scope.
- Normalized-form matching reuses the existing `_best_form`/`_collect_glosses` helpers; no new
  normalization policy is introduced.
- Interactive resolution (merge-vs-create) is affix-only; phonology gets only a
  `matched_target_guid` for future diffing. Offering phonology re-linking is explicitly
  deferred (open question in the source plan).
- **Downstream dependency (013/014):** consuming `similar_resolutions` in the planner and
  seeding defaults for all SIMILAR rows are OUT OF SCOPE here and specified in features 013
  and 014 respectively.
- Diff computation, HTML rendering, the preview pane, and any wizard-flow change are OUT OF
  SCOPE (features 012, 014, 015).

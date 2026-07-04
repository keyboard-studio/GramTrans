# Feature Specification: Merge-Preview Diff Engine & HTML Rendering

**Feature Branch**: `012-merge-preview-diff-engine`

**Created**: 2026-07-03

**Status**: Draft

**Input**: User description: "Pure merge-preview diff computation module with LCM props fetch, caching service, and HTML rendering — feature 012. Second of five features chunked from the per-item merge-preview + SIMILAR-resolution plan."

## Context

Feature 011 gave the selection layer the vocabulary to describe *which* target item a SIMILAR
source item could correspond to. This feature builds the **engine that shows the user what
transferring an item would actually do** to the target: a field-by-field, writing-system-aware
diff, rendered as colorized HTML, with no Qt dependency so it is fully unit-testable with
fakes.

It is the second of five chunks (011 data model → **012 diff engine** → 013 transfer
threading → 014 preview pane → 015 wizard flow). It produces a new pure module,
`src/gramtrans/Lib/merge_preview.py`, with three layers:

1. **Pure diff core** — given a source property dict, an optional target property dict, and a
   conflict mode, compute an ordered set of per-field diffs whose segments are tagged
   `added` / `unchanged` / `removed` / `note`. This *mirrors* (does not import) the
   `_deterministic_merge` semantics already in `conflict.py` so the preview matches what a
   real Move would do, while honoring the three conflict modes:
   - **NEW / create-new** (no target): every value is `added` (all green).
   - **LINK-ONLY** (category-default link-by-id, no field write): target fields `unchanged`;
     source-only fields get a `note` ("not transferred — links without field update"). This is
     the engine's original "MERGE" mode, renamed to avoid collision with the SIMILAR `merge`
     resolution below.
   - **OVERWRITE** (the SIMILAR `overwrite` resolution — import is golden, source-wins): per-key
     value-shape dispatch over multistrings, plain strings, list/tuple/set unions, and scalars,
     source winning on every differing value.
   - **MERGE-KEEP** (the SIMILAR `merge` resolution — target-preserving fill-gaps): equal →
     `unchanged`; source-only (or empty target) → `added`; target-only → `unchanged`; differing
     where the target already has a value → target `unchanged` plus a `note` that the source
     value is not applied (target wins). This mirrors 013's FR-007a apply semantics.
2. **LCM props fetch + category registry** — a `props_for(...)` that pulls a comparable
   property dict for any transfer category via `GetSyncableProperties`, with a per-category
   ops/finder table and **direct-multistring fallbacks** for the categories the flexicon fork
   does not cover (Slots, Phonological Features, Stem Names — see the plan's correction #5).
   Plus a writing-system→role classifier (`ws_role_map`) so value segments can be font-tagged.
3. **HTML rendering** — `to_html(preview, registry)` turning a computed preview into escaped,
   colorized, font- and direction-aware HTML for a read-only viewer, plus a Qt-free caching
   service (`MergePreviewService`) that memoizes computed previews keyed by
   `(category, source_guid, target_guid)` and lazily builds the target-entry GUID index.

The module touches no LCM live objects beyond a first-click fetch; it caches property **dicts**
(never LCM handles) per the repo's "no retained LCM handles" invariant.

Grounded in the code paths cited by the source plan: `conflict.py` `_deterministic_merge` /
`_is_merge_eligible` / `detect_conflicts`; `LexEntryOperations.py` multistring shape (ws-id
keyed dicts like "en", "koh", "koh-fonipa"); `categories.py` per-category ops precedents; the
`WsFontRegistry` / `WsFont` / `WsRole` font machinery.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See exactly what a merge would change, field by field (Priority: P1)

Given a source item's properties and a target item's properties under a given conflict mode,
the engine produces an ordered list of field diffs where each changed value is marked as added,
removed, unchanged, or an explanatory note — matching the semantics a real Move would apply.

**Why this priority**: This is the whole point of the merge-preview feature; the pane (014) is
just a viewer over this output. The pure core is independently testable and the highest-value
slice.

**Independent Test**: Call `diff_props` with fabricated source/target dicts across each mode
and value shape; assert segment kinds and field ordering without any Qt or LCM.

**Acceptance Scenarios**:

1. **Given** a None target (NEW / create-new), **When** `diff_props` runs, **Then** every
   field/value is emitted as `added`.
2. **Given** MERGE mode, **When** the source has a field the target lacks, **Then** target
   fields render `unchanged` and the source-only field carries a `note` that it will not be
   transferred.
3. **Given** OVERWRITE mode and a multistring field differing in one writing system, **When**
   `diff_props` runs, **Then** the differing ws shows `removed`(target text) beside
   `added`(source text) and equal ws values show `unchanged`; a target-only ws survives as
   `unchanged`.
4. **Given** OVERWRITE mode and a list/tuple/set field, **When** `diff_props` runs, **Then**
   the union is shown: common members `unchanged`, source-only `added`, target-only
   `unchanged`.
5. **Given** OVERWRITE mode and a scalar (int/bool/None) that differs, **When** `diff_props`
   runs, **Then** it renders `removed`(target) + `added`(source).
6. **Given** MERGE-KEEP mode and a field the target already holds with a differing value, **When**
   `diff_props` runs, **Then** the target value renders `unchanged` with a `note` that the source
   value is not applied; a field the target lacks (or holds empty) renders `added`.
7. **Given** any mode, **When** fields are emitted, **Then** they appear in alphabetical order
   mirroring conflict detection.

---

### User Story 2 - Diffs are legible: color, font, and script direction (Priority: P1)

The computed diff renders to safe HTML where added text is green, removed text is red with
strike-through, notes are gray italic, and every value span carries the correct font family,
point size, and direction for its writing-system role.

**Why this priority**: A diff the user cannot read (wrong vernacular font, mangled RTL, or
unescaped markup) fails the feature's purpose; rendering is co-equal with computation.

**Independent Test**: Feed a computed preview plus a fabricated `WsFontRegistry` to `to_html`;
assert escaping, per-role font-family/size, right-to-left direction where the role's font is
RTL, and strike-through on removed segments.

**Acceptance Scenarios**:

1. **Given** text containing HTML metacharacters, **When** rendered, **Then** it is escaped in
   the output (the viewer runs no scripts; escaping guards against rendering corruption).
2. **Given** a segment tagged with a writing-system role, **When** rendered, **Then** its span
   uses the font family and size the registry returns for that role.
3. **Given** a role whose font is right-to-left, **When** rendered, **Then** the span carries a
   right-to-left direction.
4. **Given** added / removed / note segments, **When** rendered, **Then** added is green,
   removed is red with strike-through, notes are gray italic, and indentation reflects the
   field's nesting depth.

---

### User Story 3 - Fetch comparable properties for any category, with fallbacks (Priority: P2)

The engine can pull a comparable property dict for a source or target object of any transfer
category, using the right operations wrapper per category, and — for the categories the
flexicon fork does not cover — falling back to direct guarded multistring reads so the diff
still has something to show.

**Why this priority**: Without props fetch there is nothing to diff for non-affix categories;
the fork gaps (Slots, Phonological Features, Stem Names) would otherwise crash or blank the
pane. Ranks below the core+render because affix ENTRY (the resolution workflow's subject) is
covered by the primary path.

**Independent Test**: Call `props_for` against fakes for a covered category (ENTRY/LexEntry) and
a gap category (Slots); assert the covered path returns the syncable props dict and the gap
path returns the direct-read `{field: {ws_id: text}}` shape (or None + note when even that
fails).

**Acceptance Scenarios**:

1. **Given** a covered category (e.g. affix ENTRY, POS, phonemes), **When** `props_for` is
   called, **Then** it returns the `GetSyncableProperties` dict, building any needed GUID index
   once and reusing it.
2. **Given** a template/slot request that requires the owner POS, **When** `props_for` is
   called, **Then** the owner GUID is used to resolve the wrapper.
3. **Given** a gap category (Slots, Phonological Features, Stem Names), **When** `props_for` is
   called, **Then** it returns a direct-read multistring dict of Name/Abbreviation/Description
   per writing system (plus optional bool for slots), or None with an explanatory note if the
   direct read fails.
4. **Given** a project's writing systems, **When** `ws_role_map` runs, **Then** each ws id is
   classified as VERNACULAR (in the vernacular list), IPA ("fonipa" in the tag), or ANALYSIS
   (otherwise), guarded so a missing/edge ws does not crash.

---

### User Story 4 - Recompute is cheap and re-link is a distinct result (Priority: P2)

Repeated previews of the same (category, source, target) return a cached result, while changing
the chosen target (re-link) produces a distinct cached result, and the cache can be invalidated
when the wizard re-enters a page.

**Why this priority**: The pane recomputes on every selection/re-link (a 014 requirement);
without memoization each click pays a linear target scan. Ranks P2 because correctness holds
without it — this is a performance guarantee.

**Independent Test**: Call `preview_for` twice with identical arguments and assert one
computation; call with a different target GUID and assert a distinct result; call `invalidate`
and assert recomputation.

**Acceptance Scenarios**:

1. **Given** a `MergePreviewService`, **When** `preview_for` is called twice with identical
   `(category, source_guid, target_guid, mode)`, **Then** the second call returns the cached
   result without recomputing.
2. **Given** the same source but a different `target_guid` (re-link), **When** `preview_for` is
   called, **Then** it computes and caches a distinct result under the new key.
3. **Given** a service with cached entries, **When** `invalidate` is called, **Then** the next
   `preview_for` recomputes.

---

### Edge Cases

- **Both source and target lack a field**: not emitted (only keys present on either side are
  diffed).
- **Target-only key**: `unchanged` — `ApplySyncableProperties` only touches keys it receives,
  so the target value survives; the preview must not imply deletion.
- **Non-multistring object value**: repr-stringified and treated as a plain string diff.
- **A writing system present in the value dict but not in the project's ws map**: the ws label
  is rendered as chrome (role None) and the value falls back to a default font.
- **Props fetch returns nothing** (fork gap with failed fallback): the preview shows a note
  rather than crashing or rendering an empty diff as "no changes."
- **MERGE-mode string-concat marker**: the run-id concat marker is a Move-time artifact; the
  preview shows replace semantics with a note where interactive merge could apply (it mirrors,
  not imports, `_deterministic_merge`).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A new pure module `Lib/merge_preview.py` MUST provide the diff types
  `DiffSegment(text, kind, ws_role)` with `kind` in {added, unchanged, removed, note},
  `FieldDiff(field_name, segments, indent)`, and `MergePreview(status, fields, notes)`, and
  MUST NOT import Qt. **Script direction (`rtl`) is resolved at render time in `to_html` from
  the `WsFontRegistry`, not stored on `DiffSegment`** — this keeps `diff_props` pure against
  plain dicts (lex-simplify, cycle 1).
- **FR-002**: `diff_props(src_props, tgt_props, mode, ws_role_of)` MUST, when `tgt_props` is
  None, emit every field/value as `added`.
- **FR-003**: In LINK-ONLY mode (the category-default link-by-id, formerly named MERGE),
  `diff_props` MUST render target fields `unchanged` and mark source-only fields with a `note`
  indicating they are not transferred (link-without-update).
- **FR-004**: In OVERWRITE mode (the SIMILAR `overwrite` resolution — source-wins), for each key
  in the union of source and target keys, `diff_props` MUST render: equal → `unchanged`;
  source-only → `added`; target-only → `unchanged`; differing → value-shape dispatch with the
  source value winning.
- **FR-004a**: In MERGE-KEEP mode (the SIMILAR `merge` resolution — target-preserving fill-gaps),
  for each key in the union, `diff_props` MUST render: equal → `unchanged`; source-only or
  empty-target → `added`; target-only → `unchanged`; differing where the target already holds a
  value → the target value `unchanged` plus a `note` that the source value is not applied
  (target wins). Per-writing-system emptiness is evaluated within the multistring value-shape
  dispatch (a ws empty on the target but present on the source is `added`).
- **FR-005**: The value-shape dispatch MUST handle: multistring dicts keyed by ws id (recurse
  per ws with the same equal/source-only/target-only/differing rules, differing ws showing
  removed+added); plain strings (removed+added); list/tuple/set (union: common unchanged,
  source-only added, target-only unchanged); scalars (removed+added); other objects
  (repr-stringify then treat as plain string).
- **FR-006**: `diff_props` MUST emit fields in alphabetical order, mirroring conflict
  detection, and MUST mirror (not import) the `_deterministic_merge` semantics.
- **FR-007**: `props_for(handle, category, guid, *, index=None)` MUST return a comparable
  property dict via the correct per-category operations wrapper, building any linear GUID index
  once and reusing it; template/slot requests MUST accept an owner GUID to resolve the wrapper.
- **FR-008**: For the fork-gap categories (Slots, Phonological Features, Stem Names),
  `props_for` MUST fall back to direct guarded multistring reads of Name/Abbreviation/
  Description per ws (plus optional bool for slots) into the same `{field: {ws_id: text}}`
  shape, returning None with a note if the direct read fails.
- **FR-009**: `ws_role_map(project)` MUST classify each ws id as VERNACULAR, IPA, or ANALYSIS
  using the vernacular list and the "fonipa" tag heuristic, guarded against edge/missing ws.
- **FR-010**: `to_html(preview, registry)` MUST HTML-escape all text, color added green,
  color removed red with strike-through, render notes gray italic, apply per-`WsRole`
  font-family and point size from the registry, set right-to-left direction where the role's
  font is RTL, indent by field nesting depth, and bold field names.
- **FR-011**: `MergePreviewService` MUST be Qt-free, hold source/target handles, the ws-role
  classifier, and a lazy target GUID index; `preview_for(category, source_guid, target_guid,
  status, mode, owner_guid="")` MUST compute lazily and memoize keyed by
  `(category, source_guid, target_guid, mode)`; re-link (different target) AND a resolution
  change (different mode) MUST each be a distinct key; `invalidate()` MUST clear the cache for
  page re-entry. **Rationale (lex-qc/lex-domain, cycle 1):** a user can flip a SIMILAR
  resolution (e.g. OVERWRITE → MERGE-KEEP) on the same source/target *in-page* without
  triggering `invalidate()` (which fires on page re-entry only, per SC-006 / US4). Omitting
  `mode` from the key would return a stale diff — a correctness defect, not a perf nit.
  Downstream features 014 (pane) and 015 (wizard dry-run) MUST honor this 4-tuple key shape.
- **FR-012**: The service MUST cache property **dicts**, never live LCM objects, and MUST
  re-fetch by GUID on first click (honoring the "no retained LCM handles" invariant).
- **FR-013**: This feature MUST NOT add any Qt widget, wizard page, or transfer behavior; it is
  consumed by feature 014 (pane) and depends on feature 011's `SimilarCandidate`/status types.

### Key Entities *(include if feature involves data)*

- **DiffSegment**: a run of text with a kind (added/unchanged/removed/note), an optional
  writing-system role, and a direction flag — the atom of the diff.
- **FieldDiff**: one field's ordered segments plus an indent depth.
- **MergePreview**: a status plus an ordered tuple of `FieldDiff`s plus free-text notes — the
  full computed diff for one item.
- **Category props table**: the per-category mapping from transfer category to its operations
  wrapper / finder, with direct-read fallbacks for the fork-gap categories.
- **WS role map**: ws id → VERNACULAR / IPA / ANALYSIS, used to font-tag value segments.
- **MergePreviewService**: the Qt-free cache and orchestrator that fetches props and computes
  previews on demand.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `diff_props` returns all-`added` segments for a None target across every value
  shape (0 non-added segments).
- **SC-002**: Across the mode × value-shape matrix (NEW, LINK-ONLY, OVERWRITE, MERGE-KEEP ×
  multistring, plain string, list, scalar, other), every combination produces the segment kinds
  specified in FR-002–FR-006, verified by unit tests.
- **SC-003**: Fields are emitted in alphabetical order in 100% of diffs.
- **SC-004**: `to_html` output escapes 100% of metacharacters, applies the registry's font per
  role, marks RTL roles with a right-to-left direction, and strikes through every removed
  segment.
- **SC-005**: `props_for` returns a non-None dict for every covered category fixture and the
  direct-read shape for every fork-gap fixture; a hard failure yields None + a note (never an
  exception to the caller).
- **SC-006**: `preview_for` computes once per distinct `(category, source, target, mode)` key; a
  repeat call performs zero recomputation, a re-link (different target) computes exactly one new
  entry, and a resolution change (different mode) on the same source/target computes exactly one
  new entry.
- **SC-007**: The module imports and runs with no Qt available (Qt-free guarantee), verified by
  the pure test modules.

## Assumptions

- The target project is opened write-enabled and held for the wizard's life (bound at page 1),
  so props fetches by GUID stay valid; the service still caches dicts, not handles.
- `GetSyncableProperties` is cheap; the dominant cost is the linear `LexEntry.GetAll()` scan,
  paid once per service when the GUID index is first built (mirrors the existing preview
  indexing).
- Multistring values are dicts keyed by ws id tag (e.g. "en", "koh", "koh-fonipa"); role
  classification maps ws id → `WsRole`, and the registry stores one `WsFont` per role.
- The preview intentionally mirrors, not imports, `_deterministic_merge`: the run-id
  string-concat marker is a Move-time artifact, so the preview shows replace semantics and
  annotates where interactive merge could apply.
- Fork coverage (CORRECTED cycle 1 by lex-author — the earlier "12 covered" reading conflated
  "has GetSyncableProperties" with "has a target finder"):
  - **Fully covered (4)** — GetSyncableProperties AND an existing finder: POS, LexEntry,
    Senses, Allomorphs.
  - **Finder-needed (8)** — GetSyncableProperties but NO finder (net-new finders required):
    Phonemes, NaturalClasses, Environments, PhonRules, Strata, GramCat, InflectionFeatures
    (targets IMoInflClass inflection *classes*, not IFsClosedFeature), MorphRules/templates
    (owner-POS-dependent two-level finder).
  - **Gaps (3)** — no GetSyncableProperties, direct-read fallback required: Slots, Phonological
    Features, Stem Names.
  - Fallback fields: Name / Abbreviation / Description + optional slot bool
    (`IMoAffixSlot.Optional`), emitted in `{field: {ws_id: text}}` shape.
- RTL handling is per-segment direction; full bidi layout in mixed LTR/RTL lines is
  best-effort, not guaranteed.
- **Upstream dependency (011):** the `SimilarCandidate` and status vocabulary are provided by
  feature 011.
- The preview pane widget, wizard integration, transfer threading, and the wizard-flow change
  are OUT OF SCOPE (features 014, 013, 015). This feature ships with pure unit tests only
  (diff + HTML + props fetch + caching).

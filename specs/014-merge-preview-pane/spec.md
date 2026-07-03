# Feature Specification: Merge-Preview Pane & Wizard Integration

**Feature Branch**: `014-merge-preview-pane`

**Created**: 2026-07-03

**Status**: Draft

**Input**: User description: "Merge-preview pane widget and wizard splitter integration across selection pages — feature 014. Fourth of five features chunked from the per-item merge-preview + SIMILAR-resolution plan."

## Context

Features 011–013 built the invisible machinery: the resolution data model (011), the diff
engine + HTML renderer + caching service (012), and the transfer pipeline that honors
resolutions (013). This feature is the **user-facing surface** that ties them together: a
per-item merge-preview pane docked beside each selection tree, plus — for SIMILAR affix rows —
an interactive resolution control (search-and-pick a target entry, or choose to create a new
one) that recomputes the diff instantly and feeds the choice into the transfer plan.

It is the fourth of five chunks (011 → 012 → 013 → **014 pane + wizard** → 015 flow). It adds
one new widget (`src/gramtrans/Lib/ui/merge_preview_pane.py`) and integrates it into the four
existing selection pages (affix item picker, skeleton, grammatical deps, phonology) of
`Lib/ui/selection_wizard.py` via a horizontal splitter, wiring tree-selection changes to the
pane and resolution changes back into per-page state.

Key behaviors from the source plan (sections 3 & 4):

- **The pane never touches LCM directly** — everything flows through the 012
  `MergePreviewService`; the pane is a viewer + a resolution control.
- **Selecting a tree row shows that item's diff**: NEW → all-green create preview; IN TARGET →
  same-GUID compare; SIMILAR affix → compare against the current resolution's target (or
  all-green when "create new"); SIMILAR phonology → compare against its matched target GUID
  (display only, no resolution control).
- **The resolution header is visible only for affix SIMILAR rows**: a searchable combo over the
  target-affix candidates (form — gloss) plus an **Overwrite / Merge / Create-new** three-way
  choice. **Overwrite** = import golden (source wins on every field); **Merge** = keep the
  target's existing values, fill only its empty fields; **Create-new** = a fresh entry.
  "Keep the existing target unchanged" is expressed by leaving the item unchecked in the tree
  (not transferred), not by a resolution control. Changing the combo or the action emits a
  resolution and recomputes the diff instantly (overwrite → source-wins diff; merge →
  target-preserving diff; create-new → all-green).
- **Per-item defaults are seeded here**: each SIMILAR affix row defaults to
  `overwrite(guid → suggested_target_guid)` (preserving today's source-wins behavior),
  satisfying 013's "seed a default for every SIMILAR row" requirement. `collect_selection()`
  folds the page's resolutions into the returned `Selection`.
- **The reconstruction caveat**: the preview reconstruction path rebuilds a `Selection` from
  affix picks and drops extra fields, so the dry-run/plan helper must copy
  `similar_resolutions` across via `dataclasses.replace`.

Grounded in the source plan's cited lines: the item-picker/skeleton/deps/phonology row builders
and their data roles; `_PageItemPicker`, `_PagePreview._on_preview`, `build_selection`; the
phonology double-connect guard; the wizard resize.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See a per-item merge preview beside every selection tree (Priority: P1)

On each selection page, selecting an item row shows, in a docked pane, a field-by-field preview
of what transferring that item would do to the target — all-green for new items, a same-item
compare for items already in the target — with correct fonts and script direction.

**Why this priority**: Surfacing the 012 diff for any selected item is the feature's baseline
value and works for all four pages regardless of the SIMILAR resolution workflow. It is the
MVP.

**Independent Test**: With an offscreen Qt harness, build a page with a `MergePreviewService`,
select a NEW row and an IN-TARGET row, and assert the pane renders an all-added preview and a
compare preview respectively.

**Acceptance Scenarios**:

1. **Given** a selection page wired to a service, **When** the user selects a NEW item row,
   **Then** the pane shows an all-green (create) preview for that item.
2. **Given** the same page, **When** the user selects an IN-TARGET row, **Then** the pane shows
   a same-GUID compare preview under the category's default conflict mode.
3. **Given** a group/header row (not an item), **When** it is selected, **Then** the pane clears
   (no stale diff).
4. **Given** a page that builds an inventory, **When** the page is (re-)entered, **Then** the
   pane is given a fresh service and font registry and any prior cached preview is invalidated.

---

### User Story 2 - Resolve a SIMILAR affix: overwrite, merge, or create new (Priority: P1)

For a SIMILAR affix row, the pane shows a resolution header: a searchable dropdown of candidate
target entries (form — gloss) defaulting to the suggested match, plus a three-way choice between
"overwrite" (import golden), "merge" (keep target, fill gaps), and "create new." Picking a
different entry or changing the action recomputes the diff immediately and records the choice for
the transfer.

**Why this priority**: This is the interactive workflow the whole feature is named for; it is
what turns 011's data model and 013's pipeline into a user capability.

**Independent Test**: Offscreen, show a SIMILAR affix row; assert the header is visible, the
combo filters by typed substring over "form — gloss," selecting a candidate under "overwrite"
emits an `overwrite`-resolution and re-renders a source-wins diff, switching to "merge" emits a
`merge` resolution and re-renders a target-preserving diff, and switching to "create new" emits a
`create_new` resolution and re-renders all-green.

**Acceptance Scenarios**:

1. **Given** a SIMILAR affix row, **When** the pane shows it, **Then** the resolution header is
   visible, the combo is pre-set to the suggested match, and the action is on "overwrite" (the
   default).
2. **Given** the combo, **When** the user types a substring, **Then** it filters candidates
   case-insensitively by "form — gloss" and does not insert free text.
3. **Given** the user picks a different candidate under overwrite or merge, **When** the selection
   changes, **Then** the pane recomputes the diff against the new target and emits a resolution
   of the current action carrying that target GUID.
4. **Given** the user switches the action to "merge," **When** it changes, **Then** the pane
   recomputes a target-preserving diff and emits a `merge` resolution; **given** a switch to
   "create new," **Then** it recomputes an all-green create preview and emits a `create_new`
   resolution.
5. **Given** a non-affix or non-SIMILAR row, **When** the pane shows it, **Then** the resolution
   header is hidden.

---

### User Story 3 - Resolutions default sensibly and flow into the plan (Priority: P1)

Every SIMILAR affix row starts resolved to "overwrite its suggested match" (import golden — the
current source-wins default) without user action, the page reflects each row's current resolution
in its Target column, and the collected selection carries all resolutions into the transfer plan.

**Why this priority**: 013's pipeline requires a resolution seeded for every SIMILAR row; without
this seeding + collection the transfer would not see the user's (or default) choices.

**Independent Test**: Build the item-picker page, collect the selection without interacting, and
assert every SIMILAR affix row has a default `merge`-to-suggested resolution in the returned
`Selection`; change one to create-new and assert the collected selection reflects it.

**Acceptance Scenarios**:

1. **Given** the item-picker page initializes with SIMILAR affix rows, **When** no interaction
   occurs, **Then** each such row has a default `overwrite(guid → suggested_target_guid)`
   resolution in the page store.
2. **Given** a resolution change from the pane, **When** it is received, **Then** the page
   updates its store and the row's Target column reads "SIMILAR → overwrite", "SIMILAR → merge",
   or "SIMILAR → new" accordingly.
3. **Given** the collected selection, **When** it is assembled, **Then** it folds in the page's
   resolutions (via `dataclasses.replace`), and the plan/dry-run reconstruction path copies
   `similar_resolutions` across rather than dropping them.

---

### User Story 4 - Phonology SIMILAR shows a diff, without a resolution control (Priority: P2)

Selecting a SIMILAR phonology row shows a compare preview against its matched target item, but
no merge/create control appears — phonology is display-only.

**Why this priority**: Reuses 011's `matched_target_guid` and the 012 engine for a useful
display, while honoring the decision that phonology re-linking is deferred. Lower priority than
the affix workflow.

**Independent Test**: Offscreen, select a SIMILAR phonology row and assert a compare preview
renders and the resolution header is hidden.

**Acceptance Scenarios**:

1. **Given** a SIMILAR phonology row with a matched target GUID, **When** it is selected, **Then**
   the pane shows a compare preview against that target and hides the resolution header.
2. **Given** a NEW phonology row, **When** it is selected, **Then** the pane shows an all-green
   create preview.

---

### Edge Cases

- **SIMILAR affix with no candidates** (edge of 011 capture): the header shows, the combo is
  empty, and "create new" is the only viable choice; selecting merge with no target is not
  possible.
- **Re-entering a page after changing picks**: the service is rebuilt and the cache invalidated
  so previews reflect current source/target state.
- **Deps page rows lacking a category/status data role**: the page adds the needed roles so the
  pane can build a preview request (item-data audit gap called out in the plan).
- **Template/slot preview requiring the owner POS**: the skeleton page carries the owner GUID
  into the preview request so the service can resolve the wrapper.
- **Double-connecting the tree-selection signal on re-entry**: guarded (as the phonology page
  already does) so the handler fires once.
- **A category with no diffable props** (fork gap with failed fallback): the pane shows the
  engine's note rather than a blank or a false "no changes."

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A new `MergePreviewPane` widget MUST render a computed preview as read-only HTML
  (via the 012 `to_html`) and MUST route all data access through the 012 `MergePreviewService`
  (never touching LCM directly).
- **FR-002**: The pane MUST expose `set_context(service, registry, candidates)` (called on each
  page's initialize), `show_item(request)` where the request carries category, source GUID,
  target GUID, status, mode, resolvable flag, current resolution, and owner GUID, and `clear()`
  for group/header rows.
- **FR-003**: The pane's resolution header MUST be visible only for affix SIMILAR rows
  (`resolvable`), showing a searchable combo over the target-affix candidates rendered as
  "form — gloss" (case-insensitive substring match, no free-text insertion, data = target GUID)
  and an Overwrite / Merge / Create-new three-way action control. The combo MUST be enabled for
  Overwrite and Merge (both name a target) and disabled/ignored for Create-new.
- **FR-004**: Changing the combo selection or the action MUST emit a resolution-changed signal
  carrying `(entry_guid, SimilarResolution)` with the current action and MUST immediately
  recompute and re-render the diff (overwrite → OVERWRITE source-wins diff; merge → MERGE-KEEP
  target-preserving diff; create-new → target None → all-green).
- **FR-005**: Each selection page MUST place its tree and the pane in a horizontal splitter
  (tree wider), via a shared helper applied in every page's UI build.
- **FR-006**: On each page's initialize, the page MUST construct a `MergePreviewService` for the
  bound source/target, call `set_context` with the service, a project font registry, and the
  page's candidate list (empty where not applicable), and connect tree-selection changes to a
  handler that builds the preview request (guarding against double-connect).
- **FR-007**: The preview request's conflict mode MUST come from the per-category Layer-1
  defaults; target GUID MUST be the source GUID when IN TARGET, the matched target GUID for
  phonology SIMILAR, the current resolution's target for affix SIMILAR, and None for NEW;
  `resolvable` MUST be true only on the item-picker page for affix rows with SIMILAR status.
- **FR-008**: The item-picker page MUST seed, on initialize, a default
  `overwrite(guid → suggested_target_guid)` resolution for every SIMILAR affix row (preserving
  today's source-wins behavior), update the store on pane resolution-changed signals, and reflect
  each row's resolution in its Target column ("SIMILAR → overwrite" / "SIMILAR → merge" /
  "SIMILAR → new").
- **FR-009**: The page's `collect_selection()` MUST fold its resolutions into the returned
  `Selection` (via `dataclasses.replace`), and any plan/dry-run reconstruction that rebuilds a
  `Selection` from picks MUST copy `similar_resolutions` across (not drop them).
- **FR-010**: Rows that today lack the data roles the pane needs (deps: category + status;
  others: status) MUST gain those roles wherever their status text is set, so a preview request
  can be built for any selectable row.
- **FR-011**: The wizard window MUST be resized to comfortably fit tree + pane side by side.
- **FR-012**: This feature MUST NOT change transfer planning/execution behavior beyond consuming
  the resolutions defined in 011 and honored in 013; it depends on features 011, 012, and 013.

### Key Entities *(include if feature involves data)*

- **MergePreviewPane**: the docked viewer + resolution control; emits resolution-changed,
  consumes the service.
- **PreviewRequest**: the per-selection request (category, source GUID, target GUID, status,
  mode, resolvable, current resolution, owner GUID) the page builds from the selected row.
- **Page resolution store**: the per-page map of source entry GUID → `SimilarResolution`, seeded
  with defaults and mutated by pane signals, folded into the collected `Selection`.
- **Candidate list**: the target-affix candidates (from 011) populating the searchable combo.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On all four selection pages, selecting an item row renders a preview in under the
  perceptible-delay threshold on first click (index built once) and instantly on cached
  re-selection.
- **SC-002**: For a SIMILAR affix row, changing the combo or the action recomputes and re-renders
  the diff with no page reload; overwrite renders a source-wins diff, merge a target-preserving
  diff, and create-new always renders all-green.
- **SC-003**: With zero interaction, 100% of SIMILAR affix rows carry a default
  overwrite-to-suggested resolution in the collected selection; changing a row to merge or
  create-new is reflected in the collected selection.
- **SC-004**: The resolution header is shown for exactly the affix SIMILAR rows on the item-picker
  page and hidden for all other rows (NEW, IN TARGET, phonology SIMILAR, non-affix).
- **SC-005**: SIMILAR phonology rows render a compare preview with no resolution control; NEW
  phonology rows render all-green.
- **SC-006**: The plan/dry-run reconstruction preserves `similar_resolutions` (0 dropped) so a
  resolved selection reaches the planner intact.
- **SC-007**: Offscreen-Qt pane tests cover header visibility, combo substring filtering, and
  both resolution signals.

## Assumptions

- Features 011 (resolution model + candidates), 012 (diff engine + service + `to_html`), and 013
  (planner/executor honoring resolutions) are merged; this feature is the UI over them.
- The target is bound before the selection pages (early-bind), so the service has live target
  data on first click; the service caches props dicts, not LCM handles.
- **012 cache key is a 4-tuple `(category, source_guid, target_guid, mode)`** (012 FR-011, fixed
  in cycle-1 review). When the user flips a SIMILAR resolution (Overwrite ↔ Merge ↔ Create-new)
  on the same item *in-page*, the pane MUST call `preview_for` with the new `mode` — the differing
  `mode` yields a distinct cache entry, so no `invalidate()` is required for a resolution flip
  (invalidate is for page re-entry only). The pane MUST NOT assume a 3-tuple key.
- General conflict-mode selection UI (per-category ADD_NEW/LINK-ONLY/OVERWRITE for non-SIMILAR
  rows) remains out of scope: those still use the per-category Layer-1 defaults. The pane exposes
  only the per-entry SIMILAR resolution — now a three-way Overwrite / Merge / Create-new choice
  (previously two-way). "Keep the existing target" is not a resolution; the user leaves the item
  unchecked in the tree.
- Phonology (and skeleton/deps) SIMILAR is display-only; the interactive merge/create control is
  affix-only, consistent with 011's scope and the deferred phonology-relink open question.
- Qt is imported guardedly (`importorskip("PyQt6")` in tests); pure logic remains in the 012
  module so the pane stays a thin viewer.
- The wizard page **flow change** (removing the standalone Preview step and gating Move behind a
  dry run) is OUT OF SCOPE here and specified in feature 015; this feature keeps the existing page
  flow and only docks the pane and wires resolutions. The dry-run/reconstruction helper's
  `similar_resolutions` copy (FR-009) is defined here because the pane produces the resolutions,
  but the dry-run gating itself lands in 015.

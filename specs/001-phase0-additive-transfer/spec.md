# Feature Specification: Phase 0 — Additive Grammar Transfer

**Feature Branch**: `001-phase0-additive-transfer`

**Created**: 2026-06-15

**Status**: Draft

**Input**: Project description: "Transfer FLEx Grammar Module — first deliverable, scoped to
Phase 0 (Additive) per constitution Principle IV. A FlexTools-compatible module that copies
selected grammar pieces from a source FLEx project (typically a 'toy' project used for
FLExTrans / parser bring-up) into a target production project. Phase 0 adds new items
unconditionally without conflict resolution or merge UI."

## Clarifications

### Session 2026-06-15

- Q: How should the module behave when source and target are on different LCM / FLEx
  versions? → A: Same-version is a precondition guaranteed by the host environment.
  Both projects are opened in the same FLEx instance with the same flexlibs version, so
  cross-version compatibility is not a concern in Phase 0; the module relies on this
  assumption rather than version-checking at runtime.
- Q: How does the module identify source and target projects? → A: The project currently
  open in the FlexTools host is always the **source** (the toy project, scanned most
  deeply); the **target** is chosen from a picker showing the user's available FLEx
  projects. Roles are not swappable in Phase 0.

### Session 2026-06-16

- Q: How should the module handle writing systems (vernacular and analysis) that
  differ between source and target? → A: Before the transfer runs, the user manually
  maps each source writing system 1:1 to a target writing system. Mapping covers
  **both vernacular and analysis** writing systems. When a needed target writing
  system does not yet exist, the user can opt to create it in the target as part of
  the mapping step. There is no auto-mapping, no fuzzy matching, and no silent
  drop-through of unmapped WSs in Phase 0.
- Q: What UI shape does per-affix selection use? → A: A **tree view by template →
  slot → affix** that mirrors the grammar structure. Affixes that are not yet bound
  to any template appear under an "Unbound" bucket at the top level of the tree, so
  bring-up-stage affixes (which often have no template assignment yet) remain
  selectable.
- Q: What format does the Import Residue tag use? → A: A **structured tag** carrying
  three fields: a run ID (e.g., `GT-YYYYMMDD-HHMMSS`), the source project's name, and
  an ISO-8601 timestamp. Per-run distinguishability is required; the format is
  designed to be reusable unchanged by Phase 1 (overwrite) and Phase 2 (interactive
  merge).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Copy Grammar Pieces from Toy Project to Production (Priority: P1)

A linguist has been using a small "toy" FLEx project to get FLExTrans and the parser
working. They have built up phonology, morphology, custom fields, affixes, slots, and
templates that all behave correctly. They now need that same grammar work to appear in
the much larger production project. They open the toy project in FlexTools (the host
project is always the source), run the module, pick the production project as target
from the picker, and the module copies the selected grammar pieces — together with
everything those pieces depend on — into the target. New objects
land in the target tagged so the user can audit what arrived.

**Why this priority**: Without this, every linguist who prototyped in a toy project must
rebuild the grammar by hand in production — the exact pain motivating the module. This is
the entire reason Phase 0 exists, and on its own it eliminates the manual rebuild step
even before merge sophistication arrives.

**Independent Test**: Open a known toy project with a documented grammar inventory and an
empty target project. Run the module with all categories selected. Verify that every
selected source item (and its dependency closure) exists in the target with the same
GUID, that referenced features/classes/categories exist in the target, that every new
object is tagged in Import Residue, and that the target's default vernacular writing
system is mapped from the source.

**Acceptance Scenarios**:

1. **Given** a toy source project containing phonemes, natural classes, gram categories,
   inflection features, custom fields, affixes (with allomorphs and APRs), slots, and
   templates, **and** an empty target project, **When** the user runs the module with all
   grammar piece categories selected, **Then** every selected source object appears in
   the target preserving its source GUID, every cross-reference resolves to an object now
   present in the target, and every newly created object is tagged in Import Residue.
2. **Given** a source project and a target project that already contains some unrelated
   grammar data, **When** the user runs the module, **Then** no existing target object is
   modified or deleted, and all new objects from the source are added alongside the
   existing ones (duplicates are explicitly permitted in Phase 0).
3. **Given** a source affix that references an inflection feature and an inflection
   class, **When** the user selects only that affix to transfer, **Then** the module
   automatically also transfers the referenced inflection feature and inflection class so
   the affix is functional in the target.
4. **Given** a source project that references writing systems (vernacular and/or
   analysis) not all present in the target, **When** the module reaches the
   writing-system mapping step, **Then** the user is prompted to map each source
   writing system 1:1 to a target writing system or create a new target writing
   system, and the transfer does not proceed until every referenced source writing
   system is mapped; once mapped, transferred strings are associated with the
   user-chosen target writing system.

---

### User Story 2 - See What Was Transferred (Priority: P1)

After running a transfer, the user needs to know exactly what arrived: how many items
per category, what was skipped and why, and whether anything failed. A statistics panel
appears at the end of the run summarizing additions and skips by category, with explicit
reasons for any skip (e.g., unresolved writing system, broken cross-reference). New items
are also discoverable in the target via Import Residue tagging so the user can later
audit, undo manually, or curate.

**Why this priority**: Adding hundreds of objects to a production project without
visibility is unacceptable; the user must be able to verify and audit the transfer
immediately. This is co-equal with Story 1 — neither is useful without the other.

**Independent Test**: Run a transfer that intentionally includes one item whose
dependency cannot be satisfied (e.g., a custom field referencing a writing system absent
in the target). Verify that the statistics panel reports the addition count per category,
lists the skipped item with its reason, and that newly added items in the target carry
the Import Residue tag.

**Acceptance Scenarios**:

1. **Given** a completed transfer run, **When** the run finishes, **Then** the module
   displays a statistics panel listing per category: items added, items skipped, and the
   reason for each skip.
2. **Given** an item that cannot be transferred because a dependency cannot be resolved,
   **When** the run completes, **Then** that item appears in the skip list with a
   human-readable reason, and no partial copy of it exists in the target.
3. **Given** any item successfully added to the target, **When** the user inspects the
   target in FLEx after the run, **Then** the item is identifiable as having come from
   this transfer via its Import Residue tag.

---

### User Story 3 - Choose Which Grammar Piece Categories to Transfer (Priority: P2)

The user often wants only a subset of the grammar inventory: maybe just the phonology, or
just the morphology, or just custom fields. Before running the transfer they select which
categories of grammar pieces participate. The categories include: writing systems check,
gram categories, inflection features, custom fields, inflection classes, stem names,
exception features, variant types, complex form types, ad-hoc rules, compound rules,
affixes, slots, and templates. Selecting a category that other selected items depend on
is honored; the module never silently drops a dependency.

**Why this priority**: Selective transfer is essential for routine use (most transfers
will not be "everything") but is not required for the very first end-to-end demonstration
that the pipeline works. P2 means it ships in Phase 0 but follows the P1 path.

**Independent Test**: Select only "Affixes" and run the module. Verify that affixes
transfer along with their dependency closure (inflection features, classes, stem names,
exception features) but that unrelated categories such as compound rules or templates are
not transferred unless they were pulled in as dependencies of the selected affixes.

**Acceptance Scenarios**:

1. **Given** the module's main window, **When** the user opens it, **Then** they can
   toggle each grammar piece category on or off before running.
2. **Given** a user has selected only one category, **When** they run the transfer,
   **Then** only items in that category — plus items required as the dependency closure
   of selected items — are transferred, and the statistics panel makes the closure
   inclusions visible per category.

---

### Edge Cases

- **Source and target are the same project**: the module MUST refuse to run and surface
  a clear error before any write occurs.
- **Target is read-only or locked by another process**: the module MUST surface the lock
  condition before any write and abort the run.
- **Source contains objects whose GUIDs already exist in the target**: in Phase 0 the
  source object is still added (duplicates are explicitly permitted); both objects coexist
  and the new one is tagged in Import Residue. (Phase 1 will change this behavior.)
- **Source references a writing system not present in the target**: the dependent items
  are skipped with a clear reason; default-vernacular mapping does not silently create a
  fictitious writing system.
- **Dependency closure for a selected item cannot be fully satisfied**: that item is
  skipped (not partially copied) and reported in the statistics panel.
- **Source project contains objects outside the documented grammar piece categories**:
  those objects are ignored — Phase 0 transfers only the enumerated categories.
- **Transfer is interrupted mid-run** (user closes window, FlexTools crashes): the user
  can identify partially-added items by their Import Residue tag and remove them
  manually; Phase 0 does not guarantee transactional rollback.
- **The same item appears in the source via two dependency paths**: it is transferred
  exactly once.

## Requirements *(mandatory)*

### Functional Requirements

**Module Shape**

- **FR-001**: The deliverable MUST be a FlexTools-compatible module that runs inside a
  standard FlexTools host.
- **FR-002**: The module MUST present a main window inside the FlexTools window with
  controls for: per-category selection toggles, an auto-selection toggle that controls
  whether the dependency closure is implicitly included for selected items, a target
  project picker (see FR-003), a writing-system mapping step (see FR-011), a run
  button, and a post-run statistics panel.
- **FR-003**: The project currently open in the FlexTools host MUST be treated as the
  **source** of the transfer (the project to be scanned most deeply). The **target**
  MUST be selected by the user from a picker that lists the FLEx projects available to
  the host. Roles are not swappable in Phase 0. The module MUST refuse to proceed if
  the picked target resolves to the same project as the source.

**Grammar Piece Categories (Phase 0 scope)**

- **FR-004**: The module MUST support transferring the following categories: writing
  systems check, gram categories (preserving GOLD), inflection features (preserving
  GOLD), custom fields, inflection classes, stem names, exception features, variant
  types (with their associated inflection features), complex form types, ad-hoc rules,
  compound rules, affixes (including their allomorphs and APRs), slots, and templates
  (including which affixes fill which slots).
- **FR-005**: When transferring an affix, the module MUST include all its allomorphs,
  all its APRs, and every referenced inflection feature, inflection class, stem name,
  and exception feature.
- **FR-006**: When transferring a template, the module MUST include the slots it
  references and the affixes filling those slots.
- **FR-007**: Within the affixes category, the user MUST be able to choose which
  individual affixes to transfer (not only the all-or-nothing category toggle). The
  picker MUST be presented as a tree organized **template → slot → affix**, mirroring
  the source project's grammar structure, with an "Unbound" top-level bucket
  containing affixes not yet attached to any template. Selecting a template or slot
  MUST act as a convenience toggle that selects all affixes under it; individual
  affix-level selection MUST remain possible inside any branch.

**Additive Semantics**

- **FR-008**: Phase 0 MUST add new objects unconditionally; existing target objects MUST
  NOT be modified, replaced, or deleted by this module.
- **FR-009**: Duplicates resulting from adding a source object whose GUID or fingerprint
  already exists in the target are explicitly permitted in Phase 0.
- **FR-010**: Every object added by the module MUST be tagged in Import Residue with a
  **structured tag** carrying at minimum: a run ID of the form
  `GT-YYYYMMDD-HHMMSS`, the source project's name, and an ISO-8601 timestamp of the
  run. The tag format MUST allow the user to distinguish, in the target, items from
  one run versus another, and the same tag schema MUST be reusable unchanged by
  Phase 1 (overwrite) and Phase 2 (interactive merge).
- **FR-011**: Before any transfer writes occur, the module MUST present a
  writing-system mapping step in which the user manually maps each source writing
  system (both vernacular and analysis) 1:1 to a writing system in the target. The
  step MUST allow the user to create a new writing system in the target when no
  suitable existing match is available. The module MUST refuse to proceed with the
  transfer until every source writing system actually referenced by selected items is
  mapped to (or created in) the target. Auto-mapping and fuzzy matching are out of
  scope for Phase 0; mapping is explicit and user-driven.

**Identity & Closure**

- **FR-012**: Object identity for matching and for newly added objects MUST be preserved
  by GUID where the LCM permits; where preservation is not permitted, the module MUST
  surface that fact in the statistics panel.
- **FR-013**: For every selected item, the module MUST compute and transfer its full
  dependency closure (per Constitution Principle V). The user MUST be able to toggle the
  auto-inclusion of the closure off in the main window to opt into a bare-bones
  transfer; in that case any selected item whose dependencies cannot be otherwise
  satisfied is skipped and reported.

**Operation Modes**

- **FR-014**: The module MUST support **Preview Mode** as its default mode, listing every
  intended addition (with category, source GUID, dependency-closure pull-ins) without
  writing to the target.
- **FR-015**: The module MUST support **Move Mode**, which performs writes only after the
  user has reviewed a preview from the current session's selection state.
- **FR-016**: Move Mode SHOULD route through the host's standard undo facility wherever
  the underlying API permits, so the user can undo the run from inside FLEx.

**Reporting**

- **FR-017**: At the end of every run (Preview or Move), the module MUST display a
  statistics panel with per-category counts of items added (Preview: "would add") and
  items skipped, plus a list of skipped items with a human-readable reason for each skip.
- **FR-018**: The module MUST NOT silently drop any selected item; every selected item is
  either added (or shown as "would add" in Preview) or appears in the skip list.

**Failure & Safety**

- **FR-019**: If the source and target resolve to the same project, the module MUST abort
  before any write.
- **FR-020**: If the target cannot be written to (locked, read-only, missing permissions),
  the module MUST surface the condition before any write and abort.
- **FR-021**: An item whose dependency closure cannot be fully satisfied MUST be skipped
  in its entirety; partial objects MUST NOT be created in the target.
- **FR-022**: The module MUST NOT modify, rename, or remove GOLD categories or GOLD
  inflection features in the target as a side effect of transfer.

### Key Entities *(include if feature involves data)*

- **Grammar Piece**: A single LCM object eligible for transfer. Each piece belongs to
  exactly one of the supported categories (see FR-004). Each piece has a stable identity
  (GUID), zero or more outgoing references to other pieces (its dependencies), and a
  fingerprint suitable for cross-project matching when GUIDs collide.
- **Grammar Piece Category**: One of the enumerated transferable categories. The user
  selects categories at the main window; selection is a precondition for any piece in
  that category being eligible.
- **Source Project / Target Project**: Two distinct FLEx projects accessible to the
  FlexTools host. The source is read-only from the module's perspective; the target is
  the only project the module writes to.
- **Dependency Closure**: The transitive set of grammar pieces that a selected piece
  references, directly or indirectly, and that must accompany it for the piece to be
  functional in the target.
- **Import Residue Tag**: The structured marker applied to every newly added target
  object. Carries a run ID (`GT-YYYYMMDD-HHMMSS`), the source project's name, and an
  ISO-8601 timestamp, so per-run audit is possible. Same schema is reusable by
  Phase 1 and Phase 2 unchanged.
- **Run Report**: The statistics produced at the end of a run. Per category it contains
  added count, skipped count, and a skip list with reasons.
- **Writing System Mapping**: The user-authored 1:1 correspondence between every source
  writing system (vernacular and analysis) referenced by selected items and a writing
  system in the target. May include target writing systems created on demand during the
  mapping step. Established once per run, before any transfer writes occur.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a documented benchmark toy project containing a small but complete
  grammar (no more than 100 grammar pieces across all categories), a linguist can
  transfer the complete grammar inventory into an empty target project in **one run**
  that completes in under 5 minutes of wall-clock time.
- **SC-002**: After a successful run, 100% of selected source items either appear in the
  target's Import Residue or appear in the skip list with a human-readable reason — no
  selected item disappears silently.
- **SC-003**: For every transferred grammar piece, 100% of its outgoing cross-references
  resolve to objects present in the target (i.e., zero dangling references).
- **SC-004**: Across the benchmark transfer, the target project's existing pre-transfer
  objects show **zero modifications** when compared against a pre-run snapshot.
- **SC-005**: A user new to the module can complete their first successful transfer (from
  opening the module to seeing the statistics panel) in **under 10 minutes**, including
  reading the in-module help.
- **SC-006**: When run in Preview Mode, the module produces a complete preview without
  any change to the target — verified by snapshot comparison of the target before and
  after — for **100%** of Preview runs.
- **SC-007**: Of users who previously rebuilt grammar by hand from a toy project, **at
  least 80%** report that the Phase 0 module saved them meaningful time when surveyed
  after their first real use.

## Assumptions

- **Phase scope**: This spec covers Phase 0 only (additive, no merge UI, no conflict
  resolution). Phase 1 (overwrite with GUID/fingerprint matching) and Phase 2
  (interactive merging) are deferred to subsequent specs per constitution Principle IV.
- **Host environment**: The user is running a standard FlexTools installation; both
  source and target FLEx projects are accessible to that host. Both projects MUST be
  open in the same FLEx instance, running against the same FLEx / LCM / flexlibs
  versions — same-version compatibility between source and target is a precondition
  guaranteed by the host environment, not something the module verifies at runtime.
- **API surface (informational)**: Implementation is permitted to use either of the two
  co-equal flavors declared in constitution Principle II (flexlibs1 and LibLCM), and
  must not depend on flexlibs2. This is reiterated here as scope context; the choice of
  which flavor implements which operation is a planning concern, not a spec concern.
- **Preview default**: Preview Mode is the default execution mode (Constitution
  Principle III). Move Mode is opt-in per run.
- **Undo expectations**: Move Mode aims to be undoable via the FLEx undo stack where the
  underlying API permits; full transactional rollback across the whole run is **not**
  guaranteed in Phase 0.
- **GOLD inviolability**: GOLD gram categories and GOLD inflection features are never
  altered by this module; references to them are preserved as-is.
- **Writing-system mapping is explicit and user-driven**: Per FR-011 the user manually
  maps every source writing system (vernacular and analysis) 1:1 to a target writing
  system before transfer, and may create new target writing systems on demand from the
  mapping step. Auto-mapping, fuzzy matching, and any SFM-style mapping wizard remain
  out of scope for Phase 0 (the SFM-style wizard is a Phase 2 candidate).
- **Out of scope for Phase 0**: lexicon entries themselves, semantic domains, examples,
  texts, dictionary configuration, and anything not enumerated in FR-004. The module
  transfers *grammar* pieces only.
- **Author-side tooling**: The FLExToolsMCP may be used to scaffold and generate the
  implementation but is not a runtime dependency, per constitution Principle II.

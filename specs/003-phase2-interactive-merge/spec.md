# Feature Specification: Phase 2 — Interactive Merge

**Feature Branch**: `003-phase2-interactive-merge`

**Created**: 2026-06-20

**Status**: Draft

**Input**: User description: Phase 2 builds on Phase 0 (additive) + Phase 1 (overwrite, commits e129b72..f4cdd9c, FR-101..110). It adds interactive per-conflict merge, an SFM-style writing-system mapping wizard, and a conflict-resolution audit trail persisted into the existing residue tag.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Per-Conflict Merge Prompt (Priority: P1)

A linguist runs a transfer with overwrite enabled. The source project's verb entry "ko" has a non-empty Comment field ("revised gloss, 2026-05-10"). The target's same verb entry already has a different non-empty Comment ("old form, do not delete"). The system pauses before applying that field's overwrite and shows the linguist a side-by-side view of both values, with explicit choices: take source ("right"), keep target ("left"), merge by concatenating both, skip this field for now, or open a free-text editor for a custom value. The linguist's choice is applied immediately to that one field; the rest of the entry continues to overwrite per Phase 1 default behavior unless other conflicts arise.

**Why this priority**: This is the primary value of Phase 2. Without it, Phase 1's "source wins" policy silently destroys target-side annotations the linguist has accumulated over weeks of work — the very scenario described in the original problem statement ("They have built up phonology, morphology, custom fields, affixes, slots"). P1 because Phase 1 is currently dangerous in production without it.

**Independent Test**: Set up a target project with a verb entry whose Comment differs from the source's. Run overwrite with interactive mode enabled. Verify (a) the prompt appears with both values shown, (b) each of the five choices produces the documented outcome, (c) the run report records which choice was made.

**Acceptance Scenarios**:

1. **Given** source.Comment="A" and target.Comment="B" on the same entry, **When** the user selects "take source", **Then** target.Comment="A" after the run and the run report logs the choice for that entry/field.
2. **Given** the same conflict, **When** the user selects "keep target", **Then** target.Comment="B" (unchanged) and the entry's other syncable fields still overwrite per Phase 1 default.
3. **Given** the same conflict, **When** the user selects "merge", **Then** target.Comment combines both values in a system-defined deterministic way (concatenation with a separator line) and the result is recorded.
4. **Given** the same conflict, **When** the user selects "skip", **Then** target.Comment is unchanged AND a Skip entry of reason="interactive_skip" appears in the run report for that field.
5. **Given** the same conflict, **When** the user selects "edit" and types a custom value, **Then** target.Comment equals the typed value and the run report records both the prompt and the custom value.

---

### User Story 2 - Writing-System Mapping Wizard (Priority: P1)

A linguist starts a transfer from a source project that has a vernacular writing system "ko-x-Latn" (transliteration). The target project does not have "ko-x-Latn" — it has "ko-Hang" (a different vernacular). Before any transfer plan is built, a wizard step lists every source writing system not exact-matched in the target. For each, the linguist picks: map source→target (drop-down of existing target WS handles), create a new target WS with the source's tag, or skip — any transferred object referencing this WS will be skipped with reason "unmapped_ws_user_chose_skip" instead of failing silently. The chosen mapping is reused for every subsequent reference to that source WS within the run.

**Why this priority**: Without this, Phase 0's silent unmapped_ws skips destroy lexicon entries that reference newly-introduced writing systems — invisible data loss. The SFM importer in FieldWorks already has this pattern; users expect it. P1 because cross-project transfers between genetically-related-but-divergent dialects routinely involve mismatched WS tags.

**Independent Test**: Open a source whose vernacular WS tag differs from the target's. Launch the transfer wizard. Verify (a) the WS wizard appears before the category-picker, (b) for each mismatched source WS a row is presented with the three options, (c) the user's choices populate WSMapping and the subsequent transfer respects them.

**Acceptance Scenarios**:

1. **Given** source has WS "ko-x-Latn" not present in target, **When** the wizard opens, **Then** a row shows "ko-x-Latn" with options to map, create, or skip.
2. **Given** the user picks "map → ko-Hang", **When** the transfer runs, **Then** all source LexemeForm.ko-x-Latn values are written into target's ko-Hang slot.
3. **Given** the user picks "create new", **When** the transfer runs, **Then** a new "ko-x-Latn" WS is added to the target project before any object referencing it is created.
4. **Given** the user picks "skip", **When** the transfer runs, **Then** objects whose only form is in "ko-x-Latn" are emitted as Skip(unmapped_ws_user_chose_skip) and counted in the run report.

---

### User Story 3 - Re-Run With Prior Decision Recall (Priority: P2)

A linguist re-runs the same source→target transfer a week after their first interactive session. The system reads the residue tags written during the prior run, recovers the per-field decisions, and pre-fills the prompt with "use last time's choice — was: TAKE_SOURCE". The linguist can accept the recall (single keystroke), override it field-by-field, or override all-at-once.

**Why this priority**: Avoids forcing the linguist to re-decide every conflict on every run, which is the difference between Phase 2 being usable on a 5,000-entry lexicon and not. P2 because US1 is functional without it — but adoption depends on it.

**Independent Test**: Run the transfer once with interactive choices recorded, then run again with no source-side changes. Verify (a) every conflict is pre-filled with the prior choice, (b) accepting all yields a no-op run, (c) overriding one field changes only that field.

**Acceptance Scenarios**:

1. **Given** a prior run resolved entry-X's Comment as "take source", **When** the same conflict arises in a re-run, **Then** the prompt's default selection is "take source" with annotation "from run GT-YYYYMMDD-HHMMSS".
2. **Given** the linguist accepts every pre-filled choice, **When** the re-run completes, **Then** the run report shows 0 user-changed fields and the residue tag's run_id is updated but the resolution payload is unchanged.

---

### User Story 4 - Batched Resolution Within One Move (Priority: P3)

The linguist works through 30 conflicts during a single transfer. They make all choices before any database mutation occurs. If they change their mind on a previously-answered prompt, they can navigate back without losing prior answers. Only after they confirm "apply all" does the transfer execute the resolutions in one batch.

**Why this priority**: Improves UX but doesn't change the data-correctness contract. P3 because US1+US3 deliver value at "one prompt per conflict, applied immediately"; batching is a polish step.

**Independent Test**: Trigger a run with 5+ conflicts. Verify the wizard collects all answers before any write; navigate back-and-forward; confirm a single "apply all" commit-point.

**Acceptance Scenarios**:

1. **Given** 5 conflicts in the plan, **When** the linguist answers 3 then navigates "back", **Then** the prior answers are preserved and editable.
2. **Given** all 5 are answered, **When** the linguist clicks "apply all", **Then** all 5 resolutions execute inside the existing UndoableUnitOfWork (Ctrl+Z still undoes the whole transfer).

---

### Edge Cases

- What happens when **the source and target have IDENTICAL non-empty values for a field**? No conflict — no prompt — Phase 1 default (skip or no-op write) applies. The deduplication helper from FR-107 handles this for custom fields.
- What happens when **the source value is non-empty but the target value is empty**? Phase 1 default applies (write source). No prompt — there is nothing to lose.
- What happens when **the field is a multistring with conflicts in some writing systems but not others**? Phase 2 treats the whole multistring as one field (per Out-of-Scope: "Three-way merge of multistring text fields per writing system" is deferred). The prompt shows the multistring's best-analysis text; the user's choice replaces the entire multistring.
- What happens when **the user cancels mid-wizard (closes the dialog)**? The transfer aborts; no writes occur; no residue tags are updated.
- What happens when **a prior-run residue tag is corrupted or unparseable**? US3 falls back to US1 behavior (no pre-fill) for that field; a warning is logged but the run continues.
- What happens when **the user selects "create new WS" for a tag that conflicts with a target-side WS the user forgot about**? The wizard validates against the target's full WS list at confirm time and re-prompts with the conflict surfaced.
- What happens when **the WS wizard's source has 50+ unmapped writing systems**? Wizard remains usable but the spec does not mandate a specific UI density; assumes paginated or virtualized list (implementation detail, not user-facing).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-201**: System MUST detect per-field conflicts (source and target both carry non-empty content on the same field of an overwrite-candidate object) and pause the transfer to prompt the user.
- **FR-202**: The conflict prompt MUST present at minimum these five resolutions: take-source, keep-target, merge, skip, edit-custom.
- **FR-203**: When the user picks "merge", the system MUST produce a deterministic combination of the two values such that re-running with the same inputs yields the same merged result.
- **FR-204**: When the user picks "skip", the affected field MUST NOT be written, and a Skip(reason="interactive_skip") MUST appear in the run report associated with the specific entry+field.
- **FR-205**: When the user picks "edit-custom", the system MUST accept any free-text value the user types and write it without further validation beyond what the underlying field permits (e.g., a multistring requires text; a count requires an integer).
- **FR-206**: The user's choice for every prompted conflict MUST be persisted into the existing residue tag, in a new segment alongside the FR-106 snapshot. The segment format MUST be parseable by ImportResidueTag.parse() and round-trippable.
- **FR-207**: A re-run of the same source→target transfer MUST detect prior decisions from the residue tag and pre-fill each conflict prompt with the prior choice plus the prior run's run_id as the "last decided at" annotation.
- **FR-208**: When the user accepts a pre-filled prior decision, the run report MUST record the field as "carried-over" (not as a new interactive choice). This distinguishes truly-interactive runs from re-runs.
- **FR-209**: System MUST detect writing-system mismatches between source and target at transfer-plan time, before any category selection, and present a wizard listing every mismatched source WS with three resolution options: map to existing target WS, create new target WS preserving the source tag, or skip transfers referencing this WS.
- **FR-210**: The WS wizard's output MUST populate the existing WSMapping entity such that downstream Phase 0 / Phase 1 code paths see a complete mapping with no silent skips on user-touched WSes.
- **FR-211**: Selecting "skip" in the WS wizard for a source WS MUST cause any object whose only writing-system-keyed content lives in that WS to emit a Skip(reason="unmapped_ws_user_chose_skip") instead of failing silently.
- **FR-212**: Selecting "create new" in the WS wizard MUST create the new writing system in the target project BEFORE any transferred object referencing it is created. Mid-transfer WS creation is not permitted.
- **FR-213**: Cancelling the wizard or any conflict prompt MUST abort the entire transfer with zero database mutations. No partial state may be left in the target.
- **FR-214**: All Phase 2 interactive choices MUST execute within the same UndoableUnitOfWork that wraps the Phase 0 / Phase 1 transfer, so a single Ctrl+Z undoes the entire interactive transfer including all merge resolutions.
- **FR-215**: When prior-run residue tags are corrupted, unparseable, or absent for a given field, the system MUST fall back to the FR-201 fresh-prompt behavior for that field and emit a warning to the run report.
- **FR-216**: System MUST NOT prompt for conflicts on identical-valued fields (FR-107 dedupe already handles custom fields; FR-216 extends this to all syncable properties when source and target values are structurally equal).
- **FR-217**: System MUST NOT prompt when only one side has a non-empty value (Phase 1 source-wins or target-preserved applies automatically).

### Key Entities *(include if feature involves data)*

- **ConflictPrompt**: Represents one pending per-field conflict. Attributes: target_object_guid, field_name, left_value (target's pre-overwrite), right_value (source's value), prior_decision (optional, from residue), user_decision (one of the five resolutions), user_custom_value (only set when resolution is edit-custom).
- **MergeDecisionLog**: Ordered list of ConflictPrompts for one run. Persisted into the residue tag of every object that had at least one prompted field. Round-trippable via ImportResidueTag.parse() / serialize().
- **WSMappingChoice**: Extends the existing WSMappingEntry with an explicit user_choice field: one of {map, create, skip}. The choice was made interactively; silent-mapping is no longer permitted.
- **InteractiveSession**: Wraps a single transfer's user-decision context. Holds the MergeDecisionLog being built, references to prior-run decisions if any, and the user's wizard state (current page, navigation history for US4).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-201**: A linguist resolving a 50-conflict transfer on a 5,000-entry lexicon completes the wizard in under 15 minutes when accepting prior-run defaults (US3 recall path).
- **SC-202**: Zero target-side annotations (Comment, custom fields, LiftResidue, Description) are silently lost in any overwrite-mode transfer. Every potentially-overwritten value either survives or has an explicit user-chosen replacement recorded in the residue tag.
- **SC-203**: 100% of writing-system mismatches surface in the wizard before any database mutation. Silent unmapped_ws skips drop to zero in user-facing runs.
- **SC-204**: Re-running an identical source→target pair after a prior interactive session produces zero new prompts when the user accepts all pre-filled choices. The recall path is a no-op confirmation, not a re-decision exercise.
- **SC-205**: A linguist can audit any prior run by reading the residue tag on any touched object and reconstructing which fields were prompted, what choices were offered, and what the user chose — without opening either project file or rerunning anything.
- **SC-206**: User cancellation at any point (wizard or conflict prompt) leaves the target project bit-identical to its pre-transfer state, verified by file-hash comparison.
- **SC-207**: 90% of linguists in user testing complete the per-conflict prompt without consulting documentation, indicating the five-resolution model is self-explanatory.

## Assumptions

- The FlexTools host process is a desktop application with synchronous UI capability (PyQt is already in use per Phase 1's Lib/ui/). Browser-based or headless invocations of the transfer engine are out of scope; non-interactive callers will fall back to Phase 1's FR-109 "source wins" default.
- The existing UndoableUnitOfWork wrapper from research.md R10 covers the entire transfer including any interactive prompts the user spends arbitrary time answering. Long-running open transactions are acceptable.
- The residue tag's existing `snap=<base64>` segment can be extended with a sibling segment (e.g. `merge=<base64>`) without breaking parsers written for the Phase 1 four-segment form. Phase 1's parse() already tolerates 4-or-5-segment input; Phase 2 widens to 4-or-5-or-6.
- "Merge" semantics for arbitrary fields is concatenation-with-separator. Multistring fields concatenate per-writing-system inside the same TsString. The deterministic merge result is acceptable as a starting point; future phases may refine with field-type-aware merge strategies.
- The user is operating on a single source-target pair at a time. Multi-target broadcast transfers are out of scope.
- Constitution v5.0.0 Principle IV requires Phase 2 to be additive over Phase 1 — no Phase-1-only code path may be removed; the interactive layer wraps but does not replace the existing executor.
- The PyQt widget toolkit used in Lib/ui/ from Phase 1 is sufficient. No new UI dependencies are introduced.
- Custom fields, syncable properties, multistrings, and Description fields are all conflict-prompt-eligible. Slot membership (SlotsRC), PhoneEnvRC, and other reference collections are NOT conflict-prompt-eligible in Phase 2 — they continue to use Phase 1 source-wins.

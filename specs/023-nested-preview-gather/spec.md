# Feature Specification: Nested Preview Field Gathering

**Feature Branch**: `023-nested-preview-gather`

**Created**: 2026-07-05

**Status**: Draft

**Input**: User description: "Expand the merge preview pane's field gathering to a full nested view for entry-category items (affixes and stems). Today the gather returns a flat field/value map built only from entry-level scalar properties plus custom fields; an affix preview shows essentially only the Lexeme Form even though FLEx shows a rich nested structure (Morph Type, Sense Gloss/Definition/Grammatical Info, multiple Allomorphs with forms/morph-types/environments/comments, MSA Slots and category info) — all of which Move actually transfers. The preview must faithfully represent what Move transfers. Also fix a bug where multi-string custom fields are silently dropped, and ensure all string values render as text."

## Clarifications

### Session 2026-07-05

- Q: When previewing an entry that exists in the target (overwrite/merge), how should per-field NEW / IN TARGET / SIMILAR status apply to child content when source and target have different numbers of senses/allomorphs? → A: Match children between source and target by **visual fingerprint** (form/content), then compute per-field status on matched pairs; unmatched source children are all-NEW; unmatched target children are shown as target-only.
- Q: How deep should the sense's Grammatical Info (MSA) be represented? → A: Show the FLEx-style **label plus slots/category** (e.g. `n:NC`, slot `NC`, category info); full MSA breakdown (inflection features, from/to POS) is out of scope.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See an affix's real content in the preview (Priority: P1)

A linguist selects an affix (e.g. the noun-class prefix `n-`) in the affix transfer wizard.
The preview pane must show a representation of everything that will be transferred for that
affix — not just its Lexeme Form. In FLEx this same affix shows a Morph Type, a Sense with a
Gloss and Grammatical Info (its part-of-speech / MSA), and one or more Allomorphs each with
their own form, morph type, environments, and comment. Because Move copies all of these to the
target, the preview must display all of the non-empty ones so the linguist can verify what the
transfer will do before committing.

**Why this priority**: This is the core defect being reported. Without it the preview is
misleading — it appears the affix carries almost no data, when in fact it carries a full
grammatical structure that Move will transfer. Under Principle III (Preview-Before-Mutate),
a preview that under-represents what Move does defeats the entire review step.

**Independent Test**: Select an affix with a populated sense (gloss + grammatical info) and two
allomorphs. Confirm the pane displays the sense gloss, the grammatical info, and both allomorphs
with their distinct forms and comments — matching what FLEx shows for that entry.

**Acceptance Scenarios**:

1. **Given** an affix whose sense has gloss `1.n` and grammatical info `n:NC`, **When** the
   linguist selects it, **Then** the preview shows the gloss and the grammatical info as
   readable text (not blank, not an object identifier).
2. **Given** an affix with two allomorphs (`m` with comment "before b, p, f, w?" and another),
   **When** the linguist selects it, **Then** the preview shows both allomorphs as distinct
   entries, each with its own form and comment — neither is collapsed or dropped.
3. **Given** an affix whose entry-level fields are all empty except the Lexeme Form, **When**
   the linguist selects it, **Then** the preview still shows the non-empty child content (sense,
   allomorphs, morph type) rather than only the Lexeme Form.

---

### User Story 2 - Multi-string custom fields are never silently lost (Priority: P2)

A linguist selects an entry that has a populated multi-string custom field (e.g. a "Plural"
field). Today that field silently disappears from the preview because reading it fails. The
linguist must instead see the field's value, or — if it genuinely cannot be read — a visible
notice, never a silent omission.

**Why this priority**: Silent data loss in a review tool is dangerous: the linguist may approve a
transfer believing a field is empty when it is not. Principle I forbids silently dropping content
that the transfer carries.

**Independent Test**: Select an entry with a populated multi-string custom field. Confirm the
value appears in the preview (or a visible "could not read" notice appears), and that it is never
simply missing without explanation.

**Acceptance Scenarios**:

1. **Given** an entry with a populated multi-string custom field, **When** the linguist selects
   it, **Then** the field's text value appears in the preview.
2. **Given** an entry whose multi-string custom field is empty, **When** the linguist selects it,
   **Then** the field is omitted (empty-suppression) — consistent with all other empty fields.

---

### User Story 3 - Stems and other entry-category items benefit identically (Priority: P3)

The same nested gathering applies to stems (also entry-category items), so a linguist previewing
a stem sees its senses, allomorphs, and grammatical info with the same fidelity as an affix.

**Why this priority**: The gather is shared across all entry-category previews. Scoping the fix to
affixes only would leave stems under-represented and create an inconsistent experience.

**Independent Test**: Select a stem with multiple senses. Confirm each sense's gloss and
grammatical info appear as distinct, ordered entries.

**Acceptance Scenarios**:

1. **Given** a stem with two senses, **When** the linguist selects it, **Then** both senses'
   glosses appear as distinct entries in source order.

---

### Edge Cases

- **Multiple children of the same kind**: an entry with N senses or N allomorphs must show all N,
  each distinguishable and in source order — not just the first.
- **Empty child**: a sense or allomorph with no non-empty fields contributes nothing (suppressed),
  rather than an empty labeled group.
- **Unreadable field**: if a single field cannot be read (e.g. an API defect on a field type), the
  failure is contained to that field, a visible notice is produced, and the rest of the entry still
  renders.
- **Deeply empty entry**: an entry where only the Lexeme Form is non-empty shows just the Lexeme
  Form — no fabricated or placeholder rows.
- **Comparison against a target**: when previewing an affix that already exists in the target
  (overwrite/merge), the per-field NEW / IN TARGET / SIMILAR status must remain meaningful for the
  newly added nested fields, not just entry-level fields.
- **Child count mismatch**: source has more (or fewer) senses/allomorphs than the target. Children
  are paired by visual fingerprint; unmatched source children render all-NEW, unmatched target
  children render as target-only. No pairing is forced between non-matching children.
- **Ambiguous fingerprint match**: two source children share a fingerprint, or a source child could
  match multiple target children. The pairing must be deterministic (e.g. first-unused wins in source
  order) so the preview is stable across runs.
- **Grammatical info / MSA with no readable label**: shows a best-effort label or is suppressed,
  never an object identifier.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The preview MUST gather and display non-empty **standard** fields from an entry's
  child objects (senses, allomorphs, and the grammatical info / MSA), not only the entry's own
  scalar fields and not only custom fields.
- **FR-002**: For each **sense**, the preview MUST include (when non-empty): gloss, definition, and
  grammatical info (the sense's part-of-speech / MSA label as shown in FLEx, e.g. `n:NC`). The
  grammatical-info representation is **label + slots/category** (see FR-004); the deeper MSA
  breakdown (inflection features, from/to POS) is out of scope.
- **FR-003**: For the entry and each **allomorph** (the lexeme-form allomorph and every alternate
  form), the preview MUST include (when non-empty): the allomorph form, its morph type, its
  environments, and its comment.
- **FR-004**: The preview MUST include the entry's **morph type** and the grammatical info's
  **slot / category** information when non-empty.
- **FR-005**: When an entry has **multiple** children of the same kind (e.g. two allomorphs, three
  senses), the preview MUST represent each child **distinctly and in source order** — it MUST NOT
  collapse them or keep only the first.
- **FR-006**: All string-valued fields (single- and multi-writing-system) MUST render as **human-
  readable text**, never as an internal object identifier.
- **FR-007**: Multi-string custom fields MUST be readable; when the primary read path fails, the
  system MUST fall back to an alternate read so the value is not silently lost. If no read
  succeeds, a **visible notice** MUST be produced for that field.
- **FR-008**: Empty fields (single-string empty, multi-string all-empty, empty child objects) MUST
  continue to be **suppressed** so the preview shows only non-empty content.
- **FR-009**: System/bookkeeping fields already excluded from the preview (identity handles,
  timestamps, homograph number, publishing flags, import residue) MUST remain excluded for the new
  nested fields as well.
- **FR-010**: The nested gathering MUST apply uniformly to all **entry-category** previews (affixes
  and stems), producing consistent structure across both.
- **FR-011**: The preview's existing **diff/compare** behavior (per-field NEW / IN TARGET / SIMILAR
  status when a target match exists) MUST extend to nested fields. Source and target children of the
  same kind MUST be paired by **visual fingerprint** (their form/content), and per-field status MUST
  be computed on each matched pair. A source child with no fingerprint match in the target MUST be
  shown with all its fields as NEW; a target child with no source match MUST be shown as target-only.
  Child pairing MUST NOT rely on child GUID identity (child GUIDs are not stable across projects).
- **FR-012**: A single unreadable or malformed field or child MUST NOT abort the whole preview; the
  failure MUST be contained and the remainder of the entry MUST still render (graceful degradation).
- **FR-013**: The preview MUST NOT retain live database objects after gathering; the gathered
  representation MUST be plain, cacheable data consistent with the existing preview cache contract.
- **FR-014**: The set and ordering of displayed fields MUST reflect what Move actually transfers for
  the entry, so the linguist can trust the preview as an accurate pre-commit summary (Principle III).

### Key Entities *(include if feature involves data)*

- **Entry preview representation**: the gathered, display-ready summary of one entry-category item.
  Comprises the entry's own non-empty fields plus an ordered set of child groups.
- **Child group**: a labeled, ordered collection representing one sense or one allomorph (or the
  grammatical info), each carrying its own non-empty fields. Multiple groups of the same kind are
  distinguished by source order (e.g. Sense 1, Sense 2; Allomorph 1, Allomorph 2). For
  target-comparison previews, each source child group carries a **fingerprint** used to pair it with
  a target child group of the same kind.
- **Field entry**: a single label/value pair within the entry or a child group, where the value is
  always readable text (or a structured multi-writing-system text set), and empties are suppressed.
- **Read-failure notice**: a visible marker attached to a specific field that could not be read,
  distinguishing "could not read" from "empty."

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For an affix whose FLEx record shows a sense, grammatical info, morph type, and two
  allomorphs, the preview displays **100% of those non-empty fields** (previously it showed only the
  Lexeme Form).
- **SC-002**: When an entry has multiple senses or allomorphs, **every one** appears in the preview
  in source order — 0 collapsed or dropped children.
- **SC-003**: **Zero** string fields render as an internal object identifier across a full sweep of a
  representative project's affixes and stems.
- **SC-004**: **Zero** populated multi-string custom fields are silently omitted; each is either
  shown with its value or accompanied by a visible read-failure notice.
- **SC-005**: A malformed or unreadable field never blanks the whole pane — the entry still renders
  its other fields in **100%** of induced single-field-failure cases.
- **SC-006**: The set of fields shown in the preview matches the set of fields Move writes for the
  same entry (spot-checked against a Preview/Move pair) — no field shown that Move does not transfer,
  and no field Move transfers that is non-empty and omitted.

## Assumptions

- **Nesting representation**: multiple children are represented with an explicit ordering/index
  (e.g. "Sense 1", "Allomorph 1", "Allomorph 2") derived from source order. The exact on-screen
  grouping/labeling and the underlying data shape (flat-with-index vs. structured groups) is an
  implementation decision deferred to planning, but the requirement is that children are distinct and
  ordered. This resolves the current "first sense wins on collision" limitation.
- **Field selection is driven by what Move transfers**, cross-referenced with what FLEx displays for
  the entry. Fields that Move does not carry are out of scope for the preview even if FLEx shows them.
- **Grammatical info label** uses the same abbreviation FLEx shows (e.g. `n:NC`); when no readable
  label exists, the field is suppressed rather than shown as an identifier.
- **Writing-system-aware values** continue to use the existing per-writing-system text representation
  already used for standard multi-string fields.
- **A prior fix** already normalizes custom-field single-strings to text; this feature extends the same
  normalization to child standard fields and to the multi-string custom-field read path.
- **Diff/compare scope**: field-level status (NEW / IN TARGET / SIMILAR) extends to nested fields. The
  top-level item's overall match identity (by GUID then fingerprint) is unchanged, but **child**
  groups are paired by visual fingerprint only — not by child GUID — because child object GUIDs are
  not stable across the source/target project pair.
- **Test projects**: Ejagham Full GT-Test (and its Mini pair) provide affixes with senses, MSAs,
  multiple allomorphs, and multi-string custom fields suitable for validation.

## Out of Scope

- Editing any of the newly displayed fields from the preview pane (the pane remains read-only).
- Changing what Move transfers; this feature only changes what Preview **displays** to match Move.
- Preview gathering for non-entry categories beyond confirming they are unaffected (e.g. POS,
  phonological rules) — their existing gather paths are not part of this expansion.
- Reordering or restructuring the diff pane's visual layout beyond what is needed to show ordered
  child groups.
- Deep MSA/grammatical-info breakdown beyond label + slots/category — inflection features and
  from/to POS detail are not shown in the preview (see FR-002).

## Dependencies

- The underlying transfer defines the authoritative set of fields Move carries for an entry; the
  preview's field selection is derived from and must stay consistent with it.
- The custom-field read defect originates in the underlying library; this feature adds a
  containment/fallback around it rather than fixing the library.

# Feature Specification: Stems Item Picker (Model-A) — Un-stub the Disabled Pane

**Feature Branch**: `019-stems-item-picker`

**Created**: 2026-07-05

**Status**: Draft

**Input**: User description: "Stems item picker (#23, un-stub the disabled pane). No spec.
Roadmap build-sequence step 4."

## Context

The transfer wizard's **Item picker** page (page 2) hosts a tabbed picker: an **Affixes** tab
(active) and a **Stems** tab that currently ships **stubbed and disabled** —
[selection_wizard.py:625-689](../../src/gramtrans/Lib/ui/selection_wizard.py) renders it with
the placeholder "[STUBBED] Stem transfer is not yet available … (Layer-3 stems)". This feature
un-stubs that pane so the user can pick **stem-morphtype lexical entries** (roadmap #23) the
same way they pick affixes.

Stems are a **Model-A (item-derived)** selection, not a Model-B block: the user picks stem
`LexEntry` objects and the grammatical schema those entries depend on (parts of speech,
inflection classes, stem names, inflection features, exception features) is computed,
preselected, and shown on the downstream Skeleton and Grammatical-deps pages — exactly as it
already works for affixes. Per
[../wizard-selection-roadmap.md](../wizard-selection-roadmap.md) #23, stems anchor on
`LexDbOA.Entries`, partitioned from affixes by morphtype: an entry is a stem when its
`LexemeFormOA.MorphTypeRA` is **not** an affix type (`IsAffixType == false` — stem, root, bound
root, particle, etc.). Affixes take the complementary partition (`IsAffixType == true`), which
the Affixes tab already owns.

The **engine** side of the LexEntry item pickers is mid-refactor (Phase 3c): in
[Lib/categories.py](../../src/gramtrans/Lib/categories.py) the `affixes_*` callbacks are
`NotImplementedError` stubs ("Phase 3c T013/T015/T019"). Stems reuse the **same LexEntry
closure engine** as affixes — the owned-child closure (senses, MSAs, allomorphs, examples,
pronunciations, etymologies, entry-refs) and the grammatical-dependency wiring are identical;
only the morphtype partition differs. This feature therefore depends on the shared LexEntry
picker engine and adds the stem partition + un-stubs the UI pane; it does not invent a parallel
engine.

Consistent with the affix picker and 009/010: no conflict-mode UI this phase (Layer-1 category
defaults apply automatically); the NEW / IN TARGET / SIMILAR target-status column carries
collision information; nothing on the pane writes to the target (the only write remains at
Move); GOLD inviolability and GUID-first identity hold (Constitution I).

## Clarifications

### Session 2026-07-05

- Q: How is an entry with a missing lexeme form or null morphtype classified? → A: **Default to
  stem/root** — such entries fall into the Stems tab (never silently dropped from both, never a
  crash). An entry is an affix only when `LexemeFormOA.MorphTypeRA.IsAffixType` is explicitly
  true; everything else (including null/ambiguous morphtype) is treated as a stem. This firms up
  the drafted leaning — it is no longer deferred to `research.md`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pick stem entries from an enabled Stems tab (Priority: P1)

The Stems tab is enabled and lists the source's stem-morphtype lexical entries; the user
checks the stems they want to transfer, just like the Affixes tab.

**Why this priority**: Enabling the pane and letting the user select stems is the whole feature
and the MVP; nothing else is meaningful until stems can be picked.

**Independent Test**: Bind a source with both affix and stem entries; open the Item picker;
confirm the Stems tab is enabled (no "[STUBBED]" placeholder), lists exactly the stem-morphtype
entries (not the affixes), and check state can be toggled per entry.

**Acceptance Scenarios**:

1. **Given** a bound source, **When** the Item picker opens, **Then** the Stems tab is enabled
   and shows the stem-morphtype entries; the Affixes tab still shows only affix-morphtype
   entries (no overlap, no double-listing).
2. **Given** the Stems tab, **When** the user checks a stem entry, **Then** that stem is
   recorded in the selection; unchecking removes it.
3. **Given** a source with zero stem entries, **When** the tab opens, **Then** it shows an
   empty list (not the stub placeholder, not an error) and the wizard still advances.

---

### User Story 2 - Picked stems drive grammatical-dependency closure (Priority: P1)

When stems are picked, the parts of speech, inflection classes, stem names, inflection
features, and exception features those stems depend on are computed and preselected on the
downstream Skeleton / Grammatical-deps pages, and transferred with the stems.

**Why this priority**: Model-A value comes from item-derived closure; a stem transferred without
its POS/MSA is broken. This makes the pick actually produce a correct transfer.

**Independent Test**: Pick a stem whose sense MSA references POS P (not otherwise selected);
confirm P is preselected on the Skeleton page and appears in the plan; deselect the stem and
confirm P is no longer pulled on the stem's account.

**Acceptance Scenarios**:

1. **Given** a picked stem entry referencing POS P and inflection class C, **When** the plan is
   computed, **Then** P and C are included (preselected on Skeleton/Grammatical deps) as
   derived dependencies.
2. **Given** the stem's owned children (senses, allomorphs, examples, etc.), **When** the plan
   is computed, **Then** the owned-child closure travels with the stem (same closure rules as
   affixes).
3. **Given** a stem deselected, **When** the plan is recomputed, **Then** dependencies pulled
   solely on that stem's account are dropped (unless another kept item needs them).

---

### User Story 3 - Know what already exists in the target (Priority: P2)

Every stem row shows whether it is NEW, IN TARGET, or SIMILAR against the early-bound target.

**Why this priority**: Reuses the affix picker's target-status logic; informs decisions but does
not gate them (conflict handling is deferred).

**Independent Test**: Bind source=target; confirm every stem row reads IN TARGET. Bind a fresh
target; confirm rows read NEW.

**Acceptance Scenarios**:

1. **Given** a bound target, **When** the Stems tab renders, **Then** each stem row shows
   NEW / IN TARGET / SIMILAR against that target, using the affix picker's logic.
2. **Given** no target bound, **When** the tab renders, **Then** the target-status column is
   blank and the tab does not crash.

---

### User Story 4 - Deselecting a needed dependency is reported, not silent (Priority: P1)

If the user keeps a stem but deselects a grammatical dependency it needs (e.g. its POS) on a
downstream page, and the target lacks it, the transfer is not silently broken — the user is
warned once, in aggregate, and must confirm at Move.

**Why this priority**: Referential Completeness (Constitution V) is non-negotiable and applies
identically to stems and affixes.

**Independent Test**: Keep a stem whose POS is deselected on Skeleton against a target lacking
that POS; confirm Preview shows one aggregated warning naming the stem and Move requires a
single consolidated confirmation.

**Acceptance Scenarios**:

1. **Given** a kept stem needing POS P, **When** P is deselected and absent from target,
   **Then** Preview shows an entry-centric warning naming the stem and Move pops one
   consolidated confirmation.
2. **Given** several such omissions, **When** the user reaches Move, **Then** they see a SINGLE
   dialog, not one prompt per stranded dependency.

---

### Edge Cases

- **Source with no stem entries**: the tab shows an empty list (not the stub, not an error);
  the wizard advances; no stem actions planned.
- **Entry whose morphtype is ambiguous or null** (`LexemeFormOA` or `MorphTypeRA` missing):
  classified by an explicit, documented rule (see Assumptions) rather than crashing; not
  silently dropped from both tabs.
- **Entry with multiple allomorphs of differing morphtypes**: partition follows the lexeme
  form's morphtype (`LexemeFormOA.MorphTypeRA`), consistent with the affix partition, so an
  entry appears in exactly one tab.
- **Stem already in target (IN TARGET)**: shown with IN TARGET status; Layer-1 default governs
  add/skip (no conflict UI this phase).
- **Same POS needed by both a picked affix and a picked stem**: the dependency is pulled once
  (deduplicated by GUID), not double-counted.
- **No target bound**: target-status blank; missing-reference checks degrade gracefully (treat
  target as lacking the reference — safe default), no crash.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Item picker's Stems tab MUST be enabled (the "[STUBBED]/disabled" placeholder
  at selection_wizard.py:625-689 removed) and MUST list the source's stem-morphtype lexical
  entries.
- **FR-002**: Stem/affix partition MUST be by `LexEntry.LexemeFormOA.MorphTypeRA.IsAffixType`:
  an entry is an **affix** only when `IsAffixType` is explicitly true; **all other entries —
  including those with a missing lexeme form or null morphtype — MUST default to the stem
  partition** (never dropped from both tabs, never a crash). Each entry MUST appear in exactly
  one tab (no overlap, no double-listing).
- **FR-003**: The user MUST be able to check/uncheck individual stem entries; the selection MUST
  record the picked stem GUIDs (the wizard's item-pick set), consistent with the affix picker.
- **FR-004**: Picked stems MUST feed the same Model-A grammatical-dependency closure as affixes:
  the POS, inflection classes, stem names, inflection features, and exception features a stem
  depends on MUST be computed and preselected on the Skeleton / Grammatical-deps pages and
  included in the plan.
- **FR-005**: A picked stem's owned-child closure (senses, MSAs, allomorphs, examples,
  pronunciations, etymologies, entry-refs) MUST travel with the stem, using the shared LexEntry
  closure engine.
- **FR-006**: Every stem row MUST display its target presence (NEW / IN TARGET / SIMILAR) using
  the affix picker's logic; blank when no target is bound.
- **FR-007**: A source with zero stem entries MUST render an empty tab (not the stub, not an
  error) and MUST NOT block advancing.
- **FR-008**: The pane's picks MUST feed the existing plan/closure engine
  (`Lib/preview.py` / `Lib/transfer.py`) via the shared LexEntry picker engine; nothing on the
  pane writes to the target (the only write remains at Move).
- **FR-009**: Deselecting a grammatical dependency a kept stem needs, when the target lacks it,
  MUST be reported as an entry-centric missing-reference warning (one per kept stem with an
  unresolvable dependency), routed to the shared aggregated Move gate, never silently
  transferred broken (Constitution V).
- **FR-010**: Missing-reference warnings MUST feed the shared aggregated Move gate — one
  combined confirmation dialog across all wizard pages, never one prompt per stranded
  dependency.
- **FR-011**: GOLD-shipped objects MUST NOT be re-created (engine GOLD-skip); GUID-first
  identity governs create-vs-skip (Constitution I).
- **FR-012**: This phase MUST NOT present conflict-mode (ADD_NEW / MERGE / OVERWRITE) controls;
  the per-category Layer-1 default MUST be applied automatically.

### Key Entities *(include if feature involves data)*

- **Stem entry**: a `LexEntry` whose lexeme-form morphtype is a non-affix type (stem, root,
  bound root, particle, …); the item the user picks.
- **Stem pick set**: the set of picked stem GUIDs recorded on the wizard selection, sibling to
  the affix pick set, feeding the shared Model-A closure.
- **Derived grammatical dependency**: a POS / inflection class / stem name / inflection feature
  / exception feature computed from picked stems and preselected downstream.
- **Missing-reference warning**: a (kept-stem, stranded-dependency) pair produced when a needed
  dependency is deselected and absent from the target; aggregated for the shared Move gate.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The Stems tab is enabled and lists exactly the stem-morphtype entries; no entry
  appears in both the Affixes and Stems tabs (partition is complete and disjoint).
- **SC-002**: Picking a stem and advancing includes that stem and its owned-child closure in
  the plan, verified live against a stem-bearing source→target pair.
- **SC-003**: A picked stem's POS / inflection class / stem-name dependencies are preselected on
  the Skeleton / Grammatical-deps pages and appear in the plan; deselecting the stem drops the
  dependencies pulled solely on its account.
- **SC-004**: Every stem row shows a target-presence status; with source=target, 100% read IN
  TARGET; with a fresh target, rows read NEW.
- **SC-005**: A kept stem whose needed dependency is deselected and target-absent produces
  exactly one aggregated warning entry and a single Move confirmation — never per-item prompts.
- **SC-006**: A source with zero stems shows an empty (non-stub, non-error) tab and the wizard
  advances.
- **SC-007**: The pane presents no ADD_NEW / MERGE / OVERWRITE control; the per-category Layer-1
  default is applied without user input.

## Assumptions

- The target project is bound before the Item picker (Project+WS page), so target presence and
  missing-reference checks have live target data — same early-bind assumption as affixes/009.
- Stems reuse the **shared LexEntry picker/closure engine** (owned-child closure + grammatical
  dependency wiring) that the affix picker uses; only the morphtype partition differs. This
  feature depends on that shared engine (currently in the Phase 3c refactor) and does not create
  a parallel stem engine.
- **Morphtype partition rule**: an entry is an **affix** only when
  `LexemeFormOA.MorphTypeRA.IsAffixType` is explicitly true; every other entry — including one
  with a missing lexeme form or null morphtype — defaults to the **stem** partition, surfaced in
  the Stems tab rather than silently dropped (per the 2026-07-05 clarification; no longer
  deferred to `research.md`).
- **Default selection**: unlike Model-B blocks, the Stems tab follows the **affix picker's**
  default (not all-preselected wholesale) — the item-derived model starts from the user's picks;
  this matches the Affixes tab and is not re-specified here.
- The transfer unit is the individual `LexEntry` plus its owned-child closure; there is no
  sub-field fragment selection on this pane (field-level merge is the 020 phase).
- The shared aggregated Move gate is owned by the existing wizard Move gate (009/010); this
  feature routes its warnings into it and does not create a pane-specific dialog.
- Conflict handling beyond Layer-1 defaults (field-level merge, per-category modes) is the later
  020 phase and OUT OF SCOPE. Lexical-entry types (021), rules (018), custom fields (016),
  phonology (010), and semantic domains are separate increments and OUT OF SCOPE.
- **No target bound:** the missing-reference check treats the target as lacking every reference
  (safe default); deliberate surface-rather-than-hide policy, not a bug.

# Feature Specification: Rules Page — Ad Hoc & Compound Rules (Model-B Block + Engine)

**Feature Branch**: `018-rules-page`

**Created**: 2026-07-05

**Status**: Draft

**Input**: User description: "Rules page (Ad Hoc #20, Compound Rules #21). No spec. Roadmap
build-sequence step 3."

## Context

This feature adds a **Model-B (independent block)** wizard page surfacing the two
morphological-rule inventories — **Ad Hoc Rules**
(`MorphologicalDataOA.AdhocCoProhibitionsOS`, roadmap #20) and **Compound Rules**
(`MorphologicalDataOA.CompoundRulesOS`, roadmap #21) — AND the transfer **engine** those
categories need. Unlike the Phonology (010) and Lexical-entry types (021) blocks, whose
engines already ship, the rules engine is **not yet implemented**: in
[Lib/categories.py](../../src/gramtrans/Lib/categories.py) the `adhoc_compound_rules_*`
callbacks (`enumerate_source`, `required_writing_systems`, `plan_action`, `execute_action`)
currently `raise NotImplementedError("Phase 3c T056-T060")`. This spec therefore covers
**both** the engine callbacks and the wizard page.

Both LCM lists are heterogeneous, requiring **per-subclass dispatch** (planned as FR-341):

- Ad hoc prohibitions (`IMoAdhocProhibition`): `IMoAlloAdhocProhib` (allomorph adjacency
  prohibitions, reference `IMoForm` allomorphs), `IMoMorphAdhocProhib` (morpheme adjacency
  prohibitions, reference `IMoMorphSynAnalysis`/morphemes), and the `IMoAdhocProhibGr`
  grouping node that owns children.
- Compound rules (`IMoCompoundRule`): `IMoEndoCompound` and `IMoExoCompound`, which reference
  parts of speech (left/right members and the resulting `ToMsa`/overriding POS).

Because each rule references morphemes and/or parts of speech that live in the Model-A
grammar, this block's dependencies point **into** the affix/POS selection. It is therefore
placed **after** the Model-A pages (and after Lexical-entry types 021), before Preview:
Project+WS → Custom Fields → Phonology → Affixes → Skeleton → Grammatical deps →
Lexical-entry types → **Rules** → Preview → Finish. Closure is computed at Preview regardless
of page order; placement is a UX choice (see Assumptions).

Consistent with 010/021: no conflict-mode UI this phase (Layer-1 category defaults apply
automatically); the NEW / IN TARGET / SIMILAR target-status column carries collision
information; nothing on the page writes to the target (the only write remains at Move); GOLD
inviolability and GUID-first identity hold (Constitution I).

## Clarifications

### Session 2026-07-05

- Q: Page placement? → A: **Keep drafted order** — Rules sits after Lexical-entry types (021),
  both after Grammatical deps and before Preview. Rule dependencies point into the Model-A
  grammar; closure is still computed at Preview, so correctness does not depend on the slot.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Engine transfers ad hoc and compound rules by subclass (Priority: P1)

The transfer engine enumerates every ad hoc prohibition and compound rule in the source,
dispatches by concrete subclass, plans a GUID-preserving create action for each user-defined
rule not already in the target, and executes it — creating the correct LCM subclass with its
member/reference wiring intact.

**Why this priority**: Without the engine, the page has nothing to feed and no rule can
transfer. This is the foundational MVP slice; the UI (US2) is inert until it exists.

**Independent Test**: With a source containing at least one `IMoAlloAdhocProhib`, one
`IMoMorphAdhocProhib`, one `IMoEndoCompound`, and one `IMoExoCompound`, run the engine
directly (no UI) against a fresh target; confirm each is created as the correct subclass with
its referenced morphemes/POS wired, and re-running is idempotent (FR-307).

**Acceptance Scenarios**:

1. **Given** a source ad hoc prohibition of each subclass, **When** the engine plans and
   executes, **Then** the target gains one object of the matching subclass per source rule,
   GUID-preserved, with allomorph/morpheme references resolved to target objects.
2. **Given** a source compound rule of each subclass, **When** the engine plans and executes,
   **Then** the target gains the matching `IMoEndoCompound`/`IMoExoCompound` with left/right
   member POS and result POS wired to target objects.
3. **Given** a rule already present in the target by GUID, **When** the engine plans, **Then**
   it emits a Skip (no duplicate) — idempotency holds on re-run.
4. **Given** an `IMoAdhocProhibGr` grouping node, **When** the engine transfers its children,
   **Then** the group structure is preserved (children owned by the transferred group).

---

### User Story 2 - Transfer the whole rules block from the wizard (Priority: P1)

Arriving at the Rules page, the user sees every user-defined ad hoc rule and compound rule
already selected, grouped by category with counts, and can advance with a single click to
bring the block across.

**Why this priority**: Wholesale transfer is the dominant Model-B case and the reason the
engine exists; all-selected-by-default delivers it with zero interaction.

**Independent Test**: Bind a source with rules; open the page; confirm both categories render
preselected with correct counts and the collapsed selection includes every user-defined rule
before any interaction.

**Acceptance Scenarios**:

1. **Given** a bound source with rule data, **When** the page is shown, **Then** every
   user-defined rule row is checked and each category group toggle reads fully-selected.
2. **Given** the fully-selected page, **When** the user advances without interacting,
   **Then** the plan includes all user-defined ad hoc and compound rules.
3. **Given** a category with zero user-defined rules, **When** the page renders, **Then** that
   category shows as empty (not an error) and the page still advances.

---

### User Story 3 - Toggle the whole block off, or trim individual rules (Priority: P1)

The user can turn the entire rules block off with one control, or keep it on and deselect
individual rules for a leaner transfer.

**Why this priority**: Wholesale-with-opt-out is the defining Model-B behavior; without it the
"NONE" and "bare-bones" cases are impossible. Independently testable on top of US2.

**Independent Test**: Toggle the whole block off; confirm the plan contains zero rules. Toggle
back on, deselect one compound rule; confirm the plan contains all rules except that one.

**Acceptance Scenarios**:

1. **Given** the fully-selected page, **When** the user toggles the whole block off, **Then**
   all rows read unchecked and the plan contains no rule items.
2. **Given** the block on, **When** the user deselects a single ad hoc rule, **Then** the plan
   contains every rule except that one.
3. **Given** all rules in a category deselected individually, **When** the page state is read,
   **Then** that category's group toggle reads fully-unchecked (tristate consistency).

---

### User Story 4 - Rule member references travel or are reported, never silently broken (Priority: P1)

A transferred rule's referenced morphemes/allomorphs (ad hoc) or parts of speech (compound)
must resolve in the target: if the reference is not already in the target and its source
object was deselected on the Model-A pages, the user is warned once, in aggregate, at Move.

**Why this priority**: Referential Completeness (Constitution V) is non-negotiable. A compound
rule with a dangling member POS or an ad hoc prohibition with a missing allomorph is a broken
transfer.

**Independent Test**: Keep a compound rule whose left-member POS was deselected on Grammatical
deps and is absent from target; confirm Preview shows one aggregated warning naming the rule
and Move requires a single consolidated confirmation.

**Acceptance Scenarios**:

1. **Given** a kept compound rule referencing POS P, **When** P is deselected and absent from
   target, **Then** Preview shows an entry-centric warning naming the rule and Move pops one
   consolidated confirmation before writing.
2. **Given** a kept ad hoc prohibition referencing allomorph/morpheme M, **When** M is absent
   from target, **Then** the same aggregated warning + single Move confirmation applies.
3. **Given** a rule whose references all resolve in the target (or are being transferred),
   **When** the plan is computed, **Then** no missing-reference warning is raised for it.

---

### User Story 5 - Know what already exists in the target (Priority: P2)

Every selectable rule row shows whether it is NEW, IN TARGET, or SIMILAR against the
early-bound target.

**Why this priority**: Reuses the 008/009/010 target-status logic; informs decisions but does
not gate them (conflict handling is deferred).

**Independent Test**: Bind source=target; confirm every rule row reads IN TARGET. Bind a fresh
target; confirm rows read NEW.

**Acceptance Scenarios**:

1. **Given** a bound target, **When** the page renders, **Then** each rule row shows
   NEW / IN TARGET / SIMILAR computed against that target.
2. **Given** no target bound, **When** the page renders, **Then** the target-status column is
   blank and the page does not crash.

---

### Edge Cases

- **Source with no rules at all**: both categories render empty; the whole-block toggle reads
  unchecked/disabled (NOT vacuously fully-selected); no rule actions are planned.
- **One category populated, the other empty**: the empty category shows as empty; the
  populated one behaves normally.
- **Ad hoc grouping node (`IMoAdhocProhibGr`) with mixed selected/deselected children**: the
  group is created only if at least one child is kept; deselected children are not created;
  group ownership of kept children is preserved.
- **Rule referencing a morpheme/POS the target already has**: the reference resolves; no
  warning; the rule wires to the existing target object.
- **Unknown/future rule subclass encountered**: the engine MUST fail loudly for that item
  (explicit unhandled-subclass error), not silently skip it, so coverage gaps are visible.
- **No target bound**: target-status blank; missing-reference checks degrade gracefully (treat
  target as lacking the reference — safe default), no crash.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The engine MUST implement `adhoc_compound_rules_enumerate_source` to yield every
  ad hoc prohibition (`AdhocCoProhibitionsOS`) and compound rule (`CompoundRulesOS`) in the
  source, including children of `IMoAdhocProhibGr` grouping nodes.
- **FR-002**: The engine MUST dispatch per concrete subclass — `IMoAlloAdhocProhib`,
  `IMoMorphAdhocProhib`, `IMoAdhocProhibGr`, `IMoEndoCompound`, `IMoExoCompound` — for both
  planning and execution (FR-341 per-subclass dispatch).
- **FR-003**: `plan_action` MUST be GUID-first: emit a create action for a user-defined rule
  absent from the target by GUID, and a Skip when the GUID is already present (idempotency,
  FR-307). GOLD-shipped rules (if any) MUST be skipped (Constitution I).
- **FR-004**: `execute_action` MUST create the correct LCM subclass in the target with GUID
  preserved and MUST wire each rule's references (ad hoc: allomorph/morpheme members; compound:
  left/right member POS and result POS) to the corresponding target objects by GUID.
- **FR-005**: `adhoc_compound_rules_dependencies` MUST yield the rule's member references as
  cross-category dependencies (ad hoc → the affix/allomorph objects; compound → the POS
  objects) so closure pulls them when the rule is kept.
- **FR-006**: The engine MUST fail loudly on an unhandled rule subclass rather than silently
  skipping it, so coverage gaps surface in verification.
- **FR-007**: The wizard MUST present a Rules page positioned after Lexical-entry types and
  before Preview.
- **FR-008**: The page MUST surface two categories, grouped and individually itemized: Ad Hoc
  Rules and Compound Rules, with grouping-node structure represented.
- **FR-009**: The page MUST open with all user-defined rules preselected; advancing without
  interaction transfers the block.
- **FR-010**: The page MUST provide a single whole-block toggle (tristate: all / none /
  partial) and per-item deselect/re-select with tristate roll-up on category and grouping-node
  toggles.
- **FR-011**: Each category group MUST display its user-defined rule count; an empty category
  MUST render as empty (not an error) and MUST NOT block advancing.
- **FR-012**: Every selectable rule row MUST display its target presence
  (NEW / IN TARGET / SIMILAR); blank when no target is bound.
- **FR-013**: The page's selections MUST feed the existing plan/closure engine
  (`Lib/preview.py` / `Lib/transfer.py`) via the new `adhoc_compound_rules_*` callbacks;
  nothing on the page writes to the target (the only write remains at Move). Per-item trim uses
  the same per-category item-pick subset on `Selection` as spec 010.
- **FR-014**: A kept rule whose member reference is deselected on the Model-A pages AND absent
  from the target MUST be reported as an entry-centric missing-reference warning (one per kept
  rule with an unresolvable reference), routed to the shared aggregated Move gate, never
  silently transferred broken (Constitution V).
- **FR-015**: Missing-reference warnings MUST feed the shared aggregated Move gate — one
  combined confirmation dialog across all wizard pages, never one prompt per stranded
  reference.
- **FR-016**: This phase MUST NOT present conflict-mode (ADD_NEW / MERGE / OVERWRITE) controls;
  the per-category Layer-1 default MUST be applied automatically.

### Key Entities *(include if feature involves data)*

- **Ad hoc prohibition**: an `IMoAdhocProhibition` (allo/morph subclass, or grouping node) that
  forbids a co-occurrence of allomorphs/morphemes; references those members.
- **Compound rule**: an `IMoCompoundRule` (endo/exo) defining a compounding pattern; references
  left/right member POS and a result POS.
- **Rules block selection**: the set of chosen user-defined rules across both categories, each
  with checked state, grouping-node position, and target-presence status; plus the whole-block
  toggle state.
- **Missing-reference warning**: a (kept-rule, stranded-member) pair produced when a needed
  morpheme/POS is deselected and absent from the target; aggregated for the shared Move gate.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The engine transfers one target object of the correct subclass per source rule
  across all five subclasses, GUID-preserved, with references wired — verified live against a
  rule-bearing source→target pair.
- **SC-002**: Re-running the transfer produces zero duplicate rules (all Skip on second run) —
  idempotency (FR-307) holds.
- **SC-003**: On opening the page against a rule-bearing source, 100% of user-defined rules
  across both categories are checked with zero user actions.
- **SC-004**: Advancing the page unchanged produces a plan whose per-category rule counts
  exactly equal the user-defined source inventory counts shown on the page.
- **SC-005**: Toggling the whole block off yields a plan with zero rules; toggling back on
  restores all rules.
- **SC-006**: A kept rule whose member reference is otherwise unselected and target-absent
  produces exactly one aggregated warning entry and a single Move confirmation — never per-item
  prompts; no warning when the reference resolves in the target.
- **SC-007**: Every rule row shows a target-presence status; with source=target, 100% read IN
  TARGET; with a fresh target, rows read NEW.
- **SC-008**: An unhandled rule subclass causes a loud, visible failure (not a silent skip) in
  verification.
- **SC-009**: The page presents no ADD_NEW / MERGE / OVERWRITE control; the per-category
  Layer-1 default is applied without user input.

## Assumptions

- The target project is bound before this page (Project+WS), so target presence and
  missing-reference checks have live target data — same early-bind assumption as 008/009/010.
- **Default selection is ALL-preselected** (user-defined rules only); the block opens fully
  checked and the user deselects to trim. "NONE" is reachable via the whole-block toggle.
- The five rule subclasses named above (`IMoAlloAdhocProhib`, `IMoMorphAdhocProhib`,
  `IMoAdhocProhibGr`, `IMoEndoCompound`, `IMoExoCompound`) constitute the coverage set; any
  additional subclass surfaced during implementation is added to the dispatch and MUST fail
  loudly until handled.
- The transfer unit is the individual rule object; there is no sub-field fragment selection on
  this page (field-level merge is the 020 phase).
- **Page placement after Lexical-entry types** is a resolved UX decision (rule deps point into
  the Model-A grammar): closure is computed at Preview, so correctness does not depend on the
  exact slot.
- The shared aggregated Move gate is owned by the existing wizard Move gate (009/010); this
  feature routes its warnings into it and does not create a page-specific dialog.
- Conflict handling beyond Layer-1 defaults (field-level merge, per-category modes) is the
  later 020 phase and OUT OF SCOPE. Lexical-entry types (021), stems (019), custom fields
  (016), and phonology (010) are separate increments and OUT OF SCOPE.
- **No target bound:** the missing-reference check treats the target as lacking every reference
  (safe default); deliberate surface-rather-than-hide policy, not a bug.

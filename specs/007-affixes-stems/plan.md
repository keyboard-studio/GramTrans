# Implementation Plan: Phase 3c — Affixes / Stems / Templates Block

**Branch**: `main` (solo fork, no feature branch) | **Date**: 2026-06-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/007-affixes-stems/spec.md`

## Summary

Wire memo steps 14-18 plus the 17.1 MSA-slot wiring sub-pass through the existing `_LEAF_DISPATCH_CATEGORIES` loop established by Phase 3a (commit 608b72c) and extended by Phase 3b. Five new categories enter the dispatch tuple: `AFFIXES`, `ADHOC_COMPOUND_RULES`, `SLOTS`, `AFFIX_TEMPLATES`, `STEMS`. Unlike Phase 3a/3b, two of these (`AFFIXES`, `STEMS`) own deep child trees (senses, MSAs, allomorphs, examples, pronunciations, etymologies, entry-refs) — the planner walks the child closure inside `enumerate_source` per parent entry; the executor creates the parent + owned children atomically. `MSA.SlotsRC` and `LexEntryRef.ComponentLexemesRS`/`PrimaryLexemesRS` are deferred to two named tail passes: 17.1 lives as a post-execute block on `AFFIX_TEMPLATES`, post-pass A runs after `STEMS`.

Technical approach: Per Phase 3a/3b precedent, MCP-probe each new factory at planning time before locking the contracts. Affix-vs-stem partition is decided per-entry by `entry.LexemeFormOA.MorphTypeRA.IsAffixType` (FR-332). Compound rules dispatch on `ICmObject(src_obj).ClassName` to per-subclass factories — `IMoEndoCompoundFactory`, `IMoExoCompoundFactory`, and any other concrete subclasses surfaced at probe time (FR-341). Phase 0 verb-vertical is retired-in-place by relying on the universal target-GUID collision guard in `_create_with_guid` rather than category-specific Phase-0-collision code (FR-334). The 17.1 sub-pass consumes a new `plan.msa_slot_bindings` dict populated by the affix-entry executor; templates' post-execute tail writes `MSA.SlotsRC` from that mapping (FR-333).

## Technical Context

**Language/Version**: Python 3.12.

**Primary Dependencies**:
- `flexlibs2` (MattGyverLee fork) — direct LCM access per constitution Principle II. Pre-existing Operations classes already in fork: `LexEntryOperations`, `LexSenseOperations`, `AllomorphOperations`, `MSAOperations`, `MorphRuleOperations`. New surface for Phase 3c probes: affix-template / slot / compound-rule factories under `LangProject.MorphologicalDataOA` and `IPartOfSpeech.AffixTemplatesOS` / `AffixSlotsOC`.
- `SIL.LCModel` interfaces (lazy-imported): `ILexEntry`, `ILexSense`, `IMoMorphType` (for the `IsAffixType` partition), `IMoInflAffMsa`, `IMoStemMsa`, `IMoAffixAllomorph`, `IMoStemAllomorph`, `ILexExampleSentence`, `ILexPronunciation`, `ILexEtymology`, `ILexEntryRef`, `IMoInflAffixSlot`, `IMoInflAffixTemplate`, `IMoEndoCompound`, `IMoExoCompound`, `IMoAdhocProhibition`, plus factories.

**Storage**: No new storage. State lives in target LCM objects + the existing residue tag. One new in-plan mapping: `RunPlan.msa_slot_bindings: dict[Guid, list[Guid]]` (msa_guid → list of slot_guids) — ephemeral, consumed at the end of `AFFIX_TEMPLATES` execution and discarded with the plan.

**Testing**:
- `pytest` unit tests. Five new test files for the five categories + one wiring test + one post-pass A test:
  `test_categories_affixes.py`, `test_categories_adhoc_compound.py`, `test_categories_slots.py`, `test_categories_affix_templates.py`, `test_categories_stems.py`, `test_phase3c_leaf_dispatch.py`, `test_phase3c_post_pass_a.py`. The 17.1 sub-pass is covered inside `test_categories_affix_templates.py`.
- Live MCP verification on `Ejagham Mini` → `Ejagham Full GT-Test` exercising the full Phase 3a→3b→3c chain end-to-end. Per memo, the production pipeline is now full-chain; Phase 0 verb-vertical is acknowledged as POC and is not re-run as part of Phase 3c verification.

**Target Platform**: Same as Phases 0-2/3a/3b — Windows desktop FlexTools host (pythonnet + LCM 9.x).

**Project Type**: FlexTools-compatible Python module. Single project; flat entry + `src/gramtrans/Lib/` siblings.

**Performance Goals**:
- SC-301: ~250 affix + stem entries, ~25 slots, ~5 templates transfer in under 10 seconds wall-clock.
- Per-category `enumerate_source` < 300ms even when walking the affix/stem child closure (senses + MSAs + allomorphs + examples + pronunciations + etymologies + entry-refs). LexEntries are the largest realistic inventory at ~250.
- Post-pass A and 17.1 sub-pass each < 200ms for the realistic ceiling.

**Constraints**:
- Constitution Principle II: flexlibs2-Direct.
- Principle III: Preview-Before-Mutate — every new `plan_action` runs during `build_run_plan`, no LCM writes. The 17.1 sub-pass and post-pass A produce their `PlannedAction`s during preview as well; executor merely wires references using already-stashed mappings.
- Principle IV: additive over Phases 0/1/2/3a/3b. The collision guard in `_create_with_guid` already returns `Skip(ALREADY_PRESENT_BY_GUID)` for entries Phase 0 created; no new Phase-0-aware code paths in Phase 3c.
- Affix vs stem partition is strictly per-entry by `IsAffixType` — no enumeration-time short-circuit, no global filter switch.
- Unknown compound subclasses MUST emit `Skip(NEEDS_MANUAL)` per FR-341; no lossy generic fallback.

**Scale/Scope**:
- Realistic ceiling: ~250 affix entries, ~250 stem entries, ~25 slots across all POSes, ~5 templates, ~10 compound rules, ~20 ad-hoc prohibitions. Phase 3c sized for this.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Justification |
|-----------|--------|---------------|
| I. FLEx Domain Fidelity | PASS | GUID preservation default for all five new categories where the factory supports `Create(Guid, owner)`. Where the factory lacks Guid overloads (MSAs and allomorphs via `IMoInflAffMsaFactory.Create(ILexEntry, SandboxGenericMSA)` — already verified in Phase 0 Layer 3), `identity_remap` per FR-303 inherited from Phase 1. GOLD inviolability does not apply to any Phase 3c category (no FW catalog at the affix/stem/template/slot/rule level). |
| II. flexlibs2-Direct | PASS | All five callbacks import `flexlibs2` Operations classes directly (`LexEntryOperations`, `MSAOperations`, `AllomorphOperations`, `MorphRuleOperations`). No adapter contract. |
| III. Preview-Before-Mutate | PASS | Five-callback shape preserved across all five new categories. The 17.1 sub-pass and post-pass A produce their planned wires during preview (`enumerate_source` returns the binding intent; `plan_action` records the binding as a side effect on `plan.msa_slot_bindings` / `plan.lexentry_ref_bindings`); the executor only emits the writes when the dispatch loop reaches the owning category. |
| IV. Phased Merge Discipline | PASS | Phase 3c ordered behind 0-2-3a-3b. FR-338 reaffirms Phase 1 overwrite + Phase 2 merge inheritance. FR-334 codifies retirement-in-place of Phase 0 verb-vertical via universal collision guard, no special-case code. |
| V. Referential Completeness | PASS | FR-332 enforces lexeme-form + morph-type closure for the affix/stem partition. FR-335 enforces sense → semantic-domain closure against Phase 3b transfers. FR-336 enforces MSA → Stratum closure against Phase 3a. FR-337 enforces ad-hoc + compound rules → affix LexEntry closure via `identity_remap`. FR-340 enforces post-pass A closure with explicit `DEPENDENCY_UNRESOLVED` skips. |

**No violations. No Complexity Tracking entries required.**

### Re-check after Phase 1 design

| Principle | Status | Notes |
|-----------|--------|-------|
| I. | PASS | data-model.md catalogs each LCM type per category and the `IsAffixType` partition; GOLD detection N/A. |
| II. | PASS | contracts/category-callbacks.md uses flexlibs2 Operations classes exclusively. |
| III. | PASS | quickstart.md exercises Preview first, then Move. Scenario E confirms preview produces no LCM writes. |
| IV. | PASS | quickstart.md Scenario F confirms a Phase 0 verb-vertical re-run after Phase 3c produces 0 new actions (SC-303). |
| V. | PASS | All five reference-closure FRs surface in data-model.md as explicit edge tables. |

## Project Structure

### Documentation (this feature)

```text
specs/007-affixes-stems/
|-- plan.md              # This file
|-- research.md          # Phase 0 output (MCP-probe results for new factories)
|-- data-model.md        # Phase 1 output
|-- quickstart.md        # Phase 1 output
|-- contracts/           # Phase 1 output
|   |-- category-callbacks.md      # 5-callback shape per category
|   |-- msa-slot-wiring.md         # 17.1 sub-pass contract
|   `-- post-pass-a.md             # LexEntryRef post-pass contract
|-- checklists/
|   `-- requirements.md            # Spec quality checklist (green)
`-- tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
src/gramtrans/Lib/
|-- models.py                # +5 GrammarCategory enum members:
|                            #   AFFIXES, ADHOC_COMPOUND_RULES, SLOTS,
|                            #   AFFIX_TEMPLATES, STEMS
|                            # +RunPlan.msa_slot_bindings: dict[Guid, list[Guid]]
|                            # +RunPlan.lexentry_ref_bindings: dict[Guid, dict]
|-- categories.py            # MOD: 5 new (category, 5-callback) registry entries.
|                            # Affixes + Stems share helper _walk_lex_entry_closure
|                            # for senses/MSAs/allomorphs/examples/etc.
|                            # Compound-rules executor dispatches on ClassName.
|-- preview.py               # MOD: extend _LEAF_DISPATCH_CATEGORIES with the
|                            # 5 new categories. Add 17.1 + post-pass A
|                            # planning entry points (called from leaf-dispatch
|                            # tail after AFFIX_TEMPLATES / STEMS respectively).
|-- transfer.py              # MOD: same _LEAF_DISPATCH_CATEGORIES extension.
|                            # AFFIX_TEMPLATES executor's tail block consumes
|                            # plan.msa_slot_bindings and writes MSA.SlotsRC.
|                            # STEMS executor's tail block runs post-pass A.
|-- conflict.py              # NO CHANGES (Phase 2 inheritance is FR-338)
`-- ws_mapping.py            # NO CHANGES

tests/
|-- unit/
|   |-- test_categories_affixes.py             # NEW
|   |-- test_categories_adhoc_compound.py      # NEW (per-subclass dispatch)
|   |-- test_categories_slots.py               # NEW
|   |-- test_categories_affix_templates.py     # NEW (covers 17.1)
|   |-- test_categories_stems.py               # NEW
|   |-- test_phase3c_leaf_dispatch.py          # NEW
|   |-- test_phase3c_post_pass_a.py            # NEW
|   `-- (existing 324 tests)                   # unchanged
`-- integration/
    `-- test_phase3c_affixes_stems_e2e.py      # NEW: 5-category run
                                               # against fake LCM surface
```

**Structure Decision**: Single project, FLExTrans-style flat entry + `Lib/` siblings. Phase 3c is the deepest extension to date — two of the five categories own non-trivial child trees, and two tail-pass mechanisms (17.1 sub-pass on `AFFIX_TEMPLATES`, post-pass A on `STEMS`) introduce a new in-plan binding mapping. Still, the leaf-dispatch shape from Phase 3a/3b absorbs the work without modifying the dispatch loop itself — only the executor's per-category tail blocks change.

## Selection UI Extension (revised 2026-07-01)

Two user design refinements landed after the cycle-1 "item-anchor" GO and before
build. The full UI narrative lives in `../../Transfer FLEx Grammar Module.md`
section "Selection UI Design"; this subsection records the formal deltas.

**Refinement 1 -- second mental model + per-category three-scope selector.**
Each schema category becomes a three-scope selector NONE / AS-NEEDED / ALL
(default AS-NEEDED), plus per-item dependency deselection inside AS-NEEDED. This
introduces a FOURTH plan disposition, `EXCLUDED-LOSSY` (deliberate, warn+allow),
distinct from the accidental hard-failing `DEPENDENCY_UNRESOLVED`.

Model deltas (`src/gramtrans/Lib/models.py`, Selection ~L140):
- Add `CategoryScope` enum {NONE, AS_NEEDED, ALL}.
- Replace/augment global `include_closure: bool` with
  `category_scopes: dict[GrammarCategory, CategoryScope]`. `include_closure=True`
  maps to uniform AS_NEEDED; an explicit whole-category toggle maps to ALL. The
  two were conflated under one bool and are now separated.
- Add per-item exclusion set `excluded_deps: frozenset[str]` (source GUIDs).
- Add `SkipReason.EXCLUDED_LOSSY` (or a dedicated warning channel) so the
  disposition is representable end-to-end.
- Keep backward-compat construction (bool -> uniform scope) so the existing 324
  tests pass until migrated.

`preview.py` closure branches (~L322 POS, ~L394 templates, ~L470/480 Layer-3
gate) currently read one `closure_on = selection.include_closure`. Each becomes
per-category-scope-aware: NONE (no pull; referencing entry -> EXCLUDED-LOSSY if
target lacks the dep), AS_NEEDED (current behaviour minus `excluded_deps`), ALL
(enumerate whole source category).

**Refinement 2 -- target-aware warning gate for deliberate omissions.**
Soft gate, never hard-blocks. Per dropped dep, three outcomes; only the third
warns: (1) dep exists in target -> LINK, silent; (2) dep absent + unreferenced ->
silent; (3) dep absent + a copied entry references it -> WARN+ALLOW =
EXCLUDED-LOSSY. Warning is ENTRY-CENTRIC ("Entry '-PL' will have no Part of
Speech"). Because target is bound+probed early (locked constraint), the
"exists in target?" check has live data at Preview time.

Gate surfaces in `stats_panel.py` as a distinct WARNING severity (not error, not
skip). Move is the confirmation gate: outstanding warnings -> summary dialog
("N entries will transfer with missing references. Proceed?") before writing.
Preserves "only write is at Move/Finish."

**Refinement 3 -- 5-page wizard replaces single-window (BUILD DECISION 2026-07-01).**
The single-window base (commit 88f2925) is verified GREEN (422 passed / 22 skipped
/ 0 failed, all constitution gates PASS). The delivery vehicle becomes a 5-page
QWizard that re-hosts the existing widgets verbatim and REPLACES `main_window`. The
full narrative is in `../../Transfer FLEx Grammar Module.md` section (0); formal
deltas:

- Pages: (1) Project + Writing Systems, (2) item picker [Stems tab stubbed/disabled],
  (3) schema scope + conflict mode, (4) Preview, (5) Finish/Move.
- WS becomes a PROJECT-LEVEL page-1 decision over ACTIVE writing systems only. The
  two-stage `NEEDS_WS_MAPPING` handshake is RETIRED. Low blast radius: only
  `tests/unit/test_api_surface.py` asserts the handshake shape (2 assertions to
  rewrite); the other five `compute_preview` callers ride through unchanged.
- EMPTY-WS PRUNE AT MOVE: prune multistring/multiunicode alternatives with no
  content for a chosen WS, using the strings `GetSyncableProperties` already
  extracted (no ITsMultiString cast, no extra LCM call).
- WIRE THE P1 CONFIRM-ON-MOVE GATE at Finish: the verified base has the gate as a
  validated data-model predicate (`plan.excluded_lossy_count()`) but it is NOT
  Qt-wired -- a headless Move would silently proceed. Finish MUST query the
  predicate and block/confirm when `excluded_lossy_count() > 0`.

**P0 defect fixes (2026-07-01, commit on feature/007-selection-ui).**

- Defect 1 [P0] -- Write-layer idempotency guard (`transfer.py`).
  LCM `factory.Create(existingGuid, owner)` does NOT throw on a duplicate GUID;
  it silently writes a second object to `.fwdata` on CloseProject. Fix: at every
  Guid-preserving Create site, call `target.Object(src_guid)` inside try/except
  BEFORE `factory.Create`. If the object exists and its ClassName matches, return
  the typed cast (skip Create). If the ClassName mismatches, log WARNING and return
  None (skip Create, do not reuse wrong-class object).
  Seven guarded sites: _create_pos_with_guid (PartOfSpeech),
  _create_template_with_guid (MoInflAffixTemplate), _create_slot_with_guid
  (MoInflAffixSlot), _create_environment_with_guid (PhEnvironment),
  _create_lexentry_with_guid (LexEntry), _create_lexsense_with_guid (LexSense).
  MSA and allomorph are EXCLUDED because their factories have no Guid overload
  (they remap via identity_remap).
  Move non-repeatability: after a successful execute_move, `_PagePreview._cached_plan`
  is set to None so a double-click or re-entry cannot re-execute the plan.

- Defect 2 [P0-ish] -- WS page rebuild (`selection_wizard.py`).
  The bare QListWidget on page 1 is replaced by a three-way MAP / CREATE / SKIP
  control split into Vernacular WS and Analysis WS groups (by WSKind). Dual-role
  WS appears in both groups; vernacular is lead (analysis defaults to vernacular
  choice, linked-until-touched). Dual-role CREATE -> both roles point at the SAME
  target WS (no double-create, WSMapping 1:1 invariant satisfied). The resulting
  WSMapping is threaded into both `gt_api.compute_preview` and `gt_api.execute_move`
  (via the plan, which carries ws_mapping from compute_preview).

**Refinement 4 -- conflict-mode model (category-kind default + per-item IsProtected).**
Add `ConflictMode` enum {ADD_NEW, MERGE, OVERWRITE} and
`category_conflict_modes: dict[GrammarCategory, ConflictMode]` on Selection. Gating
is two-layer (full table + rationale in the design doc section (h)):
- Layer 1 category-kind default (from lex-domain classification):
  MULTI_INSTANCE offers all three; SINGLETON_NONDELETABLE hides ADD_NEW;
  GOLD_RESERVED hides ADD_NEW + forbids OVERWRITE (Merge/link only).
- Layer 2 per-item `IsProtected` refinement (cast-safe read on ILexEntryType /
  IPartOfSpeech / ICmSemanticDomain / IMoMorphType / ILexEntryInflType /
  ILexRefType): a protected item downgrades to Merge/link-only regardless of
  category default; a non-protected item offers the full set (capped by Layer 1).
  Failed cast / absent attr -> treat as IsProtected=False (permissive) only when
  protection cannot be proven.
- Reclassifications from the probe session: STRATA -> MULTI_INSTANCE-capable
  (StrataOS is an Owning SEQUENCE, multi is model-legal). CUSTOM_FIELDS keeps the
  conservative default (ADD hidden, OVERWRITE forbidden, MERGE no-op-if-identical)
  pending probe 4 (custom-field-definition mutability), which is UNRESOLVED but
  safely defaulted.
- Interim MERGE is Option b: link-if-present-by-GUID else ADD, NO field-level
  update, explicitly labeled in the page-3 control.

**Constitution alignment (re-checked):**
- III Preview-Before-Mutate: PASS. Scope resolution + warning computation happen
  at Preview; confirm-on-Move keeps the single write point at Move/Finish. Wizard
  page 5 = Finish = the single write point; the newly-wired confirm gate preserves
  the invariant.
- V Referential Completeness: PASS (strengthened). Lines 248-251 require the
  closure be per-item deselectable AND require unsatisfiable deps be REPORTED, not
  silently transferred broken. Per-item exclusion satisfies the deselect mandate;
  the entry-centric warning + EXCLUDED-LOSSY disposition IS the required report.
- I FLEx Domain Fidelity: PASS. LINK-not-copy for already-present/GOLD deps
  preserves target identity; EXCLUDED-LOSSY writes a null reference only on
  explicit informed waiver. Per-item IsProtected gating prevents overwriting
  factory-seeded reference data while still permitting user-added peers.

## Complexity Tracking

> Constitution Check passed with no violations.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| _(none)_  | _(none)_   | _(none)_                            |

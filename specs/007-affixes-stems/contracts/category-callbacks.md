# Phase 3c Contract: Category Callbacks

**Date**: 2026-06-22
**Spec**: [../spec.md](../spec.md)
**Data model**: [../data-model.md](../data-model.md)

Each of the five new Phase 3c categories implements the standard 5-callback shape (`enumerate_source`, `dependencies`, `plan_action`, `execute_action`, `apply_residue`) established by Phase 0 leaf categories and the leaf-dispatch loop landed in Phase 3a (commit 608b72c). This contract documents the per-category signatures and side effects on the in-plan binding mappings.

## Universal callback shape (Phase 0 inheritance)

```python
def enumerate_source(source: ILcmCache, *, src_pos: Optional[IPartOfSpeech] = None) -> Iterable[ICmObject]: ...
def dependencies(src_obj: ICmObject, *, source: ILcmCache) -> Iterable[Tuple[GrammarCategory, Guid]]: ...
def plan_action(src_obj: ICmObject, *, target: ILcmCache, plan: RunPlan, run_ctx: RunContext) -> PlannedAction | Skip: ...
def execute_action(src_obj: ICmObject, action: PlannedAction, *, target: ILcmCache, plan: RunPlan, run_ctx: RunContext) -> ICmObject: ...
def apply_residue(target_obj: ICmObject, *, run_ctx: RunContext) -> None: ...
```

`plan` is the live `RunPlan` and is mutated only in `plan_action` (binding stashes) and the tail blocks defined below.

## Category: `AFFIXES`

**`enumerate_source`**: Filter `source.LangProject.LexDbOA.EntriesOC` to entries where `e.LexemeFormOA is not None and e.LexemeFormOA.MorphTypeRA is not None and e.LexemeFormOA.MorphTypeRA.IsAffixType`. Skip entries failing the closure with `Skip(DEPENDENCY_UNRESOLVED)` in `plan_action` (NOT filtered out at enumerate time — every source entry is surfaced to the planner so the skip is recorded).

**`dependencies`**: Yields `(POS, msa.PartOfSpeechRA.Guid)` for each MSA's owning POS. (`MorphType` is FW-global; no dependency edge emitted.)

**`plan_action`**: One `PlannedAction` per affix LexEntry. Side effect: for each affix MSA with non-empty source `SlotsRC`, append `(msa.Guid, [slot.Guid for slot in msa.SlotsRC])` to `plan.msa_slot_bindings`. For each EntryRef with non-empty `ComponentLexemesRS`/`PrimaryLexemesRS`, append to `plan.lexentry_ref_bindings`.

**`execute_action`**: Atomic write of the owned-child closure (E2 in data-model). Returns the created `ILexEntry`. Sub-dispatch on MSA `ClassName` (E4) and allomorph `ClassName` (E3). MSA `SlotsRC` is NOT written here — left empty for 17.1.

**`apply_residue`**: Carrier A — `entry.LiftResidue = TsStringUtils.MakeString(tag.serialise(), default_ws)`. Cascade to senses, MSAs, allomorphs as carrier A (per E9).

## Category: `ADHOC_COMPOUND_RULES`

**Corrected per T008/T009/T011 MCP probes — see [../probe-results.md](../probe-results.md).**

**`enumerate_source`**: Use the flexicon wrappers — `project.MorphRules.GetAllCompoundRules()` ∪ `project.MorphRules.GetAllAdhocCoProhibitions()`. The wrappers internally enumerate `MorphologicalDataOA.{CompoundRulesOS, AdhocCoProhibitionsOC}`.

**`dependencies`**: Per-subclass:
- Compound rules: `(STRATA, rule.StratumRA.Guid)` for the rule's stratum scope per FR-336; `(AFFIXES, msa.Guid)` for any owned `OverridingMsaOA`/`ToMsaOA`'s parent entry; `(POS, pos.Guid)` for the MSA's owning POS.
- Ad-hoc `MoAdhocProhibGr`: no top-level dependencies (members are owned children, walked recursively in `plan_action`/`execute_action`).
- Ad-hoc `MoAlloAdhocProhib`: `(AFFIXES, allo.Owner.Guid)` for each allomorph in `AllomorphsRS` (allomorphs belong to entries created in US1).
- Ad-hoc `MoMorphAdhocProhib`: `(AFFIXES, msa.Owner.Guid)` for each MSA in `MorphemesRS`.

**`plan_action`**: Subclass dispatch on `ICmObject(src_obj).ClassName`. Returns one `PlannedAction` per rule. Unknown subclass → `Skip(NEEDS_MANUAL)`.

**`execute_action`**: Per-subclass:
- `MoEndoCompound`: prefer `project.MorphRules.CreateCompoundRule(name, endocentric=True, description=...)` (flexicon wrapper); ServiceLocator fallback if unsuitable. Then write `HeadLast` and (if source has one) clone the owned `OverridingMsaOA` (recursive walk + identity_remap). Write inherited `StratumRA` + `ToProdRestrictRC`.
- `MoExoCompound`: `project.MorphRules.CreateCompoundRule(name, endocentric=False, description=...)`. Then clone the mandatory `ToMsaOA` (recursive walk + identity_remap). Write inherited `StratumRA` + `ToProdRestrictRC`.
- `MoAdhocProhibGr`: `IMoAdhocProhibGrFactory.Create(Guid)` via ServiceLocator; write `Name`, recursively create `MembersOC` (owned atoms — re-enter the dispatcher for each child atom).
- `MoAlloAdhocProhib`: `IMoAlloAdhocProhibFactory.Create(Guid)` via ServiceLocator; wire `AllomorphsRS`, `FirstAllomorphRA`, `RestOfAllosRS` via identity_remap against US1-created `IMoForm` allomorphs. Wire inherited `Adjacency`, `Disabled`.
- `MoMorphAdhocProhib`: `IMoMorphAdhocProhibFactory.Create(Guid)` via ServiceLocator; wire `MorphemesRS`, `FirstMorphemeRA`, `RestOfMorphsRS` via identity_remap against US1-created `IMoMorphSynAnalysis` instances. Wire inherited `Adjacency`, `Disabled`.

Owner attach: top-level rules go to `target.LangProject.MorphologicalDataOA.CompoundRulesOS` (`.Append`) or `AdhocCoProhibitionsOC` (`.Add`); nested atomic prohibitions become owned children of their parent `MoAdhocProhibGr.MembersOC`.

**`apply_residue`**:
- `MoEndoCompound`/`MoExoCompound`/`MoAdhocProhibGr`: Carrier B — `Description` multistring append.
- `MoAlloAdhocProhib`/`MoMorphAdhocProhib`: **no residue** — emit `report.Info(f"[adhoc-atomic] {src_guid} -> {target_guid} (run_id={tag.run_id})")` instead; no LCM mutation.

**Live-verification gap**: Ejagham Mini has 0 compound rules + 0 ad-hoc prohibitions (T012 inventory). US4 ships with unit + synthetic-fixture integration coverage only.

## Category: `SLOTS`

**`enumerate_source`**: For each POS already in target, walk `target.<POS>.AffixSlotsOC` against the corresponding `source.<POS>.AffixSlotsOC`. Sub-iteration; the planner emits one PlannedAction per source slot.

**`dependencies`**: Yields `(POS, owning_pos.Guid)` for the slot's owning POS.

**`plan_action`**: One `PlannedAction` per slot. Universal collision guard (FR-334) emits `Skip(ALREADY_PRESENT_BY_GUID)` if slot guid already in target.

**`execute_action`**: `IMoInflAffixSlotFactory.Create(Guid)`, then `pos.AffixSlotsOC.Add(slot)`. Phase 0 verified.

**`apply_residue`**: Carrier B — `Description` multistring append.

## Category: `AFFIX_TEMPLATES`

**`enumerate_source`**: For each POS already in target, walk `target.<POS>.AffixTemplatesOS` against `source.<POS>.AffixTemplatesOS`. One PlannedAction per template.

**`dependencies`**: Yields `(POS, owning_pos.Guid)` and `(SLOTS, slot.Guid)` for each slot referenced in `PrefixSlotsRS`/`SuffixSlotsRS`.

**`plan_action`**: One `PlannedAction` per template. Collision guard as above.

**`execute_action`**: Prefer `project.MorphRules.CreateAffixTemplate(pos_or_hvo, name, description=None)` (flexicon wrapper); ServiceLocator fallback to `IMoInflAffixTemplateFactory.Create(Guid)` only if Guid preservation requires it. Then wire **5 slot reference sequences** in source order via target-slot GUID lookup: `PrefixSlotsRS`, `SuffixSlotsRS`, `EncliticSlotsRS`, `ProcliticSlotsRS`, `SlotsRS` (per T010 probe — spec previously assumed only 2). Write `Final` (bool), `Disabled` (bool); wire `StratumRA` to Phase 3a-transferred Stratum by GUID (per FR-336). Clone owned `RegionOA` if non-null. **Tail block (17.1 sub-pass)**: after all template writes complete, iterate `plan.msa_slot_bindings`; for each `(msa_guid, slot_guids)` pair, write `msa.SlotsRC.Add(slot)` per resolved slot. Unresolved → `Skip(DEPENDENCY_UNRESOLVED)` emitted into the run report (NOT a PlannedAction failure — the template write already succeeded).

**`apply_residue`**: Carrier B — `Description` multistring append.

## Category: `STEMS`

**`enumerate_source`**: Filter `source.LangProject.LexDbOA.EntriesOC` to entries where `e.LexemeFormOA is not None and e.LexemeFormOA.MorphTypeRA is not None and not e.LexemeFormOA.MorphTypeRA.IsAffixType`.

**`dependencies`**: Yields `(POS, msa.PartOfSpeechRA.Guid)` and `(SEMANTIC_DOMAINS, domain.Guid)` for each sense's `SemanticDomainsRC` entry. `(STRATA, stratum.Guid)` for each `MoStemMsa.StratumRA`.

**`plan_action`**: One `PlannedAction` per stem entry. Side effect: same `lexentry_ref_bindings` stash as `AFFIXES` for any EntryRefs found on stem entries.

**`execute_action`**: Same owned-child closure as `AFFIXES`, with MSA dispatch including `MoStemMsa` (E4). Wire `MoStemMsa.StratumRA` by GUID lookup to Phase 3a-transferred Strata; missing → `Skip(DEPENDENCY_UNRESOLVED)` on the MSA. Wire `sense.SemanticDomainsRC` by GUID lookup; missing → `Skip(DEPENDENCY_UNRESOLVED)` on the sense.

**Tail block (post-pass A)**: after all stem writes complete, iterate `plan.lexentry_ref_bindings`; for each `(src_entry_guid, refs)` pair, resolve target entry by GUID, resolve each referenced lexeme by (a) in-plan creation list or (b) target-by-GUID lookup, write RS sequence in source order. Unresolved → `Skip(DEPENDENCY_UNRESOLVED)` on the EntryRef (FR-340).

**`apply_residue`**: Carrier A — same as `AFFIXES`.

## Cross-cutting invariants

- All five categories MUST honor `enable_overwrite=True` per FR-338 — overwrite path follows Phase 1 fingerprint matching for owned children (allomorphs, MSAs) where GUID is not preserved; direct GUID-overwrite for entries/senses/slots/templates.
- All five categories MUST surface per-field conflicts to Phase 2's `ConflictPrompt` queue per FR-338 — no Phase 3c-specific merge code.
- Empty-source UX (FR-339): each of the five categories MUST be picked up by `report._build_from_plan`'s `empty_categories` derivation; verified by an inheritance test per `tests/unit/test_phase3c_leaf_dispatch.py`.

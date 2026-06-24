# Phase 3c Quickstart: Affixes / Stems / Templates Block

**Date**: 2026-06-22
**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)
**Source pair**: `Ejagham Mini` → `Ejagham Full GT-Test` (per Phase 3a/3b precedent)

This quickstart documents the runnable validation scenarios for Phase 3c. It exists for live-MCP verification by future sessions and the close-sweep gate. Implementation code lives in `tasks.md` and the actual `Lib/` modules; this file is a run guide only.

## Prerequisites

1. **Backup restored to target**: `Ejagham Full GT-Test` restored from `backups/Ejagham Full.fwbackup` (see [STATUS.md](../../STATUS.md) "Restore the throwaway target" command).
2. **Phase 3a + Phase 3b shipped to target first**: Phase 3c assumes the phonology block (memo step 5b Strata, step 13b Semantic Domains) and the inflection-prep block (POS, Inflection Features, Inflection Classes, Variant Types, Complex Form Types, Semantic Domains) are already in target. Run Phase 3a then Phase 3b first if the target is empty.
3. **flexlibs2 fork installed**: `pip install -e D:/Github/_Projects/_LEX/flexlibs2` (see [CLAUDE.md](../../CLAUDE.md) "flexlibs2 fork dependency").
4. **MCP server available**: `flextools-mcp` MUST be reachable for the verification probes.

## Scenario A — Empty target, full Phase 3a→3b→3c chain

**Setup**: Fresh-restored target.

**Run**:
```python
# Through Lib/api.py — the UI-facing entry
api.initialize_run("Ejagham Mini", "Ejagham Full GT-Test")
api.bind_target_writeable(modifyAllowed=True)
plan = api.compute_preview(selection=Selection.all_phase3_categories())
report = api.execute_move(plan)
```

**Expected outcome**:
- Phase 3a categories: ~30-50 actions (phonemes + NCs + envs + phon rules + strata) per [005 quickstart](../005-phonology-block/quickstart.md).
- Phase 3b categories: ~10-30 actions (POS + inflection features + custom-field detect-only + variant types + complex form types + ~5 custom semantic domains).
- Phase 3c categories:
  - `AFFIXES`: ~88 affix LexEntries (T012 inventory; was ~13 in Verb-only subset (Ejagham Mini full affix surface) with full owned-child closure (senses + MSAs + allomorphs + examples + pronunciations + etymologies + entry-refs).
  - `SLOTS`: 9 slots across 6 POSes (T012 inventory) that have them.
  - `AFFIX_TEMPLATES`: 7 templates with `PrefixSlotsRS`/`SuffixSlotsRS` wired.
  - 17.1 sub-pass: up to 83 MoInflAffMsas wired to slots (T012 inventory) (Phase 0 verb-vertical's 12/13 case is a Verb-only subset).
  - `STEMS`: 164 stem LexEntries (T012 inventory) with full owned-child closure + sense-to-semantic-domain wiring + MSA-to-stratum wiring.
  - `ADHOC_COMPOUND_RULES`: per probe-derived count (deferred to Phase 0 implementation).
  - Post-pass A: per source EntryRef inventory.
- Total wall-clock < 30 s (SC-301 bounds Phase 3c slice alone at < 10s; full chain estimated < 30s).
- Zero `Skip(NEEDS_MANUAL)` if all compound-rule subclasses are within `{MoEndoCompound, MoExoCompound}` set surfaced by probe.

## Scenario B — Phase 3c re-run on populated target (FR-307 idempotency)

**Setup**: Target with Scenario A's Phase 3c outputs already applied.

**Run**: Same as Scenario A.

**Expected outcome**:
- All Phase 3c categories produce skips: `ALREADY_PRESENT_BY_GUID` for entries/senses/slots/templates/compound-rules (GUID-preserved); `identity_remap` resolution skips for MSAs/allomorphs (cross-run identity holds because source guids are stable).
- Zero new actions (`RunReport.added_count == 0`).
- 17.1 sub-pass: zero net writes (idempotency invariant from msa-slot-wiring contract).
- Post-pass A: zero net writes (idempotency invariant from post-pass-a contract).

## Scenario C — Phase 1 overwrite path

**Setup**: Target with Scenario A's Phase 3c outputs. Edit one affix entry's gloss on the source side (or simulate via fake LCM surface).

**Run**:
```python
plan = api.compute_preview(
    selection=Selection(categories={GrammarCategory.AFFIXES}),
    enable_overwrite=True,
)
report = api.execute_move(plan)
```

**Expected outcome**:
- 1 `Overwrite` action on the edited affix entry's sense.
- Merge residue tag landed on `LiftResidue` per Phase 1 FR-105 / FR-106.
- Identity_remap unchanged for MSAs/allomorphs (same source guids resolve to same target objects).

## Scenario D — Phase 2 interactive merge path

**Setup**: Same as Scenario C but with conflicting fields (different gloss on source vs target for the same affix entry sense).

**Run**:
```python
plan = api.compute_preview(
    selection=Selection(categories={GrammarCategory.AFFIXES, GrammarCategory.STEMS}),
    enable_overwrite=False,
)
conflicts = api.detect_conflicts(plan)
# In live mode, ConflictDialog renders; here, FakeResolver picks TAKE_SOURCE for every prompt
decisions = FakeResolver(default="TAKE_SOURCE").resolve_all(conflicts)
report = api.execute_move(plan, merge_decisions=decisions)
```

**Expected outcome**:
- N `ConflictPrompt`s, one per conflicting field on each affected entry/sense.
- All conflicts resolved per FakeResolver policy.
- Run report records merge decisions and applies them.

## Scenario E — Preview-only (modifyAllowed=False)

**Setup**: Fresh-restored target.

**Run**:
```python
api.initialize_run("Ejagham Mini", "Ejagham Full GT-Test")
api.bind_target_writeable(modifyAllowed=False)
plan = api.compute_preview(selection=Selection.all_phase3c_categories())
# No execute_move call
```

**Expected outcome**:
- Plan produced with all Phase 3c PlannedActions enumerated.
- `plan.msa_slot_bindings` populated (preview-time side effect).
- `plan.lexentry_ref_bindings` populated (preview-time side effect).
- Zero LCM writes — `Cache.UnitOfWorkService.IsDirty == False` after preview.
- Constitution Principle III satisfied.

## Scenario F — Phase 0 verb-vertical re-run after Phase 3c (SC-303)

**Setup**: Target with Scenario A's Phase 3c outputs.

**Run**: Phase 0 verb-vertical entrypoint as documented in Phase 0 spec ([001-phase0-additive-transfer](../001-phase0-additive-transfer/)).

**Expected outcome**:
- All ~67 Phase 0 actions emit `Skip(ALREADY_PRESENT_BY_GUID)`. Phase 0 is retired-in-place per FR-334.
- `RunReport.added_count == 0`.
- Verifies the universal collision-guard suffices for the transition window.

## Verification log location

Per Phase 3a/3b precedent, raw MCP probe + run output goes to `specs/007-affixes-stems/verification-log.md` (created during Phase 0 implementation, not by `/speckit-plan`).

## Reference: Ejagham Mini Phase 3c inventory (Phase 0 carry-over)

From [STATUS.md](../../STATUS.md) Layer 3 inventory:

| Inventory | Count |
|---|---|
| Total LexEntries | 252 |
| Affix entries (`IsAffixType == True`) | **88** |
| Stem entries (`IsAffixType == False`) | **164** |
| Allomorphs (all entries; lexeme form + alternates) | **293** |
| Distinct PhEnvironments referenced (Phase 3a already-transferred) | 2 |
| MSAs (full project, T012) | **247** (83 MoInflAffMsa + 164 MoStemMsa; no Deriv/Unclassified) |
| Slots (across 6 POSes that carry them) | **9** |
| Templates (across 6 POSes that carry them) | **7** |
| Compound rules | **0** (US4 live-verification gap; synthetic fixtures only) |
| Ad-hoc prohibitions | **0** (US4 live-verification gap) |
| EntryRefs with ComponentLexemesRS | **6** (post-pass A surface) |
| EntryRefs with PrimaryLexemesRS | **0** |

**Deferred to Phase 0 implementation probe** (T004-T010 of future tasks.md):

- Compound rule count.
- Ad-hoc prohibition count.
- Stem MSA inventory (MoStemMsa per stem entry, with StratumRA distribution).
- EntryRef inventory across all entries.
- Slot inventory for non-Verb POSes (Phase 0 only walked Verb).

# Phase 3c Data Model: Affixes / Stems / Templates Block

**Date**: 2026-06-22
**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)
**Research**: [research.md](research.md)

This document catalogs the LCM types, ownership shape, reference closure, and identity scheme for each of the five new Phase 3c categories. Identity, residue, and GUID-preservation policies inherit from Phase 0/1/2/3a — only the per-category specifics are recorded here.

## E1 — `GrammarCategory` enum extensions

| Member | Source collection | Owner | Item type |
|---|---|---|---|
| `AFFIXES` | `LangProject.LexDbOA.EntriesOC` (filtered: `e.LexemeFormOA.MorphTypeRA.IsAffixType == True`) | `ILexDb` | `ILexEntry` |
| `ADHOC_COMPOUND_RULES` | `LangProject.MorphologicalDataOA.AdhocCoProhibitionsOC` ∪ `LangProject.MorphologicalDataOA.CompoundRulesOS` | `IMoMorphData` | `IMoAdhocProhibition` ∪ `IMoCompoundRule` (abstract base; dispatch on subclass) |
| `SLOTS` | for each POS in target: `IPartOfSpeech.AffixSlotsOC` | `IPartOfSpeech` | `IMoInflAffixSlot` |
| `AFFIX_TEMPLATES` | for each POS in target: `IPartOfSpeech.AffixTemplatesOS` | `IPartOfSpeech` | `IMoInflAffixTemplate` |
| `STEMS` | `LangProject.LexDbOA.EntriesOC` (filtered: `e.LexemeFormOA.MorphTypeRA.IsAffixType == False`) | `ILexDb` | `ILexEntry` |

## E2 — Affix LexEntry closure (owned children)

For each affix `ILexEntry`, the planner walks the following owned-child tree as a unit. All owned children are created atomically with the parent.

| Path | LCM type | Cardinality | Notes |
|---|---|---|---|
| `entry.LexemeFormOA` | `IMoAffixAllomorph` | 0..1 (Owning Atomic) | The primary form. `Skip(DEPENDENCY_UNRESOLVED)` on parent if absent. |
| `entry.AlternateFormsOS` | `IMoForm` (sequence) | 0..N | Alternate allomorphs. Subclass dispatch (see E3). |
| `entry.SensesOS` | `ILexSense` (sequence) | 0..N | Each sense walks its own owned subtree. |
| `entry.SensesOS[i].ExamplesOS` | `ILexExampleSentence` | 0..N | Per-sense. |
| `entry.SensesOS[i].MorphoSyntaxAnalysisRA` | `IMoMorphSynAnalysis` | 0..1 (Reference, but MSA owned by entry) | Wired to MSA in `entry.MorphoSyntaxAnalysesOC`. |
| `entry.MorphoSyntaxAnalysesOC` | `IMoMorphSynAnalysis` (collection) | 0..N | Subclass dispatch (see E4). |
| `entry.PronunciationsOS` | `ILexPronunciation` | 0..N | Per-entry. |
| `entry.EtymologyOS` | `ILexEtymology` | 0..N | Per-entry. |
| `entry.EntryRefsOS` | `ILexEntryRef` | 0..N | `ComponentLexemesRS` + `PrimaryLexemesRS` deferred to post-pass A (E7). |

## E3 — Allomorph subclass dispatch

| ClassName | Factory | Owner attach |
|---|---|---|
| `MoAffixAllomorph` | `IMoAffixAllomorphFactory.Create()` — no Guid overload | `entry.LexemeFormOA = allo` OR `entry.AlternateFormsOS.Add(allo)` |
| `MoStemAllomorph` | `IMoStemAllomorphFactory.Create()` — no Guid overload | same |
| `MoAffixProcess` | (probe-pending) | (probe-pending) |

Identity for no-Guid-overload allomorphs: `identity_remap` per FR-303 (Phase 1 inheritance).

## E4 — MSA subclass dispatch

| ClassName | Factory / Operation | Identity |
|---|---|---|
| `MoInflAffMsa` | `MSAOperations.CreateInflAff(sense, pos, slots=[])` — Phase 0 verified | `identity_remap` (no Guid overload) |
| `MoDerivAffMsa` | `MSAOperations.CreateDerivAff(sense, from_pos, to_pos)` — probe-pending | `identity_remap` |
| `MoUnclassifiedAffixMsa` | `MSAOperations.CreateUnclassified(sense, pos)` — probe-pending | `identity_remap` |
| `MoStemMsa` | `MSAOperations.CreateStem(sense, pos)` — probe-pending | `identity_remap`. `StratumRA` resolves to Phase 3a Strata. |

**MSA → Slot references** (for `MoInflAffMsa` only): left empty at creation time. Populated by 17.1 sub-pass (E5).

**MSA → Stratum references** (for `MoStemMsa` only): resolved to target Strata by GUID lookup; Phase 3a transferred Strata are stable in target before Phase 3c begins (Phase 3 ordering memo step 5b precedes 14).

## E5 — 17.1 MSA-Slot wiring sub-pass

**In-plan binding**: `RunPlan.msa_slot_bindings: dict[Guid, list[Guid]]`.

| Step | Action |
|---|---|
| `AFFIXES.plan_action` | For each affix MSA with non-empty source `SlotsRC`, stash `(msa_guid, [src_slot_guid, ...])` in `plan.msa_slot_bindings`. |
| `AFFIX_TEMPLATES.execute_action` | Tail block (after all template writes): for each `(msa_guid, slot_guids)` pair in `plan.msa_slot_bindings`, resolve MSA in target by guid + identity_remap, resolve each slot in target by guid, write `msa.SlotsRC.Add(slot)`. |

**Skip conditions**:
- MSA not found in target → `Skip(DEPENDENCY_UNRESOLVED)` on the MSA (with detail "msa_guid={...} not in target after affix transfer").
- Slot not found in target → `Skip(DEPENDENCY_UNRESOLVED)` on the MSA (with detail "slot_guid={...} not in target after slot transfer").
- Empty source `SlotsRC` → no binding stashed; MSA stays unbound (matches Phase 0 Layer 3's 1-unbound-affix case for Ejagham Mini's `ro~-`).

## E6 — Compound rule + ad-hoc-prohibition subclass dispatch

**Corrected per T008/T009 MCP probes — see [probe-results.md](probe-results.md).**

### Compound rules

Base `IMoCompoundRule` (5 inherited properties): `Name` (IMultiUnicode), `Description` (IMultiString — Carrier B residue), `Disabled` (bool), `StratumRA` (→ `IMoStratum`, Phase 3a dependency per FR-336), `ToProdRestrictRC` (→ `ICmPossibility` ref collection).

| ClassName | Factory / wrapper | Subclass-specific OWNED MSAs (write in `execute_action`) |
|---|---|---|
| `MoEndoCompound` | `MorphRuleOperations.CreateCompoundRule(name, endocentric=True, description=None)` (preferred); ServiceLocator fallback if needed | `HeadLast` (bool) + `OverridingMsaOA` (owned `IMoStemMsa`, optional — walk recursively if non-null and clone via identity_remap) |
| `MoExoCompound` | `MorphRuleOperations.CreateCompoundRule(name, endocentric=False, description=None)` | `ToMsaOA` (owned `IMoStemMsa`, mandatory — walk recursively and clone via identity_remap) |
| Unknown | (no factory dispatch path) | `Skip(NEEDS_MANUAL)` per FR-341 |

**No `LeftMsaOA`/`RightMsaOA`**: the LCM model does NOT carry left/right operand MSAs on the rule. The morphological parser derives the operands at parse time from the morpheme-template chain; the rule stores only the result MSA (Endo: `OverridingMsaOA` when overriding; Exo: mandatory `ToMsaOA`) plus head selection (`HeadLast` for Endo) plus stratum scope (`StratumRA`).

### Ad-hoc prohibitions

Base `IMoAdhocProhib` (2 inherited properties): `Adjacency` (int), `Disabled` (bool). No residue carrier on the base.

| ClassName | Factory | Subclass-specific fields | Residue |
|---|---|---|---|
| `MoAdhocProhibGr` (GROUP) | `IMoAdhocProhibGrFactory.Create(Guid)` (ServiceLocator fallback) | `Name`, `Description` (IMultiString — Carrier B), **`MembersOC` (owned collection)** of nested `IMoAdhocProhib` atoms — group OWNS its members, recursive walk + create | Carrier B on `Description` |
| `MoAlloAdhocProhib` (ATOMIC, allomorph-based) | `IMoAlloAdhocProhibFactory.Create(Guid)` (ServiceLocator fallback) | `AllomorphsRS` (ordered ref seq of `IMoForm`) + `FirstAllomorphRA` (single `IMoForm` ref) + `RestOfAllosRS` (ordered ref seq of `IMoForm`) — wire via `identity_remap` to US1 allomorphs | **NONE** — skip residue (atomic prohibitions carry no Description/LiftResidue accessor) |
| `MoMorphAdhocProhib` (ATOMIC, morpheme-based) | `IMoMorphAdhocProhibFactory.Create(Guid)` (ServiceLocator fallback) | `MorphemesRS` (ordered ref seq of `IMoMorphSynAnalysis`) + `FirstMorphemeRA` (single `IMoMorphSynAnalysis` ref) + `RestOfMorphsRS` (ordered ref seq of `IMoMorphSynAnalysis`) — wire via `identity_remap` to US1 MSAs | **NONE** — skip residue |
| Unknown | — | — | `Skip(NEEDS_MANUAL)` |

**`MembersOC` vs `MembersRS`**: critical model correction — the LCM model stores prohibition group members as **owned** children (`MembersOC`), not as references (`MembersRS`). Each atom belongs to exactly one parent group. US4 `execute_action` recursively creates atomic prohibitions as owned children of the new group rather than wiring references.

**Residue posture for atomic ad-hoc prohibitions**: atomic prohibitions carry no `Description` accessor. Group-owned atomics inherit their parent group's `GT|<run_id>|...` residue trail by ownership. Top-level atomic prohibitions (rare in practice — Ejagham Mini has 0) emit a run-report info-level line citing the source GUID and the run_id, no residue on the LCM object itself.

All compound + ad-hoc rules' references to affix LexEntries / MSAs resolve via `identity_remap` (FR-337) where source-GUID differs from target-GUID.

## E7 — LexEntryRef post-pass A

**In-plan binding**: `RunPlan.lexentry_ref_bindings: dict[Guid, dict[str, list[Guid]]]`.

| Step | Action |
|---|---|
| `AFFIXES.plan_action` + `STEMS.plan_action` | For each entry with non-empty `EntryRefsOS[i].ComponentLexemesRS` / `PrimaryLexemesRS`, stash `{src_entry_guid: {"ComponentLexemesRS": [...], "PrimaryLexemesRS": [...]}}` in `plan.lexentry_ref_bindings`. |
| `STEMS.execute_action` | Tail block (after all stem writes): for each binding, resolve target entry by GUID, resolve each referenced lexeme by (a) in-plan creation list or (b) target-by-GUID lookup, write the RS sequence in source order. |

**Skip conditions** (FR-340):
- Referenced lexeme resolves to neither in-plan nor target-by-GUID → `Skip(DEPENDENCY_UNRESOLVED)` on the EntryRef. No fingerprint fallback. No persistent cross-phase state.

## E8 — Identity & GUID preservation matrix

| Category | Identity | GUID-preserved? |
|---|---|---|
| `AFFIXES` (LexEntry parent) | Guid (factory `Create(Guid, ILexDb)`) | Yes |
| `AFFIXES` (Senses) | Guid (factory `Create(Guid, ILexEntry)`) | Yes |
| `AFFIXES` (MSAs) | `identity_remap` | No — new guid per FR-303 |
| `AFFIXES` (Allomorphs) | `identity_remap` | No |
| `AFFIXES` (Examples/Pronunciations/Etymologies/EntryRefs) | (probe-pending) | (probe-pending) |
| `ADHOC_COMPOUND_RULES` | Guid (per-subclass factory) | Yes |
| `SLOTS` | Guid (`Create(Guid)`) | Yes — verified Phase 0 |
| `AFFIX_TEMPLATES` | Guid (`Create(Guid)`) | Yes — verified Phase 0 |
| `STEMS` | same as `AFFIXES` row-by-row | same |

## E9 — Residue carrier matrix

| LCM type | Carrier | Field |
|---|---|---|
| `ILexEntry` | A | `LiftResidue` (Unicode single string) |
| `ILexSense` | A | `LiftResidue` |
| `IMoMorphSynAnalysis` | A | `LiftResidue` |
| `IMoForm` (all allomorph subclasses) | A | `LiftResidue` |
| `IMoInflAffixSlot` | B | `Description` (multistring) |
| `IMoInflAffixTemplate` | B | `Description` (multistring) |
| `IMoEndoCompound` / `IMoExoCompound` | B | `Description` (inherited from `IMoCompoundRule`) — confirmed T008 |
| `IMoAdhocProhibGr` (group) | B | `Description` (multistring) — confirmed T009 |
| `IMoAlloAdhocProhib` / `IMoMorphAdhocProhib` (atomic) | **none** | no carrier accessor; skip residue, emit run-report line only — confirmed T009 |

## E10 — Skip reason matrix (Phase 3c-specific)

| Reason | Origin |
|---|---|
| `ALREADY_PRESENT_BY_GUID` | `_create_with_guid` collision guard (FR-334; universal). |
| `DEPENDENCY_UNRESOLVED` | FR-332 (missing LexemeForm/MorphType), FR-335 (missing semantic domain), FR-336 (missing Stratum), FR-340 (unresolved EntryRef component), 17.1 (unresolved slot/MSA at wire time). |
| `NEEDS_MANUAL` | FR-341 (unknown compound rule subclass; unknown ad-hoc subclass). |
| `GOLD_INVIOLABLE` | Not applicable to Phase 3c — no FW catalog at affix/stem/template/slot/rule level. |

## E11 — RunPlan extensions

```python
@dataclass
class RunPlan:
    # ... existing fields ...
    msa_slot_bindings: dict[Guid, list[Guid]] = field(default_factory=dict)
    lexentry_ref_bindings: dict[Guid, dict[str, list[Guid]]] = field(default_factory=dict)
```

Both fields are ephemeral, plan-scoped, and consumed by their respective tail-block executors. They are NOT serialised to the run snapshot artifact and NOT persisted across runs.

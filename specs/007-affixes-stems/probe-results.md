# Phase 3c MCP Probe Results

**Date**: 2026-06-22 (T006-T011 executed against `Ejagham Mini` via flextools-mcp; T012 inventory probe pending)
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

This document records the live FlexTools-MCP probe outputs that validate (and substantially correct) the assumptions in [research.md](research.md). Each section below corresponds to a probe task in [tasks.md](tasks.md).

**Major spec corrections surfaced (see "Spec corrections required" at end)**:

- Compound rules: **no `LeftMsaOA`/`RightMsaOA`** in LCM — model assumption invalid.
- Ad-hoc prohibitions: **3-way subclass split**, not 2-way. Group OWNS members via `MembersOC`, not `MembersRS`.
- MSA wrapper name: **`CreateUnclassifiedAffix`**, not `CreateUnclassified`.
- Affix template carries **5 slot ref sequences** (`PrefixSlotsRS`, `SuffixSlotsRS`, `EncliticSlotsRS`, `ProcliticSlotsRS`, `SlotsRS`) plus `Final` bool and `StratumRA` — spec assumed only 2.
- Atomic ad-hoc prohibitions (`MoAlloAdhocProhib`, `MoMorphAdhocProhib`) carry **NO residue accessor**.

---

## T006 — LexEntry owned-child factories

| Factory | Catalog state | Create signature (or fallback) |
|---|---|---|
| `ILexExampleSentenceFactory` | 1 method | `Create(Guid guid, ILexSense owner)` — **Guid-preserved** |
| `ILexPronunciationFactory` | 0 methods (MCP stub) | **ServiceLocator fallback**: `Cache.ServiceLocator.GetInstance[ILexPronunciationFactory]().Create(...)` |
| `ILexEtymologyFactory` | 0 methods | **ServiceLocator fallback** |
| `ILexEntryRefFactory` | 0 methods | **ServiceLocator fallback** |

**Decision**: `ILexExampleSentence` uses the Guid-preserving create. The other three use the ServiceLocator fallback path identical to Phase 3b's `ILexEntryTypeFactory` pattern (research.md R3). Phase 3c implementation must probe each non-`Create(Guid)` factory's signature at run-write time (deferred to US1 T019 implementation; `_create_with_guid` fallback inside `_walk_lex_entry_closure` per T016 will surface the actual signature).

**Residue choice for LexEntry**: `LiftResidue` (String, writable). Consistent with Phase 0 / STATUS.md `_apply_carrier_a` helper. NOT `ImportResidue` (ITsString, less convenient cross-WS handling). The Phase 0 helper is the reference.

---

## T007 — MSA subclass operations (`MSAOperations`)

flexicon wrappers in `Lexicon/MSAOperations`, all confirmed:

| Method | Signature | Returns | Phase 3c use |
|---|---|---|---|
| `CreateInflAff` | `(sense, pos, slots=None)` | `IMoInflAffMsa` | US1 affix MSA creation. **`slots` parameter exists** — but Phase 3c US1 leaves it `None` (FR-333: defer `SlotsRC` to 17.1 sub-pass) |
| `CreateDerivAff` | `(sense, from_pos, to_pos)` | `IMoDerivAffMsa` | US1 derivational affix MSA |
| `CreateStem` | `(sense, pos)` | `IMoStemMsa` | US3 stem MSA |
| `CreateUnclassifiedAffix` | `(sense, pos)` | `IMoUnclassifiedAffixMsa` | US1 unclassified-affix MSA. **Note name**: `CreateUnclassifiedAffix`, NOT `CreateUnclassified` as research.md R3 assumed. |

**Identity**: None of these wrappers take a Guid parameter. All MSA subclasses use `identity_remap` per FR-303 (matches Phase 0 Layer 3 precedent).

**`MoStemMsa.StratumRA`** wiring (FR-336): inherited from the base interface — the wrapper does not set it. Phase 3c US3 must write `msa.StratumRA = target_stratum` in `execute_action` after `CreateStem`. Stratum resolves via GUID lookup against Phase 3a-transferred Strata.

**`MoInflAffMsa.SlotsRC`** wiring (FR-333, 17.1 sub-pass): the `slots` parameter on `CreateInflAff` is convenient but DOES NOT fit Phase 3c's deferred-wiring contract. US1 calls `CreateInflAff(sense, pos, slots=None)`; the 17.1 tail block on `AFFIX_TEMPLATES.execute_action` writes `target_msa.SlotsRC.Add(slot)` per slot from `plan.msa_slot_bindings`.

---

## T008 — Compound rule subclass factories + accessor inventory

### Factories (both ServiceLocator fallback)

| Factory | Catalog state | Path |
|---|---|---|
| `IMoEndoCompoundFactory` | 0 methods | `Cache.ServiceLocator.GetInstance[IMoEndoCompoundFactory]().Create(...)` |
| `IMoExoCompoundFactory` | 0 methods | `Cache.ServiceLocator.GetInstance[IMoExoCompoundFactory]().Create(...)` |

Exact `Create(...)` signature must be probed at write-implementation time (US4 T059). Likely `Create(Guid)` per LCM convention; verify by reading similar Phase 0/3a factory uses.

### Critical model correction: NO `LeftMsaOA`/`RightMsaOA`

The R7 assumption that `IMoCompoundRule` (or its subclasses) carry `LeftMsaOA` + `RightMsaOA` fields **is invalid**. Live catalog inventory:

**`IMoCompoundRule` (abstract base) — 5 properties**:
- `Description`: IMultiString — **Carrier B residue target** (replaces "(probe-pending)" in data-model E9)
- `Disabled`: Boolean
- `Name`: IMultiUnicode
- `StratumRA`: → `IMoStratum` (single ref) — **Phase 3a Strata dependency, FR-336 also applies here**
- `ToProdRestrictRC`: → `ICmPossibility` (ref collection) — productivity-restriction tags

**`IMoEndoCompound` (concrete, endocentric) — adds 2 properties**:
- `HeadLast`: Boolean — whether the head is on the right
- `OverridingMsaOA`: → `IMoStemMsa` (single owned) — optional MSA override for the compound

**`IMoExoCompound` (concrete, exocentric) — adds 1 property**:
- `ToMsaOA`: → `IMoStemMsa` (single owned) — the exocentric output MSA

### Compound rule semantics (corrected understanding)

The compound rule doesn't store Left/Right MSAs because the operands are derived by the morphological parser at parse time from the morpheme-template chain. The rule stores only the *result* MSA (Endo via `OverridingMsaOA` when overriding, Exo via mandatory `ToMsaOA`) plus head selection (`HeadLast` for Endo) plus stratum scope (`StratumRA`).

### Updated compound subclass dispatch (FR-341 correction)

| ClassName | Factory | Subclass-specific OWNED MSAs | Refs to wire |
|---|---|---|---|
| `MoEndoCompound` | `IMoEndoCompoundFactory.Create(Guid)` (probe T059) | `OverridingMsaOA` (when source has one — walk recursively; copy as owned MoStemMsa via identity_remap) | base: `StratumRA` + `ToProdRestrictRC` |
| `MoExoCompound` | `IMoExoCompoundFactory.Create(Guid)` (probe T059) | `ToMsaOA` (always — exocentric requires it; walk recursively) | base: `StratumRA` + `ToProdRestrictRC` |
| Unknown subclass | — | — | `Skip(NEEDS_MANUAL)` per FR-341 |

### Residue carrier choice (analyze C3 closed)

**`IMoCompoundRule.Description` (IMultiString) → Carrier B** for both Endo and Exo subclasses. No probe-pending branch remains; T060 ships with `apply_residue` writing to `Description` via the standard Carrier B helper.

---

## T009 — Ad-hoc prohibition subclass factories + accessor inventory

### Critical model correction: 3-way subclass split

The R7 assumption of "atom vs group" is invalid. The actual LCM hierarchy:

**`IMoAdhocProhib` (abstract base) — 2 properties**:
- `Adjacency`: Int32 — distance constraint
- `Disabled`: Boolean

**`IMoAdhocProhibGr` (concrete, GROUP) — adds 3 properties**:
- `Description`: IMultiString — **Carrier B residue target**
- `MembersOC`: **Owned collection** of `IMoAdhocProhib` (children) — **NOT `MembersRS`** as research.md R7 / data-model E6 assumed
- `Name`: IMultiUnicode

**`IMoAlloAdhocProhib` (concrete, ATOMIC, allomorph-based) — adds 3 properties**:
- `AllomorphsRS`: ordered ref sequence of `IMoForm` (the prohibited allomorph chain)
- `FirstAllomorphRA`: single ref of `IMoForm` (head of the chain)
- `RestOfAllosRS`: ordered ref sequence of `IMoForm` (tail)
- **NO `Description`, NO `LiftResidue`, NO `ImportResidue`** — atomic prohibitions have no residue carrier

**`IMoMorphAdhocProhib` (concrete, ATOMIC, morpheme-based) — adds 3 properties**:
- `MorphemesRS`: ordered ref sequence of `IMoMorphSynAnalysis`
- `FirstMorphemeRA`: single ref of `IMoMorphSynAnalysis`
- `RestOfMorphsRS`: ordered ref sequence of `IMoMorphSynAnalysis`
- **NO residue carrier**

### Updated ad-hoc subclass dispatch

| ClassName | Factory | Concrete owns | Refs to wire (via identity_remap per FR-337) | Residue |
|---|---|---|---|---|
| `MoAdhocProhibGr` | `IMoAdhocProhibGrFactory.Create(Guid)` (catalog 0 methods → ServiceLocator) | `MembersOC` (atomic children created recursively) | base: `Adjacency`, `Disabled` | Carrier B on `Description` |
| `MoAlloAdhocProhib` | `IMoAlloAdhocProhibFactory.Create(Guid)` (catalog 0 methods → ServiceLocator) | (none) | `AllomorphsRS`, `FirstAllomorphRA`, `RestOfAllosRS` (all → `IMoForm` allomorphs from US1) | **none** — skip residue |
| `MoMorphAdhocProhib` | `IMoMorphAdhocProhibFactory.Create(Guid)` (catalog 0 methods → ServiceLocator) | (none) | `MorphemesRS`, `FirstMorphemeRA`, `RestOfMorphsRS` (all → `IMoMorphSynAnalysis` from US1) | **none** — skip residue |
| Unknown | — | — | — | `Skip(NEEDS_MANUAL)` |

### Residue posture for atomic ad-hoc prohibitions (NEW spec call needed)

Atomic prohibitions (`MoAlloAdhocProhib`, `MoMorphAdhocProhib`) cannot carry a residue tag on themselves. Three options:

1. **Skip residue silently** — the parent group's residue (if any) provides the run_id linkage for grouped atomics; top-level atomics emit a run-report-only trace via `RunReport.identity_remap`.
2. **Attach residue to parent group** — works for grouped atomics; top-level atomics still have no carrier.
3. **Skip the entire atomic transfer with `Skip(NEEDS_MANUAL)`** — defer all top-level atomic prohibitions to manual handling.

**Recommended**: Option 1. Top-level atomic prohibitions are rare in practice (typical FLEx projects group them under `MoAdhocProhibGr`); Phase 3c records them via `identity_remap` and surfaces an info-level run-report line. Defer Option 2/3 escalation until Ejagham Mini inventory (T012) shows non-trivial top-level atomic counts.

---

## T010 — Affix template + slot accessor inventory

### `IMoInflAffixTemplate` — 11 properties (spec assumed 2 slot ref sequences; actual is 5)

| Property | Kind | Type | Phase 3c handling |
|---|---|---|---|
| `Description` | IMultiString | residue carrier B | Standard Carrier B write |
| `Disabled` | Boolean | property | Copy from source |
| `Final` | Boolean | property | Copy from source (whether template is the final one in the stratum) |
| `Name` | IMultiUnicode | property | Copy from source |
| `PrefixSlotsRS` | ordered ref sequence | → `IMoInflAffixSlot` | Wire via slot-GUID lookup against Phase 3c US2 transfers |
| `SuffixSlotsRS` | ordered ref sequence | → `IMoInflAffixSlot` | Same |
| `EncliticSlotsRS` | **(new in spec)** ordered ref sequence | → `IMoInflAffixSlot` | **Same** — spec/data-model E2 must add this |
| `ProcliticSlotsRS` | **(new in spec)** ordered ref sequence | → `IMoInflAffixSlot` | **Same** |
| `SlotsRS` | **(new in spec)** ordered ref sequence | → `IMoInflAffixSlot` | **Same** — general slot list (likely union or unconstrained) |
| `RegionOA` | single owned | → ? | Walk and clone if non-null; check accessor type at write time |
| `StratumRA` | single ref | → `IMoStratum` | Wire to Phase 3a-transferred Stratum via GUID lookup (matches `IMoCompoundRule.StratumRA` pattern) |

**Spec/data-model correction needed**: Affix template's slot-ref surface is 5 sequences, not 2. T030 (`affix_templates.execute_action`) must wire all 5. The 17.1 sub-pass (T031) MSA→Slot binding still works against any of these slot references because all 5 sequences ultimately point at `IMoInflAffixSlot` instances that 17.1 looks up by GUID.

### `IPartOfSpeech` — confirms data-model E1

| Property | Kind | Matches spec |
|---|---|---|
| `AffixSlotsOC` | Unordered owned collection | ✓ Slots owned by POS (US2 T029) |
| `AffixTemplatesOS` | Ordered owned sequence | ✓ Templates owned by POS (US2 T030) |
| `InflectionClassesOC` | Unordered owned collection | (Phase 3b — already handled) |
| `StemNamesOC` | Unordered owned collection | (Phase 3b — already handled) |
| `BearableFeaturesRC`, `InflectableFeatsRC`, `DefaultInflectionClassRA`, ... | various | Phase 3b territory |

### `IMoInflAffixSlot` — Carrier B residue

| Property | Kind | Phase 3c handling |
|---|---|---|
| `Name` | IMultiUnicode | Copy from source |
| `Description` | IMultiString | Carrier B residue write |
| `Optional` | Boolean | Copy from source |
| `Affixes` | derived IEnumerable | not copied (computed view) |
| `OtherInflectionalAffixLexEntries` | derived IEnumerable | not copied (computed view) |

T029 (`slots.execute_action`) writes Name + Description + Optional via `BaseOperations.ApplySyncableProperties`; the two derived collections are excluded.

---

## T011 — MorphologicalData accessors

`IMoMorphData` — confirms data-model E1 owner attach points:

| Property | Kind | Owner attach pattern |
|---|---|---|
| `AdhocCoProhibitionsOC` | Unordered owned collection | `.Add(prohib)` |
| `CompoundRulesOS` | Ordered owned sequence | `.Append(rule)` (preserve source order) |
| `StrataOS` | Ordered owned sequence | (Phase 3a — already handled) |
| `ParserParameters`, `ProdRestrictOA`, `TestSetsOC`, `GlossSystemOA`, `ActiveParser`, `AnalyzingAgentsRC` | various | Out of Phase 3c scope |

**Conclusion**: T056 (`adhoc_compound_rules.enumerate_source`) concatenates `source.MorphologicalDataOA.AdhocCoProhibitionsOC` ∪ `source.MorphologicalDataOA.CompoundRulesOS` and dispatches on `ClassName` per the corrected subclass tables in T008/T009 above.

---

## T012 — Ejagham Mini inventory (executed 2026-06-22)

Inventory probe via `flextools_run_module` walking `project.LexEntry.GetAll()` + `project.MorphRules.GetAllCompoundRules/AdhocCoProhibitions/AffixTemplates` + `project.POS.GetAll(recursive=True)`. Read-only certified by the runner (`is_certified_readonly=true, confidence=high`).

### Counts

| Surface | Count | Notes |
|---|---|---|
| Total LexEntries | 252 | matches STATUS.md baseline (Layer 3 inventory) |
| Affix entries (`IsAffixType==True`) | **88** | **STATUS.md's "13 verb-affix entries" was the Verb-only subset; the full affix count across all POSes is 88** |
| Stem entries (`IsAffixType==False`) | **164** | first time bulk-counted |
| Entries with `LexemeFormOA is None` | 0 | no degenerate entries |
| Entries with `MorphTypeRA is None` | 0 | no degenerate entries |
| Allomorphs (incl. lexeme form) | 293 | |
| MorphType distribution (top 4 by guid8) | d7f713e8=154, d7f713dd=50, d7f713db=38, d7f713e7=10 | 4 distinct morph types in use |
| EntryRefs with non-empty `ComponentLexemesRS` | **6** | tiny post-pass A surface in this corpus |
| EntryRefs with non-empty `PrimaryLexemesRS` | **0** | not exercised in Ejagham Mini |
| MSAs total | 247 | |
| MSA classes | `MoInflAffMsa: 83`, `MoStemMsa: 164` | **No `MoDerivAffMsa`, no `MoUnclassifiedAffixMsa`** in this corpus |
| **Compound rules** | **0** | US4 compound path cannot be live-verified against Ejagham Mini |
| **Ad-hoc prohibitions** | **0** | US4 ad-hoc path cannot be live-verified against Ejagham Mini |
| Affix templates | **7** | only `MoInflAffixTemplate` (no other template subclasses surfaced in catalog either) |
| POSes | 20 | 6 carry slots, 6 carry templates |
| Slots total (all POSes) | **9** | small surface |

### Structural takeaways

1. **MSA dispatch scope can shrink in MVP**. Phase 3c US1/US3 need only `MoInflAffMsa` + `MoStemMsa` paths to ship a working Ejagham Mini → Ejagham Full GT-Test transfer end-to-end. `MoDerivAffMsa` and `MoUnclassifiedAffixMsa` (and any future MSA subclass) can stay as `Skip(NEEDS_MANUAL)` stubs without breaking live verification. The spec stays correct (FR-341-style fail-loud posture extends to MSAs per T017 / T026), but the IMPLEMENTATION priority for US1 narrows to two subclasses for MVP completion.

2. **US4 (compound + ad-hoc) has NO live verification path against Ejagham Mini.** Both `CompoundRulesOS` and `AdhocCoProhibitionsOC` are empty. Three options:
   - **(a)** Author synthetic test fixtures only (unit tests T061-T066 cover this). Document the verification gap in `specs/007-affixes-stems/verification-log.md`. **Recommended** — matches Phase 3a US2 "strata" precedent (Phase 3a had zero strata in source, shipped with unit smoke + synthetic + deferred live).
   - **(b)** Locate a different source project that has compound rules + ad-hoc prohibitions and add it as a secondary verification target.
   - **(c)** Defer US4 entirely to a follow-up slice once such a source project exists.

3. **STATUS.md "13 verb-affix entries" was the Verb-only subset.** Phase 0 verb-vertical only walked Verb POSes; full Phase 3c affix transfer surface is ~7× larger (88 vs 13). SC-301 budget assumed ~250 affix+stem combined, which still bounds the project (252 total). The 17.1 sub-pass will fire for up to 83 MoInflAffMsas (not 12); update T041 integration test fixture accordingly.

4. **Post-pass A surface is tiny** — 6 EntryRefs across the whole project. Realistic test fixture: 1-3 component refs per fixture file is sufficient; integration assertions per T055 will verify all 6 wire correctly.

5. **Templates = 7, Slots = 9** — both smaller than spec quickstart estimates (~5/~25). 17.1 sub-pass should run in milliseconds. SC-301 wall-clock budget (< 10s for Phase 3c slice) trivially achievable.

6. **flexicon wrapper availability for US4 implementation**: `MorphRuleOperations.CreateCompoundRule(name, endocentric=True, description=None)` exists — US4 T059 should use this wrapper instead of the ServiceLocator fallback path. Same applies to `MorphRuleOperations.CreateAffixTemplate(pos, name, description=None)` for US2 T030. **Spec correction needed**: update FR-341 + research.md R7 + contracts/category-callbacks.md to reflect wrapper availability.

### Spec corrections required (additions to the original list)

14. **plan.md SC-301** (sizing): note that compound + ad-hoc rules are 0 in Ejagham Mini; live verification of US4 is gap-flagged.
15. **quickstart.md Scenario A**: revise inventory numbers — "~13 affix entries" → "~88 affix entries", "~25 slots" → "9 slots", "~5 templates" → "7 templates", "~239 stem entries" → "164 stem entries".
16. **research.md R7 + contracts/category-callbacks.md (US2 + US4)**: prefer `MorphRuleOperations.CreateAffixTemplate` and `CreateCompoundRule` flexicon wrappers over ServiceLocator fallback. Reduces T030 + T059 surface area.
17. **tasks.md T028 / T041 / T055**: update fixture expected counts to match the 88 / 7 / 9 / 6 numbers.
18. **tasks.md US4 (T056-T066)**: insert a note that live verification deferred / requires synthetic fixtures (Option (a)). Live MCP Scenario A (T073) skips the US4 sub-step against Ejagham Mini.

---

## Spec corrections required (post-probe)

The following spec / plan / data-model / contracts / tasks documents need updates to reflect the live LCM model:

### High-impact corrections

1. **FR-341** (spec.md): drop the "Atom vs Group" framing. Replace with 3-way subclass dispatch (`MoAdhocProhibGr` / `MoAlloAdhocProhib` / `MoMorphAdhocProhib`).
2. **FR-341** (spec.md): compound subclasses do NOT have `LeftMsaOA`/`RightMsaOA`. Replace with `OverridingMsaOA` (Endo, optional) / `ToMsaOA` (Exo, mandatory) plus inherited `StratumRA` + `ToProdRestrictRC`.
3. **FR-336** (spec.md): broaden — `StratumRA` resolution applies not just to `MoStemMsa` but also to `IMoCompoundRule.StratumRA` and `IMoInflAffixTemplate.StratumRA`. All three resolve to Phase 3a Strata.

### Mid-impact corrections

4. **data-model E2** (data-model.md): `IMoInflAffixTemplate` carries 5 slot ref sequences plus `Final` + `RegionOA` + `StratumRA`, not just `PrefixSlotsRS` + `SuffixSlotsRS`.
5. **data-model E6** (data-model.md): rewrite compound + ad-hoc subclass tables per the corrected hierarchies above. `MembersOC` (owned), not `MembersRS`.
6. **data-model E9** (data-model.md): commit residue carrier choices: compound rules + ad-hoc groups + slots + templates → Carrier B on `Description`. **Atomic ad-hoc prohibitions → no carrier** (skip-residue posture per "Residue posture for atomic ad-hoc prohibitions" above).
7. **contracts/category-callbacks.md**: `adhoc_compound_rules.dependencies` must yield `(STRATA, stratum.Guid)` for compound rules (was missing; FR-336 broadened).
8. **research.md R3**: rename `CreateUnclassified` → `CreateUnclassifiedAffix`.
9. **research.md R6**: same rename.

### Low-impact / informational

10. **tasks.md T030**: expand "wire `PrefixSlotsRS`/`SuffixSlotsRS` in source order" to "wire all 5 slot reference sequences (`PrefixSlotsRS`, `SuffixSlotsRS`, `EncliticSlotsRS`, `ProcliticSlotsRS`, `SlotsRS`) in source order".
11. **tasks.md T031**: 17.1 sub-pass is unchanged (still works against `plan.msa_slot_bindings` regardless of which template-slot-sequence the original source carried).
12. **tasks.md T034**: add coverage for template `Final` bool + `StratumRA` wiring.
13. **plan.md Performance Goals**: post-pass A + 17.1 budget assumed ~250 affix + stem entries; if T012 inventory reveals materially larger numbers, revisit SC-301.

These corrections land as a single follow-up commit before US1 implementation begins.

---

## Cross-cutting carry-overs from Phase 0/3a/3b

Probes T006-T011 do NOT re-cover the following already-validated surface:

- `ILexEntryFactory.Create(Guid, ILexDb)` — Guid-preserved. Phase 0 verified.
- `ILexSenseFactory.Create(Guid, ILexEntry)` — Guid-preserved. Phase 0 verified.
- `MSAOperations.CreateInflAff(sense, pos, slots=None)` — Phase 0 Layer 3 verified; Phase 3c uses `slots=None` to defer to 17.1.
- `IMoAffixAllomorphFactory.Create()` + owner attach — no Guid overload; `identity_remap` path established.
- `IPhEnvironmentFactory.Create(Guid)` — Phase 3a verified.
- `IMoInflAffixSlotFactory.Create(Guid)` — Phase 0 verified (4 slots under Verb).
- `IMoInflAffixTemplateFactory.Create(Guid)` — Phase 0 verified.
- `MorphType` cross-project resolution: GUIDs are FW-global, resolve in target by GUID without identity_remap (STATUS.md Phase 0.5).
- `BaseOperations.ApplySyncableProperties` — patched fork (CLAUDE.md flexicon fork dependency). Handles ITsString + object-ref-skip paths.
- `ILexEntry.LiftResidue` (String, writable) — Phase 0 Carrier A target. **Not `ImportResidue`** (also present; ITsString-typed, less convenient).

These are referenced as known-good in the Phase 3c implementation tasks; probes T006-T011 only chase the genuinely-new surface and surfaced the corrections above.

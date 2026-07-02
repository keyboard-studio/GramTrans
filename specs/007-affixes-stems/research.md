# Phase 3c Research: Affixes / Stems / Templates Block

**Date**: 2026-06-22
**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)

This document records the research decisions for the five new Phase 3c categories. Each decision is grounded in either a prior Phase 0-3b MCP probe artifact or a new probe (deferred to Phase 0 implementation per Spec "Next steps" item 4). MCP probes use the flextools-mcp catalog against `Ejagham Mini` (read) and `Ejagham Full GT-Test` (read/write rehearsal).

## R1 — Affix / Stem Partition

**Decision**: Per-entry, `entry.LexemeFormOA.MorphTypeRA.IsAffixType` (the LCM `IMoMorphType.IsAffixType` boolean).

**Rationale**: Locked by Clarifications Session 2026-06-22, codified in FR-332. Matches FLEx UI's affix/stem split and the lexicon export pipeline. Per-entry decision avoids the need for a separate enumeration of "affix morph types" or "stem morph types" — the partition is decided where each entry is encountered.

**Alternatives considered**:
- Whitelist of affix morph-type GUIDs from `LangProject.LexDbOA.MorphTypesOA` — rejected: requires per-project tuning and fragile against user-added morph types.
- `entry.LexemeFormOA.ClassName` startswith "MoAffix" — rejected: brittle to subclass renames; LCM already exposes `IsAffixType` for this exact partition.

**Edge cases**:
- `LexemeFormOA is None` → emit `Skip(DEPENDENCY_UNRESOLVED)` on the parent entry; FR-332 final clause covers this.
- `MorphTypeRA is None` → same skip.
- Cross-project MorphType resolution: morphtype GUIDs are FW-global (verified in Phase 0 Layer 3 — STATUS.md). The `MorphTypeRA` reference resolves in target by GUID without identity-remap.

## R2 — Affix LexEntry Closure (Owned Children)

**Decision**: For each affix LexEntry, the planner walks the same owned-child closure already established by Phase 0 Layer 3 work — senses (`SensesOS`), MSAs (`MorphoSyntaxAnalysesOC`), lexeme-form allomorph (`LexemeFormOA`), alternate forms (`AlternateFormsOS`), examples (`SensesOS[i].ExamplesOS`), pronunciations (`PronunciationsOS`), etymologies (`EtymologyOS`), and entry-refs (`EntryRefsOS`).

**Rationale**: Phase 0 Layer 3 already proved this closure works for the 13 Ejagham Mini verb-affix entries (STATUS.md: 59 added, 0 skipped, 0.387s wall-clock against an empty target). Phase 3c generalises the walk to all affix entries (not just `MSA.PartOfSpeechRA == Verb`) and reuses the same factory + create-with-guid pattern.

**Carry-over from Phase 0**:
- `ILexEntry`: `Create(Guid, ILexDb)` — Guid-preserved.
- `ILexSense`: `Create(Guid, ILexEntry)` — Guid-preserved.
- `IMoInflAffMsa`: factory `Create(ILexEntry, SandboxGenericMSA)` — no Guid overload; identity_remap captures the mapping.
- `IMoAffixAllomorph`: `Create()` then `entry.LexemeFormOA = allo` OR `entry.AlternateFormsOS.Add(allo)`. No Guid overload — identity_remap.

**Deferred to Phase 0 implementation MCP probes**:
- `ILexExampleSentence` factory — confirm `Create(Guid, ILexSense)` signature.
- `ILexPronunciation` factory.
- `ILexEtymology` factory.
- `ILexEntryRef` factory.

**Alternatives considered**:
- Flatten owned children into separate Phase 3c categories (e.g., `LEX_EXAMPLES` as a category) — rejected: violates ownership semantics. Owned children come with their parent atomically per memo principle (Owned vs Referenced).

## R3 — MSA Subclass Dispatch

**Decision**: The affix-entry executor inspects each MSA via `ICmObject(msa).ClassName` and dispatches:
- `MoInflAffMsa` → `MSAOperations.CreateInflAff(sense, pos, slots=[])` (verified in Phase 0). `SlotsRC` left empty for 17.1 sub-pass.
- `MoDerivAffMsa` → `MSAOperations.CreateDerivAff(sense, from_pos, to_pos)`.
- `MoUnclassifiedAffixMsa` → `MSAOperations.CreateUnclassified(sense, pos)`.

**Rationale**: Phase 0 Layer 3 used `CreateInflAff` exclusively (verb-vertical only encounters inflectional affix MSAs). Phase 3c generalises to derivational + unclassified — both surfaced by MCP probe at Phase 0 implementation time.

**Deferred to Phase 0 implementation MCP probes**: confirm `MSAOperations` has `CreateDerivAff` + `CreateUnclassifiedAffix` wrappers, or fall back to `IMoDerivAffMsaFactory` / `IMoUnclassifiedAffixMsaFactory` via `Cache.ServiceLocator.GetInstance[T]()`.

**Edge case**: An MSA whose subclass is not surfaced by probe emits `Skip(NEEDS_MANUAL)` — same fail-loud posture as FR-341 compound rules.

## R4 — Slots (Step 16)

**Decision**: `IMoInflAffixSlot.Create(Guid)` under `IPartOfSpeech.AffixSlotsOC`. Slot creation occurs after `POS` (Phase 3b) has placed the owning POS in target.

**Carry-over from Phase 0**: STATUS.md confirms `IMoInflAffixSlotFactory.Create(Guid)` works — Phase 0 spike created 4 slots under the Verb POS with GUIDs preserved (`SbjAgr`, `Neg/Mood`, `Repetative`, `VSuffix`).

**Reference fields**: Slots have no outgoing references in their initial state (residue carrier B on `Description`).

## R5 — Affix Templates + 17.1 MSA-Slot Wiring (Step 17)

**Decision**: Templates created via `IMoInflAffixTemplate.Create(Guid)` under `IPartOfSpeech.AffixTemplatesOS`. `PrefixSlotsRS` + `SuffixSlotsRS` reference sequences wired in source order against slot GUIDs already in target (from step 16). Carrier B residue on `Description`.

**17.1 sub-pass** (FR-333): Runs as a post-execute tail block on the `AFFIX_TEMPLATES` executor. Consumes `plan.msa_slot_bindings: dict[Guid, list[Guid]]` populated by the affix-entry executor (US1). For each MSA-guid → slot-guid-list pair, looks up the MSA in target by guid (or via identity_remap if Phase 0 created it), looks up each slot in target by guid, and writes `MSA.SlotsRC.Add(slot)` per slot. Unresolved slot-GUIDs at wire time emit `Skip(DEPENDENCY_UNRESOLVED)` on the affected MSA, not on the template.

**Rationale**: Phase 0 verb-vertical Layer 3 wired MSA → Slot inline during MSA creation (12 of 13 MSAs wired correctly to one of the 4 slots). Phase 3c separates this into a tail pass so the wiring is decoupled from MSA creation order — affix entries can be planned before slots are stable, which matters when the spec's memo ordering places affixes (step 14) before slots (step 16).

**In-plan mapping shape**:
```python
plan.msa_slot_bindings: dict[Guid, list[Guid]] = {
    msa_guid: [slot_guid_1, slot_guid_2, ...],
    ...
}
```

## R6 — Stems (Step 18)

**Decision**: Stem LexEntries follow the same closure walk as affix entries (R2), partitioned in by `IsAffixType == False`. Sense-to-semantic-domain refs (`ILexSense.SemanticDomainsRC`) resolve against Phase 3b semantic domains (FR-326) by GUID lookup against `LangProject.SemanticDomainListOA.PossibilitiesOS` walked recursively. Unresolved → `Skip(DEPENDENCY_UNRESOLVED)`.

**MSA subclasses for stems**:
- `MoStemMsa` → `MSAOperations.CreateStem(sense, pos)` (probe to confirm signature).
- `MoStemMsa.StratumRA` resolves against Phase 3a Strata transfers (FR-336).

**Carry-over from Phase 0**: STATUS.md notes ~239 stem entries in Ejagham Mini (252 total − 13 verb-affix). Phase 3c is the first phase to transfer them in bulk.

## R7 — Ad-Hoc Prohibitions + Compound Rules (Step 15)

**Decision**: Two distinct sub-paths under the `ADHOC_COMPOUND_RULES` category.

**Ad-hoc prohibitions**: Located under `LangProject.MorphologicalDataOA.AdhocCoProhibitionsOC`. Subclasses:
- `IMoAdhocProhibAtom` — bare atomic prohibition.
- `IMoAdhocProhibitionGr` — group prohibition with `MembersRS` sequence.

Each subclass dispatch on `ClassName` to its respective factory. References to affix LexEntries resolve through `identity_remap` (Phase 1 inheritance, FR-337).

**Compound rules** (FR-341): Located under `LangProject.MorphologicalDataOA.CompoundRulesOS`. Subclasses:
- `IMoEndoCompound` → `IMoEndoCompoundFactory.Create(Guid)`. Endo-centric: `LeftMsaOA` + `RightMsaOA` + head selector (`HeadLast` bool).
- `IMoExoCompound` → `IMoExoCompoundFactory.Create(Guid)`. Exo-centric: `LeftMsaOA` + `RightMsaOA` + `ToMsaOA` (the derived MSA, exo-specific).

Subclass-specific reference fields (`IMoExoCompound.ToMsaRA`, etc.) MUST be wired in `execute_action`. Unknown subclasses emit `Skip(NEEDS_MANUAL)` per FR-341.

**Deferred to Phase 0 implementation MCP probes**:
- Confirm `IMoEndoCompoundFactory` + `IMoExoCompoundFactory` are surfaced; if not, use `Cache.ServiceLocator.GetInstance[T]()`.
- Confirm subclass list (e.g., is there an `IMoBinaryCompound` base or further concrete subclasses).
- Confirm `MembersRS` and `LeftMsaOA`/`RightMsaOA`/`ToMsaOA` accessor names.

**Alternatives considered**:
- Single generic `IMoCompoundRule` factory with `ClassName` post-set — rejected per FR-341: LCM does not expose a settable `ClassName`; subclass must be chosen at creation.
- Skip compound rules entirely from Phase 3c — rejected: memo step 15 is in-scope; Ejagham Mini has compound rules surfaced by MCP probe.

## R8 — Phase 0 Verb-Vertical Collision (FR-334)

**Decision**: Retire Phase 0 verb-vertical in place. No category-specific Phase-0-collision code in Phase 3c. The universal target-GUID collision guard in `_create_with_guid` (Phase 3a hardening, commits 608b72c + 3863ed2) returns `Skip(ALREADY_PRESENT_BY_GUID)` for any entry/MSA/allomorph Phase 0 created.

**Rationale**: Clarifications Session 2026-06-22 confirmed Phase 0 is POC/MVP, not steady-state. The production pipeline ordering (Phase 3b pre-reqs → POS + empty templates + empty slots → Affixes → 17.1 → Stems) is the canonical path. The collision-guard suffices for the transition window when Phase 0 may have already populated a target.

**Expected collision width**: Phase 0's picked-POS affix subset only (Ejagham Mini: 13 verb-affix entries). Stems are entirely untouched by Phase 0.

**Verification**: SC-303 — Phase 0 verb-vertical re-run after a full Phase 3c transfer produces zero new actions.

## R9 — Empty-Source UX (FR-339)

**Decision**: Inherit Phase 3a FR-308 verbatim. `report.py._build_from_plan` derives `empty_categories` from `plan.selection.categories` minus the categories that produced any actions/skips/overwrites; `render_text_summary` emits `[skip] no items in source for X` per empty category. The five new Phase 3c categories appear in the iteration automatically once they're added to `GrammarCategory` enum.

**No new code required** — only test coverage to confirm the inheritance works for each of the five new categories.

## R10 — In-Plan Bindings Lifecycle

**Decision**: `RunPlan` gains two new optional fields:
- `msa_slot_bindings: dict[Guid, list[Guid]]` — populated during affix-entry preview, consumed by `AFFIX_TEMPLATES` executor tail (17.1 sub-pass).
- `lexentry_ref_bindings: dict[Guid, dict[str, list[Guid]]]` — populated during affix/stem entry preview, consumed by `STEMS` executor tail (post-pass A). Structure: `{src_entry_guid: {"ComponentLexemesRS": [...], "PrimaryLexemesRS": [...]}}`.

**Lifecycle**: Bindings live for the duration of one `transfer.execute(plan, ...)` call. They are NOT persisted to disk and NOT carried across runs (FR-340 explicitly forbids persistent cross-phase state). On re-run, the planner re-derives them from source.

**Alternatives considered**:
- Pass bindings as separate arguments through `execute_action` signatures — rejected: clutters the 5-callback interface for the four categories that don't need bindings.
- Store bindings on a global module-level dict — rejected: breaks the "plan is the single source of truth" principle established in Phase 3a.

## R11 — Live-MCP Verification Scenarios

**Decision**: Per quickstart.md (Phase 1 output), six scenarios:
- A: Empty target — full Phase 3a→3b→3c chain end-to-end (Preview + Move).
- B: Phase 3c re-run on populated target — all categories produce skips, zero new actions (FR-307 inheritance).
- C: Phase 1 overwrite path with `enable_overwrite=True` — selected affixes overwrite with merge residue.
- D: Phase 2 interactive merge path with FakeResolver — conflict prompts collected per affix sense.
- E: Preview-only (modifyAllowed=False) — zero LCM writes, plan-only output.
- F: Phase 0 verb-vertical re-run after full Phase 3c — SC-303 verification (zero new actions).

**Deferred to Phase 0 implementation**: Run all six against `Ejagham Mini → Ejagham Full GT-Test` per Phase 3a/3b precedent. Capture results in `specs/007-affixes-stems/verification-log.md`.

## Open MCP probes (executed during Phase 0 implementation)

These are deferred to T004-T010 of the future tasks.md per the Phase 3a/3b precedent:

1. `ILexExampleSentenceFactory`, `ILexPronunciationFactory`, `ILexEtymologyFactory`, `ILexEntryRefFactory` — confirm `Create(Guid, owner)` or fall back to ServiceLocator.
2. `MSAOperations.CreateDerivAff`, `CreateUnclassifiedAffix`, `CreateStem` — confirm wrapper signatures.
3. `IMoEndoCompoundFactory`, `IMoExoCompoundFactory` — surface confirmation + subclass enumeration.
4. `IMoAdhocProhibAtomFactory`, `IMoAdhocProhibitionGrFactory` — surface confirmation.
5. `IMoInflAffixTemplate.PrefixSlotsRS` / `SuffixSlotsRS` accessor names + collection types (RS sequence vs OS owning).
6. `LangProject.MorphologicalDataOA` — confirm `AdhocCoProhibitionsOC` + `CompoundRulesOS` accessor names.
7. Ejagham Mini inventory probe: count compound rules, ad-hoc prohibitions, stem entries by morph type, slots per POS, templates per POS.

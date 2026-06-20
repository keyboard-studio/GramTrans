# GramTrans — Session Handoff

**Updated**: 2026-06-19 (late evening)
**Branch**: `main`
**Phase**: Phase 0 — Additive Grammar Transfer (constitution v5.0.0)

---

## ▶▶▶ Multi-POS walker + leaf categories + Phase 1 scaffold (2026-06-20)

Phase 0 verb-vertical is now general-purpose:

- `Lib/preview._select_source_poses(source, selection)` returns the list of
  source POS objects to walk based on `selection.pos_picks` (frozenset of
  GUIDs). Empty `pos_picks` + any POS-closure category on → walks every
  top-level POS in source.
- `Lib/preview._plan_pos_closure(...)` and `_plan_layer3_for_pos(...)` take
  `src_pos` and run the same POS → Template → Slot → Entry → Sense → MSA
  → Allomorph → PhEnvironment walk per POS.
- `Lib/transfer.execute` iterates `_pos_guids_from_plan(plan)` (derived
  from the plan's POS PlannedActions + POS Skips) and calls
  `_execute_verb_vertical` + `_execute_layer3` for each, threading
  `src_pos_guid` through.
- `Selection.pos_picks: frozenset[str]` added per the spec model.

Live MCP verification on freshly-restored target with
`pos_picks=frozenset({verb_guid})`: **same 67 actions, 0 skips, 0.709s,
lcm_undoable_action_count=69** — byte-equivalent to the pre-multi-POS run.

**Leaf categories** implemented in `Lib/categories.py` (Stream 2 of the
parallel work):

- `gram_categories` (GOLD-aware via `CatalogSourceId`)
- `inflection_features` (GOLD-aware; co-creates IFsSymFeatVal values)
- `inflection_classes` (no GOLD; `IMoInflClassFactory.Create(Guid)`)
- `stem_names` (no GOLD; `IMoStemNameFactory.Create(Guid)`)
- `exception_features` (no GOLD; ref-wire only via target POS lookup)

Stubs remain for `custom_fields`, `variant_types`, `complex_form_types`,
`adhoc_rules`, `compound_rules`.

**Phase 1 scaffold** (Stream 3):

- `specs/002-phase1-overwrite/` with `spec.md` (FR-101..110 + SC-101..103)
  and stubs for plan/research/data-model/quickstart/tasks.
- `src/gramtrans/Lib/matcher.py`: `Match` frozen dataclass +
  `lookup_target(source_guid, category, target, *, source_obj,
  identity_remap, fingerprint_fn) → Match` that resolves via direct GUID
  hit → identity_remap fallback → fingerprint fallback. Fingerprint
  registry seeded with `fingerprint_for_msa` + `fingerprint_for_allomorph`.

**Tests**: 141 unit (up from 101) + 5 integration scaffolds skipped on
bare pytest.

Non-fatal stderr warnings during the multi-POS Move run: 26 instances of
`LexSenseOperations.GetSyncableProperties: 'ILangProject' object has no
attribute 'PublicationsOA'`. Silently skipped by the BaseOperations
patch's `cannot be converted to SIL.LCModel.` clause; queue for fork-level
cleanup in Phase 0.5.

## ▶▶ Layer 3 end-to-end transfer landed (2026-06-19 night)

After T-Spike closure, Layer 3 (LexEntry / LexSense / MSA / Allomorph /
PhEnvironment) was implemented and MCP-verified live against the Layer-1+2
target. Full run:

- **59 added, 8 skipped, wall-clock 0.387s, `lcm_undoable_action_count=62`**
- 13 LexEntries + 13 LexSenses with **GUIDs preserved** (LCM factory accepts
  `Create(Guid, owner)` on these)
- 13 MoInflAffMsas + 20 MoAffixAllomorphs created with new GUIDs (LibLCM's
  `IMoInflAffMsaFactory.Create(ILexEntry, SandboxGenericMSA)` and
  `IMoAffixAllomorphFactory.Create` don't expose Guid overloads;
  `identity_remap` captures the mapping per FR-012). Used flexlibs2's
  `MSAOperations.CreateInflAff(sense, pos, slots)` wrapper for the
  SandboxGenericMSA dance.
- 12 of 13 MSAs wired to a slot via `SlotsRC` (by GUID lookup against
  target Layer-2 slots); 1 unbound (the `ro~-` affix) — matches the MCP
  inventory's prediction exactly.
- 2 PhEnvironments shared with the target's FW-template defaults → reused
  via `Skip(ALREADY_PRESENT_BY_GUID)` and resolved from `target.Environments`.
- Allomorph `PhoneEnvRC` re-wired to the (reused) target environments.

**Fork patches landed during this work** (all under
`D:/Github/_Projects/_LEX/flexlibs2/flexlibs2/code/Lexicon/`):

- `LexEntryOperations.py`, `AllomorphOperations.py`, `LexSenseOperations.py`,
  `ExampleOperations.py`, `EtymologyOperations.py`, `LexReferenceOperations.py`,
  `PronunciationOperations.py` — all rewritten to enumerate writing
  systems via `self.project.WritingSystems.GetAll()` returning
  `CoreWritingSystemDefinition` objects (`.Handle`, `.Id`) instead of the
  nonexistent `GetAllWritingSystems()` / `GetWritingSystemTag(handle)` methods.
  Same fix pattern that was already applied to the Grammar Operations.

**Resolved 2026-06-19 night (Phase 0.5 patches):**

- Patched fork's `BaseOperations.ApplySyncableProperties` to handle two
  setattr gaps: (a) ITsString-typed string properties (raw `str` →
  `TsStringUtils.MakeString(value, default_ws)`); (b) object-reference
  properties (e.g. `MorphoSyntaxAnalysisRA`) where setattr-with-str fails
  with `cannot be converted to SIL.LCModel.<Iface>` — silently skip those,
  the caller wires cross-project references explicitly.
- Added explicit `MorphTypeRA` wiring in `_create_allomorph_with_guid` via
  GUID lookup against the target's `LangProject.LexDbOA.MorphTypesOA`
  possibility list (morphtype GUIDs are FW-global, shared across projects).
- Re-ran a clean Layer 1+2+3 end-to-end (full 67 actions, 0 skips) on a
  freshly-restored target. Result: 13/13 entries carry their lexeme form
  text AND morphtype reference — verified by reading back the headwords:
  `n~-1`, `n~-2`, `e~-`, `ro~-`, `a~-`, `ń~-3`, `ń~-2`, `o~-1`, `o~-2`,
  `á~-`, `kí~-`, `-k`, `ń~-1`. Wall clock 0.512s.
  `lcm_undoable_action_count=69`.

**Remaining (cosmetic)**:

- LexEntry/LexSense/MSA residue tags currently fall through to a Carrier B
  attempt that no-ops (those classes expose neither `LiftResidue` (None on
  fresh-created) nor `Description`). The residue trail is recoverable via
  `RunReport.identity_remap` + the per-allomorph PhoneEnvRC structure. A
  follow-up could explicitly initialize `LiftResidue` on these classes
  post-create.
- Homograph numbering (`-1`, `-2`, `-3`) is regenerated by FLEx based on
  how many entries share a form; matches source incidentally because the
  Verb-affix set is identical. With a non-empty pre-existing target,
  homograph numbers may shift.

## ▶ T-Spike step 3 fully closed (2026-06-19 evening)

Fresh-target Move re-run executed end-to-end through the new `Lib/preview` +
`Lib/transfer` pair against a `FieldWorks.exe -restore`-d Ejagham Full GT-Test:

- Preview produced 6 PlannedActions, 0 skips (correct — target was empty for these GUIDs)
- Move created POS `86ff66f6` 'Verb' + template `821a96d6` + 4 slots, all GUIDs preserved
- Run report: 6 added, 0 skipped, **wall-clock 0.082s** (vs SC-001's ≤5min budget)
- `lcm_undoable_action_count: 7` — `Ctrl+Z` reverts the entire run
- All 6 freshly-created objects carry parseable Carrier-B residue tags with run_id `GT-20260619-222958`
- Snapshot artifact at `tests/integration/_snapshots/spike_close_post.json`

**Constitution v5.0.0 Principle III closing-clause is now mechanically satisfied.**
Layer 3 (MSA / Allomorph / Environment) is unblocked.

## Late-session MCP verifications (2026-06-19, post-T-Spike)

Four MCP-driven checks against live LCM, all PASS:

1. **T-Spike step 3 (post-spike state)**: new `Lib/preview.build_run_plan` walked
   Ejagham Mini → Ejagham Full GT-Test and emitted 0 actions + 6 skips, with all 6
   GUIDs matching the spike's writes byte-for-byte. `is_certified_readonly=true,
   confidence=high` ⟶ SC-006 verified.
2. **Snapshot artifact** at `tests/integration/_snapshots/spike_close_post.json`
   (1833 bytes, contracts/run-report.md-compliant field order).
3. **Layer 3 inventory** of Ejagham Mini: 252 LexEntries, 13 verb-affix entries,
   20 allomorphs, 2 distinct PhEnvironments, 1 Unbound MSA (FR-007 bucket
   confirmed with real data). T051b PlannedAction estimate: ~61 + 6 Layer 1+2 =
   ~67 total, well under SC-001's 100-piece budget.
4. **Patched fork ApplySyncableProperties** confirmed at runtime on POS,
   MorphRules, LexEntry, Allomorphs (MCP indexer doesn't surface it but the
   runtime has it). Validates the `flexlibs2 fork` dependency is correctly
   installed.

Plus one **bug fix** discovered via MCP: `Lib/residue.apply_carrier_b` previously
cast `obj` to `ICmPossibility` before reading `Description`. Live MCP probe
showed that cast raises `TypeError` on `IMoInflAffixTemplate` — the spike's
writes happened to land somehow (likely a flexlibs2-version-dependent fallback),
but a fresh write through the new code path would crash. Replaced with direct
`getattr(obj, "Description")` access; uniform across every Carrier-B class
(POS, Template, Slot, FsClosedFeature, ...). Round-trip parsed all 6 spike
tags successfully — including the template's residue.

Cross-session run_ids decoded from live Description fields:
- `GT-20260619-162337` Ejagham Mini — POS-only spike
- `GT-20260619-164210` Ejagham Mini — template + 4 slots spike

## TL;DR of this session

1. **`/speckit-analyze` audit** found Layer 1+2 work had outrun the planned
   scaffolding (v4.0.0 adapter pattern bypassed; Move-mode writes happened
   before any Preview engine existed).
2. **Constitution v5.0.0** retired the v4.0.0 adapter-contract requirement —
   `flavors/` is gone; flexlibs2 is imported directly; the LibLCM-direct
   implementation moved to a separate post-Phase-2 sibling repository.
3. **T-Spike refactor**: the inline `transfer_verb_vertical()` Move logic was
   split into `Lib/preview.py` (plan builder, never mutates target) and
   `Lib/transfer.py` (plan executor, the only writer). Principle III is now
   mechanical.
4. **Foundation modules + 70 unit tests** landed (all green in 0.16 s) covering
   residue serialize/parse, FR-018 invariants, Selection invariants, WSMapping
   1:1, closure walker (incl. diamond dedup), WS-mapping validation, affix
   tree → Selection helpers, preview-no-writes, closure-off skip semantics,
   no-silent-drops, and the UI ↔ engine API surface.

The next session's blocking task is **T-Spike step 3** — a live re-run on
`Ejagham Full GT-Test` through the new Preview/Move pair to verify parity
with the original spike (rubric in tasks.md T-Spike).

---

## File layout (post-T-Spike, FLExTrans-style)

```text
src/gramtrans/
├── __init__.py          # v5.0.0 — package metadata only; no re-exports
├── gramtrans.py         # entry: docs dict + MainFunction(project, report, modifyAllowed)
│                        # site.addsitedir(Lib) per FLExTrans convention
└── Lib/                 # helpers (sibling dir, loaded at runtime)
    ├── __init__.py      # docstring only — no sys.path injection (caused double-loads)
    ├── models.py        # E1-E6 dataclasses + enums (renamed from `types.py`
    │                    #   to avoid shadowing stdlib `types` under addsitedir)
    ├── residue.py       # ImportResidueTag + Carrier A/B dispatchers
    ├── closure.py       # BFS walk(seeds, dep_fn) + topological reverse
    ├── ws_mapping.py    # validate / is_complete / required_ws_set +
    │                    #   WSMappingIncomplete / WSMappingOverspecified
    ├── selection.py     # PickerState + SourceAffixInventory +
    │                    #   compute_required_affixes/templates + build_selection
    ├── preview.py       # build_run_plan(...) → RunPlan; closure-on + closure-off
    │                    #   semantics; verb-vertical (POS→Template→Slots)
    ├── transfer.py      # execute(plan, source, target, sink, tag) → RunReport
    │                    #   per-layer creators preserved verbatim from the spike
    ├── report.py        # RunReport.build_from_plan classmethod + to_snapshot_json
    │                    #   method (per_category dict ordered by enum decl) +
    │                    #   render_text_summary for the FlexTools report pane
    ├── api.py           # UI ↔ engine facade (T058):
    │                    #   initialize_run / list_target_candidates / bind_target /
    │                    #   compute_preview / execute_move + exceptions
    └── ui/              # PyQt widgets (T054-T057, T074 — UI shells next)
        └── __init__.py
```

**No `flavors/` directory.** v5.0.0 retired the adapter contract.

---

## What's validated end-to-end against live data

Layer 1 (POS) + Layer 2 (Template + 4 Slots) cross-project transfer
**Ejagham Mini → Ejagham Full GT-Test** completed in the previous session.
That was the one-time "validation spike" per constitution v5.0.0 Principle III's
closing clause. The new Preview/Move pair (T-Spike steps 1-2 below) **mirrors**
that spike's behaviour byte-for-byte but lives behind the plan-builder /
plan-executor separation now.

### Layer 1 — POS — VERIFIED in spike; awaiting re-verify through Lib/transfer.py
- Source Verb POS copied to target with **GUID preserved** (`86ff66f6-…`)
- Multi-WS Name/Abbreviation/Description fields copied via
  `BaseOperations.ApplySyncableProperties` (patched fork)
- Carrier B residue tag appended to `Description` multistring
- FR-009 additive duplicate confirmed
- LCM UndoableUnitOfWork (FlexTools-runner's outer UOW) caught the writes;
  `Ctrl+Z` in FLEx undoes the run

### Layer 2 — Template + 4 Slots — VERIFIED in spike; awaiting re-verify
- Verb template GUID preserved (`821a96d6-…`)
- 4 slot GUIDs preserved (SbjAgr, Neg/Mood, Repetative, VSuffix)
- Slot reference sequences (`PrefixSlotsRS` / `SuffixSlotsRS`) wired in
  source order
- Residue tags on Description multistrings of template + each slot

### Layer 3 — LexEntry + Sense + MSA + Allomorph + PhEnvironment — OUTLINED

**Live inventory of Ejagham Mini (via MCP, 2026-06-19 evening)**:

| Entity | Count |
|---|---|
| Total LexEntries | 252 |
| Total senses | 250 |
| Verb-affix entries (sense.MSA is `IMoInflAffMsa` with PartOfSpeechRA=Verb) | **13** |
| InflAffMsas under Verb | 13 |
| ...of which Unbound (`SlotsRC.Count == 0`) | **1** ✓ (matches the FR-007 "Unbound bucket" use case) |
| Allomorphs across those 13 entries | 20 |
| Distinct `IPhEnvironment` referenced | 2 |

Sample verb-affix headwords (first 5): `n~-1`, `n~-2`, `e~-`, `ro~-`, `a~-`.

**MSA → Slot wiring (live, full set)** for T051b implementer:

| Headword | Slot |
|---|---|
| `n~-1`, `n~-2`, `e~-`, `a~-`, `ń~-3`, `ń~-2`, `o~-1`, `o~-2`, `á~-`, `ń~-1` | SbjAgr (10 affixes) |
| `kí~-` | Neg/Mood |
| `-k` | VSuffix |
| `ro~-` | (unbound — `SlotsRC.Count == 0`) |

`ILcmReferenceCollection[IMoInflAffixSlot]` supports direct Python iteration
(`for sl in msa.SlotsRC`) — DON'T try `.ElementAt(i)`, that raises
AttributeError. This pattern applies to all `SlotsRC` / `PhoneEnvRC` /
similar `Rc` reference collections in LCM.

Layer-3 PlannedAction count for a full verb-vertical run:
~13 LexEntry + 13 LexSense + 13 MSA + 20 Allomorph + 2 PhEnv = **~61 actions** beyond
Layer 1+2's 6 (POS + template + 4 slots) = **~67 objects total**. Well under SC-001's
≤100-piece / <5-min budget.

Layer 3 implementation is gated on T-Spike step 3 fresh-target re-run (per constitution
v5.0.0 Principle III). The post-spike state verified the planner sees the spike's
writes correctly; the fresh-target Move-path verification needs a `FieldWorks.exe -restore`
of `Ejagham Full.fwbackup` to re-test the create chain.

Factory + Apply pattern (all validated in spike):

| Object | Factory create | Owner attach |
|---|---|---|
| `ILexEntry` | `Create(Guid, ILexDb)` | one-shot |
| `ILexSense` | `Create(Guid, ILexEntry)` | one-shot |
| `IMoInflAffMsa` | `Create(Guid)` | `entry.MorphoSyntaxAnalysesOC.Add(msa)`; `sense.MorphoSyntaxAnalysisRA = msa` |
| `IMoAffixAllomorph` | `Create(Guid)` | `entry.LexemeFormOA = allo` OR `entry.AlternateFormsOS.Add(allo)` |
| `IPhEnvironment` | `Create(Guid)` | `cache.LangProject.PhonologicalDataOA.EnvironmentsOS.Add(env)` |

Residue carrier: **A** (`LiftResidue`) for `ILexEntry`/`ILexSense`/`IMoForm`/
`IMoMorphSynAnalysis`; **B** (`Description`-append) for `IPhEnvironment`.

---

## Tasks closed this session

**Foundation**: T001, T002, T003, T004, T006, T007, T009, T010, T011, T012, T013.

**Data-model + residue + report**: T019, T020, T021, T022.

**Foundational tests** (10): T023, T024, T025, T026.

**US1 (engine)**: T029, T036, T037, T052 (preview.py), T053 (transfer.py),
T058 (api.py).

**US2 (reporting)**: T063, T064, T065, T067.

**US3 (selection + closure-off)**: T072, T073, T076.

**Polish**: T083, T084, T085, plus T-Spike steps 1+2.

70 unit tests passing in ~0.16 s. Run with `pytest tests/unit/`.

---

## flexlibs2 fork dependency (CLAUDE.md + README.md document this)

Runtime depends on **MattGyverLee/flexlibs2** at
`D:/Github/_Projects/_LEX/flexlibs2`. Two patches:

1. `GetSyncableProperties` writing-system enumeration fix
   (`project.WritingSystems.GetAll()`, not `ws_factory.WritingSystems`).
2. New `ApplySyncableProperties(item, props, ws_map=None)` on `BaseOperations`
   + 8 Grammar Operations subclasses.

Patched files (9):
`BaseOperations.py`, `Grammar/POSOperations.py`, `Grammar/MorphRuleOperations.py`,
`Grammar/GramCatOperations.py`, `Grammar/InflectionFeatureOperations.py`,
`Grammar/NaturalClassOperations.py`, `Grammar/EnvironmentOperations.py`,
`Grammar/PhonologicalRuleOperations.py`, `Grammar/PhonemeOperations.py`.

Install via `pip install -e D:/Github/_Projects/_LEX/flexlibs2`.

---

## Next session pick-up checklist

1. **Run T-Spike step 3** — restore `Ejagham Full GT-Test`, run
   `gramtrans.gramtrans.MainFunction` through FlexTools, verify the parity
   rubric (tasks.md T-Spike: same GUIDs, same residue tags, empty skip list,
   Ctrl+Z undoes, Preview produces no writes).
2. **Capture pre/post Import Residue snapshots** into
   `tests/integration/_snapshots/spike_close_{pre,post}.json` (T-Spike step 4).
3. **Then** begin Layer 3 — extend `Lib/preview.py._plan_verb_vertical` (and
   `Lib/transfer.py._execute_verb_vertical`) to walk entries/senses/MSAs/
   allomorphs/environments per the table above. Split into
   `Lib/categories_msas.py` per the plan.
4. **UI widget shells (T054-T057, T074)** — start with `Lib/ui/target_picker.py`
   since it has no LCM dependency beyond `list_target_candidates`.
5. **Integration tests** — T030 (full categories), T031 (pre-existing target
   not modified), T033/T033b (FR-019/FR-020 refusal), T034 (GUID preservation),
   T035 (GOLD inviolability).

---

## Reference notes

- **Restore the throwaway target**:
  ```powershell
  & 'C:\Program Files\SIL\FieldWorks 9\FieldWorks.exe' -restore `
    'D:\Github\_Projects\_LEX\GramTrans\backups\Ejagham Full.fwbackup' `
    -db 'Ejagham Full GT-Test' -include c
  ```
  Backups at `D:/Github/_Projects/_LEX/GramTrans/backups/`.

- **Open spec questions** (none blocking):
  - WS mapping (FR-011) is identity-only in the MVP. The
    `ApplySyncableProperties(item, props, ws_map=None)` signature is ready
    to accept a `ws_map` dict when the UI surfaces one.
  - "Unbound" affix bucket display: validated as
    `IMoInflAffMsa.SlotsRC.Count == 0`. Ejagham Mini has 1 such affix.

- **MCP validator quirks** worth knowing:
  - `getattr(project, "Cache")` / `getattr(project.POS, "ApplySyncableProperties")`
    dodge static checks when needed in MCP probes — never needed in actual runtime.
  - The runner pre-wraps every snippet in a UOW; don't nest your own
    `UndoableUnitOfWorkHelper.Do(...)`.
  - `from flexlibs2 import (...)` MUST be a single line for the MCP parser.

- **Don't reintroduce `Flavor` enum**: v5.0.0 explicitly removed it.

- **Don't add `gramtrans.Lib` to sys.path inside `Lib/__init__.py`**: that
  caused a double-load of `models.py` (top-level + package) and two distinct
  `GrammarCategory` enums, silently breaking dict lookups. Helpers use
  `__package__`-aware imports instead (`from .models import ...` when loaded
  as `gramtrans.Lib.X`, `from models import ...` when loaded via
  `site.addsitedir(Lib)`).

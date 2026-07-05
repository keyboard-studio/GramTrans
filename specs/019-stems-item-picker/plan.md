# Implementation Plan: Stems Item Picker (Model-A) — Un-stub the Disabled Pane

**Feature**: `019-stems-item-picker` | **Spec**: [spec.md](./spec.md) |
**Created**: 2026-07-05 | **Status**: Draft

## Summary

Un-stub the transfer wizard's **Stems** tab (currently the disabled "[STUBBED]" placeholder at
[selection_wizard.py:625-689](../../src/gramtrans/Lib/ui/selection_wizard.py)) so the user can
pick **stem-morphtype lexical entries** exactly as they already pick affixes. Stems are a
**Model-A (item-derived)** selection sharing the affixes' `LexEntry` closure engine in
[Lib/selection.py](../../src/gramtrans/Lib/selection.py); only the **morphtype partition** and
the **stem MSA dispatch arm** differ.

The live UI engine is `Lib/selection.py` — **not** the `categories.py` `affixes_*/stems_*`
callbacks (those `NotImplementedError` stubs at ~1817-1916 belong to the separate,
out-of-scope Phase-3c LibLCM-direct track and are never invoked by the wizard). Four builders
in `selection.py` hard-filter to `IsAffixType == true`; each gains a complementary **stem
partition** (`IsAffixType != true`, including null/uncastable morphtype → stem, per FR-002).
A sibling `stem_picks` field on `Selection` threads through wizard pages 3–5 into the existing
skeleton/deps closure and the **existing** aggregated Move gate. Nothing on the page writes to
the target (Constitution III); the only write remains at Move.

## Technical Context

- **Language/runtime**: Python 3, FlexTools host; PyQt wizard (`QtWidgets.QWizardPage`).
- **Engine touch points**:
  - [Lib/selection.py](../../src/gramtrans/Lib/selection.py) — the four `IsAffixType`
    filter sites, each needing a stem partition:
    - `_build_target_sets` (~:374) — partition target guids/forms by morphtype (both tabs
      need target-status).
    - `build_pos_grouped_inventory` (~:656) — the item-picker inventory; stem tree.
    - `build_skeleton_inventory` (~:1207) — Model-A closure (POS/inflection classes/stem
      names/features) for picked stems.
    - `build_deps_inventory` (~:1557) — grammatical-deps closure.
    - MSA dispatch arm at ~:706-810 (affix arm reads `SlotsRC` on `IMoInflAffMsa`); add a
      `MoStemMsa` arm reading `PartOfSpeechRA` + `MsFeaturesOA`.
    - `build_excluded_lossy_warnings` (~:1800+) — stem missing-reference warnings route here.
  - [Lib/models.py](../../src/gramtrans/Lib/models.py) — `Selection` dataclass: add
    `stem_picks: frozenset[str]` sibling to `affix_picks`; `GrammarCategory.STEMS` invariant
    (stem_picks requires STEMS category on), mirroring the affix invariant.
  - [Lib/ui/selection_wizard.py](../../src/gramtrans/Lib/ui/selection_wizard.py) —
    `_PageItemPicker`: enable + populate the Stems tab (remove stub at :625-689);
    `collect_selection()` (~:1189) emits `stem_picks`; pages 3–5 gain `_get_stem_picks()`
    mirroring `_get_affix_picks()` (~:1410, :1897) and thread `stem_picks` into the builders;
    Move gate at ~:3171 (`plan.excluded_lossy_count()`) already aggregates — no new dialog.
  - [Lib/preview.py](../../src/gramtrans/Lib/preview.py) /
    [Lib/transfer.py](../../src/gramtrans/Lib/transfer.py) — plan-builder / plan-executor
    consume the pick set via the shared engine; verify stem picks flow through `compute_plan`.
- **flexicon surface** (MCP-verified, cycle 1):
  - Partition: `LexEntry.LexemeFormOA.MorphTypeRA.IsAffixType` (boolean on `IMoMorphType`).
    `LexemeFormOA`/`MorphTypeRA` may be null. Enumeration anchor `LexDbOA.Entries` (flat,
    unpartitioned — feeds both tabs).
  - Stem MSA: `MoStemMsa.PartOfSpeechRA` (POS), `MoStemMsa.MsFeaturesOA` (exception/inflection
    features). Inflection classes via `POS.InflectionClassesOC`; stem names via
    `IPartOfSpeech.StemNamesOC`; inflectable features via `POS.InflectableFeatsRC`.
    **`InflectionClassRA` (RA → `IMoInflClass`) and `SlotsRC` (RC) BOTH exist on `IMoStemMsa`
    (MCP-confirmed 2026-07-05; require cast). `InflectionClassRA`: READ-IF-PRESENT — the stem
    dep walk reads it (guarded None-check) as an FR-009 referential edge alongside
    `POS.InflectionClassesOC`; 0/2444 populated on Ejagham live data (no behavior change).
    `SlotsRC`: OUT — empty (0/2444) AND affix-only; never read, never triggers a cast to
    `IMoInflAffMsa`.**
  - Owned-child closure on `ILexEntry` (shared with affix path): `SensesOS`,
    `MorphoSyntaxAnalysesOC`, `AlternateFormsOS`, `ExamplesOS` (via senses), `LexemeFormOA`.
- **Reference specs**: 008 (affix POS picker), 009 (skeleton/deps selectors, cross-page
  selection, target-status column), 007 (affixes/stems split).

## Constitution Check (v5.1.0, Principles I–V)

- **I. FLEx Domain Fidelity** — PASS. GUID-first identity on stem picks; NEW/IN TARGET/SIMILAR
  status by GUID-then-fingerprint (FR-006). GOLD inviolability held (FR-011, engine GOLD-skip).
  Cross-references (stem → POS/inflection class/stem name/feature) must resolve in target or
  fail loud (FR-009) — routed to the aggregated Move gate, never silently dropped.
- **II. FlexTools-Compatible, flexicon-Direct** — PASS. Direct flexicon/LCM property access in
  `selection.py`; no `flavors/` indirection. Page lives under `Lib/ui/`. Degrades gracefully:
  zero-stem source renders an empty (non-stub, non-error) tab (FR-007).
- **III. Preview-Before-Mutate (NON-NEGOTIABLE)** — PASS. The Stems tab is selection-only; **no
  page write**. Picks feed `Lib/preview.py`/`Lib/transfer.py`; the only write is at Move
  (FR-008). No new write path introduced.
- **IV. Phased Merge Discipline** — PASS. No conflict-mode UI (ADD_NEW/MERGE/OVERWRITE); the
  per-category Layer-1 default applies automatically (FR-012). Field-level merge is the
  separate 020 phase and OUT OF SCOPE. This is item-selection parity with the shipped affix
  picker, not a new merge phase.
- **V. Referential Completeness** — PASS. Picked stems pull their full owned-child closure
  (FR-005) and grammatical-dependency closure (FR-004) by default, deselectable downstream; a
  kept stem whose needed dependency is deselected and target-absent produces exactly one
  aggregated warning (FR-009/FR-010), never a silent broken transfer.

**Verdict**: No violations. No Complexity Tracking entries required.

## Project Structure

```text
specs/019-stems-item-picker/
├── plan.md              # This file
├── spec.md              # Corrected: FR-002 null-guard inversion, FR-004 accessors, FR-013 MSA scope
├── research.md          # Phase 0 — partition/MSA/null-guard decisions (MCP-verified)
├── data-model.md        # Phase 1 — Selection.stem_picks, StemRow, derived-dependency entities
├── contracts/
│   └── stems-item-picker.md   # UI + engine contract for the Stems tab and stem partition
├── quickstart.md        # Phase 1 — live source→target validation scenarios
└── tasks.md             # Phase 2 (/speckit-tasks — NOT created here)
```

**Structure Decision**: Single FlexTools module (`src/gramtrans/`, flat `Lib/` per
constitution). No new top-level files; all work extends existing `selection.py`, `models.py`,
and `selection_wizard.py`. New stem-specific test modules mirror the affix test surface.

## Key Design Decisions

1. **Parameterize, don't duplicate.** Add a `want_affix: bool = True` (or `want_stem`)
   parameter to each of the four builders; the affix call site keeps its default so existing
   behavior is byte-stable. The stem partition is the complement filter. Rationale: a parallel
   `build_stem_*` family would duplicate the shared owned-child closure the spec forbids
   re-inventing. **Alternative rejected**: full parallel builders (duplication, drift risk).

2. **Null-guard inversion is a deliberate, tested divergence (FR-002).** The affix filter uses
   `except (AttributeError, TypeError): continue` (skip). The stem filter MUST invert to
   **include-on-exception**: a null/uncastable morphtype falls into the stem bucket. This is
   the single highest-risk correctness point; it gets a dedicated unit test (null lexeme form,
   null morphtype, non-castable morphtype → all appear in Stems, none dropped).

3. **Separate MSA dispatch arm for `MoStemMsa` (FR-013).** Never cast a stem MSA to
   `IMoInflAffMsa`; never read `SlotsRC`; never enter the affix slot/template skeleton builder.
   The stem dep walk is `PartOfSpeechRA → POS.{InflectionClassesOC, StemNamesOC,
   InflectableFeatsRC}` + `MoStemMsa.MsFeaturesOA`. Prevents the silent no-op / AttributeError
   the affix arm would produce on a stem entry.

4. **`stem_picks` is a first-class sibling of `affix_picks`, not a reuse of it.** New frozenset
   field on `Selection`, its own STEMS-category invariant, its own `_get_stem_picks()`
   accessors on pages 3–5. Both pick sets deduplicate shared dependencies by GUID (a POS needed
   by both a picked affix and a picked stem is pulled once).

5. **No new Move dialog.** Stem missing-reference warnings fold into the existing
   `plan.excluded_lossy_count()` / `build_excluded_lossy_warnings()` aggregation (FR-010).
   Single consolidated confirmation across all wizard pages.

## Phased Task Outline (for /speckit-tasks)

- **Phase A — Data model**: add `Selection.stem_picks` + STEMS-category invariant
  (`models.py`); extend `tests/unit/test_selection_invariants.py`.
- **Phase B — Engine partition (TDD)**: parameterize the four `selection.py` builders with the
  stem partition + include-on-exception null guard; add the `MoStemMsa` dispatch arm and stem
  dep walk. New tests: `test_stem_partition.py` (null-guard cases, disjoint/complete
  partition), `test_build_stem_inventory.py`, stem skeleton/deps closure, mixed affix+stem
  GUID dedup.
- **Phase C — UI**: un-stub `_PageItemPicker` Stems tab (remove :625-689 placeholder), populate
  from the stem inventory, wire check state → `stem_picks`; `collect_selection()` emits
  `stem_picks`; pages 3–5 `_get_stem_picks()` + thread into builders. Extend
  `tests/unit/test_selection_ui.py` + affix tree tests for the stem tree.
- **Phase D — Integration/verify**: live source→target pair with mixed stems+affixes — confirm
  disjoint/complete partition (SC-001), closure in plan (SC-002/003), target-status
  (SC-004), single aggregated Move warning (SC-005), zero-stem empty tab (SC-006), no
  conflict-mode control (SC-007). Attach pre/post residue artifacts per the verification gate.

## Open Questions / To Resolve in /speckit-tasks

- Parameter shape: single `want_affix: bool` across all four builders vs. a shared
  `_partition_entries(entries, want_affix)` helper — decide after reading the exact filter
  bodies; default to the helper if the four filters are textually identical.
- Whether `_build_target_sets` needs one call returning both partitions or two calls (perf: one
  enumeration pass preferred).
- SIMILAR (vs NEW/IN TARGET) fingerprint reuse for stems: confirm the affix fingerprint applies
  unchanged to stem entries (lexeme form + morphtype), or needs a stem-specific fingerprint.

# Implementation Plan: Similar-Candidate Capture & Per-Item Resolution Data Model

**Branch**: `011-similar-resolution-datamodel` | **Date**: 2026-07-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/011-similar-resolution-datamodel/spec.md`

**Note**: This plan was produced via `/speckit-plan` driven by the LEX crew (`/lex-lead`
review cycle) with every LCM API assumption validated read-only against a live FLEx repo
through the FLExTools MCP (project **Ejagham Full GT-Test**). See [research.md](research.md)
for the live evidence backing each decision.

## Summary

Feature 011 is the **data-model foundation** for the per-item merge-preview + SIMILAR-resolution
workflow (first of five chunks: 011 model → 012 diff → 013 transfer → 014 pane → 015 wizard).
It adds pure-Python frozen typed vocabulary plus the capture logic the later chunks consume —
**no UI, no diff rendering, no transfer/closure/execution behavior change** (FR-010). Concretely:

1. A frozen `SimilarCandidate(target_guid, form, gloss)` describing one target entry a SIMILAR
   source item could merge into (FR-001).
2. The affix target-set build gains a `normalized-form → ordered tuple[SimilarCandidate]` map
   plus a flat deduped all-candidates collection for a global dropdown; the single existing call
   site is updated (FR-002/FR-005). `AffixRow` gains `suggested_target_guid` (FR-004).
3. `PhonologyRow` gains `matched_target_guid`, populated for SIMILAR rows from a
   collision-aware label→GUID resolution kept during phonology build (FR-006).
4. A frozen `SimilarResolution(entry_guid, action, target_guid?)` with a **three-way** action —
   `overwrite` (source wins every field / import golden), `merge` (target-preserving, fill-gaps
   only), or `create_new` (fresh, no link) — validated so both `overwrite` and `merge` name a
   target while `create_new` names none (FR-007). Carried inertly on `Selection.similar_resolutions`
   with a `similar_resolution_for(guid)` accessor (FR-008), following the existing `leaf_item_picks`
   inert-when-off precedent exactly. The default action (seeded downstream in 014) is `overwrite`,
   which preserves today's source-wins execution exactly.

**Technical approach (research-grounded):** reuse the existing `_best_form` / `_collect_glosses` /
`_phon_label` / `_phon_guid` helpers; extend the two existing target-set builders
(`_build_target_sets`, `_phon_target_sets`) in place; order all candidate tuples and resolve all
label collisions **deterministically by HVO ascending** (the live target proves both affix-form
and phonology-label collisions are real and pervasive — the ordering is not cosmetic, it is a
reproducibility contract for SC-001/SC-002).

## Technical Context

**Language/Version**: Python 3 (hosted by a standard FlexTools install; `from __future__ import annotations`).

**Primary Dependencies**: None new. Pure-Python `dataclasses` + `enum` + `typing`. `Lib/models.py`
imports no flexlibs2/LCM (flavor-agnostic per its module docstring); `Lib/selection.py` capture
helpers reuse the existing `_cast`-guarded LCM access already present in the file. Runtime flavor
is the MattGyverLee/flexlibs2 fork per constitution v5.0.0 Principle II (no new fork surface used
by 011).

**Storage**: N/A — in-memory frozen dataclasses only.

**Testing**: pytest (`tests/unit/`). New fixtures reproduce the two live-proven collision classes
(affix form `'n'`→5 candidates; NaturalClass `Consonants`×2 label collision). Live LCM validation
was performed read-only via the FLExTools MCP during planning; it is an author-side assistant, not
a test dependency (constitution: MCP is non-normative).

**Target Platform**: FlexTools host on Windows (PyQt), source→target between two FLEx projects.

**Project Type**: Single project — FLExTrans-style module (`src/gramtrans/gramtrans.py` entry +
`src/gramtrans/Lib/` helpers). Feature 011 touches only `Lib/models.py` and `Lib/selection.py`.

**Performance Goals**: N/A (build runs over inventory-sized collections; the affix target project
tested has 33 affixes / 4317 entries — trivial). One extra HVO-ascending sort per target-set build.

**Constraints**: FR-009 back-compat — every new dataclass field MUST be defaulted so existing
constructors/call sites/tests stay valid unmodified. FR-010 inert — `similar_resolutions` MUST NOT
change any plan/closure/execution output (SC-004 byte-identical guarantee).

**Scale/Scope**: Two files edited; ~4 new types/fields + 2 helper extensions. No new module, no UI.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design — still passing.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. FLEx Domain Fidelity** (NON-NEGOTIABLE) | PASS | `SimilarCandidate` carries the lower-cased target **GUID** as identity (GUID-first, Principle I). No GOLD/reserved item is mutated (read-only capture). No cross-reference is written; nothing resolves-or-fails because nothing is transferred here. |
| **II. FlexTools-Compatible, flexlibs2-Direct** | PASS | No adapter layer. `Lib/models.py` stays flavor-agnostic (survives into the LibLCM sibling repo unchanged); `Lib/selection.py` capture reuses the file's existing `_cast`-guarded flexlibs2-direct access. No new dependency. |
| **III. Preview-Before-Mutate** (NON-NEGOTIABLE) | PASS (vacuous) | 011 is **data-model only**. It writes nothing to any target, adds no Move path, and `similar_resolutions` is inert until 013 consumes it (FR-010). `Lib/preview.py` / `Lib/transfer.py` are untouched. |
| **IV. Phased Merge Discipline** | PASS | 011 delivers typed vocabulary for the eventual interactive-merge phase without partially implementing it — no per-conflict prompt, no field merge, no wizard page. It is additive scaffolding chunked ahead of 012–015, each of which has its own spec. |
| **V. Referential Completeness** | PASS (N/A) | No closure is computed or transferred by 011. Candidate capture records *potential* target matches for a later UI; it neither pulls nor drops dependencies. |

**Result:** No violations. Complexity Tracking table left empty.

## Project Structure

### Documentation (this feature)

```text
specs/011-similar-resolution-datamodel/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions D1–D5 with live MCP evidence
├── data-model.md        # Phase 1 — new types + field additions + invariants
├── quickstart.md        # Phase 1 — validation/run guide (incl. collision fixtures)
├── contracts/
│   └── target-set-builders.md   # the two changed return-shape seams (D4/D5)
└── tasks.md             # Created later by /speckit-tasks (NOT by /speckit-plan)
```

### Source Code (repository root)

```text
src/gramtrans/
└── Lib/
    ├── models.py       # + SimilarCandidate, SimilarResolution (frozen);
    │                   #   Selection.similar_resolutions + similar_resolution_for
    └── selection.py    # + AffixRow.suggested_target_guid (FR-004)
                        # + PosGroupedAffixInventory.target_affix_candidates (FR-005)
                        # + PhonologyRow.matched_target_guid (FR-006)
                        # ~ _build_target_sets: return shape extended (FR-002, single caller @536)
                        # ~ build_pos_grouped_inventory: consume new shape; set suggested_target_guid
                        # ~ _phon_target_sets: add collision-aware label→guid dict (FR-006/D5)
                        # ~ build_phonology_inventory: thread label→guid to PhonologyRow
                        # + _suggested_target_guid_for(form, index) helper (FR-003)
                        # FIX _merge_row_glosses: forward suggested_target_guid (lex-qc P1)

tests/unit/             # new + regression fixtures (see quickstart.md)
```

**Structure Decision**: Single FLExTrans-style module. 011 edits exactly two existing files under
`src/gramtrans/Lib/`. No new files in `src/` (only spec docs + tests). This matches the
constitution's flat-`Lib/` layout — no `flavors/`, `core/`, or `ui/` subpackages.

## Complexity Tracking

> No Constitution Check violations. Table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

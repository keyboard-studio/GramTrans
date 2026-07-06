# Implementation Plan: Nested Preview Field Gathering

**Branch**: `023-nested-preview-gather` | **Date**: 2026-07-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/023-nested-preview-gather/spec.md`

## Summary

Today the merge-preview pane shows an affix as essentially one field (Lexeme Form), because
`props_for` gathers only entry-level scalar properties (`GetSyncableProperties`) plus custom fields.
Move, however, transfers the full nested structure — senses (gloss, definition, grammatical
info/MSA), morph type, and every allomorph (form, morph type, environments, comment). Per
constitution Principle III the preview MUST represent what Move does.

**Approach**: extend the entry-category gather to traverse child objects' **standard** fields,
emitting them into the existing flat `{field: value}` dict under **fingerprint-derived join keys**
so the existing independent-per-side fetch + `diff_props`-by-key architecture keeps working
unchanged: a source child and its target counterpart land on the same key when their fingerprints
match, giving per-field NEW/IN TARGET/SIMILAR status for free; unmatched source children fall to
all-ADDED, unmatched target children render target-only. Child fingerprints reuse the matchers that
`preview.py`/`matcher.py` already use for Move (`fingerprint_for_allomorph`, MSA/allomorph
fingerprints), so preview pairing equals Move pairing (SC-006). Display label ("Allomorph 1",
"Sense 1") and source ordering are layered on via a small `FieldDiff` extension (`display_name` +
`sort_key`) that leaves the existing alphabetical scalar behavior intact. Separately, the
MultiString custom-field read that crashes flexicon's `GetValue` gets a direct-read fallback so
those fields are no longer silently dropped (Principle I).

## Technical Context

**Language/Version**: Python 3.8+ (`from __future__ import annotations`; py38 typing per
`merge_preview.py` header).

**Primary Dependencies**: flexicon (pyflexicon) Operations API (`project.LexEntry`,
`project.LexSense`, `project.MSA`, `project.Allomorph`, `project.CustomField`); existing in-repo
`matcher.py` and `preview.py` fingerprint helpers; PyQt (only in `merge_preview_pane.py`, never in
`merge_preview.py`).

**Storage**: N/A — in-memory only. Preview cache holds plain dicts / `MergePreview` values, never
live LCM objects (FR-013, feature 012 FR-012).

**Testing**: pytest (`tests/unit`, `tests/integration`); live validation via FLExToolsMCP against
the `Ejagham Mini` → `Ejagham Full GT-Test` pair.

**Target Platform**: FlexTools host on Windows (desktop).

**Project Type**: desktop-app (PyQt module inside FlexTools).

**Performance Goals**: per-selection preview stays interactive (target < 100 ms per item); the
existing 4-tuple memoization and per-side props cache absorb repeat selections.

**Constraints**:
- `merge_preview.py` MUST remain **Qt-free** (feature 012 SC-007).
- Cache MUST retain no live LCM handles (FR-013).
- Independent per-side props fetch MUST be preserved → child join keys MUST be derivable from one
  side alone (fingerprint-based), not from cross-side coordination.
- Graceful degradation: a single unreadable field/child MUST NOT abort the preview (FR-012).

**Scale/Scope**: dozens of affixes/stems per project; each with a handful of senses/allomorphs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| **I. FLEx Domain Fidelity** | PASS — preview is read-only; no writes, no GUID mutation. The child **fingerprint** used for pairing is an identity strategy and its per-class definition is documented in `data-model.md` (satisfies the "fingerprint definition per object class MUST be documented" mandate). Directly fixes a silent-drop defect (MultiString CF), advancing "no silent drops." |
| **II. FlexTools-Compatible, flexicon-Direct** | PASS — child standard fields read via flexicon Operations; `merge_preview.py` stays Qt-free; degrades gracefully (skip + note) if a field/child cannot be read. |
| **III. Preview-Before-Mutate (NON-NEGOTIABLE)** | PASS — this feature *is* raising preview fidelity to match Move. Preview stays read-only; no Move changes. |
| **IV. Phased Merge Discipline** | PASS — no mode/disposition changes and no phase reordering. NOTE: `merge_preview.py`'s internal mode names (`NEW`/`LINK_ONLY`/`OVERWRITE`/`MERGE_KEEP`) predate the v6.0.0 vocabulary and are **out of scope** here (not renamed). |
| **V. Referential Completeness** | PASS — showing the full child closure (senses, MSA, allomorphs, environments) in preview aligns with the mandate to display the dependency closure. |

**Result**: No violations. Proceed. One justified model complexity tracked below.

**Post-Design Re-check (after Phase 1)**: Still PASS. The design keeps `merge_preview.py` and the new
`Lib/fingerprints.py` Qt-free (II); documents the per-class child fingerprint in `data-model.md` (I);
adds the SC-006 preview-vs-Move parity contract strengthening III; and changes no mode/disposition or
phase ordering (IV). The MultiString fallback converts a silent drop into a value-or-note (I). No new
violations introduced by the design artifacts.

## Project Structure

### Documentation (this feature)

```text
specs/023-nested-preview-gather/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── gather-nested-entry.md
│   ├── child-fingerprint-join.md
│   └── multistring-cf-read.md
├── checklists/
│   └── requirements.md  # from /speckit-specify
└── tasks.md             # /speckit-tasks (not created here)
```

### Source Code (repository root)

```text
src/gramtrans/Lib/
├── merge_preview.py         # PRIMARY: extend gather (child standard fields, fingerprint join
│                            #   keys, MultiString CF fallback); extend FieldDiff (display_name,
│                            #   sort_key); ordering-aware diff_props path. Stays Qt-free.
├── matcher.py               # REUSE: fingerprint_for_allomorph / fingerprint_for_msa
├── preview.py               # REUSE (extract/share): _allomorph_fingerprint, _msa_fingerprint,
│                            #   child match helpers — factor a shared fingerprint token usable
│                            #   by merge_preview.py without importing Qt or Move-execution code
└── ui/
    └── merge_preview_pane.py  # render ordered child groups (uses FieldDiff.indent + display_name)

tests/
├── unit/
│   ├── test_merge_preview_service.py   # extend: nested gather, child pairing, ordering, CF fallback
│   └── test_merge_preview_diff.py      # (diff_props) ordering + join-key matching
└── integration/
    └── test_nested_preview_e2e.py      # live-ish gather over an affix with senses + 2 allomorphs
```

**Structure Decision**: Single-project layout (Option 1). All changes are localized to the preview
subsystem (`merge_preview.py` primary, `merge_preview_pane.py` for rendering) plus a small shared
extraction of the child-fingerprint token from `preview.py`/`matcher.py`. No new top-level modules.

## Complexity Tracking

| Violation / Added Complexity | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Extend `FieldDiff` with `display_name` + `sort_key` (was: `field_name` + alpha sort only) | Nested children need a human label ("Allomorph 1 ▸ Comment") **separate** from the machine join key (fingerprint-based), plus source-order sorting that alpha can't express | Encoding order/label into `field_name` and keeping pure alpha sort collapses source order and leaks fingerprint tokens into the visible label; cross-side ordinal labels would break the independent per-side fetch |
| Extract a shared child-fingerprint token from `preview.py` | Preview pairing MUST equal Move pairing (SC-006); reusing the Move matchers is the only way to guarantee that | Re-deriving a second, independent fingerprint in `merge_preview.py` risks preview/Move divergence — the exact failure this feature exists to prevent |

# Implementation Plan: Conflict-Mode UI & Field-Level Merge (per-category ADD_NEW / MERGE / OVERWRITE)

**Branch**: `020-conflict-mode-field-merge` | **Date**: 2026-07-05 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/020-conflict-mode-field-merge/spec.md`

## Summary

Deliver roadmap build-sequence step 5: the per-category **conflict-mode selector**
(ADD_NEW / MERGE / OVERWRITE) inline on every category page, plus **field-level
conflict resolution** for IN TARGET / SIMILAR items running in `OVERWRITE`, wired
into the merge-preview pane. The spec frames this as "surface & wire existing
machinery." A crew review (lex-domain / lex-programmer / lex-author over two
cycles) plus **live FLExTools MCP probes** (Ejagham Full + Esperanto, read-only,
2026-07-05 — see [probe-results.md](./probe-results.md)) confirmed the model and
dialog layers largely exist, but surfaced **five gaps** that this plan resolves —
**not guessed**:

1. **MERGE is link-only** (`models.py:81-82`); field detection only ever runs on
   `plan.overwrites` (`conflict.py:315-317`). → **OVERWRITE-only** field
   resolution for 020; strike the "or MERGE with divergent fields" parenthetical
   from US2/FR-003 (R1).
2. **Field detection covers 4 categories** (`_OW_OPS`: pos/entry/sense/allomorph,
   `conflict.py:233-238`). → **uniform mode-SELECTOR** everywhere; field-**diff**
   is tiered by whether a category has a working syncable-scalar surface (R2).
3. **No `allowed_modes_for` API** — the Layer-1 permitted-mode gating is trapped
   as locals in `_build_default_conflict_modes` (`models.py:102-157`). → add a
   read-only `allowed_modes_for(category)` (surfacing, not redefinition — R3).
4. **`_is_protected` fails open** (`protection.py:18-38`). → invert to
   **fail-closed** + `ICmPossibility` cast (R4).
5. **Reference scope was mis-stated.** Live probe proves atomic `*RA` refs
   (`Sense.MorphoSyntaxAnalysisRA/SenseTypeRA/StatusRA`, `Allomorph.MorphTypeRA`)
   **are** in `GetSyncableProperties` and DO surface as conflicts; only `*RS`/`*OC`
   are excluded (R5).

Plus one **blocking discovery**: `GetSyncableProperties` **raises**
(`AttributeError: 'ITsString' object has no attribute 'get_String'`) for
**Phonemes** and **Environments**, reproduced on both projects — a flexicon-level
bug. Those two categories ship **mode-selector-only** in 020; the bug is filed
separately against flexicon (R6).

Net build: `allowed_modes_for` + kind-set promotion (models.py), fail-closed
`_is_protected` (protection.py), `_OW_OPS` extension for the confirmed Tier-A
categories (conflict.py), a per-category mode-selector view model + inline widget
on each wizard page, merge-preview reflecting choices, and reuse of the shipped
`detect_conflicts` / `ConflictDialog` / prior-recall machinery unchanged.

## Technical Context

**Language/Version**: Python 3 (FlexTools host). **Primary deps**: PyQt6, flexicon
(pyflexicon>=4.1), SIL.LCModel via pythonnet. **Testing**: pytest (fake handles)
for builders + model surfaces; live FLExTools MCP against **Ejagham Mini → Ejagham
Full GT-Test** (Move) and **Ejagham Full / Esperanto** (read-only detection).
**Project type**: FLExTrans-style flat `Lib/`. **Constraints**: detection is
Preview-clean (read-only); the mode selector and field resolver build a
`Selection` / `InteractiveSession` only — the sole write stays at Move
(`transfer.py`). `IsProtected` MUST be read via `ICmPossibility(x).IsProtected`
(MCP static validator rejects bare access; probe §3). **Scale/Scope**: cross-cutting
UI over ~26 category pages; field-diff wired for the ~6–7 Tier-A categories.

**Pre-wired plumbing (no work needed)**: `ConflictMode`, `MergeResolution`,
`Selection.category_conflict_modes` + `conflict_mode_for` + `_replace_conflict_modes`,
`_DEFAULT_CONFLICT_MODES`, `PlannedOverwrite.write_mode`, `ConflictPrompt`,
`MergeDecision(Log)`, `InteractiveSession` (models.py); `detect_conflicts`,
`collect_overwrite_conflicts`, `_deterministic_merge`, `load_prior_log/decision`,
`build_session_from_resolutions`, `UserCancelled` (conflict.py); `ConflictDialog`
(ui/conflict_dialog.py); `apply_isprotected_layer2` (protection.py). All verified
present against the worktree.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- **I. FLEx Domain Fidelity** — PASS. GUID-first identity preserved (detection
  matches on lowercase-normalized `ICmObject.Guid`). GOLD inviolability enforced
  two ways: Layer-1 (`allowed_modes_for` omits OVERWRITE for GOLD_RESERVED /
  CUSTOM_FIELDS) and Layer-2 (`_is_protected`, now **fail-closed** — R4). Every
  scope claim traces to a live probe or an explicit 018-probe citation
  (probe-results.md), satisfying probe-before-claim.
- **II. flexicon-Direct** — PASS. Direct `GetSyncableProperties` /
  `ApplySyncableProperties` / `ICmPossibility` usage; `allowed_modes_for` is
  in-repo (models.py), no adapter. The Phoneme/Environment `GetSyncableProperties`
  defect is upstream in flexicon and is filed there, **not** patched in this tree.
- **III. Preview-Before-Mutate** — PASS. `collect_overwrite_conflicts` and the
  fail-closed `_is_protected` are read-only (detection/Preview side); the only
  write is the existing Move path in `transfer.py`, which consumes the
  `InteractiveSession` produced during Preview. `UserCancelled` ⇒ no partial write.
- **IV. Phased Merge Discipline** — PASS. This is the Phase-2 Interactive-Merge
  surface. **FR-011 explicitly reviewed**: `ConflictMode` values and Layer-1 kind
  gating are NOT redefined — R1 keeps MERGE semantics untouched, R3's
  `allowed_modes_for` surfaces existing gating. The OVERWRITE-only decision (R1)
  is what preserves FR-011.
- **V. Referential Completeness** — PASS. Field-diff excludes RS/OC multi-valued
  references (documented limitation, R5) but never silently drops them; atomic RA
  refs surface as conflicts. Missing/unresolved references continue to route
  through the existing skip/warning channels, not silent drops.

**Known constraint (recorded, not a violation)**: module source must use
`ICmPossibility(x).IsProtected` to pass the MCP static validator even though
runtime resolves bare access (probe §3). No violations. Complexity Tracking empty.

## Project Structure

### Documentation (this feature)

```text
specs/020-conflict-mode-field-merge/
├── spec.md              # feature spec (input)
├── probe-results.md     # FLExTools MCP ground-truth (LIVE 2026-07-05) — authoritative
├── plan.md              # this file
├── research.md          # Phase 0 — R1..R8 (scope decisions + gap closures)
├── data-model.md        # Phase 1 — allowed_modes_for + fail-closed protection + UI view model
├── contracts/
│   └── conflict-mode-ui.md  # Phase 1 — C1..C6 selector/resolver/gating/preview contracts
├── quickstart.md        # Phase 1 — unit + live (Ejagham/Esperanto) validation scenarios
└── tasks.md             # Phase 2 — /speckit-tasks (NOT created here)
```

### Source Code (repository root)

```text
src/gramtrans/Lib/
├── models.py            # ADD allowed_modes_for(category); PROMOTE kind-sets
│                        #   (_MULTI_INSTANCE_CATS / _SINGLETON_CATS /
│                        #   _GOLD_RESERVED_CATS / _CUSTOM_FIELDS_CATS) from
│                        #   _build_default_conflict_modes locals to module scope.
├── protection.py        # CHANGE _is_protected: ICmPossibility cast + fail-CLOSED
│                        #   on indeterminate state + diagnostic log.
├── conflict.py          # EXTEND _OW_OPS with confirmed Tier-A categories
│                        #   (inflection_features, natural_classes, morph rules —
│                        #   after R2a live re-probe) + _find_target_*_by_guid
│                        #   finders (lowercase-normalized GUID match).
├── preview.py           # merge-preview: render planned action (create/overwrite/
│                        #   link) + field-diff from captured MergeDecisions (US5).
└── ui/
    ├── conflict_dialog.py     # REUSE as-is (resolver already complete).
    └── selection_wizard.py    # ADD inline per-category mode selector on each page
                               #   (ConflictModeChoice view model); populate from
                               #   allowed_modes_for; persist via
                               #   _replace_conflict_modes; drop stale field
                               #   decisions on mode change (FR-009).

tests/
├── unit/
│   ├── test_allowed_modes.py         # SC-001 gating per kind; invariant default∈allowed
│   ├── test_conflict_mode_persist.py # SC-002 override persists; untouched=default
│   ├── test_field_scope.py           # R5: scalar+atomic-RA in; RS/OC out; merge_eligible
│   ├── test_protection_failclosed.py # R4/US4: failed cast => protected=True + log
│   ├── test_mode_change_invalidation.py # FR-009/R8 stale-decision drop
│   └── test_tier_map.py              # FR-012 every page tiered; Tier-C blocked_reason
└── integration/
    └── test_conflict_live.py         # MCP: probe parity (probe-results.md) +
                                      #   Ejagham Mini->GT-Test OVERWRITE field-diff,
                                      #   GOLD/protected veto, prior recall, cancel.
```

**Structure Decision**: Extend the existing flat `Lib/` files in place beside the
conflict/merge machinery they augment (models/protection/conflict/preview) and add
the inline selector to the existing wizard pages — no new module files, matching
the FLExTrans flat-`Lib/` convention and the 010/018 precedent. The mode selector
is cross-cutting (FR-012): one reusable `ConflictModeChoice` view model + widget
rendered on every page, sourced from a static category→tier map (per
probe-results.md), not re-decided per run.

### Buildable scope (three tiers — probe-grounded, honest)

- **Tier A (mode selector + real field-diff)**: POS, InflectionFeature,
  NaturalClass, LexEntry, Sense, Allomorph; MorphRule pending R2a live re-probe.
- **Tier B (mode selector only; field-diff a documented no-op)**: templates,
  slots, MSAs, strata, inflection classes, stem names, exception features, variant
  types, complex-form types, adhoc/compound rules, semantic domains, gram
  categories.
- **Tier C (mode selector only; field-diff BLOCKED by flexicon bug)**: PHONEMES,
  PH_ENVIRONMENT — do NOT add to `_OW_OPS` until the flexicon
  `GetSyncableProperties` defect is fixed.

## Follow-ups

- **File flexicon bug** (separate from 020): `GetSyncableProperties` raises
  `AttributeError("'ITsString' object has no attribute 'get_String'")` for Phoneme
  and Environment; reproduced on Ejagham Full + Esperanto 2026-07-05. Cross-ref the
  bug id into probe-results.md Tier C.
- **R2a**: live re-probe MorphRule `GetSyncableProperties` against a rule-bearing
  project before wiring it into Tier A.
- **Spec edits (for /speckit-clarify or a spec touch-up)**: strike "or MERGE with
  divergent fields" from US2/FR-003 (R1); reword FR-012 to "uniform mode-selector;
  field-diff where a syncable-scalar surface exists"; correct the Assumptions
  "references out of scope" line to the atomic-RA-in / RS-OC-out rule (R5); add the
  Phoneme/Environment blocked note.

## Complexity Tracking

*No constitution violations. No deviations requiring justification.*

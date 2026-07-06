# Implementation Plan: Per-Item Disposition Model (LINK rename + UPDATE intent + auto-SKIP)

**Branch**: `022-disposition-model` | **Date**: 2026-07-05 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/022-disposition-model/spec.md`

## Summary

Formalize the cross-project transfer **disposition model** introduced conceptually
during 020 planning: replace the misleading `ConflictMode.MERGE` vocabulary with
`LINK` (its true semantics), add a non-destructive `UPDATE` intent, and compute an
honest per-item **disposition** (IGNORE / SKIP / ADD / UPDATE / OVERWRITE) so the
run report reflects what actually happened — not a phantom overwrite on an unchanged
item.

Four concrete changes:

1. **MERGE -> LINK rename** (`models.py:89`). `MERGE="merge"` is re-declared as
   `LINK="link"`. A read-time compatibility shim at `conflict_mode_for`
   (`models.py:447`) maps the legacy persisted value `"merge"` to `LINK` for at
   least one release.
2. **ADD UPDATE to `ConflictMode`** (`models.py:74` class, new member). UPDATE is
   non-destructive: source wins on diverged fields, but a target field is never
   blanked because the corresponding source field is empty. UPDATE becomes the
   default for `_MULTI_INSTANCE_CATS`; OVERWRITE is demoted to explicit opt-in.
3. **Per-item disposition computation** (`conflict.py`). The write path inspects
   field identity (2-way on first run; 3-way against the residue baseline on
   re-run) to emit SKIP for genuinely-unchanged items rather than a no-op
   overwrite. The disposition is recorded and surfaced in the run report.
4. **Auto-SKIP on re-run** (`conflict.py` / `residue.py`). When the residue
   baseline shows a field is untouched since the prior run, the item is
   auto-SKIP'd without prompting. If the source changed since the prior run, only
   that field is surfaced for re-evaluation (020 R7 pattern).

020 ships the selector and field-level resolution machinery **over the existing
enum**; 022 replaces the vocabulary and write semantics built on that base.

## Technical Context

**Language/Version**: Python 3 (FlexTools host). **Primary deps**: PyQt6, flexicon
(pyflexicon>=4.1), SIL.LCModel via pythonnet. **Testing**: pytest (fake handles) +
live FLExTools MCP against Ejagham Mini -> Ejagham Full GT-Test.
**Project type**: FLExTrans-style flat `Lib/`. **Constraints**: disposition
computation is Preview-clean (read-only); the sole write stays at Move
(`transfer.py`); UPDATE semantic must never blank a target field from an empty
source (FR-003). **Backward compat**: the `"merge"` persisted value is aliased to
LINK at one read point only (models.py `conflict_mode_for`); the residue
`merge=` wire format (`residue.py:27,96,179; conflict.py:385`) is the distinct
`MergeDecisionLog` base64 encoding and is NOT touched.

**Pre-wired plumbing (020 delivers, 022 modifies)**: `ConflictMode` enum, `allowed_modes_for`,
`_DEFAULT_CONFLICT_MODES`, `_MULTI_INSTANCE_CATS` / `_SINGLETON_CATS` / `_GOLD_RESERVED_CATS`,
`Selection.conflict_mode_for` / `_replace_conflict_modes`, `detect_conflicts`,
`collect_overwrite_conflicts`, `_deterministic_merge`, `apply_isprotected_layer2`,
per-category mode selector UI, merge-preview pane. All assumed present; 022 changes
the vocabulary and adds UPDATE semantics over that base, not the safety rails.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- **I. FLEx Domain Fidelity** -- PASS. GUID-first identity unchanged. GOLD
  inviolability preserved: `allowed_modes_for` continues to exclude OVERWRITE (and
  now UPDATE) for GOLD_RESERVED/CUSTOM_FIELDS; fail-closed `_is_protected` from 020
  R4 unchanged. Per-item disposition replaces a no-op overwrite with an honest SKIP
  -- no data is written that was not already written. The 020 probe-before-claim
  requirement carries forward; no LCM API surface is added here.
- **II. flexicon-Direct** -- PASS. No new flexicon calls. `GetSyncableProperties` /
  `ApplySyncableProperties` usage unchanged. Phoneme/Environment stay SELECTOR-ONLY
  (020 Tier C) pending the upstream `ITsString.get_String` fix; a flexicon version
  check gates their promotion (see Scope Deferrals below).
- **III. Preview-Before-Mutate** -- PASS. Disposition computation (2-way / 3-way
  field identity, SKIP downgrade) runs in the Preview/plan path (read-only).
  UPDATE writes run at Move via `transfer.py` execute path only. `UserCancelled`
  => no partial write (carried unchanged from 020).
- **IV. Phased Merge Discipline** -- PASS with amendment. **Constitution v6.0.0
  is ratified** (`.specify/memory/constitution.md`; Sync Impact Report header).
  Principle IV now explicitly covers the `{ADD_NEW, LINK, UPDATE, OVERWRITE}` mode
  vocabulary and the `{IGNORE, SKIP, ADD, UPDATE, OVERWRITE}` per-item disposition.
  This feature is the *implementation* of the v6.0.0 amendment. The prior enum
  (`MERGE="merge"`) is retired via shim, not via silent rename-and-break.
- **V. Referential Completeness** -- PASS. SKIP disposition emits no write and
  leaves references untouched. UPDATE writes only the differing fields; missing or
  unresolved references continue through the existing skip/warning channels.

No violations. Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/022-disposition-model/
├── spec.md              # feature spec (input)
├── plan.md              # this file
└── tasks.md             # ordered task checklist
```

### Source Code (worktree: GramTrans-020-conflict-mode-field-merge)

```text
src/gramtrans/Lib/
├── models.py
│   # line 74   -- ConflictMode class: add LINK="link", UPDATE="update"; remove MERGE
│   # line 89   -- formerly MERGE="merge" declaration
│   # line 149,151,153,156 -- _DEFAULT_CONFLICT_MODES / _build_default_conflict_modes:
│   #              update all MERGE refs to LINK; set MULTI_INSTANCE default to UPDATE
│   # line 201,205 -- MergeResolution enum: NOT touched (distinct; unrelated to rename)
│   # line 355   -- Selection.category_conflict_modes field annotation: update type hint
│   # line 447   -- conflict_mode_for(): add "merge" -> LINK compatibility shim
│   # line 450   -- remaining MERGE sentinel refs -> LINK
│   # allowed_modes_for(): add UPDATE to _MULTI_INSTANCE_CATS permitted set
│
├── conflict.py
│   # line 385  -- MergeDecisionLog base64 residue wire format: NOT touched
│   # disposition computation: 2-way (first run) and 3-way (re-run baseline)
│   # SKIP downgrade: an item with zero field diffs is SKIP, not no-op overwrite
│   # UPDATE write semantic: apply source fields that diverge; skip source-empty fields
│   # auto-SKIP: residue baseline shows field untouched -> skip without prompting
│   # changed-since-baseline: surface for re-evaluation only (020 R7 pattern)
│
├── protection.py
│   # line 54   -- apply_isprotected_layer2: LINK is the safe-downgrade target
│   #              (was MERGE); one rename only
│
├── residue.py
│   # lines 27,96,179 -- MergeDecisionLog base64 encoding: NOT touched
│   # 3-way baseline read: expose prior-run baseline per item for disposition compare
│
└── ui/
    └── selection_wizard.py
        # line 128  -- _CONFLICT_LABELS: "MERGE" label -> "LINK" / "Link to existing"
        # line 184  -- allowed-modes fn: add UPDATE to MULTI_INSTANCE offered set
        # line 186  -- allowed-modes fn: secondary UPDATE reference
        # line 1275 -- default wiring: MULTI_INSTANCE default -> UPDATE (was ADD_NEW)

tests/
├── unit/
│   ├── test_conflict_mode_model.py
│   │   # line 66  -- .value == "link" (was "merge")
│   │   # line 97  -- LINK member exists; MERGE does not
│   │   # line 163 -- allowed_modes_for MULTI_INSTANCE includes UPDATE
│   │   # line 261 -- shim: "merge" string -> LINK
│   └── test_wizard_page_flow.py
│       # line 423 -- conflict-mode control shows LINK not MERGE; UPDATE offered
└── integration/
    └── test_conflict_live.py   # UPDATE behavioral assertions; SKIP vs OVERWRITE
```

## Scope / Non-Scope

### In Scope (022)

- ConflictMode.MERGE -> LINK rename throughout model, UI, and tests (~45 refs)
- Read-time compatibility shim: persisted `"merge"` -> LINK at `conflict_mode_for` (one shim point)
- ConflictMode.UPDATE: new enum member; non-destructive write semantic; UPDATE as default for MULTI_INSTANCE
- Per-item disposition (IGNORE / SKIP / ADD / UPDATE / OVERWRITE) computed and reported
- True SKIP: zero-field-diff items reported SKIP, not no-op overwrite
- Auto-SKIP on re-run via residue baseline (3-way field identity); first transfer falls back to 2-way
- Source-changed-since-baseline detection: surface for re-evaluation, not silent reapply
- flexicon version check to gate Phoneme/Environment UPDATE detection (auto-enables when ITsString fix ships)

### Deferrals (out of scope -- do NOT implement in 022)

1. **LINK stale-reference re-pointing** -- a "re-point a stale LINK reference to a new target GUID" variant is deferred to **023** (Ruling: scope decision, 2026-07-05).
2. **Phoneme / PH_ENVIRONMENT field-diff** -- stays SELECTOR-ONLY in 022; gated behind a flexicon version check. Root cause: `EnvironmentOperations.GetSyncableProperties` (~:694-698) and `PhonemeOperations.GetSyncableProperties` (~:1309-1319) call `.get_String()` unguarded on scalar `ITsString` fields (`StringRepresentation`, `BasicIPASymbol`); a ~3-5 line flexicon-side guard fixes it. Bug filed separately (Ruling Y). The flexicon version check will auto-promote these categories to Tier A when the fix ships.
3. **MergeResolution enum rename** -- the distinct `MergeResolution` enum at `models.py:201/205` governs field-level merge decisions and is NOT renamed or touched in 022; it is an unrelated vocabulary.

## Decision Rulings (encode, do not re-litigate)

| Ruling | Decision |
|---|---|
| MERGE rename | Renamed to LINK. Persisted value "merge" shimmed to LINK at read time (models.py conflict_mode_for, one point). |
| UPDATE default | UPDATE is the default for MULTI_INSTANCE categories. OVERWRITE is opt-in. |
| UPDATE semantic | Non-destructive: source wins on diverged fields; target field is never blanked from an empty source field. |
| OVERWRITE contrast | Wholesale source-wins; may blank a target field from an empty source. Pre-022 behavior preserved exactly. |
| Auto-SKIP | Residue baseline drives auto-SKIP on re-run. Prompt only where baseline shows drift (source changed). |
| Phoneme/Environment | SELECTOR-ONLY in 022; gated behind flexicon version check (Ruling Y). |
| LINK re-pointing | Out of scope for 022; filed as 023 follow-up. |
| MergeResolution enum | NOT renamed, NOT touched. |

## Risk Notes

- **~45 test refs**: `test_conflict_mode_model.py` and `test_wizard_page_flow.py` plus
  scatter across the suite all reference `MERGE` or `"merge"`. Every ref must be updated
  or it breaks on import. A grep-first T001 catalogs them before any code change.
- **Backward-compat shim**: the shim is at exactly one read point (`conflict_mode_for`,
  `models.py:447`). If a second read path is discovered during implementation it must
  also receive the shim -- the spec commits to "no error on load" for at least one
  release.
- **UPDATE is new code**: unlike LINK (rename only), UPDATE requires a new write
  semantic in `conflict.py`. The non-destructive invariant (never blank from empty
  source) must be verified field-by-field in the execute path, not assumed from
  the enum name alone.
- **3-way baseline read**: the residue baseline integration must not disturb the
  `MergeDecisionLog` base64 wire format (residue.py:27,96,179; conflict.py:385).
  Read-only access to the baseline for field comparison is safe; writing the format
  is out of scope.
- **020 must ship first**: 022 replaces vocabulary and write semantics built on the
  020 selector and field-diff machinery. 022 cannot ship without 020.

## Complexity Tracking

*No constitution violations. No deviations requiring justification.*

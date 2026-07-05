# Quickstart / Validation — 020 Conflict-Mode Field Merge

Runnable validation scenarios proving the feature works end-to-end. Unit builders
use fake handles (no LCM); live scenarios use the FLExTools MCP against the
constitution's validation pair **Ejagham Mini → Ejagham Full GT-Test** (throwaway
target). See [contracts/conflict-mode-ui.md](./contracts/conflict-mode-ui.md) and
[data-model.md](./data-model.md) for the surfaces referenced here;
[probe-results.md](./probe-results.md) for the authoritative API facts.

## Prerequisites

- Worktree: `GramTrans-020-conflict-mode-field-merge` (branch
  `020-conflict-mode-field-merge`).
- flexicon installed editable: `pip install -e D:/Github/_Projects/_LEX/flexlibs2`.
- FLExTools MCP session started **read-only** for detection probes; a **throwaway
  write** target (Ejagham Full GT-Test) only for the Move scenarios.
- Test source: **Ejagham Mini** (or Ejagham Full); **Esperanto** as an alternate
  source. Never write to Ejagham Mini/Full/Esperanto — target GT-Test only.

## Unit (pytest, fake handles — no LCM)

Run: `pytest tests/unit -k conflict_mode or field_merge`

1. **allowed_modes_for gating (US1 / SC-001)** — assert per kind:
   MULTI_INSTANCE ⇒ `{ADD_NEW, MERGE, OVERWRITE}`; GOLD_RESERVED ⇒ `{MERGE}`;
   CUSTOM_FIELDS ⇒ `{MERGE}`; SINGLETON ⇒ `{MERGE, OVERWRITE}`. Assert
   `conflict_mode_for(cat) in allowed_modes_for(cat)` for every category.
2. **Override persists (US1 / SC-002)** — set a MULTI_INSTANCE category to
   OVERWRITE via `_replace_conflict_modes`; assert `conflict_mode_for` returns it;
   assert an untouched category still returns its Layer-1 default (key absent).
3. **detect_conflicts field scope (US2 / R5)** — feed a src/tgt props pair with a
   differing scalar (`Name`), an identical scalar, an int (`HomographNumber`), and
   an atomic RA (`MorphTypeRA`). Assert: identical suppressed; `Name` prompt with
   `merge_eligible=True`; `HomographNumber` prompt `merge_eligible=False`; RA
   prompt present `merge_eligible=False`. No RS/OC keys appear.
4. **Per-field application (US2 / SC-003)** — build decisions (one TAKE_SOURCE,
   one KEEP_TARGET) and assert the filtered props dict contains only the
   TAKE_SOURCE key before `ApplySyncableProperties`.
5. **_is_protected fail-closed (US4 / R4)** — pass an object whose
   `ICmPossibility` cast fails; assert `_is_protected` returns `True` and logs.
   Pass a concrete unprotected possibility; assert `False`.
6. **Mode-change invalidation (FR-009 / R8)** — capture field decisions under
   OVERWRITE, switch the category to ADD_NEW, assert the category's
   `merge_decisions_by_guid` entries are dropped.
7. **Tier map (FR-012)** — assert every GrammarCategory page maps to a tier
   (A/B/C) and that Tier-C categories (PHONEMES, PH_ENVIRONMENT) are
   selector-only with a non-empty `blocked_reason`.

## Live (FLExTools MCP — read-only detection)

Probe (read-only) against **Ejagham Full**, reproducing probe-results.md:

- `GetSyncableProperties` on POS / InflectionFeature / NaturalClass / LexEntry /
  Sense / Allomorph returns the §1 key sets.
- `GetSyncableProperties` on a Phoneme and an Environment **raises** the ITsString
  AttributeError (Tier C confirmation).
- `ICmPossibility(pos).IsProtected` resolves to a bool (US4 cast path).

Expected: matches [probe-results.md](./probe-results.md) exactly. Any drift ⇒
update probe-results.md before implementing.

## Live (Move — throwaway target only)

Source **Ejagham Mini** → target **Ejagham Full GT-Test**:

1. **OVERWRITE field-diff (US2 / SC-003)** — pick an IN TARGET POS whose source
   and target differ on `Description` and `Abbreviation`; set category to
   OVERWRITE; resolve `Description`=TAKE_SOURCE, `Abbreviation`=KEEP_TARGET;
   Move; verify the target POS has the new Description and the old Abbreviation.
2. **GOLD/protected veto (US4 / SC-004)** — attempt OVERWRITE on a GOLD_RESERVED
   category ⇒ not selectable. Attempt TAKE_SOURCE on a protected target field ⇒
   vetoed; target field unchanged after Move.
3. **Prior-decision recall (US3 / SC-005)** — re-run scenario 1 with unchanged
   source; verify the resolution dialog preselects the prior per-field decisions.
4. **Preview reflects choices (US5 / SC-006)** — set a category to OVERWRITE with
   field decisions; open merge-preview; verify it shows "overwrite" and exactly
   the chosen changed fields. A default-mode category shows pre-020 behavior.
5. **Cancel = no write (SC-007)** — open the resolver, Cancel; verify the target
   is byte-unchanged for that item.

Attach pre/post Import Residue artifacts for the Move scenarios (constitution
Verification gate).

## Out of scope (documented, not tested here)

- MERGE-mode field-level resolution (R1 — post-020).
- Field-diff for Tier-B categories (selector-only; field-diff a no-op).
- Field-diff for Tier-C PHONEMES / PH_ENVIRONMENT (R6 — blocked by flexicon bug).
- RS/OC multi-valued reference merge (R5 — allomorph environments, POS template
  slots flagged future scope).

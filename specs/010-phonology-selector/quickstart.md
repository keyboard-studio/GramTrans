# Quickstart: Phonology Selector (Model-B) — Validation Guide

Runnable validation for feature 010. Unit scenarios use fake handles; live scenarios use the
FlexTools MCP against **Ejagham Mini → Ejagham Full GT-Test** (restore a fresh target first).

## Prerequisites

- flexlibs2 fork installed (`pip install -e D:/Github/_Projects/_LEX/flexlibs2`).
- Fresh target for live runs:
  ```powershell
  & 'C:\Program Files\SIL\FieldWorks 9\FieldWorks.exe' -restore `
    'D:\Github\_Projects\_LEX\GramTrans\backups\Ejagham Full.fwbackup' `
    -db 'Ejagham Full GT-Test' -include c
  ```

## Unit (pytest, fake handles)

```powershell
python -m pytest tests/unit/test_phonology_inventory.py tests/unit/test_leaf_item_picks.py `
  tests/unit/test_strata_gating.py tests/unit/test_phonology_excluded_lossy.py -q
```

| Scenario | Asserts | Spec |
|----------|---------|------|
| Inventory build | 5 groups; counts match source; all rows preselected; empty category → empty rows, no error | SC-001, FR-002/006 |
| Target status | source=target ⇒ every row `in_target`; fresh ⇒ `new`; target=None ⇒ status `None` | SC-005, FR-007 |
| leaf_item_picks filter | key present ⇒ only those GUIDs enumerated; key absent ⇒ all (existing behavior unchanged) | FR-005, R1 |
| Strata gating | ≥1 rule kept ⇒ `categories[STRATA]=True`; rules off / block off ⇒ no strata | SC-003/004, FR-009 |
| EXCLUDED-LOSSY | kept rule + deselected+absent NC ⇒ 1 entry-centric warning; kept rule + deselected+absent direct phoneme ⇒ 1 warning; kept NC + deselected+absent phoneme ⇒ 1 warning; N omissions ⇒ aggregated | US5, FR-010/011, SC-006 |

## Live (FlexTools MCP)

### Scenario A — Whole block, all preselected (US1)
1. Open wizard, bind target. **Then** page 2 is Phonology; all five categories render
   preselected — 32 phonemes, 5 natural classes, 2+ environments, features, rules — with counts.
2. Advance unchanged → Preview. **Expect** phonology PlannedActions per category = source counts
   (SC-002); strata included (rules present); zero warnings.

### Scenario B — Whole-block off (US2)
1. Toggle the whole block off. **Expect** Preview shows zero phonology actions and zero strata
   actions (SC-003).

### Scenario C — Per-item trim (US2 / FR-005)
1. Block on; deselect 3 of 32 phonemes that no kept NC/rule references. **Expect** plan
   transfers 29 phonemes, no warning.
2. Deselect a phoneme a kept natural class references, target lacking it. **Expect** one
   entry-centric EXCLUDED-LOSSY warning naming the NC (US5 sc1); Move pops ONE confirm dialog.

### Scenario D — Rule-gated strata (US3 / FR-009)
1. Deselect all phonological rules, keep phonemes + NCs. **Expect** no strata actions planned
   (SC-004); no strata row ever visible.

### Scenario E — Idempotency regression (spec-005 FR-307)
1. Re-run whole-block Move on an already-populated target. **Expect** already-present-by-GUID
   phonology items skip; no duplicate creates — confirming the enumerate-filter change did not
   disturb spec-005 behavior.

## Success gate

All unit scenarios green; live Scenarios A–E match expectations; the 324+ pre-existing unit
tests remain green (leaf_item_picks absent-key back-compat).

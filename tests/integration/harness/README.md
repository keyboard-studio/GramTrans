# GramTrans End-to-End Validation Harness

Pytest-driven end-to-end validation that a full GramTrans transfer **persists**
and is **idempotent** against a live FLEx project pair.

## What's here

| File | Purpose |
|------|---------|
| `restore.py` | Shells out to FieldWorks.exe to restore the target from a `.fwbackup` (clean baseline per run). Not a test. |
| `full_run.py` | Orchestration helpers: build the full Selection, run source RO -> preview -> move, reopen and count inventory. Not a test. |
| `../test_full_workflow_e2e.py` | The pytest module that ties it together. |

## How to run

The E2E module is **double-gated** so it never runs by accident: it skips unless
`flexicon` is importable **and** `GRAMTRANS_E2E=1`.

```
set GRAMTRANS_E2E=1 && set GRAMTRANS_DEBUG=1 && pytest tests/integration/test_full_workflow_e2e.py -m integration -v
```

`GRAMTRANS_DEBUG=1` turns on the export/persist diagnostic logging in
`Lib/debuglog.py` (log file under the system temp dir); the harness also sets it
programmatically, but setting it in the shell captures the banner too.

To collect (and skip) without running anything:

```
pytest tests/integration -q
```

## Prerequisites

- **FieldWorks 9** installed. The restore helper finds `FieldWorks.exe` via the
  `GRAMTRANS_FW_EXE` env var, else scans
  `C:\Program Files\SIL\FieldWorks 9\` and the `(x86)` variant.
- **Source** project `Ejagham Mini` present.
- **Target** project `Ejagham Full GT-Test` present at
  `C:\ProgramData\SIL\FieldWorks\Projects\Ejagham Full GT-Test`.
- **Target is CLOSED in FLEx** (a locked project cannot be restored).
- At least one `*.fwbackup` in the repo `backups/` folder (newest is used).

Any missing prerequisite results in a `pytest.skip` with an actionable message,
never a hard error.

## What each test proves

- **`test_persist_confirmation`** (the #1 goal): restore clean -> baseline count
  -> full transfer with **Custom Fields enabled** -> reopen fresh -> assert the
  inventory grew. Proves writes survived the `PATH-CLOSE-REBIND` custom-field
  branch of `api.execute_move` (the historical "export doesn't persist" bug).

- **`test_full_selection_and_idempotency`**: restore -> run #1 creates objects
  (`plan.actions > 0`) -> run #2 **without restore** creates ~0 new objects
  (`plan.actions == 0`); already-present/skip is fine. A normalized `RunReport`
  snapshot is written to `_snapshots/full_e2e_post.json` on first run and diffed
  on subsequent runs (fails on drift; delete the file to re-baseline).

## Selection under test

`build_full_selection()` enables **every** `GrammarCategory` except
`GrammarCategory.STEMS`, with all pick-sets empty (engine walks all POSes and
transfers all leaf items). Custom Fields is included -- that's what exercises the
persist branch.

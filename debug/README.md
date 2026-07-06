# debug/ — live diagnostic tooling

Runnable diagnostics for the GramTrans transfer engine. These are **not** part
of the pytest suite; you run them directly against a live FLEx host to see what
a full transfer actually does and where it falls short.

## coverage_report.py

Copies **everything** from a source project into a target and logs per-category
**gaps** (selected types whose source items did not land in the target).

```powershell
# from the repo root, with the target CLOSED in FLEx:
$env:GRAMTRANS_SOURCE = "Ejagham Mini"    # optional (default)
$env:GRAMTRANS_TARGET = "Target"           # optional (default)
python debug/coverage_report.py
#   --no-restore   use the target as-is (skip the baseline restore)
#   --once         skip the idempotency second run
```

What it does:
1. Restores the target baseline from the newest `backups/*.fwbackup`
   (the archived `.fwdata` is renamed to the target project name).
2. Inventories the target (before) and the source.
3. Runs a full transfer (all categories except STEMS) — run #1.
4. Re-inventories the target (after).
5. Runs a second transfer with no restore to check idempotency.
6. Prints a per-category table (SOURCE / tgt-before / tgt-after / delta /
   run1-plan) + an explicit **GAPS** section, and writes it to
   `debug/logs/coverage_report.txt`.

Prerequisites: `flexicon` installed; source + target present under
`C:\ProgramData\SIL\FieldWorks\Projects`; target closed in FLEx; a
`*.fwbackup` in `backups/`.

The GAP heuristic flags a category when the source has items but the target
neither already held them nor gained them (delta 0 and after < source),
excluding canonical GOLD lists (e.g. `semantic_domains`) the target is expected
to already contain.

Reuses the live harness under `tests/integration/harness/` (restore + full_run).
Generated logs land in `debug/logs/` (git-ignored).

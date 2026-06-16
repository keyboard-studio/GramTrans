# Contract: Run Report

**Plan**: [../plan.md](../plan.md)
**Data Model**: [../data-model.md](../data-model.md) (entity E6)

The `RunReport` is the only artifact `ui/stats_panel.py` consumes, and it is the
artifact `tests/integration/` snapshot for SC-002 / SC-004 verification.

## Invariants (engine MUST guarantee)

- For every `PlannedAction` produced by Preview: in the corresponding Move-Mode
  report it appears as either `+1 added` (count) or `+1 skipped` (count, with a
  matching `Skip` entry in `skips`). **No silent disappearance** (FR-018).
- For every user-selected source piece across categories: either it appears in some
  category's `added`/`skipped` count, or its closure-pulled-in dependency does.
  (User-selected pieces with closure-off mode whose deps cannot be satisfied become
  Skips with `BARE_BONES_MISSING_CLOSURE`.)
- `skips` is **deduplicated by `(category, source_guid)`**. The same item is never
  reported as skipped twice.
- `identity_remap` is non-empty only when at least one LCM class refused
  GUID-on-create (R6). Each entry: `source_guid → actual_target_guid`.
- `wall_clock_seconds` is the time from "Preview clicked" (Preview Mode) or
  "Move clicked" (Move Mode) to `RunReport` construction. It includes UI render
  for the stats panel? **No** — measured before the panel render call.

## Display contract (`stats_panel.py`)

Per FR-017, the panel MUST show:

```text
┌─ Run Report (Preview | Move) ──────────────────────────────┐
│ Source: <source_project_name>                              │
│ Target: <target_project_name>                              │
│ Run ID: <run_id>                                           │
│ Elapsed: <wall_clock_seconds>s                             │
│                                                            │
│ Per category:                                              │
│  Affixes               12 added  (+3 by closure)   1 skip  │
│  Templates              2 added                    0 skip  │
│  Inflection Features    7 added  (+7 by closure)   0 skip  │
│  Custom Fields          4 added                    0 skip  │
│  ...                                                       │
│                                                            │
│ Skips (1):                                                 │
│  - Affixes / <guid-or-name>: UNMAPPED_WS (`seh-fonipa`)    │
│                                                            │
│ Identity remap (0):  -                                     │
└────────────────────────────────────────────────────────────┘
```

Implementation detail (non-normative): the rendering is a `QTextEdit` or
`QTableWidget`; choice doesn't affect this contract.

## Snapshot format for integration tests

For SC-002 / SC-004 verification, integration tests serialize `RunReport` to a
deterministic JSON form. The shape:

```json
{
  "mode": "MOVE",
  "context": {
    "run_id": "GT-20260616-093015",
    "source_project_name": "ToySource",
    "target_project_name": "EmptyTarget",
    "started_at": "2026-06-16T09:30:15"
  },
  "per_category": {
    "AFFIXES": {"added": 12, "skipped": 1, "closure_pulled_in": 3},
    "TEMPLATES": {"added": 2, "skipped": 0, "closure_pulled_in": 0}
  },
  "skips": [
    {
      "category": "AFFIXES",
      "source_guid": "...",
      "reason": "UNMAPPED_WS",
      "detail": "WS `seh-fonipa` not mapped"
    }
  ],
  "identity_remap": {},
  "wall_clock_seconds": 3.42
}
```

Field ordering MUST be stable so snapshot diffs are meaningful. Helper:
`RunReport.to_snapshot_json()` lives in `core/report.py`.

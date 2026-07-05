# Data Model: Phase 0 — Additive Grammar Transfer

**Plan**: [plan.md](plan.md)
**Spec**: [spec.md](spec.md) (see Key Entities)
**Date**: 2026-06-16

This document captures the in-module data model — the Python-level structures the
engine passes around. It is **not** the LCM data model; LCM object shapes are
governed by FieldWorks and are accessed via direct flexicon imports per
constitution v5.1.0 Principle II (no flavor-adapter contract in this repo).
flexicon is the standalone `pyflexicon>=4.1` package (a standalone independent
project, NOT a fork of stock flexicon) that natively provides the `WritingSystems`
enumeration fix and the `ApplySyncableProperties` method.

Conventions:
- Frozen dataclasses unless mutation is intrinsic.
- Identifiers favor `str` GUIDs (LCM's GUID type → str at the module boundary).
- There is no `Flavor` enum in v5.1.0: every action in this repo is flexicon
  by construction; the Phase 3 LibLCM-fork sibling repo defines its own runtime
  type if needed.

---

## E1. RunContext

The run-scope state captured once at module launch. Built by `Lib/ui/main_window.py`
once the source is detected and the target picked.

| Field | Type | Notes |
|-------|------|-------|
| `source_handle` | LCM project handle | Read-only project handle to the open FlexTools host project. |
| `source_project_name` | `str` | Used in the Import Residue tag (E5). |
| `target_handle` | LCM project handle | Opened for write. |
| `target_project_name` | `str` | For display + audit. |
| `run_id` | `str` | `GT-YYYYMMDD-HHMMSS` per Q5. Generated at `RunContext` construction. |
| `started_at` | ISO-8601 `str` | Same instant the `run_id` was generated. |

Invariants:
- `source_handle != target_handle` (FR-019).
- `run_id` matches the timestamp portion of `started_at`.

---

## E2. Selection

The user's category and per-item choices, captured in `Lib/selection.py`.

| Field | Type | Notes |
|-------|------|-------|
| `categories` | `dict[GrammarCategory, bool]` | Whether each enumerated category (FR-004) is on. |
| `include_closure` | `bool` | The dependency-closure toggle from the main window (Principle V; FR-013). |
| `affix_picks` | `frozenset[str]` | Source GUIDs of individually selected affixes. Only meaningful when `categories[AFFIXES]` is on. Empty set + `categories[AFFIXES]=True` means "all affixes". |
| `template_picks` | `frozenset[str]` | Source GUIDs of selected templates. Same semantics as `affix_picks`. |

`GrammarCategory` is an `Enum` of the FR-004 list:
`WRITING_SYSTEMS_CHECK`, `GRAM_CATEGORIES`, `INFLECTION_FEATURES`, `CUSTOM_FIELDS`,
`INFLECTION_CLASSES`, `STEM_NAMES`, `EXCEPTION_FEATURES`, `VARIANT_TYPES`,
`COMPLEX_FORM_TYPES`, `ADHOC_RULES`, `COMPOUND_RULES`, `AFFIXES`, `SLOTS`, `TEMPLATES`.

Invariants:
- If `affix_picks` is non-empty, `categories[AFFIXES]` MUST be true.
- If `categories[AFFIXES]` is true and `affix_picks` is empty, all affixes are
  selected (the "category-all" sentinel).
- Same rules for `template_picks` ↔ `TEMPLATES`.

---

## E3. WSMapping

The user's writing-system mapping (Clarification Q3, FR-011). Built in
`Lib/ui/ws_mapping_dialog.py`, validated in `Lib/ws_mapping.py`.

| Field | Type | Notes |
|-------|------|-------|
| `entries` | `tuple[WSMappingEntry, ...]` | One entry per source WS *actually referenced* by the current Selection (computed during preview). |

`WSMappingEntry`:

| Field | Type | Notes |
|-------|------|-------|
| `source_ws_id` | `str` | Source WS identifier (e.g., `seh`, `seh-fonipa`). |
| `source_ws_kind` | `WSKind` enum | `VERNACULAR` or `ANALYSIS`. |
| `target_ws_id` | `str` | Target WS identifier. May equal `source_ws_id` if already present. |
| `create_in_target` | `bool` | If True, `target_ws_id` does not yet exist in the target and MUST be created before any other writes. |

Invariants:
- Every source WS referenced by a selected item appears in `entries` exactly once.
- Mapping is 1:1: no two `entries` share `target_ws_id` unless they share
  `source_ws_id`. (Phase 0 forbids many-source-to-one-target collapsing.)
- `create_in_target` is true ⇒ the WS does not exist in the target at preview time.

---

## E4. RunPlan

The immutable plan produced by `Lib/preview.py`. Move Mode consumes this; nothing
else does. Preview Mode is "compute, display, return without mutating target".

| Field | Type | Notes |
|-------|------|-------|
| `context` | `RunContext` | The session's context (E1). |
| `selection` | `Selection` | The user's choices (E2). |
| `ws_mapping` | `WSMapping` | Resolved mapping (E3). |
| `actions` | `tuple[PlannedAction, ...]` | Ordered list of additions (categories before their dependents). |
| `skips` | `tuple[Skip, ...]` | Items that will not be transferred, with reasons. |
| `identity_remap` | `dict[str, str]` | Source GUID → planned-target GUID for cases where GUID-on-create is denied (R6). Empty in the common case. |

Invariants:
- `actions` is topologically ordered: dependencies precede dependents.
- No GUID appears in both `actions` and `skips` for the same category.
- Every Skip has a non-empty `reason`.

### E4a. PlannedAction

| Field | Type | Notes |
|-------|------|-------|
| `category` | `GrammarCategory` | Category of this action. |
| `source_guid` | `str` | GUID of the source piece. |
| `intended_target_guid` | `str` | Same as `source_guid` unless `identity_remap` says otherwise. |
| `summary` | `str` | Human-readable one-line summary for the Preview UI. |
| `pulled_in_by` | `tuple[str, ...]` | Source GUIDs that caused this action via closure (empty for user-selected items). |

### E4b. Skip

| Field | Type | Notes |
|-------|------|-------|
| `category` | `GrammarCategory` | |
| `source_guid` | `str` | |
| `reason` | `SkipReason` enum | See below. |
| `detail` | `str` | Human-readable detail (e.g., "WS `seh-fonipa` not mapped"). |

`SkipReason`:
`UNMAPPED_WS`, `DEPENDENCY_UNRESOLVED`, `GOLD_INVIOLABLE`,
`GUID_CONFLICT_NO_OVERRIDE` (reserved for Phase 1; unused in Phase 0),
`UNSUPPORTED_LCM_TYPE`, `BARE_BONES_MISSING_CLOSURE` (closure-off mode +
prerequisites absent).

---

## E5. ImportResidueTag

The structured tag (Q5, FR-010) written to every newly added target object.

| Field | Type | Notes |
|-------|------|-------|
| `prefix` | `str` | Literal `"GT"`. |
| `run_id` | `str` | `GT-YYYYMMDD-HHMMSS`. |
| `source_project_name` | `str` | From `RunContext.source_project_name`. |
| `timestamp` | ISO-8601 `str` | From `RunContext.started_at`. |

Serialization (`Lib/residue.py`):

```text
GT|<run_id>|<source_project_name>|<timestamp>
```

Carrier (per FR-010, see [research.md R7](research.md#r7-import-residue-tag-location)):
- **Carrier A** — written directly into the LCM `LiftResidue` field on object
  classes that expose it (Lex-related + `IMoForm`, `IMoMorphSynAnalysis`).
- **Carrier B** — appended to the `Description` multistring with the line prefix
  `[GT-Tag]: ` for grammar-piece classes that lack `LiftResidue`.

Parser (`parse(s: str) -> ImportResidueTag | None`) accepts both forms: it scans
for the line that starts with `[GT-Tag]: GT|` (Carrier B) and falls back to
treating the entire string as a Carrier A tag if no marker line is found.

Invariants:
- `prefix == "GT"` (so Phase 1/2 can detect "this came from GramTrans" with a single
  startswith check).
- `run_id` matches the timestamp.

---

## E6. RunReport

Output of a Preview or Move run. Drives `Lib/ui/stats_panel.py` (FR-017).

| Field | Type | Notes |
|-------|------|-------|
| `context` | `RunContext` | |
| `mode` | `RunMode` enum | `PREVIEW` or `MOVE`. |
| `per_category` | `dict[GrammarCategory, CategoryReport]` | One per category that had any activity. |
| `skips` | `tuple[Skip, ...]` | Aggregate of all category-level skips. |
| `identity_remap` | `dict[str, str]` | Carried from the plan, populated only if non-empty. |
| `wall_clock_seconds` | `float` | For SC-001 verification. |

`CategoryReport`:

| Field | Type | Notes |
|-------|------|-------|
| `added` | `int` | "Would add" in Preview Mode; "Added" in Move Mode. |
| `skipped` | `int` | Count of items in `skips` belonging to this category. |
| `closure_pulled_in` | `int` | Count of items added solely because of closure (not directly user-selected). |

Invariants:
- For every `PlannedAction` in the run plan: either it became `+1 added` in the
  corresponding category, or it became a Skip in the corresponding category — never
  silently absent (FR-018).
- In Preview Mode, `wall_clock_seconds` does not include any LCM mutation time
  because there is none.

---

## Relationships

```text
RunContext ─┐
            ├─> RunPlan ─> RunReport
Selection ──┤
WSMapping ──┘
                       ImportResidueTag ── attached to each
                                          target object on Move
```

- `RunContext` is built once.
- `Selection` and `WSMapping` are updated interactively in the main window.
- A `RunPlan` is rebuilt on every Preview click; Move Mode consumes the most-recent
  plan only if `(Selection, WSMapping)` have not changed since.
- `RunReport` is the only thing the stats panel reads.

---

## State transitions (mode gating in the UI)

```text
[Start]
  │
  ▼
Source detected, target picker shown
  │ (user picks target ≠ source)
  ▼
Categories + closure-toggle + (optional per-affix tree, per-template tree)
  │ (user clicks Preview)
  ▼
WS mapping dialog — compute required WSs from current Selection
  │ (user maps every required WS; may create in target)
  ▼
PREVIEW_READY  ────────────────► Move button enabled
  │                                   │
  │ (user changes selection)          │ (user clicks Move)
  ▼                                   ▼
PREVIEW_STALE  ◄── Move button     MOVE_RUNNING → RunReport(MOVE)
  │ disabled                          │
  │ (user clicks Preview again)        ▼
  ▼                                  [Stats panel]
PREVIEW_READY ...
```

The gate `PREVIEW_READY → MOVE_RUNNING` is the mechanical enforcement of
Principle III.

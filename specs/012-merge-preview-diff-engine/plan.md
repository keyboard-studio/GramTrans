# Implementation Plan: Merge-Preview Diff Engine & HTML Rendering

**Branch**: `012-merge-preview-diff-engine` | **Date**: 2026-07-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/012-merge-preview-diff-engine/spec.md`

## Summary

Feature 012 adds one new **pure, Qt-free** module — `src/gramtrans/Lib/merge_preview.py` —
that computes a field-by-field, writing-system-aware diff of what transferring a SIMILAR
source item would do to a chosen target item, and renders it as escaped, colorized,
font/direction-aware HTML. It has three layers stacked in one file:

1. **Pure diff core** (`diff_props` + `DiffSegment`/`FieldDiff`/`MergePreview`) that
   *mirrors* — never imports — the `_deterministic_merge` semantics in
   [conflict.py](../../src/gramtrans/Lib/conflict.py) across four conflict modes
   (NEW, LINK-ONLY, OVERWRITE, MERGE-KEEP) and a value-shape dispatch
   (multistring dict / plain string / list-tuple-set / scalar / other-object).
2. **LCM props fetch + registries** (`props_for`, `ws_role_map`) that pull a comparable
   `{field: value}` dict per transfer category via `GetSyncableProperties`, with
   **direct-multistring fallbacks** for the three fork-gap categories (Slots, Phonological
   Features, Stem Names), plus a ws-id → `WsRole` classifier.
3. **HTML rendering + caching service** (`to_html`, `MergePreviewService`) that renders a
   computed preview using the existing [ws_fonts.py](../../src/gramtrans/Lib/ws_fonts.py)
   `WsFontRegistry`/`WsFont`/`WsRole` machinery, and memoizes previews keyed by
   `(category, source_guid, target_guid)` while caching property **dicts, never LCM
   handles**.

The module ships with **pure unit tests only** (spec Assumptions). It adds no Qt widget,
no wizard page, and no transfer behavior; it is consumed by feature 014 (pane) and depends
on feature 011's `SimilarResolution` action vocabulary (`overwrite`/`merge`/`create_new`).

## Technical Context

**Language/Version**: Python 3, `requires-python >=3.8`; `target-version = py38`
(per [pyproject.toml](../../pyproject.toml)). No 3.9+ syntax; use `from __future__ import
annotations` and `typing` generics (`Dict`, `Tuple`, `Optional`), matching `ws_fonts.py`.

**Primary Dependencies**: flexlibs2 (MattGyverLee fork) for `GetSyncableProperties` at
runtime **only** — the pure core and `to_html` never import it. The module MUST NOT import
Qt (PyQt6). Reuses in-repo `Lib/ws_fonts.py` (`WsRole`, `WsFont`, `WsFontRegistry`).

**Storage**: N/A. In-memory cache of property dicts + computed previews inside
`MergePreviewService`; nothing persisted.

**Testing**: pytest (`tests/unit/`); tests run with **no Qt and no LCM available**, using
fabricated source/target dicts and a fake `WsFontRegistry`. `-m "not integration"` is the
default posture; this feature adds no integration tests.

**Target Platform**: FlexTools host (Python 3 + PyQt6), but this module is headless-testable.

**Project Type**: FlexTools-compatible module — flat entry file + `Lib/` helper package
(constitution v5.0.0 Principle II). Single-project layout.

**Performance Goals**: `preview_for` computes once per distinct
`(category, source_guid, target_guid, mode)` (the 4-tuple key — a re-link OR a resolution
change is a distinct key; see FR-011); a repeat call performs **zero** recomputation
(SC-006). The dominant cost is the one-time linear target-GUID index build (mirrors the
existing preview indexing); `GetSyncableProperties` is assumed cheap.

**Constraints**: Qt-free (SC-007); no retained LCM handles (FR-012, constitution I);
HTML fully escaped (SC-004); alphabetical field ordering mirroring conflict detection
(FR-006).

**Scale/Scope**: One new module (~3 layers), 8 public symbols
(`DiffSegment`, `FieldDiff`, `MergePreview`, `diff_props`, `props_for`, `ws_role_map`,
`to_html`, `MergePreviewService`) plus the `SegmentKind` / mode constants and a per-category
props table. Pure unit tests only.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. FLEx Domain Fidelity** | PASS | Read-only feature. GUID-first identity is honored (cache keys are GUIDs; re-fetch by GUID on first click). WS identity drives the `ws_role_map` classifier so string-bearing segments are font/direction-tagged. Target-only keys render `unchanged` (never implies deletion) — matches `ApplySyncableProperties` touch-only-keys-it-receives semantics. |
| **II. FlexTools-Compatible, flexlibs2-Direct** | PASS | Runtime `props_for`/`MergePreviewService` import flexlibs2 directly (no `flavors/`). `GetSyncableProperties` is the canonical surface; direct-multistring fallback covers the fork gaps. Degrades gracefully (props fetch failure → note, never exception to caller — FR-008/SC-005). No new optional dependency. |
| **III. Preview-Before-Mutate** | PASS (reinforces) | This feature *is* preview machinery. It writes nothing to any project; it computes and renders diffs only. It advances the Principle III mandate that Move work route through a preview layer. |
| **IV. Phased Merge Discipline** | PASS | Additive to the Phase 1/2 preview surface; no phase reordering. Mirrors (does not import) `_deterministic_merge`, keeping the Move-time merge semantics as the single source of truth. Introduces no Phase 3 / LibLCM concern. |
| **V. Referential Completeness** | N/A (read-only) | This feature diffs a single item's fields; closure display remains a preview-pane (014) concern. No closure computation here. |

**Gate result: PASS.** No violations; Complexity Tracking left empty.

**Post-Design re-check (after Phase 1):** PASS — the data model introduces only pure value
types (frozen dataclasses / enums) and a cache keyed by GUID tuples; no LCM handle is
retained, no Qt symbol is imported, and the mirror-not-import boundary against `conflict.py`
is preserved. See [research.md](research.md) R1 and R6.

## Project Structure

### Documentation (this feature)

```text
specs/012-merge-preview-diff-engine/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── merge_preview.md # Public API contract for Lib/merge_preview.py
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/gramtrans/
├── gramtrans.py                 # FlexTools entry (unchanged by this feature)
└── Lib/
    ├── merge_preview.py         # NEW — the three-layer module (this feature)
    ├── conflict.py              # MIRRORED (not imported): _deterministic_merge semantics
    ├── ws_fonts.py              # REUSED: WsRole, WsFont, WsFontRegistry
    ├── categories.py            # REFERENCE: per-category ops precedents
    ├── models.py                # REFERENCE: SimilarResolution action vocabulary (011)
    └── preview.py               # REFERENCE: GUID-index build precedent

tests/
├── unit/
│   ├── test_merge_preview_diff.py     # NEW — US1: diff_props matrix (modes × shapes)
│   ├── test_merge_preview_html.py     # NEW — US2: to_html escaping/font/rtl/strike
│   ├── test_merge_preview_props.py    # NEW — US3: props_for covered + fork-gap + ws_role_map
│   └── test_merge_preview_service.py  # NEW — US4: caching / re-link / invalidate
└── fixtures/
    └── merge_preview/                 # NEW (if needed) — fabricated props dicts + fake registry
```

**Structure Decision**: Single new file `Lib/merge_preview.py` following the flat-`Lib/`
FLExTrans convention (constitution II). No new subpackage. Test files are split one-per-user-
story under `tests/unit/` to keep each story independently runnable (matching the repo's
existing `tests/unit/` layout). A `tests/fixtures/merge_preview/` directory is added only if
fabricated dict fixtures grow beyond inline literals.

## Complexity Tracking

> No Constitution Check violations. Section intentionally empty.

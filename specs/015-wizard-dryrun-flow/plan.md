# Implementation Plan: Wizard Dry-Run Flow (Drop Preview Step, Gate Move)

**Branch**: `015-wizard-dryrun-flow` | **Date**: 2026-07-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/015-wizard-dryrun-flow/spec.md`

## Summary

Feature 015 collapses the seven-page wizard to six pages by removing the standalone
`_PagePreview` step (now redundant because per-item merge previews live on the selection
pages from feature 014) and replacing it with a **dry-run button on the Finish page**
that assembles the plan and report before Move becomes enabled.

The structural change has three parts:

1. **Page-count reduction**: `_PagePreview` is instantiated but NOT passed to `addPage`;
   all "Step N of 7" titles renumber to "of 6"; the `page_preview()` accessor keeps
   returning the retained instance for back-compat.
2. **Plan-assembly extraction**: the body of `_PagePreview._on_preview` is lifted into
   a new module-level helper `_compute_wizard_plan(wizard) -> (plan, report)` that
   performs the identical affix-picks + phonology-collapse + Layer-1 conflict-modes +
   WS-mapping assembly **plus** copying pages' `similar_resolutions` onto the selection
   (via `dataclasses.replace`) before building the plan and run report.
   `_PagePreview._on_preview` becomes a thin wrapper around this helper.
3. **Finish-page dry-run gate**: `_PageFinish` gains a "Dry run (preview plan)" button,
   its own `_cached_plan` field, and an `initializePage()` override that clears the
   cached plan and disables Move. Move enables only after a successful dry run; post-move
   invalidation also clears the cache.

This is a pure wizard-flow / interaction change — no engine code, no diff logic, no
new Qt widget beyond the one button. It depends on feature 014 (selection pages expose
`similar_resolutions`).

## Technical Context

**Language/Version**: Python 3, `requires-python >=3.8`. No 3.9+ syntax; use
`from __future__ import annotations` and `typing` generics, matching the existing
file conventions.

**Primary File**: `src/gramtrans/Lib/ui/selection_wizard.py` — sole change surface.
No engine files (`preview.py`, `transfer.py`, `models.py`) are touched.

**Upstream Dependencies**:

- Feature 013 merged: `PlannedOverwrite.write_mode` and `fill_gaps` executor path live.
- Feature 014 merged: each selection page exposes its `similar_resolutions` store and
  per-item preview pane.
- `gt_api.compute_preview` and `gt_api.execute_move` unchanged; `gt_api.PreviewStale`
  backstop remains in force.

**Testing**: pytest (`tests/unit/`); the page-flow and idempotency tests are updated
(not added); no new module-level test file is required by this feature.

**Scope**: Changes are confined to `selection_wizard.py` (one file). The only net-new
symbols are the module-level `_compute_wizard_plan` function and the
`_PageFinish.initializePage` override.

## Design Rulings (Decided — Do Not Re-Derive)

### DR-1 — Gating Store

`_PageFinish._cached_plan` is the **sole freshness gate** for the dry-run flow.

- `_move_btn` is disabled on `_PageFinish.__init__` construction (unconditionally,
  regardless of `modify_allowed` — already disabled while no dry run has run).
- `_move_btn` is disabled again on every `_PageFinish.initializePage()` call (DR-2a).
- `_move_btn` is enabled **only** after a successful `_compute_wizard_plan` call that
  returns a non-None plan.

`_PagePreview._cached_plan` persists on the retained object so its thin `_on_preview`
wrapper keeps working, but it is **never the gate** for Move in the 015 flow.

### DR-2 — Two Invalidation Points + Keep PreviewStale

Two code sites clear the Finish page's cached plan:

**(a)** `_PageFinish.initializePage()` — added as a new override — sets
`self._cached_plan = None` and disables `_move_btn`. This replaces the freshness
guarantee previously provided by `_PagePreview.isComplete()` (lines 2718-2719), which
no longer gates Move.

**(b)** Post-move path in `_PageFinish._on_move` — after `execute_move` succeeds, sets
`self._cached_plan = None` (migrated from lines 2846-2847, which previously invalidated
`preview_page._cached_plan`).

The `PreviewStale` engine catch at line 2837 (`except gt_api.PreviewStale as e:`) is
kept unchanged as the backstop for engine-side staleness detection.

### DR-3 — 012 Cache Orthogonality

The 012 per-item diff cache (keyed by 4-tuple `(category, source_guid, target_guid, mode)`)
is **not flushed** on `_PageFinish.initializePage()`. A resolution-action change is
reflected by a differing `mode` component, not by cache invalidation. The wizard's own
plan cache (DR-1) and the 012 diff cache are orthogonal; invalidating one does not
require invalidating the other.

### DR-4 — `_compute_wizard_plan` Body (Ordered Extraction from `_on_preview`)

The new module-level function `_compute_wizard_plan(wizard)` is assembled from
`_PagePreview._on_preview` (lines 2626-2713) in this exact order:

1. **Context None-guard**: `if wizard.page_project_ws().context() is None: return (None, None)`.
   No `QMessageBox` here — the wrapper owns all UI dialogs (DR-5).
2. **Affix selection**: `affix_selection = page_items.collect_selection()`.
3. **Selection build + conflict modes**: `build_selection(...)._replace_conflict_modes(dict(_DEFAULT_CONFLICT_MODES))`
   with the package-flat `__package__` import guard for `_DEFAULT_CONFLICT_MODES`.
4. **Exactly one `dataclasses.replace` stamping** with
   `similar_resolutions=affix_selection.similar_resolutions`. The redundant second
   `collect_selection()` call at line 2665 (`_page_items_sel = page_items.collect_selection()`)
   is **dropped** (P0 fix, SC-005). The single stamp uses the already-collected
   `affix_selection` object.
5. **Ordering**: the `similar_resolutions` stamp (step 4) is applied **before** the
   phonology collapse-merge block (lines 2678-2693, P1) so that the phonology merge
   does not overwrite the stamped resolutions.
6. **WS mapping**: `ws_mapping = page0.ws_mapping() if hasattr(page0, "ws_mapping") else None`.
7. **Compute**: `state, payload = gt_api.compute_preview(context, selection, ws_mapping)`.
   The error state is **not swallowed** — if `payload` is None or `state` indicates
   failure, return `(None, None)` so the wrapper can raise the dialog (DR-5). Do not
   replicate the silent ignore pattern from line 2698.
8. **Report**: `RunReport.build_from_plan(payload, RunMode.PREVIEW, extra_excluded_lossy=_phonology_excluded_lossy_for(wizard))`.
   Return `(payload, report)`.

### DR-5 — Wrapper Owns QMessageBox

Both callers of `_compute_wizard_plan` — `_PagePreview._on_preview` and the Finish
page dry-run handler — call the helper and inspect its return value:

- If result is `(None, None)` due to a None context: show the existing
  "No target project bound" `QMessageBox.warning`.
- If result is `(None, None)` due to assembly failure: show an assembly-failure
  `QMessageBox.warning` using the same pattern as the existing `_on_preview`
  warning block.

`_compute_wizard_plan` itself shows no dialogs.

### DR-6 — `_on_move` Migration

Lines 2771-2772 in the current `_PageFinish._on_move`:

```python
preview_page = wizard.page_preview()
plan = preview_page.cached_plan() if preview_page is not None else None
```

These are rewritten to read `self._cached_plan` directly (no longer going through
the preview page's cache). The "Go back to page 5" message at line 2775 is updated
to "Go back to Finish and run a dry run" (or similar) since there is no longer a
standalone preview page at position 5.

### DR-7 — Titles and Page Count

FR-001 is authoritative: `_PagePreview` is constructed but NOT `addPage`'d.

All live `setTitle` calls using "of 7" are updated to "of 6":

| Line | Current title | New title |
|------|--------------|-----------|
| 245 | `"Step 1 of 7: Project + Writing Systems"` | `"Step 1 of 6: Project + Writing Systems"` |
| 2172 | `"Step 2 of 7: Phonology"` | `"Step 2 of 6: Phonology"` |
| 634 | `"Step 3 of 7: Item Picker"` | `"Step 3 of 6: Item Picker"` |
| 1370 | `"Step 4 of 7: Morphology Skeleton"` | `"Step 4 of 6: Morphology Skeleton"` |
| 1867 | `"Step 5 of 7: Grammatical Dependencies"` | `"Step 5 of 6: Grammatical Dependencies"` |
| 2610 | `"Step 6 of 7: Preview"` | `"Step 6 of 7: Preview"` (unchanged text; preview is retained but not added; title is moot but left consistent) |
| 2742 | `"Step 7 of 7: Finish / Move"` | `"Step 6 of 6: Finish / Move"` |

Line 1223 (`"Step 3 of 5: Schema Scope + Conflict Mode"` in `_PageScopeConflict`) is
left as-is; that page is already not added.

The `SelectionWizard` class docstring at line 2856 (`"5-page GramTrans selection wizard"`)
is updated to `"6-page GramTrans selection wizard"`.

The `addPage` call for `_page_preview` (line 2928) is removed; the remaining calls
re-index: `_page_finish` becomes index 5 (was 6).

`test_no_literal_page_index_calls_in_wizard_source` must remain green; no literal
numeric page-index calls are introduced.

### DR-8 — Test Updates

Two test files require edits (no new test files for this feature):

- **`tests/unit/test_p0_idempotency_ws.py` (~line 198)**: the assertion
  `assert preview_page._cached_plan is not None` and the invalidation simulation
  are rewritten to assert on `_PageFinish._cached_plan` instead of
  `_PagePreview._cached_plan`. The fake wizard reference is updated accordingly.
- **`tests/unit/test_wizard_page_flow.py` (line 1 docstring)**: update the
  `"5-page SelectionWizard"` string to `"6-page SelectionWizard"` (the ruling also
  covers any in-body references to the old seven-page count or the preview-page index).

### G1 — Dry-Run Assembly-Failure Error Contract

If `_compute_wizard_plan` returns `(None, None)` due to an assembly error (not a
context-None), the Finish-page dry-run handler displays a `QMessageBox.warning`
following the `_on_preview` pattern. Move remains disabled. No partial state is written.

### G2 — `_on_move` Listed as Code-Change Site

`_PageFinish._on_move` at line 2766 is an explicit code-change site (DR-6): lines
2771-2772 switch from `preview_page.cached_plan()` to `self._cached_plan`, and the
stale-plan message at line 2775 is updated.

### G3 — Post-Move Invalidation Migration

The post-move cache clear at lines 2846-2847:

```python
if hasattr(preview_page, "_cached_plan"):
    preview_page._cached_plan = None
```

is migrated to `self._cached_plan = None` inside `_PageFinish._on_move`, clearing the
Finish page's own cache rather than the preview page's.

## Feature Requirements — File & Anchor Map

### FR-001 — Remove `_PagePreview` from `addPage`

Remove line 2928 (`self.addPage(self._page_preview)`) from `SelectionWizard.__init__`.
`self._page_preview` is still instantiated; `_page_finish` becomes index 5.

### FR-002 — Renumber Titles

Update six `setTitle` calls per DR-7 table above.

### FR-003 — `page_preview()` Back-Compat

`SelectionWizard.page_preview()` (line 2956) is unchanged; it returns `self._page_preview`
which is the retained (non-added) instance.

### FR-004 — Extract `_compute_wizard_plan`

New module-level function inserted near the `_PagePreview` class, before
`_PageFinish`. Its signature:

```python
def _compute_wizard_plan(wizard) -> tuple:
    """Assemble the transfer plan from all wizard page selections.

    Returns (plan, report) on success, (None, None) on any failure.
    Does not display QMessageBox — callers own all UI dialogs.
    """
```

Body follows DR-4 ordering exactly.

### FR-005 — Thin `_on_preview` Wrapper

`_PagePreview._on_preview` (line 2626) is rewritten to:

```python
def _on_preview(self) -> None:
    wizard = self.wizard()
    if wizard is None:
        return
    plan, report = _compute_wizard_plan(wizard)
    if plan is None:
        # DR-5: wrapper owns QMessageBox
        context = wizard.page_project_ws().context()
        if context is None:
            QtWidgets.QMessageBox.warning(
                self, "GramTrans", "No target project bound. Go back to page 1."
            )
        else:
            QtWidgets.QMessageBox.warning(
                self, "GramTrans", "Plan assembly failed. Check project state."
            )
        return
    self._cached_plan = plan
    self._stats.set_report(report)
    self.completeChanged.emit()
```

### FR-006 — Finish-Page Dry-Run Button

`_PageFinish._build_ui()` gains a `"Dry run (preview plan)"` button above `_move_btn`.
Its `clicked` signal connects to `_PageFinish._on_dry_run()` which calls
`_compute_wizard_plan`, handles the `(None, None)` error case (G1), otherwise writes
`self._cached_plan = plan`, displays the report in `self._stats`, and calls
`self._move_btn.setEnabled(True)`.

### FR-007 — Move Gating

`_PageFinish.__init__` unconditionally sets:

```python
self._cached_plan = None
self._move_btn.setEnabled(False)
```

Move-btn enable/disable state tracks whether `self._cached_plan is not None`, set by
`_on_dry_run` and cleared by `initializePage` and post-move.

### FR-008 — Cached-Plan Invalidation

Two invalidation sites (DR-2):

```python
# (a) _PageFinish.initializePage — new override
def initializePage(self) -> None:
    self._cached_plan = None
    self._move_btn.setEnabled(False)

# (b) _PageFinish._on_move — post-move, after execute_move succeeds
self._cached_plan = None          # replaces lines 2846-2847
```

### FR-009 — No Engine Changes

`preview.py`, `transfer.py`, `models.py`, `conflict.py`, `merge_preview.py`, and all
`gt_api` surface are unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/015-wizard-dryrun-flow/
├── spec.md              # Feature specification (pre-existing)
└── plan.md              # This file
```

### Source Code Modified

```text
src/gramtrans/
└── Lib/
    └── ui/
        └── selection_wizard.py   # SOLE change surface
```

### Tests Modified (no new test files)

```text
tests/unit/
├── test_p0_idempotency_ws.py     # UPDATE ~line 198: assert on _PageFinish._cached_plan
└── test_wizard_page_flow.py      # UPDATE line 1 docstring + body: 6-page, no preview page
```

## Code-Change Sites

The following table maps every ruling to its concrete location in
`src/gramtrans/Lib/ui/selection_wizard.py` unless otherwise noted.

| Ruling | Site | Lines | Change |
|--------|------|-------|--------|
| DR-1 | `_PageFinish.__init__` | 2737-2747 | Add `self._cached_plan = None`; ensure `_move_btn` starts disabled |
| DR-2a | `_PageFinish.initializePage` | NEW override after `__init__` | New method: clear `_cached_plan`, disable `_move_btn` |
| DR-2b | `_PageFinish._on_move` (post-move) | 2846-2847 | Replace `preview_page._cached_plan = None` with `self._cached_plan = None` |
| DR-2 (keep) | `_PageFinish._on_move` (PreviewStale) | 2837 | Keep `except gt_api.PreviewStale as e:` unchanged |
| DR-3 | `_PageFinish.initializePage` | NEW | Do NOT flush 012 diff cache here |
| DR-4 | `_compute_wizard_plan` | NEW (before `_PageFinish` class) | New module-level function; body from lines 2626-2713 |
| DR-4 step 4 (P0) | `_on_preview` body | 2665 | DROP redundant `_page_items_sel = page_items.collect_selection()` |
| DR-4 step 5 (P1) | `_compute_wizard_plan` | NEW | Stamp resolutions BEFORE phonology merge block |
| DR-5 | `_PagePreview._on_preview` | 2626 | Rewrite as thin wrapper (QMessageBox stays here) |
| DR-5 | `_PageFinish._on_dry_run` | NEW | QMessageBox for None-context AND assembly-failure |
| DR-6 | `_PageFinish._on_move` | 2771-2772 | Read `self._cached_plan` directly; drop `preview_page` lookup |
| DR-6 | `_PageFinish._on_move` (message) | 2775 | Update "Go back to page 5" message |
| DR-7 | `_PageProjectWS.__init__` | 245 | `"Step 1 of 7"` -> `"Step 1 of 6"` |
| DR-7 | `_PagePhonology.__init__` | 2172 | `"Step 2 of 7"` -> `"Step 2 of 6"` |
| DR-7 | `_PageItemPicker.__init__` | 634 | `"Step 3 of 7"` -> `"Step 3 of 6"` |
| DR-7 | `_PageSkeleton.__init__` | 1370 | `"Step 4 of 7"` -> `"Step 4 of 6"` |
| DR-7 | `_PageGramDeps.__init__` | 1867 | `"Step 5 of 7"` -> `"Step 5 of 6"` |
| DR-7 | `_PageFinish.__init__` | 2742 | `"Step 7 of 7"` -> `"Step 6 of 6"` |
| DR-7 | `SelectionWizard` class docstring | 2856 | `"5-page"` -> `"6-page"` |
| DR-7 | `SelectionWizard.__init__` | 2928 | Remove `self.addPage(self._page_preview)` |
| DR-7 | `SelectionWizard.__init__` comment | ~2908 | Update index comment: remove `5 = Preview`; `6 = Finish` -> `5 = Finish` |
| DR-7 (leave) | `_PageScopeConflict.__init__` | 1223 | Leave `"Step 3 of 5: Schema Scope"` unchanged |
| DR-8 | `test_p0_idempotency_ws.py` | ~198 | Assert on `_PageFinish._cached_plan`; update fake wizard reference |
| DR-8 | `test_wizard_page_flow.py` | line 1 | Update `"5-page"` docstring to `"6-page"`; update body for six-page flow |
| G1 | `_PageFinish._on_dry_run` | NEW | `QMessageBox.warning` on assembly failure; Move stays disabled |
| G2 | `_PageFinish._on_move` | 2766+ | Listed as change site per DR-6 |
| G3 | `_PageFinish._on_move` (post-move) | 2846-2847 | Migrate invalidation to `self._cached_plan = None` |
| FR-006 | `_PageFinish._build_ui` | 2749+ | Insert "Dry run (preview plan)" button above `_move_btn` |

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. FLEx Domain Fidelity** | PASS | No LCM reads or writes; the dry run calls `compute_preview` (read-only) then `execute_move` (write, user-gated). GUID-keyed caches from 012/013 are untouched (DR-3). |
| **II. FlexTools-Compatible, flexlibs2-Direct** | PASS | No new imports; all engine calls go through `gt_api` as before. No `flavors/` adapter introduced. |
| **III. Preview-Before-Mutate** | PASS (reinforces) | The dry-run gate is the new preview-before-mutate checkpoint. Move is impossible without a successful `compute_preview` producing a cached plan. `PreviewStale` backstop retained (DR-2). |
| **IV. Phased Merge Discipline** | PASS | No phase reordering; pure flow change. Assembly body is unchanged (only relocated). |
| **V. Referential Completeness** | N/A | No closure computation; 013's `identity_remap` flows through unchanged via `compute_preview` -> plan. |

**Gate result: PASS.**

## Risks

### R1 — `_PageFinish.initializePage` Interaction with `_move_btn` state

`_build_ui()` sets `_move_btn.setEnabled(self._modify_allowed)`. The new
`initializePage()` must unconditionally call `self._move_btn.setEnabled(False)`, not
`self._move_btn.setEnabled(self._modify_allowed)`, so the dry-run gate is enforced
even in write-enabled mode. Verify this does not double-disable in read-only mode
(disabling an already-disabled button is a no-op in Qt; safe).

### R2 — `completeChanged` Signal

`_PageFinish` does not currently emit `completeChanged` (Move is not a wizard
completion gate in the traditional sense). If the Finish page's `isComplete()` is
used by any test or downstream code, verify it does not need to track
`_cached_plan` state. Current `_PagePreview.isComplete()` (line 2718) is the gate
being replaced; `_PageFinish` has no `isComplete` override today. No change needed
unless a test asserts on it.

### R3 — Back-Compat: `_PagePreview.isComplete` and `cached_plan()`

`_PagePreview.isComplete()` (line 2718) and `_PagePreview.cached_plan()` (line 2715)
are kept unchanged because `_PagePreview` is retained as a non-added object.
Any test or code that calls `page_preview().cached_plan()` still works; the return
value just no longer gates Move.

## Complexity Tracking

Sole source of complexity is the correctness of the two-invalidation-point contract
(DR-2): a missed invalidation allows Move to run a stale plan. The
`_PageFinish.initializePage` path is the new invalidation that previously did not
exist; it must fire on every forward navigation to the Finish page. Qt's `QWizard`
calls `initializePage` on every visit to a page (not just the first), so the
guarantee holds without additional plumbing. Validate with a test that navigates
forward, backward, and forward again, asserting Move is disabled on the second entry.

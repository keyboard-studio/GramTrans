# Tasks: Wizard Dry-Run Flow (Drop Preview Step, Gate Move)

**Feature**: 015-wizard-dryrun-flow | **Date**: 2026-07-04

Task ordering: T-001 (titles + addPage) -> T-002 (extract helper) -> T-003 (thin
wrapper) -> T-004 (Finish __init__ gate) -> T-005 (initializePage) -> T-006 (dry-run
button + handler) -> T-007 (_on_move migration) -> T-008 (post-move invalidation) ->
T-009 (idempotency test) -> T-010 (page-flow test).

Tasks T-001 and T-002 are independent and can run in parallel [P]. All others depend
on T-002 (the helper must exist before callers are rewritten).

Sole change surface: `src/gramtrans/Lib/ui/selection_wizard.py`.
Test edits: `tests/unit/test_p0_idempotency_ws.py` and
`tests/unit/test_wizard_page_flow.py`.

---

## T-001 [X] — Page-count reduction: renumber titles and remove addPage

**Covers**: DR-7, FR-001, FR-003

Rename "of 7" -> "of 6" at the five live page classes, remove the `addPage` call for
`_page_preview`, and update the class docstring and index comment.

Exact edits in `selection_wizard.py`:

| Line | Change |
|------|--------|
| 245 | `"Step 1 of 7"` -> `"Step 1 of 6"` (`_PageProjectWS.__init__`) |
| 634 | `"Step 3 of 7"` -> `"Step 3 of 6"` (`_PageItemPicker.__init__`) |
| 1370 | `"Step 4 of 7"` -> `"Step 4 of 6"` (`_PageSkeleton.__init__`) |
| 1867 | `"Step 5 of 7"` -> `"Step 5 of 6"` (`_PageGramDeps.__init__`) |
| 2172 | `"Step 2 of 7"` -> `"Step 2 of 6"` (`_PagePhonology.__init__`) |
| 2742 | `"Step 7 of 7"` -> `"Step 6 of 6"` (`_PageFinish.__init__`) |
| 2856 | `"5-page GramTrans selection wizard"` -> `"6-page GramTrans selection wizard"` (class docstring) |
| 2928 | Remove `self.addPage(self._page_preview)` |
| ~2908 | Update index comment: remove `5 = Preview`; change `6 = Finish` -> `5 = Finish` |

Leave line 1223 (`"Step 3 of 5: Schema Scope"` in `_PageScopeConflict`) unchanged --
that page is not added.

Leave line 2610 (`"Step 6 of 7: Preview"` in `_PagePreview.__init__`) unchanged --
the title is moot (page not added) but kept consistent per DR-7.

`SelectionWizard.page_preview()` at line 2956 is NOT changed (FR-003 back-compat).

**Checklist**:
- [X] All five "of 7" occurrences in live page classes updated.
- [X] `addPage` for `_page_preview` removed; `_page_preview` still instantiated.
- [X] Class docstring updated to "6-page".
- [X] `test_no_literal_page_index_calls_in_wizard_source` passes.

---

## T-002 [X] — Extract `_compute_wizard_plan` module-level helper

**Covers**: DR-4, DR-4 step 4 (P0 SC-005), DR-4 step 5, FR-004

Insert a new module-level function `_compute_wizard_plan(wizard) -> tuple` immediately
before the `_PageFinish` class definition (after `_PagePreview`).

Body assembles from `_PagePreview._on_preview` lines 2626-2713 in DR-4 order:

1. Context None-guard (return `(None, None)` if context is None -- no QMessageBox here).
2. `affix_selection = page_items.collect_selection()`.
3. `build_selection(...)._replace_conflict_modes(dict(_DEFAULT_CONFLICT_MODES))`.
4. Single `dataclasses.replace` stamp: `similar_resolutions=affix_selection.similar_resolutions`.
   DROP the redundant second `collect_selection()` call at line 2665 (SC-005).
5. Apply the `similar_resolutions` stamp BEFORE the phonology collapse-merge block
   (lines 2678-2693) so phonology merge does not overwrite it.
6. `ws_mapping = page0.ws_mapping() if hasattr(page0, "ws_mapping") else None`.
7. `state, payload = gt_api.compute_preview(context, selection, ws_mapping)`.
   Return `(None, None)` if payload is None or state indicates failure -- do not
   silently ignore like line 2698.
8. `RunReport.build_from_plan(payload, RunMode.PREVIEW, ...)`. Return `(payload, report)`.

Signature:

```python
def _compute_wizard_plan(wizard) -> tuple:
    """Assemble the transfer plan from all wizard page selections.

    Returns (plan, report) on success, (None, None) on any failure.
    Does not display QMessageBox -- callers own all UI dialogs (DR-5).
    """
```

**Checklist**:
- [X] No `QMessageBox` call inside this function.
- [X] Redundant `collect_selection()` at line 2665 is dropped (one call total).
- [X] `dataclasses.replace` stamp precedes phonology merge block.
- [X] Returns `(None, None)` on context-None, compute failure, and payload-None.
- [X] `from __future__ import annotations` already present; use `typing` generics only.

---

## T-003 [X] — Rewrite `_PagePreview._on_preview` as thin wrapper

**Depends on**: T-002 | **Covers**: DR-5, FR-005

Rewrite `_PagePreview._on_preview` (line 2626) to call `_compute_wizard_plan(wizard)`,
handle the `(None, None)` result with QMessageBox warnings per DR-5, and on success
set `self._cached_plan = plan`, update `self._stats`, emit `completeChanged`.

The original body (lines 2626-2713) is removed and replaced by the thin wrapper.
`_PagePreview._cached_plan`, `_PagePreview.isComplete()` (line 2718), and
`_PagePreview.cached_plan()` (line 2715) are retained unchanged (FR-003, R3).

**Checklist**:
- [X] `_PagePreview._on_preview` is a thin wrapper only; no plan assembly inline.
- [X] QMessageBox for None-context case shown here (not in helper).
- [X] QMessageBox for assembly-failure case shown here (not in helper).
- [X] `_PagePreview.isComplete()` and `cached_plan()` untouched.

---

## T-004 [X] — `_PageFinish.__init__`: add `_cached_plan` field and initial gate state

**Depends on**: T-002 | **Covers**: DR-1, FR-007

In `_PageFinish.__init__` (lines 2737-2747):

- Add `self._cached_plan = None`.
- Ensure `self._move_btn.setEnabled(False)` is set unconditionally at construction
  (regardless of `_modify_allowed`).

**Checklist**:
- [X] `_cached_plan` initialized to `None` in `__init__`.
- [X] `_move_btn` disabled unconditionally at construction.
- [X] No flush of the 012 diff cache (DR-3 -- orthogonal caches).

---

## T-005 [X] — Add `_PageFinish.initializePage` override

**Depends on**: T-004 | **Covers**: DR-2a, DR-3, FR-008a, R1

Insert a new `initializePage(self) -> None` override immediately after
`_PageFinish.__init__`. This is the first of the two DR-2 invalidation points.

```python
def initializePage(self) -> None:
    self._cached_plan = None
    self._move_btn.setEnabled(False)
```

Note: disabling an already-disabled button is a no-op in Qt; safe in read-only mode
(R1). Do NOT flush the 012 per-item diff cache here (DR-3).

**Checklist**:
- [X] Method exists as an override on `_PageFinish`.
- [X] Both `_cached_plan = None` and `_move_btn.setEnabled(False)` present.
- [X] No reference to `_PagePreview._cached_plan`.
- [X] No 012 diff-cache flush.

---

## T-006 [X] — Add "Dry run" button to `_PageFinish._build_ui` and `_on_dry_run` handler

**Depends on**: T-004, T-005 | **Covers**: DR-5, G1, FR-006

In `_PageFinish._build_ui()` (line 2749+): insert a `QPushButton("Dry run (preview plan)")`
above `_move_btn`. Connect its `clicked` signal to `self._on_dry_run`.

New method `_PageFinish._on_dry_run(self) -> None`:

1. Calls `_compute_wizard_plan(self.wizard())`.
2. On `(None, None)` -- context-None case: `QMessageBox.warning` ("No target project bound").
3. On `(None, None)` -- assembly failure: `QMessageBox.warning` per G1 pattern;
   Move stays disabled. No partial state written.
4. On success: `self._cached_plan = plan`; display report in `self._stats`;
   `self._move_btn.setEnabled(True)`.

**Checklist**:
- [X] Button inserted above `_move_btn` in the UI layout.
- [X] `_on_dry_run` calls `_compute_wizard_plan` (not inline assembly).
- [X] Both QMessageBox paths handled (G1 contract).
- [X] Move enabled only after non-None plan returned.

---

## T-007 [X] — Migrate `_PageFinish._on_move` cache read from preview page to self

**Depends on**: T-004 | **Covers**: DR-6, G2

In `_PageFinish._on_move` (line 2766+), rewrite lines 2771-2772:

```python
# BEFORE:
preview_page = wizard.page_preview()
plan = preview_page.cached_plan() if preview_page is not None else None

# AFTER:
plan = self._cached_plan
```

Update the stale-plan fallback message at line 2775 from "Go back to page 5" to
"Run a dry run on the Finish page" (or similar -- no standalone preview page exists).

**Checklist**:
- [X] No reference to `preview_page.cached_plan()` remains in `_on_move`.
- [X] `self._cached_plan` is the sole plan source.
- [X] Stale-plan message updated.
- [X] `except gt_api.PreviewStale` at line 2837 left unchanged (DR-2 keep).

---

## T-008 [X] — Migrate post-move cache invalidation from preview page to self

**Depends on**: T-007 | **Covers**: DR-2b, G3, FR-008b

In `_PageFinish._on_move`, after `execute_move` succeeds, replace lines 2846-2847:

```python
# BEFORE:
if hasattr(preview_page, "_cached_plan"):
    preview_page._cached_plan = None

# AFTER:
self._cached_plan = None
```

This is the second DR-2 invalidation point.

**Checklist**:
- [X] `self._cached_plan = None` written after successful `execute_move`.
- [X] No reference to `preview_page._cached_plan` in this block.
- [X] `_move_btn` disabled after post-move invalidation (consider
      `self._move_btn.setEnabled(False)` here for consistency; not strictly required
      since `initializePage` fires on re-entry, but explicit is cleaner).

---

## T-009 [X] — Update `test_p0_idempotency_ws.py` (~line 198)

**Depends on**: T-004, T-005, T-008 | **Covers**: DR-8

In `tests/unit/test_p0_idempotency_ws.py` at approximately line 198:

- Replace assertion `assert preview_page._cached_plan is not None` with an assertion
  on `finish_page._cached_plan` (i.e., the `_PageFinish` instance).
- Update the fake wizard reference used in the invalidation simulation to point at the
  `_PageFinish` instance rather than the `_PagePreview` instance.
- Add a back-navigate-and-return assertion: after simulating `initializePage()`, assert
  `finish_page._cached_plan is None` and `move_btn.isEnabled() == False`.

**Checklist**:
- [X] No assertion remains on `_PagePreview._cached_plan` as the Move gate.
- [X] Invalidation via `initializePage` tested explicitly.
- [X] Test passes with no new imports.

---

## T-010 [X] — Update `test_wizard_page_flow.py`

**Depends on**: T-001 | **Covers**: DR-8

In `tests/unit/test_wizard_page_flow.py`:

- Line 1 docstring: update `"5-page SelectionWizard"` to `"6-page SelectionWizard"`.
- Update any in-body references to the seven-page count or the old preview-page index.
- Confirm the test exercises a six-page forward flow (no preview page at position 5);
  update expected page sequence accordingly.

**Checklist**:
- [X] Docstring updated.
- [X] No in-body `"7"` page count references remain.
- [X] Expected page order reflects six-page flow.
- [X] Test passes.

---

## Dependency Summary

```
T-001 [P] ─────────────────────────────────────────> T-010
T-002 [P] ─-> T-003
T-002 [P] ─-> T-004 -> T-005 -> T-006
                        T-004 -> T-007 -> T-008 -> T-009
                        T-005 ─────────────────-> T-009
                        T-008 ─────────────────-> T-009
```

T-001 and T-002 may be executed in parallel (no shared edit site).
T-003 through T-010 sequence on T-002/T-004 as shown.

---

## Task Count

| ID | Title | Ruling(s) | Lines |
|----|-------|-----------|-------|
| T-001 | Page-count reduction: titles + addPage | DR-7, FR-001, FR-003 | 245, 634, 1370, 1867, 2172, 2742, 2856, 2928, ~2908 |
| T-002 | Extract `_compute_wizard_plan` helper | DR-4 (all steps), FR-004 | NEW (before `_PageFinish`); drops line 2665 |
| T-003 | Thin `_on_preview` wrapper | DR-5, FR-005 | 2626-2713 (rewrite) |
| T-004 | `_PageFinish.__init__` gate field | DR-1, FR-007 | 2737-2747 |
| T-005 | `_PageFinish.initializePage` override | DR-2a, DR-3, FR-008a, R1 | NEW after `__init__` |
| T-006 | Dry-run button + `_on_dry_run` handler | DR-5, G1, FR-006 | 2749+ (new button + method) |
| T-007 | `_on_move` cache read migration | DR-6, G2 | 2771-2772, 2775 |
| T-008 | Post-move invalidation migration | DR-2b, G3, FR-008b | 2846-2847 |
| T-009 | Update idempotency test | DR-8 | test_p0_idempotency_ws.py ~198 |
| T-010 | Update page-flow test | DR-8 | test_wizard_page_flow.py line 1 + body |

**Total: 10 tasks** (7 implementation, 1 optional-consistency note in T-001, 2 test updates)

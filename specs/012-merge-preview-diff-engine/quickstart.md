# Quickstart / Validation: Merge-Preview Diff Engine (012)

This feature ships **pure unit tests only** (spec Assumptions). Validation is headless — no
FlexTools host, no LCM, no Qt required.

## Prerequisites

- Python 3 (>=3.8) with the dev extras installed:
  ```powershell
  pip install -e ".[dev]"
  ```
- No live project pair is needed. All scenarios use fabricated `{field: {ws_id: text}}`
  dicts and a fake `WsFontRegistry`.

## Run the feature's tests

```powershell
# All 012 unit tests (skip the integration marker):
python -m pytest tests/unit/test_merge_preview_diff.py tests/unit/test_merge_preview_html.py tests/unit/test_merge_preview_props.py tests/unit/test_merge_preview_service.py -m "not integration" -v
```

## Validation scenarios (map to spec Success Criteria)

| # | Scenario | Asserts | SC |
|---|----------|---------|----|
| 1 | `diff_props(src, None, NEW, role_of)` across every value shape | 0 non-`added` segments | SC-001 |
| 2 | Mode × shape matrix (NEW, LINK-ONLY, OVERWRITE, MERGE-KEEP × multistring, str, list, scalar, other) | segment kinds per FR-002–FR-006 | SC-002 |
| 3 | Any `diff_props` result | `fields` alphabetical by `field_name` | SC-003 |
| 4 | `to_html(preview, fake_registry)` with metacharacters + RTL role + removed segment | escaping, per-role font, `dir=rtl`, strike-through | SC-004 |
| 5 | `props_for` covered fixture (ENTRY/LexEntry) and fork-gap fixture (Slots); forced hard failure | covered dict; direct-read shape; `None`+note (no exception) | SC-005 |
| 6 | `preview_for` twice identical, then a re-link (new `target_guid`), then a mode change (same GUIDs, new `mode`), then `invalidate` | 1 compute; distinct new entry on re-link; distinct new entry on mode change (4-tuple key); recompute after invalidate | SC-006 |
| 7 | `import Lib.merge_preview` with Qt unavailable | imports and runs Qt-free | SC-007 |

## Qt-free guarantee (SC-007)

The import-with-no-Qt test proves the module never pulls PyQt at import time. Keep flexicon
imports lazy/guarded inside `props_for`/`MergePreviewService` so `diff_props` and `to_html`
import cleanly in a bare Python environment.

## Expected outcome

All four test modules pass under `-m "not integration"`; the mode × value-shape matrix
(scenario 2) is the core acceptance surface. No target project is written to — this feature
mutates nothing.

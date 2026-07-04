# Implementation Plan: Merge-Preview Pane & Wizard Integration

**Branch**: `014-merge-preview-pane` | **Date**: 2026-07-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/014-merge-preview-pane/spec.md`

## Summary

Feature 014 adds one new Qt widget — `src/gramtrans/Lib/ui/merge_preview_pane.py` —
and integrates it into the four existing selection pages of
`src/gramtrans/Lib/ui/selection_wizard.py`:

- `_PageItemPicker` (~line 573) — affix item picker
- `_PageSkeleton` (~line 1095) — morphology skeleton
- `_PageGramDeps` (~line 1532) — grammatical dependencies
- `_PagePhonology` (~line 1761) — phonology block

Each page gains a horizontal `QSplitter` (tree left, wider; pane right) via a shared
helper applied in each page's `_build_ui`. On tree-selection changes, the page builds
a `PreviewRequest` and calls `pane.show_item(request)`; the pane routes all data access
through the 012 `MergePreviewService` and renders via `to_html` — it never touches LCM
directly.

For SIMILAR affix rows on `_PageItemPicker`, the pane additionally shows a resolution
header: a searchable combo of candidate target entries ("form -- gloss") and an
Overwrite / Merge / Create-new three-way action control. Changing either control emits a
`resolution_changed` signal, updates the page's per-page resolution store, recomputes the
diff immediately, and reflects the choice in the row's Target column. Every SIMILAR row
is seeded with a default `overwrite(guid -> suggested_target_guid)` resolution on page
initialize, preserving the existing source-wins behavior.

`collect_selection()` on `_PageItemPicker` folds the page's resolution store into the
returned `Selection` via `dataclasses.replace`. The preview-reconstruction path (the
`_PagePreview._on_preview` dry-run that rebuilds a `Selection` from affix picks) copies
`similar_resolutions` across rather than dropping the field. FR-009 lands here because
the pane is the producer of resolutions; the dry-run gating itself is deferred to feature
015.

**Out of scope**: the wizard flow change (removing the standalone Preview step, gating
Move behind a dry run) is feature 015. This feature keeps the existing page flow and only
docks the pane and wires resolutions.

**Upstream dependencies**: features 011 (`SimilarResolution`, `Selection.similar_resolutions`,
candidate capture), 012 (`MergePreviewService`, `to_html`, mode constants), and 013
(planner/executor honoring resolutions) are merged before this feature begins.

## Technical Context

**Language/Version**: Python 3, `requires-python >=3.8`. No 3.9+ syntax; use
`from __future__ import annotations` and `typing` generics (`Dict`, `Tuple`, `Optional`),
matching the style of `ws_fonts.py` and `merge_preview.py`.

**Primary Dependencies**:

- **flexicon (dist `pyflexicon`)** — the direct runtime dependency. flexicon is a
  standalone independent project, NOT a fork of stock flexlibs2; module files import
  flexicon directly per constitution v5.1.0 Principle II. `pyproject.toml` declares
  `pyflexicon>=4.1`. The deprecation shim `flexlibs2` is not referenced in new code.
- **PyQt6** — imported guardedly (`PyQt6` availability checked via `importorskip` in
  tests; guarded `try/except ImportError` at module level in the widget file). Pure diff
  logic stays in `merge_preview.py` so the pane remains a thin viewer.
- **`Lib/merge_preview.py`** (feature 012) — `MergePreviewService`, `to_html`,
  `OVERWRITE`, `MERGE_KEEP`, `NEW`, `LINK_ONLY` mode constants.
- **`Lib/models.py`** (feature 011) — `SimilarResolution`, `Selection`.
- **`Lib/ui/selection_wizard.py`** — the four page classes to be modified.
- **`Lib/ws_fonts.py`** — `WsFontRegistry` (passed to pane via `set_context`; the
  delegate registration pattern is already applied in sibling pages).

**Storage**: no persistence. Per-page resolution store is a plain `dict[str,
SimilarResolution]` held on the page instance; cleared and re-seeded on `initializePage`.

**Testing**: `pytest tests/unit/test_014_*.py`. PyQt6 widgets require
`pytest.importorskip("PyQt6")` plus the offscreen platform environment variable
`QT_QPA_PLATFORM=offscreen` set before the Qt application is instantiated. Pure diff and
service logic stays in 012 tests; the pane tests cover only widget behavior (header
visibility, combo filtering, signal emission, resolution seeding). One test file per user
story.

**Target Platform**: FlexTools host (Python 3 + PyQt6). The widget is only instantiated
inside the FlexTools environment; the pure-logic components remain headless-testable.

**Project Type**: FlexTools-compatible module — flat `Lib/` helper package per
constitution v5.1.0 Principle II. New UI file follows the existing `Lib/ui/` pattern.

**Performance Goals**: `MergePreviewService.preview_for` computes once per distinct
4-tuple `(category, source_guid, target_guid, mode)` and returns the cached
`MergePreview` on repeat calls with zero recomputation (012 SC-006). A resolution flip
from Overwrite to Merge (same source GUID, same target GUID, different mode) is a
distinct cache key — the pane calls `preview_for` with the new mode; no `invalidate()`
is required for an in-page flip. `invalidate()` is called only on page re-entry (the
`initializePage` path). The one-time GUID index build in the service mirrors the existing
preview indexing cost.

**Constraints**:

- The pane MUST NOT import LCM directly; all data access routes through
  `MergePreviewService` (FR-001).
- Qt imports in the pane file are guarded so the module can be imported in a headless
  test environment with `importorskip` directing the Qt-dependent paths.
- No new optional runtime dependencies beyond flexicon and PyQt6 (already required by
  the host).
- Feature 015 owns the wizard flow change; this feature does not alter page order or
  gating logic.

**Scale/Scope**: One new widget module (~200-300 lines), targeted modifications to four
page classes and the `_PagePreview._on_preview` reconstruction path in
`selection_wizard.py`, one shared splitter helper, and three-to-four offscreen-Qt test
files.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. FLEx Domain Fidelity** | PASS | The pane is read-only display; it writes nothing to any project. GUID identity flows through the service's 4-tuple cache key unchanged. Resolution data carried by `SimilarResolution` is GUID-keyed. The pane reflects the user's resolution choice; the actual LCM write is 013's concern and has already passed Constitution I review. |
| **II. FlexTools-Compatible, flexicon-Direct** | PASS | The new widget module and the four page modifications import flexicon directly (no `flavors/` adapter). `MergePreviewService` was already flexicon-direct in 012. No new dependency is introduced beyond PyQt6 (already present in the host). Constitution v5.1.0 Principle II framing: flexicon is a standalone independent project, not a fork of flexlibs2. |
| **III. Preview-Before-Mutate** | PASS (directly reinforces) | This feature is preview surface. It presents the per-item diff before any move is executed, fulfilling the mandate that "Move work route through a preview layer." The `similar_resolutions` copy in the reconstruction path (FR-009) ensures the planner receives the resolutions the pane produced — the preview and the move remain consistent. |
| **IV. Phased Merge Discipline** | PASS | Additive to the Phase 1/2 overwrite and interactive-merge surface. No phase is reordered. The three-way Overwrite / Merge / Create-new resolution control is the user-facing expression of Phase 2's per-item merge semantics introduced in 011 and honoured in 013. Feature 015 (flow gating) remains a distinct subsequent phase. |
| **V. Referential Completeness** | LARGELY N/A (read-only display) | The pane displays a single-item diff; closure display is outside scope. The resolution a user picks affects which target entry is written to (013's concern) but does not alter the closure displayed by the existing Preview page. No closure computation is added or removed here. |

**Gate result: PASS.** No violations.

**Post-Design re-check**: PASS. The mode-mapping table (Overwrite -> `OVERWRITE`,
Merge -> `MERGE_KEEP`, Create-new -> `NEW` via `target_guid=None`) mirrors the 012
constant names without inventing new vocabulary. The 4-tuple cache key is used strictly
as documented in 012; no shortcut to a 3-tuple is made anywhere in this feature.

## Design Rulings (Decided -- Do Not Re-Derive)

### R1 -- Action-to-Mode Mapping (FR-004, FR-007)

The three user-facing actions map to 012 mode constants as follows:

| User action | `SimilarResolution.action` | `preview_for` mode | Diff rendering |
|-------------|---------------------------|-------------------|----------------|
| Overwrite   | `"overwrite"`             | `OVERWRITE`       | Source-wins diff (changed fields show old -> new) |
| Merge       | `"merge"`                 | `MERGE_KEEP`      | Target-preserving fill-gaps (source fills only empty target slots) |
| Create new  | `"create_new"`            | `NEW`             | All-green (target GUID passed as `""` or `None`; service branches on `mode == NEW`) |

For Create-new, the pane passes `target_guid=""` and `mode=NEW` to `preview_for`. The
service's existing branch `if mode == NEW or not target_guid: tgt_props = None` handles
this without modification.

### R2 -- Cache Key Discipline (spec Assumptions)

The 012 cache key is the 4-tuple `(category, source_guid, target_guid, mode)` (confirmed
from `merge_preview.py` line 1094). A resolution flip on the same item within a page
produces a distinct cache entry because `mode` changes; `invalidate()` is therefore NOT
called on a resolution flip. `invalidate()` is called only in `initializePage` (page
re-entry) to clear stale props and preview caches when source/target state may have
changed. The pane MUST NOT assume a 3-tuple key.

### R3 -- Resolution Store and Default Seeding (FR-008, SC-003)

`_PageItemPicker` holds `_resolution_store: dict[str, SimilarResolution]` initialized to
`{}` on `__init__`. On `initializePage`, after populating the tree, the page seeds one
default `SimilarResolution(entry_guid=g, action="overwrite", target_guid=suggested_guid)`
for every SIMILAR affix row. This preserves today's source-wins behavior without user
interaction. The store is mutated by pane `resolution_changed` signals in-page. It is NOT
reset between resolution changes -- only between page (re-)entries.

### R4 -- `collect_selection` Fold and Reconstruction Copy (FR-009)

`_PageItemPicker.collect_selection()` calls `dataclasses.replace(base_selection,
similar_resolutions=dict(self._resolution_store))` to fold resolutions into the returned
`Selection`.

The `_PagePreview._on_preview` reconstruction path (~line 2186 of `selection_wizard.py`)
rebuilds a `Selection` from affix picks via `build_selection` and then applies
`_replace_conflict_modes`. This rebuilt `Selection` does NOT carry `similar_resolutions`
today (the field is not passed to `build_selection`). The fix: after the conflict-mode
replacement, apply a second `dataclasses.replace` to copy `similar_resolutions` from
the page-items `collect_selection()` result. This is the minimal surgical change; it does
not alter any planner or executor behavior.

### R5 -- `resolvable` Flag (FR-003, FR-007)

The `resolvable` flag on a `PreviewRequest` is `True` only for rows on `_PageItemPicker`
with status `"similar"` (SIMILAR) and a non-empty candidate list. It is `False` for:
all rows on `_PageSkeleton`, `_PageGramDeps`, and `_PagePhonology`; NEW and IN-TARGET
rows on `_PageItemPicker`; and SIMILAR rows with an empty candidate list. The pane
shows the resolution header iff `resolvable` is `True`.

### R6 -- Data Roles Required (FR-010)

The pane builds a `PreviewRequest` from the selected tree row using Qt item data roles.
The required roles per page:

| Page | Roles already set | Roles to add |
|------|------------------|--------------|
| `_PageItemPicker` | entry GUID (`UserRole`), status text ("NEW" / "IN TARGET" / "SIMILAR") | `_ITEM_STATUS_ROLE` (read status), `_ITEM_CAT_ROLE` (GrammarCategory) |
| `_PageSkeleton` | slot/template GUID | `_SKEL_STATUS_ROLE`, `_SKEL_CAT_ROLE`, `_SKEL_OWNER_ROLE` (owner POS GUID for template/slot preview) |
| `_PageGramDeps` | item GUID | `_DEPS_STATUS_ROLE`, `_DEPS_CAT_ROLE` (currently missing -- the audit gap flagged in spec edge cases) |
| `_PagePhonology` | `_PHON_GUID_ROLE`, `_PHON_CAT_ROLE` already defined (~line 1756) | `_PHON_STATUS_ROLE` (matched_target_guid for SIMILAR rows) |

New role constants follow the existing `UserRole + N` pattern; N values are chosen to
avoid collisions with existing constants.

### R7 -- Splitter Helper (FR-005, FR-011)

A module-level function `_make_tree_pane_splitter(tree_widget, pane_widget,
tree_stretch=3, pane_stretch=2) -> QSplitter` in `selection_wizard.py` creates the
horizontal splitter and sets initial stretch factors. Each page's `_build_ui` replaces
the direct `layout.addWidget(self._tree, 1)` call with a call to this helper. Wizard
window resize (`FR-011`) is handled by adjusting the `minimumSize` or calling
`QWizard.setMinimumSize` in the wizard's `__init__` to accommodate tree + pane side by
side.

### R8 -- Phonology SIMILAR: Display-Only (User Story 4)

SIMILAR phonology rows carry a `matched_target_guid` from 011. The pane for these rows
calls `preview_for(category, source_guid, matched_target_guid, "similar",
OVERWRITE, owner_guid="")` (using OVERWRITE as the display mode -- a compare preview).
The resolution header is hidden (`resolvable=False`). No `SimilarResolution` is seeded
or stored for phonology rows.

## Feature Requirements -- File & Anchor Map

### FR-001, FR-002 -- `MergePreviewPane` public API

**File**: `src/gramtrans/Lib/ui/merge_preview_pane.py` (NEW)

Three public methods:

```python
def set_context(
    self,
    service: MergePreviewService,
    registry: WsFontRegistry,
    candidates: list[tuple[str, str, str]],  # list of (entry_guid, form, gloss)
) -> None: ...

def show_item(self, request: PreviewRequest) -> None: ...

def clear(self) -> None: ...
```

`PreviewRequest` is a plain dataclass (or named tuple) defined in the same file:

```python
@dataclass
class PreviewRequest:
    category: str
    source_guid: str
    target_guid: str       # "" for NEW / create_new
    status: str            # "new" | "in_target" | "similar"
    mode: str              # OVERWRITE | MERGE_KEEP | NEW | LINK_ONLY
    resolvable: bool       # True only for affix SIMILAR on _PageItemPicker
    current_resolution: Optional[SimilarResolution]
    owner_guid: str = ""
```

`resolution_changed` signal (PyQt6 `pyqtSignal(str, object)`) carries
`(entry_guid, SimilarResolution)`.

### FR-003 -- Resolution header visibility

**File**: `src/gramtrans/Lib/ui/merge_preview_pane.py`

The resolution header widget (`QWidget` containing the combo + action buttons) is shown
via `setVisible(request.resolvable)` in `show_item`. The combo is populated from
`self._candidates` (set by `set_context`). The action control is a `QButtonGroup` of
three `QRadioButton`s (Overwrite / Merge / Create new). The combo is enabled when the
action is Overwrite or Merge, disabled when Create new is selected.

When the combo has no candidates (`self._candidates` is empty), the combo is shown empty
and disabled regardless of action; only Create new is viable. The action control still
shows all three buttons; Overwrite and Merge are visually enabled but clicking them does
not emit a resolution without a target (the pane guards: if action != "create_new" and
not target_guid, no signal is emitted).

### FR-004 -- Resolution signal and immediate diff recompute

**File**: `src/gramtrans/Lib/ui/merge_preview_pane.py`

On combo selection change or action button change:

1. Derive `new_action` ("overwrite" / "merge" / "create_new") and `new_target_guid`
   from the current control state.
2. Construct `SimilarResolution(entry_guid, new_action, new_target_guid)`.
3. Emit `resolution_changed(entry_guid, resolution)`.
4. Call `self._service.preview_for(category, source_guid, new_target_guid,
   status, mode_for(new_action), owner_guid)` and render the result via
   `to_html(preview, self._registry)`.

`mode_for` is the R1 mapping table as a local helper:

```python
def _action_to_mode(action: str) -> str:
    return {"overwrite": OVERWRITE, "merge": MERGE_KEEP, "create_new": NEW}[action]
```

### FR-005, FR-007, FR-011 -- Splitter integration in each page

**File**: `src/gramtrans/Lib/ui/selection_wizard.py`

Each of the four page classes gains:

- A `MergePreviewPane` instance (`self._pane`) constructed in `_build_ui`.
- A call to `_make_tree_pane_splitter(self._tree, self._pane)` replacing the direct
  `layout.addWidget(self._tree, 1)` line in `_build_ui`.
- A tree-selection handler `_on_tree_selection_changed(current, previous)` connected to
  `self._tree.currentItemChanged` in `initializePage` (with the existing double-connect
  guard pattern from `_PagePhonology`).
- A `MergePreviewService` instance (`self._preview_service`) constructed and
  `set_context`-called in `initializePage` after the inventory is built.

`_on_tree_selection_changed` logic:

1. If `current` is `None` or is a group/header row (kind role == "group"): call
   `self._pane.clear()` and return.
2. Read GUID, category, status, owner GUID from data roles (R6).
3. Determine `mode` and `target_guid` from status (R1 table + R8 for phonology SIMILAR).
4. Determine `resolvable` per R5.
5. Build `PreviewRequest` and call `self._pane.show_item(request)`.

### FR-006 -- `set_context` call on `initializePage`

**File**: `src/gramtrans/Lib/ui/selection_wizard.py`

After the inventory is populated and before the tree-selection signal is connected:

```python
self._preview_service = MergePreviewService(source, target)
self._pane.set_context(
    self._preview_service,
    WsFontRegistry.from_project(source),
    self._candidate_list(),   # [] for non-affix pages
)
```

If `initializePage` is re-entered, the service is rebuilt fresh and
`self._preview_service.invalidate()` is redundant (new object); `self._pane.clear()` is
called to reset the display.

### FR-008 -- Default seeding and store update in `_PageItemPicker`

**File**: `src/gramtrans/Lib/ui/selection_wizard.py`, `_PageItemPicker`

After populating the tree in `initializePage`:

```python
self._resolution_store: dict[str, SimilarResolution] = {}
for entry_guid, suggested_target_guid in self._similar_affix_pairs():
    self._resolution_store[entry_guid] = SimilarResolution(
        entry_guid=entry_guid,
        action="overwrite",
        target_guid=suggested_target_guid,
    )
```

`_similar_affix_pairs()` walks the tree items with status SIMILAR and reads
`suggested_target_guid` from the inventory row data.

On `resolution_changed` signal from the pane:

```python
def _on_resolution_changed(self, entry_guid: str, resolution: SimilarResolution) -> None:
    self._resolution_store[entry_guid] = resolution
    self._update_target_column(entry_guid, resolution)
```

`_update_target_column` reads the action and sets the Target column text on the matching
tree item(s) via `self._guid_to_items`:

| `resolution.action` | Target column text |
|---------------------|--------------------|
| `"overwrite"`       | `"SIMILAR -> overwrite"` |
| `"merge"`           | `"SIMILAR -> merge"` |
| `"create_new"`      | `"SIMILAR -> new"` |

### FR-009 -- `collect_selection` fold and reconstruction copy

**File**: `src/gramtrans/Lib/ui/selection_wizard.py`

`_PageItemPicker.collect_selection()` (current line 958) is modified:

```python
def collect_selection(self) -> Selection:
    if self._inventory is None:
        dummy = SourceAffixInventory()
        return build_selection(PickerState(), dummy)
    ps = self.picker_state()
    base = collapse_pos_grouped(ps.checked_affixes, self._inventory)
    import dataclasses
    return dataclasses.replace(base, similar_resolutions=dict(self._resolution_store))
```

`_PagePreview._on_preview` reconstruction (current ~line 2186):

```python
# After the existing build_selection + _replace_conflict_modes call:
page_items_selection = page_items.collect_selection()   # already has similar_resolutions
selection = dataclasses.replace(
    selection,
    similar_resolutions=page_items_selection.similar_resolutions,
)
```

### FR-010 -- Data role additions

**File**: `src/gramtrans/Lib/ui/selection_wizard.py`

New role constants added near the top of each page's section (following the
`_PHON_GUID_ROLE = QtCore.Qt.ItemDataRole.UserRole + 20` pattern):

```python
# _PageItemPicker roles
_ITEM_STATUS_ROLE  = QtCore.Qt.ItemDataRole.UserRole + 30  # "new" | "in_target" | "similar"
_ITEM_CAT_ROLE     = QtCore.Qt.ItemDataRole.UserRole + 31  # GrammarCategory

# _PageSkeleton roles
_SKEL_STATUS_ROLE  = QtCore.Qt.ItemDataRole.UserRole + 40
_SKEL_CAT_ROLE     = QtCore.Qt.ItemDataRole.UserRole + 41
_SKEL_OWNER_ROLE   = QtCore.Qt.ItemDataRole.UserRole + 42  # owner POS GUID

# _PageGramDeps roles
_DEPS_STATUS_ROLE  = QtCore.Qt.ItemDataRole.UserRole + 50
_DEPS_CAT_ROLE     = QtCore.Qt.ItemDataRole.UserRole + 51

# _PagePhonology (existing: 20-22; new:)
_PHON_STATUS_ROLE  = QtCore.Qt.ItemDataRole.UserRole + 23  # matched_target_guid for SIMILAR
```

Each role is set in the row-builder paths where item data is currently written (the
status text lines in the tree-populate helpers).

## Project Structure

### Documentation (this feature)

```text
specs/014-merge-preview-pane/
├── spec.md              # Feature specification (pre-existing)
├── plan.md              # This file
└── tasks.md             # Ordered implementation tasks (authored separately)
```

### Source Code (repository root)

```text
src/gramtrans/
├── gramtrans.py                          # FlexTools entry (unchanged)
└── Lib/
    ├── merge_preview.py                  # REUSED (012): MergePreviewService, to_html,
    │                                     #   OVERWRITE, MERGE_KEEP, NEW, LINK_ONLY
    ├── models.py                         # REUSED (011): SimilarResolution, Selection
    ├── ws_fonts.py                       # REUSED: WsFontRegistry
    └── ui/
        ├── merge_preview_pane.py         # NEW -- MergePreviewPane widget + PreviewRequest
        └── selection_wizard.py           # MODIFIED:
                                          #   _PageItemPicker: splitter, pane, resolution
                                          #     store, seeding, store update,
                                          #     collect_selection fold (FR-008, FR-009)
                                          #   _PageSkeleton: splitter, pane, set_context,
                                          #     tree-selection handler (FR-005, FR-006)
                                          #   _PageGramDeps: splitter, pane, set_context,
                                          #     tree-selection handler + data roles (FR-010)
                                          #   _PagePhonology: splitter, pane, set_context,
                                          #     tree-selection handler (R8)
                                          #   _make_tree_pane_splitter: NEW helper (R7)
                                          #   _PagePreview._on_preview: similar_resolutions
                                          #     copy in reconstruction path (FR-009)

tests/
└── unit/
    ├── test_014_pane_display.py          # NEW -- US1: offscreen-Qt pane renders NEW /
    │                                     #   IN-TARGET / group-clear; header hidden
    ├── test_014_resolution_control.py    # NEW -- US2: header visibility, combo filter,
    │                                     #   signal emission, mode recompute
    ├── test_014_resolution_seeding.py    # NEW -- US3: default seeding, store update,
    │                                     #   collect_selection fold, reconstruction copy
    └── test_014_phonology_display.py     # NEW -- US4: SIMILAR phonology compare preview,
                                          #   no resolution header
```

**Structure Decision**: The new widget is a single file under `Lib/ui/` following the
existing flat-`Lib/ui/` convention (no new subpackage). `PreviewRequest` is co-located
with `MergePreviewPane` in `merge_preview_pane.py` — it is a UI-layer data carrier, not
a model entity. Test files are one-per-user-story under `tests/unit/`, matching the
012/013 pattern.

## Complexity Tracking

No Constitution Check violations.

**Primary complexity source**: `selection_wizard.py` is a large file (~2200+ lines).
The four pages each require the same structural change (splitter + pane + handler +
set_context call). The shared `_make_tree_pane_splitter` helper reduces duplication, but
the data-role additions and inventory-walk paths differ per page. Tasks must be ordered
so each page is a discrete, independently testable unit.

**Secondary complexity**: the `_PageItemPicker` data-role audit (FR-010) and the
`_PageGramDeps` deps-category mapping (currently no `_DEPS_CAT_ROLE`) require reading the
inventory model carefully to determine which `GrammarCategory` enum value maps to each
deps section (inflection features, inflection classes, stem names). This is a
research/verify step before the deps page handler is implemented.

**Reconstruction copy (FR-009)**: the `_PagePreview._on_preview` path (~line 2186) uses
a non-obvious chain of `build_selection` + `_replace_conflict_modes` + phonology merge.
The `dataclasses.replace` for `similar_resolutions` must be inserted at the correct point
in this chain (after all other fields are resolved, before `compute_preview` is called).

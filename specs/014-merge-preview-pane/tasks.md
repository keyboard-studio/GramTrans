# Tasks: Merge-Preview Pane & Wizard Integration

**Feature**: 014-merge-preview-pane | **Date**: 2026-07-04

Upstream dependencies (must be merged before this feature begins):
- 011: `SimilarResolution`, `Selection.similar_resolutions`, candidate capture
- 012: `MergePreviewService`, `to_html`, `OVERWRITE`, `MERGE_KEEP`, `NEW`, `LINK_ONLY`
- 013: planner/executor honoring resolutions

Task ordering: shared infrastructure first (widget + splitter helper + data roles),
then per-page integration in dependency order (item-picker -> skeleton -> deps ->
phonology), then reconstruction fix, then tests.

Tasks marked **[P]** are parallelizable once their stated dependencies are complete.

---

## Phase 0 -- Shared Infrastructure

### T001 -- Create `merge_preview_pane.py`: `PreviewRequest` dataclass and stub widget

**Depends on**: None (first task; all later tasks depend on this)
**FR/SC**: FR-001, FR-002

Create `src/gramtrans/Lib/ui/merge_preview_pane.py` as a new file. Add the module
header matching the project's `Lib/ui/` convention (module name, platform, copyright).
Guard Qt imports at module level with `try/except ImportError` so the module can be
imported in a headless test environment.

Define the `PreviewRequest` dataclass:

```python
from __future__ import annotations
import dataclasses
from typing import Optional
from ..models import SimilarResolution

@dataclasses.dataclass
class PreviewRequest:
    category: str
    source_guid: str
    target_guid: str        # "" for NEW / create_new
    status: str             # "new" | "in_target" | "similar"
    mode: str               # OVERWRITE | MERGE_KEEP | NEW | LINK_ONLY
    resolvable: bool        # True only for affix SIMILAR on _PageItemPicker
    current_resolution: Optional[SimilarResolution]
    owner_guid: str = ""
```

Define the `MergePreviewPane` class stub (public API only; implementation in T002-T004):
- `__init__(self, parent=None)` — constructs the Qt widget skeleton
- `set_context(self, service, registry, candidates)` — stores service/registry/candidates
- `show_item(self, request: PreviewRequest)` — placeholder `pass`
- `clear(self)` — placeholder `pass`
- `resolution_changed` PyQt6 signal: `pyqtSignal(str, object)`

**Files**: `src/gramtrans/Lib/ui/merge_preview_pane.py` (NEW)

**Checklist**:
- [ ] `PreviewRequest` fields match plan R5 exactly (no extra fields).
- [ ] `resolution_changed = pyqtSignal(str, object)` declared on the class body.
- [ ] Module importable without PyQt6 installed (guarded import, stub class survives).
- [ ] No LCM imports anywhere in the file.
- [NOTE] LINK_ONLY is imported from 012's merge_preview.py for completeness but is NOT a valid 014 pane mode. Do not wire LINK_ONLY into any 014 PreviewRequest / mode combo. Valid 014 pane modes are OVERWRITE, MERGE_KEEP, NEW only (per R1).

---

### T002 -- Implement pane display: `QWebEngineView`/`QTextBrowser`, `show_item`, `clear`

**Depends on**: T001
**FR/SC**: FR-001, FR-002

Implement the HTML viewer region of `MergePreviewPane`:

1. In `__init__`, create a `QTextBrowser` (or `QWebEngineView` if available) for the
   HTML diff region. Use `QTextBrowser` as the safe fallback (no extra dependency).
2. Implement `set_context(self, service, registry, candidates)`:
   - Store `self._service = service`, `self._registry = registry`,
     `self._candidates = candidates` (list of `(entry_guid, form, gloss)` triples).
   - Clear the display.
3. Implement `show_item(self, request: PreviewRequest)`:
   - Store `self._current_request = request`.
   - If `request` is `None`, call `self.clear()` and return.
   - Call `self._service.preview_for(...)` with the request's fields to obtain a
     `MergePreview`.
   - Call `to_html(preview, self._registry)` and set the result on the text browser.
   - Call `self._resolution_header.setVisible(request.resolvable)` (header built in T003).
   - Populate and initialise the resolution controls from `request.current_resolution`
     (details in T003).
4. Implement `clear(self)`: clear the text browser, hide the resolution header, reset
   `self._current_request = None`.

Import `MergePreviewService`, `to_html`, `OVERWRITE`, `MERGE_KEEP`, `NEW` from
`..merge_preview`. Import `WsFontRegistry` from `..ws_fonts`.

**Files**: `src/gramtrans/Lib/ui/merge_preview_pane.py`

**Checklist**:
- [ ] `show_item` with a non-resolvable request hides the resolution header.
- [ ] `clear()` leaves the widget in the same state as just after `__init__`.
- [ ] `preview_for` is called with the full 4-tuple `(category, source_guid, target_guid, mode)` — never a 3-tuple.
- [ ] `to_html` output is set on the browser widget without modification.
- [NOTE] LINK_ONLY is imported from 012's merge_preview.py for completeness but is NOT a valid 014 pane mode. Do not wire LINK_ONLY into any 014 PreviewRequest / mode combo. Valid 014 pane modes are OVERWRITE, MERGE_KEEP, NEW only (per R1).

---

### T003 -- Implement resolution header: combo + three-way action control

**Depends on**: T001, T002
**FR/SC**: FR-003, FR-004, SC-002, SC-004, SC-007

Implement the resolution header widget inside `MergePreviewPane`:

1. Build a `QWidget` container (`self._resolution_header`) with a vertical layout:
   - A `QComboBox` (`self._combo`) for the target candidates.
   - A `QButtonGroup` of three `QRadioButton`s: "Overwrite", "Merge", "Create new"
     (`self._btn_overwrite`, `self._btn_merge`, `self._btn_create_new`).
2. Populate the combo in `_populate_combo(candidates)` — each item displays
   `"form — gloss"` (em dash, matching plan FR-003) and stores the target GUID as
   `Qt.ItemDataRole.UserRole` data. Filtering is by case-insensitive substring match
   implemented via `QSortFilterProxyModel` or by rebuilding the combo on text change;
   the combo must NOT allow free-text insertion (`setEditable(True)` +
   `setInsertPolicy(QComboBox.InsertPolicy.NoInsert)`).
3. Implement `_action_to_mode`:
   ```python
   _ACTION_TO_MODE = {"overwrite": OVERWRITE, "merge": MERGE_KEEP, "create_new": NEW}
   ```
4. Wire combo `currentIndexChanged` and each radio button `toggled` to
   `_on_resolution_control_changed(self)`:
   - Derive `new_action` and `new_target_guid` from current control state.
   - Guard: if `new_action != "create_new"` and `new_target_guid` is empty, do not
     emit a signal.
   - Construct `SimilarResolution(entry_guid, new_action, new_target_guid)`.
   - Emit `self.resolution_changed.emit(entry_guid, resolution)`.
   - Call `preview_for` with the new mode and re-render (same pattern as `show_item`).
   - Enable/disable the combo: enabled for Overwrite and Merge, disabled for Create new.
5. In `show_item`, after storing the request:
   - Block signals, set combo to the current resolution's target GUID, set the
     matching radio button, unblock signals (avoids spurious emissions on initialise).

**Files**: `src/gramtrans/Lib/ui/merge_preview_pane.py`

**Checklist**:
- [ ] Combo does not accept free-text; candidates only.
- [ ] Switching to Create new disables the combo and does not guard-block the signal.
- [ ] Switching to Overwrite/Merge with an empty combo does NOT emit `resolution_changed`.
- [ ] Signal carries the correct `(entry_guid, SimilarResolution)`.
- [ ] No `invalidate()` call on mode flip (plan R2: distinct 4-tuple cache key is sufficient).
- [ ] Signal blocking during `show_item` initialisation prevents double-emit.

---

### T004 -- Add `_make_tree_pane_splitter` shared helper to `selection_wizard.py`

**Depends on**: T001
**FR/SC**: FR-005, FR-011, R7

Add a module-level private function to `selection_wizard.py`, placed before the first
page class definition:

```python
def _make_tree_pane_splitter(tree_widget, pane_widget,
                             tree_stretch=3, pane_stretch=2):
    """Return a horizontal QSplitter with tree on the left and pane on the right.

    Replaces the direct layout.addWidget(tree, 1) call in each page's _build_ui.
    """
    splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
    splitter.addWidget(tree_widget)
    splitter.addWidget(pane_widget)
    splitter.setStretchFactor(0, tree_stretch)
    splitter.setStretchFactor(1, pane_stretch)
    return splitter
```

Also widen the wizard window: in the wizard's `__init__`, add or update
`self.setMinimumSize(QSize(W, H))` (W, H chosen to fit tree + pane comfortably side
by side at 1280+ width; confirm with a brief manual check on the FlexTools host).

**Files**: `src/gramtrans/Lib/ui/selection_wizard.py`

**Checklist**:
- [ ] Helper is private (underscore prefix).
- [ ] Returns a `QSplitter` (not a layout).
- [ ] Stretch factors are 3:2 (tree:pane) as per plan R7.
- [ ] Wizard `minimumSize` updated so tree + pane are not clipped at launch.

---

### T005 -- Add data-role constants: `_PageItemPicker` (`_ITEM_STATUS_ROLE`, `_ITEM_CAT_ROLE`)

**Depends on**: None [P]
**FR/SC**: FR-010, R6

In `selection_wizard.py`, add two new role constants near the top of the
`_PageItemPicker` section (following the `_PHON_GUID_ROLE = UserRole + 20` pattern
already present for phonology):

```python
_ITEM_STATUS_ROLE = QtCore.Qt.ItemDataRole.UserRole + 30  # "new" | "in_target" | "similar"
_ITEM_CAT_ROLE    = QtCore.Qt.ItemDataRole.UserRole + 31  # GrammarCategory
```

In the tree-row builder(s) for `_PageItemPicker`, wherever status text is set on each
affix item (the `"new"` / `"in_target"` / `"similar"` label), also call:

```python
item.setData(0, _ITEM_STATUS_ROLE, status_str)
item.setData(0, _ITEM_CAT_ROLE,    grammar_category)
```

`grammar_category` is the `GrammarCategory` enum value already available in the row
builder (it names the affix's part-of-speech category for the inventory).

**Files**: `src/gramtrans/Lib/ui/selection_wizard.py`, `_PageItemPicker` section

**Checklist**:
- [ ] `UserRole + 30` and `+ 31` do not collide with any existing role constant (grep
      confirmed: phonology uses 20-22; no other constant uses 30-31).
- [ ] Both roles set on every item row (new, in-target, similar), not only on SIMILAR rows.
- [ ] No existing behavior changed (roles are additive).

---

### T006 -- Add data-role constants: `_PageSkeleton` (`_SKEL_STATUS_ROLE`, `_SKEL_CAT_ROLE`, `_SKEL_OWNER_ROLE`)

**Depends on**: None [P]
**FR/SC**: FR-010, R6

Add three new role constants in the `_PageSkeleton` section (~line 1095):

```python
_SKEL_STATUS_ROLE = QtCore.Qt.ItemDataRole.UserRole + 40  # "new" | "in_target" | "similar"
_SKEL_CAT_ROLE    = QtCore.Qt.ItemDataRole.UserRole + 41  # GrammarCategory (slot / template)
_SKEL_OWNER_ROLE  = QtCore.Qt.ItemDataRole.UserRole + 42  # owner POS GUID (for template/slot preview)
```

In the skeleton tree-row builder, wherever status text is set on slot and template
item rows, also set all three roles:

```python
item.setData(0, _SKEL_STATUS_ROLE, status_str)
item.setData(0, _SKEL_CAT_ROLE,    grammar_category)
item.setData(0, _SKEL_OWNER_ROLE,  owner_pos_guid)
```

The `owner_pos_guid` is the GUID of the POS node that owns the slot or template; it
is the value already iterated at the POS-node level of the skeleton builder.

**Files**: `src/gramtrans/Lib/ui/selection_wizard.py`, `_PageSkeleton` section

**Checklist**:
- [ ] `UserRole + 40/41/42` do not collide with any existing role constant.
- [ ] Owner GUID set correctly for both slot rows and template rows.
- [ ] Group/header rows (the POS node itself) do NOT receive item-level status roles
      (or receive a sentinel that `_on_tree_selection_changed` filters as a group).

---

### T007 -- Add data-role constants: `_PageGramDeps` (`_DEPS_STATUS_ROLE`, `_DEPS_CAT_ROLE`)

**Depends on**: None [P]
**FR/SC**: FR-010, R6

`_PageGramDeps` (~line 1532) currently sets no category or status data role on its
tree rows — the audit gap identified in the spec edge cases. This task closes that gap.

Add two new role constants in the `_PageGramDeps` section:

```python
_DEPS_STATUS_ROLE = QtCore.Qt.ItemDataRole.UserRole + 50  # "new" | "in_target" | "similar"
_DEPS_CAT_ROLE    = QtCore.Qt.ItemDataRole.UserRole + 51  # GrammarCategory
```

**Research step (required before coding)**: Walk the `_PageGramDeps` tree-builder to
confirm which `GrammarCategory` enum value maps to each section (inflection features,
inflection classes, stem names). Read the inventory model structure to determine whether
category is already derivable from the row's section header or must be read from the
row data source. Document the mapping in the task's commit message.

In the row-builder paths, wherever status text is written on deps item rows, also set:

```python
item.setData(0, _DEPS_STATUS_ROLE, status_str)
item.setData(0, _DEPS_CAT_ROLE,    grammar_category)
```

**Files**: `src/gramtrans/Lib/ui/selection_wizard.py`, `_PageGramDeps` section

**Checklist**:
- [ ] `UserRole + 50/51` do not collide with existing constants.
- [ ] All three deps sections (inflection features, inflection classes, stem names)
      have the correct `GrammarCategory` mapped.
- [ ] Section-header (group) rows do NOT receive item-level status roles.
- [ ] The research mapping is confirmed before the PR is filed.

---

### T008 -- Add data-role constant: `_PagePhonology` (`_PHON_STATUS_ROLE`)

**Depends on**: None [P]
**FR/SC**: FR-010, R6, R8

`_PagePhonology` (~line 1756) already defines `_PHON_GUID_ROLE` (UserRole+20),
`_PHON_KIND_ROLE` (UserRole+21), `_PHON_CAT_ROLE` (UserRole+22). Add:

```python
_PHON_STATUS_ROLE = QtCore.Qt.ItemDataRole.UserRole + 23  # "new" | "in_target" | "similar"
```

For SIMILAR phonology rows, the status value is `"similar"` and the role also carries
the `matched_target_guid` as a second read in `_on_tree_selection_changed` (see T012).
In the phonology row-builder, wherever a row's match status is set (the "similar" /
"new" / "in_target" logic from feature 011), also set:

```python
item.setData(0, _PHON_STATUS_ROLE, status_str)
```

For SIMILAR phonology rows, the `matched_target_guid` is already stored in the
`_PHON_GUID_ROLE` slot or a separate mechanism from feature 011 — verify which, and
read `matched_target_guid` from that existing slot in `_on_tree_selection_changed`
rather than adding a duplicate role.

**Files**: `src/gramtrans/Lib/ui/selection_wizard.py`, `_PagePhonology` section

**Checklist**:
- [ ] `UserRole + 23` does not collide (next available after 22).
- [ ] Status role set on all phonology item rows (all five categories).
- [ ] Group rows receive `_PHON_KIND_ROLE = "group"` (already set); they do not
      receive `_PHON_STATUS_ROLE` (filtered in the selection handler).

---

## Phase 1 -- Per-Page Integration

### T009 -- Integrate pane into `_PageItemPicker`: splitter, `set_context`, selection handler

**Depends on**: T001, T002, T003, T004, T005
**FR/SC**: FR-005, FR-006, FR-007, FR-008, R3, R5, SC-001

Wire the pane into `_PageItemPicker` (~line 573 of `selection_wizard.py`):

1. **`_build_ui`**: Construct `self._pane = MergePreviewPane(self)` and replace
   `layout.addWidget(self._tree, 1)` with:
   ```python
   splitter = _make_tree_pane_splitter(self._tree, self._pane)
   layout.addWidget(splitter, 1)
   ```

2. **`initializePage`**: After populating the tree and before returning:
   ```python
   self._preview_service = MergePreviewService(source, target)
   self._pane.set_context(
       self._preview_service,
       WsFontRegistry.from_project(source),
       self._candidate_list(),   # list of (guid, form, gloss) for SIMILAR affix candidates
   )
   self._pane.clear()
   ```
   Connect `self._tree.currentItemChanged` to `self._on_tree_selection_changed` with the
   double-connect guard (check whether the signal is already connected before connecting).

3. **`_on_tree_selection_changed(self, current, previous)`**: New method.
   - If `current is None` or `current.data(0, _ITEM_KIND_ROLE) == "group"`: call
     `self._pane.clear()` and return.
   - Read `source_guid`, `category`, `status` from `_ITEM_GUID_ROLE` (or equivalent),
     `_ITEM_CAT_ROLE`, `_ITEM_STATUS_ROLE`.
   - Determine `target_guid` and `mode`:
     - `"new"`: `target_guid=""`, `mode=NEW`.
     - `"in_target"`: `target_guid=source_guid`, `mode=OVERWRITE`.
     - `"similar"`: `target_guid=resolution_store.get(source_guid).target_guid`,
       `mode=_action_to_mode(resolution.action)`.
   - `resolvable = (status == "similar" and bool(self._candidates))` per R5.
   - Build `PreviewRequest` and call `self._pane.show_item(request)`.

4. **Resolution store initialisation** (FR-008 default seeding, R3): add
   `self._resolution_store: dict = {}` in `__init__`. In `initializePage`, after tree
   population, seed defaults (details in T010).

5. **Connect `resolution_changed`**: connect `self._pane.resolution_changed` to
   `self._on_resolution_changed` (implementation in T010).

**Files**: `src/gramtrans/Lib/ui/selection_wizard.py`, `_PageItemPicker`

**Checklist**:
- [ ] Splitter replaces the direct `addWidget(self._tree, 1)` call exactly.
- [ ] `_preview_service` is constructed fresh on each `initializePage` (no stale state).
- [ ] `_on_tree_selection_changed` fires once per selection (double-connect guard present).
- [ ] Group/header rows produce `self._pane.clear()` with no further processing.
- [ ] `resolvable=False` for NEW and IN-TARGET rows (header hidden).
- [ ] `resolvable=True` only when `status == "similar"` and candidates are non-empty.
- [ ] The 4-tuple passed to `preview_for` always uses the current resolution's `mode`,
      not a hardcoded mode.

---

### T010 -- `_PageItemPicker`: resolution store seeding, store update, Target column reflect

**Depends on**: T009
**FR/SC**: FR-008, SC-003, SC-004

Implement the full resolution store lifecycle on `_PageItemPicker`:

1. **`_similar_affix_pairs(self)`**: New private method. Walks `self._tree` items with
   `_ITEM_STATUS_ROLE == "similar"`, reads `source_guid` and `suggested_target_guid`
   (the suggested match from feature 011 — confirm the role or attribute name from the
   011 row-builder). Returns a list of `(source_guid, suggested_target_guid)` pairs.

2. **`initializePage` seeding** (after tree population, before `set_context`):
   ```python
   self._resolution_store = {}
   for entry_guid, suggested_target_guid in self._similar_affix_pairs():
       self._resolution_store[entry_guid] = SimilarResolution(
           entry_guid=entry_guid,
           action="overwrite",
           target_guid=suggested_target_guid,
       )
   ```

3. **`_on_resolution_changed(self, entry_guid: str, resolution: SimilarResolution)`**:
   ```python
   def _on_resolution_changed(self, entry_guid, resolution):
       self._resolution_store[entry_guid] = resolution
       self._update_target_column(entry_guid, resolution)
   ```

4. **`_update_target_column(self, entry_guid, resolution)`**: New private method.
   Reads `self._guid_to_items[entry_guid]` (the tree item list for this GUID) and
   sets the Target column (column 4) text:

   | `resolution.action` | Target column text |
   |---------------------|--------------------|
   | `"overwrite"`       | `"SIMILAR -> overwrite"` |
   | `"merge"`           | `"SIMILAR -> merge"` |
   | `"create_new"`      | `"SIMILAR -> new"` |

   Also updates the tree item's `_ITEM_STATUS_ROLE` if the resolution changes the
   effective target GUID (so subsequent selection-handler reads stay consistent).

5. After seeding, call `_update_target_column` for each SIMILAR row to initialise the
   Target column text to `"SIMILAR -> overwrite"`.

**Files**: `src/gramtrans/Lib/ui/selection_wizard.py`, `_PageItemPicker`

**Checklist**:
- [ ] 100% of SIMILAR rows have a store entry after `initializePage` (no gaps).
- [ ] Store is reset to `{}` at the top of `initializePage` (not accumulated across entries).
- [ ] `_update_target_column` handles all three action strings without a KeyError.
- [ ] `self._guid_to_items` is confirmed to exist in the 011 implementation before use.
- [ ] Target column text is set even when `resolution.target_guid` is empty (create_new).

---

### T011 -- `_PageItemPicker`: `collect_selection` fold (FR-009)

**Depends on**: T010
**FR/SC**: FR-009, SC-006

Modify `_PageItemPicker.collect_selection()` (current ~line 958) to fold the page's
resolution store into the returned `Selection`:

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

The `import dataclasses` can be moved to the module top-level if it is not already
present. `dict(self._resolution_store)` is a shallow copy so the caller cannot mutate
the page's live store.

**Files**: `src/gramtrans/Lib/ui/selection_wizard.py`, `_PageItemPicker.collect_selection`

**Checklist**:
- [ ] Returned `Selection.similar_resolutions` is a copy, not a reference to the live store.
- [ ] The dummy/fallback path (inventory is None) returns an empty `similar_resolutions`
      (the dataclass default), not `None`.
- [ ] All existing callers of `collect_selection` continue to work (the new field is
      additive; callers that do not read `similar_resolutions` are unaffected).
- [ ] MUST NOT touch planner/executor (FR-012) — reconstruction copy in _PagePreview._on_preview and collect_selection fold are UI/selection layer only.

---

### T012 -- Integrate pane into `_PagePhonology`: splitter, `set_context`, selection handler (display-only)

**Depends on**: T001, T002, T004, T008
**FR/SC**: FR-005, FR-006, FR-007, R8, SC-001, SC-005

Wire the pane into `_PagePhonology` (~line 1761):

1. **`_build_ui`**: Construct `self._pane = MergePreviewPane(self)` and replace
   `layout.addWidget(self._tree, 1)` with the splitter helper call.

2. **`initializePage`**: Construct `self._preview_service = MergePreviewService(source, target)`,
   call `self._pane.set_context(self._preview_service, WsFontRegistry.from_project(source), [])`.
   Call `self._pane.clear()`. Connect `self._tree.currentItemChanged` to
   `self._on_tree_selection_changed` using the **existing double-connect guard** already
   present in `_PagePhonology` (the spec edge case explicitly calls this out).

3. **`_on_tree_selection_changed(self, current, previous)`**: New method.
   - If `current is None` or `current.data(0, _PHON_KIND_ROLE) == "group"`: `self._pane.clear()`.
   - Read `source_guid` from `_PHON_GUID_ROLE`, `category` from `_PHON_CAT_ROLE`,
     `status` from `_PHON_STATUS_ROLE`.
   - Per R8: all phonology rows use `resolvable=False` (no resolution header shown).
   - Mode selection:
     - `"similar"`: `target_guid = matched_target_guid` (read from existing role —
       confirm the slot from 011), `mode=OVERWRITE` (display compare, per R8).
     - `"new"`: `target_guid=""`, `mode=NEW`.
     - `"in_target"`: `target_guid=source_guid`, `mode=OVERWRITE`.
   - Build `PreviewRequest(resolvable=False, ...)` and call `self._pane.show_item(request)`.

**Files**: `src/gramtrans/Lib/ui/selection_wizard.py`, `_PagePhonology`

**Checklist**:
- [ ] `resolvable=False` for ALL phonology rows (including SIMILAR); no resolution header.
- [ ] Double-connect guard is applied (existing pattern; do not remove it).
- [ ] SIMILAR phonology uses `OVERWRITE` mode for display, not `MERGE_KEEP`.
- [ ] No `SimilarResolution` is seeded or stored for phonology.
- [ ] `matched_target_guid` source confirmed against 011 implementation before coding.

---

### T013 -- Integrate pane into `_PageSkeleton`: splitter, `set_context`, selection handler [P]

**Depends on**: T001, T002, T004, T006
**FR/SC**: FR-005, FR-006, FR-007, SC-001

Wire the pane into `_PageSkeleton` (~line 1095). This page has no resolution workflow
(all rows are display-only); `resolvable=False` for all rows.

1. **`_build_ui`**: `self._pane = MergePreviewPane(self)` + splitter helper.
2. **`initializePage`**: Construct service, call `set_context` with empty candidate list,
   clear pane, connect `currentItemChanged` (with double-connect guard).
3. **`_on_tree_selection_changed`**:
   - Group rows -> `self._pane.clear()`.
   - Item rows: read `source_guid` (`_SKEL_GUID_ROLE` or equivalent), `category`
     (`_SKEL_CAT_ROLE`), `status` (`_SKEL_STATUS_ROLE`), `owner_guid` (`_SKEL_OWNER_ROLE`).
   - `target_guid` derived same as item-picker (new=`""`, in_target=source, similar=matched).
   - Build `PreviewRequest(resolvable=False, owner_guid=owner_guid)` and call `show_item`.

**Files**: `src/gramtrans/Lib/ui/selection_wizard.py`, `_PageSkeleton`

**Checklist**:
- [ ] Owner GUID flows into `PreviewRequest.owner_guid` for slot/template rows.
- [ ] `resolvable=False` for all skeleton rows.
- [ ] Double-connect guard present.
- [ ] Existing skeleton page behavior (checkboxes, skeleton collection) unchanged.

---

### T014 -- Integrate pane into `_PageGramDeps`: splitter, `set_context`, selection handler [P]

**Depends on**: T001, T002, T004, T007
**FR/SC**: FR-005, FR-006, FR-007, FR-010, SC-001

Wire the pane into `_PageGramDeps` (~line 1532). This page had the deps-category
data-role gap (fixed in T007); this task uses those new roles.

1. **`_build_ui`**: `self._pane = MergePreviewPane(self)` + splitter helper.
2. **`initializePage`**: Construct service, call `set_context` with empty candidate list,
   clear pane, connect `currentItemChanged` (with double-connect guard).
3. **`_on_tree_selection_changed`**:
   - Group/section-header rows -> `self._pane.clear()`.
   - Item rows: read `source_guid` (existing GUID role), `category` (`_DEPS_CAT_ROLE`),
     `status` (`_DEPS_STATUS_ROLE`).
   - No owner GUID needed for deps rows (`owner_guid=""`).
   - `resolvable=False` for all deps rows.
   - Build `PreviewRequest` and call `show_item`.

**Files**: `src/gramtrans/Lib/ui/selection_wizard.py`, `_PageGramDeps`

**Checklist**:
- [ ] Uses `_DEPS_CAT_ROLE` and `_DEPS_STATUS_ROLE` introduced in T007.
- [ ] Section-header rows (inflection features, inflection classes, stem names headers)
      produce `self._pane.clear()` rather than a preview attempt.
- [ ] `resolvable=False` for all deps rows.
- [ ] Existing deps page behavior (checkboxes, dependency collection) unchanged.

---

## Phase 2 -- Reconstruction Fix

### T015 -- `_PagePreview._on_preview`: copy `similar_resolutions` in dry-run reconstruction

**Depends on**: T011
**FR/SC**: FR-009, SC-006

The `_PagePreview._on_preview` reconstruction path (~line 2186 of `selection_wizard.py`)
rebuilds a `Selection` from affix picks using `build_selection` + `_replace_conflict_modes`.
The rebuilt `Selection` drops `similar_resolutions` today because `build_selection` does
not accept or pass through that field.

Fix: after the existing `build_selection` + `_replace_conflict_modes` chain, insert:

```python
# Preserve similar_resolutions from the item-picker page across reconstruction.
page_items_selection = page_items.collect_selection()   # already carries similar_resolutions
selection = dataclasses.replace(
    selection,
    similar_resolutions=page_items_selection.similar_resolutions,
)
```

where `page_items` is the `_PageItemPicker` instance (already accessible in
`_on_preview` via `self.wizard().page(PAGE_ITEM_PICKER)` or the equivalent local
reference used in that function). `selection` is the `Selection` produced by the
reconstruction chain immediately above this insertion point.

The insertion is **before** any `compute_preview` call that consumes the selection —
confirm the exact line by reading the reconstruction chain in `_on_preview` before
coding.

**Files**: `src/gramtrans/Lib/ui/selection_wizard.py`, `_PagePreview._on_preview` (~line 2186)

**Checklist**:
- [ ] Insertion is after `_replace_conflict_modes` and before `compute_preview` (verify
      line order by reading the function).
- [ ] `dataclasses` is imported at module level (or already imported).
- [ ] `similar_resolutions` from the picker page is a copy (T011 already returns a copy
      from `collect_selection`); no aliasing concern.
- [ ] No other fields of `selection` are altered by this line.
- [ ] Existing `_PagePreview` test paths (dry-run with no SIMILAR rows) pass unchanged.
- [ ] MUST NOT touch planner/executor (FR-012) — reconstruction copy in _PagePreview._on_preview and collect_selection fold are UI/selection layer only.

---

## Phase 3 -- Tests

### T016 -- Test file: `test_014_pane_display.py` (US1 -- pane renders, clear on group) [P]

**Depends on**: T001, T002
**FR/SC**: FR-001, FR-002, SC-001, SC-007

**File**: `tests/unit/test_014_pane_display.py` (NEW)

Set `QT_QPA_PLATFORM=offscreen` and call `pytest.importorskip("PyQt6")` at the top.
Create a minimal `QApplication` fixture (session-scoped).

Test cases:

1. **`test_new_row_renders_all_green`**: Build a `MergePreviewPane`, call `set_context`
   with a stub `MergePreviewService` that returns a fixed all-added `MergePreview`,
   call `show_item` with a NEW `PreviewRequest`, assert the text browser's
   `toHtml()` or `toPlainText()` contains the expected diff content.

2. **`test_in_target_row_renders_compare`**: Same pattern with an IN-TARGET request
   (same GUID as source); stub service returns a compare `MergePreview`; assert content.

3. **`test_group_row_clears_pane`**: After a successful `show_item`, call `clear()`
   and assert the text browser content is empty and the resolution header is hidden.

4. **`test_set_context_clears_display`**: Call `set_context` on a pane that already
   has content; assert content is cleared.

Stub the `MergePreviewService` with a simple object that implements `preview_for`
returning a fixed `MergePreview`; stub `to_html` to return a known HTML string.

**Files**: `tests/unit/test_014_pane_display.py` (NEW)

**Checklist**:
- [ ] `QT_QPA_PLATFORM=offscreen` set before `QApplication` construction.
- [ ] `pytest.importorskip("PyQt6")` at module level.
- [ ] Stub service does not require a live LCM project.
- [ ] Tests are marked `not integration` (no fixture dependency on live project).
- [ ] All four test cases present and passing.

---

### T017 -- Test file: `test_014_resolution_control.py` (US2 -- header, combo, signals) [P]

**Depends on**: T001, T002, T003
**FR/SC**: FR-003, FR-004, SC-002, SC-004, SC-007

**File**: `tests/unit/test_014_resolution_control.py` (NEW)

Offscreen Qt harness (same setup as T016).

Test cases covering SC-007 requirements:

1. **`test_header_visible_for_similar_resolvable`**: Show a SIMILAR `PreviewRequest`
   with `resolvable=True`; assert `pane._resolution_header.isVisible() is True`.

2. **`test_header_hidden_for_new_row`**: Show a NEW `PreviewRequest` with
   `resolvable=False`; assert `pane._resolution_header.isVisible() is False`.

3. **`test_header_hidden_for_in_target_row`**: Show an IN-TARGET `PreviewRequest`
   with `resolvable=False`; assert header hidden.

4. **`test_combo_substring_filter_case_insensitive`**: Set up candidates
   `[("g1","run","go fast"), ("g2","walk","go slow")]`; type "FAST" into the combo's
   line edit; assert only the "run" candidate is visible (case-insensitive match).

5. **`test_overwrite_resolution_signal`**: With a SIMILAR pane showing a candidate,
   click "Overwrite"; capture the `resolution_changed` signal via `QSignalSpy`; assert
   the emitted `SimilarResolution.action == "overwrite"` and `target_guid` matches the
   selected candidate GUID.

6. **`test_merge_resolution_signal`**: Switch to "Merge"; assert signal carries
   `action="merge"` with same target GUID.

7. **`test_create_new_resolution_signal`**: Switch to "Create new"; assert signal
   carries `action="create_new"` and `target_guid=""` (or `None`).

8. **`test_no_signal_without_target_for_overwrite`**: Empty candidates, action=Overwrite;
   assert no `resolution_changed` signal emitted.

**Files**: `tests/unit/test_014_resolution_control.py` (NEW)

**Checklist**:
- [ ] `QSignalSpy` used to capture `resolution_changed` emissions.
- [ ] Combo substring filter test confirms case-insensitivity (both upper and lower input).
- [ ] All eight test cases present.
- [ ] No live LCM required (stub service).

---

### T018 -- Test file: `test_014_resolution_seeding.py` (US3 -- seeding, fold, reconstruction) [P]

**Depends on**: T010, T011, T015
**FR/SC**: FR-008, FR-009, SC-003, SC-006

**File**: `tests/unit/test_014_resolution_seeding.py` (NEW)

These tests exercise the resolution store and `collect_selection` fold. The item-picker
page requires the wizard context to initialize; use a minimal fake wizard + fake
inventory fixture that satisfies `initializePage` without a live LCM project.

Test cases:

1. **`test_default_seeding_overwrite`**: Build the item-picker page with two SIMILAR
   affix rows in the fake inventory; call `initializePage`; assert that
   `page._resolution_store` contains two entries, both with `action="overwrite"` and
   `target_guid == suggested_target_guid`.

2. **`test_collect_selection_includes_resolutions`**: After seeding, call
   `page.collect_selection()`; assert `selection.similar_resolutions` is non-empty and
   matches the store.

3. **`test_store_update_on_resolution_changed`**: Emit a `resolution_changed` signal
   with `action="merge"` for one GUID; assert `page._resolution_store[guid].action == "merge"`.

4. **`test_target_column_text_updated`**: After the store update in test 3, assert the
   tree item's Target column (column 4) text is `"SIMILAR -> merge"`.

5. **`test_reconstruction_preserves_similar_resolutions`**: Build a `PreviewRequest`
   fixture that invokes the reconstruction path; assert that the reconstructed
   `Selection.similar_resolutions` is non-empty (matches the picker page store).
   This test may require a fake `_PagePreview` wrapper; stub as needed.

**Files**: `tests/unit/test_014_resolution_seeding.py` (NEW)

**Checklist**:
- [ ] Fake inventory fixture has at least two SIMILAR affix rows.
- [ ] Test 5 covers the reconstruction copy from T015 (the `dataclasses.replace` line).
- [ ] No live LCM required.
- [ ] All five test cases present.

---

### T019 -- Test file: `test_014_phonology_display.py` (US4 -- phonology SIMILAR, no header) [P]

**Depends on**: T001, T002, T012
**FR/SC**: FR-007, SC-005, SC-007

**File**: `tests/unit/test_014_phonology_display.py` (NEW)

Offscreen Qt harness.

Test cases:

1. **`test_similar_phonology_shows_compare_no_header`**: Build the pane, call
   `show_item` with a phonology SIMILAR `PreviewRequest` (`resolvable=False`,
   `mode=OVERWRITE`, `target_guid=matched_target_guid`); assert a compare preview
   renders (stub service returns a compare `MergePreview`) and the resolution header
   is hidden.

2. **`test_new_phonology_shows_all_green_no_header`**: Show a NEW phonology row
   (`resolvable=False`, `mode=NEW`, `target_guid=""`); assert all-green preview renders
   and resolution header is hidden.

3. **`test_phonology_similar_no_resolution_stored`**: Confirm that `_PagePhonology`
   does not maintain a `_resolution_store` attribute (phonology is display-only, R8).

**Files**: `tests/unit/test_014_phonology_display.py` (NEW)

**Checklist**:
- [ ] Stub service returns an appropriate `MergePreview` for each mode.
- [ ] Resolution header confirmed hidden via `pane._resolution_header.isVisible() is False`.
- [ ] Test 3 uses `hasattr` or `getattr` with a sentinel; does not crash on absence.
- [ ] All three test cases present.

---

## Dependency Graph

```
T001 (PreviewRequest + stub widget)
  |
  +-- T002 (viewer: show_item, clear)
  |     |
  |     +-- T003 (resolution header: combo + radio)
  |     |     |
  |     |     +-- T009 (item-picker: splitter + set_context + handler)
  |     |           |
  |     |           +-- T010 (resolution store seeding + update)
  |     |                 |
  |     |                 +-- T011 (collect_selection fold)
  |     |                       |
  |     |                       +-- T015 (reconstruction copy)
  |     |
  |     +-- T012 (phonology: splitter + handler) [P after T004+T008]
  |     +-- T013 (skeleton: splitter + handler)  [P after T004+T006]
  |     +-- T014 (deps: splitter + handler)      [P after T004+T007]
  |
  +-- T004 (_make_tree_pane_splitter + wizard resize)

T005 [P] -> T009
T006 [P] -> T013
T007 [P] -> T014
T008 [P] -> T012

Tests (all [P] once their impl deps are met):
T016 -> T001, T002
T017 -> T001, T002, T003
T018 -> T010, T011, T015
T019 -> T001, T002, T012
```

---

## Task Count

| ID | Description | Phase | Files |
|----|-------------|-------|-------|
| T001 | `PreviewRequest` + widget stub | 0 - Infra | `merge_preview_pane.py` (NEW) |
| T002 | Pane display: viewer, `show_item`, `clear` | 0 - Infra | `merge_preview_pane.py` |
| T003 | Resolution header: combo + three-way action | 0 - Infra | `merge_preview_pane.py` |
| T004 | `_make_tree_pane_splitter` helper + wizard resize | 0 - Infra | `selection_wizard.py` |
| T005 | Data roles: `_PageItemPicker` (`_ITEM_STATUS_ROLE`, `_ITEM_CAT_ROLE`) | 0 - Infra | `selection_wizard.py` |
| T006 | Data roles: `_PageSkeleton` (status, cat, owner) | 0 - Infra | `selection_wizard.py` |
| T007 | Data roles: `_PageGramDeps` (status, cat) — research step required | 0 - Infra | `selection_wizard.py` |
| T008 | Data roles: `_PagePhonology` (`_PHON_STATUS_ROLE`) | 0 - Infra | `selection_wizard.py` |
| T009 | Item-picker: splitter, `set_context`, selection handler | 1 - Pages | `selection_wizard.py` |
| T010 | Item-picker: resolution store seeding, store update, Target column | 1 - Pages | `selection_wizard.py` |
| T011 | Item-picker: `collect_selection` fold | 1 - Pages | `selection_wizard.py` |
| T012 | Phonology: splitter, `set_context`, selection handler | 1 - Pages | `selection_wizard.py` |
| T013 | Skeleton: splitter, `set_context`, selection handler | 1 - Pages | `selection_wizard.py` |
| T014 | GramDeps: splitter, `set_context`, selection handler | 1 - Pages | `selection_wizard.py` |
| T015 | `_PagePreview._on_preview`: reconstruction `similar_resolutions` copy | 2 - Recon | `selection_wizard.py` |
| T016 | Tests: `test_014_pane_display.py` (US1) | 3 - Tests | `tests/unit/` (NEW) |
| T017 | Tests: `test_014_resolution_control.py` (US2, SC-007) | 3 - Tests | `tests/unit/` (NEW) |
| T018 | Tests: `test_014_resolution_seeding.py` (US3) | 3 - Tests | `tests/unit/` (NEW) |
| T019 | Tests: `test_014_phonology_display.py` (US4) | 3 - Tests | `tests/unit/` (NEW) |

**Total: 19 tasks**
(8 Phase-0 infrastructure, 6 Phase-1 page integration, 1 Phase-2 reconstruction fix, 4 Phase-3 test files)

---

## Traceability Matrix

| Requirement | Tasks | Status |
|-------------|-------|--------|
| **FR-001** MergePreviewPane renders via `to_html`, no direct LCM | T001, T002, T016 | Covered |
| **FR-002** `set_context`, `show_item`, `clear`, `PreviewRequest` API | T001, T002 | Covered |
| **FR-003** Resolution header visible only for affix SIMILAR (`resolvable`); searchable combo; enable/disable | T003, T017 | Covered |
| **FR-004** Combo/action change emits signal and immediately recomputes diff | T003, T017 | Covered |
| **FR-005** Horizontal splitter (tree left, pane right) on each page | T004, T009, T012, T013, T014 | Covered |
| **FR-006** Each page's `initializePage` constructs service, calls `set_context`, connects handler | T009, T012, T013, T014 | Covered |
| **FR-007** `PreviewRequest` mode/target/resolvable derived correctly per page and status | T009, T012, T013, T014 | Covered |
| **FR-008** Default `overwrite(guid -> suggested_target_guid)` seeding; store update; Target column reflect | T010, T018 | Covered |
| **FR-009** `collect_selection` folds resolutions; reconstruction copies `similar_resolutions` | T011, T015, T018 | Covered |
| **FR-010** Data-role gaps closed: deps (cat + status); skeleton (status, cat, owner); phonology (status); item-picker (status, cat) | T005, T006, T007, T008 | Covered |
| **FR-011** Wizard window resized to fit tree + pane | T004 | Covered |
| **FR-012** No change to transfer planning/execution behavior | All tasks (constraint) | Enforced — no planner/executor files touched |
| | | |
| **SC-001** Per-item preview renders on first click, instant on cache hit | T009, T012, T013, T014 | Covered (4-tuple cache key used, no invalidate on flip) |
| **SC-002** Resolution flip recomputes diff in-page, no page reload | T003, T017 | Covered |
| **SC-003** 100% of SIMILAR rows default to overwrite-to-suggested; change reflected in collected selection | T010, T018 | Covered |
| **SC-004** Resolution header shown only for affix SIMILAR rows; hidden elsewhere | T003, T009, T017 | Covered |
| **SC-005** SIMILAR phonology: compare preview, no resolution control; NEW phonology: all-green | T012, T019 | Covered |
| **SC-006** Reconstruction preserves `similar_resolutions` (0 dropped) | T015, T018 | Covered |
| **SC-007** Offscreen-Qt tests: header visibility, combo substring filter, both resolution signals | T016, T017, T018, T019 | Covered |

All 12 functional requirements and 7 success criteria are covered by at least one task.
No requirement is orphaned.

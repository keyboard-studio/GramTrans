"""Selection Wizard (Phase 3c, plan.md Refinement 3, 2026-07-01).

5-page QWizard that replaces the single-window `main_window.py`.  The
existing widgets are re-hosted verbatim; no widget logic is rewritten.

Pages:
  1  Project + Writing Systems  (WS is a project-level decision, made ONCE)
  2  Item picker                (affix / stem / affix-template tree)
  3  Schema scope + conflict mode
  4  Preview / StatsPanel
  5  Finish / Move              (the ONLY write point)

Writing-system rules:
- Enumerate ACTIVE writing systems only (analysis + vernacular active in
  the project; not the full installed superset).
- The two-stage NEEDS_WS_MAPPING handshake is RETIRED -- page-1 handles WS
  once, project-level.

Constitution alignment:
- Principle III: the only write is in the page-5 Finish handler, which
  first queries `plan.excluded_lossy_count()` and blocks/confirms if > 0.
- Principle V: per-item deselection surfaces on page 3; EXCLUDED-LOSSY
  warnings surface on page 4 (StatsPanel).
"""
from __future__ import annotations

import dataclasses
from typing import Optional, Set

from PyQt6 import QtCore, QtWidgets

if __package__:
    from .. import api as gt_api
    from ..models import (
        CategoryScope,
        ConflictMode,
        ExcludedLossy,
        GrammarCategory,
        RunMode,
        Selection,
        WSKind,
        WSMapping,
        WSMappingEntry,
        _DEFAULT_CONFLICT_MODES,
    )
    from ..protection import _is_protected, apply_isprotected_layer2
    from ..selection import (
        PickerState,
        PosGroupedAffixInventory,
        SourceAffixInventory,
        affix_label_runs,
        build_deps_inventory,
        build_entry_types_inventory,
        build_excluded_lossy_warnings,
        build_phonology_excluded_lossy,
        build_phonology_inventory,
        build_pos_grouped_inventory,
        build_rules_inventory,
        build_selection,
        build_skeleton_inventory,
        collapse_entry_types,
        collapse_phonology,
        collapse_pos_grouped,
        entry_types_missing_ref_warnings,
        mirror_check_state,
        phonology_uses_untraversed_rules,
    )
    from ..ws_fonts import WsFontRegistry, WsRole
    from .stats_panel import StatsPanel
    from .target_picker import TargetPickerDialog
    from .ws_font_delegate import attach_ws_font_delegate, set_ws_runs
    from .merge_preview_pane import MergePreviewPane, PreviewRequest, _action_to_mode
    from ..merge_preview import MergePreviewService, OVERWRITE, MERGE_KEEP, NEW
    from ..models import SimilarResolution
    from ..report import RunReport
else:
    import api as gt_api  # type: ignore
    from models import (  # type: ignore
        CategoryScope,
        ConflictMode,
        ExcludedLossy,
        GrammarCategory,
        RunMode,
        Selection,
        WSKind,
        WSMapping,
        WSMappingEntry,
        _DEFAULT_CONFLICT_MODES,
    )
    from protection import _is_protected, apply_isprotected_layer2  # type: ignore
    from selection import (  # type: ignore
        PickerState,
        PosGroupedAffixInventory,
        SourceAffixInventory,
        affix_label_runs,
        build_deps_inventory,
        build_entry_types_inventory,
        build_excluded_lossy_warnings,
        build_phonology_excluded_lossy,
        build_phonology_inventory,
        build_pos_grouped_inventory,
        build_rules_inventory,
        build_selection,
        build_skeleton_inventory,
        collapse_entry_types,
        collapse_phonology,
        collapse_pos_grouped,
        entry_types_missing_ref_warnings,
        mirror_check_state,
        phonology_uses_untraversed_rules,
    )
    from ws_fonts import WsFontRegistry, WsRole  # type: ignore
    from stats_panel import StatsPanel  # type: ignore
    from target_picker import TargetPickerDialog  # type: ignore
    from ws_font_delegate import attach_ws_font_delegate, set_ws_runs  # type: ignore
    from merge_preview_pane import MergePreviewPane, PreviewRequest, _action_to_mode  # type: ignore
    from merge_preview import MergePreviewService, OVERWRITE, MERGE_KEEP, NEW  # type: ignore
    from models import SimilarResolution  # type: ignore  (already imported above but needs bare-name alias)
    from report import RunReport  # type: ignore


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SCOPE_LABELS = {
    CategoryScope.NONE: "NONE",
    CategoryScope.AS_NEEDED: "AS-NEEDED (default)",
    CategoryScope.ALL: "ALL",
}

_CONFLICT_LABELS = {
    ConflictMode.ADD_NEW: "Add new (always create a copy)",
    ConflictMode.LINK: "Link (link existing by ID, else add; no field update)",
    ConflictMode.UPDATE: "Update (non-destructive: source wins on diverged fields; never blanks target)",
    ConflictMode.OVERWRITE: "Overwrite (replace target values with source)",
}

# Schema categories for the per-category scope selectors on page 3.
_SCHEMA_CATEGORIES = [
    GrammarCategory.POS,
    GrammarCategory.GRAM_CATEGORIES,
    GrammarCategory.INFLECTION_FEATURES,
    GrammarCategory.INFLECTION_CLASSES,
    GrammarCategory.STEM_NAMES,
    GrammarCategory.EXCEPTION_FEATURES,
    GrammarCategory.VARIANT_TYPES,
    GrammarCategory.COMPLEX_FORM_TYPES,
]

# Categories that are GOLD_RESERVED at Layer 1 (ADD_NEW hidden, OVERWRITE forbidden).
_GOLD_RESERVED = {
    GrammarCategory.GRAM_CATEGORIES,
    GrammarCategory.INFLECTION_FEATURES,
    GrammarCategory.VARIANT_TYPES,
    GrammarCategory.COMPLEX_FORM_TYPES,
    GrammarCategory.POS,
    GrammarCategory.PHONOLOGICAL_FEATURES,
    GrammarCategory.SEMANTIC_DOMAINS,
}

# CUSTOM_FIELDS: conservative (ADD hidden, OVERWRITE forbidden).
_CUSTOM_FIELDS_ONLY = {GrammarCategory.CUSTOM_FIELDS}

# All item category toggles (page 2 / 3).
_CATEGORY_TOGGLES = [
    GrammarCategory.POS,
    GrammarCategory.GRAM_CATEGORIES,
    GrammarCategory.INFLECTION_FEATURES,
    GrammarCategory.INFLECTION_CLASSES,
    GrammarCategory.STEM_NAMES,
    GrammarCategory.EXCEPTION_FEATURES,
    GrammarCategory.VARIANT_TYPES,
    GrammarCategory.COMPLEX_FORM_TYPES,
    GrammarCategory.ADHOC_COMPOUND_RULES,
    GrammarCategory.CUSTOM_FIELDS,
    GrammarCategory.AFFIXES,
    GrammarCategory.SLOTS,
    GrammarCategory.AFFIX_TEMPLATES,
]


# ---------------------------------------------------------------------------
# Layer-1 helper: which ConflictMode values are offered for a category?
# ---------------------------------------------------------------------------

def _allowed_modes(cat: GrammarCategory) -> list:
    """Return the list of ConflictMode values offered for `cat` per Layer 1."""
    if cat in _GOLD_RESERVED or cat in _CUSTOM_FIELDS_ONLY:
        # ADD_NEW hidden, OVERWRITE/UPDATE forbidden (GOLD safety rail, 022 T005)
        return [ConflictMode.LINK]
    # MULTI_INSTANCE or SINGLETON_NONDELETABLE that isn't GOLD -> all four modes
    return [ConflictMode.ADD_NEW, ConflictMode.LINK, ConflictMode.UPDATE, ConflictMode.OVERWRITE]


# ---------------------------------------------------------------------------
# Shared splitter helper (T004, FR-005, FR-011, R7)
# ---------------------------------------------------------------------------

def _make_tree_pane_splitter(tree_widget, pane_widget,
                             tree_stretch=3, pane_stretch=2):
    """Return a horizontal QSplitter with tree on the left and pane on the right.

    Replaces the direct layout.addWidget(tree, 1) call in each page's _build_ui.
    Stretch factors default to 3:2 (tree:pane) per plan R7.
    """
    splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
    splitter.addWidget(tree_widget)
    splitter.addWidget(pane_widget)
    splitter.setStretchFactor(0, tree_stretch)
    splitter.setStretchFactor(1, pane_stretch)
    return splitter


# ---------------------------------------------------------------------------
# Page 1 -- Project + Writing Systems
# ---------------------------------------------------------------------------

class _PageProjectWS(QtWidgets.QWizardPage):
    """Page 1: bind source + target projects and choose writing-system mapping.

    The source is already bound from the FlexTools host (passed in at wizard
    construction time).  The user picks the target here.

    WS decision: enumerate ACTIVE writing systems from the source project and
    present a three-way MAP / CREATE / SKIP control re-hosted from
    ws_mapping_dialog.py / ws_wizard.py mechanics.  Writing systems are split
    into two groups: Vernacular WS and Analysis WS (by WSKind).  A dual-role
    WS (appears in both groups) defaults both rows to the same choice and is
    independently overridable (linked-until-touched).  A dual-role CREATE
    choice points BOTH roles at the SAME target WS (no double-create).

    Vernacular is lead: when a vernacular row is set, the same-tag analysis
    row defaults to the vernacular choice and remains independently
    overridable.

    This is a PROJECT-LEVEL decision made once; no per-category WS negotiation.
    """

    # Choice constants (MAP=0, CREATE=1, SKIP=2) mirrored from WSChoice.
    _CHOICE_MAP = 0
    _CHOICE_CREATE = 1
    _CHOICE_SKIP = 2

    def __init__(self, stub, host_project, parent=None):
        super().__init__(parent)
        self._stub = stub
        self._host = host_project
        self._context = None   # set when target is bound
        self._target_ws_ids: list = []  # existing WS IDs in the target
        # Row state: dict keyed by (ws_id, kind_value) -> {"choice": int, "target": str}
        # kind_value is WSKind.VERNACULAR.value or WSKind.ANALYSIS.value
        self._row_state: dict = {}
        # Track which analysis rows are still "linked" to their vernacular twin.
        self._analysis_linked: set = set()  # set of ws_id strings

        self.setTitle("Step 1 of 9: Project + Writing Systems")
        self.setSubTitle(
            "Bind a target project and map source writing systems to target "
            "writing systems. Each WS can be Mapped, Created, or Skipped."
        )
        self._build_ui()
        self.registerField("target_ready*", self, "target_ready_prop",
                            self.target_ready_changed)

    # Qt property for the required-field completion gate.
    _target_ready = False
    target_ready_changed = QtCore.pyqtSignal()

    @QtCore.pyqtProperty(bool, notify=target_ready_changed)
    def target_ready_prop(self) -> bool:
        return self._target_ready

    def _set_target_ready(self, val: bool) -> None:
        if val != self._target_ready:
            self._target_ready = val
            self.target_ready_changed.emit()
            self.completeChanged.emit()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        src_row = QtWidgets.QHBoxLayout()
        src_row.addWidget(QtWidgets.QLabel("Source:", self))
        self._src_label = QtWidgets.QLabel(
            f"<b>{self._stub.source_project_name}</b> (open in FlexTools)", self
        )
        src_row.addWidget(self._src_label, 1)
        layout.addLayout(src_row)

        tgt_row = QtWidgets.QHBoxLayout()
        tgt_row.addWidget(QtWidgets.QLabel("Target:", self))
        self._tgt_label = QtWidgets.QLabel("<i>(not picked)</i>", self)
        tgt_row.addWidget(self._tgt_label, 1)
        pick_btn = QtWidgets.QPushButton("Pick target project...", self)
        pick_btn.clicked.connect(self._on_pick_target)
        tgt_row.addWidget(pick_btn)
        layout.addLayout(tgt_row)

        layout.addWidget(QtWidgets.QLabel(
            "Writing-system mapping (MAP / CREATE / SKIP per WS):", self
        ))

        # Scrollable area holding the two WS group tables (Vernacular, Analysis).
        scroll = QtWidgets.QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll_container = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_container)

        # -- Vernacular WS group --
        vern_group = QtWidgets.QGroupBox("Vernacular Writing Systems", scroll_container)
        self._vern_layout = QtWidgets.QVBoxLayout(vern_group)
        self._vern_table = self._make_ws_table(vern_group)
        self._vern_layout.addWidget(self._vern_table)
        scroll_layout.addWidget(vern_group)

        # -- Analysis WS group --
        anal_group = QtWidgets.QGroupBox("Analysis Writing Systems", scroll_container)
        self._anal_layout = QtWidgets.QVBoxLayout(anal_group)
        self._anal_table = self._make_ws_table(anal_group)
        self._anal_layout.addWidget(self._anal_table)
        scroll_layout.addWidget(anal_group)

        scroll.setWidget(scroll_container)
        layout.addWidget(scroll, 1)

        note = QtWidgets.QLabel(
            "[NOTE] Writing-system choice is made ONCE here, project-level.\n"
            "The per-category WS handshake from earlier phases is retired.\n"
            "Vernacular is lead: analysis rows with the same WS tag default to "
            "the vernacular choice and are independently overridable.",
            self,
        )
        note.setWordWrap(True)
        layout.addWidget(note)

    def _make_ws_table(self, parent) -> "QtWidgets.QTableWidget":
        """Create a QTableWidget with columns: Source WS | Choice | Target WS."""
        table = QtWidgets.QTableWidget(0, 3, parent)
        table.setHorizontalHeaderLabels(["Source WS", "Choice", "Target WS"])
        table.horizontalHeader().setStretchLastSection(True)
        return table

    # ------------------------------------------------------------------
    def _on_pick_target(self) -> None:
        candidates = gt_api.list_target_candidates(self._stub)
        if not candidates:
            QtWidgets.QMessageBox.warning(
                self,
                "GramTrans",
                "No candidate target projects found in the FieldWorks projects directory.",
            )
            return
        dlg = TargetPickerDialog(candidates, parent=self)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        choice = dlg.selected_candidate()
        if choice is None:
            return
        try:
            self._context = gt_api.bind_target(self._stub, choice)
        except gt_api.SameProjectError as e:
            QtWidgets.QMessageBox.critical(self, "GramTrans", str(e))
            return
        except gt_api.TargetUnavailable as e:
            QtWidgets.QMessageBox.critical(self, "GramTrans", str(e))
            return
        self._tgt_label.setText(
            f"<b>{choice.project_name}</b> (<code>{choice.project_path}</code>)"
        )
        # Enumerate target WS IDs for the MAP target dropdown.
        self._target_ws_ids = _enumerate_active_ws_ids(self._context.target_handle) \
            if hasattr(self._context, "target_handle") else []
        self._populate_ws_tables()
        self._set_target_ready(True)

    def _populate_ws_tables(self) -> None:
        """Enumerate ACTIVE writing systems from the source project and build rows.

        Writing systems are classified as VERNACULAR, ANALYSIS, or both (dual-role).
        Dual-role WS appears in both groups; the analysis row is linked to the
        vernacular choice until the user touches it independently.
        """
        vern_ids, anal_ids = _enumerate_ws_by_kind(self._host)
        dual_ids = set(vern_ids) & set(anal_ids)

        # Reset state.
        self._row_state.clear()
        self._analysis_linked = set(dual_ids)  # start linked for dual-role WSes

        self._fill_table(
            self._vern_table, vern_ids, kind_value=WSKind.VERNACULAR.value,
            is_vernacular=True,
        )
        self._fill_table(
            self._anal_table, anal_ids, kind_value=WSKind.ANALYSIS.value,
            is_vernacular=False,
        )

    def _fill_table(self, table, ws_ids: list, kind_value: str,
                    is_vernacular: bool) -> None:
        """Populate `table` with one row per ws_id."""
        table.setRowCount(0)
        for ws_id in ws_ids:
            row = table.rowCount()
            table.insertRow(row)

            # Col 0: source WS label (read-only)
            src_item = QtWidgets.QTableWidgetItem(ws_id)
            src_item.setFlags(src_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 0, src_item)

            # Col 1: choice combo (MAP / CREATE / SKIP)
            choice_cb = QtWidgets.QComboBox(table)
            choice_cb.addItem("MAP to existing target WS", self._CHOICE_MAP)
            choice_cb.addItem("CREATE new target WS", self._CHOICE_CREATE)
            choice_cb.addItem("SKIP (drop objects using this WS)", self._CHOICE_SKIP)
            # Pre-select MAP if a same-tag target WS exists.
            if ws_id in self._target_ws_ids:
                choice_cb.setCurrentIndex(self._CHOICE_MAP)
            else:
                choice_cb.setCurrentIndex(self._CHOICE_CREATE)
            table.setCellWidget(row, 1, choice_cb)

            # Col 2: target WS combo (editable; used for MAP).
            tgt_cb = QtWidgets.QComboBox(table)
            tgt_cb.setEditable(True)
            tgt_cb.addItem("")
            for t in self._target_ws_ids:
                tgt_cb.addItem(t)
            # Pre-populate with same-tag if available.
            if ws_id in self._target_ws_ids:
                tgt_cb.setCurrentText(ws_id)
            else:
                tgt_cb.setCurrentText(ws_id)  # CREATE: use source tag as proposed name
            table.setCellWidget(row, 2, tgt_cb)

            # Initialize row state.
            key = (ws_id, kind_value)
            self._row_state[key] = {
                "choice": choice_cb.currentIndex(),
                "target": tgt_cb.currentText(),
            }

            # Wire change signals to state updater.
            choice_cb.currentIndexChanged.connect(
                lambda idx, k=key, is_v=is_vernacular, wid=ws_id:
                self._on_choice_changed(k, idx, is_v, wid)
            )
            tgt_cb.currentTextChanged.connect(
                lambda text, k=key, is_v=is_vernacular, wid=ws_id:
                self._on_target_changed(k, text, is_v, wid)
            )

    def _on_choice_changed(self, key, idx: int, is_vernacular: bool, ws_id: str) -> None:
        """Update row state; propagate to linked analysis row if vernacular lead."""
        self._row_state[key] = dict(self._row_state.get(key, {}), choice=idx)
        if is_vernacular:
            # Seed the linked analysis row if it hasn't been independently touched.
            anal_key = (ws_id, WSKind.ANALYSIS.value)
            if anal_key in self._row_state and ws_id in self._analysis_linked:
                self._row_state[anal_key] = dict(
                    self._row_state[anal_key], choice=idx
                )
                self._sync_analysis_row_widget(ws_id, idx)

    def _on_target_changed(self, key, text: str, is_vernacular: bool, ws_id: str) -> None:
        """Update row state; break link when analysis row is independently changed."""
        self._row_state[key] = dict(self._row_state.get(key, {}), target=text)
        if not is_vernacular:
            # User explicitly changed analysis row: break the link.
            self._analysis_linked.discard(ws_id)
        if is_vernacular:
            # Propagate to linked analysis row.
            anal_key = (ws_id, WSKind.ANALYSIS.value)
            if anal_key in self._row_state and ws_id in self._analysis_linked:
                self._row_state[anal_key] = dict(
                    self._row_state[anal_key], target=text
                )

    def _sync_analysis_row_widget(self, ws_id: str, choice_idx: int) -> None:
        """Sync the analysis table widget for ws_id to choice_idx (linked update)."""
        vern_ids, anal_ids = _enumerate_ws_by_kind(self._host)
        if ws_id not in anal_ids:
            return
        row_idx = anal_ids.index(ws_id)
        if row_idx >= self._anal_table.rowCount():
            return
        choice_cb = self._anal_table.cellWidget(row_idx, 1)
        if choice_cb is not None and hasattr(choice_cb, "setCurrentIndex"):
            # Block signal to avoid recursive propagation.
            try:
                choice_cb.blockSignals(True)
                choice_cb.setCurrentIndex(choice_idx)
            finally:
                choice_cb.blockSignals(False)

    # ------------------------------------------------------------------
    def context(self):
        return self._context

    def selected_ws_ids(self) -> list:
        """Return the list of source WS IDs that are not SKIP.

        When the WS table has been populated (_row_state is set), derive the
        list from the three-way control state.  Falls back to reading
        _ws_list (the legacy QListWidget) if _row_state is unavailable,
        for backward compatibility with existing test doubles that inject
        a bare _ws_list mock.
        """
        row_state = getattr(self, "_row_state", None)
        if row_state is not None:
            result = []
            seen = set()
            for (ws_id, _kind), state in row_state.items():
                if ws_id not in seen and state.get("choice") != self._CHOICE_SKIP:
                    result.append(ws_id)
                    seen.add(ws_id)
            return result
        # Legacy fallback (used by test_wizard_page_flow.py and old callers).
        ws_list = getattr(self, "_ws_list", None)
        if ws_list is None:
            return []
        return [
            ws_list.item(i).text()
            for i in range(ws_list.count())
            if ws_list.item(i).isSelected()
        ]

    def ws_mapping(self) -> "WSMapping":
        """Build a WSMapping from the current page state.

        MAP rows:    source_ws_id -> target_ws_id (create_in_target=False)
        CREATE rows: source_ws_id -> source_ws_id (create_in_target=True)
        SKIP rows:   omitted from the mapping.

        Dual-role CREATE: both VERNACULAR and ANALYSIS entries point at the SAME
        target WS (no double-create), identified by the source tag.
        """
        entries = []
        seen_creates: dict = {}  # ws_id -> target_ws_id for CREATE rows
        for (ws_id, kind_value), state in self._row_state.items():
            choice = state.get("choice", self._CHOICE_SKIP)
            target_text = (state.get("target") or ws_id).strip()
            kind = WSKind(kind_value)
            if choice == self._CHOICE_SKIP:
                continue
            if choice == self._CHOICE_CREATE:
                # Dual-role: reuse the same target tag as the vernacular twin.
                create_target = seen_creates.get(ws_id, target_text)
                seen_creates[ws_id] = create_target
                entries.append(WSMappingEntry(
                    source_ws_id=ws_id,
                    source_ws_kind=kind,
                    target_ws_id=create_target,
                    create_in_target=True,
                ))
            else:  # MAP
                entries.append(WSMappingEntry(
                    source_ws_id=ws_id,
                    source_ws_kind=kind,
                    target_ws_id=target_text or ws_id,
                    create_in_target=False,
                ))
        return WSMapping(entries=tuple(entries))

    def isComplete(self) -> bool:
        return self._target_ready


# ---------------------------------------------------------------------------
# Item-data roles used throughout _PageItemPicker
# ---------------------------------------------------------------------------

_GUID_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1   # entry_guid string
_KIND_ROLE = QtCore.Qt.ItemDataRole.UserRole + 2   # "affix" | "pos_group" | "subgroup"
_ROLE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 3   # "attaches" | "produces" (leaf rows)
_IS_PRODUCES = QtCore.Qt.ItemDataRole.UserRole + 4  # bool: True for deriv_produces rows
# T005 -- Data roles for _PageItemPicker (FR-010, R6)
_ITEM_STATUS_ROLE = QtCore.Qt.ItemDataRole.UserRole + 30  # "new" | "in_target" | "similar"
_ITEM_CAT_ROLE    = QtCore.Qt.ItemDataRole.UserRole + 31  # GrammarCategory


# ---------------------------------------------------------------------------
# Page 2 -- Item picker (POS-grouped, specs/008-affix-pos-picker)
# ---------------------------------------------------------------------------

def _count_affixes_in_node(pos_node) -> int:
    """Return the count of distinct affix entry_guids in pos_node's whole subtree.

    Counts guids in inflectional + deriv_attaches + deriv_produces at this
    node and recursively in all children.  Deduplicates across sub-lists so
    an entry appearing in multiple subgroups of the same node is counted once.
    Used by FR-017(b) to annotate POS group header labels.
    """
    guids: Set[str] = set()

    def _collect(node) -> None:
        for row in node.inflectional:
            guids.add(row.entry_guid)
        for row in node.deriv_attaches:
            guids.add(row.entry_guid)
        for row in node.deriv_produces:
            guids.add(row.entry_guid)
        for child in node.children:
            _collect(child)

    _collect(pos_node)
    return len(guids)


class _PageItemPicker(QtWidgets.QWizardPage):
    """Page 2: POS-grouped affix item picker.

    Tree layout (5 columns):
        Col 0: Affix form -> glosses  |  Col 1: Type  |  Col 2: From  |
        Col 3: To  |  Col 4: Target

    POS hierarchy:
        [POS node]
          [Inflectional]   <- swept by POS header-check
            affix rows...
          [Derivation - attaches to]  <- swept by POS header-check
            affix rows...
          [Derivation - produces]  <- NOT swept by POS header-check
            affix rows...
        [Unattached affixes]
          [No part of speech]
            affix rows...
          [No sense / no analysis]
            affix rows...

    Stems tab is STUBBED / DISABLED (Layer-3 stems land later).

    Group-check semantics:
        Checking a POS node sweeps Inflectional + Derivation-attaches subgroups
        and descendant POS nodes, but NOT the Derivation-produces subgroup.
        This is achieved by marking produces rows with _IS_PRODUCES=True so that
        the Qt auto-tristate propagation covers the entire subtree; the header
        check logic in collect_selection filters them out by role.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Step 4 of 9: Item Picker")
        self.setSubTitle(
            "Select the affixes to transfer, grouped by the part of speech they attach to. "
            "Stems are not yet supported (coming in a later phase)."
        )
        self._inventory: Optional[PosGroupedAffixInventory] = None
        # Map from entry_guid -> list of QTreeWidgetItem (for mirroring)
        self._guid_to_items: dict = {}
        # Re-entrancy guard for itemChanged mirroring
        self._mirroring: bool = False
        # T009/T010: per-page resolution store (FR-008, R3)
        self._resolution_store: dict = {}
        self._preview_service = None
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        # Tab widget: Affixes (active) + Stems (disabled stub)
        self._tabs = QtWidgets.QTabWidget(self)

        # --- Affixes tab (POS-grouped tree) ---
        affix_tab = QtWidgets.QWidget()
        affix_tab_layout = QtWidgets.QVBoxLayout(affix_tab)
        # FR-017(a): instruction label making clear the pick unit is affixes
        affix_tab_layout.addWidget(QtWidgets.QLabel(
            "Select the affixes to transfer. "
            "Parts of speech below are groupings only -- "
            "checking one selects the affixes under it.",
            affix_tab,
        ))
        self._tree = QtWidgets.QTreeWidget(affix_tab)
        # FR-017(d): 5 columns; col 4 = Target presence
        self._tree.setColumnCount(5)
        self._tree.setHeaderLabels(["Affix / Group", "Type", "From", "To", "Target"])
        self._tree.header().setStretchLastSection(False)
        self._tree.setAlternatingRowColors(True)
        # T009: merge-preview pane docked to the right via a horizontal splitter (FR-005)
        self._pane = MergePreviewPane(affix_tab)
        splitter = _make_tree_pane_splitter(self._tree, self._pane)
        affix_tab_layout.addWidget(splitter, 1)
        self._tabs.addTab(affix_tab, "Affixes")

        # --- Stems tab (019: enabled, POS-grouped stem tree) ---
        stems_tab = QtWidgets.QWidget()
        stems_layout = QtWidgets.QVBoxLayout(stems_tab)
        stems_layout.addWidget(QtWidgets.QLabel(
            "Select the stem entries to transfer, grouped by part of speech. "
            "Checking a part of speech selects the stems under it.",
            stems_tab,
        ))
        self._stem_tree = QtWidgets.QTreeWidget(stems_tab)
        self._stem_tree.setColumnCount(5)
        self._stem_tree.setHeaderLabels(
            ["Stem / Group", "Type", "From", "To", "Target"]
        )
        self._stem_tree.header().setStretchLastSection(False)
        self._stem_tree.setAlternatingRowColors(True)
        stems_layout.addWidget(self._stem_tree, 1)
        self._tabs.addTab(stems_tab, "Stems")
        # Stem inventory + per-guid item registry (mirrors the affix tree).
        self._stem_inventory: Optional[PosGroupedAffixInventory] = None
        self._stem_guid_to_items: dict = {}

        layout.addWidget(self._tabs, 1)

    # ------------------------------------------------------------------
    def initializePage(self) -> None:
        """Called when the wizard enters page 2.

        Builds the inventory from the bound source project and populates
        the tree. This is the missing feed that caused the empty picker.
        Guards for no-source (renders empty labeled tree, no crash).
        """
        self._tree.itemChanged.disconnect() if self._tree.receivers(
            self._tree.itemChanged
        ) > 0 else None

        source = self._get_source()
        if source is None:
            # No source bound yet -- show empty labeled tree, no crash
            self._inventory = None
            self._guid_to_items = {}
            self._tree.clear()
            empty_item = QtWidgets.QTreeWidgetItem(
                self._tree, ["(No source project bound)"]
            )
            empty_item.setFlags(empty_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled)
            # 019: clear the stem tab too (no crash when unbound).
            self._stem_inventory = None
            self._stem_guid_to_items = {}
            self._stem_tree.clear()
            return

        # FR-018(e): obtain target handle from page-0 context; guard for no-target
        target = self._get_target()

        try:
            inventory = build_pos_grouped_inventory(source, target=target)
        except Exception:  # noqa: BLE001
            inventory = None  # type: ignore[assignment]

        if inventory is None:
            self._inventory = None
            self._guid_to_items = {}
            return

        self._inventory = inventory
        self._guid_to_items = {}
        # spec 011: vernacular lexeme forms (col 0) + analysis glosses/POS
        # (cols 0/2/3) each in their FLEx-defined WS font.
        attach_ws_font_delegate(
            self._tree, [0, 2, 3], WsFontRegistry.from_project(source)
        )
        self.populate_pos_tree(inventory)
        self._tree.itemChanged.connect(self._on_item_changed)

        # T009/T010: resolution store seeding (FR-008, R3)
        self._resolution_store = {}
        for entry_guid, suggested_target_guid in self._similar_affix_pairs():
            self._resolution_store[entry_guid] = SimilarResolution(
                entry_guid=entry_guid,
                action="overwrite",
                target_guid=suggested_target_guid,
            )
        # Reflect default seed in Target column
        for entry_guid, resolution in self._resolution_store.items():
            self._update_target_column(entry_guid, resolution)

        # T009: construct service and set pane context (FR-006)
        self._preview_service = MergePreviewService(source, target)
        candidates = self._candidate_list()
        self._pane.set_context(
            self._preview_service,
            WsFontRegistry.from_project(source),
            candidates,
        )
        self._pane.clear()
        # Connect tree selection handler (with double-connect guard)
        if self._tree.receivers(self._tree.currentItemChanged) == 0:
            self._tree.currentItemChanged.connect(self._on_tree_selection_changed)
        # Connect pane resolution_changed signal (T009)
        self._pane.resolution_changed.connect(self._on_resolution_changed)

        # --- 019: build + populate the Stems tab (want_affix=False) ---
        try:
            stem_inventory = build_pos_grouped_inventory(
                source, target=target, want_affix=False
            )
        except Exception:  # noqa: BLE001
            stem_inventory = None  # type: ignore[assignment]
        self._stem_inventory = stem_inventory
        attach_ws_font_delegate(
            self._stem_tree, [0, 2, 3], WsFontRegistry.from_project(source)
        )
        if stem_inventory is not None:
            self.populate_stem_tree(stem_inventory)

    # T009/T010: helper methods
    def _candidate_list(self):
        """Return list of (guid, form, gloss) for SIMILAR affix candidates."""
        # All SIMILAR rows' suggested targets become candidates for the combo
        candidates = []
        seen = set()
        root = self._tree.invisibleRootItem()

        def _walk(node):
            for i in range(node.childCount()):
                child = node.child(i)
                status = child.data(0, _ITEM_STATUS_ROLE)
                if status == "similar":
                    # The suggested target guid is in the resolution store
                    # (seeded from inventory row). Gather from inventory.
                    pass
                _walk(child)

        # Build candidates from inventory rows that have similar matches
        if self._inventory is not None:
            def _collect_similar_rows(node):
                for row in node.inflectional + node.deriv_attaches + node.deriv_produces:
                    if getattr(row, "status", None) == "similar":
                        tg = getattr(row, "suggested_target_guid", None) or ""
                        if tg and tg not in seen:
                            seen.add(tg)
                            form = getattr(row, "target_form", "") or tg[:8]
                            gloss = getattr(row, "target_gloss", "") or ""
                            candidates.append((tg, form, gloss))
                for child in node.children:
                    _collect_similar_rows(child)

            for root_node in self._inventory.roots:
                _collect_similar_rows(root_node)
        return candidates

    def _similar_affix_pairs(self):
        """Return list of (source_guid, suggested_target_guid) for SIMILAR affix rows."""
        pairs = []
        root = self._tree.invisibleRootItem()

        def _walk(node):
            for i in range(node.childCount()):
                child = node.child(i)
                status = child.data(0, _ITEM_STATUS_ROLE)
                if status == "similar":
                    source_guid = child.data(0, _GUID_ROLE)
                    # Look up suggested target from inventory row
                    # The row.suggested_target_guid is set by build_pos_grouped_inventory
                    suggested_tg = self._find_suggested_target(source_guid)
                    if source_guid and suggested_tg:
                        pairs.append((source_guid, suggested_tg))
                _walk(child)

        _walk(self._tree.invisibleRootItem())
        return pairs

    def _find_suggested_target(self, entry_guid: str) -> str:
        """Look up the suggested target GUID for a SIMILAR affix from the inventory."""
        if self._inventory is None:
            return ""

        def _search_rows(rows):
            for row in rows:
                if row.entry_guid == entry_guid:
                    return getattr(row, "suggested_target_guid", "") or ""
            return ""

        def _search_node(node):
            result = _search_rows(node.inflectional)
            if result:
                return result
            result = _search_rows(node.deriv_attaches)
            if result:
                return result
            result = _search_rows(node.deriv_produces)
            if result:
                return result
            for child in node.children:
                result = _search_node(child)
                if result:
                    return result
            return ""

        for root_node in self._inventory.roots:
            result = _search_node(root_node)
            if result:
                return result
        # Also check junk
        if self._inventory.junk:
            for row in (list(getattr(self._inventory.junk, "no_pos", []))
                        + list(getattr(self._inventory.junk, "no_analysis", []))):
                if row.entry_guid == entry_guid:
                    return getattr(row, "suggested_target_guid", "") or ""
        return ""

    def _on_tree_selection_changed(self, current, previous) -> None:
        """T009: build PreviewRequest from selected row and call pane.show_item."""
        if current is None:
            self._pane.clear()
            return
        kind = current.data(0, _KIND_ROLE)
        if kind != "affix":
            # Group or subgroup header -> clear pane
            self._pane.clear()
            return

        source_guid = current.data(0, _GUID_ROLE) or ""
        category = current.data(0, _ITEM_CAT_ROLE)
        status = current.data(0, _ITEM_STATUS_ROLE) or ""

        # Derive target_guid and mode per status (R1)
        if status == "new":
            target_guid = ""
            mode = NEW
        elif status == "in_target":
            target_guid = source_guid
            mode = OVERWRITE
        elif status == "similar":
            resolution = self._resolution_store.get(source_guid)
            if resolution is not None:
                target_guid = resolution.target_guid or ""
                mode = _action_to_mode(resolution.action)
            else:
                target_guid = ""
                mode = NEW
        else:
            self._pane.clear()
            return

        # resolvable if status=="similar" (store entry implies candidate was found)
        resolvable = status == "similar"

        current_resolution = self._resolution_store.get(source_guid)
        cat_str = category.value if category is not None else GrammarCategory.AFFIXES.value

        request = PreviewRequest(
            category=cat_str,
            source_guid=source_guid,
            target_guid=target_guid,
            status=status,
            mode=mode,
            resolvable=resolvable,
            current_resolution=current_resolution,
            owner_guid="",
        )
        self._pane.show_item(request)

    def _on_resolution_changed(self, entry_guid: str, resolution) -> None:
        """T010: update the resolution store and reflect in Target column."""
        self._resolution_store[entry_guid] = resolution
        self._update_target_column(entry_guid, resolution)

    def _update_target_column(self, entry_guid: str, resolution) -> None:
        """T010: set Target column text for the given entry_guid's tree items."""
        _ACTION_LABELS = {
            "overwrite": "SIMILAR -> overwrite",
            "merge": "SIMILAR -> merge",
            "create_new": "SIMILAR -> new",
        }
        label = _ACTION_LABELS.get(getattr(resolution, "action", ""), "")
        for item in self._guid_to_items.get(entry_guid, []):
            item.setText(4, label)

    def _get_source(self):
        """Return the source project handle from page 0, or None."""
        try:
            wizard = self.wizard()
            if wizard is None:
                return None
            page0 = wizard.page_project_ws()
            if page0 is None:
                return None
            # Try context().source_handle first, then _host directly
            ctx = page0.context()
            if ctx is not None:
                h = getattr(ctx, "source_handle", None)
                if h is not None:
                    return h
            host = getattr(page0, "_host", None)
            return host
        except Exception:  # noqa: BLE001
            return None

    def _get_target(self):
        """Return the target project handle from page-0 context, or None.

        FR-018(e): the RunContext (set when user picks a target on page 1)
        exposes .target_handle.  If no context or no target yet, returns None
        so the builder is called with target=None (Target column blank, no crash).
        """
        try:
            wizard = self.wizard()
            if wizard is None:
                return None
            page0 = wizard.page_project_ws()
            if page0 is None:
                return None
            ctx = page0.context()
            if ctx is None:
                return None
            return getattr(ctx, "target_handle", None)
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------------
    def populate_pos_tree(self, inventory: PosGroupedAffixInventory) -> None:
        """Populate the 4-column POS-hierarchy tree from inventory.

        Called by initializePage; may also be called directly in tests.
        """
        self._tree.clear()
        self._guid_to_items = {}

        # --- POS hierarchy nodes ---
        for pos_node in inventory.roots:
            self._add_pos_node(self._tree.invisibleRootItem(), pos_node)

        # --- Unattached drawer ---
        has_junk = bool(inventory.junk.no_pos or inventory.junk.no_analysis)
        if has_junk:
            drawer = self._make_group_item(
                self._tree, "Unattached affixes",
                kind="pos_group", checkable=True, is_produces_group=False,
            )
            if inventory.junk.no_pos:
                sg = self._make_group_item(
                    drawer, "No part of speech",
                    kind="subgroup", checkable=True, is_produces_group=False,
                )
                for row in inventory.junk.no_pos:
                    self._add_affix_row(sg, row)
            if inventory.junk.no_analysis:
                sg2 = self._make_group_item(
                    drawer, "No sense / no analysis",
                    kind="subgroup", checkable=True, is_produces_group=False,
                )
                for row in inventory.junk.no_analysis:
                    self._add_affix_row(sg2, row)

        self._tree.expandAll()
        # Resize columns to content after population (5 columns now)
        for col in range(5):
            self._tree.resizeColumnToContents(col)

    def _add_pos_node(self, parent, pos_node) -> None:
        """Recursively add a PosNode and its subgroups/children to the tree."""
        # FR-017(b): annotate POS group label with distinct affix count
        affix_count = _count_affixes_in_node(pos_node)
        affix_word = "affix" if affix_count == 1 else "affixes"
        pos_label = f"{pos_node.label} -- {affix_count} {affix_word}"
        pos_item = self._make_group_item(
            parent, pos_label,
            kind="pos_group", checkable=True, is_produces_group=False,
        )
        pos_item.setData(0, _GUID_ROLE, pos_node.pos_guid)
        # spec 011: POS name in the analysis WS font; affix-count suffix is chrome.
        set_ws_runs(pos_item, 0, (
            (pos_node.label, WsRole.ANALYSIS),
            (f" -- {affix_count} {affix_word}", None),
        ))

        # Inflectional subgroup
        if pos_node.inflectional:
            sg_infl = self._make_group_item(
                pos_item, "Inflectional",
                kind="subgroup", checkable=True, is_produces_group=False,
            )
            for row in pos_node.inflectional:
                self._add_affix_row(sg_infl, row)

        # Derivation - attaches to subgroup
        if pos_node.deriv_attaches:
            sg_att = self._make_group_item(
                pos_item, "Derivation - attaches to",
                kind="subgroup", checkable=True, is_produces_group=False,
            )
            for row in pos_node.deriv_attaches:
                self._add_affix_row(sg_att, row)

        # Derivation - produces subgroup (NOT swept by header check)
        if pos_node.deriv_produces:
            sg_prod = self._make_group_item(
                pos_item, "Derivation - produces",
                kind="subgroup", checkable=True, is_produces_group=True,
            )
            for row in pos_node.deriv_produces:
                self._add_affix_row(sg_prod, row)

        # Descendant POS nodes
        for child in pos_node.children:
            self._add_pos_node(pos_item, child)

    def _make_group_item(self, parent, label: str, *,
                         kind: str, checkable: bool,
                         is_produces_group: bool) -> QtWidgets.QTreeWidgetItem:
        """Create a group/header tree item.

        FR-017(c): header rows (pos_group and subgroup) are styled with bold
        font so they are visually distinct from affix leaf rows.
        """
        # 5 columns: label, type, from, to, target (blank for headers)
        if isinstance(parent, QtWidgets.QTreeWidget):
            item = QtWidgets.QTreeWidgetItem(parent, [label, "", "", "", ""])
        else:
            item = QtWidgets.QTreeWidgetItem(parent, [label, "", "", "", ""])
        item.setData(0, _KIND_ROLE, kind)
        item.setData(0, _IS_PRODUCES, is_produces_group)
        if checkable:
            item.setFlags(
                item.flags()
                | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                | QtCore.Qt.ItemFlag.ItemIsAutoTristate
            )
            item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        # FR-017(c): bold font for all header/group rows
        from PyQt6 import QtGui
        bold_font = item.font(0)
        bold_font.setBold(True)
        item.setFont(0, bold_font)
        return item

    def _add_affix_row(self, parent: QtWidgets.QTreeWidgetItem,
                       row) -> None:
        """Add a leaf AffixRow item to the tree under parent."""
        # spec 011: form is vernacular, gloss is analysis -- split into WS runs.
        label_runs = affix_label_runs(row.form, row.glosses)
        label = "".join(text for text, _ in label_runs)
        type_label = {"infl": "Infl", "deriv": "Deriv", "uncl": "Uncl"}.get(
            row.msa_kind, row.msa_kind
        )
        from_label = row.from_pos if row.from_pos else ("—" if row.role == "produces" else "")
        to_label = row.to_pos if row.to_pos else ("—" if row.msa_kind == "deriv" else "")
        # FR-017(d): Target column -- "NEW" / "IN TARGET" / "SIMILAR" / ""
        _status_labels = {
            "new": "NEW",
            "in_target": "IN TARGET",
            "similar": "SIMILAR",
        }
        target_label = _status_labels.get(row.status or "", "")

        item = QtWidgets.QTreeWidgetItem(
            parent, [label, type_label, from_label, to_label, target_label]
        )
        # spec 011: per-WS fonts -- form+gloss on col 0, POS names on cols 2/3.
        set_ws_runs(item, 0, label_runs)
        if from_label and from_label != "—":
            set_ws_runs(item, 2, ((from_label, WsRole.ANALYSIS),))
        if to_label and to_label != "—":
            set_ws_runs(item, 3, ((to_label, WsRole.ANALYSIS),))
        item.setData(0, _GUID_ROLE, row.entry_guid)
        item.setData(0, _KIND_ROLE, "affix")
        item.setData(0, _ROLE_ROLE, row.role)
        item.setData(0, _IS_PRODUCES, row.role == "produces")
        # T005: data roles for pane PreviewRequest construction (FR-010, R6)
        item.setData(0, _ITEM_STATUS_ROLE, row.status or "")
        item.setData(0, _ITEM_CAT_ROLE, GrammarCategory.AFFIXES)
        item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
        # FR-001 (T009): affixes open fully preselected; deselection is the
        # primary user action (opens checked, not unchecked).
        item.setCheckState(0, QtCore.Qt.CheckState.Checked)

        # Register for GUID mirroring
        guid = row.entry_guid
        if guid not in self._guid_to_items:
            self._guid_to_items[guid] = []
        self._guid_to_items[guid].append(item)

    # ------------------------------------------------------------------
    def _on_item_changed(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        """Mirror check state to all other appearances of the same entry GUID."""
        if self._mirroring:
            return
        if column != 0:
            return
        guid = item.data(0, _GUID_ROLE)
        kind = item.data(0, _KIND_ROLE)
        if kind != "affix" or guid is None:
            return
        new_state = item.checkState(0)
        siblings = self._guid_to_items.get(guid, [])
        if len(siblings) <= 1:
            return
        assignments = mirror_check_state(siblings, new_state)
        self._mirroring = True
        try:
            for sibling, state in assignments:
                if sibling is not item:
                    sibling.setCheckState(0, state)
        finally:
            self._mirroring = False

    # ------------------------------------------------------------------
    def picker_state(self) -> PickerState:
        """Collect checked leaf entry_guids from the tree."""
        checked: set = set()
        self._collect_checked(self._tree.invisibleRootItem(), checked)
        return PickerState(checked_affixes=frozenset(checked))

    def _collect_checked(self, node: QtWidgets.QTreeWidgetItem, out: set) -> None:
        """Recursively collect checked affix entry_guids.

        Produces-role rows (_IS_PRODUCES=True) are excluded from header-driven
        collection (FR-008): a POS-header check must not pull produces-only GUIDs
        into affix_picks.  Only attaches-role leaf rows contribute.
        """
        for i in range(node.childCount()):
            child = node.child(i)
            kind = child.data(0, _KIND_ROLE)
            if kind == "affix":
                # Skip produces-role rows; they MUST NOT be swept by header check
                is_produces = child.data(0, _IS_PRODUCES)
                if is_produces:
                    continue
                if child.checkState(0) == QtCore.Qt.CheckState.Checked:
                    guid = child.data(0, _GUID_ROLE)
                    if guid:
                        out.add(guid)
            else:
                self._collect_checked(child, out)

    # ------------------------------------------------------------------
    # 019: Stems tab population + pick collection
    # ------------------------------------------------------------------
    def populate_stem_tree(self, inventory: PosGroupedAffixInventory) -> None:
        """Populate the POS-grouped Stems tree from the stem inventory.

        Mirrors ``populate_pos_tree`` but for stems: rows carry
        ``GrammarCategory.STEMS`` and open preselected (checked). Called by
        initializePage; may also be called directly in tests.
        """
        self._stem_tree.clear()
        self._stem_guid_to_items = {}
        for pos_node in inventory.roots:
            self._add_stem_pos_node(self._stem_tree.invisibleRootItem(), pos_node)
        has_junk = bool(inventory.junk.no_pos or inventory.junk.no_analysis)
        if has_junk:
            drawer = self._make_group_item(
                self._stem_tree, "Unattached stems",
                kind="pos_group", checkable=True, is_produces_group=False,
            )
            for label, rows in (
                ("No part of speech", inventory.junk.no_pos),
                ("No sense / no analysis", inventory.junk.no_analysis),
            ):
                if rows:
                    sg = self._make_group_item(
                        drawer, label,
                        kind="subgroup", checkable=True, is_produces_group=False,
                    )
                    for row in rows:
                        self._add_stem_row(sg, row)
        self._stem_tree.expandAll()
        for col in range(5):
            self._stem_tree.resizeColumnToContents(col)

    def _add_stem_pos_node(self, parent, pos_node) -> None:
        """Recursively add a stem POS group and its stem rows + child POSes."""
        stem_count = _count_affixes_in_node(pos_node)
        word = "stem" if stem_count == 1 else "stems"
        label = f"{pos_node.label} -- {stem_count} {word}"
        pos_item = self._make_group_item(
            parent, label,
            kind="pos_group", checkable=True, is_produces_group=False,
        )
        pos_item.setData(0, _GUID_ROLE, pos_node.pos_guid)
        set_ws_runs(pos_item, 0, (
            (pos_node.label, WsRole.ANALYSIS),
            (f" -- {stem_count} {word}", None),
        ))
        # Stems land in the inflectional (attaches) bucket of the shared row shape.
        for row in pos_node.inflectional:
            self._add_stem_row(pos_item, row)
        for child in pos_node.children:
            self._add_stem_pos_node(pos_item, child)

    def _add_stem_row(self, parent: QtWidgets.QTreeWidgetItem, row) -> None:
        """Add a leaf stem row; renders the NEW / IN TARGET / SIMILAR column."""
        label_runs = affix_label_runs(row.form, row.glosses)
        label = "".join(text for text, _ in label_runs)
        _status_labels = {"new": "NEW", "in_target": "IN TARGET", "similar": "SIMILAR"}
        target_label = _status_labels.get(row.status or "", "")
        item = QtWidgets.QTreeWidgetItem(
            parent, [label, "Stem", "", "", target_label]
        )
        set_ws_runs(item, 0, label_runs)
        item.setData(0, _GUID_ROLE, row.entry_guid)
        item.setData(0, _KIND_ROLE, "stem")
        item.setData(0, _IS_PRODUCES, False)
        item.setData(0, _ITEM_STATUS_ROLE, row.status or "")
        item.setData(0, _ITEM_CAT_ROLE, GrammarCategory.STEMS)
        item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
        # Open preselected (mirror the affix picker default; deselect is primary).
        item.setCheckState(0, QtCore.Qt.CheckState.Checked)
        self._stem_guid_to_items.setdefault(row.entry_guid, []).append(item)

    def _collect_checked_stems(self, node: QtWidgets.QTreeWidgetItem,
                               out: set) -> None:
        """Recursively collect checked stem entry_guids from the Stems tree."""
        for i in range(node.childCount()):
            child = node.child(i)
            if child.data(0, _KIND_ROLE) == "stem":
                if child.checkState(0) == QtCore.Qt.CheckState.Checked:
                    guid = child.data(0, _GUID_ROLE)
                    if guid:
                        out.add(guid)
            else:
                self._collect_checked_stems(child, out)

    def _stem_picks(self) -> frozenset:
        """Checked stem GUIDs intersected with the known stem inventory."""
        if self._stem_inventory is None:
            return frozenset()
        checked: set = set()
        self._collect_checked_stems(self._stem_tree.invisibleRootItem(), checked)
        return frozenset(checked) & self._stem_inventory.all_affix_guids()

    def collect_selection(self) -> Selection:
        """Build a Selection from the current picker state (T011, FR-009).

        Folds the page's resolution store into the returned Selection via
        dataclasses.replace.  Returns a shallow copy of the store so callers
        cannot mutate the live store.
        """
        if self._inventory is None:
            dummy = SourceAffixInventory()
            base = build_selection(PickerState(), dummy)
            # Empty similar_resolutions (dataclass default) on fallback path
            return base
        ps = self.picker_state()
        base = collapse_pos_grouped(ps.checked_affixes, self._inventory)
        # 019: fold stem picks in. Non-empty stem_picks requires categories[STEMS].
        stem_picks = self._stem_picks()
        categories = dict(base.categories)
        if stem_picks:
            categories[GrammarCategory.STEMS] = True
        return dataclasses.replace(
            base,
            categories=categories,
            stem_picks=stem_picks,
            similar_resolutions=dict(self._resolution_store),
        )


# ---------------------------------------------------------------------------
# Page 3 -- Schema scope + conflict mode
# ---------------------------------------------------------------------------

class _PageScopeConflict(QtWidgets.QWizardPage):
    """Page 3: per-category three-scope selector + conflict mode.

    Re-hosts the existing scope-combo controls from main_window and adds
    per-category ConflictMode selectors gated by the Layer-1 kind table.

    The LINK control carries an explicit label ("link existing by ID, else
    add; no field update") per spec section (i) (022: renamed from MERGE).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Step 3 of 5: Schema Scope + Conflict Mode")
        self.setSubTitle(
            "For each schema category, choose how much to transfer (NONE / AS-NEEDED / ALL) "
            "and what to do when a source item already exists in the target."
        )
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QtWidgets.QVBoxLayout(self)

        # --- Category toggles (which categories to transfer at all) ---
        toggles_group = QtWidgets.QGroupBox("Grammar piece categories to transfer", self)
        toggles_layout = QtWidgets.QGridLayout(toggles_group)
        self._toggles: dict = {}
        for i, cat in enumerate(_CATEGORY_TOGGLES):
            cb = QtWidgets.QCheckBox(cat.value.replace("_", " "), toggles_group)
            toggles_layout.addWidget(cb, i // 3, i % 3)
            self._toggles[cat] = cb
        outer.addWidget(toggles_group)

        # --- Per-schema-category scope + conflict mode combos ---
        scroll = QtWidgets.QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(container)
        grid.addWidget(QtWidgets.QLabel("<b>Category</b>", container), 0, 0)
        grid.addWidget(QtWidgets.QLabel("<b>Scope</b>", container), 0, 1)
        grid.addWidget(QtWidgets.QLabel("<b>Conflict mode</b>", container), 0, 2)

        self._scope_combos: dict = {}
        self._conflict_combos: dict = {}
        for row_i, cat in enumerate(_SCHEMA_CATEGORIES, start=1):
            grid.addWidget(
                QtWidgets.QLabel(cat.value.replace("_", " ") + ":", container),
                row_i, 0,
            )

            scope_cb = QtWidgets.QComboBox(container)
            for scope in (CategoryScope.NONE, CategoryScope.AS_NEEDED, CategoryScope.ALL):
                scope_cb.addItem(_SCOPE_LABELS[scope], scope)
            scope_cb.setCurrentIndex(1)  # AS_NEEDED default
            grid.addWidget(scope_cb, row_i, 1)
            self._scope_combos[cat] = scope_cb

            conflict_cb = QtWidgets.QComboBox(container)
            for mode in _allowed_modes(cat):
                conflict_cb.addItem(_CONFLICT_LABELS[mode], mode)
            # Default: Layer-1 default mode
            default_mode = _DEFAULT_CONFLICT_MODES.get(cat, ConflictMode.LINK)  # 022: LINK as ultimate fallback
            for idx in range(conflict_cb.count()):
                if conflict_cb.itemData(idx) == default_mode:
                    conflict_cb.setCurrentIndex(idx)
                    break
            grid.addWidget(conflict_cb, row_i, 2)
            self._conflict_combos[cat] = conflict_cb

        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

        # Legacy closure checkbox (back-compat fallback)
        self._closure_cb = QtWidgets.QCheckBox(
            "Include dependency closure (legacy fallback; per-category scopes above take precedence)",
            self,
        )
        self._closure_cb.setChecked(True)
        outer.addWidget(self._closure_cb)

    # ------------------------------------------------------------------
    def collect_selection(self, picker_state: PickerState,
                          inventory: SourceAffixInventory) -> Selection:
        """Build a Selection from this page's current UI state."""
        cats = {cat: True for cat, cb in self._toggles.items() if cb.isChecked()}
        category_scopes = {}
        for cat, combo in self._scope_combos.items():
            scope = combo.currentData()
            if scope is not None:
                category_scopes[cat] = scope
        category_conflict_modes = {}
        for cat, combo in self._conflict_combos.items():
            mode = combo.currentData()
            if mode is not None:
                category_conflict_modes[cat] = mode

        return build_selection(
            picker_state,
            inventory,
            include_closure=self._closure_cb.isChecked(),
            extra_categories=list(cats.keys()),
            category_scopes=category_scopes,
        )._replace_conflict_modes(category_conflict_modes)  # helper below


# ---------------------------------------------------------------------------
# Data roles for _PageSkeleton and _PageGramDeps trees
# ---------------------------------------------------------------------------

_SKEL_GUID_ROLE = QtCore.Qt.ItemDataRole.UserRole + 10   # slot/tpl/pos guid
_SKEL_KIND_ROLE = QtCore.Qt.ItemDataRole.UserRole + 11   # "pos"|"slot"|"template"|"dep"
_SKEL_READ_ONLY = QtCore.Qt.ItemDataRole.UserRole + 12   # bool: template slot entry
# T006 -- Data roles for _PageSkeleton (FR-010, R6)
_SKEL_STATUS_ROLE = QtCore.Qt.ItemDataRole.UserRole + 40  # "new" | "in_target" | "similar"
_SKEL_CAT_ROLE    = QtCore.Qt.ItemDataRole.UserRole + 41  # GrammarCategory (slot / template)
_SKEL_OWNER_ROLE  = QtCore.Qt.ItemDataRole.UserRole + 42  # owner POS GUID (for template/slot preview)
# T007 -- Data roles for _PageGramDeps (FR-010, R6)
# GrammarCategory mapping (research: _populate_deps_tree sections):
#   "Inflection Features" -> GrammarCategory.INFLECTION_FEATURES
#   "Inflection Classes"  -> GrammarCategory.INFLECTION_CLASSES
#   "Stem Names"          -> GrammarCategory.STEM_NAMES
_DEPS_STATUS_ROLE = QtCore.Qt.ItemDataRole.UserRole + 50  # "new" | "in_target" | "similar"
_DEPS_CAT_ROLE    = QtCore.Qt.ItemDataRole.UserRole + 51  # GrammarCategory

# Target-status label map (shared with affix picker).
_STATUS_LABELS = {
    "new": "NEW",
    "in_target": "IN TARGET",
    "similar": "SIMILAR",
}


# ---------------------------------------------------------------------------
# Page 3b -- Morphology Skeleton  (T011-T012)
# ---------------------------------------------------------------------------

class _PageSkeleton(QtWidgets.QWizardPage):
    """Page 3b: Morphology skeleton derived from the affix picks.

    POS-rooted tree:
        [POS node — preselected if any picked affix attaches]
          [Slots subgroup]
            [slot row — preselected if any picked affix fills it]
            ...
          [Templates subgroup]
            [template row — preselected if any referenced slot is filled]
              (slot read-only child items listing referenced slots)
            ...

    Target-status column: "NEW" / "IN TARGET" / "SIMILAR" / ""

    Template semantics (T012):
      - Checking a template selects its full referenced slot set (extra
        slots may transfer empty; FR-007).
      - Deselecting a template leaves only the affix-filled slots selected.
      - Template check/deselect NEVER re-expands affix_picks.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Step 5 of 9: Morphology Skeleton")
        self.setSubTitle(
            "Review the parts of speech, slots, and templates the picked affixes require. "
            "Pre-checked items are derived from your affix selection. "
            "Deselect to trim to a bare-bones transfer; check extras to add more."
        )
        self._skeleton: Optional[object] = None  # SkeletonInventory
        self._mirroring: bool = False
        # T013: preview service (initialized in initializePage)
        self._preview_service = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(
            "Slots/templates needed by the selected affixes are pre-checked. "
            "Checking a template includes all slots it arranges (even unfilled ones). "
            "Deselecting a template retains only slots filled by picked affixes.",
            self,
        ))
        self._tree = QtWidgets.QTreeWidget(self)
        self._tree.setColumnCount(3)
        self._tree.setHeaderLabels(["Slot / Template", "Affixes", "Target"])
        self._tree.header().setStretchLastSection(False)
        self._tree.setAlternatingRowColors(True)
        # T013: merge-preview pane docked to the right (FR-005)
        self._pane = MergePreviewPane(self)
        splitter = _make_tree_pane_splitter(self._tree, self._pane)
        layout.addWidget(splitter, 1)

    def initializePage(self) -> None:
        """Build skeleton from affix picks + bound target when the page is entered."""
        self._tree.itemChanged.disconnect() if self._tree.receivers(
            self._tree.itemChanged
        ) > 0 else None
        self._tree.clear()
        self._skeleton = None

        affix_picks = self._get_affix_picks()
        source = self._get_source()
        if source is None or not affix_picks:
            empty = QtWidgets.QTreeWidgetItem(
                self._tree, ["(No affixes selected or no source bound)"]
            )
            empty.setFlags(empty.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled)
            return

        target = self._get_target()
        try:
            skeleton = build_skeleton_inventory(source, affix_picks, target=target)
        except Exception:  # noqa: BLE001
            skeleton = None

        if skeleton is None or not skeleton.pos_nodes:
            empty = QtWidgets.QTreeWidgetItem(
                self._tree, ["(No skeleton derived from current affix picks)"]
            )
            empty.setFlags(empty.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled)
            return

        self._skeleton = skeleton
        # spec 011: POS / slot / template names render in the analysis WS font.
        attach_ws_font_delegate(
            self._tree, [0], WsFontRegistry.from_project(source)
        )
        self._populate_skeleton_tree(skeleton)
        self._tree.expandAll()
        for col in range(3):
            self._tree.resizeColumnToContents(col)
        self._tree.itemChanged.connect(self._on_item_changed)

        # T013: construct service and set pane context (FR-006)
        self._preview_service = MergePreviewService(source, target)
        self._pane.set_context(
            self._preview_service,
            WsFontRegistry.from_project(source),
            [],  # no candidates for skeleton
        )
        self._pane.clear()
        # Double-connect guard
        if self._tree.receivers(self._tree.currentItemChanged) == 0:
            self._tree.currentItemChanged.connect(self._on_tree_selection_changed)

    def _populate_skeleton_tree(self, skeleton) -> None:
        """Build the POS-rooted skeleton tree from a SkeletonInventory."""
        for pos_node in skeleton.pos_nodes:
            pos_item = QtWidgets.QTreeWidgetItem(
                self._tree,
                [pos_node.label, "", _STATUS_LABELS.get(pos_node.status or "", "")]
            )
            pos_item.setData(0, _SKEL_GUID_ROLE, pos_node.pos_guid)
            set_ws_runs(pos_item, 0, ((pos_node.label, WsRole.ANALYSIS),))
            pos_item.setData(0, _SKEL_KIND_ROLE, "pos")
            pos_item.setFlags(
                pos_item.flags()
                | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                | QtCore.Qt.ItemFlag.ItemIsAutoTristate
            )
            check_state = (QtCore.Qt.CheckState.Checked if pos_node.preselected
                           else QtCore.Qt.CheckState.Unchecked)
            pos_item.setCheckState(0, check_state)
            from PyQt6 import QtGui
            bold_font = pos_item.font(0)
            bold_font.setBold(True)
            pos_item.setFont(0, bold_font)

            # Slots subgroup
            if pos_node.slots:
                slots_group = QtWidgets.QTreeWidgetItem(pos_item, ["Slots", "", ""])
                slots_group.setData(0, _SKEL_KIND_ROLE, "slots_group")
                slots_group.setFlags(
                    slots_group.flags()
                    | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                    | QtCore.Qt.ItemFlag.ItemIsAutoTristate
                )
                slots_group.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
                bold_f = slots_group.font(0)
                bold_f.setBold(True)
                slots_group.setFont(0, bold_f)
                for slot_node in pos_node.slots:
                    count_label = (
                        f"{slot_node.affix_count} affix"
                        + ("es" if slot_node.affix_count != 1 else "")
                        if slot_node.affix_count > 0 else ""
                    )
                    slot_item = QtWidgets.QTreeWidgetItem(
                        slots_group,
                        [slot_node.label, count_label,
                         _STATUS_LABELS.get(slot_node.status or "", "")]
                    )
                    slot_item.setData(0, _SKEL_GUID_ROLE, slot_node.slot_guid)
                    set_ws_runs(slot_item, 0, ((slot_node.label, WsRole.ANALYSIS),))
                    slot_item.setData(0, _SKEL_KIND_ROLE, "slot")
                    slot_item.setFlags(
                        slot_item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                    )
                    slot_cs = (QtCore.Qt.CheckState.Checked if slot_node.preselected
                               else QtCore.Qt.CheckState.Unchecked)
                    slot_item.setCheckState(0, slot_cs)
                    # T006: data roles for pane PreviewRequest (FR-010, R6)
                    slot_item.setData(0, _SKEL_STATUS_ROLE, slot_node.status or "")
                    slot_item.setData(0, _SKEL_CAT_ROLE, GrammarCategory.SLOTS)
                    slot_item.setData(0, _SKEL_OWNER_ROLE, pos_node.pos_guid)

            # Templates subgroup
            if pos_node.templates:
                tpl_group = QtWidgets.QTreeWidgetItem(pos_item, ["Templates", "", ""])
                tpl_group.setData(0, _SKEL_KIND_ROLE, "templates_group")
                tpl_group.setFlags(
                    tpl_group.flags()
                    | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                    | QtCore.Qt.ItemFlag.ItemIsAutoTristate
                )
                tpl_group.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
                bold_tf = tpl_group.font(0)
                bold_tf.setBold(True)
                tpl_group.setFont(0, bold_tf)
                for tpl_node in pos_node.templates:
                    tpl_item = QtWidgets.QTreeWidgetItem(
                        tpl_group,
                        [tpl_node.label, "",
                         _STATUS_LABELS.get(tpl_node.status or "", "")]
                    )
                    tpl_item.setData(0, _SKEL_GUID_ROLE, tpl_node.template_guid)
                    set_ws_runs(tpl_item, 0, ((tpl_node.label, WsRole.ANALYSIS),))
                    tpl_item.setData(0, _SKEL_KIND_ROLE, "template")
                    tpl_item.setFlags(
                        tpl_item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                    )
                    tpl_cs = (QtCore.Qt.CheckState.Checked if tpl_node.preselected
                              else QtCore.Qt.CheckState.Unchecked)
                    tpl_item.setCheckState(0, tpl_cs)
                    # T006: data roles for pane PreviewRequest (FR-010, R6)
                    tpl_item.setData(0, _SKEL_STATUS_ROLE, tpl_node.status or "")
                    tpl_item.setData(0, _SKEL_CAT_ROLE, GrammarCategory.AFFIX_TEMPLATES)
                    tpl_item.setData(0, _SKEL_OWNER_ROLE, pos_node.pos_guid)
                    # Read-only slot list under the template (FR-006)
                    for ref_sg in tpl_node.referenced_slot_guids:
                        # Find the slot node from the POS to recover its label
                        # and Optional flag.
                        ref_slot = next(
                            (s for s in pos_node.slots if s.slot_guid == ref_sg),
                            None,
                        )
                        slot_label = ref_slot.label if ref_slot else ref_sg[:8]
                        # FLEx convention: optional slots are shown in parentheses.
                        if ref_slot is not None and ref_slot.optional:
                            slot_label = f"({slot_label})"
                        ro_item = QtWidgets.QTreeWidgetItem(
                            tpl_item, [f"  {slot_label}", "", ""]
                        )
                        set_ws_runs(ro_item, 0,
                                    (("  ", None), (slot_label, WsRole.ANALYSIS)))
                        ro_item.setData(0, _SKEL_GUID_ROLE, ref_sg)
                        ro_item.setData(0, _SKEL_KIND_ROLE, "template_slot_ro")
                        ro_item.setData(0, _SKEL_READ_ONLY, True)
                        # Read-only: no checkable flag
                        ro_item.setFlags(
                            ro_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsUserCheckable
                        )

        # Strike through referenced-slot rows whose slot won't copy over.
        self._refresh_template_strikethroughs()

    # T013: tree selection handler (display-only, resolvable=False for all rows)
    def _on_tree_selection_changed(self, current, previous) -> None:
        """Build PreviewRequest from selected skeleton row (display-only)."""
        if current is None:
            self._pane.clear()
            return
        kind = current.data(0, _SKEL_KIND_ROLE)
        # Group/header rows -> clear
        if kind not in ("slot", "template"):
            self._pane.clear()
            return

        source_guid = current.data(0, _SKEL_GUID_ROLE) or ""
        category = current.data(0, _SKEL_CAT_ROLE)
        status = current.data(0, _SKEL_STATUS_ROLE) or ""
        owner_guid = current.data(0, _SKEL_OWNER_ROLE) or ""

        if status == "new":
            target_guid = ""
            mode = NEW
        elif status == "similar":
            target_guid = source_guid
            mode = OVERWRITE
        else:  # "in_target"
            target_guid = source_guid
            mode = OVERWRITE

        cat_str = (category.value if category is not None
                   else GrammarCategory.SLOTS.value)
        request = PreviewRequest(
            category=cat_str,
            source_guid=source_guid,
            target_guid=target_guid,
            status=status,
            mode=mode,
            resolvable=False,
            current_resolution=None,
            owner_guid=owner_guid,
        )
        self._pane.show_item(request)

    def _on_item_changed(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        """Handle template check/deselect semantics (T012)."""
        if self._mirroring or column != 0:
            return
        if self._skeleton is None:
            return
        kind = item.data(0, _SKEL_KIND_ROLE)
        if kind == "template":
            # Template check/deselect: update slot check states accordingly.
            tpl_guid = item.data(0, _SKEL_GUID_ROLE)
            new_state = item.checkState(0)
            self._mirroring = True
            try:
                self._apply_template_slot_semantics(tpl_guid, new_state)
            finally:
                self._mirroring = False
        # Any slot/template toggle can change what copies over -> restrike
        # the template referenced-slot rows. Font-only, so no itemChanged
        # recursion, but keep it under the guard for safety.
        self._mirroring = True
        try:
            self._refresh_template_strikethroughs()
        finally:
            self._mirroring = False

    def _refresh_template_strikethroughs(self) -> None:
        """Strike through template referenced-slot rows whose slot won't copy.

        A referenced slot copies over iff its slot checkbox is currently
        checked. Empty (deselected) slots -- including empty optional slots
        like Repetitive -- render struck through so the user can see at a
        glance which template positions carry nothing across.
        """
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            pos_item = root.child(i)
            if pos_item.data(0, _SKEL_KIND_ROLE) != "pos":
                continue
            # Map slot_guid -> checked for this POS's real (checkable) slots.
            checked: dict = {}
            for j in range(pos_item.childCount()):
                group = pos_item.child(j)
                if group.data(0, _SKEL_KIND_ROLE) != "slots_group":
                    continue
                for k in range(group.childCount()):
                    slot_item = group.child(k)
                    if slot_item.data(0, _SKEL_KIND_ROLE) != "slot":
                        continue
                    sg = slot_item.data(0, _SKEL_GUID_ROLE)
                    checked[sg] = (
                        slot_item.checkState(0) == QtCore.Qt.CheckState.Checked
                    )
            # Apply strikethrough to template_slot_ro rows accordingly.
            for j in range(pos_item.childCount()):
                group = pos_item.child(j)
                if group.data(0, _SKEL_KIND_ROLE) != "templates_group":
                    continue
                for k in range(group.childCount()):
                    tpl_item = group.child(k)
                    for m in range(tpl_item.childCount()):
                        ro = tpl_item.child(m)
                        if ro.data(0, _SKEL_KIND_ROLE) != "template_slot_ro":
                            continue
                        sg = ro.data(0, _SKEL_GUID_ROLE)
                        struck = not checked.get(sg, False)
                        f = ro.font(0)
                        f.setStrikeOut(struck)
                        ro.setFont(0, f)

    def _apply_template_slot_semantics(self, tpl_guid: str,
                                        tpl_state) -> None:
        """Apply template check/deselect semantics to the slot checkboxes.

        Checked: force all referenced slots checked.
        Unchecked: revert slots to affix-filled state only (bare-bones).
        Never modifies affix_picks (FR-007).
        """
        if self._skeleton is None:
            return
        # Find the template node
        tpl_node = None
        pos_node_found = None
        for pos_node in self._skeleton.pos_nodes:
            for tn in pos_node.templates:
                if tn.template_guid == tpl_guid:
                    tpl_node = tn
                    pos_node_found = pos_node
                    break
            if tpl_node is not None:
                break
        if tpl_node is None or pos_node_found is None:
            return

        if tpl_state == QtCore.Qt.CheckState.Checked:
            # Force all referenced slots checked
            slots_to_check = set(tpl_node.referenced_slot_guids)
        else:
            # Deselect: only affix-filled slots remain
            slots_to_check = self._skeleton.affix_filled_slot_guids()

        # Walk the tree and update slot items under this POS
        self._update_slot_checks_in_tree(pos_node_found.pos_guid, slots_to_check,
                                          tpl_state == QtCore.Qt.CheckState.Checked)

    def _update_slot_checks_in_tree(self, pos_guid: str, slot_guids: set,
                                     force_checked: bool) -> None:
        """Walk the tree and set slot check states under the given POS."""
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            pos_item = root.child(i)
            if pos_item.data(0, _SKEL_GUID_ROLE) != pos_guid:
                continue
            for j in range(pos_item.childCount()):
                group = pos_item.child(j)
                if group.data(0, _SKEL_KIND_ROLE) != "slots_group":
                    continue
                for k in range(group.childCount()):
                    slot_item = group.child(k)
                    if slot_item.data(0, _SKEL_KIND_ROLE) != "slot":
                        continue
                    sg = slot_item.data(0, _SKEL_GUID_ROLE)
                    if force_checked and sg in slot_guids:
                        slot_item.setCheckState(0, QtCore.Qt.CheckState.Checked)
                    elif not force_checked:
                        # Deselect: only keep affix-filled
                        cs = (QtCore.Qt.CheckState.Checked
                              if sg in slot_guids
                              else QtCore.Qt.CheckState.Unchecked)
                        slot_item.setCheckState(0, cs)

    # ------------------------------------------------------------------
    def _get_source(self):
        try:
            w = self.wizard()
            if w is None:
                return None
            p0 = w.page_project_ws()
            if p0 is None:
                return None
            ctx = p0.context()
            if ctx is not None:
                h = getattr(ctx, "source_handle", None)
                if h is not None:
                    return h
            return getattr(p0, "_host", None)
        except Exception:  # noqa: BLE001
            return None

    def _get_target(self):
        try:
            w = self.wizard()
            if w is None:
                return None
            p0 = w.page_project_ws()
            if p0 is None:
                return None
            ctx = p0.context()
            if ctx is None:
                return None
            return getattr(ctx, "target_handle", None)
        except Exception:  # noqa: BLE001
            return None

    def _get_affix_picks(self) -> frozenset:
        """Retrieve affix_picks from the item-picker page (index 1)."""
        try:
            w = self.wizard()
            if w is None:
                return frozenset()
            page_items = w.page_items()
            if page_items is None:
                return frozenset()
            sel = page_items.collect_selection()
            return sel.affix_picks
        except Exception:  # noqa: BLE001
            return frozenset()

    def _get_stem_picks(self) -> frozenset:
        """019: retrieve stem_picks from the item-picker page (mirror of
        _get_affix_picks). The skeleton builder itself stays AFFIX-ONLY per
        FR-013; this accessor exists for parity and downstream use.
        """
        try:
            w = self.wizard()
            if w is None:
                return frozenset()
            page_items = w.page_items()
            if page_items is None:
                return frozenset()
            sel = page_items.collect_selection()
            return sel.stem_picks
        except Exception:  # noqa: BLE001
            return frozenset()

    def collect_skeleton_picks(self) -> dict:
        """Return the current skeleton selections as:
        {
          "pos_guids": set[str],
          "slot_guids": set[str],
          "template_guids": set[str],
        }
        """
        pos_guids: Set[str] = set()
        slot_guids: Set[str] = set()
        template_guids: Set[str] = set()
        root = self._tree.invisibleRootItem()

        def _walk(node: QtWidgets.QTreeWidgetItem) -> None:
            kind = node.data(0, _SKEL_KIND_ROLE)
            state = node.checkState(0)
            if kind == "pos" and state == QtCore.Qt.CheckState.Checked:
                g = node.data(0, _SKEL_GUID_ROLE)
                if g:
                    pos_guids.add(g)
            elif kind == "slot" and state == QtCore.Qt.CheckState.Checked:
                g = node.data(0, _SKEL_GUID_ROLE)
                if g:
                    slot_guids.add(g)
            elif kind == "template" and state == QtCore.Qt.CheckState.Checked:
                g = node.data(0, _SKEL_GUID_ROLE)
                if g:
                    template_guids.add(g)
            for i in range(node.childCount()):
                _walk(node.child(i))

        for i in range(root.childCount()):
            _walk(root.child(i))

        return {
            "pos_guids": pos_guids,
            "slot_guids": slot_guids,
            "template_guids": template_guids,
        }

    def deselected_filled_slot_guids(self) -> frozenset:
        """Return slot GUIDs that a picked affix fills but the user unchecked.

        Used by the EXCLUDED-LOSSY gate at Move (T017).
        """
        if self._skeleton is None:
            return frozenset()
        picks = self.collect_skeleton_picks()
        checked_slots = picks["slot_guids"]
        affix_filled = self._skeleton.affix_filled_slot_guids()
        return frozenset(affix_filled - checked_slots)


# ---------------------------------------------------------------------------
# Page 3c -- Grammatical Dependencies  (T014)
# ---------------------------------------------------------------------------

class _PageGramDeps(QtWidgets.QWizardPage):
    """Page 3c: Grammatical dependencies derived from the affix picks' POSes.

    Sections:
      - Inflection Features
      - Inflection Classes
      - Stem Names

    ExceptionFeaturesOC does not exist on the live LCM runtime; that dep-kind
    is tracked under a separate shared-bug ticket and is NOT shown here.

    All items are preselected (AS-NEEDED); per-item deselect is the user action.
    Empty sections render cleanly (no error, section header visible but empty).
    Target-status column (NEW / IN TARGET / SIMILAR).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Step 6 of 9: Grammatical Dependencies")
        self.setSubTitle(
            "Review the inflection features, classes, and stem names "
            "that the picked affixes' parts of speech require. All are preselected. "
            "Deselect items you do not want to transfer."
        )
        self._deps: Optional[object] = None  # DepsInventory
        # T014: preview service (initialized in initializePage)
        self._preview_service = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        self._tree = QtWidgets.QTreeWidget(self)
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["Item", "Target"])
        self._tree.header().setStretchLastSection(True)
        self._tree.setAlternatingRowColors(True)
        # T014: merge-preview pane docked to the right (FR-005)
        self._pane = MergePreviewPane(self)
        splitter = _make_tree_pane_splitter(self._tree, self._pane)
        layout.addWidget(splitter, 1)

    def initializePage(self) -> None:
        """Build deps from affix picks + bound target when the page is entered."""
        self._tree.clear()
        self._deps = None

        affix_picks = self._get_affix_picks()
        stem_picks = self._get_stem_picks()
        source = self._get_source()
        if source is None or not (affix_picks or stem_picks):
            empty = QtWidgets.QTreeWidgetItem(
                self._tree, ["(No affixes or stems selected, or no source bound)"]
            )
            empty.setFlags(empty.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled)
            return

        target = self._get_target()
        try:
            deps = build_deps_inventory(
                source, affix_picks, target=target, stem_picks=stem_picks
            )
        except Exception:  # noqa: BLE001
            deps = None

        if deps is None:
            return

        self._deps = deps
        # spec 011: feature / class / stem-name labels in the analysis WS font.
        attach_ws_font_delegate(
            self._tree, [0], WsFontRegistry.from_project(source)
        )
        self._populate_deps_tree(deps)
        self._tree.expandAll()
        for col in range(2):
            self._tree.resizeColumnToContents(col)

        # T014: construct service and set pane context (FR-006)
        self._preview_service = MergePreviewService(source, target)
        self._pane.set_context(
            self._preview_service,
            WsFontRegistry.from_project(source),
            [],  # no candidates for deps
        )
        self._pane.clear()
        # Double-connect guard
        if self._tree.receivers(self._tree.currentItemChanged) == 0:
            self._tree.currentItemChanged.connect(self._on_tree_selection_changed)

    def _on_tree_selection_changed(self, current, previous) -> None:
        """T014: build PreviewRequest from selected deps row (display-only)."""
        if current is None:
            self._pane.clear()
            return
        kind = current.data(0, _SKEL_KIND_ROLE)
        # Section-header rows -> clear
        if kind != "dep":
            self._pane.clear()
            return

        source_guid = current.data(0, _SKEL_GUID_ROLE) or ""
        category = current.data(0, _DEPS_CAT_ROLE)
        status = current.data(0, _DEPS_STATUS_ROLE) or ""

        if status == "new":
            target_guid = ""
            mode = NEW
        elif status == "similar":
            target_guid = source_guid
            mode = OVERWRITE
        else:  # "in_target"
            target_guid = source_guid
            mode = OVERWRITE

        cat_str = (category.value if category is not None
                   else GrammarCategory.INFLECTION_FEATURES.value)
        request = PreviewRequest(
            category=cat_str,
            source_guid=source_guid,
            target_guid=target_guid,
            status=status,
            mode=mode,
            resolvable=False,
            current_resolution=None,
            owner_guid="",
        )
        self._pane.show_item(request)

    def _populate_deps_tree(self, deps) -> None:
        """Populate the sections tree from a DepsInventory."""
        # T007: category mapping (research confirmed from section labels)
        _SECTION_CAT = {
            "Inflection Features": GrammarCategory.INFLECTION_FEATURES,
            "Inflection Classes": GrammarCategory.INFLECTION_CLASSES,
            "Stem Names": GrammarCategory.STEM_NAMES,
        }
        sections = [
            ("Inflection Features", deps.infl_features),
            ("Inflection Classes", deps.infl_classes),
            ("Stem Names", deps.stem_names),
        ]
        for section_label, rows in sections:
            section_item = QtWidgets.QTreeWidgetItem(
                self._tree, [section_label, ""]
            )
            section_item.setData(0, _SKEL_KIND_ROLE, "section")
            # Section-header rows do NOT receive item-level status roles (T007)
            section_item.setFlags(
                section_item.flags()
                | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                | QtCore.Qt.ItemFlag.ItemIsAutoTristate
            )
            section_item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
            from PyQt6 import QtGui
            bold_f = section_item.font(0)
            bold_f.setBold(True)
            section_item.setFont(0, bold_f)
            if not rows:
                empty_child = QtWidgets.QTreeWidgetItem(
                    section_item, ["(none)", ""]
                )
                empty_child.setFlags(
                    empty_child.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled
                )
            else:
                grammar_cat = _SECTION_CAT.get(section_label)
                for row in rows:
                    row_item = QtWidgets.QTreeWidgetItem(
                        section_item,
                        [row.label, _STATUS_LABELS.get(row.status or "", "")]
                    )
                    set_ws_runs(row_item, 0, ((row.label, WsRole.ANALYSIS),))
                    row_item.setData(0, _SKEL_GUID_ROLE, row.guid)
                    row_item.setData(0, _SKEL_KIND_ROLE, "dep")
                    # T007: data roles for pane PreviewRequest (FR-010, R6)
                    row_item.setData(0, _DEPS_STATUS_ROLE, row.status or "")
                    if grammar_cat is not None:
                        row_item.setData(0, _DEPS_CAT_ROLE, grammar_cat)
                    row_item.setFlags(
                        row_item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                    )
                    cs = (QtCore.Qt.CheckState.Checked if row.preselected
                          else QtCore.Qt.CheckState.Unchecked)
                    row_item.setCheckState(0, cs)

    # ------------------------------------------------------------------
    def _get_source(self):
        try:
            w = self.wizard()
            if w is None:
                return None
            p0 = w.page_project_ws()
            if p0 is None:
                return None
            ctx = p0.context()
            if ctx is not None:
                h = getattr(ctx, "source_handle", None)
                if h is not None:
                    return h
            return getattr(p0, "_host", None)
        except Exception:  # noqa: BLE001
            return None

    def _get_target(self):
        try:
            w = self.wizard()
            if w is None:
                return None
            p0 = w.page_project_ws()
            if p0 is None:
                return None
            ctx = p0.context()
            if ctx is None:
                return None
            return getattr(ctx, "target_handle", None)
        except Exception:  # noqa: BLE001
            return None

    def _get_affix_picks(self) -> frozenset:
        try:
            w = self.wizard()
            if w is None:
                return frozenset()
            page_items = w.page_items()
            if page_items is None:
                return frozenset()
            sel = page_items.collect_selection()
            return sel.affix_picks
        except Exception:  # noqa: BLE001
            return frozenset()

    def _get_stem_picks(self) -> frozenset:
        """019: retrieve stem_picks from the item-picker page (mirror of
        _get_affix_picks)."""
        try:
            w = self.wizard()
            if w is None:
                return frozenset()
            page_items = w.page_items()
            if page_items is None:
                return frozenset()
            sel = page_items.collect_selection()
            return sel.stem_picks
        except Exception:  # noqa: BLE001
            return frozenset()

    def collect_dep_picks(self) -> dict:
        """Return currently-checked dep GUIDs by section.

        Returns
        -------
        dict with keys:
          "infl_features", "infl_classes", "stem_names", "exception_features"
          each a set[str] of GUIDs.
        """
        result = {
            "infl_features": set(),
            "infl_classes": set(),
            "stem_names": set(),
        }
        section_map = {
            "Inflection Features": "infl_features",
            "Inflection Classes": "infl_classes",
            "Stem Names": "stem_names",
        }
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            section_item = root.child(i)
            section_label = section_item.text(0)
            key = section_map.get(section_label)
            if key is None:
                continue
            for j in range(section_item.childCount()):
                row_item = section_item.child(j)
                if row_item.checkState(0) == QtCore.Qt.CheckState.Checked:
                    g = row_item.data(0, _SKEL_GUID_ROLE)
                    if g:
                        result[key].add(g)
        return result

    def deselected_dep_guids(self) -> frozenset:
        """Return all GUIDs that were preselected but the user unchecked.

        Used for EXCLUDED-LOSSY warnings.
        """
        if self._deps is None:
            return frozenset()
        all_preselected = frozenset(
            row.guid
            for collection in (
                self._deps.infl_features,
                self._deps.infl_classes,
                self._deps.stem_names,
            )
            for row in collection
            if row.preselected
        )
        picks = self.collect_dep_picks()
        checked = frozenset(
            g
            for guids in picks.values()
            for g in guids
        )
        return all_preselected - checked


# ---------------------------------------------------------------------------
# Page 2 -- Custom Fields  (Feature 016, US1/US2/US4)
# ---------------------------------------------------------------------------

# Data roles for _PageCustomFields
_CF_GUID_ROLE   = QtCore.Qt.ItemDataRole.UserRole + 60  # synthetic "cf:<owner>:<name>" guid
_CF_KIND_ROLE   = QtCore.Qt.ItemDataRole.UserRole + 61  # "group" | "item"
_CF_STATUS_ROLE = QtCore.Qt.ItemDataRole.UserRole + 63  # "NEW" | "IN TARGET" | ""

# Display labels for the four owner-class levels.
_CF_LEVEL_LABELS = {
    "LexEntry":           "Entry",
    "LexSense":           "Sense",
    "LexExampleSentence": "Example",
    "MoForm":             "Allomorph",
}


class _PageCustomFields(QtWidgets.QWizardPage):
    """Page 2: Custom Fields block (Feature 016, US1/US2/US4).

    Grouped tree: four owner-class levels (Entry / Sense / Example / Allomorph),
    each with a count on its header.  Every row shows ``name + type-label`` in
    col 0 and target-status in col 1 (US4).  ALL rows preselected on open.

    The whole-block tristate toggle mirrors _PagePhonology: empty block =>
    unchecked + disabled (not vacuously full, per Acceptance 1.3).

    No ADD_NEW / LINK / UPDATE / OVERWRITE conflict-mode control (per spec: CUSTOM_FIELDS
    uses conservative LINK-only default, applied automatically at plan time).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Step 2 of 9: Custom Fields")
        self.setSubTitle(
            "Review the source project's custom fields. All fields are preselected. "
            "Untick the block to skip custom fields, or deselect individual fields. "
            "Status column shows whether each field exists in the target."
        )
        self._mirroring: bool = False
        self._records: list = []   # list[_CustomFieldRecord]
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        self._whole_block = QtWidgets.QCheckBox("Transfer custom fields block", self)
        self._whole_block.setTristate(True)
        self._whole_block.clicked.connect(self._on_whole_block_clicked)
        layout.addWidget(self._whole_block)

        self._tree = QtWidgets.QTreeWidget(self)
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["Field (type)", "Status"])
        self._tree.header().setStretchLastSection(True)
        self._tree.setAlternatingRowColors(True)
        layout.addWidget(self._tree, 1)

    # ------------------------------------------------------------------
    def initializePage(self) -> None:
        """Called when the wizard enters this page; populates from source."""
        if self._tree.receivers(self._tree.itemChanged) > 0:
            self._tree.itemChanged.disconnect(self._on_item_changed)
        self._populate_from_source()
        self._tree.itemChanged.connect(self._on_item_changed)

    def _populate_from_source(self) -> None:
        """Enumerate source custom fields and build the four-level tree."""
        self._tree.clear()
        self._records = []

        source = self._get_source()
        target = self._get_target()

        if source is None:
            empty = QtWidgets.QTreeWidgetItem(self._tree, ["(No source project bound)", ""])
            empty.setFlags(empty.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled)
            self._refresh_whole_block()
            return

        # Import enumerate helper from categories (read-only, safe inside UoW).
        if __package__:
            from ..categories import (
                _enumerate_custom_fields,
                custom_field_type_label,
                classify_custom_field,
            )
        else:
            from categories import (  # type: ignore
                _enumerate_custom_fields,
                custom_field_type_label,
                classify_custom_field,
            )

        try:
            all_records = list(_enumerate_custom_fields(source))
        except Exception:  # noqa: BLE001
            all_records = []

        self._records = all_records

        # Group by owner class in canonical order.
        from PyQt6 import QtGui as _QtGui

        if __package__:
            from ..categories import _CUSTOM_FIELD_OWNER_CLASSES
        else:
            from categories import _CUSTOM_FIELD_OWNER_CLASSES  # type: ignore

        by_class: dict = {cls: [] for cls in _CUSTOM_FIELD_OWNER_CLASSES}
        for rec in all_records:
            if rec.owner_class in by_class:
                by_class[rec.owner_class].append(rec)

        for cls in _CUSTOM_FIELD_OWNER_CLASSES:
            rows = by_class[cls]
            level_label = _CF_LEVEL_LABELS.get(cls, cls)
            count = len(rows)
            header = QtWidgets.QTreeWidgetItem(
                self._tree, [f"{level_label} ({count})", ""]
            )
            header.setData(0, _CF_KIND_ROLE, "group")
            header.setFlags(
                header.flags()
                | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                | QtCore.Qt.ItemFlag.ItemIsAutoTristate
            )
            header.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
            bold = header.font(0)
            bold.setBold(True)
            header.setFont(0, bold)

            for rec in rows:
                type_label = custom_field_type_label(rec.field_type)
                row_label = f"{rec.name} ({type_label})"

                # US4: classify against target.
                status, type_diff_note = ("", None)
                if target is not None:
                    try:
                        status, type_diff_note = classify_custom_field(rec, target)
                    except Exception:  # noqa: BLE001
                        status, type_diff_note = "", None

                # Map status token to display text.
                _status_display = {
                    "NEW": "NEW",
                    "IN_TARGET": "IN TARGET",
                    "": "",
                }
                status_text = _status_display.get(status, status)
                if type_diff_note:
                    status_text = "IN TARGET"  # field exists, type differs

                item = QtWidgets.QTreeWidgetItem(header, [row_label, status_text])
                item.setData(0, _CF_GUID_ROLE, rec.guid)
                item.setData(0, _CF_KIND_ROLE, "item")
                item.setData(0, _CF_STATUS_ROLE, status)
                item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, QtCore.Qt.CheckState.Checked)
                if type_diff_note:
                    item.setToolTip(0, type_diff_note)
                    item.setToolTip(1, type_diff_note)

        self._tree.expandAll()
        for col in range(2):
            self._tree.resizeColumnToContents(col)
        self._refresh_whole_block()

    # -- whole-block toggle -----------------------------------------------
    def _on_whole_block_clicked(self, _checked: bool = False) -> None:
        if not self._has_any_item():
            self._refresh_whole_block()
            return
        want_checked = not self._all_items_checked()
        self._set_all_items(want_checked)
        self._refresh_whole_block()

    def _set_all_items(self, checked: bool) -> None:
        state = (QtCore.Qt.CheckState.Checked if checked
                 else QtCore.Qt.CheckState.Unchecked)
        self._mirroring = True
        try:
            for _grp, item in self._iter_item_rows():
                item.setCheckState(0, state)
        finally:
            self._mirroring = False

    def _refresh_whole_block(self) -> None:
        """Reflect aggregate item state on the whole-block tristate box.

        Empty block => unchecked + disabled (NOT vacuously full, per Acceptance 1.3).
        """
        self._mirroring = True
        try:
            if not self._has_any_item():
                self._whole_block.setEnabled(False)
                self._whole_block.setCheckState(QtCore.Qt.CheckState.Unchecked)
                return
            self._whole_block.setEnabled(True)
            checked = sum(
                1 for _g, it in self._iter_item_rows()
                if it.checkState(0) == QtCore.Qt.CheckState.Checked
            )
            total = sum(1 for _ in self._iter_item_rows())
            if checked == 0:
                self._whole_block.setCheckState(QtCore.Qt.CheckState.Unchecked)
            elif checked == total:
                self._whole_block.setCheckState(QtCore.Qt.CheckState.Checked)
            else:
                self._whole_block.setCheckState(QtCore.Qt.CheckState.PartiallyChecked)
        finally:
            self._mirroring = False

    def _on_item_changed(self, item, column) -> None:
        if self._mirroring or column != 0:
            return
        self._refresh_whole_block()

    # -- tree walking helpers -----------------------------------------------
    def _iter_item_rows(self):
        """Yield (group_item, item) for every checkable custom-field item row."""
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            if group.data(0, _CF_KIND_ROLE) != "group":
                continue
            for j in range(group.childCount()):
                item = group.child(j)
                if item.data(0, _CF_KIND_ROLE) == "item":
                    yield group, item

    def _has_any_item(self) -> bool:
        for _ in self._iter_item_rows():
            return True
        return False

    def _all_items_checked(self) -> bool:
        any_item = False
        for _g, item in self._iter_item_rows():
            any_item = True
            if item.checkState(0) != QtCore.Qt.CheckState.Checked:
                return False
        return any_item

    # -- state API (US2) ---------------------------------------------------
    def leaf_item_picks(self) -> dict:
        """Return leaf_item_picks dict for custom fields.

        Fully-checked => omit key (transfer-all back-compat).
        Partial => {GrammarCategory.CUSTOM_FIELDS: frozenset[str guids]}.
        Fully-unchecked / empty => {GrammarCategory.CUSTOM_FIELDS: frozenset()}.
        """
        if not self._has_any_item():
            return {}

        checked_guids: set = set()
        total = 0
        for _grp, item in self._iter_item_rows():
            total += 1
            if item.checkState(0) == QtCore.Qt.CheckState.Checked:
                guid = item.data(0, _CF_GUID_ROLE)
                if guid:
                    checked_guids.add(guid)

        if len(checked_guids) == total:
            # Fully checked => omit key (transfer-all).
            return {}
        return {GrammarCategory.CUSTOM_FIELDS: frozenset(checked_guids)}

    def whole_block_on(self) -> bool:
        """True iff any field row is checked."""
        for _g, item in self._iter_item_rows():
            if item.checkState(0) == QtCore.Qt.CheckState.Checked:
                return True
        return False

    # -- source/target helpers ---------------------------------------------
    def _get_source(self):
        try:
            w = self.wizard()
            if w is None:
                return None
            p0 = w.page_project_ws()
            if p0 is None:
                return None
            ctx = p0.context()
            if ctx is not None:
                h = getattr(ctx, "source_handle", None)
                if h is not None:
                    return h
            return getattr(p0, "_host", None)
        except Exception:  # noqa: BLE001
            return None

    def _get_target(self):
        try:
            w = self.wizard()
            if w is None:
                return None
            p0 = w.page_project_ws()
            if p0 is None:
                return None
            ctx = p0.context()
            if ctx is None:
                return None
            return getattr(ctx, "target_handle", None)
        except Exception:  # noqa: BLE001
            return None


# ---------------------------------------------------------------------------
# Page 3 -- Phonology  (spec 010, Model-B independent block)
# ---------------------------------------------------------------------------

_PHON_GUID_ROLE = QtCore.Qt.ItemDataRole.UserRole + 20   # source GUID (item rows)
_PHON_KIND_ROLE = QtCore.Qt.ItemDataRole.UserRole + 21   # "group" | "item"
_PHON_CAT_ROLE = QtCore.Qt.ItemDataRole.UserRole + 22    # GrammarCategory (group + item)
# T008 -- Data role for _PagePhonology (FR-010, R6)
_PHON_STATUS_ROLE = QtCore.Qt.ItemDataRole.UserRole + 23  # "new" | "in_target" | "similar"

# SC-008: module-level aliases used inside _PagePhonology instead of string literals.
_PHON_MODE_OVERWRITE = OVERWRITE
_PHON_MODE_NEW = NEW

# ---------------------------------------------------------------------------
# Data roles for _PageRules (018-rules-page T017)
# ---------------------------------------------------------------------------

_RULES_GUID_ROLE   = QtCore.Qt.ItemDataRole.UserRole + 70  # normalized rule GUID (item rows)
_RULES_KIND_ROLE   = QtCore.Qt.ItemDataRole.UserRole + 71  # "group" | "item"
_RULES_STATUS_ROLE = QtCore.Qt.ItemDataRole.UserRole + 72  # "NEW" | "IN TARGET" | "SIMILAR" | ""

# Status display map shared with phonology convention
_RULES_STATUS_LABELS = {
    "NEW": "NEW",
    "IN TARGET": "IN TARGET",
    "SIMILAR": "SIMILAR",
    "": "",
}


class _PageRules(QtWidgets.QWizardPage):
    """Rules page (018-rules-page): Ad Hoc Rules + Compound Rules block.

    Two grouped tristate trees, all rows preselected.  Whole-block toggle
    controls the entire block (tristate: all / none / partial).  Empty
    category renders as empty (FR-011) — not an error.

    No ADD_NEW / LINK / UPDATE / OVERWRITE conflict-mode control (FR-016):
    per-category Layer-1 defaults are applied automatically at plan time.

    On page-leave, ``collect_rules_picks()`` collapses checked rows into
    ``Selection.leaf_item_picks[ADHOC_COMPOUND_RULES]``:
      - whole block ON, nothing trimmed  => key ABSENT (SC-004)
      - whole block OFF                  => empty frozenset (SC-005)
      - individual trim                  => full set minus deselected GUIDs
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Step 8 of 9: Rules")
        self.setSubTitle(
            "Review the source project's ad hoc and compound rules. "
            "All rules are preselected. "
            "Untick the block to skip rules, or deselect individual rules. "
            "Status column shows whether each rule exists in the target."
        )
        self._inventory = None   # RulesInventory | None
        self._mirroring: bool = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        self._whole_block = QtWidgets.QCheckBox("Transfer rules block", self)
        self._whole_block.setTristate(True)
        self._whole_block.clicked.connect(self._on_whole_block_clicked)
        layout.addWidget(self._whole_block)

        self._tree = QtWidgets.QTreeWidget(self)
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["Rule", "Target"])
        self._tree.header().setStretchLastSection(True)
        self._tree.setAlternatingRowColors(True)
        layout.addWidget(self._tree, 1)

    # ------------------------------------------------------------------
    def initializePage(self) -> None:
        """Build the inventory from source+target; ALL rows preselected."""
        if self._tree.receivers(self._tree.itemChanged) > 0:
            self._tree.itemChanged.disconnect(self._on_item_changed)
        self._tree.clear()
        self._inventory = None

        source = self._get_source()
        if source is None:
            empty = QtWidgets.QTreeWidgetItem(
                self._tree, ["(No source project bound)", ""]
            )
            empty.setFlags(empty.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled)
            self._refresh_whole_block()
            return

        target = self._get_target()
        try:
            inventory = build_rules_inventory(source, target=target)
        except Exception:  # noqa: BLE001
            inventory = None

        if inventory is None:
            self._refresh_whole_block()
            return

        self._inventory = inventory
        self._populate_tree(inventory)
        self._tree.expandAll()
        for col in range(2):
            self._tree.resizeColumnToContents(col)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._refresh_whole_block()

    def _populate_tree(self, inventory) -> None:
        """One tristate group per category (count on header); item rows checked."""
        for group in (inventory.adhoc, inventory.compound):
            header = QtWidgets.QTreeWidgetItem(
                self._tree,
                [f"{group.category_label} ({group.count})", ""]
            )
            header.setData(0, _RULES_KIND_ROLE, "group")
            header.setFlags(
                header.flags()
                | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                | QtCore.Qt.ItemFlag.ItemIsAutoTristate
            )
            header.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
            bold = header.font(0)
            bold.setBold(True)
            header.setFont(0, bold)

            if not group.rows:
                # FR-011: empty category renders as empty, not an error
                none_item = QtWidgets.QTreeWidgetItem(header, ["(none)", ""])
                none_item.setFlags(
                    none_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled
                )
                continue

            for row in group.rows:
                status_text = _RULES_STATUS_LABELS.get(row.target_status, row.target_status)
                item = QtWidgets.QTreeWidgetItem(
                    header, [row.label, status_text]
                )
                item.setData(0, _RULES_GUID_ROLE, row.guid)
                item.setData(0, _RULES_KIND_ROLE, "item")
                item.setData(0, _RULES_STATUS_ROLE, row.target_status)
                item.setFlags(
                    item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                )
                cs = (QtCore.Qt.CheckState.Checked if row.checked
                      else QtCore.Qt.CheckState.Unchecked)
                item.setCheckState(0, cs)

    # -- whole-block toggle ------------------------------------------------
    def _on_whole_block_clicked(self, _checked: bool = False) -> None:
        """User toggled the whole-block checkbox: check-all or uncheck-all."""
        if not self._has_any_item():
            self._refresh_whole_block()
            return
        want_checked = not self._all_items_checked()
        self._set_all_items(want_checked)
        self._refresh_whole_block()

    def _set_all_items(self, checked: bool) -> None:
        state = (QtCore.Qt.CheckState.Checked if checked
                 else QtCore.Qt.CheckState.Unchecked)
        self._mirroring = True
        try:
            for _g, item in self._iter_item_rows():
                item.setCheckState(0, state)
        finally:
            self._mirroring = False

    def _refresh_whole_block(self) -> None:
        """Reflect aggregate item state on the whole-block tristate box.

        Empty block => unchecked + disabled (NOT vacuously fully-selected,
        per edge-case invariant — mirrors _PagePhonology / _PageCustomFields).
        """
        self._mirroring = True
        try:
            if not self._has_any_item():
                self._whole_block.setEnabled(False)
                self._whole_block.setCheckState(QtCore.Qt.CheckState.Unchecked)
                return
            self._whole_block.setEnabled(True)
            checked = sum(
                1 for _g, it in self._iter_item_rows()
                if it.checkState(0) == QtCore.Qt.CheckState.Checked
            )
            total = sum(1 for _ in self._iter_item_rows())
            if checked == 0:
                self._whole_block.setCheckState(QtCore.Qt.CheckState.Unchecked)
            elif checked == total:
                self._whole_block.setCheckState(QtCore.Qt.CheckState.Checked)
            else:
                self._whole_block.setCheckState(
                    QtCore.Qt.CheckState.PartiallyChecked
                )
        finally:
            self._mirroring = False

    def _on_item_changed(self, item, column) -> None:
        if self._mirroring or column != 0:
            return
        self._refresh_whole_block()

    # -- tree walking helpers ----------------------------------------------
    def _iter_item_rows(self):
        """Yield (group_item, item) for every checkable rule item row."""
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            if group.data(0, _RULES_KIND_ROLE) != "group":
                continue
            for j in range(group.childCount()):
                item = group.child(j)
                if item.data(0, _RULES_KIND_ROLE) == "item":
                    yield group, item

    def _has_any_item(self) -> bool:
        for _ in self._iter_item_rows():
            return True
        return False

    def _all_items_checked(self) -> bool:
        any_item = False
        for _g, item in self._iter_item_rows():
            any_item = True
            if item.checkState(0) != QtCore.Qt.CheckState.Checked:
                return False
        return any_item

    def whole_block_on(self) -> bool:
        """True iff any item row is currently checked."""
        for _g, item in self._iter_item_rows():
            if item.checkState(0) == QtCore.Qt.CheckState.Checked:
                return True
        return False

    # -- state API (T019) --------------------------------------------------
    def collect_rules_picks(self) -> Optional[frozenset]:
        """Return checked GUIDs as a frozenset, or None for 'transfer all'.

        None  => key absent from leaf_item_picks (SC-004 untouched default).
        frozenset() => whole block OFF, transfer nothing (SC-005).
        frozenset({...}) => individual trim — full set minus deselected.

        Grouping node semantics: a group node is included iff >=1 child is
        kept; deselected children are excluded (data-model.md edge case).
        """
        if self._inventory is None:
            return None

        all_item_guids = frozenset(
            item.data(0, _RULES_GUID_ROLE)
            for _g, item in self._iter_item_rows()
            if item.data(0, _RULES_GUID_ROLE)
        )
        checked_guids = frozenset(
            item.data(0, _RULES_GUID_ROLE)
            for _g, item in self._iter_item_rows()
            if item.checkState(0) == QtCore.Qt.CheckState.Checked
            and item.data(0, _RULES_GUID_ROLE)
        )

        # Whole block OFF => empty frozenset
        if not checked_guids:
            return frozenset()

        # All rows checked => key absent (SC-004 / data-model "untouched" case)
        if checked_guids == all_item_guids:
            return None

        # Individual trim
        return checked_guids

    def inventory(self):
        """Return the current RulesInventory (may be None before initializePage)."""
        return self._inventory

    # ------------------------------------------------------------------
    def _get_source(self):
        try:
            w = self.wizard()
            if w is None:
                return None
            p0 = w.page_project_ws()
            if p0 is None:
                return None
            ctx = p0.context()
            if ctx is not None:
                h = getattr(ctx, "source_handle", None)
                if h is not None:
                    return h
            return getattr(p0, "_host", None)
        except Exception:  # noqa: BLE001
            return None

    def _get_target(self):
        try:
            w = self.wizard()
            if w is None:
                return None
            p0 = w.page_project_ws()
            if p0 is None:
                return None
            ctx = p0.context()
            if ctx is None:
                return None
            return getattr(ctx, "target_handle", None)
        except Exception:  # noqa: BLE001
            return None


class _PagePhonology(QtWidgets.QWizardPage):
    """Page 2: Phonology block (spec 010 — the first Model-B selector).

    A grouped tree of the five user-facing phonology categories (features,
    phonemes, natural classes, environments, rules), each with a count on its
    header, ALL rows preselected. The user may toggle the whole block off, trim
    a whole category, or deselect individual items; trimmed categories emit a
    ``leaf_item_picks`` subset at collapse time (fully-checked categories omit
    the key ⇒ transfer-all).

    Strata are NEVER a user row (FR-009) — they travel automatically iff a rule
    is kept, decided in ``collapse_phonology``.

    Deliberately renders NO ADD_NEW/LINK/UPDATE/OVERWRITE conflict-mode control
    (FR-012 / SC-008); Layer-1 default conflict modes are applied automatically
    when the Preview page builds the Selection.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Step 3 of 9: Phonology")
        self.setSubTitle(
            "Review the source's phonology. The whole block is preselected. "
            "Untick the block to skip phonology, untick a category to trim it, "
            "or deselect individual items. Strata travel automatically with any "
            "kept phonological rule."
        )
        self._inventory: Optional[object] = None  # PhonologyInventory
        self._mirroring: bool = False
        # T012: preview service (initialized in initializePage)
        self._preview_service = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        self._whole_block = QtWidgets.QCheckBox(
            "Transfer phonology block", self
        )
        self._whole_block.setTristate(True)
        # `clicked` fires on user action only (not on programmatic setCheckState),
        # so the aggregate refresh below never re-enters through it.
        self._whole_block.clicked.connect(self._on_whole_block_clicked)
        layout.addWidget(self._whole_block)

        self._tree = QtWidgets.QTreeWidget(self)
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["Item", "Target"])
        self._tree.header().setStretchLastSection(True)
        self._tree.setAlternatingRowColors(True)
        # T012: merge-preview pane docked to the right (FR-005)
        self._pane = MergePreviewPane(self)
        splitter = _make_tree_pane_splitter(self._tree, self._pane)
        layout.addWidget(splitter, 1)

    # ------------------------------------------------------------------
    def initializePage(self) -> None:
        """Build the inventory from the bound source+target; ALL preselected."""
        if self._tree.receivers(self._tree.itemChanged) > 0:
            self._tree.itemChanged.disconnect(self._on_item_changed)
        self._tree.clear()
        self._inventory = None

        source = self._get_source()
        if source is None:
            empty = QtWidgets.QTreeWidgetItem(
                self._tree, ["(No source project bound)", ""]
            )
            empty.setFlags(empty.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled)
            self._refresh_whole_block()
            return

        target = self._get_target()
        try:
            inventory = build_phonology_inventory(source, target=target)
        except Exception:  # noqa: BLE001
            inventory = None

        if inventory is None:
            self._refresh_whole_block()
            return

        self._inventory = inventory
        # spec 011: render each item in its FLEx-defined WS font (phoneme
        # grapheme in the vernacular font, /IPA/ in the IPA font, etc.).
        attach_ws_font_delegate(
            self._tree, [0], WsFontRegistry.from_project(source)
        )
        self._populate_tree(inventory)
        self._tree.expandAll()
        for col in range(2):
            self._tree.resizeColumnToContents(col)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._refresh_whole_block()

        # T012: construct service and set pane context (FR-006)
        self._preview_service = MergePreviewService(source, target)
        self._pane.set_context(
            self._preview_service,
            WsFontRegistry.from_project(source),
            [],  # no candidates for phonology
        )
        self._pane.clear()
        # Double-connect guard (existing pattern preserved)
        if self._tree.receivers(self._tree.currentItemChanged) == 0:
            self._tree.currentItemChanged.connect(self._on_tree_selection_changed)

    def _populate_tree(self, inventory) -> None:
        """One tristate group per category (count on header); item rows checked."""
        from PyQt6 import QtGui  # noqa: F401  (font bolding, mirrors sibling pages)
        for group in inventory.groups:
            header = QtWidgets.QTreeWidgetItem(
                self._tree, [f"{group.label} ({group.count})", ""]
            )
            header.setData(0, _PHON_KIND_ROLE, "group")
            header.setData(0, _PHON_CAT_ROLE, group.category)
            header.setFlags(
                header.flags()
                | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                | QtCore.Qt.ItemFlag.ItemIsAutoTristate
            )
            header.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
            bold = header.font(0)
            bold.setBold(True)
            header.setFont(0, bold)

            if not group.rows:
                none_item = QtWidgets.QTreeWidgetItem(header, ["(none)", ""])
                none_item.setFlags(
                    none_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled
                )
                continue

            for row in group.rows:
                item = QtWidgets.QTreeWidgetItem(
                    header,
                    [row.label, _STATUS_LABELS.get(row.status or "", "")]
                )
                set_ws_runs(item, 0, row.runs)
                item.setData(0, _PHON_GUID_ROLE, row.guid)
                item.setData(0, _PHON_KIND_ROLE, "item")
                item.setData(0, _PHON_CAT_ROLE, row.category)
                # T008: status role for pane PreviewRequest construction (FR-010, R6)
                item.setData(0, _PHON_STATUS_ROLE, row.status or "")
                item.setFlags(
                    item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                )
                cs = (QtCore.Qt.CheckState.Checked if row.preselected
                      else QtCore.Qt.CheckState.Unchecked)
                item.setCheckState(0, cs)

    # T012: tree selection handler (display-only, R8)
    def _on_tree_selection_changed(self, current, previous) -> None:
        """Build PreviewRequest from selected phonology row (display-only, R8).

        Phonology rows never show the resolution header (resolvable=False).
        SIMILAR phonology rows use the overwrite diff mode for compare display.
        Mode strings come from merge_preview constants imported at module level;
        the string form is used here to avoid ConflictMode references (SC-008).
        """
        if current is None:
            self._pane.clear()
            return
        kind = current.data(0, _PHON_KIND_ROLE)
        if kind == "group":
            self._pane.clear()
            return

        source_guid = current.data(0, _PHON_GUID_ROLE) or ""
        category = current.data(0, _PHON_CAT_ROLE)
        status = current.data(0, _PHON_STATUS_ROLE) or ""

        # R8: all phonology rows use resolvable=False.
        # SIMILAR -> compare diff (overwrite diff mode); NEW -> all-green (new mode).
        # Use module-level aliases _PHON_MODE_OVERWRITE / _PHON_MODE_NEW (SC-008).
        if status == "similar":
            # matched_target_guid: 011 stores the match target in _PHON_GUID_ROLE
            # for SIMILAR rows when available; fall back to source_guid.
            matched_target_guid = getattr(
                self, "_phon_similar_target", {}
            ).get(source_guid, source_guid)
            target_guid = matched_target_guid
            mode = _PHON_MODE_OVERWRITE
        elif status == "new":
            target_guid = ""
            mode = _PHON_MODE_NEW
        else:  # "in_target"
            target_guid = source_guid
            mode = _PHON_MODE_OVERWRITE

        cat_str = category.value if category is not None else GrammarCategory.PHONEMES.value
        request = PreviewRequest(
            category=cat_str,
            source_guid=source_guid,
            target_guid=target_guid,
            status=status,
            mode=mode,
            resolvable=False,
            current_resolution=None,
            owner_guid="",
        )
        self._pane.show_item(request)

    # -- whole-block toggle (T017) -------------------------------------
    def _on_whole_block_clicked(self, _checked: bool = False) -> None:
        """User toggled the whole-block checkbox: check-all or uncheck-all.

        Ignores Qt's cycled tristate state and decides from the tree so the
        behaviour is deterministic (partial ⇒ check-all, full ⇒ uncheck-all).
        """
        if not self._has_any_item():
            self._refresh_whole_block()
            return
        want_checked = not self._all_items_checked()
        self._set_all_items(want_checked)
        self._refresh_whole_block()

    def _set_all_items(self, checked: bool) -> None:
        state = (QtCore.Qt.CheckState.Checked if checked
                 else QtCore.Qt.CheckState.Unchecked)
        self._mirroring = True
        try:
            for group, item in self._iter_item_rows():
                item.setCheckState(0, state)
        finally:
            self._mirroring = False

    def _refresh_whole_block(self) -> None:
        """Reflect the aggregate item state on the whole-block tristate box.

        Empty block (no items at all) ⇒ unchecked + disabled (NOT vacuously
        fully-selected, per the edge-case invariant in the contract).
        """
        self._mirroring = True
        try:
            if not self._has_any_item():
                self._whole_block.setEnabled(False)
                self._whole_block.setCheckState(QtCore.Qt.CheckState.Unchecked)
                return
            self._whole_block.setEnabled(True)
            checked = sum(
                1 for _g, it in self._iter_item_rows()
                if it.checkState(0) == QtCore.Qt.CheckState.Checked
            )
            total = sum(1 for _ in self._iter_item_rows())
            if checked == 0:
                self._whole_block.setCheckState(QtCore.Qt.CheckState.Unchecked)
            elif checked == total:
                self._whole_block.setCheckState(QtCore.Qt.CheckState.Checked)
            else:
                self._whole_block.setCheckState(
                    QtCore.Qt.CheckState.PartiallyChecked
                )
        finally:
            self._mirroring = False

    def _on_item_changed(self, item, column) -> None:
        if self._mirroring or column != 0:
            return
        self._refresh_whole_block()

    # -- tree walking helpers ------------------------------------------
    def _iter_item_rows(self):
        """Yield (group_item, item) for every checkable phonology item row."""
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            if group.data(0, _PHON_KIND_ROLE) != "group":
                continue
            for j in range(group.childCount()):
                item = group.child(j)
                if item.data(0, _PHON_KIND_ROLE) == "item":
                    yield group, item

    def _has_any_item(self) -> bool:
        for _ in self._iter_item_rows():
            return True
        return False

    def _all_items_checked(self) -> bool:
        any_item = False
        for _g, item in self._iter_item_rows():
            any_item = True
            if item.checkState(0) != QtCore.Qt.CheckState.Checked:
                return False
        return any_item

    # -- state API (contract §Page state) ------------------------------
    def collect_phonology_picks(self) -> dict:
        """Return {GrammarCategory: set[str] checked guids} for the 5 categories."""
        picks: dict = {}
        for group, item in self._iter_item_rows():
            if item.checkState(0) != QtCore.Qt.CheckState.Checked:
                continue
            cat = item.data(0, _PHON_CAT_ROLE)
            guid = item.data(0, _PHON_GUID_ROLE)
            if cat is None or not guid:
                continue
            picks.setdefault(cat, set()).add(guid)
        return picks

    def whole_block_on(self) -> bool:
        """True iff any category has >=1 checked row."""
        for _g, item in self._iter_item_rows():
            if item.checkState(0) == QtCore.Qt.CheckState.Checked:
                return True
        return False

    def deselected_needed_guids(self) -> frozenset:
        """Preselected-but-unchecked guids (input to EXCLUDED-LOSSY, T024)."""
        out = set()
        for _g, item in self._iter_item_rows():
            if item.checkState(0) != QtCore.Qt.CheckState.Checked:
                guid = item.data(0, _PHON_GUID_ROLE)
                if guid:
                    out.add(guid)
        return frozenset(out)

    def inventory(self):
        return self._inventory

    # ------------------------------------------------------------------
    def _get_source(self):
        try:
            w = self.wizard()
            if w is None:
                return None
            p0 = w.page_project_ws()
            if p0 is None:
                return None
            ctx = p0.context()
            if ctx is not None:
                h = getattr(ctx, "source_handle", None)
                if h is not None:
                    return h
            return getattr(p0, "_host", None)
        except Exception:  # noqa: BLE001
            return None

    def _get_target(self):
        try:
            w = self.wizard()
            if w is None:
                return None
            p0 = w.page_project_ws()
            if p0 is None:
                return None
            ctx = p0.context()
            if ctx is None:
                return None
            return getattr(ctx, "target_handle", None)
        except Exception:  # noqa: BLE001
            return None


# ---------------------------------------------------------------------------
# Shared phonology EXCLUDED-LOSSY channel (spec 010 US5 — T024/T025/T026b)
# ---------------------------------------------------------------------------

def _phonology_nc_or_phoneme_trimmed(inventory, checked_by_category) -> bool:
    """True iff the user deselected any NC or phoneme (KL-010-1 guard input)."""
    for cat in (GrammarCategory.NATURAL_CLASSES, GrammarCategory.PHONEMES):
        grp = inventory.group_for(cat)
        if grp is None:
            continue
        all_guids = {r.guid for r in grp.rows}
        if all_guids - set(checked_by_category.get(cat, set())):
            return True
    return False


def _kl010_notice(inventory, checked_rule_guids) -> ExcludedLossy:
    """Coarse Principle-V notice for a kept metathesis/reduplication rule.

    The reference traversal does not follow metathesis/reduplication part
    sequences (KL-010-1), so a trim MIGHT strand a reference we cannot see.
    Surface one honest notice into the shared Move gate rather than transfer
    silently. Attributed to the first such kept rule.
    """
    rule_guids = sorted(inventory.untraversed_rule_guids & set(checked_rule_guids))
    rg = rule_guids[0] if rule_guids else "?"
    label = rg[:8]
    grp = inventory.group_for(GrammarCategory.PHONOLOGICAL_RULES)
    if grp is not None:
        for r in grp.rows:
            if r.guid == rg:
                label = r.label
                break
    return ExcludedLossy(
        category=GrammarCategory.PHONOLOGICAL_RULES,
        entry_guid=rg or "?",
        entry_label=label,
        dep_category=GrammarCategory.PHONOLOGICAL_RULES,
        dep_guid=rg or "?",
        dep_label=label,
        message=(
            f"Reference check is not supported for rule '{label}' "
            "(metathesis/reduplication); trimming phonemes or natural classes "
            "may strand references not verified here (KL-010-1)."
        ),
    )


def _phonology_excluded_lossy_for(wizard) -> list:
    """Intra-phonology EXCLUDED-LOSSY warnings for the current page state.

    Shared by Preview (StatsPanel channel, T025) and Finish (Move gate, T024)
    so both agree on the entry-centric count. Returns a list of ExcludedLossy;
    empty when there is no phonology page / inventory. Appends the coarse
    KL-010-1 notice (T026b) when a kept metathesis/reduplication rule coincides
    with an NC/phoneme trim.
    """
    phon_page = (wizard.page_phonology()
                 if hasattr(wizard, "page_phonology") else None)
    if phon_page is None or phon_page.inventory() is None:
        return []
    inventory = phon_page.inventory()
    checked = phon_page.collect_phonology_picks()

    # Target GUIDs per category drive the absent-from-target test. Reuse the
    # builder against the target handle (read-only) rather than re-deriving.
    target = None
    try:
        p0 = wizard.page_project_ws()
        ctx = p0.context() if p0 is not None else None
        target = getattr(ctx, "target_handle", None) if ctx is not None else None
    except Exception:  # noqa: BLE001
        target = None
    tgt_by_cat: dict = {}
    if target is not None:
        try:
            tinv = build_phonology_inventory(target)
            tgt_by_cat = {g.category: {r.guid for r in g.rows}
                          for g in tinv.groups}
        except Exception:  # noqa: BLE001
            tgt_by_cat = {}

    warnings = list(build_phonology_excluded_lossy(inventory, checked, tgt_by_cat))

    checked_rules = checked.get(GrammarCategory.PHONOLOGICAL_RULES, set())
    if (phonology_uses_untraversed_rules(inventory, checked_rules)
            and _phonology_nc_or_phoneme_trimmed(inventory, checked)):
        warnings.append(_kl010_notice(inventory, checked_rules))
    return warnings


# ---------------------------------------------------------------------------
# Page 7 -- Lexical-Entry Types (spec 021, Model-B independent block)
# ---------------------------------------------------------------------------

# Data roles for _PageEntryTypes
_ET_GUID_ROLE   = QtCore.Qt.ItemDataRole.UserRole + 70  # source GUID (item rows)
_ET_KIND_ROLE   = QtCore.Qt.ItemDataRole.UserRole + 71  # "group" | "item"
_ET_CAT_ROLE    = QtCore.Qt.ItemDataRole.UserRole + 72  # GrammarCategory
_ET_STATUS_ROLE = QtCore.Qt.ItemDataRole.UserRole + 73  # "new" | "in_target" | ""

# SC-008: module-level mode aliases used inside _PageEntryTypes (no ConflictMode refs).
_ET_MODE_OVERWRITE = OVERWRITE
_ET_MODE_NEW = NEW


class _PageEntryTypes(QtWidgets.QWizardPage):
    """Page 7: Lexical-Entry Types block (spec 021 -- the second Model-B selector).

    A grouped tree of two entry-type categories (Variant Types, Complex Form Types),
    each with a count on its header, ALL user-defined rows preselected.  The user may
    toggle the whole block off, trim a whole category, or deselect individual types.
    Trimmed categories emit a ``leaf_item_picks`` subset at collapse time (fully-
    checked categories omit the key => transfer-all).

    Hierarchy: sub-types (SubPossibilitiesOS children) appear as nested tree children
    under their parent item.

    GOLD types are shown as IN TARGET (cross-referencing device per spec 021 FR-009
    clarification; the engine's plan_action will Skip(GOLD_INVIOLABLE) at Move time).

    Deliberately renders NO ADD_NEW/MERGE/OVERWRITE conflict-mode control
    (FR-012 / SC-008); Layer-1 default conflict modes are applied automatically when
    the Preview page builds the Selection.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Step 7 of 9: Lexical-Entry Types")
        self.setSubTitle(
            "Review the source's lexical-entry types (variant types and complex form "
            "types). The whole block is preselected. Untick the block to skip, untick "
            "a category to trim it, or deselect individual types."
        )
        self._inventory: Optional[object] = None  # EntryTypesInventory
        self._mirroring: bool = False
        self._preview_service = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        self._whole_block = QtWidgets.QCheckBox(
            "Transfer lexical-entry types block", self
        )
        self._whole_block.setTristate(True)
        self._whole_block.clicked.connect(self._on_whole_block_clicked)
        layout.addWidget(self._whole_block)

        self._tree = QtWidgets.QTreeWidget(self)
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["Item", "Target"])
        self._tree.header().setStretchLastSection(True)
        self._tree.setAlternatingRowColors(True)
        self._pane = MergePreviewPane(self)
        splitter = _make_tree_pane_splitter(self._tree, self._pane)
        layout.addWidget(splitter, 1)

    # ------------------------------------------------------------------
    def initializePage(self) -> None:
        """Build the inventory from the bound source+target; ALL preselected."""
        if self._tree.receivers(self._tree.itemChanged) > 0:
            self._tree.itemChanged.disconnect(self._on_item_changed)
        self._tree.clear()
        self._inventory = None

        source = self._get_source()
        if source is None:
            empty = QtWidgets.QTreeWidgetItem(
                self._tree, ["(No source project bound)", ""]
            )
            empty.setFlags(empty.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled)
            self._refresh_whole_block()
            return

        target = self._get_target()
        try:
            inventory = build_entry_types_inventory(source, target=target)
        except Exception:  # noqa: BLE001
            inventory = None

        if inventory is None:
            self._refresh_whole_block()
            return

        self._inventory = inventory
        attach_ws_font_delegate(
            self._tree, [0], WsFontRegistry.from_project(source)
        )
        self._populate_tree(inventory)
        self._tree.expandAll()
        for col in range(2):
            self._tree.resizeColumnToContents(col)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._refresh_whole_block()

        self._preview_service = MergePreviewService(source, target)
        self._pane.set_context(
            self._preview_service,
            WsFontRegistry.from_project(source),
            [],  # no candidates for entry types
        )
        self._pane.clear()
        if self._tree.receivers(self._tree.currentItemChanged) == 0:
            self._tree.currentItemChanged.connect(self._on_tree_selection_changed)

    def _populate_tree(self, inventory) -> None:
        """One tristate group per category (count on header); item rows checked."""
        from PyQt6 import QtGui  # noqa: F401
        for group in inventory.groups:
            header = QtWidgets.QTreeWidgetItem(
                self._tree, [f"{group.label} ({group.count})", ""]
            )
            header.setData(0, _ET_KIND_ROLE, "group")
            header.setData(0, _ET_CAT_ROLE, group.category)
            header.setFlags(
                header.flags()
                | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                | QtCore.Qt.ItemFlag.ItemIsAutoTristate
            )
            header.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
            bold = header.font(0)
            bold.setBold(True)
            header.setFont(0, bold)

            if not group.rows:
                none_item = QtWidgets.QTreeWidgetItem(header, ["(none)", ""])
                none_item.setFlags(
                    none_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled
                )
                continue

            # Build tree hierarchy: maintain a stack of (depth, tree_item).
            # Rows are in depth-first order from _walk_entry_type_nodes so a
            # depth increase always means the row is a child of the preceding.
            parent_stack = [(- 1, header)]  # sentinel (-1 depth, group header)
            for row in group.rows:
                # Find the appropriate parent: the nearest ancestor whose depth < row.depth
                while len(parent_stack) > 1 and parent_stack[-1][0] >= row.depth:
                    parent_stack.pop()
                tree_parent = parent_stack[-1][1]

                item = QtWidgets.QTreeWidgetItem(
                    tree_parent,
                    [row.label, _STATUS_LABELS.get(row.status or "", "")]
                )
                set_ws_runs(item, 0, row.runs)
                item.setData(0, _ET_GUID_ROLE, row.guid)
                item.setData(0, _ET_KIND_ROLE, "item")
                item.setData(0, _ET_CAT_ROLE, row.category)
                item.setData(0, _ET_STATUS_ROLE, row.status or "")
                item.setFlags(
                    item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                )
                cs = (QtCore.Qt.CheckState.Checked if row.preselected
                      else QtCore.Qt.CheckState.Unchecked)
                item.setCheckState(0, cs)
                parent_stack.append((row.depth, item))

    def _on_tree_selection_changed(self, current, previous) -> None:
        """Build PreviewRequest from selected entry-type row (display-only)."""
        if current is None:
            self._pane.clear()
            return
        kind = current.data(0, _ET_KIND_ROLE)
        if kind == "group":
            self._pane.clear()
            return

        source_guid = current.data(0, _ET_GUID_ROLE) or ""
        category = current.data(0, _ET_CAT_ROLE)
        status = current.data(0, _ET_STATUS_ROLE) or ""

        if status == "in_target":
            target_guid = source_guid
            mode = _ET_MODE_OVERWRITE
        else:
            target_guid = ""
            mode = _ET_MODE_NEW

        cat_str = (category.value if category is not None
                   else GrammarCategory.VARIANT_TYPES.value)
        request = PreviewRequest(
            category=cat_str,
            source_guid=source_guid,
            target_guid=target_guid,
            status=status,
            mode=mode,
            resolvable=False,
            current_resolution=None,
            owner_guid="",
        )
        self._pane.show_item(request)

    # -- whole-block toggle (mirrors _PagePhonology) ------------------
    def _on_whole_block_clicked(self, _checked: bool = False) -> None:
        if not self._has_any_item():
            self._refresh_whole_block()
            return
        want_checked = not self._all_items_checked()
        self._set_all_items(want_checked)
        self._refresh_whole_block()

    def _set_all_items(self, checked: bool) -> None:
        state = (QtCore.Qt.CheckState.Checked if checked
                 else QtCore.Qt.CheckState.Unchecked)
        self._mirroring = True
        try:
            for _g, item in self._iter_item_rows():
                item.setCheckState(0, state)
        finally:
            self._mirroring = False

    def _refresh_whole_block(self) -> None:
        """Reflect the aggregate item state on the whole-block tristate box.

        Empty block (no items) => unchecked + disabled (NOT vacuously checked).
        """
        self._mirroring = True
        try:
            if not self._has_any_item():
                self._whole_block.setEnabled(False)
                self._whole_block.setCheckState(QtCore.Qt.CheckState.Unchecked)
                return
            self._whole_block.setEnabled(True)
            checked = sum(
                1 for _g, it in self._iter_item_rows()
                if it.checkState(0) == QtCore.Qt.CheckState.Checked
            )
            total = sum(1 for _ in self._iter_item_rows())
            if checked == 0:
                self._whole_block.setCheckState(QtCore.Qt.CheckState.Unchecked)
            elif checked == total:
                self._whole_block.setCheckState(QtCore.Qt.CheckState.Checked)
            else:
                self._whole_block.setCheckState(
                    QtCore.Qt.CheckState.PartiallyChecked
                )
        finally:
            self._mirroring = False

    def _on_item_changed(self, item, column) -> None:
        if self._mirroring or column != 0:
            return
        self._refresh_whole_block()

    # -- tree walking helpers ------------------------------------------
    def _iter_item_rows(self):
        """Yield (group_item, item) for every checkable entry-type item row.

        Walks the full tree depth (groups -> items -> sub-items) so that
        nested child types are included in the whole-block count.
        """
        root = self._tree.invisibleRootItem()

        def _walk(parent, in_group_item):
            for i in range(parent.childCount()):
                child = parent.child(i)
                kind = child.data(0, _ET_KIND_ROLE)
                if kind == "group":
                    # Recurse into group header's children
                    _walk(child, False)
                elif kind == "item":
                    if in_group_item or True:  # always yield items
                        yield (parent, child)
                    # Also walk children of this item (sub-types)
                    for j in range(child.childCount()):
                        grandchild = child.child(j)
                        if grandchild.data(0, _ET_KIND_ROLE) == "item":
                            yield (child, grandchild)

        for i in range(root.childCount()):
            group = root.child(i)
            if group.data(0, _ET_KIND_ROLE) != "group":
                continue
            for pair in _walk(group, False):
                yield pair

    def _has_any_item(self) -> bool:
        for _ in self._iter_item_rows():
            return True
        return False

    def _all_items_checked(self) -> bool:
        any_item = False
        for _g, item in self._iter_item_rows():
            any_item = True
            if item.checkState(0) != QtCore.Qt.CheckState.Checked:
                return False
        return any_item

    # -- state API -----------------------------------------------------
    def collect_entry_type_picks(self) -> dict:
        """Return {GrammarCategory: set[str checked guids]} for both categories."""
        picks: dict = {}
        for _g, item in self._iter_item_rows():
            if item.checkState(0) != QtCore.Qt.CheckState.Checked:
                continue
            cat = item.data(0, _ET_CAT_ROLE)
            guid = item.data(0, _ET_GUID_ROLE)
            if cat is None or not guid:
                continue
            picks.setdefault(cat, set()).add(guid)
        return picks

    def whole_block_on(self) -> bool:
        """True iff any category has >= 1 checked row."""
        for _g, item in self._iter_item_rows():
            if item.checkState(0) == QtCore.Qt.CheckState.Checked:
                return True
        return False

    def deselected_needed_guids(self) -> frozenset:
        """Preselected-but-unchecked guids (input to missing-ref warning)."""
        out = set()
        for _g, item in self._iter_item_rows():
            if item.checkState(0) != QtCore.Qt.CheckState.Checked:
                guid = item.data(0, _ET_GUID_ROLE)
                if guid:
                    out.add(guid)
        return frozenset(out)

    def inventory(self):
        return self._inventory

    # -- source/target accessors (mirror _PagePhonology pattern) ------
    def _get_source(self):
        wizard = self.wizard()
        if wizard is None:
            return None
        return getattr(wizard, "_host", None)

    def _get_target(self):
        wizard = self.wizard()
        if wizard is None:
            return None
        page0 = wizard.page_project_ws() if hasattr(wizard, "page_project_ws") else None
        if page0 is None:
            return None
        ctx = page0.context() if hasattr(page0, "context") else None
        if ctx is None:
            return None
        return getattr(ctx, "target_handle", None)


def _entry_types_missing_ref_for(wizard) -> list:
    """Entry-types inflection-feature missing-ref warnings for the current page state.

    Shared by Finish (Move gate) so the count is aggregated into the single
    consolidated dialog (FR-011). Returns a list of warning dicts; empty when
    there is no entry-types page / inventory.
    """
    et_page = (wizard.page_entry_types()
               if hasattr(wizard, "page_entry_types") else None)
    if et_page is None or et_page.inventory() is None:
        return []
    inventory = et_page.inventory()
    checked = et_page.collect_entry_type_picks()
    target = et_page._get_target()
    return entry_types_missing_ref_warnings(inventory, checked, target=target)


# ---------------------------------------------------------------------------
# Page 4 -- Preview
# ---------------------------------------------------------------------------

class _PagePreview(QtWidgets.QWizardPage):
    """Page 4: Preview / StatsPanel.

    Re-hosts the existing StatsPanel widget verbatim.  Preview is triggered
    when the page is entered; the plan is cached for use on page 5.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Preview (inactive)")
        self.setSubTitle(
            "Review the planned transfer before committing. "
            "Warnings (entries with missing references) are highlighted."
        )
        self._cached_plan = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        self._preview_btn = QtWidgets.QPushButton("Compute Preview", self)
        self._preview_btn.clicked.connect(self._on_preview)
        layout.addWidget(self._preview_btn)
        self._stats = StatsPanel(self)
        layout.addWidget(self._stats, 1)

    def _on_preview(self) -> None:
        """Thin wrapper delegating to _compute_wizard_plan (DR-5, FR-005)."""
        wizard = self.wizard()
        if wizard is None:
            return
        plan, report = _compute_wizard_plan(wizard)
        if plan is None:
            # DR-5: wrapper owns QMessageBox dialogs.
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

    def cached_plan(self):
        return self._cached_plan

    def isComplete(self) -> bool:
        return self._cached_plan is not None


# ---------------------------------------------------------------------------
# Module-level plan assembler (DR-4, FR-004)
# ---------------------------------------------------------------------------

def _compute_wizard_plan(wizard) -> tuple:
    """Assemble the transfer plan from all wizard page selections.

    Returns (plan, report) on success, (None, None) on any failure.
    Does not display QMessageBox -- callers own all UI dialogs (DR-5).

    DR-4 step order:
    1. Context None-guard.
    2. affix_selection = page_items.collect_selection().
    3. build_selection + _replace_conflict_modes.
    4. dataclasses.replace stamp with similar_resolutions (single call -- SC-005).
    5. similar_resolutions stamp BEFORE phonology merge block (P1 ordering).
    6. ws_mapping from page0.
    7. gt_api.compute_preview; return (None, None) on payload-None or failure.
    8. RunReport.build_from_plan; return (payload, report).
    """
    # Step 1: context None-guard (no QMessageBox here -- caller owns dialogs).
    context = wizard.page_project_ws().context()
    if context is None:
        return (None, None)

    # Step 2: affix selection (single collect_selection call -- SC-005).
    page_items = wizard.page_items()
    affix_selection = page_items.collect_selection()

    # Step 3: build selection + apply Layer-1 conflict-mode defaults.
    selection = build_selection(
        PickerState(
            checked_affixes=affix_selection.affix_picks,
            checked_templates=affix_selection.template_picks,
        ),
        SourceAffixInventory(
            unbound_affixes=affix_selection.affix_picks,
            template_to_slots={t: () for t in affix_selection.template_picks},
        ),
        category_scopes={},
    )._replace_conflict_modes(dict(_DEFAULT_CONFLICT_MODES))

    # Step 4: stamp similar_resolutions BEFORE phonology merge (DR-4 step 5, P1).
    # Uses the already-collected affix_selection -- no second collect_selection call.
    selection = dataclasses.replace(
        selection,
        similar_resolutions=affix_selection.similar_resolutions,
    )

    # Step 5a: custom-fields merge (US2/T014 -- fold leaf_item_picks into selection).
    cf_page = wizard.page_custom_fields() if hasattr(wizard, "page_custom_fields") else None
    if cf_page is not None:
        cf_picks = cf_page.leaf_item_picks()
        if cf_picks:
            merged_categories = dict(selection.categories)
            merged_categories[GrammarCategory.CUSTOM_FIELDS] = True
            merged_leaf = dict(selection.leaf_item_picks)
            merged_leaf.update(cf_picks)
            selection = dataclasses.replace(
                selection,
                categories=merged_categories,
                leaf_item_picks=merged_leaf,
            )
        elif cf_page.whole_block_on():
            # Fully selected => include CUSTOM_FIELDS category (transfer-all).
            merged_categories = dict(selection.categories)
            merged_categories[GrammarCategory.CUSTOM_FIELDS] = True
            selection = dataclasses.replace(selection, categories=merged_categories)

    # Step 5b: phonology collapse-merge (applied AFTER resolution stamp per DR-4/P1).
    phon_page = wizard.page_phonology()
    if phon_page is not None and phon_page.inventory() is not None:
        collapsed = collapse_phonology(
            phon_page.inventory(), phon_page.collect_phonology_picks()
        )
        if collapsed["categories"]:
            merged_categories = dict(selection.categories)
            merged_categories.update(collapsed["categories"])
            merged_leaf = dict(selection.leaf_item_picks)
            merged_leaf.update(collapsed["leaf_item_picks"])
            selection = dataclasses.replace(
                selection,
                categories=merged_categories,
                leaf_item_picks=merged_leaf,
            )

    # Step 5c: entry-types collapse-merge (spec 021, applied after phonology).
    et_page = (wizard.page_entry_types()
               if hasattr(wizard, "page_entry_types") else None)
    if et_page is not None and et_page.inventory() is not None:
        collapsed = collapse_entry_types(
            et_page.inventory(), et_page.collect_entry_type_picks()
        )
        if collapsed["categories"]:
            merged_categories = dict(selection.categories)
            merged_categories.update(collapsed["categories"])
            merged_leaf = dict(selection.leaf_item_picks)
            merged_leaf.update(collapsed["leaf_item_picks"])
            selection = dataclasses.replace(
                selection,
                categories=merged_categories,
                leaf_item_picks=merged_leaf,
            )

    # Step 5d: rules block collapse-merge (018-rules-page T019).
    # collect_rules_picks() returns:
    #   None         => key absent (transfer ALL, SC-004 untouched default)
    #   frozenset()  => whole block OFF, zero rules transferred (SC-005)
    #   frozenset({..}) => individual trim subset
    rules_page = wizard.page_rules() if hasattr(wizard, "page_rules") else None
    if rules_page is not None and rules_page.inventory() is not None:
        rules_picks = rules_page.collect_rules_picks()
        if rules_picks is None:
            # Untouched / fully-checked => include category, key absent (transfer all)
            merged_categories = dict(selection.categories)
            merged_categories[GrammarCategory.ADHOC_COMPOUND_RULES] = True
            selection = dataclasses.replace(selection, categories=merged_categories)
        else:
            # Trimmed or whole-block-OFF: include category + emit frozenset (may be empty)
            merged_categories = dict(selection.categories)
            merged_categories[GrammarCategory.ADHOC_COMPOUND_RULES] = True
            merged_leaf = dict(selection.leaf_item_picks)
            merged_leaf[GrammarCategory.ADHOC_COMPOUND_RULES] = rules_picks
            selection = dataclasses.replace(
                selection,
                categories=merged_categories,
                leaf_item_picks=merged_leaf,
            )

    # Step 6: WS mapping from page 0.
    page0 = wizard.page_project_ws()
    ws_mapping = page0.ws_mapping() if hasattr(page0, "ws_mapping") else None

    # Step 7: compute preview; return (None, None) on failure or None payload.
    state, payload = gt_api.compute_preview(context, selection, ws_mapping)
    if payload is None:
        return (None, None)

    # Step 8: build run report and return.
    phon_warnings = _phonology_excluded_lossy_for(wizard)
    report = RunReport.build_from_plan(
        payload, RunMode.PREVIEW, extra_excluded_lossy=phon_warnings
    )
    return (payload, report)


# ---------------------------------------------------------------------------
# Page 5 -- Finish / Move
# ---------------------------------------------------------------------------

class _PageFinish(QtWidgets.QWizardPage):
    """Page 5: Finish / Move.

    The ONLY write point.  The Finish handler:
    1. Queries `plan.excluded_lossy_count()`.
    2. When > 0: blocks and pops the summary dialog.
       Confirm -> write; cancel -> stay on wizard.
    3. Executes the move via `gt_api.execute_move`.
    4. Shows the RunReport (MOVE) in the StatsPanel.
    """

    def __init__(self, report_sink, modify_allowed: bool, parent=None):
        super().__init__(parent)
        self._report_sink = report_sink
        self._modify_allowed = modify_allowed
        self._move_done = False
        # DR-1: cached plan is the sole freshness gate for the dry-run flow.
        self._cached_plan = None
        self.setTitle("Step 9 of 9: Finish / Move")
        self.setSubTitle(
            "Click 'Execute Move' to write all planned actions to the target project. "
            "This is the only write point -- changes can be undone in FLEx with Ctrl+Z."
        )
        self._build_ui()
        # DR-1: Move starts disabled unconditionally; enabled only after dry run.
        self._move_btn.setEnabled(False)

    def initializePage(self) -> None:
        """DR-2a: clear cached plan and disable Move on every Finish page entry."""
        self._cached_plan = None
        self._move_btn.setEnabled(False)

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        if not self._modify_allowed:
            warn = QtWidgets.QLabel(
                "[WARN] GramTrans is running in read-only (preview-only) mode. "
                "Move is disabled.",
                self,
            )
            warn.setWordWrap(True)
            layout.addWidget(warn)
        self._dry_run_btn = QtWidgets.QPushButton("Dry run (preview plan)", self)
        self._dry_run_btn.clicked.connect(self._on_dry_run)
        layout.addWidget(self._dry_run_btn)
        self._move_btn = QtWidgets.QPushButton("Execute Move", self)
        self._move_btn.setEnabled(False)
        self._move_btn.clicked.connect(self._on_move)
        layout.addWidget(self._move_btn)
        self._stats = StatsPanel(self)
        layout.addWidget(self._stats, 1)

    def _on_dry_run(self) -> None:
        """DR-5, G1, FR-006: compute the plan and show report; enable Move on success."""
        wizard = self.wizard()
        if wizard is None:
            return
        plan, report = _compute_wizard_plan(wizard)
        if plan is None:
            # DR-5: caller owns QMessageBox.
            context = wizard.page_project_ws().context()
            if context is None:
                QtWidgets.QMessageBox.warning(
                    self, "GramTrans", "No target project bound. Go back to page 1."
                )
            else:
                # G1: assembly failure -- Move stays disabled, no partial state.
                QtWidgets.QMessageBox.warning(
                    self, "GramTrans", "Plan assembly failed. Check project state."
                )
            return
        self._cached_plan = plan
        self._stats.set_report(report)
        if self._modify_allowed:
            self._move_btn.setEnabled(True)

    def _on_move(self) -> None:
        wizard = self.wizard()
        if wizard is None:
            return
        # DR-6: read cached plan from self (set by dry run), not preview page.
        plan = self._cached_plan
        if plan is None:
            QtWidgets.QMessageBox.warning(
                self, "GramTrans",
                "No plan available. Run a dry run on the Finish page first."
            )
            return
        context = wizard.page_project_ws().context()
        if context is None:
            return

        # T017: Aggregate EXCLUDED-LOSSY from the plan + skeleton/deps deselections.
        # plan.excluded_lossy_count() covers warnings emitted during preview planning.
        # Additionally, check skeleton page (index 2) and deps page (index 3) for
        # slots/deps the user deselected that a picked affix needs.
        el_count = plan.excluded_lossy_count()

        # Extra skeleton EXCLUDED-LOSSY (T017)
        skel_page = wizard.page_skeleton()
        if skel_page is not None and hasattr(skel_page, "deselected_filled_slot_guids"):
            deselected_slots = skel_page.deselected_filled_slot_guids()
            if deselected_slots and skel_page._skeleton is not None:
                # Build affix_slot_map from skeleton
                affix_slot_map = {
                    affix_guid: list(slot_guids)
                    for affix_guid, slot_guids in (
                        (ag, frozenset(
                            sg for sg, fills in skel_page._skeleton.affix_fills.items()
                            if ag in fills
                        ))
                        for ag in skel_page._skeleton.affix_picks
                    )
                }
                # target slot guids (blank; skeleton doesn't have live target here)
                extra_warnings = build_excluded_lossy_warnings(
                    affix_slot_map=affix_slot_map,
                    deselected_slot_guids=set(deselected_slots),
                    target_slot_guids=set(),
                )
                el_count += len(extra_warnings)

        # Extra phonology EXCLUDED-LOSSY + KL-010-1 guard (spec 010 T024/T026b).
        # Aggregated into the SAME el_count so a single consolidated dialog
        # covers skeleton/deps AND phonology (FR-011 — no second dialog).
        el_count += len(_phonology_excluded_lossy_for(wizard))

        # Extra entry-types missing-ref warnings (spec 021 T024 / FR-010/FR-011).
        # Kept ILexEntryInflType whose infl-feat ref is absent from target; counted
        # into the SAME consolidated dialog -- never a separate prompt.
        el_count += len(_entry_types_missing_ref_for(wizard))

        # Consolidated single confirmation dialog (FR-011 / T017).
        if el_count > 0:
            answer = QtWidgets.QMessageBox.question(
                self,
                "GramTrans -- Missing references",
                (
                    f"{el_count} entr{'y' if el_count == 1 else 'ies'} will transfer "
                    f"with missing references (deliberately excluded dependencies).\n\n"
                    "These entries will have null fields in the target project.\n\n"
                    "Proceed with Move?"
                ),
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return  # User cancelled -- no write occurs.

        try:
            report = gt_api.execute_move(context, plan)
        except gt_api.PreviewStale as e:
            QtWidgets.QMessageBox.critical(self, "GramTrans", str(e))
            return
        self._stats.set_report(report)
        self._move_btn.setEnabled(False)
        self._move_done = True
        # DR-2b, G3: invalidate Finish page's own cached plan (post-move).
        # Move non-repeatability: a double-click or re-entry cannot re-execute
        # the same plan and create duplicate LCM objects. initializePage also
        # clears on re-entry (DR-2a), so this provides belt-and-suspenders safety.
        self._cached_plan = None
        self.completeChanged.emit()


# ---------------------------------------------------------------------------
# Main wizard
# ---------------------------------------------------------------------------

class SelectionWizard(QtWidgets.QWizard):
    """6-page GramTrans selection wizard (Phase 3c, Refinement 3).

    Replaces `main_window.MainWindow`.  All existing widgets are re-hosted
    verbatim; no widget logic is rewritten.

    Constructor args:
        host_project: the FlexTools host's open FLExProject (the SOURCE).
        report_sink:  FlexTools report object (.Info / .Warning / .Error / .Blank).
        modify_allowed: True when FlexTools is running write-enabled.
        source_project_name: display name of the source project.
    """

    def __init__(
        self,
        host_project,
        report_sink,
        modify_allowed: bool,
        *,
        source_project_name: str,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._host = host_project
        self._report = report_sink
        self._modify_allowed = modify_allowed

        self.setWindowTitle("GramTrans -- Selection Wizard (Phase 3c)")
        self.setModal(True)
        self.resize(1300, 760)
        # T004/FR-011: widen wizard to accommodate tree + preview pane side by side
        from PyQt6 import QtCore as _QtCore
        self.setMinimumSize(_QtCore.QSize(1100, 680))
        # ClassicStyle renders pages using the widget palette instead of forcing
        # a white page (AeroStyle/ModernStyle default on Windows). Under an OS
        # dark theme the forced-white page left every QLabel white-on-white
        # (illegible); ClassicStyle keeps text/background consistent with the
        # palette in both light and dark themes.
        self.setWizardStyle(QtWidgets.QWizard.WizardStyle.ClassicStyle)

        stub = gt_api.initialize_run(
            host_handle=host_project,
            source_project_name=source_project_name,
            source_project_path=_safe_path(host_project),
        )

        # Create pages.
        # Page order (spec 021 FR-001 / SC-007 — Lexical-Entry Types at index 6):
        #   0 = Project + WS
        #   1 = Custom Fields (Model-B)
        #   2 = Phonology (Model-B independent block)
        #   3 = Affixes (item picker)
        #   4 = Skeleton
        #   5 = Grammatical deps
        #   6 = Lexical-Entry Types (Model-B independent block)
        #   7 = Finish / Move
        # _PagePreview retained (not added) for back-compat via page_preview().
        # Cross-page lookups go through named accessors (P-1) so this insertion
        # does not silently mis-resolve any literal page index.
        # _PageScopeConflict is retained for back-compat but removed from the flow.
        self._page_project_ws = _PageProjectWS(stub, host_project)
        self._page_custom_fields = _PageCustomFields()
        self._page_phonology = _PagePhonology()
        self._page_items = _PageItemPicker()
        self._page_skeleton = _PageSkeleton()
        self._page_gram_deps = _PageGramDeps()
        self._page_entry_types = _PageEntryTypes()   # spec 021 idx 6
        # _PageScopeConflict kept but NOT added to the wizard (conflict UI deferred FR-012).
        self._page_scope = _PageScopeConflict()
        # 018-rules-page: Rules page sits after Lexical-entry types (021, not yet added)
        # and before Preview (FR-007).  Positioned after _PageGramDeps per spec order.
        self._page_rules = _PageRules()
        self._page_preview = _PagePreview()
        self._page_finish = _PageFinish(report_sink, modify_allowed)

        self.addPage(self._page_project_ws)    # index 0
        self.addPage(self._page_custom_fields) # index 1
        self.addPage(self._page_phonology)     # index 2
        self.addPage(self._page_items)         # index 3
        self.addPage(self._page_skeleton)      # index 4
        self.addPage(self._page_gram_deps)     # index 5
        self.addPage(self._page_entry_types)   # index 6  (spec 021 lexical-entry types)
        self.addPage(self._page_rules)         # index 7  (018-rules-page)
        self.addPage(self._page_finish)        # index 8

        self.setOption(QtWidgets.QWizard.WizardOption.HaveHelpButton, False)

    def context(self):
        """Return the bound RunContext (available after page 1 is completed)."""
        return self._page_project_ws.context()

    # -- Named page accessors (spec 010 P-1) ---------------------------------
    # Pages MUST reference each other through these, never by literal index:
    # inserting a page (e.g. Phonology at index 1) shifts every literal
    # `wizard.page(N)` silently. Each accessor returns the stored attribute.
    def page_project_ws(self):
        return self._page_project_ws

    def page_custom_fields(self):
        return self._page_custom_fields

    def page_phonology(self):
        return self._page_phonology

    def page_items(self):
        return self._page_items

    def page_skeleton(self):
        return self._page_skeleton

    def page_gram_deps(self):
        return self._page_gram_deps

    def page_entry_types(self):
        return self._page_entry_types

    def page_rules(self):
        """Named accessor for _PageRules (018-rules-page P-1 pattern)."""
        return self._page_rules

    def page_preview(self):
        return self._page_preview

    def page_finish(self):
        return self._page_finish


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _safe_path(flex_project) -> str:
    for attr in ("ProjectPath", "ProjectFilename", "ProjectFolder"):
        try:
            v = getattr(flex_project, attr)
            return v() if callable(v) else str(v)
        except Exception:
            continue
    return ""


def _enumerate_active_ws_ids(project) -> list:
    """Enumerate ACTIVE writing systems from a FLExProject.

    Active = analysis + vernacular writing systems currently active in the
    project (not the full installed superset). Falls back to an empty list
    on any introspection failure.
    """
    ws_ids = []
    try:
        # Attempt 1: flexicon's GetSyncableProperties-compatible path.
        # flexicon exposes WritingSystems.GetAll().
        all_wss = project.WritingSystems.GetAll()
        for ws in all_wss:
            ws_id = getattr(ws, "Id", None)
            if ws_id:
                ws_ids.append(str(ws_id))
        if ws_ids:
            return ws_ids
    except (AttributeError, TypeError, Exception):  # noqa: BLE001
        pass

    # Attempt 2: try AnalysisWritingSystems + VernacularWritingSystems (LCM 9.x).
    try:
        for attr in ("AnalysisWritingSystems", "VernacularWritingSystems"):
            wss = getattr(project, attr, None)
            if wss is None:
                continue
            for ws in wss:
                ws_id = getattr(ws, "Id", None) or getattr(ws, "IcuLocale", None)
                if ws_id and ws_id not in ws_ids:
                    ws_ids.append(str(ws_id))
        if ws_ids:
            return ws_ids
    except (AttributeError, TypeError, Exception):  # noqa: BLE001
        pass

    # Attempt 3: best-effort GetWritingSystems (used by old WS dialog).
    try:
        for ws in project.GetWritingSystems():
            ws_id = getattr(ws, "Id", None)
            if ws_id and ws_id not in ws_ids:
                ws_ids.append(str(ws_id))
    except (AttributeError, TypeError, Exception):  # noqa: BLE001
        pass

    return ws_ids


def _enumerate_ws_by_kind(project) -> "tuple[list, list]":
    """Enumerate ACTIVE writing systems split by kind.

    Returns:
        (vern_ids, anal_ids) -- each a list[str] of WS IDs in active order.
        A dual-role WS (both vernacular + analysis) appears in BOTH lists.
        Falls back to treating all active WSes as both kinds on total failure.

    Primary access path (LCM 9.x via flexicon FLExProject.Cache):
        project.Cache.LangProject.CurrentVernacularWritingSystems
        project.Cache.LangProject.CurrentAnalysisWritingSystems
    Each entry exposes .Id (full BCP-47 tag, e.g. 'etu', 'etu-fonipa').
    Current* is the correct "active/enabled" list; each distinct variant tag
    (e.g. 'etu' vs 'etu-fonipa') is a separate entry and maps 1:1 by default.

    NOTE: project.VernacularWritingSystems and project.AnalysisWritingSystems
    are NOT exposed by the flexicon FLExProject wrapper and return None --
    the Cache.LangProject.Current* path is the correct primary path.
    """
    vern_ids: list = []
    anal_ids: list = []
    try:
        cache = getattr(project, "Cache", None)
        lang = getattr(cache, "LangProject", None)
        if lang is not None:
            cvws = getattr(lang, "CurrentVernacularWritingSystems", None)
            if cvws is not None:
                for ws in cvws:
                    ws_id = getattr(ws, "Id", None)
                    if ws_id and str(ws_id) not in vern_ids:
                        vern_ids.append(str(ws_id))
            caws = getattr(lang, "CurrentAnalysisWritingSystems", None)
            if caws is not None:
                for ws in caws:
                    ws_id = getattr(ws, "Id", None)
                    if ws_id and str(ws_id) not in anal_ids:
                        anal_ids.append(str(ws_id))
        if vern_ids or anal_ids:
            return (vern_ids, anal_ids)
    except (AttributeError, TypeError, Exception):  # noqa: BLE001
        pass

    # Fallback: treat all active WSes as both kinds (graceful degradation).
    all_ids = _enumerate_active_ws_ids(project)
    return (list(all_ids), list(all_ids))

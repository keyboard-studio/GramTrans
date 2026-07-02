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

from typing import Optional

from PyQt6 import QtCore, QtWidgets

if __package__:
    from .. import api as gt_api
    from ..models import (
        CategoryScope,
        ConflictMode,
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
        build_pos_grouped_inventory,
        build_selection,
        collapse_pos_grouped,
        mirror_check_state,
    )
    from .stats_panel import StatsPanel
    from .target_picker import TargetPickerDialog
else:
    import api as gt_api  # type: ignore
    from models import (  # type: ignore
        CategoryScope,
        ConflictMode,
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
        build_pos_grouped_inventory,
        build_selection,
        collapse_pos_grouped,
        mirror_check_state,
    )
    from stats_panel import StatsPanel  # type: ignore
    from target_picker import TargetPickerDialog  # type: ignore


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
    ConflictMode.MERGE: "Merge (link existing by ID, else add; no field update)",
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
        # ADD_NEW hidden, OVERWRITE forbidden
        return [ConflictMode.MERGE]
    # MULTI_INSTANCE or SINGLETON_NONDELETABLE that isn't GOLD -> all three
    return [ConflictMode.ADD_NEW, ConflictMode.MERGE, ConflictMode.OVERWRITE]


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

        self.setTitle("Step 1 of 5: Project + Writing Systems")
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


# ---------------------------------------------------------------------------
# Page 2 -- Item picker (POS-grouped, specs/008-affix-pos-picker)
# ---------------------------------------------------------------------------

class _PageItemPicker(QtWidgets.QWizardPage):
    """Page 2: POS-grouped affix item picker.

    Tree layout (4 columns):
        Col 0: Affix form -> glosses  |  Col 1: Type  |  Col 2: From  |  Col 3: To

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
        self.setTitle("Step 2 of 5: Item Picker")
        self.setSubTitle(
            "Select the affixes to transfer, grouped by the part of speech they attach to. "
            "Stems are not yet supported (coming in a later phase)."
        )
        self._inventory: Optional[PosGroupedAffixInventory] = None
        # Map from entry_guid -> list of QTreeWidgetItem (for mirroring)
        self._guid_to_items: dict = {}
        # Re-entrancy guard for itemChanged mirroring
        self._mirroring: bool = False
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        # Tab widget: Affixes (active) + Stems (disabled stub)
        self._tabs = QtWidgets.QTabWidget(self)

        # --- Affixes tab (POS-grouped tree) ---
        affix_tab = QtWidgets.QWidget()
        affix_tab_layout = QtWidgets.QVBoxLayout(affix_tab)
        affix_tab_layout.addWidget(QtWidgets.QLabel(
            "Check POS groups or individual affixes to include in the transfer.\n"
            "Checking a POS group selects all affixes that attach to it "
            "(not affixes that only produce it).",
            affix_tab,
        ))
        self._tree = QtWidgets.QTreeWidget(affix_tab)
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels(["Affix / Group", "Type", "From", "To"])
        self._tree.header().setStretchLastSection(False)
        self._tree.setAlternatingRowColors(True)
        affix_tab_layout.addWidget(self._tree, 1)
        self._tabs.addTab(affix_tab, "Affixes")

        # --- Stems tab (stubbed, disabled) ---
        stems_tab = QtWidgets.QWidget()
        stems_layout = QtWidgets.QVBoxLayout(stems_tab)
        stems_layout.addWidget(QtWidgets.QLabel(
            "[STUBBED] Stem transfer is not yet available. "
            "It will be enabled in a future phase (Layer-3 stems).",
            stems_tab,
        ))
        self._tabs.addTab(stems_tab, "Stems (not yet available)")
        self._tabs.setTabEnabled(1, False)

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
            return

        try:
            inventory = build_pos_grouped_inventory(source)
        except Exception:  # noqa: BLE001
            inventory = None  # type: ignore[assignment]

        if inventory is None:
            self._inventory = None
            self._guid_to_items = {}
            return

        self._inventory = inventory
        self._guid_to_items = {}
        self.populate_pos_tree(inventory)
        self._tree.itemChanged.connect(self._on_item_changed)

    def _get_source(self):
        """Return the source project handle from page 0, or None."""
        try:
            wizard = self.wizard()
            if wizard is None:
                return None
            page0 = wizard.page(0)
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
        # Resize columns to content after population
        for col in range(4):
            self._tree.resizeColumnToContents(col)

    def _add_pos_node(self, parent, pos_node) -> None:
        """Recursively add a PosNode and its subgroups/children to the tree."""
        pos_item = self._make_group_item(
            parent, pos_node.label,
            kind="pos_group", checkable=True, is_produces_group=False,
        )
        pos_item.setData(0, _GUID_ROLE, pos_node.pos_guid)

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
        """Create a group/header tree item."""
        if isinstance(parent, QtWidgets.QTreeWidget):
            item = QtWidgets.QTreeWidgetItem(parent, [label, "", "", ""])
        else:
            item = QtWidgets.QTreeWidgetItem(parent, [label, "", "", ""])
        item.setData(0, _KIND_ROLE, kind)
        item.setData(0, _IS_PRODUCES, is_produces_group)
        if checkable:
            item.setFlags(
                item.flags()
                | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                | QtCore.Qt.ItemFlag.ItemIsAutoTristate
            )
            item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        return item

    def _add_affix_row(self, parent: QtWidgets.QTreeWidgetItem,
                       row) -> None:
        """Add a leaf AffixRow item to the tree under parent."""
        label = f"{row.form}  ->  {row.glosses}"
        type_label = {"infl": "Infl", "deriv": "Deriv", "uncl": "Uncl"}.get(
            row.msa_kind, row.msa_kind
        )
        from_label = row.from_pos if row.from_pos else ("—" if row.role == "produces" else "")
        to_label = row.to_pos if row.to_pos else ("—" if row.msa_kind == "deriv" else "")

        item = QtWidgets.QTreeWidgetItem(
            parent, [label, type_label, from_label, to_label]
        )
        item.setData(0, _GUID_ROLE, row.entry_guid)
        item.setData(0, _KIND_ROLE, "affix")
        item.setData(0, _ROLE_ROLE, row.role)
        item.setData(0, _IS_PRODUCES, row.role == "produces")
        item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)

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

    def collect_selection(self) -> Selection:
        """Build a Selection from the current picker state."""
        if self._inventory is None:
            dummy = SourceAffixInventory()
            return build_selection(PickerState(), dummy)
        ps = self.picker_state()
        return collapse_pos_grouped(ps.checked_affixes, self._inventory)


# ---------------------------------------------------------------------------
# Page 3 -- Schema scope + conflict mode
# ---------------------------------------------------------------------------

class _PageScopeConflict(QtWidgets.QWizardPage):
    """Page 3: per-category three-scope selector + conflict mode.

    Re-hosts the existing scope-combo controls from main_window and adds
    per-category ConflictMode selectors gated by the Layer-1 kind table.

    The MERGE control carries an explicit label ("link existing by ID, else
    add; no field update") per spec section (i).
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
            default_mode = _DEFAULT_CONFLICT_MODES.get(cat, ConflictMode.MERGE)
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
# Page 4 -- Preview
# ---------------------------------------------------------------------------

class _PagePreview(QtWidgets.QWizardPage):
    """Page 4: Preview / StatsPanel.

    Re-hosts the existing StatsPanel widget verbatim.  Preview is triggered
    when the page is entered; the plan is cached for use on page 5.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Step 4 of 5: Preview")
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
        wizard = self.wizard()
        if wizard is None:
            return
        context = wizard.page(0).context()
        if context is None:
            QtWidgets.QMessageBox.warning(
                self, "GramTrans", "No target project bound. Go back to page 1."
            )
            return
        # Page 1 (index 1) is _PageItemPicker -- it now owns collect_selection()
        # and reads its own inventory. Page 2 (index 2) is _PageScopeConflict.
        page_items = wizard.page(1)
        affix_selection = page_items.collect_selection()
        # Merge scope/conflict settings from page 2 (_PageScopeConflict).
        # Preserve template_picks from the item-picker selection so they are
        # not discarded when re-wrapping into PickerState/SourceAffixInventory.
        page_scope = wizard.page(2)
        selection = page_scope.collect_selection(
            PickerState(
                checked_affixes=affix_selection.affix_picks,
                checked_templates=affix_selection.template_picks,
            ),
            SourceAffixInventory(
                unbound_affixes=affix_selection.affix_picks,
                template_to_slots={t: () for t in affix_selection.template_picks},
            ),
        )
        # WS mapping from page 1 (three-way MAP/CREATE/SKIP control).
        # Falls back to an empty mapping if page 1 has not yet built the table.
        page1 = wizard.page(0)
        ws_mapping = page1.ws_mapping() if hasattr(page1, "ws_mapping") else None
        state, payload = gt_api.compute_preview(context, selection, ws_mapping)
        # Phase 3c: compute_preview always returns PREVIEW_READY
        self._cached_plan = payload
        if __package__:
            from ..report import RunReport
        else:
            from report import RunReport  # type: ignore
        report = RunReport.build_from_plan(payload, RunMode.PREVIEW)
        self._stats.set_report(report)
        self.completeChanged.emit()

    def cached_plan(self):
        return self._cached_plan

    def isComplete(self) -> bool:
        return self._cached_plan is not None


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
        self.setTitle("Step 5 of 5: Finish / Move")
        self.setSubTitle(
            "Click 'Execute Move' to write all planned actions to the target project. "
            "This is the only write point -- changes can be undone in FLEx with Ctrl+Z."
        )
        self._build_ui()

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
        self._move_btn = QtWidgets.QPushButton("Execute Move", self)
        self._move_btn.setEnabled(self._modify_allowed)
        self._move_btn.clicked.connect(self._on_move)
        layout.addWidget(self._move_btn)
        self._stats = StatsPanel(self)
        layout.addWidget(self._stats, 1)

    def _on_move(self) -> None:
        wizard = self.wizard()
        if wizard is None:
            return
        plan = wizard.page(3).cached_plan()
        if plan is None:
            QtWidgets.QMessageBox.warning(
                self, "GramTrans", "No preview plan available. Go back to page 4."
            )
            return
        context = wizard.page(0).context()
        if context is None:
            return

        # Confirm-on-Move gate (spec section e, Refinement 3 P1).
        el_count = plan.excluded_lossy_count()
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
        # Move non-repeatability (P0): invalidate the preview page's cached plan
        # so a double-click or re-entry cannot re-execute the same plan and
        # create duplicate LCM objects.
        preview_page = wizard.page(3)
        if hasattr(preview_page, "_cached_plan"):
            preview_page._cached_plan = None
        self.completeChanged.emit()


# ---------------------------------------------------------------------------
# Main wizard
# ---------------------------------------------------------------------------

class SelectionWizard(QtWidgets.QWizard):
    """5-page GramTrans selection wizard (Phase 3c, Refinement 3).

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
        self.resize(900, 720)
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

        # Create pages (indices 0-4 match spec pages 1-5).
        self._page_project_ws = _PageProjectWS(stub, host_project)
        self._page_items = _PageItemPicker()
        self._page_scope = _PageScopeConflict()
        self._page_preview = _PagePreview()
        self._page_finish = _PageFinish(report_sink, modify_allowed)

        self.addPage(self._page_project_ws)
        self.addPage(self._page_items)
        self.addPage(self._page_scope)
        self.addPage(self._page_preview)
        self.addPage(self._page_finish)

        self.setOption(QtWidgets.QWizard.WizardOption.HaveHelpButton, False)

    def context(self):
        """Return the bound RunContext (available after page 1 is completed)."""
        return self._page_project_ws.context()


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
        # Attempt 1: flexlibs2 fork's GetSyncableProperties-compatible path.
        # The fork exposes WritingSystems.GetAll() per CLAUDE.md.
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

    Primary access path (LCM 9.x via flexlibs2 FLExProject.Cache):
        project.Cache.LangProject.CurrentVernacularWritingSystems
        project.Cache.LangProject.CurrentAnalysisWritingSystems
    Each entry exposes .Id (full BCP-47 tag, e.g. 'etu', 'etu-fonipa').
    Current* is the correct "active/enabled" list; each distinct variant tag
    (e.g. 'etu' vs 'etu-fonipa') is a separate entry and maps 1:1 by default.

    NOTE: project.VernacularWritingSystems and project.AnalysisWritingSystems
    are NOT exposed by the flexlibs2 FLExProject wrapper and return None --
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

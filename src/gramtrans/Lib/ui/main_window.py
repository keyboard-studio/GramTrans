"""Main window (T057, FR-002) — orchestrates the state machine from
contracts/module-ui.md.

State sequence:
    [Start]
      → Source detected from FlexTools host (already open)
      → Target picker (FR-003) — opens TargetPickerDialog
      → Category toggles + closure-on/off + (optional) affix tree picker
      → Click Preview → WS mapping dialog (FR-011) when ws_mapping missing →
        Re-Preview with mapping → PREVIEW_READY → stats panel shows plan
      → Click Move (gated: current selection == cached plan selection) →
        execute_move() → stats panel shows RunReport(MOVE)
      → Any Selection / WSMapping change re-disables Move (Principle III
        mechanical enforcement).

The window is a QDialog hosted by `gramtrans.py.MainFunction`.
"""
from __future__ import annotations

from typing import Optional

from PyQt6 import QtCore, QtWidgets

if __package__:
    from .. import api as gt_api
    from ..models import CategoryScope, GrammarCategory, RunMode, Selection, WSMapping
    from .stats_panel import StatsPanel
    from .target_picker import TargetPickerDialog
    from .ws_mapping_dialog import WSMappingDialog
else:
    import api as gt_api  # type: ignore
    from models import CategoryScope, GrammarCategory, RunMode, Selection, WSMapping  # type: ignore
    from stats_panel import StatsPanel  # type: ignore
    from target_picker import TargetPickerDialog  # type: ignore
    from ws_mapping_dialog import WSMappingDialog  # type: ignore


# Schema categories that participate in per-category three-scope selection.
# These are the dependency categories the item-picker (affixes/stems/templates)
# can reference; the main window exposes a three-scope selector for each.
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

# Scope labels for the three-way combobox.
_SCOPE_LABELS = {
    CategoryScope.NONE: "NONE",
    CategoryScope.AS_NEEDED: "AS-NEEDED (default)",
    CategoryScope.ALL: "ALL",
}


# All FR-004 categories the main window exposes as toggles.
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


class MainWindow(QtWidgets.QDialog):
    """Single dialog hosting the entire GramTrans flow inside FlexTools."""

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

        self.setWindowTitle("GramTrans — Phase 0 (Additive)")
        self.setModal(True)
        self.resize(820, 700)

        # State.
        self._stub = gt_api.initialize_run(
            host_handle=host_project,
            source_project_name=source_project_name,
            source_project_path=_safe_path(host_project),
        )
        self._target_candidate: Optional[gt_api.TargetCandidate] = None
        self._context = None  # set after bind_target succeeds
        self._cached_plan = None
        self._cached_plan_signature = None  # (selection, ws_mapping) at the time

        self._build_ui()
        self._refresh_buttons()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        # Header
        self._header_label = QtWidgets.QLabel(
            f"Source: <b>{self._stub.source_project_name}</b> (open in FlexTools).<br>"
            f"Run ID: <code>{self._stub.run_id}</code>",
            self,
        )
        layout.addWidget(self._header_label)

        # Target picker row
        target_row = QtWidgets.QHBoxLayout()
        self._target_label = QtWidgets.QLabel("Target: <i>(not picked)</i>", self)
        target_row.addWidget(self._target_label, 1)
        pick_btn = QtWidgets.QPushButton("Pick target…", self)
        pick_btn.clicked.connect(self._on_pick_target)
        target_row.addWidget(pick_btn)
        layout.addLayout(target_row)

        # Item category toggles (affixes, stems, templates, etc.)
        toggles_group = QtWidgets.QGroupBox("Grammar piece categories to transfer", self)
        toggles_layout = QtWidgets.QGridLayout(toggles_group)
        self._toggles: dict = {}
        for i, cat in enumerate(_CATEGORY_TOGGLES):
            cb = QtWidgets.QCheckBox(cat.value.replace("_", " "), toggles_group)
            cb.toggled.connect(self._on_selection_changed)
            toggles_layout.addWidget(cb, i // 3, i % 3)
            self._toggles[cat] = cb
        layout.addWidget(toggles_group)

        # Schema-section three-scope selectors (one per schema category).
        # Each category gets a label + combobox: NONE / AS-NEEDED / ALL.
        schema_group = QtWidgets.QGroupBox(
            "Schema dependency scope (per-category: NONE / AS-NEEDED / ALL)", self
        )
        schema_layout = QtWidgets.QGridLayout(schema_group)
        self._scope_combos: dict = {}  # GrammarCategory -> QComboBox
        for i, cat in enumerate(_SCHEMA_CATEGORIES):
            lbl = QtWidgets.QLabel(cat.value.replace("_", " ") + ":", schema_group)
            combo = QtWidgets.QComboBox(schema_group)
            for scope in (CategoryScope.NONE, CategoryScope.AS_NEEDED, CategoryScope.ALL):
                combo.addItem(_SCOPE_LABELS[scope], scope)
            # Default: AS_NEEDED (index 1).
            combo.setCurrentIndex(1)
            combo.currentIndexChanged.connect(self._on_selection_changed)
            schema_layout.addWidget(lbl, i // 2, (i % 2) * 2)
            schema_layout.addWidget(combo, i // 2, (i % 2) * 2 + 1)
            self._scope_combos[cat] = combo
        layout.addWidget(schema_group)

        # Legacy closure toggle (kept for back-compat with existing tests and
        # callers that don't use the per-category scopes; still drives the
        # fallback path in Selection.scope_for when category_scopes is empty).
        self._closure_cb = QtWidgets.QCheckBox(
            "Include dependency closure (legacy fallback; per-category scopes above take precedence)", self
        )
        self._closure_cb.setChecked(True)
        self._closure_cb.toggled.connect(self._on_selection_changed)
        layout.addWidget(self._closure_cb)

        # Run buttons row
        run_row = QtWidgets.QHBoxLayout()
        self._preview_btn = QtWidgets.QPushButton("Preview", self)
        self._move_btn = QtWidgets.QPushButton("Move", self)
        self._preview_btn.clicked.connect(self._on_preview)
        self._move_btn.clicked.connect(self._on_move)
        run_row.addWidget(self._preview_btn)
        run_row.addWidget(self._move_btn)
        run_row.addStretch(1)
        layout.addLayout(run_row)

        # Stats panel
        self._stats = StatsPanel(self)
        layout.addWidget(self._stats, 1)

    # ------------------------------------------------------------------
    # Slots
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
        self._target_candidate = choice
        self._target_label.setText(
            f"Target: <b>{choice.project_name}</b> (<code>{choice.project_path}</code>)"
        )
        self._invalidate_plan()

    def _on_selection_changed(self, *_) -> None:
        self._invalidate_plan()

    def _on_preview(self) -> None:
        if self._context is None:
            QtWidgets.QMessageBox.information(
                self, "GramTrans", "Pick a target project first."
            )
            return
        selection = self._collect_selection()
        if not selection.categories:
            QtWidgets.QMessageBox.information(
                self, "GramTrans", "Select at least one category before running."
            )
            return

        # Two-stage compute_preview: ws_mapping starts None.
        state, payload = gt_api.compute_preview(self._context, selection, None)
        if state is gt_api.PreviewState.NEEDS_WS_MAPPING:
            ws = self._collect_ws_mapping(payload)
            if ws is None:
                return
            state, payload = gt_api.compute_preview(self._context, selection, ws)
            if state is gt_api.PreviewState.NEEDS_WS_MAPPING:
                QtWidgets.QMessageBox.warning(
                    self, "GramTrans", "WS mapping still incomplete; refine and retry."
                )
                return
            ws_mapping = ws
        else:
            ws_mapping = WSMapping(entries=())

        plan = payload  # RunPlan
        self._cached_plan = plan
        self._cached_plan_signature = (selection, ws_mapping)

        if self._modify_allowed:
            self._move_btn.setEnabled(True)
        # Render the preview's "would add" view via the same stats panel.
        # Dual-mode import: package (tests) vs flat/site.addsitedir (runtime).
        if __package__:
            from ..report import RunReport
        else:
            from report import RunReport  # type: ignore
        report = RunReport.build_from_plan(plan, RunMode.PREVIEW)
        self._stats.set_report(report)

    def _on_move(self) -> None:
        if self._cached_plan is None or self._cached_plan_signature is None:
            QtWidgets.QMessageBox.warning(self, "GramTrans", "Click Preview first.")
            return
        current = (self._collect_selection(), self._cached_plan_signature[1])
        if current != self._cached_plan_signature:
            QtWidgets.QMessageBox.warning(
                self, "GramTrans",
                "Selection changed since last Preview. Re-Preview before Move.",
            )
            self._move_btn.setEnabled(False)
            return

        # Confirm-on-Move gate (plan.md section (e), Task 7):
        # If the cached plan has EXCLUDED-LOSSY warnings, require explicit
        # confirmation before writing.  This preserves "the only write is at
        # Move/Finish" (Principle III) while satisfying Principle V's
        # requirement that deliberate omissions be reported.
        el_count = len(getattr(self._cached_plan, "excluded_lossy", ()))
        if el_count:
            answer = QtWidgets.QMessageBox.question(
                self,
                "GramTrans — Missing references",
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
                return  # User cancelled — no write occurs.

        try:
            report = gt_api.execute_move(self._context, self._cached_plan)
        except gt_api.PreviewStale as e:
            QtWidgets.QMessageBox.critical(self, "GramTrans", str(e))
            return
        self._stats.set_report(report)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _collect_selection(self) -> Selection:
        cats = {cat: True for cat, cb in self._toggles.items() if cb.isChecked()}
        # Collect per-category scopes from the three-scope comboboxes.
        # Only include categories whose scope differs from the default (AS_NEEDED)
        # to keep the Selection compact; scope_for() falls back for missing entries.
        scope_combos = getattr(self, "_scope_combos", {})
        category_scopes = {}
        for cat, combo in scope_combos.items():
            scope = combo.currentData()
            if scope is not None:
                category_scopes[cat] = scope
        return Selection(
            categories=cats,
            include_closure=self._closure_cb.isChecked(),
            category_scopes=category_scopes,
        )

    def _collect_ws_mapping(self, required_payload) -> Optional[WSMapping]:
        pairs = required_payload.pairs
        if not pairs:
            return WSMapping(entries=())
        existing = _enumerate_target_ws_ids(self._context.target_handle)
        dlg = WSMappingDialog(pairs, existing, parent=self)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None
        return dlg.selected_mapping()

    def _invalidate_plan(self) -> None:
        self._cached_plan = None
        self._cached_plan_signature = None
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        target_ready = self._context is not None
        self._preview_btn.setEnabled(target_ready)
        # Move is enabled only after a current-selection Preview produced a plan.
        self._move_btn.setEnabled(False)


def _safe_path(flex_project) -> str:
    for attr in ("ProjectPath", "ProjectFilename", "ProjectFolder"):
        try:
            v = getattr(flex_project, attr)
            return v() if callable(v) else str(v)
        except Exception:
            continue
    return ""


def _enumerate_target_ws_ids(target) -> list:
    """Best-effort enumeration of target's existing WS IDs for the mapping
    dialog's combobox. Returns [] on any introspection failure — the user can
    still type a target WS ID and check `create_in_target`."""
    try:
        all_wss = list(target.GetWritingSystems())
        return [w.Id for w in all_wss]
    except Exception:
        return []

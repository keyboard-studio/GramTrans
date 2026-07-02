"""ConflictDialog (T026) -- PyQt6 implementation of the ConflictResolver
protocol from `Lib/conflict.py`.

Per [contracts/conflict-prompt.md], the dialog:
- Receives `tuple[ConflictPrompt, ...]`.
- Returns `tuple[MergeDecision, ...]` of the same length and order.
- Raises `UserCancelled` if the user clicks Cancel / closes the dialog.
- Pre-selects `prompt.prior_decision.resolution` when present (US3 recall).
- Hides the MERGE button when `prompt.merge_eligible is False` (scalars).

Layout (single-window, scrollable list -- batched per FR-214):
- Left pane: QListWidget of prompts (one row per conflict; class + field).
- Right pane: side-by-side QPlainTextEdit views for left/right values,
  a QButtonGroup of resolution radios, and a QLineEdit (visible only
  when EDIT_CUSTOM is selected) for the user-typed value.
- Bottom: Apply (commits resolutions, returns) / Cancel (raises
  UserCancelled).

Per research R8 this widget is NOT exercised by pytest -- the
FakeConflictResolver test double satisfies the same Protocol.  Live
verification is via FlexTools MCP / manual session.
"""
from __future__ import annotations

from typing import List, Optional

from PyQt6 import QtCore, QtWidgets

if __package__:
    from ..conflict import UserCancelled
    from ..models import MergeDecision, MergeResolution
else:
    from conflict import UserCancelled
    from models import MergeDecision, MergeResolution


_RESOLUTION_LABELS = [
    (MergeResolution.TAKE_SOURCE, "Take source"),
    (MergeResolution.KEEP_TARGET, "Keep target"),
    (MergeResolution.MERGE,       "Merge both"),
    (MergeResolution.SKIP,        "Skip this field"),
    (MergeResolution.EDIT_CUSTOM, "Edit custom value..."),
]


class ConflictDialog(QtWidgets.QDialog):
    """ConflictResolver implementation: shows all prompts in one batched
    window; user resolves each then clicks Apply."""

    def __init__(self, prompts, parent=None):
        super().__init__(parent)
        self._prompts = tuple(prompts)
        self._decisions: List[Optional[MergeDecision]] = [None] * len(self._prompts)
        self._build_ui()
        self._populate_list()
        if self._prompts:
            self._list.setCurrentRow(0)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.setWindowTitle("Resolve conflicts")
        self.resize(900, 600)
        outer = QtWidgets.QVBoxLayout(self)

        # Header explanation
        header = QtWidgets.QLabel(
            "Source and target both have non-empty values for these fields.\n"
            "Choose how to resolve each conflict.  All resolutions are\n"
            "applied together when you click Apply."
        )
        outer.addWidget(header)

        # Split: list on left, detail on right
        split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self._list = QtWidgets.QListWidget()
        self._list.currentRowChanged.connect(self._on_row_changed)
        split.addWidget(self._list)

        # Right detail pane
        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        self._field_label = QtWidgets.QLabel("(no conflict selected)")
        self._field_label.setStyleSheet("font-weight: bold;")
        right_layout.addWidget(self._field_label)
        self._prior_label = QtWidgets.QLabel("")
        self._prior_label.setStyleSheet("color: #666;")
        right_layout.addWidget(self._prior_label)

        # Side-by-side values
        values = QtWidgets.QHBoxLayout()
        left_box = QtWidgets.QVBoxLayout()
        left_box.addWidget(QtWidgets.QLabel("Target (left):"))
        self._left_view = QtWidgets.QPlainTextEdit()
        self._left_view.setReadOnly(True)
        left_box.addWidget(self._left_view)
        values.addLayout(left_box)
        right_box = QtWidgets.QVBoxLayout()
        right_box.addWidget(QtWidgets.QLabel("Source (right):"))
        self._right_view = QtWidgets.QPlainTextEdit()
        self._right_view.setReadOnly(True)
        right_box.addWidget(self._right_view)
        values.addLayout(right_box)
        right_layout.addLayout(values)

        # Resolution radios
        self._radio_group = QtWidgets.QButtonGroup(self)
        self._radio_widgets = {}
        radios_box = QtWidgets.QGroupBox("Resolution")
        radios_layout = QtWidgets.QVBoxLayout(radios_box)
        for resolution, label in _RESOLUTION_LABELS:
            radio = QtWidgets.QRadioButton(label)
            radio.toggled.connect(self._on_radio_toggled)
            self._radio_group.addButton(radio)
            self._radio_widgets[resolution] = radio
            radios_layout.addWidget(radio)
        right_layout.addWidget(radios_box)

        # Custom-value editor (visible only on EDIT_CUSTOM)
        self._custom_edit = QtWidgets.QLineEdit()
        self._custom_edit.setPlaceholderText("Type custom value, then click Apply")
        self._custom_edit.setVisible(False)
        right_layout.addWidget(self._custom_edit)

        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        outer.addWidget(split)

        # Bottom button bar
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Apply
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Apply
        ).clicked.connect(self._on_apply)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------

    def _populate_list(self):
        for p in self._prompts:
            item = QtWidgets.QListWidgetItem(
                f"{p.target_class_name}:{p.field_name} ({p.target_guid[:8]})"
            )
            self._list.addItem(item)

    def _current_index(self) -> int:
        return self._list.currentRow()

    def _on_row_changed(self, row: int):
        if row < 0 or row >= len(self._prompts):
            return
        p = self._prompts[row]
        self._field_label.setText(f"{p.target_class_name}.{p.field_name}")
        if p.prior_decision is not None:
            self._prior_label.setText(
                f"Prior decision from run {p.prior_decision.prior_run_id}: "
                f"{p.prior_decision.resolution.value}"
            )
        else:
            self._prior_label.setText("")
        self._left_view.setPlainText(str(p.left_value) if p.left_value is not None else "")
        self._right_view.setPlainText(str(p.right_value) if p.right_value is not None else "")
        # MERGE button hidden for scalars (FR-202 per merge_eligible)
        self._radio_widgets[MergeResolution.MERGE].setVisible(p.merge_eligible)
        # Pre-select either the prior decision or any cached current pick.
        cached = self._decisions[row]
        if cached is not None:
            self._radio_widgets[cached.resolution].setChecked(True)
            if cached.resolution == MergeResolution.EDIT_CUSTOM:
                self._custom_edit.setText(str(cached.custom_value or ""))
                self._custom_edit.setVisible(True)
            else:
                self._custom_edit.setVisible(False)
        elif p.prior_decision is not None:
            self._radio_widgets[p.prior_decision.resolution].setChecked(True)
        else:
            # No preselection.
            self._radio_group.setExclusive(False)
            for rb in self._radio_widgets.values():
                rb.setChecked(False)
            self._radio_group.setExclusive(True)
            self._custom_edit.setVisible(False)

    def _on_radio_toggled(self, checked: bool):
        if not checked:
            return
        is_custom = self._radio_widgets[MergeResolution.EDIT_CUSTOM].isChecked()
        self._custom_edit.setVisible(is_custom)

    # ------------------------------------------------------------------
    # Apply / Cancel
    # ------------------------------------------------------------------

    def _capture_current(self):
        """Save the current row's radio selection into self._decisions."""
        row = self._current_index()
        if row < 0:
            return
        p = self._prompts[row]
        resolution = None
        for r, rb in self._radio_widgets.items():
            if rb.isChecked():
                resolution = r
                break
        if resolution is None:
            return  # not yet answered
        custom_value = None
        prior_run_id = ""
        if resolution == MergeResolution.EDIT_CUSTOM:
            custom_value = self._custom_edit.text()
            if not custom_value:
                # Block apply: EDIT_CUSTOM requires a value.
                return
        elif (p.prior_decision is not None
              and p.prior_decision.resolution == resolution):
            # User accepted the pre-filled prior decision -- mark
            # carried-over per FR-208.
            prior_run_id = p.prior_decision.prior_run_id
        self._decisions[row] = MergeDecision(
            field_name=p.field_name,
            resolution=resolution,
            left_value=p.left_value,
            right_value=p.right_value,
            custom_value=custom_value,
            prior_run_id=prior_run_id,
        )

    def _on_apply(self):
        # Capture current row first, then validate the rest.
        self._capture_current()
        unresolved = [i for i, d in enumerate(self._decisions) if d is None]
        if unresolved:
            QtWidgets.QMessageBox.warning(
                self, "Unresolved conflicts",
                f"{len(unresolved)} conflict(s) still need a resolution.",
            )
            self._list.setCurrentRow(unresolved[0])
            return
        self.accept()

    # ------------------------------------------------------------------
    # Protocol surface (ConflictResolver)
    # ------------------------------------------------------------------

    def resolve(self, prompts):
        """Used by callers that construct a single ConflictDialog and
        invoke it as the resolver.

        Note: typical use is to instantiate ConflictDialog(prompts) and
        call exec_().  This method exists so a single dialog instance
        satisfies the structural Protocol (resolve(prompts) -> tuple).
        """
        if tuple(prompts) != self._prompts:
            # Re-init if caller passes a different prompt list.
            return ConflictDialog(prompts, parent=self.parent()).resolve(prompts)
        result = self.exec()
        if result != QtWidgets.QDialog.DialogCode.Accepted:
            raise UserCancelled("conflict dialog dismissed")
        return tuple(d for d in self._decisions if d is not None)

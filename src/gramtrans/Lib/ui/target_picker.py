"""Target project picker (T054, FR-003, Clarification Q2).

A single-select list of `TargetCandidate`s presented as a `QDialog`. The
list is enumerated by `Lib/api.list_target_candidates(stub)` — the picker
itself doesn't touch the filesystem or LCM.

Contract (per contracts/module-ui.md):
- Reads: `list[TargetCandidate]`
- Returns: the chosen `TargetCandidate` (or None on cancel)
- Forbidden: mutating any state besides its return value; opening the
  target itself (that's `api.bind_target`'s job).
"""
from __future__ import annotations

from typing import List, Optional

from PyQt6 import QtCore, QtWidgets

if __package__:
    from ..api import TargetCandidate
else:
    from api import TargetCandidate  # type: ignore


class TargetPickerDialog(QtWidgets.QDialog):
    """Modal dialog presenting a vertical list of FLEx target projects.

    Usage:
        dlg = TargetPickerDialog(candidates, parent=main_window)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            choice = dlg.selected_candidate()
            # → caller passes `choice` into api.bind_target(stub, choice)
    """

    def __init__(self,
                 candidates: List[TargetCandidate],
                 parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._candidates = list(candidates)
        self._selected_index: Optional[int] = None

        self.setWindowTitle("GramTrans — Pick target project")
        self.setModal(True)
        self.resize(520, 380)

        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel(
            "Choose the production project to transfer grammar pieces INTO.\n"
            "The current FlexTools project is always the SOURCE (read-only).",
            self,
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        self._list = QtWidgets.QListWidget(self)
        for cand in self._candidates:
            item = QtWidgets.QListWidgetItem(
                f"{cand.project_name}\n    {cand.project_path}",
                self._list,
            )
            item.setData(QtCore.Qt.ItemDataRole.UserRole, cand)
        layout.addWidget(self._list, 1)

        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        self._list.itemDoubleClicked.connect(lambda _: self.accept())

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
            QtCore.Qt.Orientation.Horizontal,
            self,
        )
        self._ok_button = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        self._ok_button.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_selection_changed(self) -> None:
        items = self._list.selectedItems()
        self._selected_index = self._list.row(items[0]) if items else None
        self._ok_button.setEnabled(self._selected_index is not None)

    def selected_candidate(self) -> Optional[TargetCandidate]:
        if self._selected_index is None:
            return None
        return self._candidates[self._selected_index]

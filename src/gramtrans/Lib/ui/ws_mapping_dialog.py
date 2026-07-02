"""Writing-system mapping dialog (T055, FR-011, Clarification Q3).

Modal dialog presenting every required `(source_ws_id, kind)` pair the
current Selection touches. The user maps each to an existing target WS or
flags it for creation. Confirm is disabled until every required row is
mapped.

Returns a `WSMapping` object the caller passes back to
`api.compute_preview(context, selection, ws_mapping)`.
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

from PyQt6 import QtCore, QtWidgets

if __package__:
    from ..models import WSKind, WSMapping, WSMappingEntry
else:
    from models import WSKind, WSMapping, WSMappingEntry  # type: ignore


class WSMappingDialog(QtWidgets.QDialog):
    """Each row in the table corresponds to one required source WS. The
    user picks either an existing target WS from a combo or types a new
    target WS ID + checks the "create" box."""

    def __init__(
        self,
        required: Iterable[Tuple[str, WSKind]],
        target_existing_ws_ids: Iterable[str],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._required: List[Tuple[str, WSKind]] = sorted(set(required), key=lambda x: (x[1].value, x[0]))
        self._target_existing = sorted(set(target_existing_ws_ids))

        self.setWindowTitle("GramTrans — Map source writing systems to target")
        self.setModal(True)
        self.resize(640, 420)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(
            "Map each source writing system to a target writing system.\n"
            "Map exactly 1:1. Phase 0 has no auto-mapping — every row must be set.",
            self,
        ))

        self._table = QtWidgets.QTableWidget(len(self._required), 4, self)
        self._table.setHorizontalHeaderLabels(["Source WS", "Kind", "Target WS", "Create in target?"])
        self._table.horizontalHeader().setStretchLastSection(True)
        for row, (src_id, kind) in enumerate(self._required):
            self._table.setItem(row, 0, QtWidgets.QTableWidgetItem(src_id))
            kind_item = QtWidgets.QTableWidgetItem(kind.value)
            kind_item.setFlags(kind_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 1, kind_item)

            combo = QtWidgets.QComboBox(self._table)
            combo.setEditable(True)
            combo.addItem("(choose…)")
            for existing in self._target_existing:
                combo.addItem(existing)
            # Pre-populate if the source ID matches an existing target ID — common case.
            if src_id in self._target_existing:
                combo.setCurrentText(src_id)
            combo.currentTextChanged.connect(self._refresh_ok)
            self._table.setCellWidget(row, 2, combo)

            check = QtWidgets.QCheckBox(self._table)
            check.toggled.connect(self._refresh_ok)
            self._table.setCellWidget(row, 3, check)
        layout.addWidget(self._table, 1)

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

        self._refresh_ok()

    def _row_target_id(self, row: int) -> str:
        combo = self._table.cellWidget(row, 2)
        text = combo.currentText().strip()
        if text == "(choose…)" or not text:
            return ""
        return text

    def _row_create_flag(self, row: int) -> bool:
        check = self._table.cellWidget(row, 3)
        return bool(check.isChecked())

    def _refresh_ok(self) -> None:
        complete = all(self._row_target_id(r) for r in range(self._table.rowCount()))
        self._ok_button.setEnabled(complete)

    def selected_mapping(self) -> WSMapping:
        entries: List[WSMappingEntry] = []
        for row, (src_id, kind) in enumerate(self._required):
            target_id = self._row_target_id(row)
            create = self._row_create_flag(row)
            if not target_id:
                # Shouldn't happen — UI gating refuses confirm otherwise.
                continue
            entries.append(WSMappingEntry(
                source_ws_id=src_id,
                source_ws_kind=kind,
                target_ws_id=target_id,
                create_in_target=create,
            ))
        return WSMapping(entries=tuple(entries))

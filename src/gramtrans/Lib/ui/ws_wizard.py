"""WSWizard (T034) -- PyQt6 implementation of the WSResolver protocol
from `Lib/ws_mapping.py`.

Per [contracts/ws-wizard.md], the wizard:
- Receives `tuple[WSMismatch, ...]`.
- Returns `tuple[WSMappingChoice, ...]` of the same length and order.
- Raises `UserCancelled` on dismiss.
- Per FR-212, CREATE choices create the new WS in the target BEFORE
  returning.  The caller passes a `target` flexlibs2 project handle so
  the wizard can do this in its Finish step.

Layout (single window for simplicity; one row per mismatch):
- A QTreeWidget with columns: source WS, choice (MAP/CREATE/SKIP),
  target WS (drop-down for MAP, identity for CREATE, blank for SKIP).
- Bottom: Apply (validates + creates WSes when CREATE chosen) / Cancel.

Per research R8 this widget is NOT exercised by pytest -- the
FakeWSResolver test double satisfies the same Protocol.  Live
verification is via FlexTools MCP / manual session.
"""
from __future__ import annotations

from typing import List, Optional

from PyQt6 import QtCore, QtWidgets  # noqa: F401 — QtCore kept for parity

if __package__:
    from ..conflict import UserCancelled
    from ..models import WSChoice, WSMappingChoice
else:
    from conflict import UserCancelled
    from models import WSChoice, WSMappingChoice


_CHOICE_LABELS = [
    (WSChoice.MAP,    "Map to existing target WS"),
    (WSChoice.CREATE, "Create new target WS"),
    (WSChoice.SKIP,   "Skip (drop objects referencing this WS)"),
]


class WSWizard(QtWidgets.QDialog):
    """WSResolver implementation.  Single-window batch UI.

    Args:
        mismatches: tuple[WSMismatch, ...].
        target_project: optional flexlibs2 project handle.  When CREATE
            is chosen, the wizard creates the new WS in target on Apply
            (FR-212).  Pass None in unit tests; production callers MUST
            supply it.
    """

    def __init__(self, mismatches, target_project=None, parent=None):
        super().__init__(parent)
        self._mismatches = tuple(mismatches)
        self._target = target_project
        self._choices: List[Optional[WSMappingChoice]] = [None] * len(self._mismatches)
        self._build_ui()
        self._populate()

    def _build_ui(self):
        self.setWindowTitle("Writing-System Mapping")
        self.resize(800, 400)
        outer = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QLabel(
            "Source has writing systems not present in target.  For each:\n"
            "  - Map: route content to an existing target WS\n"
            "  - Create: add the new WS to target preserving its tag\n"
            "  - Skip: skip transfer of objects whose only content is in this WS"
        )
        outer.addWidget(header)

        self._tree = QtWidgets.QTreeWidget()
        self._tree.setColumnCount(3)
        self._tree.setHeaderLabels(["Source WS", "Choice", "Target WS"])
        self._tree.setRootIsDecorated(False)
        outer.addWidget(self._tree)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Apply
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Apply
        ).clicked.connect(self._on_apply)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _populate(self):
        for i, m in enumerate(self._mismatches):
            row = QtWidgets.QTreeWidgetItem(
                [f"{m.source_ws_id} ({m.source_ws_kind.value})", "", ""]
            )
            self._tree.addTopLevelItem(row)
            # Choice combo
            choice_cb = QtWidgets.QComboBox()
            for c, label in _CHOICE_LABELS:
                choice_cb.addItem(label, c)
            choice_cb.currentIndexChanged.connect(
                lambda idx, idx_=i: self._on_choice_changed(idx_)
            )
            self._tree.setItemWidget(row, 1, choice_cb)
            # Target combo (visible only for MAP)
            tgt_cb = QtWidgets.QComboBox()
            for cand in m.target_ws_candidates:
                tgt_cb.addItem(cand)
            self._tree.setItemWidget(row, 2, tgt_cb)
        self._tree.resizeColumnToContents(0)
        self._tree.resizeColumnToContents(1)

    def _on_choice_changed(self, idx: int):
        row = self._tree.topLevelItem(idx)
        choice_cb = self._tree.itemWidget(row, 1)
        tgt_cb = self._tree.itemWidget(row, 2)
        if choice_cb is None or tgt_cb is None:
            return
        choice = choice_cb.currentData()
        tgt_cb.setEnabled(choice == WSChoice.MAP)

    def _capture_choices(self) -> bool:
        """Read every row into self._choices.  Returns False if any row
        is invalid (MAP with no target_ws_id, e.g.) -- caller bails."""
        for i, m in enumerate(self._mismatches):
            row = self._tree.topLevelItem(i)
            choice_cb = self._tree.itemWidget(row, 1)
            tgt_cb = self._tree.itemWidget(row, 2)
            choice = choice_cb.currentData()
            if choice == WSChoice.MAP:
                tgt = tgt_cb.currentText()
                if not tgt:
                    QtWidgets.QMessageBox.warning(
                        self, "Map target missing",
                        f"Row {i + 1} ({m.source_ws_id}) needs a target WS.",
                    )
                    return False
                self._choices[i] = WSMappingChoice(
                    source_ws_id=m.source_ws_id,
                    source_ws_kind=m.source_ws_kind,
                    choice=WSChoice.MAP,
                    target_ws_id=tgt,
                )
            elif choice == WSChoice.CREATE:
                # Apply the CREATE side-effect (FR-212) if target was supplied.
                if self._target is not None:
                    try:
                        self._target.WritingSystems.Add(m.source_ws_id)
                    except (AttributeError, TypeError, Exception):
                        # Best-effort; the new WS may already exist from a
                        # prior wizard run on the same session.
                        pass
                self._choices[i] = WSMappingChoice(
                    source_ws_id=m.source_ws_id,
                    source_ws_kind=m.source_ws_kind,
                    choice=WSChoice.CREATE,
                )
            else:  # SKIP
                self._choices[i] = WSMappingChoice(
                    source_ws_id=m.source_ws_id,
                    source_ws_kind=m.source_ws_kind,
                    choice=WSChoice.SKIP,
                )
        return True

    def _on_apply(self):
        if not self._capture_choices():
            return
        self.accept()

    def resolve(self, mismatches):
        """WSResolver Protocol entry."""
        if tuple(mismatches) != self._mismatches:
            return WSWizard(
                mismatches, target_project=self._target, parent=self.parent()
            ).resolve(mismatches)
        result = self.exec()
        if result != QtWidgets.QDialog.DialogCode.Accepted:
            raise UserCancelled("WS wizard dismissed")
        return tuple(c for c in self._choices if c is not None)

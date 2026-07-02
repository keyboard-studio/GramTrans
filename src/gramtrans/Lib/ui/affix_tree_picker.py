"""Affix tree picker (T074, FR-007, Clarification Q4).

A QTreeWidget organized as **Template → Slot → Affix**, with a top-level
"Unbound" bucket containing affixes not yet attached to any template.

Convenience-toggle semantics (verified by T072 unit tests in
`Lib/selection.py`):
- Checking a template implicitly selects every affix under it via slot
  membership.
- Checking a slot pulls in just that slot's affixes.
- Per-affix selection still works inside any branch.

Returns the picker's checked state as a `PickerState` from `Lib/selection.py`;
the caller passes it through `selection.build_selection(picker, inventory)`
to produce the canonical `Selection`.

[LEGACY / UNUSED in wizard path - T022, specs/008-affix-pos-picker R6]
The standalone `AffixTreePicker` dialog below is a pre-wizard entry point
and is NOT on the active wizard path.  The live item-picker surface on
wizard page 2 is `_PageItemPicker` in `Lib/ui/selection_wizard.py`, which
uses the new POS-grouped inventory (`build_pos_grouped_inventory` /
`PosGroupedAffixInventory`) from `Lib/selection.py`.  This dialog is
retained for the deferred template-grouping phase and its existing unit
tests (`test_affix_tree_selection.py`) remain green (they exercise the
`SourceAffixInventory` shape, which is unchanged).  Do not port the new
POS-grouping logic here until a non-wizard entry point is needed.
"""
from __future__ import annotations

from typing import Optional

from PyQt6 import QtCore, QtWidgets

if __package__:
    from ..selection import PickerState, SourceAffixInventory
else:
    from selection import PickerState, SourceAffixInventory  # type: ignore


# Roles used on QTreeWidgetItem so we can recover GUIDs at confirm time.
_GUID_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1
_KIND_ROLE = QtCore.Qt.ItemDataRole.UserRole + 2  # "template" | "slot" | "affix"


class AffixTreePicker(QtWidgets.QDialog):
    """Tree-style affix picker.

    Construct with the source's affix inventory; call `picker_state()` after
    Accepted to get a `PickerState` for downstream selection.build_selection().
    """

    def __init__(self,
                 inventory: SourceAffixInventory,
                 *,
                 affix_label_for: Optional[dict] = None,
                 slot_label_for: Optional[dict] = None,
                 template_label_for: Optional[dict] = None,
                 parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._inventory = inventory
        self._affix_label_for = affix_label_for or {}
        self._slot_label_for = slot_label_for or {}
        self._template_label_for = template_label_for or {}

        self.setWindowTitle("GramTrans — Pick affixes to transfer")
        self.setModal(True)
        self.resize(640, 540)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(
            "Check templates, slots, or individual affixes to include in the transfer.\n"
            "Checking a template selects all affixes under it; checking a slot selects only that slot's affixes.",
            self,
        ))

        self._tree = QtWidgets.QTreeWidget(self)
        self._tree.setColumnCount(1)
        self._tree.setHeaderLabels(["Affixes by template"])
        self._populate_tree()
        layout.addWidget(self._tree, 1)
        self._tree.itemChanged.connect(self._on_item_changed)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
            QtCore.Qt.Orientation.Horizontal,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    def _populate_tree(self) -> None:
        # Templates → slots → affixes
        for tpl_guid, slot_guids in self._inventory.template_to_slots.items():
            tpl_label = self._template_label_for.get(tpl_guid, tpl_guid)
            tpl_item = QtWidgets.QTreeWidgetItem(self._tree, [f"Template: {tpl_label}"])
            tpl_item.setData(0, _GUID_ROLE, tpl_guid)
            tpl_item.setData(0, _KIND_ROLE, "template")
            tpl_item.setFlags(tpl_item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsAutoTristate)
            tpl_item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
            for slot_guid in slot_guids:
                slot_label = self._slot_label_for.get(slot_guid, slot_guid)
                slot_item = QtWidgets.QTreeWidgetItem(tpl_item, [f"Slot: {slot_label}"])
                slot_item.setData(0, _GUID_ROLE, slot_guid)
                slot_item.setData(0, _KIND_ROLE, "slot")
                slot_item.setFlags(slot_item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsAutoTristate)
                slot_item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
                for affix_guid in self._inventory.slot_to_affixes.get(slot_guid, ()):
                    affix_label = self._affix_label_for.get(affix_guid, affix_guid)
                    affix_item = QtWidgets.QTreeWidgetItem(slot_item, [affix_label])
                    affix_item.setData(0, _GUID_ROLE, affix_guid)
                    affix_item.setData(0, _KIND_ROLE, "affix")
                    affix_item.setFlags(affix_item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                    affix_item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)

        # Unbound bucket
        if self._inventory.unbound_affixes:
            unbound = QtWidgets.QTreeWidgetItem(self._tree, ["Unbound (not attached to any template)"])
            unbound.setFlags(unbound.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsAutoTristate)
            unbound.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
            for affix_guid in sorted(self._inventory.unbound_affixes):
                affix_label = self._affix_label_for.get(affix_guid, affix_guid)
                ai = QtWidgets.QTreeWidgetItem(unbound, [affix_label])
                ai.setData(0, _GUID_ROLE, affix_guid)
                ai.setData(0, _KIND_ROLE, "affix")
                ai.setFlags(ai.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                ai.setCheckState(0, QtCore.Qt.CheckState.Unchecked)

        self._tree.expandAll()

    # ------------------------------------------------------------------
    def _on_item_changed(self, item, column: int) -> None:
        # Qt's auto-tristate handles parent/child propagation. We only need
        # to react if we want extra behavior (logging, validation). Stub.
        pass

    # ------------------------------------------------------------------
    def picker_state(self) -> PickerState:
        """Collapse the tree's checked state into a `PickerState`.

        Rules:
        - A template fully-checked (all descendants checked) → in `checked_templates`.
        - A slot fully-checked → in `checked_slots`. (When the template above
          is fully-checked, we still record both — `compute_required_affixes`
          handles either form.)
        - Any leaf affix individually checked → in `checked_affixes`.
        """
        checked_templates = set()
        checked_slots = set()
        checked_affixes = set()

        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            top = root.child(i)
            kind = top.data(0, _KIND_ROLE)
            if kind == "template":
                if top.checkState(0) == QtCore.Qt.CheckState.Checked:
                    checked_templates.add(top.data(0, _GUID_ROLE))
                # Descend regardless — partial-check slots / affixes still count.
                for j in range(top.childCount()):
                    slot_item = top.child(j)
                    if slot_item.checkState(0) == QtCore.Qt.CheckState.Checked:
                        checked_slots.add(slot_item.data(0, _GUID_ROLE))
                    for k in range(slot_item.childCount()):
                        a = slot_item.child(k)
                        if a.checkState(0) == QtCore.Qt.CheckState.Checked:
                            checked_affixes.add(a.data(0, _GUID_ROLE))
            else:
                # Unbound bucket — iterate affixes directly.
                for j in range(top.childCount()):
                    a = top.child(j)
                    if a.checkState(0) == QtCore.Qt.CheckState.Checked:
                        checked_affixes.add(a.data(0, _GUID_ROLE))

        return PickerState(
            checked_templates=frozenset(checked_templates),
            checked_slots=frozenset(checked_slots),
            checked_affixes=frozenset(checked_affixes),
        )

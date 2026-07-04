"""Merge-Preview Pane widget (feature 014).

Single-item diff viewer docked into each selection-wizard page.  Renders a
``MergePreview`` via ``to_html`` (feature 012) and — for SIMILAR affix rows
on ``_PageItemPicker`` — shows a resolution header (combo + three-way radio)
that emits ``resolution_changed`` when the user changes the action or target.

Design constants (plan.md):
- R1 mode mapping: overwrite->OVERWRITE, merge->MERGE_KEEP, create_new->NEW
- R2 cache-key discipline: 4-tuple; no invalidate() on flip
- R3 default seed: overwrite(guid -> suggested_target_guid)
- R5 resolvable: True only for SIMILAR affix rows on _PageItemPicker
- LINK_ONLY is imported below for completeness but is NOT a valid 014 pane mode;
  valid modes are OVERWRITE, MERGE_KEEP, NEW only (per R1).
"""
from __future__ import annotations

import dataclasses
from typing import List, Optional, Tuple

if __package__:
    from ..models import SimilarResolution
    from ..merge_preview import (
        MergePreviewService,
        MergePreview,
        to_html,
        OVERWRITE,
        MERGE_KEEP,
        NEW,
        LINK_ONLY,  # imported for completeness; NOT wired into any 014 mode
    )
    from ..ws_fonts import WsFontRegistry
else:
    from models import SimilarResolution  # type: ignore
    from merge_preview import (  # type: ignore
        MergePreviewService,
        MergePreview,
        to_html,
        OVERWRITE,
        MERGE_KEEP,
        NEW,
        LINK_ONLY,
    )
    from ws_fonts import WsFontRegistry  # type: ignore


# ---------------------------------------------------------------------------
# PreviewRequest dataclass (FR-002, R5)
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class PreviewRequest:
    """UI-layer carrier built from a selected tree row.

    ``mode`` MUST be one of OVERWRITE, MERGE_KEEP, NEW (never LINK_ONLY in
    014 pane context — see module docstring).
    """
    category: str
    source_guid: str
    target_guid: str        # "" for NEW / create_new
    status: str             # "new" | "in_target" | "similar"
    mode: str               # OVERWRITE | MERGE_KEEP | NEW
    resolvable: bool        # True only for affix SIMILAR on _PageItemPicker
    current_resolution: Optional[SimilarResolution]
    owner_guid: str = ""


# ---------------------------------------------------------------------------
# Action -> mode mapping (R1)
# ---------------------------------------------------------------------------

_ACTION_TO_MODE = {
    "overwrite": OVERWRITE,
    "merge": MERGE_KEEP,
    "create_new": NEW,
}


def _action_to_mode(action: str) -> str:
    """Map a SimilarResolution action string to a 012 mode constant (R1).

    Raises ValueError for unknown action strings so the caller fails before
    any resolution_changed signal is emitted with a half-built resolution.
    """
    try:
        return _ACTION_TO_MODE[action]
    except KeyError:
        raise ValueError("unknown action: %r" % action)


# ---------------------------------------------------------------------------
# Qt guard: pane is importable in headless test environments
# ---------------------------------------------------------------------------

try:
    from PyQt6 import QtCore, QtWidgets
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False


# ---------------------------------------------------------------------------
# MergePreviewPane widget
# ---------------------------------------------------------------------------

if _QT_AVAILABLE:
    class MergePreviewPane(QtWidgets.QWidget):
        """Horizontal pane: HTML diff viewer + optional resolution header.

        Public API (FR-002):
            set_context(service, registry, candidates)
            show_item(request: PreviewRequest)
            clear()
            resolution_changed  -- pyqtSignal(str, object)

        The resolution header is shown only when ``request.resolvable`` is True
        (SIMILAR affix rows on _PageItemPicker, per R5).
        """

        resolution_changed = QtCore.pyqtSignal(str, object)

        def __init__(self, parent=None):
            super().__init__(parent)
            self._service: Optional[MergePreviewService] = None
            self._registry: Optional[WsFontRegistry] = None
            self._candidates: List[Tuple[str, str, str]] = []
            self._current_request: Optional[PreviewRequest] = None
            self._build_ui()

        # ------------------------------------------------------------------
        def _build_ui(self) -> None:
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)

            # Resolution header (combo + radio buttons) — shown only when resolvable
            self._resolution_header = QtWidgets.QWidget(self)
            header_layout = QtWidgets.QVBoxLayout(self._resolution_header)
            header_layout.setContentsMargins(4, 4, 4, 4)

            # Target-combo label + combo
            combo_row = QtWidgets.QHBoxLayout()
            combo_row.addWidget(QtWidgets.QLabel("Target entry:", self._resolution_header))
            self._combo = QtWidgets.QComboBox(self._resolution_header)
            self._combo.setEditable(True)
            self._combo.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
            if hasattr(self._combo, "lineEdit") and self._combo.lineEdit():
                self._combo.lineEdit().setPlaceholderText("Type to filter...")
            combo_row.addWidget(self._combo, 1)
            header_layout.addLayout(combo_row)

            # Radio buttons for action
            radio_row = QtWidgets.QHBoxLayout()
            self._btn_group = QtWidgets.QButtonGroup(self._resolution_header)
            self._btn_overwrite = QtWidgets.QRadioButton("Overwrite", self._resolution_header)
            self._btn_merge = QtWidgets.QRadioButton("Merge", self._resolution_header)
            self._btn_create_new = QtWidgets.QRadioButton("Create new", self._resolution_header)
            self._btn_group.addButton(self._btn_overwrite)
            self._btn_group.addButton(self._btn_merge)
            self._btn_group.addButton(self._btn_create_new)
            radio_row.addWidget(self._btn_overwrite)
            radio_row.addWidget(self._btn_merge)
            radio_row.addWidget(self._btn_create_new)
            radio_row.addStretch(1)
            header_layout.addLayout(radio_row)

            layout.addWidget(self._resolution_header)
            self._resolution_header.setVisible(False)

            # HTML viewer
            self._browser = QtWidgets.QTextBrowser(self)
            self._browser.setOpenExternalLinks(False)
            layout.addWidget(self._browser, 1)

            # Wire signals
            self._combo.currentIndexChanged.connect(self._on_resolution_control_changed)
            self._btn_overwrite.toggled.connect(self._on_resolution_control_changed)
            self._btn_merge.toggled.connect(self._on_resolution_control_changed)
            self._btn_create_new.toggled.connect(self._on_resolution_control_changed)

        # ------------------------------------------------------------------
        def set_context(
            self,
            service: MergePreviewService,
            registry: WsFontRegistry,
            candidates: List[Tuple[str, str, str]],
        ) -> None:
            """Store service/registry/candidates and reset display (FR-006)."""
            self._service = service
            self._registry = registry
            self._candidates = list(candidates)
            self.clear()

        # ------------------------------------------------------------------
        def show_item(self, request: PreviewRequest) -> None:
            """Render a diff for the given request (FR-002, FR-003)."""
            if request is None:
                self.clear()
                return
            self._current_request = request
            self._resolution_header.setVisible(request.resolvable)

            if request.resolvable:
                # Block signals during initialisation to avoid spurious emissions
                self._combo.blockSignals(True)
                self._btn_overwrite.blockSignals(True)
                self._btn_merge.blockSignals(True)
                self._btn_create_new.blockSignals(True)
                try:
                    self._populate_combo(self._candidates)
                    # Set combo to current resolution's target GUID
                    res = request.current_resolution
                    if res is not None:
                        self._set_combo_to_guid(res.target_guid or "")
                        action = res.action
                    else:
                        action = "overwrite"
                    # Set radio button
                    if action == "overwrite":
                        self._btn_overwrite.setChecked(True)
                    elif action == "merge":
                        self._btn_merge.setChecked(True)
                    else:
                        self._btn_create_new.setChecked(True)
                    # Enable/disable combo per action
                    self._combo.setEnabled(action != "create_new")
                finally:
                    self._combo.blockSignals(False)
                    self._btn_overwrite.blockSignals(False)
                    self._btn_merge.blockSignals(False)
                    self._btn_create_new.blockSignals(False)

            self._render_preview(
                request.category,
                request.source_guid,
                request.target_guid,
                request.status,
                request.mode,
                request.owner_guid,
            )

        # ------------------------------------------------------------------
        def clear(self) -> None:
            """Reset to post-__init__ state (FR-002)."""
            self._current_request = None
            self._browser.clear()
            self._resolution_header.setVisible(False)

        # ------------------------------------------------------------------
        def _populate_combo(self, candidates: List[Tuple[str, str, str]]) -> None:
            """Fill the combo with (guid, form, gloss) triples (FR-003).

            Each item displays "form — gloss" (em dash) and stores the
            GUID as UserRole data.  The combo is searchable via the editable
            line edit.  Filtering is left to the built-in completer; the
            full candidate list is always present in the model.
            """
            self._combo.clear()
            for guid, form, gloss in candidates:
                display = f"{form} — {gloss}" if gloss else form
                self._combo.addItem(display, guid)

        def _set_combo_to_guid(self, target_guid: str) -> None:
            """Select the combo entry whose UserRole data matches target_guid."""
            for i in range(self._combo.count()):
                if self._combo.itemData(i, QtCore.Qt.ItemDataRole.UserRole) == target_guid:
                    self._combo.setCurrentIndex(i)
                    return
            # If not found, leave at index 0 (or -1 for empty)

        def _current_target_guid(self) -> str:
            """Read the GUID stored on the currently selected combo item."""
            idx = self._combo.currentIndex()
            if idx < 0:
                return ""
            data = self._combo.itemData(idx, QtCore.Qt.ItemDataRole.UserRole)
            return data or ""

        def _current_action(self) -> str:
            """Read the active radio button as an action string."""
            if self._btn_create_new.isChecked():
                return "create_new"
            if self._btn_merge.isChecked():
                return "merge"
            return "overwrite"

        # ------------------------------------------------------------------
        def _on_resolution_control_changed(self, *args) -> None:
            """Handle combo or radio changes (FR-004).

            Guard: if action != "create_new" and no target GUID, do not emit.
            No invalidate() call — distinct 4-tuple key is sufficient (R2).
            """
            if self._current_request is None:
                return
            request = self._current_request
            new_action = self._current_action()
            new_target_guid = self._current_target_guid() if new_action != "create_new" else ""

            # Enable/disable combo
            self._combo.setEnabled(new_action != "create_new")

            if new_action != "create_new" and not new_target_guid:
                # No valid target -- do not emit (FR-003 guard)
                return

            entry_guid = request.source_guid
            resolution = SimilarResolution(
                entry_guid=entry_guid,
                action=new_action,
                target_guid=new_target_guid if new_action != "create_new" else None,
            )
            self.resolution_changed.emit(entry_guid, resolution)

            # Recompute and render the diff with the new mode (FR-004)
            new_mode = _action_to_mode(new_action)
            self._render_preview(
                request.category,
                request.source_guid,
                new_target_guid,
                request.status,
                new_mode,
                request.owner_guid,
            )

        # ------------------------------------------------------------------
        def _render_preview(
            self,
            category: str,
            source_guid: str,
            target_guid: str,
            status: str,
            mode: str,
            owner_guid: str = "",
        ) -> None:
            """Call service.preview_for and set HTML on the browser."""
            if self._service is None:
                self._browser.setHtml("<p>(No service bound)</p>")
                return
            try:
                preview = self._service.preview_for(
                    category, source_guid, target_guid, status, mode, owner_guid
                )
                registry = self._registry
                html_str = to_html(preview, registry)
                self._browser.setHtml(html_str)
            except Exception as exc:  # noqa: BLE001
                self._browser.setHtml(
                    f"<p><em>Preview error: {exc}</em></p>"
                )

else:
    # Headless stub: importable without PyQt6 (SC-007 / tests)
    class MergePreviewPane:  # type: ignore[no-redef]
        """Headless stub used when PyQt6 is not available."""

        # Mimic the signal API minimally
        class _Stub:
            def emit(self, *args):
                pass
            def connect(self, *args):
                pass

        resolution_changed = _Stub()

        def __init__(self, parent=None):
            self._service = None
            self._registry = None
            self._candidates: list = []
            self._current_request = None

        def set_context(self, service, registry, candidates):
            self._service = service
            self._registry = registry
            self._candidates = list(candidates)
            self.clear()

        def show_item(self, request):
            self._current_request = request

        def clear(self):
            self._current_request = None

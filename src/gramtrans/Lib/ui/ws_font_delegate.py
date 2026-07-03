"""Per-writing-system font delegate for the selection wizard (spec 011).

A ``QStyledItemDelegate`` that paints a tree cell as a sequence of WS-tagged
runs, each in the font FLEx defines for that writing system: a phoneme cell
renders its grapheme in the vernacular font and ``/j/`` in the IPA font; an
affix cell renders the lexeme form in the vernacular font and the gloss in the
analysis font -- within one cell.

Cells with no run metadata (chrome, counts, status badges, un-migrated columns)
fall straight through to the base delegate, so installing this on a column is
safe even where most rows are plain text. Runs are attached to an item with
:func:`set_ws_runs`; the delegate is installed with
:func:`attach_ws_font_delegate`.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets

from ..ws_fonts import LabelRun, WsFont, WsFontRegistry, WsRole

# Item data role holding the tuple[LabelRun, ...] for a cell. High offset so it
# never collides with the wizard's other UserRole payloads.
WS_RUNS_ROLE = int(QtCore.Qt.ItemDataRole.UserRole) + 4200


def set_ws_runs(item: "QtWidgets.QTreeWidgetItem", column: int,
                runs: Tuple[LabelRun, ...]) -> None:
    """Attach WS-tagged runs to a tree item cell for per-WS rendering.

    No-op for a single ``None``-role run (nothing to gain over the default
    font), which keeps chrome cells out of the delegate's slow path.
    """
    if not runs:
        return
    if len(runs) == 1 and runs[0][1] is None:
        return
    item.setData(column, WS_RUNS_ROLE, tuple(runs))


def attach_ws_font_delegate(tree: "QtWidgets.QTreeWidget", columns,
                            registry: Optional[WsFontRegistry]) -> "WsFontDelegate":
    """Install a WsFontDelegate on the given columns of a tree.

    Kept alive by stashing it on the tree (Qt does not take Python ownership of
    a per-column delegate). Re-invoking replaces the prior delegate, so a page
    that rebuilds on every ``initializePage`` stays correct.
    """
    delegate = WsFontDelegate(registry or WsFontRegistry.empty(), tree)
    for col in columns:
        tree.setItemDelegateForColumn(col, delegate)
    # Retain a reference; setItemDelegateForColumn does not own it Python-side.
    tree._ws_font_delegate = delegate  # type: ignore[attr-defined]
    return delegate


class WsFontDelegate(QtWidgets.QStyledItemDelegate):
    """Paints WS-tagged runs, each in its writing system's FLEx font."""

    def __init__(self, registry: WsFontRegistry, parent=None):
        super().__init__(parent)
        self._registry = registry
        self._qfont_cache: Dict[Tuple[str, int, bool, bool], QtGui.QFont] = {}

    # -- font resolution --------------------------------------------------
    def _qfont_for(self, role: Optional[WsRole],
                   base: QtGui.QFont) -> QtGui.QFont:
        """QFont for a run's role: FLEx font *family* at the base font's size.

        Only the family is taken from the WS; point size, bold and italic are
        inherited from the item's own font so rows keep their existing sizing
        (and header bolding). Role ``None`` (separators, guid fallbacks) uses
        the base font unchanged.
        """
        ws_font: Optional[WsFont] = self._registry.font_for(role)
        if ws_font is None:
            return base
        # Key on the base size so a font-size change elsewhere never stales.
        key = (ws_font.font_name, base.pointSizeF(),
               base.pixelSize(), base.bold(), base.italic())
        cached = self._qfont_cache.get(key)
        if cached is None:
            cached = QtGui.QFont(base)  # copy size/weight/style from the item
            cached.setFamily(ws_font.font_name)
            self._qfont_cache[key] = cached
        return cached

    # -- painting ---------------------------------------------------------
    def paint(self, painter, option, index):  # noqa: N802 (Qt override)
        runs = index.data(WS_RUNS_ROLE)
        if not runs:
            super().paint(painter, option, index)
            return

        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget = opt.widget
        style = widget.style() if widget is not None else QtWidgets.QApplication.style()

        # Draw the item chrome (background, selection, check indicator, focus)
        # WITHOUT its text; we render the WS runs into the text sub-rect below.
        opt.text = ""
        style.drawControl(
            QtWidgets.QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget
        )
        text_rect = style.subElementRect(
            QtWidgets.QStyle.SubElement.SE_ItemViewItemText, opt, widget
        )

        selected = bool(opt.state & QtWidgets.QStyle.StateFlag.State_Selected)
        enabled = bool(opt.state & QtWidgets.QStyle.StateFlag.State_Enabled)
        cg = (QtGui.QPalette.ColorGroup.Normal if enabled
              else QtGui.QPalette.ColorGroup.Disabled)
        pen_role = (QtGui.QPalette.ColorRole.HighlightedText if selected
                    else QtGui.QPalette.ColorRole.Text)

        painter.save()
        painter.setClipRect(text_rect)
        painter.setPen(opt.palette.color(cg, pen_role))
        x = text_rect.left()
        for text, run_role in runs:
            if not text:
                continue
            font = self._qfont_for(run_role, opt.font)
            painter.setFont(font)
            fm = QtGui.QFontMetrics(font)
            baseline = (text_rect.top()
                        + (text_rect.height() + fm.ascent() - fm.descent()) // 2)
            painter.drawText(x, baseline, text)
            x += fm.horizontalAdvance(text)
            if x >= text_rect.right():
                break
        painter.restore()

    def sizeHint(self, option, index):  # noqa: N802 (Qt override)
        runs = index.data(WS_RUNS_ROLE)
        base = super().sizeHint(option, index)
        if not runs:
            return base
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        width = 0
        height = base.height()
        for text, run_role in runs:
            font = self._qfont_for(run_role, opt.font)
            fm = QtGui.QFontMetrics(font)
            width += fm.horizontalAdvance(text)
            height = max(height, fm.height())
        # Pad for the check indicator / cell margins the base hint accounts for
        # but our width computation does not.
        widget = opt.widget
        style = widget.style() if widget is not None else QtWidgets.QApplication.style()
        margin = 2 * style.pixelMetric(
            QtWidgets.QStyle.PixelMetric.PM_FocusFrameHMargin, opt, widget
        )
        indicator = 0
        if opt.features & QtWidgets.QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator:
            indicator = style.pixelMetric(
                QtWidgets.QStyle.PixelMetric.PM_IndicatorWidth, opt, widget
            ) + margin
        return QtCore.QSize(width + margin + indicator + 4, height)

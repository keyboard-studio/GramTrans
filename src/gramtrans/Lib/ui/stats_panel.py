"""Run-report statistics panel (T056, T066, FR-017).

Renders a `RunReport` (E6) as a tabular view inside the main window. Per
contracts/run-report.md the display lists:

- Per-category counts: added | skipped | closure_pulled_in
- Skip list with reasons
- Identity remap section (only shown when non-empty per R6)

Read-only — the panel never mutates the report.
"""
from __future__ import annotations

from typing import Optional

from PyQt6 import QtCore, QtWidgets

if __package__:
    from ..models import GrammarCategory, RunMode, RunReport
    from ..report import render_text_summary
else:
    from models import GrammarCategory, RunMode, RunReport  # type: ignore
    from report import render_text_summary  # type: ignore

# Stylesheet constants for EXCLUDED-LOSSY warning rows.
_WARNING_BG = "#fff3cd"   # amber tint
_WARNING_FG = "#856404"   # dark amber text


class StatsPanel(QtWidgets.QWidget):
    """Bottom-panel widget shown after Preview or Move completes."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)

        self._header = QtWidgets.QLabel("(No run yet — click Preview.)", self)
        self._header.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._header)

        # Per-category table — 5 columns: Category, Added, Skipped,
        # Pulled in by closure, Excluded-lossy (warn+allow).
        self._table = QtWidgets.QTableWidget(0, 5, self)
        self._table.setHorizontalHeaderLabels(
            ["Category", "Added", "Skipped", "Pulled in by closure", "Excl-lossy"]
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        layout.addWidget(self._table, 2)

        # EXCLUDED-LOSSY warning list (distinct severity — not error, not skip).
        warn_label = QtWidgets.QLabel(
            "Warnings (entries with missing references -- deliberate, warn+allow):", self
        )
        warn_label.setStyleSheet(f"color: {_WARNING_FG}; font-weight: bold;")
        layout.addWidget(warn_label)
        self._warn_view = QtWidgets.QPlainTextEdit(self)
        self._warn_view.setReadOnly(True)
        self._warn_view.setMaximumBlockCount(500)
        self._warn_view.setStyleSheet(f"background: {_WARNING_BG};")
        layout.addWidget(self._warn_view, 1)

        # Skip list
        skip_label = QtWidgets.QLabel("Skips (FR-018: every selected item appears here or in counts above):", self)
        layout.addWidget(skip_label)
        self._skip_view = QtWidgets.QPlainTextEdit(self)
        self._skip_view.setReadOnly(True)
        self._skip_view.setMaximumBlockCount(2000)
        layout.addWidget(self._skip_view, 1)

        # Identity remap (hidden unless non-empty)
        self._remap_label = QtWidgets.QLabel("Identity remap (LCM denied GUID-on-create):", self)
        self._remap_view = QtWidgets.QPlainTextEdit(self)
        self._remap_view.setReadOnly(True)
        self._remap_label.setVisible(False)
        self._remap_view.setVisible(False)
        layout.addWidget(self._remap_label)
        layout.addWidget(self._remap_view)

        # Wall-clock footer
        self._footer = QtWidgets.QLabel("", self)
        layout.addWidget(self._footer)

    def set_report(self, report: RunReport) -> None:
        mode_word = "Preview" if report.mode is RunMode.PREVIEW else "Move"
        self._header.setText(
            f"{mode_word} run · run_id={report.context.run_id} · "
            f"source={report.context.source_project_name!r} → target={report.context.target_project_name!r}"
        )

        cats = sorted(report.per_category.keys(), key=lambda c: c.value)
        self._table.setRowCount(len(cats))
        for row, cat in enumerate(cats):
            r = report.per_category[cat]
            self._table.setItem(row, 0, QtWidgets.QTableWidgetItem(cat.value))
            self._table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(r.added)))
            self._table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(r.skipped)))
            self._table.setItem(row, 3, QtWidgets.QTableWidgetItem(str(r.closure_pulled_in)))
            el_count = getattr(r, "excluded_lossy", 0)
            el_item = QtWidgets.QTableWidgetItem(str(el_count) if el_count else "")
            if el_count:
                el_item.setForeground(QtWidgets.QApplication.palette().windowText())
            self._table.setItem(row, 4, el_item)

        # Render EXCLUDED-LOSSY warnings (distinct severity, entry-centric).
        el_list = getattr(report, "excluded_lossy", ())
        if el_list:
            lines = [f"[WARN] {el.message}" for el in el_list]
            self._warn_view.setPlainText("\n".join(lines))
            self._warn_view.setVisible(True)
        else:
            self._warn_view.setPlainText("(no warnings)")
            self._warn_view.setVisible(True)

        if report.skips:
            lines = []
            for s in report.skips:
                lines.append(f"[{s.category.value}] {s.source_guid}  {s.reason.value}: {s.detail}")
            self._skip_view.setPlainText("\n".join(lines))
        else:
            self._skip_view.setPlainText("(no skips)")

        if report.identity_remap:
            self._remap_label.setVisible(True)
            self._remap_view.setVisible(True)
            self._remap_view.setPlainText(
                "\n".join(f"{src} -> {dst}" for src, dst in sorted(report.identity_remap.items()))
            )
        else:
            self._remap_label.setVisible(False)
            self._remap_view.setVisible(False)

        self._footer.setText(f"Wall clock: {report.wall_clock_seconds:.3f}s")

    def render_text(self, report: RunReport) -> str:
        """Helper for tests / report-pane fallback. Uses
        `Lib/report.render_text_summary` directly."""
        return "\n".join(render_text_summary(report))

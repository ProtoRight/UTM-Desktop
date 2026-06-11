"""Non-modal dialog for manually including / excluding individual data points.

The dialog shows all post-preprocessing data points in a table.  Unchecking a
row marks that point as excluded — the graph and calculated results update live
via the ``exclusions_changed`` signal.  All points are still exported to CSV;
excluded rows get a "Y" marker in the dedicated column.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView,
)


class DataEditorDialog(QDialog):
    """Floating tool window — stays open while the user examines the graph."""

    exclusions_changed = pyqtSignal(set)   # set[int] of excluded row indices

    def __init__(self, parent=None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowTitle("Edit Data Points")
        self.resize(420, 520)
        self._updating = False   # guard against re-entrant itemChanged signals
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Top toolbar
        top = QHBoxLayout()
        self._btn_all  = QPushButton("Select All")
        self._btn_none = QPushButton("Deselect All")
        self._status   = QLabel("No data loaded")
        self._status.setStyleSheet("color: #888; font-size: 8pt;")
        top.addWidget(self._btn_all)
        top.addWidget(self._btn_none)
        top.addStretch()
        top.addWidget(self._status)
        layout.addLayout(top)

        hint = QLabel(
            "Uncheck rows to exclude points from calculations and the graph.\n"
            "All points are always exported to CSV (excluded rows are flagged)."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 8pt;")
        layout.addWidget(hint)

        # Table
        self._tbl = QTableWidget(0, 4)
        self._tbl.setHorizontalHeaderLabels(["#", "Disp (mm)", "Load (kg)", "Include?"])
        hdr = self._tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tbl.verticalHeader().setVisible(False)
        layout.addWidget(self._tbl)

        # Connections
        self._btn_all.clicked.connect(self._select_all)
        self._btn_none.clicked.connect(self._deselect_all)
        self._tbl.itemChanged.connect(self._on_item_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_data(
        self,
        disp_list: list[float],
        load_list: list[float],
        excluded: set,
    ) -> None:
        """Populate the table.  Call whenever new test data is available."""
        self._updating = True
        self._tbl.setRowCount(len(disp_list))

        for i, (d, f) in enumerate(zip(disp_list, load_list)):
            def _ro(text: str) -> QTableWidgetItem:
                it = QTableWidgetItem(text)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                return it

            self._tbl.setItem(i, 0, _ro(str(i)))
            self._tbl.setItem(i, 1, _ro(f"{d:.4f}"))
            self._tbl.setItem(i, 2, _ro(f"{f:.4f}"))

            chk = QTableWidgetItem()
            chk.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            chk.setCheckState(
                Qt.CheckState.Unchecked if i in excluded
                else Qt.CheckState.Checked
            )
            self._tbl.setItem(i, 3, chk)

        self._updating = False
        self._refresh_status()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or item.column() != 3:
            return
        self._emit()

    def _emit(self) -> None:
        excluded: set[int] = set()
        for row in range(self._tbl.rowCount()):
            it = self._tbl.item(row, 3)
            if it and it.checkState() == Qt.CheckState.Unchecked:
                excluded.add(row)
        self._refresh_status(excluded)
        self.exclusions_changed.emit(excluded)

    def _refresh_status(self, excluded: set | None = None) -> None:
        n = self._tbl.rowCount()
        if excluded is None:
            excluded = {
                r for r in range(n)
                if (it := self._tbl.item(r, 3))
                and it.checkState() == Qt.CheckState.Unchecked
            }
        inc = n - len(excluded)
        self._status.setText(f"{inc} of {n} points included")

    def _select_all(self) -> None:
        self._updating = True
        for r in range(self._tbl.rowCount()):
            it = self._tbl.item(r, 3)
            if it:
                it.setCheckState(Qt.CheckState.Checked)
        self._updating = False
        self._emit()

    def _deselect_all(self) -> None:
        self._updating = True
        for r in range(self._tbl.rowCount()):
            it = self._tbl.item(r, 3)
            if it:
                it.setCheckState(Qt.CheckState.Unchecked)
        self._updating = False
        self._emit()

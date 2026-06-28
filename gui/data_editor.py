"""Non-modal dialog for manually including / excluding individual data points.

The dialog shows all post-preprocessing data points in a table.  Unchecking a
row marks that point as excluded — the graph and calculated results update live
via the ``exclusions_changed`` signal.  All points are still exported to CSV;
excluded rows get a "Y" marker in the dedicated column.

Rows falling within the modulus chord window are highlighted so the user can
see which points drive the modulus calculation.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView,
)

_COL_IDX   = 0
_COL_DISP  = 1
_COL_LOAD  = 2
_COL_CHORD = 3
_COL_INC   = 4

_CLR_ONSET = QColor(180, 150, 40)    # amber — onset region
_CLR_CHORD = QColor(60, 180, 120)    # teal-green — in chord window


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
        self.resize(520, 540)
        self._updating = False
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

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
            "All points are exported to CSV (excluded rows flagged).  "
            "Chord window rows are highlighted — excluding them may reduce modulus accuracy."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 8pt;")
        layout.addWidget(hint)

        # Legend
        legend = QHBoxLayout()
        for colour, text in ((_CLR_ONSET, "onset region"), (_CLR_CHORD, "chord ε₁→ε₂")):
            dot = QLabel("●")
            dot.setStyleSheet(f"color: rgb({colour.red()},{colour.green()},{colour.blue()}); font-size: 11pt;")
            legend.addWidget(dot)
            legend.addWidget(QLabel(text))
            legend.addSpacing(10)
        legend.addStretch()
        layout.addLayout(legend)

        self._tbl = QTableWidget(0, 5)
        self._tbl.setHorizontalHeaderLabels(["#", "Disp (mm)", "Load (kg)", "Chord region", "Include?"])
        hdr = self._tbl.horizontalHeader()
        hdr.setSectionResizeMode(_COL_IDX,   QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_DISP,  QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_COL_LOAD,  QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_COL_CHORD, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_INC,   QHeaderView.ResizeMode.ResizeToContents)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tbl.verticalHeader().setVisible(False)
        layout.addWidget(self._tbl)

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
        onset_disp: float | None = None,
        chord_start_disp: float | None = None,
        chord_end_disp: float | None = None,
    ) -> None:
        """Populate the table.  Call whenever test data or chord bounds change."""
        self._updating = True
        self._tbl.setRowCount(len(disp_list))

        for i, (d, f) in enumerate(zip(disp_list, load_list)):
            d_abs = abs(d)

            def _ro(text: str) -> QTableWidgetItem:
                it = QTableWidgetItem(text)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                return it

            self._tbl.setItem(i, _COL_IDX,  _ro(str(i)))
            self._tbl.setItem(i, _COL_DISP, _ro(f"{d:.4f}"))
            self._tbl.setItem(i, _COL_LOAD, _ro(f"{f:.4f}"))

            # Chord region label
            chord_label = ""
            chord_colour: QColor | None = None
            if onset_disp is not None and chord_start_disp is not None and chord_end_disp is not None:
                if onset_disp <= d_abs < chord_start_disp:
                    chord_label  = "onset"
                    chord_colour = _CLR_ONSET
                elif chord_start_disp <= d_abs <= chord_end_disp:
                    chord_label  = "ε₁→ε₂"
                    chord_colour = _CLR_CHORD

            chord_item = _ro(chord_label)
            if chord_colour is not None:
                chord_item.setForeground(chord_colour)
            self._tbl.setItem(i, _COL_CHORD, chord_item)

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
            self._tbl.setItem(i, _COL_INC, chk)

        self._updating = False
        self._refresh_status()

    # ------------------------------------------------------------------
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or item.column() != _COL_INC:
            return
        self._emit()

    def _emit(self) -> None:
        excluded: set[int] = set()
        for row in range(self._tbl.rowCount()):
            it = self._tbl.item(row, _COL_INC)
            if it and it.checkState() == Qt.CheckState.Unchecked:
                excluded.add(row)
        self._refresh_status(excluded)
        self.exclusions_changed.emit(excluded)

    def _refresh_status(self, excluded: set | None = None) -> None:
        n = self._tbl.rowCount()
        if excluded is None:
            excluded = {
                r for r in range(n)
                if (it := self._tbl.item(r, _COL_INC))
                and it.checkState() == Qt.CheckState.Unchecked
            }
        inc = n - len(excluded)
        self._status.setText(f"{inc} of {n} points included")

    def _select_all(self) -> None:
        self._updating = True
        for r in range(self._tbl.rowCount()):
            it = self._tbl.item(r, _COL_INC)
            if it:
                it.setCheckState(Qt.CheckState.Checked)
        self._updating = False
        self._emit()

    def _deselect_all(self) -> None:
        self._updating = True
        for r in range(self._tbl.rowCount()):
            it = self._tbl.item(r, _COL_INC)
            if it:
                it.setCheckState(Qt.CheckState.Unchecked)
        self._updating = False
        self._emit()

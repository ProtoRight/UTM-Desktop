"""Post-test results panel — calculated mechanical properties + export/recalculate."""

from __future__ import annotations

from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox, QGridLayout, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout,
)

from calculations import BendResults, TensileResults


def _val(v: Optional[float], fmt: str = ".3f", unit: str = "") -> str:
    if v is None:
        return "—"
    return f"{v:{fmt}}  {unit}".strip()


class ResultsPanel(QGroupBox):
    """Displays mechanical property results after a test completes."""

    export_requested      = pyqtSignal()
    recalculate_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__("Results", parent)
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(4)

        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setColumnMinimumWidth(0, 170)
        grid.setColumnStretch(1, 1)

        self._rows: dict[str, QLabel] = {}
        fields = [
            ("peak_load",  "Peak load:"),
            ("peak_disp",  "Peak displacement:"),
            ("sep1",       ""),
            ("stress",     "Flexural / UTS stress:"),
            ("strain",     "Strain at peak:"),
            ("modulus",    "Modulus:"),
            ("yield",      "Yield strength (0.2 %):"),
            ("area",       "Cross-section area:"),
            ("sep2",       ""),
            ("notes",      "Notes:"),
        ]
        for row_idx, (key, label_text) in enumerate(fields):
            if key.startswith("sep"):
                grid.addWidget(QLabel(""), row_idx, 0, 1, 2)
                continue
            lbl_w = QLabel(label_text)
            lbl_w.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val_w = QLabel("—")
            val_w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._rows[key] = val_w
            grid.addWidget(lbl_w, row_idx, 0)
            grid.addWidget(val_w, row_idx, 1)

        root.addLayout(grid)

        # Button row
        btn_row = QHBoxLayout()
        self._recalc_btn = QPushButton("↻  Recalculate with current specimen")
        self._recalc_btn.setEnabled(False)
        self._recalc_btn.setToolTip(
            "Re-run all calculations on the last test dataset using\n"
            "the specimen dimensions and geometry currently entered."
        )
        self._recalc_btn.clicked.connect(self.recalculate_requested)
        btn_row.addWidget(self._recalc_btn, 1)

        self._export_btn = QPushButton("Export CSV")
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self.export_requested)
        btn_row.addWidget(self._export_btn)
        root.addLayout(btn_row)

    # ------------------------------------------------------------------
    def _set(self, key: str, text: str) -> None:
        if key in self._rows:
            self._rows[key].setText(text)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def clear(self) -> None:
        for lbl in self._rows.values():
            lbl.setText("—")
        self._export_btn.setEnabled(False)
        self._recalc_btn.setEnabled(False)

    def show_bend_results(self, r: BendResults) -> None:
        self._set("peak_load",  _val(r.peak_load_kg,  ".2f", "kg")
                                + f"  ({_val(r.peak_load_N, '.1f', 'N')})")
        self._set("peak_disp",  _val(r.peak_displacement_mm, ".3f", "mm"))
        self._set("stress",     _val(r.flexural_stress_MPa,  ".2f", "MPa"))
        self._set("strain",     _val(r.flexural_strain_peak, ".4f"))
        self._set("modulus",    _val(r.flexural_modulus_GPa, ".3f", "GPa"))
        self._set("yield",      "—  (N/A for bend)")
        self._set("area",       "—  (N/A for bend)")
        self._set("notes",      "  |  ".join(r.notes) if r.notes else "—")
        self._export_btn.setEnabled(True)
        self._recalc_btn.setEnabled(True)

    def show_tensile_results(self, r: TensileResults) -> None:
        self._set("peak_load",  _val(r.peak_load_kg,  ".2f", "kg")
                                + f"  ({_val(r.peak_load_N, '.1f', 'N')})")
        self._set("peak_disp",  _val(r.peak_displacement_mm, ".3f", "mm"))
        self._set("stress",     _val(r.uts_MPa,            ".2f", "MPa  (UTS)"))
        self._set("strain",     _val(r.strain_at_peak,     ".4f"))
        self._set("modulus",    _val(r.youngs_modulus_GPa, ".3f", "GPa"))
        self._set("yield",      _val(r.yield_strength_MPa, ".2f", "MPa"))
        area = r.cross_section_area_mm2
        self._set("area",       _val(area, ".3f", "mm²") if area else "—")
        self._set("notes",      "  |  ".join(r.notes) if r.notes else "—")
        self._export_btn.setEnabled(True)
        self._recalc_btn.setEnabled(True)

    def enable_recalculate(self, enabled: bool) -> None:
        self._recalc_btn.setEnabled(enabled)

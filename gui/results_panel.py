"""Post-test results panel — calculated mechanical properties with unit toggle."""

from __future__ import annotations

from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox, QGridLayout, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QComboBox, QCheckBox, QFrame,
)

from calculations import BendResults, TensileResults
from units import (
    ResultsUnit, RESULTS_LABELS,
    convert_results_load, convert_results_stress,
    convert_results_modulus, convert_results_disp,
)


def _fmt(v: Optional[float], fmt: str = ".3f", unit: str = "") -> str:
    if v is None:
        return "—"
    return f"{v:{fmt}}  {unit}".strip()


class ResultsPanel(QGroupBox):
    export_requested      = pyqtSignal()
    recalculate_requested = pyqtSignal()
    overlays_changed      = pyqtSignal()
    edit_data_requested   = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__("Results", parent)
        self._last_bend: Optional[BendResults]    = None
        self._last_tensile: Optional[TensileResults] = None
        self._results_unit = ResultsUnit.METRIC
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(4)

        # Unit toggle row
        unit_row = QHBoxLayout()
        unit_row.addWidget(QLabel("Results units:"))
        self._unit_combo = QComboBox()
        self._unit_combo.addItems([u.value for u in ResultsUnit])
        self._unit_combo.setFixedWidth(90)
        self._unit_combo.currentIndexChanged.connect(self._on_unit_changed)
        unit_row.addWidget(self._unit_combo)
        unit_row.addStretch()
        root.addLayout(unit_row)

        # Results grid
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
            ("chord_method", "Chord method:"),
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

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #444;")
        root.addWidget(sep)

        # Overlay checkboxes
        overlay_lbl = QLabel("Graph overlays:")
        overlay_lbl.setStyleSheet("color: #aaa; font-size: 8pt;")
        root.addWidget(overlay_lbl)

        overlay_row = QHBoxLayout()
        overlay_row.setSpacing(12)
        self._chk_modulus  = QCheckBox("Modulus line")
        self._chk_peak_ref = QCheckBox("Peak load ref")
        self._chk_yield    = QCheckBox("Yield / 0.2 % offset")
        for chk in (self._chk_modulus, self._chk_peak_ref, self._chk_yield):
            chk.stateChanged.connect(lambda _: self.overlays_changed.emit())
            overlay_row.addWidget(chk)
        overlay_row.addStretch()
        root.addLayout(overlay_row)

        # Button row
        btn_row = QHBoxLayout()
        self._recalc_btn = QPushButton("↻  Recalculate with current specimen")
        self._recalc_btn.setEnabled(False)
        self._recalc_btn.setToolTip(
            "Re-run all calculations on the last test dataset using\n"
            "the specimen dimensions currently entered."
        )
        self._recalc_btn.clicked.connect(self.recalculate_requested)
        btn_row.addWidget(self._recalc_btn, 1)
        self._export_btn = QPushButton("Export CSV")
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self.export_requested)
        btn_row.addWidget(self._export_btn)
        root.addLayout(btn_row)

        # Edit data button (second row)
        edit_row = QHBoxLayout()
        self._edit_btn = QPushButton("✎  Edit / Exclude Data Points…")
        self._edit_btn.setEnabled(False)
        self._edit_btn.setToolTip(
            "Open the data editor to manually include or exclude individual\n"
            "data points.  Changes update the graph and results immediately."
        )
        self._edit_btn.clicked.connect(self.edit_data_requested)
        edit_row.addWidget(self._edit_btn)
        root.addLayout(edit_row)

    # ------------------------------------------------------------------
    def _set(self, key: str, text: str) -> None:
        if key in self._rows:
            self._rows[key].setText(text)

    def _on_unit_changed(self, idx: int) -> None:
        self._results_unit = list(ResultsUnit)[idx]
        # Re-render whichever results are cached
        if self._last_bend is not None:
            self._render_bend(self._last_bend)
        elif self._last_tensile is not None:
            self._render_tensile(self._last_tensile)

    # ------------------------------------------------------------------
    def _render_bend(self, r: BendResults) -> None:
        u = self._results_unit
        lbl = RESULTS_LABELS[u]

        peak_load_disp = convert_results_load(r.peak_load_N, u)
        peak_disp_disp = convert_results_disp(r.peak_displacement_mm, u)

        self._set("peak_load", f"{r.peak_load_kg:.2f} kg  "
                               f"({peak_load_disp:.2f} {lbl['load']})")
        self._set("peak_disp", f"{peak_disp_disp:.4f} {lbl['disp']}")

        stress = (convert_results_stress(r.flexural_stress_MPa, u)
                  if r.flexural_stress_MPa is not None else None)
        self._set("stress",  _fmt(stress,  ".2f", lbl["stress"]))
        self._set("strain",  _fmt(r.flexural_strain_peak, ".4f"))

        mod = (convert_results_modulus(r.flexural_modulus_GPa, u)
               if r.flexural_modulus_GPa is not None else None)
        mod_unit = "GPa" if u == ResultsUnit.METRIC else "Msi"
        self._set("modulus", _fmt(mod, ".3f", mod_unit))
        std = r.chord_standard or "Custom"
        self._set("chord_method",
                  f"{std}  ε {r.chord_eps1_used*100:.2f}%→{r.chord_eps2_used*100:.2f}%"
                  if r.chord_eps1_used else "—")
        self._set("yield",   "—  (N/A for bend)")
        self._set("area",    "—  (N/A for bend)")
        self._set("notes",   "  |  ".join(r.notes) if r.notes else "—")

    def _render_tensile(self, r: TensileResults) -> None:
        u = self._results_unit
        lbl = RESULTS_LABELS[u]

        peak_load_disp = convert_results_load(r.peak_load_N, u)
        peak_disp_disp = convert_results_disp(r.peak_displacement_mm, u)

        self._set("peak_load", f"{r.peak_load_kg:.2f} kg  "
                               f"({peak_load_disp:.2f} {lbl['load']})")
        self._set("peak_disp", f"{peak_disp_disp:.4f} {lbl['disp']}")

        stress = (convert_results_stress(r.uts_MPa, u)
                  if r.uts_MPa is not None else None)
        self._set("stress",  _fmt(stress, ".2f", lbl["stress"] + "  (UTS)"))
        self._set("strain",  _fmt(r.strain_at_peak, ".4f"))

        mod = (convert_results_modulus(r.youngs_modulus_GPa, u)
               if r.youngs_modulus_GPa is not None else None)
        mod_unit = "GPa" if u == ResultsUnit.METRIC else "Msi"
        self._set("modulus", _fmt(mod, ".3f", mod_unit))
        std = r.chord_standard or "Custom"
        self._set("chord_method",
                  f"{std}  ε {r.chord_eps1_used*100:.2f}%→{r.chord_eps2_used*100:.2f}%"
                  if r.chord_eps1_used else "—")

        yld = (convert_results_stress(r.yield_strength_MPa, u)
               if r.yield_strength_MPa is not None else None)
        self._set("yield",   _fmt(yld, ".2f", lbl["stress"]))

        area = r.cross_section_area_mm2
        self._set("area",    _fmt(area, ".3f", "mm²") if area else "—")
        self._set("notes",   "  |  ".join(r.notes) if r.notes else "—")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def results_unit(self) -> ResultsUnit:
        return self._results_unit

    def get_overlay_flags(self) -> dict[str, bool]:
        return {
            "modulus":  self._chk_modulus.isChecked(),
            "peak_ref": self._chk_peak_ref.isChecked(),
            "yield":    self._chk_yield.isChecked(),
        }

    def set_yield_overlay_available(self, available: bool) -> None:
        self._chk_yield.setEnabled(available)
        if not available:
            self._chk_yield.setChecked(False)

    def clear(self) -> None:
        self._last_bend    = None
        self._last_tensile = None
        for lbl in self._rows.values():
            lbl.setText("—")
        self._export_btn.setEnabled(False)
        self._recalc_btn.setEnabled(False)
        self._edit_btn.setEnabled(False)

    def show_bend_results(self, r: BendResults) -> None:
        self._last_bend    = r
        self._last_tensile = None
        self._render_bend(r)
        self._export_btn.setEnabled(True)
        self._recalc_btn.setEnabled(True)
        self._edit_btn.setEnabled(True)

    def show_tensile_results(self, r: TensileResults) -> None:
        self._last_tensile = r
        self._last_bend    = None
        self._render_tensile(r)
        self._export_btn.setEnabled(True)
        self._recalc_btn.setEnabled(True)
        self._edit_btn.setEnabled(True)

    def enable_recalculate(self, enabled: bool) -> None:
        self._recalc_btn.setEnabled(enabled)

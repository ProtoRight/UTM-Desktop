"""Test parameter calculator — recommends speed and sample interval.

Tick count depends ONLY on specimen geometry and DRO resolution:
  - Tensile:  chord window = Δε × L₀
  - 3PT:      chord window = Δε × L² / (12·c)
The modulus does NOT change how many ticks are in the window.  What modulus
does control is the load change per DRO tick (stiffness × DRO resolution),
which reveals whether the load cell can resolve individual displacement steps.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QDoubleSpinBox,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QFrame, QSizePolicy,
)

from calculations import SpecimenData, CHORD_EPS_1, CHORD_EPS_2

G = 9.80665  # N/kg

_SPEED_CANDIDATES = [1, 2, 5, 10, 20, 30, 50, 75, 100, 150]

_RED    = 5
_YELLOW = 10
_GREEN  = 20

_DRO_DEFAULT = 0.01   # mm — stated resolution of the DRO


# ---------------------------------------------------------------------------
# Physics helpers
# ---------------------------------------------------------------------------

def _chord_window_mm(specimen: SpecimenData, eps1: float = CHORD_EPS_1, eps2: float = CHORD_EPS_2) -> Optional[float]:
    """Displacement span of the chord window.

    Depends ONLY on geometry — modulus plays no role here.
    """
    delta_eps = eps2 - eps1

    if specimen.test_type == "3PT":
        L = specimen.span_mm
        c = specimen.outer_fibre_distance_mm()
        if L <= 0 or c <= 0:
            return None
        return delta_eps * L ** 2 / (12.0 * c)
    else:
        L0 = specimen.gauge_length_mm
        if L0 <= 0:
            return None
        return delta_eps * L0


def _load_per_tick_kg(specimen: SpecimenData, modulus_gpa: float,
                      dro_res_mm: float) -> Optional[float]:
    """Load change (kg) that one DRO tick produces for this specimen and modulus.

    This is specimen stiffness × DRO resolution.  It tells you whether the
    load cell can resolve individual displacement steps.
    """
    E = modulus_gpa * 1000.0  # N/mm²

    if specimen.test_type == "3PT":
        L = specimen.span_mm
        I = specimen.second_moment_of_area_mm4()
        if L <= 0 or I <= 0:
            return None
        stiffness = 48.0 * E * I / L ** 3   # N/mm
    else:
        A  = specimen.cross_section_area_mm2()
        L0 = specimen.gauge_length_mm
        if A <= 0 or L0 <= 0:
            return None
        stiffness = E * A / L0   # N/mm

    return (stiffness * dro_res_mm) / G   # kg


def _recommend_interval_ms(speed_mmmin: float, dro_res_mm: float) -> int:
    """Minimum sample interval to catch every DRO tick: half the tick period."""
    tick_ms = (dro_res_mm / (speed_mmmin / 60.0)) * 1000.0
    return max(10, min(2000, int(tick_ms / 2)))


def _tick_colour(ticks: float) -> QColor:
    if ticks < _RED:
        return QColor(180, 60, 60)
    if ticks < _YELLOW:
        return QColor(180, 140, 40)
    if ticks < _GREEN:
        return QColor(60, 150, 60)
    return QColor(40, 200, 100)


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class TestParamsCalculator(QDialog):
    apply_requested = pyqtSignal(float, int)  # (speed mm/min, interval ms)

    def __init__(self, specimen: SpecimenData, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle("Test Parameter Calculator")
        self.resize(620, 560)
        self._specimen = specimen
        self._rec_speed:    Optional[float] = None
        self._rec_interval: Optional[int]   = None
        self._build_ui()
        self._recalculate()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── Specimen inputs ────────────────────────────────────────────
        spec_box = QGroupBox("Specimen geometry")
        self._spec_form = QFormLayout(spec_box)
        self._spec_form.setSpacing(4)

        self._cmb_type = QComboBox()
        self._cmb_type.addItems(["Tensile", "3-Point Bend"])
        self._cmb_type.setCurrentIndex(0 if self._specimen.test_type != "3PT" else 1)
        self._spec_form.addRow("Test type:", self._cmb_type)

        def _dsb(lo, hi, val, dec=2, step=1.0) -> QDoubleSpinBox:
            sb = QDoubleSpinBox()
            sb.setRange(lo, hi)
            sb.setValue(max(lo, val))
            sb.setDecimals(dec)
            sb.setSingleStep(step)
            return sb

        self._sb_gauge = _dsb(1, 500, self._specimen.gauge_length_mm or 50, step=5)
        self._sb_span  = _dsb(1, 500, self._specimen.span_mm or 50, step=5)
        self._sb_d     = _dsb(0.1, 100, self._specimen.thickness_mm or 2, dec=2)
        self._sb_b     = _dsb(0.1, 100, self._specimen.width_mm or 5, dec=2)

        self._spec_form.addRow("Gauge length L₀ (mm):", self._sb_gauge)
        self._spec_form.addRow("Support span L (mm):",  self._sb_span)
        self._spec_form.addRow("Section depth d (mm):", self._sb_d)
        self._spec_form.addRow("Section width b (mm):", self._sb_b)
        root.addWidget(spec_box)

        # ── Modulus inputs ─────────────────────────────────────────────
        mod_box = QGroupBox("Expected modulus range  (affects load-per-tick only)")
        mrow = QHBoxLayout(mod_box)
        mrow.addWidget(QLabel("Min:"))
        self._sb_emin = _dsb(0.01, 500, 1.0, dec=2, step=0.5)
        mrow.addWidget(self._sb_emin)
        mrow.addWidget(QLabel("GPa      Max:"))
        self._sb_emax = _dsb(0.01, 500, 5.0, dec=2, step=0.5)
        mrow.addWidget(self._sb_emax)
        mrow.addWidget(QLabel("GPa"))
        root.addWidget(mod_box)

        # ── DRO resolution ─────────────────────────────────────────────
        dro_row = QHBoxLayout()
        dro_row.addWidget(QLabel("DRO resolution:"))
        self._sb_dro = _dsb(0.001, 1.0, _DRO_DEFAULT, dec=3, step=0.005)
        self._sb_dro.setFixedWidth(80)
        dro_row.addWidget(self._sb_dro)
        dro_row.addWidget(QLabel("mm"))
        dro_row.addStretch()
        root.addLayout(dro_row)

        self._lbl_window = QLabel()
        self._lbl_window.setStyleSheet("color: #aaa; font-size: 8pt;")
        self._lbl_window.setWordWrap(True)
        root.addWidget(self._lbl_window)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        tbl_lbl = QLabel("Speed vs. chord-window ticks and load sensitivity:")
        tbl_lbl.setStyleSheet("font-weight: bold;")
        root.addWidget(tbl_lbl)

        # 5 columns: Speed | Ticks | ΔLoad/tick @ min E | ΔLoad/tick @ max E | Rec. interval
        self._tbl = QTableWidget(len(_SPEED_CANDIDATES), 5)
        self._tbl.setHorizontalHeaderLabels([
            "Speed\n(mm/min)",
            "Ticks in\nchord window",
            "ΔLoad/tick\n@ min E (kg)",
            "ΔLoad/tick\n@ max E (kg)",
            "Rec. interval\n(ms)",
        ])
        hdr = self._tbl.horizontalHeader()
        hdr.setDefaultSectionSize(110)
        for i in range(5):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self._tbl, 1)

        legend_row = QHBoxLayout()
        for colour, text in [
            ("#b43c3c", f"< {_RED} ticks — unreliable"),
            ("#b48c28", f"{_RED}–{_YELLOW} — marginal"),
            ("#3c963c", f"{_YELLOW}–{_GREEN} — good"),
            ("#28c864", f"> {_GREEN} — excellent"),
        ]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {colour}; font-size: 11pt;")
            legend_row.addWidget(dot)
            legend_row.addWidget(QLabel(text))
            legend_row.addSpacing(6)
        legend_row.addStretch()
        root.addLayout(legend_row)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep2)

        self._lbl_rec = QLabel()
        self._lbl_rec.setWordWrap(True)
        self._lbl_rec.setStyleSheet("font-size: 9pt; padding: 4px;")
        root.addWidget(self._lbl_rec)

        btn_row = QHBoxLayout()
        self._btn_apply = QPushButton("Apply recommended settings")
        self._btn_apply.setToolTip(
            "Sends the recommended TESTSPEED and SAMPLERATE to the Arduino."
        )
        self._btn_apply.clicked.connect(self._on_apply)
        btn_row.addWidget(self._btn_apply, 1)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

        for w in (self._cmb_type, self._sb_gauge, self._sb_span, self._sb_d,
                  self._sb_b, self._sb_emin, self._sb_emax, self._sb_dro):
            if hasattr(w, "valueChanged"):
                w.valueChanged.connect(self._recalculate)
            elif hasattr(w, "currentIndexChanged"):
                w.currentIndexChanged.connect(self._recalculate)

        self._update_row_visibility()

    # ------------------------------------------------------------------
    def _update_row_visibility(self) -> None:
        is_tensile = (self._cmb_type.currentIndex() == 0)
        for widget, visible in (
            (self._sb_gauge, is_tensile),
            (self._sb_span,  not is_tensile),
            (self._sb_d,     True),   # depth needed for both (c in 3PT; width for load calc)
            (self._sb_b,     True),   # width needed for both
        ):
            widget.setVisible(visible)
            lbl = self._spec_form.labelForField(widget)
            if lbl:
                lbl.setVisible(visible)

    def _make_specimen(self) -> SpecimenData:
        s = SpecimenData()
        s.geometry      = "rectangular"
        s.width_mm      = self._sb_b.value()
        s.thickness_mm  = self._sb_d.value()
        if self._cmb_type.currentIndex() == 0:
            s.test_type       = "TENSILE"
            s.gauge_length_mm = self._sb_gauge.value()
        else:
            s.test_type = "3PT"
            s.span_mm   = self._sb_span.value()
        return s

    def _recalculate(self) -> None:
        self._update_row_visibility()
        s       = self._make_specimen()
        e_min   = self._sb_emin.value()
        e_max   = self._sb_emax.value()
        dro_res = self._sb_dro.value()

        import settings as cfg
        chord_eps1 = float(cfg.get("chord_eps1"))
        chord_eps2 = float(cfg.get("chord_eps2"))
        chord_mm = _chord_window_mm(s, chord_eps1, chord_eps2)
        if chord_mm is None:
            self._lbl_window.setText("Enter specimen dimensions to calculate.")
            self._lbl_rec.setText("")
            self._btn_apply.setEnabled(False)
            return

        ticks = chord_mm / dro_res
        lpt_min = _load_per_tick_kg(s, e_min, dro_res)
        lpt_max = _load_per_tick_kg(s, e_max, dro_res)

        lpt_min_str = f"{lpt_min:.3f} kg" if lpt_min is not None else "—"
        lpt_max_str = f"{lpt_max:.3f} kg" if lpt_max is not None else "—"

        self._lbl_window.setText(
            f"Chord window (ε {chord_eps1*100:.2f}%→{chord_eps2*100:.2f}%):  "
            f"{chord_mm:.3f} mm  →  {ticks:.1f} DRO ticks  "
            f"(tick count is geometry-only; modulus does not affect it)\n"
            f"Load change per DRO tick:  {lpt_min_str} at {e_min:.1f} GPa  —  "
            f"{lpt_max_str} at {e_max:.1f} GPa"
        )

        self._rec_speed    = None
        self._rec_interval = None

        def _cell(text: str) -> QTableWidgetItem:
            it = QTableWidgetItem(text)
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            return it

        for row, speed in enumerate(_SPEED_CANDIDATES):
            interval = _recommend_interval_ms(speed, dro_res)
            tick_ms  = (dro_res / (speed / 60.0)) * 1000.0
            avgs     = max(1.0, tick_ms / interval)

            self._tbl.setItem(row, 0, _cell(str(speed)))

            c_ticks = _cell(f"{ticks:.1f}  (×{avgs:.0f} avg)")
            c_ticks.setForeground(_tick_colour(ticks))
            self._tbl.setItem(row, 1, c_ticks)

            lpt_lo = _load_per_tick_kg(s, e_min, dro_res)
            lpt_hi = _load_per_tick_kg(s, e_max, dro_res)
            self._tbl.setItem(row, 2, _cell(f"{lpt_lo:.3f}" if lpt_lo is not None else "—"))
            self._tbl.setItem(row, 3, _cell(f"{lpt_hi:.3f}" if lpt_hi is not None else "—"))
            self._tbl.setItem(row, 4, _cell(str(interval)))

            if ticks >= _YELLOW and self._rec_speed is None:
                self._rec_speed    = speed
                self._rec_interval = interval

        if self._rec_speed is None:
            self._rec_speed    = _SPEED_CANDIDATES[0]
            self._rec_interval = _recommend_interval_ms(self._rec_speed, dro_res)
            self._lbl_rec.setText(
                f"⚠  Only {ticks:.1f} tick(s) in chord window regardless of speed — "
                f"this is set by geometry alone.  "
                f"Use a longer gauge / span length to get more ticks, or widen the chord "
                f"bounds in Test Settings (ε {chord_eps1*100:.2f}%→{chord_eps2*100:.2f}%).\n"
                f"Applying {self._rec_speed} mm/min  ·  {self._rec_interval} ms as best available."
            )
        else:
            tick_ms  = (dro_res / (self._rec_speed / 60.0)) * 1000.0
            avgs     = max(1.0, tick_ms / self._rec_interval)
            lpt_str  = f"{lpt_max:.3f} kg/tick" if lpt_max is not None else "unknown"
            self._lbl_rec.setText(
                f"Recommended: {self._rec_speed} mm/min  ·  {self._rec_interval} ms sample interval\n"
                f"→ {ticks:.0f} ticks in chord window  ·  ≈{avgs:.0f} load readings averaged per tick  "
                f"·  {lpt_str} at {e_max:.1f} GPa"
            )

        self._btn_apply.setEnabled(True)

    def _on_apply(self) -> None:
        if self._rec_speed is not None and self._rec_interval is not None:
            self.apply_requested.emit(float(self._rec_speed), self._rec_interval)

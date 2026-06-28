"""Test parameter calculator — recommends speed and sample interval.

Given specimen dimensions and expected modulus range, computes how many DRO
ticks fall inside the chord-modulus measurement window for a range of test
speeds, and recommends parameters that give adequate resolution.
"""

from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QDoubleSpinBox, QSpinBox,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QFrame, QSizePolicy,
)

from calculations import SpecimenData, CHORD_EPS_1, CHORD_EPS_2

# Candidate test speeds shown in the table (mm/min)
_SPEED_CANDIDATES = [1, 2, 5, 10, 20, 30, 50, 75, 100, 150]

# Colour thresholds for ticks-per-chord-window
_RED    = 5
_YELLOW = 10
_GREEN  = 20   # above this → bright green

# DRO hardware resolution (mm) — true value is 0.01 mm for this scale
_DRO_DEFAULT = 0.01


def _chord_window_mm(specimen: SpecimenData, modulus_gpa: float) -> Optional[float]:
    """Displacement span of the ISO 178 chord window for *this* specimen and modulus.

    Returns None if specimen geometry is incomplete.
    """
    delta_eps = CHORD_EPS_2 - CHORD_EPS_1   # 0.002 = 0.20 %

    if specimen.test_type == "3PT":
        L = specimen.span_mm
        c = specimen.outer_fibre_distance_mm()
        if L <= 0 or c <= 0:
            return None
        # ε_flex = 12·δ·c / L²  →  δ = ε·L² / (12·c)
        return delta_eps * L ** 2 / (12.0 * c)

    else:  # TENSILE
        L0 = specimen.gauge_length_mm
        if L0 <= 0:
            return None
        # ε = δ / L₀  →  δ = ε·L₀
        return delta_eps * L0


def _ticks_in_window(chord_mm: float, dro_res_mm: float) -> float:
    return chord_mm / dro_res_mm


def _recommend_interval_ms(speed_mmmin: float, dro_res_mm: float) -> int:
    """Sample interval that catches every DRO tick: half the tick period, clamped."""
    tick_ms = (dro_res_mm / (speed_mmmin / 60.0)) * 1000.0
    interval = max(10, min(2000, int(tick_ms / 2)))
    return interval


def _tick_colour(ticks: float) -> QColor:
    if ticks < _RED:
        return QColor(180, 60, 60)       # red
    if ticks < _YELLOW:
        return QColor(180, 140, 40)      # amber
    if ticks < _GREEN:
        return QColor(60, 150, 60)       # green
    return QColor(40, 200, 100)          # bright green


class TestParamsCalculator(QDialog):
    """Non-modal fly-out calculator window."""

    apply_requested = pyqtSignal(float, int)   # (speed mm/min, interval ms)

    def __init__(self, specimen: SpecimenData, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle("Test Parameter Calculator")
        self.resize(560, 580)
        self._specimen = specimen
        self._build_ui()
        self._recalculate()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── Specimen inputs ────────────────────────────────────────────
        spec_box = QGroupBox("Specimen")
        self._spec_form = QFormLayout(spec_box)
        form = self._spec_form
        form.setSpacing(4)

        self._cmb_type = QComboBox()
        self._cmb_type.addItems(["Tensile", "3-Point Bend"])
        self._cmb_type.setCurrentIndex(0 if self._specimen.test_type == "TENSILE" else 1)
        form.addRow("Test type:", self._cmb_type)

        def _dsb(lo, hi, val, dec=2, step=1.0):
            sb = QDoubleSpinBox()
            sb.setRange(lo, hi)
            sb.setValue(val)
            sb.setDecimals(dec)
            sb.setSingleStep(step)
            return sb

        self._sb_gauge = _dsb(1, 500, max(self._specimen.gauge_length_mm, 50), step=5)
        self._sb_span  = _dsb(1, 500, max(self._specimen.span_mm, 50), step=5)
        self._sb_d     = _dsb(0.1, 100, max(self._specimen.thickness_mm, 2), dec=2)

        form.addRow("Gauge length L₀ (mm):", self._sb_gauge)
        form.addRow("Support span L (mm):", self._sb_span)
        form.addRow("Section depth d (mm):", self._sb_d)

        root.addWidget(spec_box)

        # ── Modulus inputs ─────────────────────────────────────────────
        mod_box = QGroupBox("Expected modulus range")
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

        # ── Chord-window info line ─────────────────────────────────────
        self._lbl_window = QLabel()
        self._lbl_window.setStyleSheet("color: #aaa; font-size: 8pt;")
        root.addWidget(self._lbl_window)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        # ── Results table ──────────────────────────────────────────────
        tbl_lbl = QLabel("Ticks per chord window by test speed:")
        tbl_lbl.setStyleSheet("font-weight: bold;")
        root.addWidget(tbl_lbl)

        self._tbl = QTableWidget(len(_SPEED_CANDIDATES), 4)
        self._tbl.setHorizontalHeaderLabels([
            "Speed (mm/min)", "Ticks (min E)", "Ticks (max E)", "Rec. interval (ms)"
        ])
        hdr = self._tbl.horizontalHeader()
        for i in range(4):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self._tbl, 1)

        legend_row = QHBoxLayout()
        for colour, text in [
            ("#b43c3c", f"< {_RED} ticks — unreliable"),
            ("#b48c28", f"{_RED}–{_YELLOW} ticks — marginal"),
            ("#3c963c", f"{_YELLOW}–{_GREEN} ticks — good"),
            ("#28c864", f"> {_GREEN} ticks — excellent"),
        ]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {colour}; font-size: 11pt;")
            legend_row.addWidget(dot)
            legend_row.addWidget(QLabel(text))
            legend_row.addSpacing(6)
        legend_row.addStretch()
        root.addLayout(legend_row)

        # ── Recommendation ─────────────────────────────────────────────
        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep2)

        self._lbl_rec = QLabel()
        self._lbl_rec.setWordWrap(True)
        self._lbl_rec.setStyleSheet("font-size: 9pt; padding: 4px;")
        root.addWidget(self._lbl_rec)

        # ── Buttons ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._btn_apply = QPushButton("Apply recommended settings")
        self._btn_apply.setToolTip(
            "Sends the recommended TESTSPEED and SAMPLERATE to the Arduino\n"
            "and updates the control panel."
        )
        self._btn_apply.clicked.connect(self._on_apply)
        btn_row.addWidget(self._btn_apply, 1)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

        # ── Connect recalculate ────────────────────────────────────────
        for w in (self._cmb_type, self._sb_gauge, self._sb_span,
                  self._sb_d, self._sb_emin, self._sb_emax, self._sb_dro):
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
            (self._sb_d,     not is_tensile),
        ):
            widget.setVisible(visible)
            lbl = self._spec_form.labelForField(widget)
            if lbl:
                lbl.setVisible(visible)

    def _make_specimen(self) -> SpecimenData:
        s = SpecimenData()
        s.geometry = "rectangular"
        if self._cmb_type.currentIndex() == 0:
            s.test_type = "TENSILE"
            s.gauge_length_mm = self._sb_gauge.value()
        else:
            s.test_type = "3PT"
            s.span_mm = self._sb_span.value()
            s.thickness_mm = self._sb_d.value()
            s.width_mm = 1.0   # irrelevant for c calculation
        return s

    def _recalculate(self) -> None:
        self._update_row_visibility()
        s       = self._make_specimen()
        e_min   = self._sb_emin.value()
        e_max   = self._sb_emax.value()
        dro_res = self._sb_dro.value()

        win_min = _chord_window_mm(s, e_min)
        win_max = _chord_window_mm(s, e_max)

        if win_min is None or win_max is None:
            self._lbl_window.setText("Enter specimen dimensions to calculate.")
            self._lbl_rec.setText("")
            self._btn_apply.setEnabled(False)
            return

        # Higher modulus → smaller chord window (stiffer → less displacement per unit strain)
        # So worst case (fewest ticks) is at maximum modulus
        self._lbl_window.setText(
            f"Chord window (ISO 178 ε {CHORD_EPS_1*100:.2f}%→{CHORD_EPS_2*100:.2f}%): "
            f"{win_min:.3f} mm (at {e_min:.1f} GPa) — "
            f"{win_max:.3f} mm (at {e_max:.1f} GPa)    "
            f"DRO res: {dro_res:.3f} mm"
        )

        self._rec_speed    = None
        self._rec_interval = None

        for row, speed in enumerate(_SPEED_CANDIDATES):
            ticks_min = _ticks_in_window(win_min, dro_res)  # at low modulus (big window)
            ticks_max = _ticks_in_window(win_max, dro_res)  # at high modulus (small window)
            interval  = _recommend_interval_ms(speed, dro_res)

            def _cell(val, is_float=True) -> QTableWidgetItem:
                text = f"{val:.1f}" if is_float else str(val)
                it = QTableWidgetItem(text)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                return it

            self._tbl.setItem(row, 0, _cell(speed))

            c_min = _cell(ticks_min)
            c_min.setForeground(_tick_colour(ticks_min))
            self._tbl.setItem(row, 1, c_min)

            c_max = _cell(ticks_max)
            c_max.setForeground(_tick_colour(ticks_max))
            self._tbl.setItem(row, 2, c_max)

            self._tbl.setItem(row, 3, _cell(interval, False))

            # Pick the fastest speed where ticks_max (worst case) >= _YELLOW
            if ticks_max >= _YELLOW and self._rec_speed is None:
                self._rec_speed    = speed
                self._rec_interval = interval

        ticks_worst = _ticks_in_window(win_max, dro_res)
        tick_ms     = (dro_res / ((_SPEED_CANDIDATES[0] if self._rec_speed is None
                                    else self._rec_speed) / 60.0)) * 1000.0

        if self._rec_speed is None:
            self._rec_speed    = _SPEED_CANDIDATES[0]
            self._rec_interval = _recommend_interval_ms(self._rec_speed, dro_res)
            self._lbl_rec.setText(
                f"⚠  Even at {self._rec_speed} mm/min, only {ticks_worst:.1f} tick(s) fall in the "
                f"chord window at {e_max:.1f} GPa.  Consider a longer gauge / span length, or "
                f"widening the chord bounds in calculations.py (CHORD_EPS_1 / CHORD_EPS_2).\n"
                f"Applying {self._rec_speed} mm/min  ·  {self._rec_interval} ms as best available."
            )
        else:
            # Load averages per tick = tick period / HX711 conversion time
            # HX711 at 80 SPS ≈ 12.5 ms/reading; at 10 SPS ≈ 100 ms/reading.
            # Use the sample interval as a proxy (conservative lower bound).
            avgs_per_tick = max(1.0, tick_ms / self._rec_interval)
            self._lbl_rec.setText(
                f"Recommended: {self._rec_speed} mm/min  ·  {self._rec_interval} ms sample interval\n"
                f"→ {ticks_worst:.0f} ticks in chord window at worst-case {e_max:.1f} GPa  "
                f"(≈ {avgs_per_tick:.1f} load readings averaged per DRO tick)"
            )

        self._btn_apply.setEnabled(True)

    def _on_apply(self) -> None:
        if self._rec_speed is not None and self._rec_interval is not None:
            self.apply_requested.emit(float(self._rec_speed), self._rec_interval)

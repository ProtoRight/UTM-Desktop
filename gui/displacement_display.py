"""Displacement indicator: numeric readout + horizontal position bar."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel,
    QWidget, QSizePolicy,
)

import settings as cfg
from units import DispUnit, mm_to, disp_unit_label


class _DispBar(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._disp_mm   = 0.0
        self._max_mm    = 40.0
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_values(self, disp_mm: float, max_mm: float) -> None:
        self._disp_mm = disp_mm
        self._max_mm  = max(0.1, max_mm)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        pad = 4
        bx, by, bw, bh = pad, pad, w - 2*pad, h - 2*pad

        p.setPen(QPen(QColor(70, 70, 70), 1))
        p.setBrush(QBrush(QColor(28, 28, 28)))
        p.drawRoundedRect(bx, by, bw, bh, 3, 3)

        fraction = max(0.0, min(1.0, self._disp_mm / self._max_mm))
        fill_w = int(fraction * (bw - 2))
        if fill_w > 0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(41, 128, 185)))
            p.drawRoundedRect(bx + 1, by + 1, fill_w, bh - 2, 2, 2)

        p.setPen(QPen(QColor(90, 90, 90), 1))
        for frac in (0.25, 0.5, 0.75):
            tx = bx + int(frac * bw)
            p.drawLine(tx, by, tx, by + bh)
        p.end()


class DisplacementDisplay(QGroupBox):
    """Compact displacement panel: numeric value and position bar."""

    def __init__(self, parent=None) -> None:
        super().__init__("Displacement", parent)
        self._max_mm: float = float(cfg.get("travel_limit_mm"))
        self._current_mm: float = 0.0
        self._display_unit: DispUnit = DispUnit.MM
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(4)
        root.setContentsMargins(6, 6, 6, 6)

        self._val_lbl = QLabel("0.000")
        font = QFont("Segoe UI", 16)
        font.setBold(True)
        self._val_lbl.setFont(font)
        self._val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._val_lbl)

        self._unit_lbl = QLabel("mm")
        self._unit_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._unit_lbl.setStyleSheet("color: #888; font-size: 9pt;")
        root.addWidget(self._unit_lbl)

        self._bar = _DispBar()
        root.addWidget(self._bar)

        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("0"))
        range_row.addStretch()
        self._max_lbl = QLabel(f"{self._max_mm:.0f} mm")
        self._max_lbl.setStyleSheet("color: #888; font-size: 8pt;")
        range_row.addWidget(self._max_lbl)
        root.addLayout(range_row)

    # ------------------------------------------------------------------
    def set_display_unit(self, unit: DispUnit) -> None:
        self._display_unit = unit
        self._unit_lbl.setText(disp_unit_label(unit))
        self._refresh_max_label()
        self._refresh()

    def update_displacement(self, disp_mm: float) -> None:
        self._current_mm = disp_mm
        self._refresh()

    def set_travel_limit(self, limit_mm: float) -> None:
        self._max_mm = max(0.1, limit_mm)
        self._refresh_max_label()
        self._bar.set_values(self._current_mm, self._max_mm)

    def _refresh(self) -> None:
        displayed = mm_to(self._current_mm, self._display_unit)
        self._val_lbl.setText(f"{displayed:.3f}")
        self._bar.set_values(self._current_mm, self._max_mm)

    def _refresh_max_label(self) -> None:
        max_disp = mm_to(self._max_mm, self._display_unit)
        unit = disp_unit_label(self._display_unit)
        self._max_lbl.setText(f"{max_disp:.2f} {unit}")

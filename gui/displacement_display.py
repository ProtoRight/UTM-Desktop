"""Displacement indicator: numeric readout + horizontal position bar."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel,
    QWidget, QSizePolicy,
)

import settings as cfg


class _DispBar(QWidget):
    """Horizontal bar showing crosshead position from 0 to travel limit."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._disp = 0.0
        self._max_disp = 40.0
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_values(self, disp: float, max_disp: float) -> None:
        self._disp = disp
        self._max_disp = max(0.1, max_disp)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        pad = 4
        bx, by = pad, pad
        bw, bh = w - 2 * pad, h - 2 * pad

        # Background
        p.setPen(QPen(QColor(70, 70, 70), 1))
        p.setBrush(QBrush(QColor(28, 28, 28)))
        p.drawRoundedRect(bx, by, bw, bh, 3, 3)

        # Fill (clamped 0→1)
        fraction = max(0.0, min(1.0, self._disp / self._max_disp))
        fill_w = int(fraction * (bw - 2))
        if fill_w > 0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(41, 128, 185)))
            p.drawRoundedRect(bx + 1, by + 1, fill_w, bh - 2, 2, 2)

        # Quarter tick marks
        p.setPen(QPen(QColor(90, 90, 90), 1))
        for frac in (0.25, 0.5, 0.75):
            tx = bx + int(frac * bw)
            p.drawLine(tx, by, tx, by + bh)

        p.end()


class DisplacementDisplay(QGroupBox):
    """Compact displacement panel: numeric value and position bar."""

    def __init__(self, parent=None) -> None:
        super().__init__("Displacement", parent)
        self._max_disp: float = float(cfg.get("travel_limit_mm"))
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(4)
        root.setContentsMargins(6, 6, 6, 6)

        # Numeric value
        self._val_lbl = QLabel("0.000")
        font = QFont("Segoe UI", 16)
        font.setBold(True)
        self._val_lbl.setFont(font)
        self._val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._val_lbl)

        unit_lbl = QLabel("mm")
        unit_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        unit_lbl.setStyleSheet("color: #888; font-size: 9pt;")
        root.addWidget(unit_lbl)

        # Position bar
        self._bar = _DispBar()
        root.addWidget(self._bar)

        # Range labels below bar
        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("0"))
        range_row.addStretch()
        self._max_lbl = QLabel(f"{self._max_disp:.0f} mm  (travel limit)")
        self._max_lbl.setStyleSheet("color: #888; font-size: 8pt;")
        range_row.addWidget(self._max_lbl)
        root.addLayout(range_row)

    # ------------------------------------------------------------------
    def update_displacement(self, disp: float) -> None:
        self._val_lbl.setText(f"{disp:.3f}")
        self._bar.set_values(disp, self._max_disp)

    def set_travel_limit(self, limit_mm: float) -> None:
        self._max_disp = max(0.1, limit_mm)
        self._max_lbl.setText(f"{self._max_disp:.0f} mm  (travel limit)")
        self._bar.set_values(float(self._val_lbl.text()), self._max_disp)

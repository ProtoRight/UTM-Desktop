"""Graphical load indicator: large numeric readout + bipolar vertical bar."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel,
    QDoubleSpinBox, QWidget, QSizePolicy,
)

import settings as cfg


def _bar_color(fraction: float) -> QColor:
    """Map |load|/max_load (0→1) to green → yellow → red."""
    f = max(0.0, min(1.0, abs(fraction)))
    if f < 0.5:
        t = f * 2.0
        r = int(220 * t)
        g = 180
        b = 0
    else:
        t = (f - 0.5) * 2.0
        r = 220
        g = int(180 * (1.0 - t))
        b = 0
    return QColor(r, g, b)


class _LoadBar(QWidget):
    """Bipolar vertical bar: zero at centre, positive fills upward, negative downward."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._load = 0.0
        self._max_load = 500.0
        self.setMinimumWidth(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_values(self, load: float, max_load: float) -> None:
        self._load = load
        self._max_load = max(1.0, max_load)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        pad = 6
        bx = pad
        bw = w - 2 * pad
        bt = pad + 14          # top of bar (leave room for "+max" label)
        bb = h - pad - 14      # bottom of bar (leave room for "-max" label)
        bh = bb - bt

        if bh < 4:
            p.end()
            return

        # Background track
        p.setPen(QPen(QColor(70, 70, 70), 1))
        p.setBrush(QBrush(QColor(28, 28, 28)))
        p.drawRoundedRect(bx, bt, bw, bh, 3, 3)

        # Centre (zero) y-coordinate
        cy = bt + bh // 2

        # Scale tick marks at ±25%, ±50%, ±75%, ±100%
        p.setPen(QPen(QColor(80, 80, 80), 1))
        for frac in (0.25, 0.5, 0.75, 1.0):
            for sign in (1, -1):
                ty = cy - int(sign * frac * bh / 2)
                p.drawLine(bx + bw - 6, ty, bx + bw, ty)

        # Filled bar
        fraction = self._load / self._max_load
        fill_h = min(int(abs(fraction) * bh / 2), bh // 2 - 1)

        if fill_h > 0:
            color = _bar_color(abs(fraction))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
            if self._load >= 0:
                p.drawRect(bx + 1, cy - fill_h, bw - 2, fill_h)
            else:
                p.drawRect(bx + 1, cy + 1, bw - 2, fill_h)

        # Zero line
        p.setPen(QPen(QColor(200, 200, 200), 1.5))
        p.drawLine(bx, cy, bx + bw, cy)

        # Scale labels
        font = p.font()
        font.setPointSize(7)
        p.setFont(font)
        p.setPen(QPen(QColor(140, 140, 140)))
        max_txt = f"+{self._max_load:.0f}"
        min_txt = f"-{self._max_load:.0f}"
        p.drawText(bx, bt + 10, max_txt)
        p.drawText(bx, bb + 12, min_txt)

        p.end()


class LoadDisplay(QGroupBox):
    """Compact load panel: numeric value, vertical bar, and user-set load cell rating."""

    def __init__(self, parent=None) -> None:
        super().__init__("Load", parent)
        self._max_load: float = float(cfg.get("load_cell_rating_kg"))
        self._current_load: float = 0.0
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(4)
        root.setContentsMargins(6, 6, 6, 6)

        # Large numeric value
        self._val_lbl = QLabel("0.000")
        font = QFont("Segoe UI", 16)
        font.setBold(True)
        self._val_lbl.setFont(font)
        self._val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._val_lbl)

        unit_lbl = QLabel("kg")
        unit_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        unit_lbl.setStyleSheet("color: #888; font-size: 9pt;")
        root.addWidget(unit_lbl)

        # Bar
        self._bar = _LoadBar()
        root.addWidget(self._bar, 1)

        # Load cell rating input
        rating_row = QHBoxLayout()
        rating_row.addWidget(QLabel("Max:"))
        self._rating_spin = QDoubleSpinBox()
        self._rating_spin.setRange(1.0, 100_000.0)
        self._rating_spin.setDecimals(0)
        self._rating_spin.setSingleStep(50.0)
        self._rating_spin.setValue(self._max_load)
        rating_row.addWidget(self._rating_spin, 1)
        rating_row.addWidget(QLabel("kg"))
        root.addLayout(rating_row)

        self._rating_spin.valueChanged.connect(self._on_rating_changed)
        self._bar.set_values(0.0, self._max_load)

    def _on_rating_changed(self, v: float) -> None:
        self._max_load = v
        cfg.set("load_cell_rating_kg", v)
        self._bar.set_values(self._current_load, self._max_load)

    # ------------------------------------------------------------------
    def update_load(self, load: float) -> None:
        self._current_load = load
        self._val_lbl.setText(f"{load:.3f}")
        self._bar.set_values(load, self._max_load)

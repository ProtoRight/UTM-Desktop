"""Graphical load indicator: large numeric readout + bipolar vertical bar."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel,
    QDoubleSpinBox, QWidget, QSizePolicy,
)

import settings as cfg
from units import LoadUnit, kg_to, load_unit_label


def _bar_color(fraction: float) -> QColor:
    f = max(0.0, min(1.0, abs(fraction)))
    if f < 0.5:
        t = f * 2.0
        return QColor(int(220 * t), 180, 0)
    else:
        t = (f - 0.5) * 2.0
        return QColor(220, int(180 * (1.0 - t)), 0)


class _LoadBar(QWidget):
    """Bipolar vertical bar: zero at centre, positive fills upward, negative downward."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._load_kg   = 0.0
        self._max_kg    = 500.0
        self.setMinimumWidth(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_values(self, load_kg: float, max_kg: float) -> None:
        self._load_kg = load_kg
        self._max_kg  = max(1.0, max_kg)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        pad = 6
        bx, bw = pad, w - 2 * pad
        bt = pad + 14
        bb = h - pad - 14
        bh = bb - bt
        if bh < 4:
            p.end()
            return

        # Background track
        p.setPen(QPen(QColor(70, 70, 70), 1))
        p.setBrush(QBrush(QColor(28, 28, 28)))
        p.drawRoundedRect(bx, bt, bw, bh, 3, 3)

        cy = bt + bh // 2

        # Scale ticks
        p.setPen(QPen(QColor(80, 80, 80), 1))
        for frac in (0.25, 0.5, 0.75, 1.0):
            for sign in (1, -1):
                ty = cy - int(sign * frac * bh / 2)
                p.drawLine(bx + bw - 6, ty, bx + bw, ty)

        # Filled bar (always uses raw kg ratio)
        fraction = self._load_kg / self._max_kg
        fill_h = min(int(abs(fraction) * bh / 2), bh // 2 - 1)
        if fill_h > 0:
            color = _bar_color(abs(fraction))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
            if self._load_kg >= 0:
                p.drawRect(bx + 1, cy - fill_h, bw - 2, fill_h)
            else:
                p.drawRect(bx + 1, cy + 1, bw - 2, fill_h)

        # Zero line
        p.setPen(QPen(QColor(200, 200, 200), 1.5))
        p.drawLine(bx, cy, bx + bw, cy)

        # +max / -max labels
        font = p.font()
        font.setPointSize(7)
        p.setFont(font)
        p.setPen(QPen(QColor(140, 140, 140)))
        p.drawText(bx, bt + 10, f"+{self._max_kg:.0f}")
        p.drawText(bx, bb + 12, f"-{self._max_kg:.0f}")
        p.end()


class LoadDisplay(QGroupBox):
    """Load panel: numeric value (in display unit), vertical bar, load cell rating."""

    def __init__(self, parent=None) -> None:
        super().__init__("Load", parent)
        self._max_kg: float = float(cfg.get("load_cell_rating_kg"))
        self._current_kg: float = 0.0
        self._display_unit: LoadUnit = LoadUnit.KG
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

        self._unit_lbl = QLabel("kg")
        self._unit_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._unit_lbl.setStyleSheet("color: #888; font-size: 9pt;")
        root.addWidget(self._unit_lbl)

        self._bar = _LoadBar()
        root.addWidget(self._bar, 1)

        rating_row = QHBoxLayout()
        rating_row.addWidget(QLabel("Rating:"))
        self._rating_spin = QDoubleSpinBox()
        self._rating_spin.setRange(1.0, 100_000.0)
        self._rating_spin.setDecimals(0)
        self._rating_spin.setSingleStep(50.0)
        self._rating_spin.setValue(self._max_kg)
        rating_row.addWidget(self._rating_spin, 1)
        rating_row.addWidget(QLabel("kg"))
        root.addLayout(rating_row)

        self._rating_spin.valueChanged.connect(self._on_rating_changed)
        self._bar.set_values(0.0, self._max_kg)

    def _on_rating_changed(self, v: float) -> None:
        self._max_kg = v
        cfg.set("load_cell_rating_kg", v)
        self._bar.set_values(self._current_kg, self._max_kg)

    # ------------------------------------------------------------------
    def set_display_unit(self, unit: LoadUnit) -> None:
        self._display_unit = unit
        self._unit_lbl.setText(load_unit_label(unit))
        self._refresh()

    def update_load(self, load_kg: float) -> None:
        self._current_kg = load_kg
        self._refresh()

    def _refresh(self) -> None:
        displayed = kg_to(self._current_kg, self._display_unit)
        self._val_lbl.setText(f"{displayed:.3f}")
        self._bar.set_values(self._current_kg, self._max_kg)

"""Test threshold settings panel — all user-adjustable completion/safety limits."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGroupBox, QFormLayout, QDoubleSpinBox, QSpinBox, QLabel,
)

import settings as cfg


class SettingsPanel(QGroupBox):
    """Threshold and limit settings that are read at test-start time."""

    def __init__(self, parent=None) -> None:
        super().__init__("Test Settings", parent)
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        form = QFormLayout(self)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(5)

        def dsb(lo, hi, step, suffix, decimals=1) -> QDoubleSpinBox:
            sb = QDoubleSpinBox()
            sb.setRange(lo, hi)
            sb.setSingleStep(step)
            sb.setSuffix(suffix)
            sb.setDecimals(decimals)
            return sb

        def isb(lo, hi) -> QSpinBox:
            sb = QSpinBox()
            sb.setRange(lo, hi)
            return sb

        self._travel   = dsb(1, 500, 1, " mm")
        self._load     = dsb(1, 9999, 10, " kg")
        self._drop_pct = dsb(1, 99, 1, " %")
        self._drop_win = isb(3, 100)

        self._travel.setValue(cfg.get("travel_limit_mm"))
        self._load.setValue(cfg.get("load_limit_kg"))
        self._drop_pct.setValue(cfg.get("load_drop_pct"))
        self._drop_win.setValue(int(cfg.get("load_drop_window")))

        form.addRow("Travel limit:", self._travel)
        form.addRow("Load limit:", self._load)
        form.addRow(QLabel("— Fracture detection —"), QLabel(""))
        form.addRow("Load drop  ≥:", self._drop_pct)
        form.addRow("Over  N  samples:", self._drop_win)

        # Persist on change
        self._travel.valueChanged.connect(
            lambda v: cfg.set("travel_limit_mm", v))
        self._load.valueChanged.connect(
            lambda v: cfg.set("load_limit_kg", v))
        self._drop_pct.valueChanged.connect(
            lambda v: cfg.set("load_drop_pct", v))
        self._drop_win.valueChanged.connect(
            lambda v: cfg.set("load_drop_window", v))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def travel_limit_mm(self) -> float:
        return self._travel.value()

    @property
    def load_limit_kg(self) -> float:
        return self._load.value()

    @property
    def load_drop_pct(self) -> float:
        return self._drop_pct.value()

    @property
    def load_drop_window(self) -> int:
        return self._drop_win.value()

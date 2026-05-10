"""Test threshold settings panel — user-adjustable completion/safety limits."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGroupBox, QFormLayout, QDoubleSpinBox, QSpinBox, QLabel, QVBoxLayout,
)

import settings as cfg

_ARDUINO_NOTE = (
    "Hard-set in Arduino firmware.\n"
    "Will become configurable in a future firmware update."
)


class SettingsPanel(QGroupBox):
    """Threshold and limit settings read at test-start time."""

    def __init__(self, parent=None) -> None:
        super().__init__("Test Settings", parent)
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(4)
        root.setContentsMargins(6, 6, 6, 6)

        form = QFormLayout()
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

        # --- Arduino-controlled limits (display only) ---
        self._travel = dsb(1, 500, 1, " mm")
        self._load   = dsb(1, 9999, 10, " kg")
        self._travel.setValue(cfg.get("travel_limit_mm"))
        self._load.setValue(cfg.get("load_limit_kg"))
        self._travel.setEnabled(False)
        self._load.setEnabled(False)
        self._travel.setToolTip(_ARDUINO_NOTE)
        self._load.setToolTip(_ARDUINO_NOTE)

        arduino_note = QLabel("⚠  Travel & load limits are set in Arduino firmware")
        arduino_note.setWordWrap(True)
        arduino_note.setStyleSheet("color: #888; font-size: 8pt; font-style: italic;")

        form.addRow("Travel limit:", self._travel)
        form.addRow("Load limit:", self._load)
        root.addLayout(form)
        root.addWidget(arduino_note)

        # --- Software fracture detection ---
        sep = QLabel("— Fracture detection (software) —")
        sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sep.setStyleSheet("color: #555; font-size: 8pt;")
        root.addWidget(sep)

        drop_form = QFormLayout()
        drop_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        drop_form.setSpacing(5)

        self._drop_pct = dsb(1, 99, 1, " %")
        self._drop_win = isb(3, 100)
        self._drop_pct.setValue(cfg.get("load_drop_pct"))
        self._drop_win.setValue(int(cfg.get("load_drop_window")))

        self._drop_pct.setToolTip(
            "Stop the test when load drops this percentage from\n"
            "the rolling peak within the sample window."
        )
        self._drop_win.setToolTip("Number of samples over which the drop is evaluated.")

        drop_form.addRow("Load drop  ≥:", self._drop_pct)
        drop_form.addRow("Over  N  samples:", self._drop_win)
        root.addLayout(drop_form)

        # Persist fracture detection settings on change
        self._drop_pct.valueChanged.connect(lambda v: cfg.set("load_drop_pct", v))
        self._drop_win.valueChanged.connect(lambda v: cfg.set("load_drop_window", v))

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

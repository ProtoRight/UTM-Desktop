"""Machine control panel — buttons mapped to Arduino serial commands."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QDoubleSpinBox, QWidget, QFrame, QCheckBox,
)

import settings as cfg


def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


class ControlPanel(QGroupBox):
    """Emits command signals; the main window routes them to the serial worker."""

    cmd_run_3pt   = pyqtSignal()
    cmd_run_t     = pyqtSignal()
    cmd_stop      = pyqtSignal()
    cmd_tare      = pyqtSignal()
    cmd_zero      = pyqtSignal()
    cmd_jog_speed  = pyqtSignal(float)
    cmd_test_speed = pyqtSignal(float)
    cmd_idle       = pyqtSignal()
    cmd_raw        = pyqtSignal()
    cmd_cal        = pyqtSignal()
    abs_changed    = pyqtSignal(bool)   # emitted when absolute-value mode toggled

    def __init__(self, parent=None) -> None:
        super().__init__("Controls", parent)
        self._build_ui()
        self.set_connected(False)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(5)

        # --- Test buttons ---
        self._btn_3pt = QPushButton("▶  Run 3-Point Bend")
        self._btn_3pt.setMinimumHeight(34)
        self._btn_t = QPushButton("▶  Run Tensile")
        self._btn_t.setMinimumHeight(34)
        self._btn_stop = QPushButton("■  Stop")
        self._btn_stop.setMinimumHeight(34)
        self._btn_stop.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: white; font-weight: bold; }"
            "QPushButton:disabled { background-color: #888; color: #bbb; }"
        )
        root.addWidget(self._btn_3pt)
        root.addWidget(self._btn_t)
        root.addWidget(self._btn_stop)

        # --- Utility buttons ---
        util_row = QHBoxLayout()
        self._btn_tare = QPushButton("Tare Load")
        self._btn_zero = QPushButton("Zero Disp.")
        util_row.addWidget(self._btn_tare)
        util_row.addWidget(self._btn_zero)
        root.addLayout(util_row)

        # --- Speed controls ---
        root.addWidget(_separator())

        def _speed_row(label: str, default: float):
            """Return (layout, spinbox, button) for a speed row."""
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            sb = QDoubleSpinBox()
            sb.setRange(1.0, 150.0)
            sb.setValue(default)
            sb.setDecimals(1)
            sb.setSingleStep(5.0)
            sb.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
            row.addWidget(sb, 1)
            row.addWidget(QLabel("mm/min"))
            btn = QPushButton("Set")
            btn.setFixedWidth(38)
            row.addWidget(btn)
            return row, sb, btn

        jog_row, self._jog_spin, self._btn_set_jog = _speed_row(
            "Jog speed:", cfg.get("default_jog_speed")
        )
        test_row, self._test_spin, self._btn_set_test = _speed_row(
            "Test speed:", cfg.get("default_test_speed")
        )
        self._test_spin.setToolTip(
            "Crosshead speed used during a test run.\n"
            "Sent to the Arduino as TESTSPEED <value>."
        )
        root.addLayout(jog_row)
        root.addLayout(test_row)

        # Motor enabled indicator
        self._motor_label = QLabel("Motor: —")
        self._motor_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._motor_label)

        # Absolute-value mode
        self._chk_abs = QCheckBox("Use |absolute| values during test")
        self._chk_abs.setToolTip(
            "When checked, displacement and load are treated as absolute values\n"
            "for graphing and calculations.  Live readouts are unaffected.\n"
            "Both signed and absolute values are always written to the CSV."
        )
        root.addWidget(self._chk_abs)
        self._chk_abs.toggled.connect(self.abs_changed)

        # --- Machine state buttons ---
        root.addWidget(_separator())
        state_lbl = QLabel("Machine state:")
        state_lbl.setStyleSheet("color: #666; font-size: 8pt;")
        root.addWidget(state_lbl)
        state_row = QHBoxLayout()
        self._btn_idle = QPushButton("IDLE")
        self._btn_raw  = QPushButton("RAW")
        self._btn_cal  = QPushButton("CAL")
        for btn in (self._btn_idle, self._btn_raw, self._btn_cal):
            btn.setMinimumHeight(26)
            state_row.addWidget(btn)
        root.addLayout(state_row)

        # --- Wire up ---
        self._btn_3pt.clicked.connect(self.cmd_run_3pt)
        self._btn_t.clicked.connect(self.cmd_run_t)
        self._btn_stop.clicked.connect(self.cmd_stop)
        self._btn_tare.clicked.connect(self.cmd_tare)
        self._btn_zero.clicked.connect(self.cmd_zero)
        self._btn_set_jog.clicked.connect(
            lambda: self.cmd_jog_speed.emit(self._jog_spin.value())
        )
        self._btn_set_test.clicked.connect(
            lambda: self.cmd_test_speed.emit(self._test_spin.value())
        )
        self._btn_idle.clicked.connect(self.cmd_idle)
        self._btn_raw.clicked.connect(self.cmd_raw)
        self._btn_cal.clicked.connect(self.cmd_cal)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_connected(self, connected: bool) -> None:
        for btn in (self._btn_3pt, self._btn_t, self._btn_stop,
                    self._btn_tare, self._btn_zero,
                    self._btn_set_jog, self._btn_set_test,
                    self._btn_idle, self._btn_raw, self._btn_cal):
            btn.setEnabled(connected)
        if not connected:
            self._motor_label.setText("Motor: —")
            self._motor_label.setStyleSheet("")

    def set_running(self, running: bool) -> None:
        self._btn_3pt.setEnabled(not running)
        self._btn_t.setEnabled(not running)
        self._btn_stop.setEnabled(running)
        self._btn_tare.setEnabled(not running)
        self._btn_zero.setEnabled(not running)
        # Changing test speed mid-run has no effect on the Arduino, so disable
        self._btn_set_test.setEnabled(not running)

    def set_idle(self) -> None:
        self.set_connected(True)
        self._btn_stop.setEnabled(False)

    @property
    def use_absolute(self) -> bool:
        return self._chk_abs.isChecked()

    def update_motor_state(self, enabled: bool) -> None:
        if enabled:
            self._motor_label.setText("Motor: ENABLED")
            self._motor_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        else:
            self._motor_label.setText("Motor: disabled")
            self._motor_label.setStyleSheet("color: #888;")

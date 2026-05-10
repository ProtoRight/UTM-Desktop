"""Machine control panel — buttons that map to Arduino serial commands."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QDoubleSpinBox, QWidget,
)


class ControlPanel(QGroupBox):
    """Emits command signals; the main window routes them to the serial worker."""

    cmd_run_3pt   = pyqtSignal()
    cmd_run_t     = pyqtSignal()
    cmd_stop      = pyqtSignal()
    cmd_tare      = pyqtSignal()
    cmd_zero      = pyqtSignal()
    cmd_jog_speed = pyqtSignal(float)   # new speed value in mm/min

    def __init__(self, parent=None) -> None:
        super().__init__("Controls", parent)
        self._build_ui()
        self.set_connected(False)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # Test buttons
        self._btn_3pt = QPushButton("▶  Run 3-Point Bend")
        self._btn_3pt.setMinimumHeight(34)
        self._btn_t   = QPushButton("▶  Run Tensile")
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

        # Utility buttons
        util_row = QHBoxLayout()
        self._btn_tare = QPushButton("Tare Load")
        self._btn_zero = QPushButton("Zero Disp.")
        util_row.addWidget(self._btn_tare)
        util_row.addWidget(self._btn_zero)
        root.addLayout(util_row)

        # Jog speed
        jog_row = QHBoxLayout()
        jog_row.addWidget(QLabel("Jog speed:"))
        self._jog_spin = QDoubleSpinBox()
        self._jog_spin.setRange(1.0, 150.0)
        self._jog_spin.setValue(50.0)
        self._jog_spin.setSuffix(" mm/min")
        self._jog_spin.setDecimals(1)
        self._jog_spin.setSingleStep(5.0)
        jog_row.addWidget(self._jog_spin, 1)
        self._btn_set_jog = QPushButton("Set")
        self._btn_set_jog.setFixedWidth(40)
        jog_row.addWidget(self._btn_set_jog)
        root.addLayout(jog_row)

        # Motor enabled indicator (read-only display)
        self._motor_label = QLabel("Motor: —")
        self._motor_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._motor_label)

        # --- wire up ---
        self._btn_3pt.clicked.connect(self.cmd_run_3pt)
        self._btn_t.clicked.connect(self.cmd_run_t)
        self._btn_stop.clicked.connect(self.cmd_stop)
        self._btn_tare.clicked.connect(self.cmd_tare)
        self._btn_zero.clicked.connect(self.cmd_zero)
        self._btn_set_jog.clicked.connect(
            lambda: self.cmd_jog_speed.emit(self._jog_spin.value())
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_connected(self, connected: bool) -> None:
        for btn in (self._btn_3pt, self._btn_t, self._btn_stop,
                    self._btn_tare, self._btn_zero, self._btn_set_jog):
            btn.setEnabled(connected)
        if not connected:
            self._motor_label.setText("Motor: —")

    def set_running(self, running: bool) -> None:
        """While a test is running: disable start buttons, enable stop."""
        self._btn_3pt.setEnabled(not running)
        self._btn_t.setEnabled(not running)
        self._btn_stop.setEnabled(running)
        self._btn_tare.setEnabled(not running)
        self._btn_zero.setEnabled(not running)

    def set_idle(self) -> None:
        """Restore full-connected button states after test finishes."""
        self.set_connected(True)
        self._btn_stop.setEnabled(False)

    def update_motor_state(self, enabled: bool) -> None:
        if enabled:
            self._motor_label.setText("Motor: ENABLED")
            self._motor_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        else:
            self._motor_label.setText("Motor: disabled")
            self._motor_label.setStyleSheet("color: #888;")

    def set_jog_speed_display(self, speed: float) -> None:
        self._jog_spin.setValue(speed)

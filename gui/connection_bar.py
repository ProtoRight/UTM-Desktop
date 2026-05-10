"""Top connection bar — COM port selector, connect/disconnect, live status."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QComboBox, QPushButton,
)

from serial_worker import list_ports


class ConnectionBar(QWidget):
    """Emits connect_requested(port) and disconnect_requested signals."""

    connect_requested    = pyqtSignal(str)
    disconnect_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._connected = False
        self._build_ui()
        self.refresh_ports()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(QLabel("COM port:"))

        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(120)
        layout.addWidget(self._port_combo)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedWidth(62)
        self._refresh_btn.clicked.connect(self.refresh_ports)
        layout.addWidget(self._refresh_btn)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setFixedWidth(86)
        self._connect_btn.clicked.connect(self._on_connect_clicked)
        layout.addWidget(self._connect_btn)

        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet("color: #888; font-size: 14px;")
        layout.addWidget(self._status_dot)

        self._status_label = QLabel("Disconnected")
        layout.addWidget(self._status_label)

        layout.addStretch()

        # Live readouts (always visible, populated when connected)
        self._load_label = QLabel("Load:  —")
        self._disp_label = QLabel("Disp:  —")
        self._state_label = QLabel("State:  —")
        for lbl in (self._state_label, self._disp_label, self._load_label):
            lbl.setMinimumWidth(130)
            layout.addWidget(lbl)

    # ------------------------------------------------------------------
    def refresh_ports(self) -> None:
        current = self._port_combo.currentText()
        ports = list_ports()
        self._port_combo.clear()
        if ports:
            self._port_combo.addItems(ports)
            if current in ports:
                self._port_combo.setCurrentText(current)
        else:
            self._port_combo.addItem("(none found)")

    def _on_connect_clicked(self) -> None:
        if self._connected:
            self.disconnect_requested.emit()
        else:
            port = self._port_combo.currentText()
            if port and port != "(none found)":
                self.connect_requested.emit(port)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        self._port_combo.setEnabled(not connected)
        self._refresh_btn.setEnabled(not connected)
        if connected:
            self._connect_btn.setText("Disconnect")
            self._status_dot.setStyleSheet("color: #27ae60; font-size: 14px;")
            self._status_label.setText("Connected")
        else:
            self._connect_btn.setText("Connect")
            self._status_dot.setStyleSheet("color: #888; font-size: 14px;")
            self._status_label.setText("Disconnected")
            self._load_label.setText("Load:  —")
            self._disp_label.setText("Disp:  —")
            self._state_label.setText("State:  —")

    def set_arduino_verified(self, verified: bool) -> None:
        """Turns dot green/orange to show whether Arduino data is being received."""
        if verified:
            self._status_dot.setStyleSheet("color: #27ae60; font-size: 14px;")
            self._status_label.setText("Connected  ✓ Arduino detected")
        else:
            self._status_dot.setStyleSheet("color: #e67e22; font-size: 14px;")
            self._status_label.setText("Connected  — awaiting data…")

    def update_live(self, disp: float, load: float, state: str) -> None:
        self._disp_label.setText(f"Disp:  {disp:.3f} mm")
        self._load_label.setText(f"Load:  {load:.3f} kg")
        self._state_label.setText(f"State:  {state}")

    def set_estop(self, active: bool) -> None:
        if active:
            self._state_label.setStyleSheet(
                "color: white; background-color: #c0392b; "
                "font-weight: bold; padding: 2px 4px; border-radius: 3px;"
            )
            self._state_label.setText("State:  E-STOP")
        else:
            self._state_label.setStyleSheet("")

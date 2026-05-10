"""Top connection bar — COM port selector, connect/disconnect, live status, unit selectors."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QComboBox, QPushButton, QFrame,
)

from serial_worker import list_ports
from units import LoadUnit, DispUnit


def _vsep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.VLine)
    f.setFrameShadow(QFrame.Shadow.Sunken)
    return f


class ConnectionBar(QWidget):
    connect_requested    = pyqtSignal(str)
    disconnect_requested = pyqtSignal()
    load_unit_changed    = pyqtSignal(object)   # LoadUnit
    disp_unit_changed    = pyqtSignal(object)   # DispUnit

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._connected = False
        self._build_ui()
        self.refresh_ports()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # --- Connection controls ---
        layout.addWidget(QLabel("COM port:"))
        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(110)
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

        # --- Live readouts ---
        self._state_label = QLabel("State:  —")
        self._disp_label  = QLabel("Disp:  —")
        self._load_label  = QLabel("Load:  —")
        for lbl in (self._state_label, self._disp_label, self._load_label):
            lbl.setMinimumWidth(130)
            layout.addWidget(lbl)

        layout.addWidget(_vsep())

        # --- Display unit selectors ---
        layout.addWidget(QLabel("Load:"))
        self._load_unit_combo = QComboBox()
        self._load_unit_combo.addItems([u.value for u in LoadUnit])
        self._load_unit_combo.setFixedWidth(52)
        layout.addWidget(self._load_unit_combo)

        layout.addWidget(QLabel("Disp:"))
        self._disp_unit_combo = QComboBox()
        self._disp_unit_combo.addItems([u.value for u in DispUnit])
        self._disp_unit_combo.setFixedWidth(46)
        layout.addWidget(self._disp_unit_combo)

        self._load_unit_combo.currentIndexChanged.connect(self._on_load_unit_changed)
        self._disp_unit_combo.currentIndexChanged.connect(self._on_disp_unit_changed)

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

    def _on_load_unit_changed(self, idx: int) -> None:
        self.load_unit_changed.emit(list(LoadUnit)[idx])

    def _on_disp_unit_changed(self, idx: int) -> None:
        self.disp_unit_changed.emit(list(DispUnit)[idx])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def current_load_unit(self) -> LoadUnit:
        return list(LoadUnit)[self._load_unit_combo.currentIndex()]

    def current_disp_unit(self) -> DispUnit:
        return list(DispUnit)[self._disp_unit_combo.currentIndex()]

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        self._port_combo.setEnabled(not connected)
        self._refresh_btn.setEnabled(not connected)
        if connected:
            self._connect_btn.setText("Disconnect")
            self._status_dot.setStyleSheet("color: #e67e22; font-size: 14px;")
            self._status_label.setText("Connected — awaiting data…")
        else:
            self._connect_btn.setText("Connect")
            self._status_dot.setStyleSheet("color: #888; font-size: 14px;")
            self._status_label.setText("Disconnected")
            self._load_label.setText("Load:  —")
            self._disp_label.setText("Disp:  —")
            self._state_label.setText("State:  —")

    def set_arduino_verified(self, verified: bool) -> None:
        if verified:
            self._status_dot.setStyleSheet("color: #27ae60; font-size: 14px;")
            self._status_label.setText("Connected  ✓ Arduino detected")

    def update_live(self, disp_val: float, load_val: float,
                    disp_unit: str, load_unit: str, state: str) -> None:
        self._disp_label.setText(f"Disp:  {disp_val:.3f} {disp_unit}")
        self._load_label.setText(f"Load:  {load_val:.3f} {load_unit}")
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

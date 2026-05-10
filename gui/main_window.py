"""Main application window — wires together all panels and the serial worker."""

from __future__ import annotations

import csv
import os
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QScrollArea, QFileDialog, QMessageBox,
)

import settings as cfg
import line_parser as prs
from data_store import TestData
from serial_worker import SerialWorker
from calculations import (
    SpecimenData, calculate_bend, calculate_tensile,
)

from gui.connection_bar  import ConnectionBar
from gui.control_panel   import ControlPanel
from gui.live_graph      import LiveGraph
from gui.results_panel   import ResultsPanel
from gui.serial_log      import SerialLog
from gui.specimen_panel  import SpecimenPanel
from gui.settings_panel  import SettingsPanel


class MainWindow(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("UTM Desktop")
        self.setMinimumSize(1280, 780)

        self._worker: Optional[SerialWorker] = None
        self._test_data = TestData()
        self._machine_state = "DISCONNECTED"
        self._arduino_verified = False
        self._current_test_type: Optional[str] = None  # "3PT" | "TENSILE"

        cfg.load()
        self._build_ui()

        # Graph refresh timer (200 ms matches Arduino sample rate)
        self._graph_timer = QTimer(self)
        self._graph_timer.setInterval(200)
        self._graph_timer.timeout.connect(self._refresh_graph)

    # ==================================================================
    # UI construction
    # ==================================================================

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 4)
        root.setSpacing(6)

        # --- connection bar (top) ---
        self._conn_bar = ConnectionBar()
        self._conn_bar.connect_requested.connect(self._on_connect)
        self._conn_bar.disconnect_requested.connect(self._on_disconnect)
        root.addWidget(self._conn_bar)

        # --- main content splitter ---
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = self._build_left_panel()
        splitter.addWidget(left)

        right = self._build_right_panel()
        splitter.addWidget(right)

        splitter.setSizes([330, 950])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        # --- serial log (bottom) ---
        self._serial_log = SerialLog()
        root.addWidget(self._serial_log)

    # ------------------------------------------------------------------
    def _build_left_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedWidth(335)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        self._ctrl = ControlPanel()
        self._ctrl.cmd_run_3pt.connect(lambda: self._send_test("3PT"))
        self._ctrl.cmd_run_t.connect(lambda: self._send_test("TENSILE"))
        self._ctrl.cmd_stop.connect(self._send_stop)
        self._ctrl.cmd_tare.connect(lambda: self._send("TARE"))
        self._ctrl.cmd_zero.connect(lambda: self._send("ZERO"))
        self._ctrl.cmd_jog_speed.connect(
            lambda v: self._send(f"JOGSPEED {v:.1f}")
        )
        layout.addWidget(self._ctrl)

        self._specimen = SpecimenPanel()
        layout.addWidget(self._specimen)

        self._settings = SettingsPanel()
        layout.addWidget(self._settings)

        layout.addStretch()
        scroll.setWidget(inner)
        return scroll

    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._graph = LiveGraph()
        layout.addWidget(self._graph, 1)

        self._results = ResultsPanel()
        self._results.export_requested.connect(self._on_export_csv)
        self._results.setFixedHeight(240)
        layout.addWidget(self._results)

        return w

    # ==================================================================
    # Serial connection management
    # ==================================================================

    def _on_connect(self, port: str) -> None:
        self._worker = SerialWorker(port, self)
        self._worker.line_received.connect(self._on_line)
        self._worker.connection_changed.connect(self._on_connection_changed)
        self._worker.error_occurred.connect(self._on_serial_error)
        self._worker.start()

    def _on_disconnect(self) -> None:
        if self._worker:
            self._worker.stop()
            self._worker = None
        self._machine_state = "DISCONNECTED"
        self._arduino_verified = False
        self._graph_timer.stop()
        self._ctrl.set_connected(False)
        self._conn_bar.set_connected(False)
        self._conn_bar.set_arduino_verified(False)

    def _on_connection_changed(self, connected: bool) -> None:
        self._conn_bar.set_connected(connected)
        if connected:
            self._machine_state = "IDLE"
            self._ctrl.set_connected(True)
            self._ctrl.set_idle()
            self._conn_bar.set_arduino_verified(False)
        else:
            self._machine_state = "DISCONNECTED"
            self._ctrl.set_connected(False)
            self._graph_timer.stop()

    def _on_serial_error(self, msg: str) -> None:
        QMessageBox.warning(self, "Serial Error", msg)
        self._on_disconnect()

    def _send(self, cmd: str) -> None:
        if self._worker:
            self._worker.send(cmd)

    # ==================================================================
    # Incoming data handling
    # ==================================================================

    def _on_line(self, line: str) -> None:
        self._serial_log.append(line)

        parsed = prs.parse_line(line)

        # Verify Arduino on first meaningful line
        if not self._arduino_verified and (parsed.reading or parsed.event):
            self._arduino_verified = True
            self._conn_bar.set_arduino_verified(True)

        # Handle readings
        if parsed.reading:
            r = parsed.reading
            if r.motor_enabled is not None:
                self._ctrl.update_motor_state(r.motor_enabled)
            if r.jog_speed is not None:
                self._ctrl.set_jog_speed_display(r.jog_speed)

            self._conn_bar.update_live(r.displacement, r.load, self._machine_state)

            # Record data during a test run
            if self._machine_state in ("RUNNING_3PT", "RUNNING_T"):
                self._test_data.add_point(r.displacement, r.load)
                self._check_completion_conditions(r.displacement, r.load)

        # Handle state events
        if parsed.event:
            self._handle_event(parsed.event, line)

    def _handle_event(self, event: str, raw_line: str) -> None:
        if event == prs.EVT_BOOT:
            self._machine_state = "IDLE"
            self._ctrl.set_idle()

        elif event == prs.EVT_IDLE:
            self._machine_state = "IDLE"
            self._ctrl.set_idle()
            self._graph_timer.stop()

        elif event == prs.EVT_RUN_3PT:
            self._machine_state = "RUNNING_3PT"
            self._ctrl.set_running(True)
            self._graph_timer.start()

        elif event == prs.EVT_RUN_T:
            self._machine_state = "RUNNING_T"
            self._ctrl.set_running(True)
            self._graph_timer.start()

        elif event in (prs.EVT_FINISHED, prs.EVT_ABORT_TRAVEL, prs.EVT_ABORT_LOAD):
            self._on_test_complete("arduino")

        elif event == prs.EVT_ESTOP:
            self._machine_state = "ESTOP"
            self._graph_timer.stop()
            self._ctrl.set_connected(True)
            self._ctrl.set_idle()
            self._ctrl.set_running(False)
            self._conn_bar.set_estop(True)
            if not self._test_data.is_empty():
                self._on_test_complete("estop")

        elif event == prs.EVT_TARED:
            pass  # acknowledged in serial log

        elif event == prs.EVT_ZEROED:
            pass

    # ------------------------------------------------------------------
    # Completion detection (software-side)
    # ------------------------------------------------------------------

    def _check_completion_conditions(self, disp: float, load: float) -> None:
        s = self._settings
        reason: Optional[str] = None

        if self._test_data.check_travel_limit(s.travel_limit_mm):
            reason = "travel"
        elif self._test_data.check_load_limit(s.load_limit_kg):
            reason = "load"
        elif self._test_data.check_load_drop(s.load_drop_pct, s.load_drop_window):
            reason = "drop"

        if reason:
            self._send("STOP")
            self._on_test_complete(reason)

    def _on_test_complete(self, reason: str) -> None:
        if self._machine_state not in ("RUNNING_3PT", "RUNNING_T"):
            return

        was_3pt = self._machine_state == "RUNNING_3PT"
        self._machine_state = "FINISHED"
        self._test_data.completion_reason = reason
        self._graph_timer.stop()
        self._ctrl.set_idle()
        self._conn_bar.set_estop(False)

        # Final graph refresh and completion marker
        disp_list = self._test_data.displacements()
        load_list  = self._test_data.loads()
        self._graph.update_data(disp_list, load_list)
        if disp_list:
            self._graph.mark_completion(disp_list[-1], load_list[-1])

        # Calculate and display results
        specimen = self._specimen.get_specimen_data()
        if was_3pt:
            results = calculate_bend(disp_list, load_list, specimen)
            self._results.show_bend_results(results)
        else:
            results = calculate_tensile(disp_list, load_list, specimen)
            self._results.show_tensile_results(results)

    # ------------------------------------------------------------------
    # Graph refresh (on timer)
    # ------------------------------------------------------------------

    def _refresh_graph(self) -> None:
        self._graph.update_data(
            self._test_data.displacements(),
            self._test_data.loads(),
        )

    # ==================================================================
    # Test initiation
    # ==================================================================

    def _send_test(self, test_type: str) -> None:
        """Clear previous data, update graph title, send run command."""
        self._test_data.clear()
        self._results.clear()
        self._graph.clear()

        specimen = self._specimen.get_specimen_data()
        label = "3-Point Bend" if test_type == "3PT" else "Tensile"
        title_parts = [label]
        if specimen.sample_id:
            title_parts.append(specimen.sample_id)
        if specimen.material:
            title_parts.append(specimen.material)
        self._graph.set_title(" — ".join(title_parts))

        self._current_test_type = test_type
        self._send("RUN_3PT" if test_type == "3PT" else "RUN_T")

    def _send_stop(self) -> None:
        self._send("STOP")

    # ==================================================================
    # CSV export
    # ==================================================================

    def _on_export_csv(self) -> None:
        if self._test_data.is_empty():
            QMessageBox.information(self, "No Data", "No test data to export.")
            return

        specimen = self._specimen.get_specimen_data()
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
        sid = specimen.sample_id or "unknown"
        tt  = "3PT" if self._current_test_type == "3PT" else "T"
        default_name = f"{ts}_{sid}_{tt}_raw.csv"

        export_dir = cfg.get("csv_export_dir")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save CSV",
            os.path.join(export_dir, default_name),
            "CSV files (*.csv)",
        )
        if not path:
            return

        cfg.set("csv_export_dir", os.path.dirname(path))

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # Header metadata
            writer.writerow(["UTM Desktop Export"])
            writer.writerow(["Date", ts])
            writer.writerow(["Material", specimen.material])
            writer.writerow(["Sample ID", specimen.sample_id])
            writer.writerow(["Test type", "3-Point Bend" if tt == "3PT" else "Tensile"])
            writer.writerow(["Geometry", specimen.geometry])
            writer.writerow(["Completion reason", self._test_data.completion_reason or "—"])
            writer.writerow([])
            # Specimen dimensions
            if specimen.geometry == "rectangular":
                writer.writerow(["Width b (mm)", specimen.width_mm])
                writer.writerow(["Thickness d (mm)", specimen.thickness_mm])
            elif specimen.geometry == "circular":
                writer.writerow(["Diameter d (mm)", specimen.diameter_mm])
            elif specimen.geometry == "hollow":
                writer.writerow(["Outer dia. D (mm)", specimen.outer_dia_mm])
                writer.writerow(["Inner dia. d (mm)", specimen.inner_dia_mm])
            if specimen.test_type == "3PT":
                writer.writerow(["Span L (mm)", specimen.span_mm])
            else:
                writer.writerow(["Gauge length L0 (mm)", specimen.gauge_length_mm])
            writer.writerow([])
            # Raw data
            writer.writerow(["Displacement (mm)", "Load (kg)"])
            for disp, load in self._test_data.points:
                writer.writerow([f"{disp:.4f}", f"{load:.4f}"])

        QMessageBox.information(self, "Exported", f"Data saved to:\n{path}")

    # ==================================================================
    # Close event — cleanly shut down serial thread
    # ==================================================================

    def closeEvent(self, event) -> None:
        if self._worker:
            self._worker.stop()
        event.accept()

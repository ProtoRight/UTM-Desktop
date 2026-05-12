"""Main application window."""

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
    G, SpecimenData, BendResults, TensileResults,
    calculate_bend, calculate_tensile, preprocess,
)
from units import (
    LoadUnit, DispUnit, ResultsUnit,
    MPa_TO_KSI,
    kg_to, mm_to, load_unit_label, disp_unit_label,
    convert_results_stress,
)

from gui.connection_bar       import ConnectionBar
from gui.control_panel        import ControlPanel
from gui.live_graph           import LiveGraph
from gui.results_panel        import ResultsPanel
from gui.serial_log           import SerialLog
from gui.specimen_panel       import SpecimenPanel
from gui.settings_panel       import SettingsPanel
from gui.load_display         import LoadDisplay
from gui.displacement_display import DisplacementDisplay


class MainWindow(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("UTM Desktop")
        self.setMinimumSize(1100, 720)

        self._worker: Optional[SerialWorker] = None
        self._test_data = TestData()
        self._machine_state = "DISCONNECTED"
        self._arduino_verified = False
        self._current_test_type: Optional[str] = None

        # Preprocessed data and results stored after test completion (always kg/mm)
        self._clean_disp: list[float] = []
        self._clean_load: list[float] = []
        self._completion_disp_mm: Optional[float] = None
        self._completion_load_kg: Optional[float] = None
        self._last_results: Optional[object] = None  # BendResults | TensileResults
        self._last_specimen: Optional[SpecimenData] = None
        self._graph_mode: str = "fd"   # "fd" = force/disp, "ss" = stress/strain

        # Current display units (internal data always kg / mm)
        self._load_unit = LoadUnit.KG
        self._disp_unit = DispUnit.MM

        cfg.load()
        self._build_ui()

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

        self._conn_bar = ConnectionBar()
        self._conn_bar.connect_requested.connect(self._on_connect)
        self._conn_bar.disconnect_requested.connect(self._on_disconnect)
        self._conn_bar.load_unit_changed.connect(self._on_load_unit_changed)
        self._conn_bar.disp_unit_changed.connect(self._on_disp_unit_changed)
        root.addWidget(self._conn_bar)

        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.setChildrenCollapsible(False)
        self._main_splitter.addWidget(self._build_left_panel())
        self._main_splitter.addWidget(self._build_right_panel())
        self._main_splitter.setSizes([340, 960])
        self._main_splitter.setStretchFactor(0, 0)
        self._main_splitter.setStretchFactor(1, 1)

        self._serial_log = SerialLog()
        self._serial_log.command_entered.connect(self._send)

        self._vert_splitter = QSplitter(Qt.Orientation.Vertical)
        self._vert_splitter.setChildrenCollapsible(False)
        self._vert_splitter.addWidget(self._main_splitter)
        self._vert_splitter.addWidget(self._serial_log)
        self._vert_splitter.setSizes([620, 150])
        self._vert_splitter.setStretchFactor(0, 1)
        self._vert_splitter.setStretchFactor(1, 0)
        root.addWidget(self._vert_splitter, 1)

    def _build_left_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(260)

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
        self._ctrl.cmd_jog_speed.connect(lambda v: self._send(f"JOGSPEED {v:.1f}"))
        self._ctrl.cmd_idle.connect(lambda: self._send("IDLE"))
        self._ctrl.cmd_raw.connect(lambda: self._send("RAW"))
        self._ctrl.cmd_cal.connect(lambda: self._send("CAL"))
        layout.addWidget(self._ctrl)

        disp_row = QHBoxLayout()
        self._load_display = LoadDisplay()
        self._load_display.setMinimumHeight(220)
        self._disp_display = DisplacementDisplay()
        disp_row.addWidget(self._load_display)
        disp_row.addWidget(self._disp_display)
        layout.addLayout(disp_row)

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
        self._graph.mode_changed.connect(self._on_graph_mode_changed)
        layout.addWidget(self._graph, 1)

        self._results = ResultsPanel()
        self._results.export_requested.connect(self._on_export_csv)
        self._results.recalculate_requested.connect(self._on_recalculate)
        self._results.overlays_changed.connect(self._apply_overlays)
        layout.addWidget(self._results)

        return w

    # ==================================================================
    # Unit management
    # ==================================================================

    def _on_load_unit_changed(self, unit: LoadUnit) -> None:
        self._load_unit = unit
        self._load_display.set_display_unit(unit)
        self._graph.set_axis_labels(
            self._disp_axis_label(), self._load_axis_label()
        )
        if not self._test_data.is_empty():
            self._refresh_graph()

    def _on_disp_unit_changed(self, unit: DispUnit) -> None:
        self._disp_unit = unit
        self._disp_display.set_display_unit(unit)
        self._graph.set_axis_labels(
            self._disp_axis_label(), self._load_axis_label()
        )
        # Refresh graph with rescaled data
        if not self._test_data.is_empty():
            self._refresh_graph()

    def _load_axis_label(self) -> str:
        return f"Load ({load_unit_label(self._load_unit)})"

    def _disp_axis_label(self) -> str:
        return f"Displacement ({disp_unit_label(self._disp_unit)})"

    def _convert_for_graph(
        self, disp_mm: list[float], load_kg: list[float]
    ) -> tuple[list[float], list[float]]:
        """Convert raw kg/mm lists to the current display units."""
        disp = [mm_to(d, self._disp_unit) for d in disp_mm]
        load = [kg_to(f, self._load_unit) for f in load_kg]
        return disp, load

    # ==================================================================
    # Serial connection
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

    def _on_connection_changed(self, connected: bool) -> None:
        self._conn_bar.set_connected(connected)
        if connected:
            self._machine_state = "IDLE"
            self._ctrl.set_connected(True)
            self._ctrl.set_idle()
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
    # Incoming data
    # ==================================================================

    def _on_line(self, line: str) -> None:
        self._serial_log.append(line)
        parsed = prs.parse_line(line)

        if not self._arduino_verified and (parsed.reading or parsed.event):
            self._arduino_verified = True
            self._conn_bar.set_arduino_verified(True)

        if parsed.reading:
            r = parsed.reading
            # Instrument displays (always in raw kg/mm internally)
            self._load_display.update_load(r.load)
            self._disp_display.update_displacement(r.displacement)
            # Connection bar — converted to display units
            self._conn_bar.update_live(
                mm_to(r.displacement, self._disp_unit),
                kg_to(r.load, self._load_unit),
                disp_unit_label(self._disp_unit),
                load_unit_label(self._load_unit),
                self._machine_state,
            )
            if r.motor_enabled is not None:
                self._ctrl.update_motor_state(r.motor_enabled)
            # Accumulate raw data during test (always in kg/mm)
            if self._machine_state in ("RUNNING_3PT", "RUNNING_T"):
                self._test_data.add_point(r.displacement, r.load)
                self._check_completion_conditions()

        if parsed.event:
            self._handle_event(parsed.event)

    def _handle_event(self, event: str) -> None:
        if event == prs.EVT_BOOT:
            self._machine_state = "IDLE"
            self._ctrl.set_idle()
        elif event == prs.EVT_IDLE:
            self._machine_state = "IDLE"
            self._ctrl.set_idle()
            self._graph_timer.stop()
            self._conn_bar.set_estop(False)
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
            self._conn_bar.set_estop(True)
            if not self._test_data.is_empty():
                self._on_test_complete("estop")

    # ------------------------------------------------------------------
    # Completion detection
    # ------------------------------------------------------------------

    def _check_completion_conditions(self) -> None:
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

        # Preprocess: trim errant start + offset to zero; cache for later refreshes
        clean_pts        = preprocess(self._test_data.points)
        disp_list        = [p[0] for p in clean_pts]
        load_list        = [p[1] for p in clean_pts]
        self._clean_disp = disp_list
        self._clean_load = load_list
        if disp_list:
            self._completion_disp_mm = disp_list[-1]
            self._completion_load_kg = load_list[-1]

        # Calculate first so _last_results is set before _refresh_graph
        specimen = self._specimen.get_specimen_data()
        self._run_calculations(was_3pt, specimen, disp_list, load_list)
        self._results.enable_recalculate(True)

        self._graph.clear()
        self._refresh_graph()

    def _run_calculations(
        self,
        is_3pt: bool,
        specimen: SpecimenData,
        disp_list: list[float],
        load_list: list[float],
    ) -> None:
        self._last_specimen = specimen
        if is_3pt:
            r = calculate_bend(disp_list, load_list, specimen)
            self._last_results = r
            self._results.set_yield_overlay_available(False)
            self._results.show_bend_results(r)
        else:
            r = calculate_tensile(disp_list, load_list, specimen)
            self._last_results = r
            self._results.set_yield_overlay_available(r.yield_strength_MPa is not None)
            self._results.show_tensile_results(r)

    # ------------------------------------------------------------------
    # Graph refresh (timer — converts to display units)
    # ------------------------------------------------------------------

    def _refresh_graph(self) -> None:
        disp_src = self._clean_disp or self._test_data.displacements()
        load_src = self._clean_load or self._test_data.loads()

        use_ss = (
            self._graph_mode == "ss"
            and self._last_results is not None
            and self._last_specimen is not None
        )
        if use_ss:
            x_data, y_data, x_lbl, y_lbl = self._to_stress_strain(disp_src, load_src)
        else:
            x_data, y_data = self._convert_for_graph(disp_src, load_src)
            x_lbl, y_lbl  = self._disp_axis_label(), self._load_axis_label()

        self._graph.set_axis_labels(x_lbl, y_lbl)
        self._graph.update_data(x_data, y_data)

        if self._completion_disp_mm is not None:
            if use_ss:
                cx, cy, _, _ = self._to_stress_strain(
                    [self._completion_disp_mm], [self._completion_load_kg]
                )
                self._graph.mark_completion(cx[0], cy[0])
            else:
                self._graph.mark_completion(
                    mm_to(self._completion_disp_mm, self._disp_unit),
                    kg_to(self._completion_load_kg, self._load_unit),
                )
        self._apply_overlays()

    # ------------------------------------------------------------------

    def _on_graph_mode_changed(self, mode: str) -> None:
        self._graph_mode = mode
        if self._clean_disp or not self._test_data.is_empty():
            self._graph.clear()
            self._refresh_graph()

    def _to_stress_strain(
        self,
        disp_mm: list[float],
        load_kg: list[float],
    ) -> tuple[list[float], list[float], str, str]:
        """Convert to stress/strain in the current results unit."""
        r = self._last_results
        s = self._last_specimen
        use_metric = (self._results.results_unit == ResultsUnit.METRIC)

        ok, _ = s.is_valid_for_test()
        if not ok:
            x, y = self._convert_for_graph(disp_mm, load_kg)
            return x, y, self._disp_axis_label(), self._load_axis_label()

        if isinstance(r, BendResults):
            c = s.outer_fibre_distance_mm()
            L = s.span_mm
            I = s.second_moment_of_area_mm4()
            if c <= 0 or L <= 0 or I <= 0:
                x, y = self._convert_for_graph(disp_mm, load_kg)
                return x, y, self._disp_axis_label(), self._load_axis_label()
            strain = [12.0 * d * c / L ** 2 for d in disp_mm]
            stress = [f * G * L * c / (4.0 * I) for f in load_kg]
            if not use_metric:
                stress = [v * MPa_TO_KSI for v in stress]
            return (
                strain, stress,
                "Flexural Strain (ε)",
                "Flexural Stress (MPa)" if use_metric else "Flexural Stress (ksi)",
            )
        else:
            L0 = s.gauge_length_mm
            A  = s.cross_section_area_mm2()
            if L0 <= 0 or A <= 0:
                x, y = self._convert_for_graph(disp_mm, load_kg)
                return x, y, self._disp_axis_label(), self._load_axis_label()
            strain = [d / L0 for d in disp_mm]
            stress = [f * G / A for f in load_kg]
            if not use_metric:
                stress = [v * MPa_TO_KSI for v in stress]
            return (
                strain, stress,
                "Strain (ε)",
                "Stress (MPa)" if use_metric else "Stress (ksi)",
            )

    # ==================================================================
    # Test initiation
    # ==================================================================

    def _send_test(self, test_type: str) -> None:
        self._test_data.clear()
        self._clean_disp = []
        self._clean_load = []
        self._completion_disp_mm = None
        self._completion_load_kg = None
        self._last_results  = None
        self._last_specimen = None
        self._results.clear()
        self._graph.clear()
        self._graph.set_axis_labels(self._disp_axis_label(), self._load_axis_label())

        specimen = self._specimen.get_specimen_data()
        label = "3-Point Bend" if test_type == "3PT" else "Tensile"
        parts = [label]
        if specimen.sample_id:
            parts.append(specimen.sample_id)
        if specimen.material:
            parts.append(specimen.material)
        self._graph.set_title(" — ".join(parts))

        self._current_test_type = test_type
        self._send("RUN_3PT" if test_type == "3PT" else "RUN_T")

    def _send_stop(self) -> None:
        self._send("STOP")

    # ==================================================================
    # Recalculate
    # ==================================================================

    def _on_recalculate(self) -> None:
        if self._test_data.is_empty():
            QMessageBox.information(self, "No Data",
                                    "No test data available to recalculate.")
            return
        is_3pt   = (self._current_test_type == "3PT")
        specimen = self._specimen.get_specimen_data()
        clean_pts        = preprocess(self._test_data.points)
        disp_list        = [p[0] for p in clean_pts]
        load_list        = [p[1] for p in clean_pts]
        self._clean_disp = disp_list
        self._clean_load = load_list
        if disp_list:
            self._completion_disp_mm = disp_list[-1]
            self._completion_load_kg = load_list[-1]

        label = "3-Point Bend" if is_3pt else "Tensile"
        parts = [label]
        if specimen.sample_id:
            parts.append(specimen.sample_id)
        if specimen.material:
            parts.append(specimen.material)
        self._graph.set_title(" — ".join(parts))

        self._run_calculations(is_3pt, specimen, disp_list, load_list)

        self._graph.clear()
        self._refresh_graph()

    # ==================================================================
    # Overlays
    # ==================================================================

    def _apply_overlays(self) -> None:
        """Recompute and apply all graph overlays in the current display units/mode."""
        r     = self._last_results
        flags = self._results.get_overlay_flags()

        if r is None:
            self._graph.clear_overlays()
            return

        lu          = self._load_unit
        du          = self._disp_unit
        s           = self._last_specimen
        use_ss      = (self._graph_mode == "ss" and s is not None)
        use_metric  = (self._results.results_unit == ResultsUnit.METRIC)
        stress_unit = "MPa" if use_metric else "ksi"

        def _fd_slope(slope_kg_per_mm: float) -> float:
            return slope_kg_per_mm * kg_to(1.0, lu) / mm_to(1.0, du)

        def _mpa(v: float) -> float:
            return v if use_metric else v * MPa_TO_KSI

        # ----------------------------------------------------------------
        # Modulus line
        # ----------------------------------------------------------------
        can_mod = (
            flags["modulus"]
            and r.linear_region_slope_kg_per_mm is not None
            and r.linear_region_onset_mm is not None
            and r.linear_region_onset_load_kg is not None
            and r.linear_region_end_mm is not None
        )
        if can_mod:
            label    = "Flexural E line" if isinstance(r, BendResults) else "Young's E line"
            onset_kg = r.linear_region_onset_load_kg
            if use_ss and s is not None:
                if isinstance(r, BendResults):
                    c = s.outer_fibre_distance_mm(); L = s.span_mm
                    I = s.second_moment_of_area_mm4()
                    if L > 0 and c > 0 and I > 0:
                        x0  = 12 * r.linear_region_onset_mm * c / L ** 2
                        y0  = _mpa(onset_kg * G * L * c / (4.0 * I))
                        x1  = 12 * r.peak_displacement_mm   * c / L ** 2
                        E_d = _mpa(r.flexural_modulus_GPa * 1000) if r.flexural_modulus_GPa else None
                        if E_d:
                            self._graph.set_modulus_line(x0, y0, x1, E_d, label)
                        else:
                            self._graph.hide_modulus_line()
                    else:
                        self._graph.hide_modulus_line()
                else:
                    L0 = s.gauge_length_mm
                    A  = s.cross_section_area_mm2()
                    if L0 > 0 and A > 0:
                        x0  = r.linear_region_onset_mm / L0
                        y0  = _mpa(onset_kg * G / A)
                        x1  = r.peak_displacement_mm   / L0
                        E_d = _mpa(r.youngs_modulus_GPa * 1000) if r.youngs_modulus_GPa else None
                        if E_d:
                            self._graph.set_modulus_line(x0, y0, x1, E_d, label)
                        else:
                            self._graph.hide_modulus_line()
                    else:
                        self._graph.hide_modulus_line()
            else:
                x0 = mm_to(r.linear_region_onset_mm, du)
                y0 = kg_to(onset_kg, lu)
                x1 = mm_to(r.peak_displacement_mm,   du)
                self._graph.set_modulus_line(
                    x0, y0, x1, _fd_slope(r.linear_region_slope_kg_per_mm), label
                )
        else:
            self._graph.hide_modulus_line()

        # ----------------------------------------------------------------
        # Peak load reference
        # ----------------------------------------------------------------
        if flags["peak_ref"]:
            if use_ss:
                if isinstance(r, BendResults):
                    y = _mpa(r.flexural_stress_MPa) if r.flexural_stress_MPa else None
                else:
                    y = _mpa(r.uts_MPa) if r.uts_MPa else None
                if y is not None:
                    self._graph.set_peak_ref_line(y, f"Peak: {y:.2f} {stress_unit}")
                else:
                    self._graph.hide_peak_ref_line()
            else:
                y = kg_to(r.peak_load_kg, lu)
                self._graph.set_peak_ref_line(y, f"Peak: {y:.2f} {load_unit_label(lu)}")
        else:
            self._graph.hide_peak_ref_line()

        # ----------------------------------------------------------------
        # Yield & 0.2 % offset  (tensile only)
        # ----------------------------------------------------------------
        can_yield = (
            flags["yield"]
            and isinstance(r, TensileResults)
            and r.yield_strength_MPa is not None
            and r.linear_region_slope_kg_per_mm is not None
            and r.linear_region_onset_mm is not None
            and s is not None
        )
        if can_yield:
            L0 = s.gauge_length_mm
            A  = s.cross_section_area_mm2()
            if use_ss and L0 > 0:
                y_val = _mpa(r.yield_strength_MPa)
                self._graph.set_yield_hline(y_val, f"Yield: {y_val:.2f} {stress_unit}")
                E_d = _mpa(r.youngs_modulus_GPa * 1000) if r.youngs_modulus_GPa else None
                if E_d and L0 > 0:
                    x_off = r.linear_region_onset_mm / L0 + 0.002
                    x_end = r.peak_displacement_mm   / L0
                    self._graph.set_offset_line(x_off, x_end, E_d, "0.2 % offset")
                else:
                    self._graph.hide_offset_line()
            else:
                yield_kg = r.yield_strength_MPa * A / G
                y_disp   = kg_to(yield_kg, lu)
                self._graph.set_yield_hline(y_disp, f"Yield: {y_disp:.2f} {load_unit_label(lu)}")
                x_off = mm_to(r.linear_region_onset_mm + 0.002 * L0, du)
                x_end = mm_to(r.peak_displacement_mm, du)
                self._graph.set_offset_line(
                    x_off, x_end, _fd_slope(r.linear_region_slope_kg_per_mm),
                    "0.2 % offset",
                )
        else:
            self._graph.hide_yield_hline()
            self._graph.hide_offset_line()

    # ==================================================================
    # CSV export (always raw kg/mm, with unit metadata)
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
            self, "Save CSV",
            os.path.join(export_dir, default_name),
            "CSV files (*.csv)",
        )
        if not path:
            return
        cfg.set("csv_export_dir", os.path.dirname(path))

        clean_pts = preprocess(self._test_data.points)
        is_3pt = (self._current_test_type == "3PT")

        # Determine if computed stress/strain columns are possible
        spec_ok, _ = specimen.is_valid_for_test()
        ss_params: Optional[dict] = None
        if spec_ok:
            if is_3pt:
                L = specimen.span_mm
                I = specimen.second_moment_of_area_mm4()
                c = specimen.outer_fibre_distance_mm()
                if L > 0 and I > 0 and c > 0:
                    ss_params = {"L": L, "I": I, "c": c}
            else:
                A  = specimen.cross_section_area_mm2()
                L0 = specimen.gauge_length_mm
                if A > 0 and L0 > 0:
                    ss_params = {"A": A, "L0": L0}

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["UTM Desktop Export"])
            writer.writerow(["Date", ts])
            writer.writerow(["Material", specimen.material])
            writer.writerow(["Sample ID", specimen.sample_id])
            writer.writerow(["Test type", "3-Point Bend" if tt == "3PT" else "Tensile"])
            writer.writerow(["Geometry", specimen.geometry])
            writer.writerow(["Completion reason", self._test_data.completion_reason or "—"])
            writer.writerow([])
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

            if ss_params:
                if is_3pt:
                    writer.writerow([
                        "Displacement (mm)", "Load (kg)",
                        "Flexural Strain (ε)", "Flexural Stress (MPa)",
                    ])
                else:
                    writer.writerow([
                        "Displacement (mm)", "Load (kg)",
                        "Engineering Strain (ε)", "Engineering Stress (MPa)",
                    ])
            else:
                writer.writerow(["Displacement (mm)", "Load (kg)"])

            for disp, load in clean_pts:
                F_N = load * G
                if ss_params and is_3pt:
                    strain = 12.0 * disp * ss_params["c"] / ss_params["L"] ** 2
                    stress = F_N * ss_params["L"] * ss_params["c"] / (4.0 * ss_params["I"])
                    writer.writerow([
                        f"{disp:.4f}", f"{load:.4f}",
                        f"{strain:.6f}", f"{stress:.4f}",
                    ])
                elif ss_params:
                    strain = disp / ss_params["L0"]
                    stress = F_N / ss_params["A"]
                    writer.writerow([
                        f"{disp:.4f}", f"{load:.4f}",
                        f"{strain:.6f}", f"{stress:.4f}",
                    ])
                else:
                    writer.writerow([f"{disp:.4f}", f"{load:.4f}"])

        QMessageBox.information(self, "Exported", f"Data saved to:\n{path}")

    # ==================================================================
    # Close
    # ==================================================================

    def closeEvent(self, event) -> None:
        if self._worker:
            self._worker.stop()
        event.accept()

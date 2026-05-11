"""Embedded matplotlib canvas for live Force vs Displacement graphing.

Autoscaling: grow-only during a test — the view only ever expands, never
shrinks, so data never jumps out of frame.

Zoom controls:
  - Scroll wheel: zoom in/out centred on cursor
  - + / - buttons: zoom from view centre
  - Fit: autoscale to data extents
  - Pan toggle: click-drag to pan
"""

from __future__ import annotations

import matplotlib
matplotlib.use("QtAgg")

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSizePolicy,
)

_ZOOM_FACTOR = 1.30
_AXIS_MARGIN = 0.08   # fractional margin added once when data first expands the view


class LiveGraph(QWidget):
    """Displays a real-time Force vs Displacement plot with grow-only autoscaling."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._fig = Figure(tight_layout=True)
        self._ax  = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self._pan_active = False
        self._pan_start  = None

        # Grow-only limits — updated only when data exceeds them
        self._data_xmax: float = 0.0
        self._data_ymax: float = 0.0
        self._data_ymin: float = 0.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._build_toolbar())
        layout.addWidget(self._canvas, 1)

        self._line,  = self._ax.plot([], [], color="#2980b9", linewidth=1.5)
        self._completion_dot, = self._ax.plot(
            [], [], "ro", markersize=8, label="Test end", visible=False
        )

        # Overlay artists — hidden until explicitly enabled
        self._modulus_line, = self._ax.plot(
            [], [], "--", color="#e74c3c", linewidth=1.4,
            label="Modulus line", visible=False, zorder=3,
        )
        self._offset_line, = self._ax.plot(
            [], [], ":", color="#f39c12", linewidth=1.4,
            label="0.2 % offset", visible=False, zorder=3,
        )
        self._peak_ref_line, = self._ax.plot(
            [-1e9, 1e9], [0, 0], "--", color="#27ae60", linewidth=1.0,
            label="Peak load", visible=False, zorder=2,
        )
        self._yield_hline, = self._ax.plot(
            [-1e9, 1e9], [0, 0], "--", color="#9b59b6", linewidth=1.0,
            label="Yield", visible=False, zorder=2,
        )

        self._x_label = "Displacement (mm)"
        self._y_label = "Load (kg)"
        self._setup_axes()

        self._canvas.mpl_connect("scroll_event",        self._on_scroll)
        self._canvas.mpl_connect("button_press_event",  self._on_mouse_press)
        self._canvas.mpl_connect("motion_notify_event", self._on_mouse_move)
        self._canvas.mpl_connect("button_release_event",self._on_mouse_release)

        self._canvas.draw()

    # ------------------------------------------------------------------
    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        self._btn_fit      = QPushButton("Fit")
        self._btn_zoom_in  = QPushButton("＋")
        self._btn_zoom_out = QPushButton("－")
        self._btn_pan      = QPushButton("Pan")
        self._btn_pan.setCheckable(True)

        for btn in (self._btn_fit, self._btn_zoom_in,
                    self._btn_zoom_out, self._btn_pan):
            btn.setFixedHeight(24)
            btn.setFixedWidth(46)
            row.addWidget(btn)

        row.addStretch()

        self._btn_fit.clicked.connect(self.fit_to_data)
        self._btn_zoom_in.clicked.connect(
            lambda: self._zoom_from_centre(1.0 / _ZOOM_FACTOR))
        self._btn_zoom_out.clicked.connect(
            lambda: self._zoom_from_centre(_ZOOM_FACTOR))
        self._btn_pan.toggled.connect(self._on_pan_toggled)
        return bar

    def _setup_axes(self) -> None:
        self._ax.set_xlabel(self._x_label, fontsize=10)
        self._ax.set_ylabel(self._y_label, fontsize=10)
        self._ax.set_title("Force vs Displacement", fontsize=11)
        self._ax.grid(True, linestyle="--", alpha=0.4)
        self._ax.set_xlim(0, 1)
        self._ax.set_ylim(0, 1)

    # ------------------------------------------------------------------
    # Grow-only autoscale
    # ------------------------------------------------------------------

    def _grow_axes(self, disp: list[float], load: list[float]) -> None:
        """Expand the view only when data exceeds the current padded limits."""
        if not disp:
            return

        x_max = max(disp)
        y_max = max(load)
        y_min = min(load)

        changed = False

        if x_max > self._data_xmax:
            self._data_xmax = x_max
            changed = True
        if y_max > self._data_ymax:
            self._data_ymax = y_max
            changed = True
        if y_min < self._data_ymin:
            self._data_ymin = y_min
            changed = True

        if changed:
            x_range = max(self._data_xmax, 0.001)
            y_range = max(self._data_ymax - self._data_ymin, 0.001)

            x_pad = x_range * _AXIS_MARGIN
            y_pad = y_range * _AXIS_MARGIN

            cur_xlim = self._ax.get_xlim()
            cur_ylim = self._ax.get_ylim()

            new_xmax = max(cur_xlim[1], self._data_xmax + x_pad)
            new_ymax = max(cur_ylim[1], self._data_ymax + y_pad)
            new_ymin = min(cur_ylim[0], self._data_ymin - y_pad, 0)

            self._ax.set_xlim(0, new_xmax)
            self._ax.set_ylim(new_ymin, new_ymax)

    # ------------------------------------------------------------------
    # Zoom / pan helpers
    # ------------------------------------------------------------------

    def _zoom_from_centre(self, factor: float) -> None:
        xlim = self._ax.get_xlim()
        ylim = self._ax.get_ylim()
        xc = (xlim[0] + xlim[1]) / 2
        yc = (ylim[0] + ylim[1]) / 2
        self._ax.set_xlim(xc - (xc - xlim[0]) * factor,
                          xc + (xlim[1] - xc) * factor)
        self._ax.set_ylim(yc - (yc - ylim[0]) * factor,
                          yc + (ylim[1] - yc) * factor)
        self._canvas.draw_idle()

    def _zoom_around(self, xd: float, yd: float, factor: float) -> None:
        xlim = self._ax.get_xlim()
        ylim = self._ax.get_ylim()
        self._ax.set_xlim(xd - (xd - xlim[0]) * factor,
                          xd + (xlim[1] - xd) * factor)
        self._ax.set_ylim(yd - (yd - ylim[0]) * factor,
                          yd + (ylim[1] - yd) * factor)
        self._canvas.draw_idle()

    # ------------------------------------------------------------------
    # Matplotlib event handlers
    # ------------------------------------------------------------------

    def _on_scroll(self, event) -> None:
        if event.inaxes is None:
            return
        factor = (1.0 / _ZOOM_FACTOR) if event.button == "up" else _ZOOM_FACTOR
        self._zoom_around(event.xdata, event.ydata, factor)

    def _on_pan_toggled(self, checked: bool) -> None:
        self._pan_active = checked
        cursor = (Qt.CursorShape.OpenHandCursor if checked
                  else Qt.CursorShape.ArrowCursor)
        self._canvas.setCursor(cursor)

    def _on_mouse_press(self, event) -> None:
        if self._pan_active and event.inaxes and event.button == 1:
            self._pan_start = (event.xdata, event.ydata)

    def _on_mouse_move(self, event) -> None:
        if (self._pan_active and self._pan_start is not None
                and event.inaxes and event.button == 1):
            dx = event.xdata - self._pan_start[0]
            dy = event.ydata - self._pan_start[1]
            xlim = self._ax.get_xlim()
            ylim = self._ax.get_ylim()
            self._ax.set_xlim(xlim[0] - dx, xlim[1] - dx)
            self._ax.set_ylim(ylim[0] - dy, ylim[1] - dy)
            self._canvas.draw_idle()

    def _on_mouse_release(self, _event) -> None:
        self._pan_start = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_data(self, disp: list[float], load: list[float]) -> None:
        """Update plot data and grow the view if needed. Never shrinks."""
        if not disp:
            return
        self._line.set_xdata(disp)
        self._line.set_ydata(load)
        self._grow_axes(disp, load)
        self._canvas.draw_idle()

    def fit_to_data(self) -> None:
        """Reset view to tightly fit all current data."""
        # Reset grow trackers so _grow_axes will recompute from scratch
        self._data_xmax = 0.0
        self._data_ymax = 0.0
        self._data_ymin = 0.0
        self._ax.set_xlim(0, 1)
        self._ax.set_ylim(0, 1)
        xdata = self._line.get_xdata()
        ydata = self._line.get_ydata()
        if len(xdata):
            self._grow_axes(list(xdata), list(ydata))
        self._canvas.draw_idle()

    def mark_completion(self, disp: float, load: float) -> None:
        self._completion_dot.set_xdata([disp])
        self._completion_dot.set_ydata([load])
        self._completion_dot.set_visible(True)
        self._update_legend()

    def clear(self) -> None:
        self._line.set_xdata([])
        self._line.set_ydata([])
        self._completion_dot.set_visible(False)
        self._data_xmax = 0.0
        self._data_ymax = 0.0
        self._data_ymin = 0.0
        self.clear_overlays()
        self._ax.set_xlim(0, 1)
        self._ax.set_ylim(0, 1)
        self._canvas.draw_idle()

    def set_title(self, title: str) -> None:
        self._ax.set_title(title, fontsize=11)
        self._canvas.draw_idle()

    def set_axis_labels(self, x_label: str, y_label: str) -> None:
        self._x_label = x_label
        self._y_label = y_label
        self._ax.set_xlabel(x_label, fontsize=10)
        self._ax.set_ylabel(y_label, fontsize=10)
        self._canvas.draw_idle()

    # ------------------------------------------------------------------
    # Overlay API
    # ------------------------------------------------------------------

    def set_modulus_line(self, x_end: float, slope: float, label: str) -> None:
        """Line from origin with given slope in current display units."""
        self._modulus_line.set_xdata([0.0, x_end])
        self._modulus_line.set_ydata([0.0, slope * x_end])
        self._modulus_line.set_label(label)
        self._modulus_line.set_visible(True)
        self._update_legend()

    def hide_modulus_line(self) -> None:
        self._modulus_line.set_visible(False)
        self._update_legend()

    def set_offset_line(
        self, x_offset: float, x_end: float, slope: float, label: str
    ) -> None:
        """0.2 % offset line: y = slope*(x - x_offset), starting where y = 0."""
        self._offset_line.set_xdata([x_offset, x_end])
        self._offset_line.set_ydata([0.0, slope * (x_end - x_offset)])
        self._offset_line.set_label(label)
        self._offset_line.set_visible(True)
        self._update_legend()

    def hide_offset_line(self) -> None:
        self._offset_line.set_visible(False)
        self._update_legend()

    def set_peak_ref_line(self, y: float, label: str) -> None:
        """Horizontal dashed line at the peak load value."""
        self._peak_ref_line.set_ydata([y, y])
        self._peak_ref_line.set_label(label)
        self._peak_ref_line.set_visible(True)
        self._update_legend()

    def hide_peak_ref_line(self) -> None:
        self._peak_ref_line.set_visible(False)
        self._update_legend()

    def set_yield_hline(self, y: float, label: str) -> None:
        """Horizontal dashed line at the yield load value."""
        self._yield_hline.set_ydata([y, y])
        self._yield_hline.set_label(label)
        self._yield_hline.set_visible(True)
        self._update_legend()

    def hide_yield_hline(self) -> None:
        self._yield_hline.set_visible(False)
        self._update_legend()

    def clear_overlays(self) -> None:
        for artist in (
            self._modulus_line, self._offset_line,
            self._peak_ref_line, self._yield_hline,
        ):
            artist.set_visible(False)
        self._update_legend()

    # ------------------------------------------------------------------

    def _update_legend(self) -> None:
        labeled = [
            self._completion_dot, self._modulus_line,
            self._offset_line, self._peak_ref_line, self._yield_hline,
        ]
        if any(a.get_visible() for a in labeled):
            self._ax.legend(fontsize=8)
        else:
            try:
                self._ax.get_legend().remove()
            except Exception:
                pass
        self._canvas.draw_idle()

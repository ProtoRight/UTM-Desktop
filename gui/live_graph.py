"""Embedded matplotlib canvas for live Force vs Displacement graphing.

Zoom controls:
  - Scroll wheel: zoom in/out centred on cursor
  - Zoom In / Zoom Out buttons: zoom from view centre
  - Fit button: autoscale to data extents
  - Pan: click and drag when Pan mode is active (toggle button)
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


_ZOOM_FACTOR = 1.30   # per scroll tick or button click


class LiveGraph(QWidget):
    """Displays a real-time Force (kg) vs Displacement (mm) plot."""

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
        self._pan_start  = None   # (x, y) in data coords

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        layout.addWidget(self._build_toolbar())
        layout.addWidget(self._canvas, 1)

        self._line,  = self._ax.plot([], [], color="#2980b9", linewidth=1.5)
        self._completion_dot, = self._ax.plot(
            [], [], "ro", markersize=8, label="Test end", visible=False
        )

        self._setup_axes()

        # Matplotlib event connections
        self._canvas.mpl_connect("scroll_event",       self._on_scroll)
        self._canvas.mpl_connect("button_press_event", self._on_mouse_press)
        self._canvas.mpl_connect("motion_notify_event",self._on_mouse_move)
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
        self._btn_zoom_in.clicked.connect(lambda: self._zoom_from_centre(1.0 / _ZOOM_FACTOR))
        self._btn_zoom_out.clicked.connect(lambda: self._zoom_from_centre(_ZOOM_FACTOR))
        self._btn_pan.toggled.connect(self._on_pan_toggled)

        return bar

    def _setup_axes(self) -> None:
        self._ax.set_xlabel("Displacement (mm)", fontsize=10)
        self._ax.set_ylabel("Load (kg)", fontsize=10)
        self._ax.set_title("Force vs Displacement", fontsize=11)
        self._ax.grid(True, linestyle="--", alpha=0.4)
        self._ax.set_xlim(0, 1)
        self._ax.set_ylim(0, 1)

    # ------------------------------------------------------------------
    # Zoom / pan helpers
    # ------------------------------------------------------------------

    def _zoom_from_centre(self, factor: float) -> None:
        """Scale both axes by factor around their current centre point."""
        xlim = self._ax.get_xlim()
        ylim = self._ax.get_ylim()
        xc = (xlim[0] + xlim[1]) / 2
        yc = (ylim[0] + ylim[1]) / 2
        xr = (xlim[1] - xlim[0]) / 2 * factor
        yr = (ylim[1] - ylim[0]) / 2 * factor
        self._ax.set_xlim(xc - xr, xc + xr)
        self._ax.set_ylim(yc - yr, yc + yr)
        self._canvas.draw_idle()

    def _zoom_around(self, xdata: float, ydata: float, factor: float) -> None:
        """Scale axes by factor, keeping (xdata, ydata) stationary."""
        xlim = self._ax.get_xlim()
        ylim = self._ax.get_ylim()
        self._ax.set_xlim(
            xdata - (xdata - xlim[0]) * factor,
            xdata + (xlim[1] - xdata) * factor,
        )
        self._ax.set_ylim(
            ydata - (ydata - ylim[0]) * factor,
            ydata + (ylim[1] - ydata) * factor,
        )
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
        cursor = Qt.CursorShape.OpenHandCursor if checked else Qt.CursorShape.ArrowCursor
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

    def _on_mouse_release(self, event) -> None:
        self._pan_start = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_data(self, disp: list[float], load: list[float]) -> None:
        if not disp:
            return
        self._line.set_xdata(disp)
        self._line.set_ydata(load)
        self._ax.relim()
        self._ax.autoscale_view()
        xlim = self._ax.get_xlim()
        ylim = self._ax.get_ylim()
        xpad = max((xlim[1] - xlim[0]) * 0.05, 0.1)
        ypad = max((ylim[1] - ylim[0]) * 0.05, 0.5)
        self._ax.set_xlim(max(0, xlim[0] - xpad), xlim[1] + xpad)
        self._ax.set_ylim(max(0, ylim[0] - ypad), ylim[1] + ypad)
        self._canvas.draw_idle()

    def fit_to_data(self) -> None:
        """Autoscale to the current data extents."""
        self._ax.relim()
        self._ax.autoscale(True)
        self._ax.autoscale_view()
        self._canvas.draw_idle()

    def mark_completion(self, disp: float, load: float) -> None:
        self._completion_dot.set_xdata([disp])
        self._completion_dot.set_ydata([load])
        self._completion_dot.set_visible(True)
        self._ax.legend(fontsize=8)
        self._canvas.draw_idle()

    def clear(self) -> None:
        self._line.set_xdata([])
        self._line.set_ydata([])
        self._completion_dot.set_visible(False)
        try:
            self._ax.get_legend().remove()
        except Exception:
            pass
        self._ax.set_xlim(0, 1)
        self._ax.set_ylim(0, 1)
        self._canvas.draw_idle()

    def set_title(self, title: str) -> None:
        self._ax.set_title(title, fontsize=11)
        self._canvas.draw_idle()

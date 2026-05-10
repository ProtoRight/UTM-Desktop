"""Embedded matplotlib canvas for live Force vs Displacement graphing."""

from __future__ import annotations

import matplotlib
matplotlib.use("QtAgg")

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy


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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)

        self._line,  = self._ax.plot([], [], color="#2980b9", linewidth=1.5)
        self._marker = self._ax.axvline(x=0, color="red", linewidth=1.2,
                                         linestyle="--", visible=False)
        self._completion_dot, = self._ax.plot([], [], "ro", markersize=8,
                                               label="Test end", visible=False)

        self._setup_axes()
        self._canvas.draw()

    # ------------------------------------------------------------------
    def _setup_axes(self) -> None:
        self._ax.set_xlabel("Displacement (mm)", fontsize=10)
        self._ax.set_ylabel("Load (kg)", fontsize=10)
        self._ax.set_title("Force vs Displacement", fontsize=11)
        self._ax.grid(True, linestyle="--", alpha=0.4)
        self._ax.set_xlim(0, 1)
        self._ax.set_ylim(0, 1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_data(self, disp: list[float], load: list[float]) -> None:
        """Refresh the graph with the current data arrays. Call from a QTimer."""
        if not disp:
            return
        self._line.set_xdata(disp)
        self._line.set_ydata(load)
        self._ax.relim()
        self._ax.autoscale_view(scalex=True, scaley=True)
        # Add 10 % padding on both axes so the line doesn't hug the edges
        xlim = self._ax.get_xlim()
        ylim = self._ax.get_ylim()
        xpad = max((xlim[1] - xlim[0]) * 0.05, 0.1)
        ypad = max((ylim[1] - ylim[0]) * 0.05, 0.5)
        self._ax.set_xlim(max(0, xlim[0] - xpad), xlim[1] + xpad)
        self._ax.set_ylim(max(0, ylim[0] - ypad), ylim[1] + ypad)
        self._canvas.draw_idle()

    def mark_completion(self, disp: float, load: float) -> None:
        """Place a red dot at the test-end point."""
        self._completion_dot.set_xdata([disp])
        self._completion_dot.set_ydata([load])
        self._completion_dot.set_visible(True)
        self._ax.legend(fontsize=8)
        self._canvas.draw_idle()

    def clear(self) -> None:
        """Reset to blank state for a new test."""
        self._line.set_xdata([])
        self._line.set_ydata([])
        self._completion_dot.set_visible(False)
        self._marker.set_visible(False)
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

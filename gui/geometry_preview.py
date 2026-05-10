"""Cross-section geometry preview widget — draws a labeled diagram via QPainter."""

from __future__ import annotations

import math
from PyQt6.QtCore import Qt, QPoint, QRect
from PyQt6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush, QPolygon, QFontMetrics,
)
from PyQt6.QtWidgets import QWidget, QSizePolicy


_FILL   = QColor(160, 195, 230)   # steel-blue fill
_INNER  = QColor(245, 245, 245)   # hollow-tube inner fill
_OUTLINE = QColor(40, 40, 40)
_DIM    = QColor(190, 40, 40)     # dimension-line colour
_LABEL_FONT_SIZE = 9


class GeometryPreview(QWidget):
    """Draws a cross-section sketch for rectangular, circular, or hollow geometry."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._geometry = "rectangular"
        self.setMinimumSize(160, 130)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(160)

    def set_geometry(self, geometry: str) -> None:
        self._geometry = geometry
        self.update()

    # ------------------------------------------------------------------
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(250, 250, 250))

        if self._geometry == "rectangular":
            self._draw_rect(p)
        elif self._geometry == "circular":
            self._draw_circle(p)
        elif self._geometry == "hollow":
            self._draw_hollow(p)

        p.end()

    # ------------------------------------------------------------------
    # Shape drawers
    # ------------------------------------------------------------------

    def _draw_rect(self, p: QPainter) -> None:
        w, h = self.width(), self.height()
        margin = 30
        # Shape occupies roughly 55 % width, 50 % height, centred
        rw = int(w * 0.55)
        rh = int(h * 0.42)
        rx = (w - rw) // 2
        ry = int(h * 0.12)

        p.setPen(QPen(_OUTLINE, 1.5))
        p.setBrush(QBrush(_FILL))
        p.drawRect(rx, ry, rw, rh)

        # --- dimension: b (width) below shape ---
        dim_y = ry + rh + 18
        self._horiz_dim(p, rx, rx + rw, dim_y, "b  (width)")

        # --- dimension: d (thickness) right of shape ---
        dim_x = rx + rw + 18
        self._vert_dim(p, dim_x, ry, ry + rh, "d  (thickness)")

    def _draw_circle(self, p: QPainter) -> None:
        w, h = self.width(), self.height()
        r = int(min(w, h) * 0.30)
        cx, cy = w // 2, int(h * 0.42)

        p.setPen(QPen(_OUTLINE, 1.5))
        p.setBrush(QBrush(_FILL))
        p.drawEllipse(QPoint(cx, cy), r, r)

        # diameter line through centre
        p.setPen(QPen(_DIM, 1.2, Qt.PenStyle.DashLine))
        p.drawLine(cx - r, cy, cx + r, cy)

        # dimension: d (diameter)
        dim_y = cy + r + 18
        self._horiz_dim(p, cx - r, cx + r, dim_y, "d  (diameter)")

    def _draw_hollow(self, p: QPainter) -> None:
        w, h = self.width(), self.height()
        R = int(min(w, h) * 0.32)   # outer radius
        r = int(R * 0.52)           # inner radius
        cx, cy = w // 2, int(h * 0.40)

        # Outer circle
        p.setPen(QPen(_OUTLINE, 1.5))
        p.setBrush(QBrush(_FILL))
        p.drawEllipse(QPoint(cx, cy), R, R)

        # Inner circle (cut-out)
        p.setBrush(QBrush(_INNER))
        p.drawEllipse(QPoint(cx, cy), r, r)

        # dimension: D (outer diameter)
        dim_y_outer = cy + R + 20
        self._horiz_dim(p, cx - R, cx + R, dim_y_outer, "D  (outer dia.)")

        # dimension: d (inner diameter) — shown closer in
        dim_y_inner = cy + r + 8
        self._horiz_dim(p, cx - r, cx + r, dim_y_inner, "d  (inner dia.)")

    # ------------------------------------------------------------------
    # Dimension line helpers
    # ------------------------------------------------------------------

    def _horiz_dim(
        self,
        p: QPainter,
        x1: int,
        x2: int,
        y: int,
        label: str,
    ) -> None:
        p.save()
        pen = QPen(_DIM, 1.2)
        p.setPen(pen)
        p.setBrush(QBrush(_DIM))

        tick = 5
        p.drawLine(x1, y - tick, x1, y + tick)
        p.drawLine(x2, y - tick, x2, y + tick)
        p.drawLine(x1, y, x2, y)

        # arrowheads
        self._arrowhead_h(p, x1, y, right=True)
        self._arrowhead_h(p, x2, y, right=False)

        # label centred above line
        font = QFont()
        font.setPointSize(_LABEL_FONT_SIZE)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QPen(_DIM))
        fm = QFontMetrics(font)
        lw = fm.horizontalAdvance(label)
        p.drawText(int((x1 + x2) / 2 - lw / 2), y - 7, label)

        p.restore()

    def _vert_dim(
        self,
        p: QPainter,
        x: int,
        y1: int,
        y2: int,
        label: str,
    ) -> None:
        p.save()
        pen = QPen(_DIM, 1.2)
        p.setPen(pen)
        p.setBrush(QBrush(_DIM))

        tick = 5
        p.drawLine(x - tick, y1, x + tick, y1)
        p.drawLine(x - tick, y2, x + tick, y2)
        p.drawLine(x, y1, x, y2)

        self._arrowhead_v(p, x, y1, down=True)
        self._arrowhead_v(p, x, y2, down=False)

        # label to the right, vertically centred
        font = QFont()
        font.setPointSize(_LABEL_FONT_SIZE)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QPen(_DIM))
        fm = QFontMetrics(font)
        mid_y = int((y1 + y2) / 2 + fm.height() / 4)
        p.drawText(x + 8, mid_y, label)

        p.restore()

    @staticmethod
    def _arrowhead_h(p: QPainter, x: int, y: int, right: bool) -> None:
        """Small filled triangle arrowhead pointing outward on horizontal dim line."""
        size = 5
        dx = size if right else -size
        pts = QPolygon([
            QPoint(x, y),
            QPoint(x + dx, y - 3),
            QPoint(x + dx, y + 3),
        ])
        p.drawPolygon(pts)

    @staticmethod
    def _arrowhead_v(p: QPainter, x: int, y: int, down: bool) -> None:
        size = 5
        dy = size if down else -size
        pts = QPolygon([
            QPoint(x, y),
            QPoint(x - 3, y + dy),
            QPoint(x + 3, y + dy),
        ])
        p.drawPolygon(pts)

"""3-D oblique specimen preview with test-context annotations.

Draws an oblique-projection sketch of the test bar/rod for each cross-section
type.  For 3-point bend the loading direction, support triangles, and force
arrow are shown so the distinction between *thickness d* (load direction) and
*width b* is immediately obvious.  For tensile, horizontal force arrows show
the pull direction.
"""

from __future__ import annotations

import math
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush, QPolygonF, QFontMetrics,
)
from PyQt6.QtWidgets import QWidget, QSizePolicy

# ── Palette ──────────────────────────────────────────────────────────────────
_FRONT   = QColor(155, 195, 232)   # front face
_TOP     = QColor(115, 162, 210)   # top face
_SIDE    = QColor( 82, 135, 188)   # right side face
_INNER   = QColor(238, 238, 238)   # hollow-tube bore
_OUTLINE = QColor( 30,  30,  30)
_DIM     = QColor(170,  20,  20)   # dimension lines / labels
_FORCE   = QColor( 30,  30,  30)   # force arrows
_SUPPORT = QColor( 65,  65,  65)   # support triangles

# ── Oblique-projection parameters ────────────────────────────────────────────
_ANG = math.radians(30)   # depth axis rises at 30° above horizontal
_FS  = 0.48               # depth foreshortening factor


def _qf(*pts) -> QPolygonF:
    return QPolygonF(list(pts))


def _bf(size: int = 9) -> QFont:
    f = QFont(); f.setPointSize(size); f.setBold(True); return f


def _f(size: int = 8) -> QFont:
    f = QFont(); f.setPointSize(size); return f


class GeometryPreview(QWidget):
    """Oblique 3-D specimen sketch with loading context."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._geometry  = "rectangular"
        self._test_type = "3PT"
        self.setMinimumSize(160, 195)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(195)

    def set_geometry(self, geometry: str) -> None:
        self._geometry = geometry
        self.update()

    def set_test_type(self, test_type: str) -> None:
        self._test_type = test_type
        self.update()

    # ── Paint dispatch ────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(250, 250, 250))
        if self._geometry == "rectangular":
            self._draw_rect(p)
        elif self._geometry == "circular":
            self._draw_circ(p)
        elif self._geometry == "hollow":
            self._draw_hollow(p)
        p.end()

    # ── Oblique projection ────────────────────────────────────────────────────

    def _v(self, xl: float, yh: float, zd: float) -> QPointF:
        """Oblique projection → screen point.
        xl  = along bar length (+right on screen)
        yh  = height (+up → −screen y)
        zd  = depth into screen (+oblique upper-right)
        """
        return QPointF(
            self._ox + xl + zd * _FS * math.cos(_ANG),
            self._oy - yh - zd * _FS * math.sin(_ANG),
        )

    # ── Rectangular 3-D bar ───────────────────────────────────────────────────

    def _draw_rect(self, p: QPainter) -> None:
        W, H = self.width(), self.height()

        bl = W * 0.55          # bar length (screen width)
        bd = max(H * 0.16, 14) # d: bar height = thickness (load direction)
        bb = W * 0.17          # b: bar depth = width (oblique)

        # Front-bottom-left origin — room for: supports below, F-arrow above,
        # d-dimension label right, caption at bottom.
        self._ox = W * 0.06
        self._oy = H * 0.63

        v = self._v
        FBL = v(0,  0,  0);   FBR = v(bl, 0,  0)
        FTL = v(0,  bd, 0);   FTR = v(bl, bd, 0)
        BBL = v(0,  0,  bb);  BBR = v(bl, 0,  bb)  # noqa: F841
        BTL = v(0,  bd, bb);  BTR = v(bl, bd, bb)

        # Faces — back-to-front so front always paints on top
        p.setPen(QPen(_OUTLINE, 1.1))
        p.setBrush(QBrush(_SIDE))
        p.drawPolygon(_qf(FBR, BBR, BTR, FTR))   # right face

        p.setBrush(QBrush(_TOP))
        p.drawPolygon(_qf(FTL, FTR, BTR, BTL))   # top face

        p.setPen(QPen(_OUTLINE, 1.5))
        p.setBrush(QBrush(_FRONT))
        p.drawPolygon(_qf(FBL, FBR, FTR, FTL))   # front face

        # ── Test-context annotations ──────────────────────────────────────
        if self._test_type == "3PT":
            self._support_tri(p, FBL.x() + bl * 0.12, self._oy)
            self._support_tri(p, FBL.x() + bl * 0.88, self._oy)
            arw_x = FTL.x() + bl * 0.5
            self._arrow_down(p, arw_x, FTL.y() - 22, FTL.y() - 3)
            p.setPen(QPen(_FORCE)); p.setFont(_bf(9))
            p.drawText(int(arw_x + 4), int(FTL.y()) - 16, "F")
        else:
            cy = (FBL.y() + FTL.y()) / 2
            self._arrow_horiz(p, FBL.x() - 23, FBL.x() - 3, cy, right=False)
            self._arrow_horiz(p, FBR.x() +  3, FBR.x() + 23, cy, right=True)
            p.setPen(QPen(_FORCE)); p.setFont(_bf(9))
            p.drawText(int(FBL.x()) - 34, int(cy) + 4, "F")
            p.drawText(int(FBR.x()) + 26, int(cy) + 4, "F")

        # ── Dimension: d (thickness) — vertical arrow right of front face ──
        rx  = FBR.x() + 9
        p.setPen(QPen(_DIM, 1.1))
        # horizontal tick extensions
        p.drawLine(int(FBR.x()), int(FBR.y()), int(rx + 3), int(FBR.y()))
        p.drawLine(int(FBR.x()), int(FTR.y()), int(rx + 3), int(FTR.y()))
        # vertical line
        p.drawLine(int(rx), int(FTR.y()), int(rx), int(FBR.y()))
        # arrowheads
        p.setBrush(QBrush(_DIM)); p.setPen(Qt.PenStyle.NoPen)
        self._ah_v(p, rx, FTR.y(), up=True)
        self._ah_v(p, rx, FBR.y(), up=False)
        # label
        p.setPen(QPen(_DIM)); p.setFont(_bf(9))
        p.drawText(int(rx + 5), int((FBR.y() + FTR.y()) / 2) + 4, "d")

        # ── Dimension: b (width) — label along oblique top-left edge ──────
        # Draw a short dimension line along FTL→BTL with arrowheads
        p.setPen(QPen(_DIM, 1.1))
        p.drawLine(int(FTL.x()), int(FTL.y()), int(BTL.x()), int(BTL.y()))
        # Perpendicular ticks at each end (perp to oblique direction)
        px_tick = _FS * math.sin(_ANG) * 4    # perp x component
        py_tick = _FS * math.cos(_ANG) * 4    # perp y component
        for pt in (FTL, BTL):
            p.drawLine(int(pt.x() - px_tick), int(pt.y() - py_tick),
                       int(pt.x() + px_tick), int(pt.y() + py_tick))
        # Arrowheads along oblique
        p.setBrush(QBrush(_DIM)); p.setPen(Qt.PenStyle.NoPen)
        self._ah_oblique(p, FTL, BTL)
        # Label centred above midpoint
        bm = QPointF((FTL.x() + BTL.x()) / 2, (FTL.y() + BTL.y()) / 2)
        p.setPen(QPen(_DIM)); p.setFont(_bf(9))
        p.drawText(int(bm.x()) + 2, int(bm.y()) - 5, "b")

        # ── Bottom caption ────────────────────────────────────────────────
        p.setFont(_f(7)); p.setPen(QPen(QColor(120, 120, 120)))
        cap = ("d = load direction  |  b = width"
               if self._test_type == "3PT" else
               "d = thickness  |  b = width")
        fm = QFontMetrics(p.font())
        p.drawText((W - fm.horizontalAdvance(cap)) // 2, H - 4, cap)

    # ── Circular 3-D cylinder hint ────────────────────────────────────────────

    def _draw_circ(self, p: QPainter) -> None:
        W, H = self.width(), self.height()
        r  = int(min(W, H) * 0.26)
        cx = W // 2
        cy = int(H * 0.45)

        # Back-circle (dashed) offset by oblique depth
        ddx = int(W * 0.11 * math.cos(_ANG))
        ddy = int(W * 0.11 * math.sin(_ANG))

        p.setPen(QPen(_OUTLINE, 1.0, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(int(cx + ddx - r), int(cy - ddy - r), r * 2, r * 2)

        # Body tangent lines
        p.setPen(QPen(_OUTLINE, 1.1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(cx, cy - r, cx + ddx, cy - ddy - r)
        p.drawLine(cx, cy + r, cx + ddx, cy - ddy + r)

        # Front circle (filled)
        p.setPen(QPen(_OUTLINE, 1.5))
        p.setBrush(QBrush(_FRONT))
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        self._test_annotations_round(p, cx, cy, r)

        # Diameter dimension
        dim_y = cy + r + 20
        self._horiz_dim(p, cx - r, cx + r, dim_y, "d  (diameter)")

    # ── Hollow tube 3-D hint ──────────────────────────────────────────────────

    def _draw_hollow(self, p: QPainter) -> None:
        W, H = self.width(), self.height()
        R  = int(min(W, H) * 0.27)
        ri = int(R * 0.52)
        cx = W // 2
        cy = int(H * 0.42)

        ddx = int(W * 0.10 * math.cos(_ANG))
        ddy = int(W * 0.10 * math.sin(_ANG))

        p.setPen(QPen(_OUTLINE, 1.0, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(int(cx + ddx - R), int(cy - ddy - R), R * 2, R * 2)

        p.setPen(QPen(_OUTLINE, 1.1)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(cx, cy - R, cx + ddx, cy - ddy - R)
        p.drawLine(cx, cy + R, cx + ddx, cy - ddy + R)

        p.setPen(QPen(_OUTLINE, 1.5))
        p.setBrush(QBrush(_FRONT))
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)
        p.setBrush(QBrush(_INNER))
        p.drawEllipse(cx - ri, cy - ri, ri * 2, ri * 2)

        self._test_annotations_round(p, cx, cy, R)

        self._horiz_dim(p, cx - R,  cx + R,  cy + R + 22, "D  (outer dia.)")
        self._horiz_dim(p, cx - ri, cx + ri, cy + ri + 8, "d  (inner dia.)")

    # ── Shared annotation helpers ─────────────────────────────────────────────

    def _test_annotations_round(self, p, cx, cy, r) -> None:
        if self._test_type == "3PT":
            self._support_tri(p, cx - r * 0.65, cy + r)
            self._support_tri(p, cx + r * 0.65, cy + r)
            self._arrow_down(p, float(cx), float(cy - r) - 18, float(cy - r) - 2)
            p.setPen(QPen(_FORCE)); p.setFont(_bf(9))
            p.drawText(cx + 4, cy - r - 12, "F")
        else:
            self._arrow_horiz(p, float(cx - r) - 22, float(cx - r) - 2, float(cy), right=False)
            self._arrow_horiz(p, float(cx + r) + 2,  float(cx + r) + 22, float(cy), right=True)
            p.setPen(QPen(_FORCE)); p.setFont(_bf(9))
            p.drawText(cx - r - 32, cy + 4, "F")
            p.drawText(cx + r + 24, cy + 4, "F")

    def _support_tri(self, p: QPainter, cx: float, top_y: float) -> None:
        h = 13; w = 10
        pts = _qf(QPointF(cx, top_y),
                  QPointF(cx - w, top_y + h),
                  QPointF(cx + w, top_y + h))
        p.setPen(QPen(_SUPPORT, 1.2))
        p.setBrush(QBrush(_SUPPORT))
        p.drawPolygon(pts)
        p.drawLine(int(cx - w - 4), int(top_y + h),
                   int(cx + w + 4), int(top_y + h))

    def _arrow_down(self, p: QPainter, ax: float, y_top: float, y_tip: float) -> None:
        p.setPen(QPen(_FORCE, 2))
        p.drawLine(int(ax), int(y_top), int(ax), int(y_tip))
        head = 6
        pts = _qf(QPointF(ax, y_tip),
                  QPointF(ax - head, y_tip - head),
                  QPointF(ax + head, y_tip - head))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(_FORCE))
        p.drawPolygon(pts)

    def _arrow_horiz(self, p: QPainter, x_from: float, x_to: float,
                     y: float, right: bool) -> None:
        p.setPen(QPen(_FORCE, 2))
        p.drawLine(int(x_from), int(y), int(x_to), int(y))
        head = 6
        if right:
            pts = _qf(QPointF(x_to,           y),
                      QPointF(x_to - head, y - head),
                      QPointF(x_to - head, y + head))
        else:
            pts = _qf(QPointF(x_from,           y),
                      QPointF(x_from + head, y - head),
                      QPointF(x_from + head, y + head))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(_FORCE))
        p.drawPolygon(pts)

    # ── Dimension-line helpers ─────────────────────────────────────────────────

    def _horiz_dim(self, p: QPainter, x1: int, x2: int, y: int, label: str) -> None:
        p.save()
        p.setPen(QPen(_DIM, 1.2)); p.setBrush(QBrush(_DIM))
        tick = 5
        p.drawLine(x1, y - tick, x1, y + tick)
        p.drawLine(x2, y - tick, x2, y + tick)
        p.drawLine(x1, y, x2, y)
        self._ah_h(p, x1, y, right=True)
        self._ah_h(p, x2, y, right=False)
        p.setFont(_bf(9)); p.setPen(QPen(_DIM))
        fm = QFontMetrics(p.font())
        lw = fm.horizontalAdvance(label)
        p.drawText(int((x1 + x2) / 2 - lw / 2), y - 7, label)
        p.restore()

    @staticmethod
    def _ah_h(p: QPainter, x: int, y: int, right: bool) -> None:
        s = 5; dx = s if right else -s
        p.drawPolygon(_qf(QPointF(x, y), QPointF(x + dx, y - 3), QPointF(x + dx, y + 3)))

    @staticmethod
    def _ah_v(p: QPainter, x: float, y: float, up: bool) -> None:
        s = 5; dy = -s if up else s
        p.drawPolygon(_qf(QPointF(x, y), QPointF(x - 3, y + dy), QPointF(x + 3, y + dy)))

    @staticmethod
    def _ah_oblique(p: QPainter, pt_a: QPointF, pt_b: QPointF) -> None:
        """Arrowheads pointing outward at both ends of the oblique b-dimension line."""
        dx = pt_b.x() - pt_a.x(); dy = pt_b.y() - pt_a.y()
        lng = math.sqrt(dx * dx + dy * dy)
        if lng < 1:
            return
        ux, uy = dx / lng, dy / lng   # unit along oblique
        px, py = -uy, ux              # perpendicular (rotated 90°)
        s = 4
        # arrowhead at pt_a pointing AWAY from pt_b (−u direction)
        p.drawPolygon(_qf(QPointF(pt_a.x(), pt_a.y()),
                          QPointF(pt_a.x() - s * ux + s * 0.5 * px,
                                  pt_a.y() - s * uy + s * 0.5 * py),
                          QPointF(pt_a.x() - s * ux - s * 0.5 * px,
                                  pt_a.y() - s * uy - s * 0.5 * py)))
        # arrowhead at pt_b pointing AWAY from pt_a (+u direction)
        p.drawPolygon(_qf(QPointF(pt_b.x(), pt_b.y()),
                          QPointF(pt_b.x() + s * ux + s * 0.5 * px,
                                  pt_b.y() + s * uy + s * 0.5 * py),
                          QPointF(pt_b.x() + s * ux - s * 0.5 * px,
                                  pt_b.y() + s * uy - s * 0.5 * py)))

"""3-D oblique specimen preview with test-context annotations.

Drawing strategy
----------------
3PT bend     – oblique 3-D box/cylinder, supports and downward F arrow.
Tensile      – dog-bone top view (rectangular) or side-view pill (circular /
               hollow) with opposing pull arrows along the specimen axis.
               Includes L₀ gauge-length label for tensile.
"""

from __future__ import annotations

import math
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import (
    QColor, QFont, QPainter, QPainterPath, QPen, QBrush,
    QPolygonF, QFontMetrics,
)
from PyQt6.QtWidgets import QWidget, QSizePolicy

# ── Palette ──────────────────────────────────────────────────────────────────
_FRONT   = QColor(155, 195, 232)
_TOP     = QColor(115, 162, 210)
_SIDE    = QColor( 82, 135, 188)
_INNER   = QColor(238, 238, 238)
_OUTLINE = QColor( 30,  30,  30)
_DIM     = QColor(165,  15,  15)
_FORCE   = QColor( 30,  30,  30)
_SUPPORT = QColor( 65,  65,  65)

_ANG = math.radians(30)
_FS  = 0.48


def _qf(*pts) -> QPolygonF:
    return QPolygonF(list(pts))


def _bf(size: int = 11) -> QFont:
    f = QFont(); f.setPointSize(size); f.setBold(True); return f


def _f(size: int = 8) -> QFont:
    f = QFont(); f.setPointSize(size); return f


class GeometryPreview(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._geometry  = "rectangular"
        self._test_type = "3PT"
        self.setMinimumSize(160, 210)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(210)

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
        g, t = self._geometry, self._test_type
        if g == "rectangular":
            self._draw_rect_3pt(p) if t == "3PT" else self._draw_rect_tensile(p)
        elif g == "circular":
            self._draw_circ_3pt(p) if t == "3PT" else self._draw_circ_tensile(p)
        elif g == "hollow":
            self._draw_hollow_3pt(p) if t == "3PT" else self._draw_hollow_tensile(p)
        p.end()

    # ── Oblique projection ────────────────────────────────────────────────────

    def _v(self, xl: float, yh: float, zd: float) -> QPointF:
        return QPointF(
            self._ox + xl + zd * _FS * math.cos(_ANG),
            self._oy - yh - zd * _FS * math.sin(_ANG),
        )

    # =========================================================================
    # Rectangular – 3PT  (oblique 3-D box)
    # =========================================================================

    def _draw_rect_3pt(self, p: QPainter) -> None:
        W, H = self.width(), self.height()
        bl = W * 0.55
        bd = max(H * 0.16, 14)
        bb = W * 0.17

        self._ox = W * 0.06
        self._oy = H * 0.60

        v = self._v
        FBL = v(0,  0,  0);  FBR = v(bl, 0,  0)
        FTL = v(0,  bd, 0);  FTR = v(bl, bd, 0)
        BBL = v(0,  0,  bb); BBR = v(bl, 0,  bb)   # noqa: F841
        BTL = v(0,  bd, bb); BTR = v(bl, bd, bb)

        p.setPen(QPen(_OUTLINE, 1.1))
        p.setBrush(QBrush(_SIDE));  p.drawPolygon(_qf(FBR, BBR, BTR, FTR))
        p.setBrush(QBrush(_TOP));   p.drawPolygon(_qf(FTL, FTR, BTR, BTL))
        p.setPen(QPen(_OUTLINE, 1.5))
        p.setBrush(QBrush(_FRONT)); p.drawPolygon(_qf(FBL, FBR, FTR, FTL))

        # Supports & force arrow
        self._support_tri(p, FBL.x() + bl * 0.12, self._oy)
        self._support_tri(p, FBL.x() + bl * 0.88, self._oy)
        arw_x = FTL.x() + bl * 0.5
        self._arrow_down(p, arw_x, FTL.y() - 24, FTL.y() - 3)
        p.setPen(QPen(_FORCE)); p.setFont(_bf(10))
        p.drawText(int(arw_x + 5), int(FTL.y()) - 17, "F")

        # d label – vertical dimension line, pulled away from body
        rx = FBR.x() + 14
        p.setPen(QPen(_DIM, 1.2))
        p.drawLine(int(FBR.x()), int(FBR.y()), int(rx + 4), int(FBR.y()))
        p.drawLine(int(FBR.x()), int(FTR.y()), int(rx + 4), int(FTR.y()))
        p.drawLine(int(rx), int(FTR.y()), int(rx), int(FBR.y()))
        p.setBrush(QBrush(_DIM)); p.setPen(Qt.PenStyle.NoPen)
        self._ah_v(p, rx, FTR.y(), up=True)
        self._ah_v(p, rx, FBR.y(), up=False)
        p.setPen(QPen(_DIM)); p.setFont(_bf(11))
        p.drawText(int(rx + 7), int((FBR.y() + FTR.y()) / 2) + 4, "d")

        # b label – along oblique top-left edge
        p.setPen(QPen(_DIM, 1.2))
        p.drawLine(int(FTL.x()), int(FTL.y()), int(BTL.x()), int(BTL.y()))
        px_t = _FS * math.sin(_ANG) * 5
        py_t = _FS * math.cos(_ANG) * 5
        for pt in (FTL, BTL):
            p.drawLine(int(pt.x()-px_t), int(pt.y()-py_t), int(pt.x()+px_t), int(pt.y()+py_t))
        p.setBrush(QBrush(_DIM)); p.setPen(Qt.PenStyle.NoPen)
        self._ah_oblique(p, FTL, BTL)
        bm = QPointF((FTL.x() + BTL.x()) / 2, (FTL.y() + BTL.y()) / 2)
        p.setPen(QPen(_DIM)); p.setFont(_bf(11))
        p.drawText(int(bm.x()) + 3, int(bm.y()) - 7, "b")

        # Caption
        p.setFont(_f(7)); p.setPen(QPen(QColor(110, 110, 110)))
        cap = "d = load direction  |  b = width"
        fm = QFontMetrics(p.font())
        p.drawText((W - fm.horizontalAdvance(cap)) // 2, H - 4, cap)

    # =========================================================================
    # Rectangular – Tensile  (dog-bone top view)
    # =========================================================================

    def _draw_rect_tensile(self, p: QPainter) -> None:
        W, H = self.width(), self.height()

        # Dog-bone proportions
        L   = W * 0.60       # total specimen length
        ox  = (W - L) / 2   # left x of specimen
        cy  = H * 0.40       # centreline y

        E   = H * 0.18       # half-width of grip area
        G   = H * 0.085      # half-width of gauge section

        tr  = L * 0.22       # length of grip straight section
        tc  = L * 0.36       # end of transition / start of gauge
        blend = (tc - tr) * 0.5

        gauge_s = ox + tc
        gauge_e = ox + L - tc

        # ── Dog-bone outline ──────────────────────────────────────────────
        path = QPainterPath()
        # Top edge, left→right
        path.moveTo(ox,        cy - E)
        path.lineTo(ox + tr,   cy - E)
        path.cubicTo(ox + tr + blend, cy - E,
                     gauge_s  - blend, cy - G,
                     gauge_s,          cy - G)
        path.lineTo(gauge_e,           cy - G)
        path.cubicTo(gauge_e + blend,  cy - G,
                     ox + L - tr - blend, cy - E,
                     ox + L - tr,      cy - E)
        path.lineTo(ox + L,   cy - E)
        # Right end → bottom edge
        path.lineTo(ox + L,   cy + E)
        path.lineTo(ox + L - tr, cy + E)
        path.cubicTo(ox + L - tr - blend, cy + E,
                     gauge_e + blend,    cy + G,
                     gauge_e,            cy + G)
        path.lineTo(gauge_s,           cy + G)
        path.cubicTo(gauge_s - blend,  cy + G,
                     ox + tr + blend,  cy + E,
                     ox + tr,          cy + E)
        path.lineTo(ox,        cy + E)
        path.closeSubpath()

        p.setPen(QPen(_OUTLINE, 1.5))
        p.setBrush(QBrush(_FRONT))
        p.drawPath(path)

        # Thickness depth hint — oblique lines at upper-right grip corner
        ddx, ddy = int(W * 0.045), int(W * 0.022)
        p.setPen(QPen(_SIDE, 1.1))
        for tx in (int(ox + L) - 3, int(ox + L) - 11):
            p.drawLine(tx, int(cy - E), tx + ddx, int(cy - E) - ddy)
        p.drawLine(int(ox + L), int(cy - E), int(ox + L) + ddx, int(cy - E) - ddy)
        p.drawLine(int(ox + L), int(cy + E), int(ox + L) + ddx, int(cy + E) - ddy)
        p.drawLine(int(ox + L) + ddx, int(cy - E) - ddy,
                   int(ox + L) + ddx, int(cy + E) - ddy)

        # Force arrows (along specimen axis, outside grips)
        arw = 24
        self._arrow_horiz(p, ox - 6,     ox - arw, cy, right=False)
        self._arrow_horiz(p, ox + L + 6, ox + L + arw, cy, right=True)
        p.setPen(QPen(_FORCE)); p.setFont(_bf(10))
        p.drawText(int(ox - arw - 16), int(cy) + 4, "F")
        p.drawText(int(ox + L + arw + 4), int(cy) + 4, "F")

        # ── L₀ gauge-length dimension ─────────────────────────────────────
        lo_y = cy + G + 22
        p.setPen(QPen(_DIM, 1.2))
        p.drawLine(int(gauge_s), int(cy + G + 2), int(gauge_s), int(lo_y + 2))
        p.drawLine(int(gauge_e), int(cy + G + 2), int(gauge_e), int(lo_y + 2))
        p.drawLine(int(gauge_s), int(lo_y), int(gauge_e), int(lo_y))
        p.setBrush(QBrush(_DIM)); p.setPen(Qt.PenStyle.NoPen)
        self._ah_h(p, int(gauge_s), int(lo_y), right=True)
        self._ah_h(p, int(gauge_e), int(lo_y), right=False)
        p.setPen(QPen(_DIM)); p.setFont(_bf(11))
        lo_lbl = "L₀  (gauge)"
        fm = QFontMetrics(p.font())
        p.drawText(int((gauge_s + gauge_e) / 2 - fm.horizontalAdvance(lo_lbl) / 2),
                   int(lo_y) + 15, lo_lbl)

        # ── b  gauge-width dimension ──────────────────────────────────────
        bx = gauge_e + 20
        p.setPen(QPen(_DIM, 1.2))
        p.drawLine(int(gauge_e), int(cy - G), int(bx + 4), int(cy - G))
        p.drawLine(int(gauge_e), int(cy + G), int(bx + 4), int(cy + G))
        p.drawLine(int(bx), int(cy - G), int(bx), int(cy + G))
        p.setBrush(QBrush(_DIM)); p.setPen(Qt.PenStyle.NoPen)
        self._ah_v(p, bx, cy - G, up=True)
        self._ah_v(p, bx, cy + G, up=False)
        p.setPen(QPen(_DIM)); p.setFont(_bf(11))
        p.drawText(int(bx) + 7, int(cy) + 4, "b")

        # ── d  thickness – oblique arrow at upper-right grip corner ──────
        d_ox = int(ox + L) + ddx + 4
        d_oy = int(cy - E) - ddy
        p.setPen(QPen(_DIM)); p.setFont(_bf(11))
        p.drawText(d_ox + 2, d_oy - 3, "d")

    # =========================================================================
    # Circular – 3PT
    # =========================================================================

    def _draw_circ_3pt(self, p: QPainter) -> None:
        W, H = self.width(), self.height()
        r  = int(min(W, H) * 0.25)
        cx = W // 2
        cy = int(H * 0.44)

        ddx = int(W * 0.11 * math.cos(_ANG))
        ddy = int(W * 0.11 * math.sin(_ANG))

        p.setPen(QPen(_OUTLINE, 1.0, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(int(cx + ddx - r), int(cy - ddy - r), r * 2, r * 2)

        p.setPen(QPen(_OUTLINE, 1.2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(cx, cy - r, cx + ddx, cy - ddy - r)
        p.drawLine(cx, cy + r, cx + ddx, cy - ddy + r)

        p.setPen(QPen(_OUTLINE, 1.5))
        p.setBrush(QBrush(_FRONT))
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        self._support_tri(p, cx - r * 0.65, cy + r)
        self._support_tri(p, cx + r * 0.65, cy + r)
        self._arrow_down(p, float(cx), float(cy - r) - 20, float(cy - r) - 2)
        p.setPen(QPen(_FORCE)); p.setFont(_bf(10))
        p.drawText(cx + 5, cy - r - 14, "F")

        self._horiz_dim(p, cx - r, cx + r, cy + r + 22, "d  (diameter)")

    # =========================================================================
    # Circular – Tensile  (side view: pill with force arrows along axis)
    # =========================================================================

    def _draw_circ_tensile(self, p: QPainter) -> None:
        W, H = self.width(), self.height()

        # Pill (side view of horizontal cylinder)
        d   = H * 0.30        # cylinder diameter
        L   = W * 0.55        # cylinder length
        ox  = (W - L) / 2
        cy  = H * 0.42
        rad = d / 2           # corner radius for pill shape

        p.setPen(QPen(_OUTLINE, 1.5))
        p.setBrush(QBrush(_FRONT))
        p.drawRoundedRect(QRectF(ox, cy - rad, L, d), rad, rad)

        # Force arrows along the horizontal axis (left and right ends)
        arw = 24
        self._arrow_horiz(p, ox - 5,     ox - arw, cy, right=False)
        self._arrow_horiz(p, ox + L + 5, ox + L + arw, cy, right=True)
        p.setPen(QPen(_FORCE)); p.setFont(_bf(10))
        p.drawText(int(ox - arw - 16), int(cy) + 4, "F")
        p.drawText(int(ox + L + arw + 4), int(cy) + 4, "F")

        # d (diameter) dimension below the pill
        dim_y = int(cy + rad + 22)
        self._horiz_dim(p, int(ox), int(ox + d), dim_y, "d")
        # vertical arrow on left end for diameter
        self._vert_dim(p, int(ox) - 16, int(cy - rad), int(cy + rad), "d")

        # Caption
        p.setFont(_f(7)); p.setPen(QPen(QColor(110, 110, 110)))
        cap = "pull direction →"
        fm = QFontMetrics(p.font())
        p.drawText((W - fm.horizontalAdvance(cap)) // 2, H - 4, cap)

    # =========================================================================
    # Hollow – 3PT
    # =========================================================================

    def _draw_hollow_3pt(self, p: QPainter) -> None:
        W, H = self.width(), self.height()
        R  = int(min(W, H) * 0.26)
        ri = int(R * 0.52)
        cx = W // 2
        cy = int(H * 0.42)

        ddx = int(W * 0.10 * math.cos(_ANG))
        ddy = int(W * 0.10 * math.sin(_ANG))

        p.setPen(QPen(_OUTLINE, 1.0, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(int(cx + ddx - R), int(cy - ddy - R), R * 2, R * 2)

        p.setPen(QPen(_OUTLINE, 1.2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(cx, cy - R, cx + ddx, cy - ddy - R)
        p.drawLine(cx, cy + R, cx + ddx, cy - ddy + R)

        p.setPen(QPen(_OUTLINE, 1.5))
        p.setBrush(QBrush(_FRONT))
        p.drawEllipse(cx - R, cy - R, R * 2, R * 2)
        p.setBrush(QBrush(_INNER))
        p.drawEllipse(cx - ri, cy - ri, ri * 2, ri * 2)

        self._support_tri(p, cx - R * 0.65, cy + R)
        self._support_tri(p, cx + R * 0.65, cy + R)
        self._arrow_down(p, float(cx), float(cy - R) - 18, float(cy - R) - 2)
        p.setPen(QPen(_FORCE)); p.setFont(_bf(10))
        p.drawText(cx + 5, cy - R - 12, "F")

        self._horiz_dim(p, cx - R,  cx + R,  cy + R + 24, "D  (outer)")
        self._horiz_dim(p, cx - ri, cx + ri, cy + ri + 9, "d  (inner)")

    # =========================================================================
    # Hollow – Tensile  (side view: outer pill + inner dashed channel)
    # =========================================================================

    def _draw_hollow_tensile(self, p: QPainter) -> None:
        W, H = self.width(), self.height()

        D_out = H * 0.32      # outer diameter
        D_in  = D_out * 0.52  # inner diameter
        L     = W * 0.54
        ox    = (W - L) / 2
        cy    = H * 0.40
        R_out = D_out / 2
        R_in  = D_in  / 2

        # Outer pill
        p.setPen(QPen(_OUTLINE, 1.5))
        p.setBrush(QBrush(_FRONT))
        p.drawRoundedRect(QRectF(ox, cy - R_out, L, D_out), R_out, R_out)

        # Inner channel (dashed rectangle showing the bore)
        inner_l = ox + R_out
        inner_r = ox + L - R_out
        p.setPen(QPen(_OUTLINE, 1.0, Qt.PenStyle.DashLine))
        p.setBrush(QBrush(_INNER))
        p.drawRoundedRect(QRectF(inner_l, cy - R_in, inner_r - inner_l, D_in),
                          R_in, R_in)

        # Force arrows along axis
        arw = 24
        self._arrow_horiz(p, ox - 5,     ox - arw, cy, right=False)
        self._arrow_horiz(p, ox + L + 5, ox + L + arw, cy, right=True)
        p.setPen(QPen(_FORCE)); p.setFont(_bf(10))
        p.drawText(int(ox - arw - 16), int(cy) + 4, "F")
        p.drawText(int(ox + L + arw + 4), int(cy) + 4, "F")

        # D and d dimension lines on the left end
        self._vert_dim(p, int(ox) - 16, int(cy - R_out), int(cy + R_out), "D")
        self._vert_dim(p, int(ox) - 30, int(cy - R_in),  int(cy + R_in),  "d")

        # Caption
        p.setFont(_f(7)); p.setPen(QPen(QColor(110, 110, 110)))
        cap = "D = outer  |  d = inner  |  pull direction →"
        fm = QFontMetrics(p.font())
        p.drawText(max(0, (W - fm.horizontalAdvance(cap)) // 2), H - 4, cap)

    # =========================================================================
    # Shared annotation helpers
    # =========================================================================

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
        s = 7
        pts = _qf(QPointF(ax, y_tip),
                  QPointF(ax - s, y_tip - s),
                  QPointF(ax + s, y_tip - s))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(_FORCE))
        p.drawPolygon(pts)

    def _arrow_horiz(self, p: QPainter, x_from: float, x_to: float,
                     y: float, right: bool) -> None:
        p.setPen(QPen(_FORCE, 2))
        p.drawLine(int(x_from), int(y), int(x_to), int(y))
        s = 7
        if right:
            pts = _qf(QPointF(x_to,       y),
                      QPointF(x_to - s, y - s),
                      QPointF(x_to - s, y + s))
        else:
            pts = _qf(QPointF(x_from,       y),
                      QPointF(x_from + s, y - s),
                      QPointF(x_from + s, y + s))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(_FORCE))
        p.drawPolygon(pts)

    # =========================================================================
    # Dimension-line helpers
    # =========================================================================

    def _horiz_dim(self, p: QPainter, x1: int, x2: int, y: int, label: str) -> None:
        p.save()
        p.setPen(QPen(_DIM, 1.2)); p.setBrush(QBrush(_DIM))
        tick = 5
        p.drawLine(x1, y - tick, x1, y + tick)
        p.drawLine(x2, y - tick, x2, y + tick)
        p.drawLine(x1, y, x2, y)
        self._ah_h(p, x1, y, right=True)
        self._ah_h(p, x2, y, right=False)
        p.setFont(_bf(11)); p.setPen(QPen(_DIM))
        fm = QFontMetrics(p.font())
        lw = fm.horizontalAdvance(label)
        p.drawText(int((x1 + x2) / 2 - lw / 2), y - 8, label)
        p.restore()

    def _vert_dim(self, p: QPainter, x: int, y1: float, y2: float, label: str) -> None:
        p.save()
        p.setPen(QPen(_DIM, 1.2)); p.setBrush(QBrush(_DIM))
        tick = 5
        p.drawLine(x - tick, int(y1), x + tick, int(y1))
        p.drawLine(x - tick, int(y2), x + tick, int(y2))
        p.drawLine(x, int(y1), x, int(y2))
        self._ah_v(p, float(x), y1, up=False)
        self._ah_v(p, float(x), y2, up=True)
        p.setFont(_bf(11)); p.setPen(QPen(_DIM))
        fm = QFontMetrics(p.font())
        mid_y = int((y1 + y2) / 2 + fm.height() / 4)
        p.drawText(x + 7, mid_y, label)
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
        dx = pt_b.x() - pt_a.x(); dy = pt_b.y() - pt_a.y()
        lng = math.sqrt(dx * dx + dy * dy)
        if lng < 1:
            return
        ux, uy = dx / lng, dy / lng
        px, py = -uy, ux
        s = 5
        for pt, sign in ((pt_a, -1), (pt_b, 1)):
            p.drawPolygon(_qf(
                QPointF(pt.x(), pt.y()),
                QPointF(pt.x() + sign * s * ux + s * 0.5 * px,
                        pt.y() + sign * s * uy + s * 0.5 * py),
                QPointF(pt.x() + sign * s * ux - s * 0.5 * px,
                        pt.y() + sign * s * uy - s * 0.5 * py),
            ))

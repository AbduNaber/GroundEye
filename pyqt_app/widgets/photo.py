"""Stylized photo placeholder (matches the HTML mock)."""
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QLinearGradient, QPolygonF, QPainterPath
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QWidget


class Photo(QWidget):
    def __init__(self, event=None, big=False, parent=None):
        super().__init__(parent)
        self.event = event
        self.big = big
        self.setMinimumSize(80, 54)

    def set_event(self, event):
        self.event = event
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        night = bool(self.event and self.event.night)
        tag = (self.event.tag if self.event else "") or ""

        # Background gradient
        g = QLinearGradient(0, 0, r.width(), r.height())
        if night:
            g.setColorAt(0, QColor("#0d1410"))
            g.setColorAt(1, QColor("#131b15"))
        else:
            g.setColorAt(0, QColor("#1a2128"))
            g.setColorAt(1, QColor("#232a31"))
        p.fillRect(r, QBrush(g))

        # Scanline stripes
        p.setPen(QPen(QColor(255, 255, 255, 6), 1))
        for y in range(0, r.height(), 4):
            p.drawLine(0, y, r.width(), y)

        if night:
            # Green glow blob
            grad = QLinearGradient(r.width() * 0.4, r.height() * 0.6, r.width() * 0.6, r.height() * 0.3)
            grad.setColorAt(0, QColor(168, 217, 108, 40))
            grad.setColorAt(1, QColor(168, 217, 108, 0))
            p.fillRect(r, QBrush(grad))

        # Dashed inner frame
        pen = QPen(QColor(255, 255, 255, 20), 1, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(r.adjusted(4, 4, -4, -4)))

        # Subject silhouette
        if tag.startswith("subject"):
            self._draw_subject(p, r, night)
        elif tag == "wildlife":
            self._draw_wildlife(p, r, night)

        # HUD corner text
        if self.event:
            small = QFont("JetBrains Mono", 7)
            p.setFont(small)
            p.setPen(QColor(255, 255, 255, 120))
            p.drawText(8, 14, f"CAM-01 {'IR' if night else 'RGB'}")
            p.drawText(r.width() - 130, 14, f"{self.event.date} {self.event.ts[:8]}")
            p.drawText(8, r.height() - 6, f"{self.event.node_id} · {self.event.distance:.1f}m")
            p.drawText(r.width() - 110, r.height() - 6,
                       f"f/2.0 1/60 ISO{1600 if night else 200}")
            if self.big:
                p.setPen(QColor(216, 106, 91))
                p.drawText(r.width() - 40, 14, "● REC")

        p.end()

    def _draw_subject(self, p: QPainter, r, night):
        # Rough humanoid silhouette centered
        w = r.width() * 0.18
        h = r.height() * 0.55
        x = r.width() * 0.45
        y = r.height() * 0.32
        color = QColor(168, 217, 108, 110) if night else QColor(0, 0, 0, 100)
        p.setBrush(QBrush(color))
        p.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath()
        pts = [
            (0.4, 0.0), (0.6, 0.0), (0.65, 0.22), (0.72, 0.35),
            (0.70, 0.55), (0.75, 1.0), (0.55, 1.0), (0.5, 0.55),
            (0.45, 1.0), (0.25, 1.0), (0.32, 0.55), (0.28, 0.35),
            (0.35, 0.22),
        ]
        first = True
        for (px, py) in pts:
            pt = QPointF(x + px * w, y + py * h)
            if first:
                path.moveTo(pt)
                first = False
            else:
                path.lineTo(pt)
        path.closeSubpath()
        p.drawPath(path)

    def _draw_wildlife(self, p: QPainter, r, night):
        color = QColor(168, 217, 108, 90) if night else QColor(0, 0, 0, 80)
        p.setBrush(QBrush(color))
        p.setPen(Qt.PenStyle.NoPen)
        w = r.width() * 0.12
        h = r.height() * 0.22
        x = r.width() * 0.62
        y = r.height() * 0.6
        p.drawEllipse(QRectF(x, y, w, h))
        p.drawEllipse(QRectF(x + w * 0.6, y - h * 0.3, w * 0.4, h * 0.5))

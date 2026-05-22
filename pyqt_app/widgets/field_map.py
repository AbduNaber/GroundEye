"""QGraphicsView schematic field map."""
import math
from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QPolygonF
)
from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsEllipseItem, QGraphicsLineItem,
    QGraphicsPathItem, QGraphicsTextItem, QGraphicsRectItem, QGraphicsItem,
    QGraphicsItemGroup
)
from pyqt_app.services.store import store
from pyqt_app.services.bus import bus


MAP_W = 1000
MAP_H = 600


class NodePinItem(QGraphicsItemGroup):
    """Node pin group: detection radius + inner dot + label."""

    def __init__(self, node, parent_view):
        super().__init__()
        self.node = node
        self.parent_view = parent_view
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self._build()
        self._pulse_t = 0.0

    def _build(self):
        for it in list(self.childItems()):
            self.removeFromGroup(it)
            if it.scene():
                it.scene().removeItem(it)

        cx = self.node.x * MAP_W
        cy = self.node.y * MAP_H
        color = self._color()

        # Detection radius
        r = self.node.detection_radius * 8
        self.radius = QGraphicsEllipseItem(cx - r, cy - r, r * 2, r * 2)
        pen = QPen(QColor(color), 1, Qt.PenStyle.DashLine)
        pen.setDashPattern([4, 4])
        self.radius.setPen(pen)
        fc = QColor(color)
        fc.setAlpha(14)
        self.radius.setBrush(QBrush(fc))
        self.addToGroup(self.radius)

        # Pulse ring (if triggered) — drawn separately by timer
        self.pulse = QGraphicsEllipseItem(cx - 14, cy - 14, 28, 28)
        self.pulse.setPen(QPen(QColor(color), 1.5))
        self.pulse.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        if self.node.status != "triggered":
            self.pulse.setVisible(False)
        self.addToGroup(self.pulse)

        # Outer pin
        self.outer = QGraphicsEllipseItem(cx - 10, cy - 10, 20, 20)
        self.outer.setPen(QPen(QColor(color), 1.5))
        self.outer.setBrush(QBrush(QColor("#0a0d10")))
        self.addToGroup(self.outer)

        # Inner dot
        self.inner = QGraphicsEllipseItem(cx - 4, cy - 4, 8, 8)
        self.inner.setPen(QPen(Qt.PenStyle.NoPen))
        self.inner.setBrush(QBrush(QColor(color)))
        self.addToGroup(self.inner)

        # Label card
        self.label_bg = QGraphicsRectItem(cx + 14, cy - 14, 64, 32)
        self.label_bg.setPen(QPen(QColor("#2e3842"), 1))
        self.label_bg.setBrush(QBrush(QColor("#0f1317")))
        self.addToGroup(self.label_bg)

        self.label_id = QGraphicsTextItem(self.node.id)
        self.label_id.setDefaultTextColor(QColor("#d8e0e6"))
        self.label_id.setFont(QFont("JetBrains Mono", 8))
        self.label_id.setPos(cx + 18, cy - 16)
        self.addToGroup(self.label_id)

        self.label_status = QGraphicsTextItem(self.node.status.upper())
        self.label_status.setDefaultTextColor(QColor(color))
        self.label_status.setFont(QFont("JetBrains Mono", 7))
        self.label_status.setPos(cx + 18, cy - 2)
        self.addToGroup(self.label_status)

    def _color(self):
        s = self.node.status
        return (
            "#d86a5b" if s == "triggered"
            else "#5c6771" if s == "offline"
            else "#5a9fb8" if s == "connecting"
            else "#d4a84b"
        )

    def refresh(self):
        self._build()

    def advance_pulse(self):
        if self.node.status != "triggered":
            return
        self._pulse_t = (self._pulse_t + 0.04) % 1.0
        t = self._pulse_t
        r = 14 + t * 32
        alpha = int(max(0, 200 * (1 - t)))
        cx = self.node.x * MAP_W
        cy = self.node.y * MAP_H
        self.pulse.setRect(cx - r, cy - r, r * 2, r * 2)
        col = QColor("#d86a5b")
        col.setAlpha(alpha)
        self.pulse.setPen(QPen(col, 1.5))

    def mousePressEvent(self, ev):
        bus.node_selected.emit(self.node.id)
        super().mousePressEvent(ev)


class FieldMap(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setStyleSheet("background: #0a0d10; border: none;")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

        self.scene_ = QGraphicsScene(self)
        self.scene_.setSceneRect(0, 0, MAP_W, MAP_H)
        self.setScene(self.scene_)

        self.show_grid = True
        self.show_radii = True
        self.show_paths = True
        self.pins = {}
        self._rebuild()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(40)

        bus.node_updated.connect(self._on_node_updated)

    def set_option(self, key, value):
        setattr(self, f"show_{key}", value)
        self._rebuild()

    def _rebuild(self):
        self.scene_.clear()
        self.pins = {}

        # Grid
        if self.show_grid:
            pen_minor = QPen(QColor(255, 255, 255, 18), 0.5)
            for x in range(0, MAP_W + 1, 40):
                self.scene_.addLine(x, 0, x, MAP_H, pen_minor)
            for y in range(0, MAP_H + 1, 40):
                self.scene_.addLine(0, y, MAP_W, y, pen_minor)
            pen_major = QPen(QColor(255, 255, 255, 34), 0.5)
            for x in range(0, MAP_W + 1, 200):
                self.scene_.addLine(x, 0, x, MAP_H, pen_major)
            for y in range(0, MAP_H + 1, 200):
                self.scene_.addLine(0, y, MAP_W, y, pen_major)

        # Crosshairs
        pen_xh = QPen(QColor(255, 255, 255, 40), 0.5, Qt.PenStyle.DashLine)
        pen_xh.setDashPattern([2, 4])
        self.scene_.addLine(MAP_W / 2, 0, MAP_W / 2, MAP_H, pen_xh)
        self.scene_.addLine(0, MAP_H / 2, MAP_W, MAP_H / 2, pen_xh)

        # Terrain contours
        pen_con = QPen(QColor(255, 255, 255, 16), 1)
        for (cx, cy, rx, ry) in [(300, 250, 180, 90), (300, 250, 240, 130),
                                  (680, 380, 200, 110), (680, 380, 280, 160)]:
            item = self.scene_.addEllipse(cx - rx, cy - ry, rx * 2, ry * 2, pen_con)
            item.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        # Site boundary
        pen_b = QPen(QColor(255, 255, 255, 56), 1, Qt.PenStyle.DashLine)
        pen_b.setDashPattern([6, 6])
        self.scene_.addRect(60, 60, 880, 480, pen_b, QBrush(Qt.BrushStyle.NoBrush))
        t = self.scene_.addText("SITE-A PERIMETER · 120×72m",
                                 QFont("JetBrains Mono", 7))
        t.setDefaultTextColor(QColor(255, 255, 255, 90))
        t.setPos(66, 62)

        # Hub
        hub_x = 500
        hub_y = MAP_H * 0.92

        # Connection lines node → hub
        for n in store.nodes:
            x = n.x * MAP_W
            y = n.y * MAP_H
            col = (
                "#d86a5b" if n.status == "triggered"
                else "#5c6771" if n.status == "offline"
                else "#5a9fb8" if n.status == "connecting"
                else "#d4a84b"
            )
            c = QColor(col)
            c.setAlpha(90 if n.status == "offline" else 110)
            pen = QPen(c, 1)
            if n.status == "offline":
                pen.setStyle(Qt.PenStyle.DashLine)
                pen.setDashPattern([2, 5])
            elif n.status == "connecting":
                pen.setStyle(Qt.PenStyle.DashLine)
                pen.setDashPattern([4, 3])
            self.scene_.addLine(x, y, hub_x, hub_y, pen)

            # MQTT mid-label
            mx = (x + hub_x) / 2
            my = (y + hub_y) / 2
            r = self.scene_.addRect(mx - 20, my - 7, 40, 14,
                                    QPen(QColor("#242c34"), 0.5),
                                    QBrush(QColor("#0f1317")))
            tt = self.scene_.addText("MQTT", QFont("JetBrains Mono", 7))
            tt.setDefaultTextColor(QColor(255, 255, 255, 120))
            br = tt.boundingRect()
            tt.setPos(mx - br.width() / 2, my - br.height() / 2)

        # Detection radii (drawn as part of pin)

        # Path trails
        if self.show_paths:
            for p in store.paths:
                pts = []
                for (nid, _ts) in p["hits"]:
                    node = store.node(nid)
                    if node:
                        pts.append(QPointF(node.x * MAP_W, node.y * MAP_H))
                if len(pts) < 2:
                    continue
                path = QPainterPath(pts[0])
                for q in pts[1:]:
                    path.lineTo(q)
                pen = QPen(QColor("#d4a84b"), 1.5, Qt.PenStyle.DashLine)
                pen.setDashPattern([6, 3])
                item = QGraphicsPathItem(path)
                item.setPen(pen)
                self.scene_.addItem(item)
                for q in pts:
                    dot = self.scene_.addEllipse(q.x() - 3, q.y() - 3, 6, 6,
                                                  QPen(Qt.PenStyle.NoPen),
                                                  QBrush(QColor("#d4a84b")))
                # Arrowhead at last point
                if len(pts) >= 2:
                    a = pts[-2]
                    b = pts[-1]
                    ang = math.atan2(b.y() - a.y(), b.x() - a.x())
                    arrow = QPolygonF([
                        b,
                        QPointF(b.x() - 8 * math.cos(ang - 0.4),
                                b.y() - 8 * math.sin(ang - 0.4)),
                        QPointF(b.x() - 8 * math.cos(ang + 0.4),
                                b.y() - 8 * math.sin(ang + 0.4)),
                    ])
                    self.scene_.addPolygon(arrow, QPen(Qt.PenStyle.NoPen),
                                           QBrush(QColor("#d4a84b")))
                # Label
                lab = self.scene_.addText(p["label"], QFont("JetBrains Mono", 8))
                lab.setDefaultTextColor(QColor("#d4a84b"))
                lab.setPos(pts[0].x() - 40, pts[0].y() - 24)

        # Nodes
        for n in store.nodes:
            pin = NodePinItem(n, self)
            self.scene_.addItem(pin)
            self.pins[n.id] = pin

        # Hub device
        self.scene_.addRect(hub_x - 22, hub_y - 14, 44, 28,
                            QPen(QColor("#8b96a1"), 1.2),
                            QBrush(QColor("#0f1317")))
        self.scene_.addRect(hub_x - 18, hub_y - 10, 36, 20,
                            QPen(QColor("#8b96a1"), 0.5, Qt.PenStyle.DotLine),
                            QBrush(Qt.BrushStyle.NoBrush))
        t = self.scene_.addText("RPi5", QFont("JetBrains Mono", 7))
        t.setDefaultTextColor(QColor("#d8e0e6"))
        br = t.boundingRect()
        t.setPos(hub_x - br.width() / 2, hub_y - br.height() / 2)
        t2 = self.scene_.addText("CENTRAL UNIT · HUB", QFont("JetBrains Mono", 8))
        t2.setDefaultTextColor(QColor("#8b96a1"))
        br = t2.boundingRect()
        t2.setPos(hub_x - br.width() / 2, hub_y + 16)
        self.scene_.addEllipse(hub_x + 13, hub_y - 10, 4, 4,
                               QPen(Qt.PenStyle.NoPen),
                               QBrush(QColor("#6fb56a")))

        # Compass
        self.scene_.addEllipse(908, 38, 44, 44,
                               QPen(QColor("#2e3842"), 1),
                               QBrush(QColor("#0f1317")))
        for (label, dx, dy, c) in [("N", 0, -10, "#8b96a1"),
                                    ("S", 0, 14, "#5c6771"),
                                    ("W", -12, 4, "#5c6771"),
                                    ("E", 12, 4, "#5c6771")]:
            t = self.scene_.addText(label, QFont("JetBrains Mono", 7))
            t.setDefaultTextColor(QColor(c))
            br = t.boundingRect()
            t.setPos(930 - br.width() / 2 + dx, 60 - br.height() / 2 + dy)
        needle = QPolygonF([
            QPointF(930, 46),
            QPointF(933, 60),
            QPointF(930, 64),
            QPointF(927, 60),
        ])
        self.scene_.addPolygon(needle, QPen(Qt.PenStyle.NoPen),
                               QBrush(QColor("#d4a84b")))

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.fitInView(self.scene_.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _animate(self):
        for pin in self.pins.values():
            pin.advance_pulse()

    def _on_node_updated(self, node):
        pin = self.pins.get(node.id)
        if pin:
            pin.node = node
            pin.refresh()

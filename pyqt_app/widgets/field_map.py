"""QGraphicsView schematic field map.

Coordinate system
-----------------
Physical space : x ∈ [0, 1], y ∈ [0, 1]  (normalised from real metres)
                 y=0 → bottom of area (node-1/node-2 baseline)
                 y=1 → top of area   (node-3)
Screen space   : phys_to_map() adds margin and flips y (screen y grows downward)

Both node pin positions and MQTT location payload x/y live in physical space,
so applying phys_to_map() to both keeps them consistent.
"""
import math
from collections import deque
from PyQt6.QtCore import Qt, QPointF, QTimer
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QPolygonF
)
from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsEllipseItem,
    QGraphicsPathItem, QGraphicsTextItem, QGraphicsRectItem,
    QGraphicsItemGroup
)
from pyqt_app.services.store import store
from pyqt_app.services.bus import bus


MAP_W = 1000
MAP_H = 600
MARGIN = 0.14  # fraction of MAP dimension reserved as padding on each side


def phys_to_map(px: float, py: float) -> tuple[float, float]:
    """Normalised physical coords → scene pixel coords.

    y is flipped so that physical y=0 (ground baseline) appears at the bottom
    of the scene and y=1 (apex node) appears at the top.
    """
    mx = (MARGIN + px * (1.0 - 2 * MARGIN)) * MAP_W
    my = (MARGIN + (1.0 - py) * (1.0 - 2 * MARGIN)) * MAP_H
    return mx, my


class NodePinItem(QGraphicsItemGroup):
    """Node pin group: detection radius + inner dot + label."""

    def __init__(self, node, parent_view):
        super().__init__()
        self.node = node
        self.parent_view = parent_view
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self._pulse_t = 0.0
        self._build()

    def _build(self):
        for it in list(self.childItems()):
            self.removeFromGroup(it)
            if it.scene():
                it.scene().removeItem(it)

        cx, cy = phys_to_map(self.node.x, self.node.y)
        color = self._color()

        # Detection radius
        r = self.node.detection_radius * 8
        self.radius = QGraphicsEllipseItem(cx - r, cy - r, r * 2, r * 2)
        pen = QPen(QColor(color), 1, Qt.PenStyle.DashLine)
        pen.setDashPattern([4, 4])
        self.radius.setPen(pen)
        fc = QColor(color); fc.setAlpha(14)
        self.radius.setBrush(QBrush(fc))
        self.addToGroup(self.radius)

        # Pulse ring (animated when triggered)
        self.pulse = QGraphicsEllipseItem(cx - 14, cy - 14, 28, 28)
        self.pulse.setPen(QPen(QColor(color), 1.5))
        self.pulse.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.pulse.setVisible(self.node.status == "triggered")
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
        cx, cy = phys_to_map(self.node.x, self.node.y)
        self.pulse.setRect(cx - r, cy - r, r * 2, r * 2)
        col = QColor("#d86a5b"); col.setAlpha(alpha)
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
        self.pins: dict = {}

        self._location_history: deque = deque(maxlen=20)
        self._location_items: list = []

        self._rebuild()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(40)

        bus.node_updated.connect(self._on_node_updated)
        bus.location_received.connect(self._on_location_received)
        bus.playback_reset.connect(self._on_playback_reset)

    def set_option(self, key, value):
        setattr(self, f"show_{key}", value)
        self._rebuild()

    # ------------------------------------------------------------------
    # Scene construction
    # ------------------------------------------------------------------

    def _rebuild(self):
        self.scene_.clear()
        self.pins = {}
        self._location_items = []

        # ── Background grid ─────────────────────────────────────────────
        if self.show_grid:
            pen_minor = QPen(QColor(255, 255, 255, 14), 0.5)
            for x in range(0, MAP_W + 1, 40):
                self.scene_.addLine(x, 0, x, MAP_H, pen_minor)
            for y in range(0, MAP_H + 1, 40):
                self.scene_.addLine(0, y, MAP_W, y, pen_minor)
            pen_major = QPen(QColor(255, 255, 255, 28), 0.5)
            for x in range(0, MAP_W + 1, 200):
                self.scene_.addLine(x, 0, x, MAP_H, pen_major)
            for y in range(0, MAP_H + 1, 200):
                self.scene_.addLine(0, y, MAP_W, y, pen_major)

        # ── Hub (RPi5 / broker) — below the node triangle ───────────────
        hub_x = MAP_W / 2
        hub_y = MAP_H * 0.93

        # ── TDOA triangulation lines between nodes ───────────────────────
        node_pts = {n.id: phys_to_map(n.x, n.y) for n in store.nodes}
        ids = [n.id for n in store.nodes]
        pen_tri = QPen(QColor(255, 255, 255, 22), 1, Qt.PenStyle.DashLine)
        pen_tri.setDashPattern([5, 5])
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                ax, ay = node_pts[ids[i]]
                bx, by = node_pts[ids[j]]
                self.scene_.addLine(ax, ay, bx, by, pen_tri)
                # Distance label at midpoint
                mx, my = (ax + bx) / 2, (ay + by) / 2
                # compute physical distance in metres
                na = store.node(ids[i])
                nb = store.node(ids[j])
                if na and nb:
                    from pyqt_app.services.store import PHYS_W_M, PHYS_H_M
                    dm = math.hypot(
                        (na.x - nb.x) * PHYS_W_M,
                        (na.y - nb.y) * PHYS_H_M,
                    )
                    t = self.scene_.addText(f"{dm:.1f}m", QFont("JetBrains Mono", 7))
                    t.setDefaultTextColor(QColor(255, 255, 255, 60))
                    br = t.boundingRect()
                    t.setPos(mx - br.width() / 2, my - br.height() / 2)

        # ── Node → hub MQTT connection lines ────────────────────────────
        for n in store.nodes:
            nx, ny = phys_to_map(n.x, n.y)
            col = (
                "#d86a5b" if n.status == "triggered"
                else "#5c6771" if n.status == "offline"
                else "#5a9fb8" if n.status == "connecting"
                else "#d4a84b"
            )
            c = QColor(col); c.setAlpha(90 if n.status == "offline" else 110)
            pen = QPen(c, 1)
            if n.status == "offline":
                pen.setStyle(Qt.PenStyle.DashLine); pen.setDashPattern([2, 5])
            elif n.status == "connecting":
                pen.setStyle(Qt.PenStyle.DashLine); pen.setDashPattern([4, 3])
            self.scene_.addLine(nx, ny, hub_x, hub_y, pen)

            # MQTT mid-label
            mx, my = (nx + hub_x) / 2, (ny + hub_y) / 2
            self.scene_.addRect(mx - 20, my - 7, 40, 14,
                                 QPen(QColor("#242c34"), 0.5),
                                 QBrush(QColor("#0f1317")))
            tt = self.scene_.addText("MQTT", QFont("JetBrains Mono", 7))
            tt.setDefaultTextColor(QColor(255, 255, 255, 120))
            br = tt.boundingRect()
            tt.setPos(mx - br.width() / 2, my - br.height() / 2)

        # ── Node pins ───────────────────────────────────────────────────
        for n in store.nodes:
            pin = NodePinItem(n, self)
            self.scene_.addItem(pin)
            self.pins[n.id] = pin

        # ── Hub device ──────────────────────────────────────────────────
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

        # ── MQTT location overlay (re-drawn after every rebuild) ─────────
        self._update_location_display()

        # ── Compass ─────────────────────────────────────────────────────
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
        needle = QPolygonF([QPointF(930, 46), QPointF(933, 60),
                            QPointF(930, 64), QPointF(927, 60)])
        self.scene_.addPolygon(needle, QPen(Qt.PenStyle.NoPen),
                               QBrush(QColor("#d4a84b")))

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.fitInView(self.scene_.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    # ------------------------------------------------------------------
    # Animation + updates
    # ------------------------------------------------------------------

    def _animate(self):
        for pin in self.pins.values():
            pin.advance_pulse()

    def _on_node_updated(self, node):
        pin = self.pins.get(node.id)
        if pin:
            pin.node = node
            pin.refresh()

    def _on_playback_reset(self) -> None:
        self._location_history.clear()
        self._update_location_display()

    def _on_location_received(self, payload: dict) -> None:
        self._location_history.append(payload)
        self._update_location_display()

    def _update_location_display(self) -> None:
        """Redraw MQTT location overlay without full scene rebuild."""
        for item in self._location_items:
            if item.scene():
                self.scene_.removeItem(item)
        self._location_items.clear()

        if not self._location_history:
            return

        from pyqt_app.services.store import PHYS_W_M, PHYS_H_M

        def _norm(px: float, py: float) -> tuple[float, float]:
            return phys_to_map(
                max(0.0, min(1.0, px / PHYS_W_M)),
                max(0.0, min(1.0, py / PHYS_H_M)),
            )

        # ── Path trail (last 20 best positions) ─────────────────────────
        best_pts = [
            QPointF(*_norm(p["x"], p["y"]))
            for p in self._location_history
        ]
        if len(best_pts) >= 2:
            path = QPainterPath(best_pts[0])
            for pt in best_pts[1:]:
                path.lineTo(pt)
            pen = QPen(QColor(180, 180, 180, 80), 1, Qt.PenStyle.DashLine)
            pen.setDashPattern([3, 4])
            item = QGraphicsPathItem(path)
            item.setPen(pen)
            self.scene_.addItem(item)
            self._location_items.append(item)
            for pt in best_pts[:-1]:
                d = self.scene_.addEllipse(
                    pt.x() - 2, pt.y() - 2, 4, 4,
                    QPen(Qt.PenStyle.NoPen),
                    QBrush(QColor(180, 180, 180, 60)),
                )
                self._location_items.append(d)

        latest = self._location_history[-1]
        best_method = latest.get("best_method", "amplitude")

        # ── Amplitude dot (blue) ─────────────────────────────────────────
        amp = latest.get("amplitude", {})
        if amp:
            ax, ay = _norm(amp.get("x", 0), amp.get("y", 0))
            r = 9 if best_method == "amplitude" else 5
            pen = QPen(QColor("#4a9eff"), 1.5)
            col = QColor("#4a9eff"); col.setAlpha(100)
            item = self.scene_.addEllipse(ax - r, ay - r, r * 2, r * 2, pen, QBrush(col))
            self._location_items.append(item)
            if best_method == "amplitude":
                t = self.scene_.addText("AMP", QFont("JetBrains Mono", 7))
                t.setDefaultTextColor(QColor("#4a9eff"))
                t.setPos(ax + r + 2, ay - 8)
                self._location_items.append(t)

        # ── TDOA dot (red) ───────────────────────────────────────────────
        if latest.get("tdoa_used") and "tdoa" in latest:
            tdoa = latest["tdoa"]
            tx, ty = _norm(tdoa.get("x", 0), tdoa.get("y", 0))
            r = 9 if best_method == "tdoa" else 5
            pen = QPen(QColor("#d86a5b"), 1.5)
            col = QColor("#d86a5b"); col.setAlpha(100)
            item = self.scene_.addEllipse(tx - r, ty - r, r * 2, r * 2, pen, QBrush(col))
            self._location_items.append(item)
            if best_method == "tdoa":
                t = self.scene_.addText("TDOA", QFont("JetBrains Mono", 7))
                t.setDefaultTextColor(QColor("#d86a5b"))
                t.setPos(tx + r + 2, ty - 8)
                self._location_items.append(t)

        # ── Best position ring ───────────────────────────────────────────
        bx, by = _norm(latest["x"], latest["y"])
        ring_col = "#d86a5b" if best_method == "tdoa" else "#4a9eff"
        r = 14
        pen = QPen(QColor(ring_col), 2)
        col = QColor(ring_col); col.setAlpha(30)
        item = self.scene_.addEllipse(bx - r, by - r, r * 2, r * 2, pen, QBrush(col))
        self._location_items.append(item)

        conf = latest.get("confidence", 0)
        dist = latest.get("est_dist_m", 0)
        t = self.scene_.addText(
            f"{best_method.upper()}  {conf:.0%}  {dist:.1f}m",
            QFont("JetBrains Mono", 7),
        )
        t.setDefaultTextColor(QColor(ring_col))
        t.setPos(bx + r + 4, by - 8)
        self._location_items.append(t)

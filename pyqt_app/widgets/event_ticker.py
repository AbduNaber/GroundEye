"""Event ticker (live feed)."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QWidget
)
from pyqt_app.services.bus import bus


class TickerRow(QFrame):
    def __init__(self, event, node, parent=None):
        super().__init__(parent)
        self.event = event
        self.setProperty("role", "tickerItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(48)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        sev = QFrame()
        sev.setFixedSize(3, 28)
        color = (
            "#d86a5b" if event.severity == "high"
            else "#5a9fb8" if event.severity == "info"
            else "#d4a84b"
        )
        if event.ack:
            qc = QColor(color); qc.setAlpha(110)
            sev.setStyleSheet(f"background: rgba({qc.red()},{qc.green()},{qc.blue()},{qc.alpha()}); border-radius: 1px;")
        else:
            sev.setStyleSheet(f"background: {color}; border-radius: 1px;")
        lay.addWidget(sev)

        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel(f"{event.node_id} · {node.label if node else ''}")
        title.setProperty("role", "tickerTitle")
        if event.ack:
            title.setStyleSheet("color: #8b96a1;")
        col.addWidget(title)
        meta = QLabel(
            f"amp {event.amplitude:.2f} · {event.duration:.2f}s · {event.distance:.1f}m"
            f"{' · ACK' if event.ack else ''}"
        )
        meta.setProperty("role", "tickerMeta")
        col.addWidget(meta)
        lay.addLayout(col, 1)

        t = QLabel(event.ts[:8])
        t.setProperty("role", "tickerTime")
        lay.addWidget(t)

    def mousePressEvent(self, ev):
        bus.event_opened.emit(self.event)
        super().mousePressEvent(ev)


class EventTicker(QScrollArea):
    def __init__(self, events, store, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._inner = QWidget()
        self._lay = QVBoxLayout(self._inner)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)
        self._lay.addStretch(1)
        self.setWidget(self._inner)
        self.store = store
        self.populate(events)

    def populate(self, events):
        # Clear
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for ev in events[:8]:
            node = self.store.node(ev.node_id)
            row = TickerRow(ev, node)
            self._lay.insertWidget(self._lay.count() - 1, row)

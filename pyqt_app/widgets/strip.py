"""Bottom recent-captures strip."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QScrollArea, QWidget
)
from pyqt_app.widgets.photo import Photo
from pyqt_app.services.bus import bus


class StripItem(QFrame):
    def __init__(self, event, parent=None):
        super().__init__(parent)
        self.event = event
        self.setProperty("role", "stripItem")
        self.setFixedWidth(180)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        photo = Photo(event)
        photo.setFixedHeight(80)
        lay.addWidget(photo)

        meta = QVBoxLayout()
        meta.setContentsMargins(8, 6, 8, 6)
        meta.setSpacing(2)
        top = QLabel(f"{event.id} · {event.node_id}")
        top.setStyleSheet("font-family: 'JetBrains Mono'; font-size: 10px; color: #d8e0e6;")
        meta.addWidget(top)
        ts = QLabel(event.ts[:8])
        ts.setStyleSheet("font-family: 'JetBrains Mono'; font-size: 9px; color: #8b96a1;")
        meta.addWidget(ts)
        tags = QLabel(f"  {event.severity}     amp {event.amplitude:.2f}  ")
        tags.setStyleSheet(
            "font-family: 'JetBrains Mono'; font-size: 9px; color: #8b96a1;"
            " background: #1c232a; border: 1px solid #2e3842; border-radius: 2px; padding: 1px 4px;"
        )
        meta.addWidget(tags)
        wrap = QWidget()
        wrap.setLayout(meta)
        lay.addWidget(wrap)

    def mousePressEvent(self, ev):
        bus.event_opened.emit(self.event)
        super().mousePressEvent(ev)


class Strip(QScrollArea):
    def __init__(self, events, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        lay = QHBoxLayout(inner)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        for ev in events[:10]:
            lay.addWidget(StripItem(ev))
        lay.addStretch(1)
        inner.setStyleSheet("background: #242c34;")
        self.setWidget(inner)

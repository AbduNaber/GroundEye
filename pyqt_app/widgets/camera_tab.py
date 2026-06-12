"""Camera tab — live MJPEG feeds from ESP32-CAM nodes."""
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QImage, QColor, QPainter, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QPushButton, QScrollArea, QSizePolicy,
    QStackedLayout,
)

from pyqt_app.services.bus import bus


# ─── Single feed cell ─────────────────────────────────────────────────────────

class FeedCell(QFrame):
    """Displays one camera feed with an overlay header."""

    def __init__(self, node_id: str, parent=None):
        super().__init__(parent)
        self.node_id = node_id
        self.setObjectName("panel")
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
        header = QFrame(); header.setObjectName("panelHead")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(10, 0, 10, 0)
        self._title = QLabel(node_id.upper()); self._title.setProperty("role", "panelTitle")
        self._status = QLabel("CONNECTING"); self._status.setProperty("role", "monoMute")
        hl.addWidget(self._title)
        hl.addStretch(1)
        hl.addWidget(self._status)
        root.addWidget(header)

        # Image area — stacked so we can overlay a "no signal" placeholder
        img_container = QWidget()
        img_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._stack = QStackedLayout(img_container)
        self._stack.setStackingMode(QStackedLayout.StackingMode.StackAll)

        self._img_label = QLabel()
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._img_label.setStyleSheet("background:#0d1117;")

        self._placeholder = _NoSignalPlaceholder(node_id)

        self._stack.addWidget(self._img_label)
        self._stack.addWidget(self._placeholder)
        self._stack.setCurrentWidget(self._placeholder)

        root.addWidget(img_container, 1)

    # ------------------------------------------------------------------

    def set_frame(self, jpeg: bytes):
        img = QImage.fromData(jpeg, "JPEG")
        if img.isNull():
            return
        pix = QPixmap.fromImage(img).scaled(
            self._img_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._img_label.setPixmap(pix)
        self._stack.setCurrentWidget(self._img_label)
        self._status.setText("LIVE")
        self._status.setStyleSheet("color: #4caf50; font-size: 10px;")

    def set_offline(self):
        self._stack.setCurrentWidget(self._placeholder)
        self._status.setText("OFFLINE")
        self._status.setStyleSheet("color: #888; font-size: 10px;")

    def set_connecting(self):
        self._stack.setCurrentWidget(self._placeholder)
        self._status.setText("CONNECTING")
        self._status.setStyleSheet("color: #f0a500; font-size: 10px;")


class _NoSignalPlaceholder(QLabel):
    def __init__(self, node_id: str, parent=None):
        super().__init__(parent)
        self.node_id = node_id
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background:#0d1117; color:#3a4a5a;")
        self.setText(f"NO SIGNAL\n{node_id.upper()}")
        font = QFont("JetBrains Mono", 11)
        font.setBold(True)
        self.setFont(font)


# ─── Full-screen overlay ──────────────────────────────────────────────────────

class FullscreenView(QWidget):
    """Overlaid full-screen image view shown when a cell is double-clicked."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hide()
        self.setStyleSheet("background: #000;")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        # Close bar
        bar = QFrame(); bar.setObjectName("panelHead")
        bl = QHBoxLayout(bar); bl.setContentsMargins(10, 0, 10, 0)
        self._label = QLabel(); self._label.setProperty("role", "panelTitle")
        close_btn = QPushButton("CLOSE"); close_btn.setProperty("role", "tool")
        close_btn.clicked.connect(self.hide)
        bl.addWidget(self._label); bl.addStretch(1); bl.addWidget(close_btn)
        lay.addWidget(bar)

        self._img = QLabel()
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay.addWidget(self._img, 1)

        self._current_id: str = ""

    def show_feed(self, node_id: str):
        self._current_id = node_id
        self._label.setText(f"CAMERA · {node_id.upper()} · FULLSCREEN")
        self.show()
        self.raise_()

    def update_frame(self, node_id: str, jpeg: bytes):
        if not self.isVisible() or node_id != self._current_id:
            return
        img = QImage.fromData(jpeg, "JPEG")
        if img.isNull():
            return
        pix = QPixmap.fromImage(img).scaled(
            self._img.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._img.setPixmap(pix)


# ─── Camera tab ───────────────────────────────────────────────────────────────

class CameraTab(QWidget):
    """Tab that shows all discovered ESP32-CAM feeds in a responsive grid."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cells: dict[str, FeedCell] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame(); header.setObjectName("panelHead")
        hl = QHBoxLayout(header); hl.setContentsMargins(12, 0, 12, 0)
        title = QLabel("LIVE CAMERAS"); title.setProperty("role", "panelTitle")
        self._count_label = QLabel("0 feeds"); self._count_label.setProperty("role", "monoMute")
        hl.addWidget(title); hl.addStretch(1); hl.addWidget(self._count_label)
        root.addWidget(header)

        # Scrollable grid
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        self._grid = QGridLayout(inner)
        self._grid.setContentsMargins(8, 8, 8, 8)
        self._grid.setSpacing(6)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        # Empty-state label (shown when no cameras)
        self._empty = QLabel("Waiting for cameras…\nESP32-CAM nodes announce via MQTT groundeye/camera")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setProperty("role", "monoMute")
        self._empty.setWordWrap(True)
        root.addWidget(self._empty)
        self._empty.show()
        scroll.hide()
        self._scroll = scroll

        # Fullscreen overlay (parented to tab; resize handled)
        self._fs = FullscreenView(self)

        # Bus connections
        bus.camera_discovered.connect(self._on_discovered)
        bus.camera_frame.connect(self._on_frame)

    # ------------------------------------------------------------------

    def resizeEvent(self, e):
        self._fs.setGeometry(0, 0, self.width(), self.height())
        super().resizeEvent(e)

    def _on_discovered(self, payload: dict):
        node_id = payload.get("node_id", "")
        online  = payload.get("online", False)

        if online:
            if node_id not in self._cells:
                cell = FeedCell(node_id)
                cell.mouseDoubleClickEvent = lambda _e, nid=node_id: self._fs.show_feed(nid)
                self._cells[node_id] = cell
                self._relayout()
            else:
                self._cells[node_id].set_connecting()
        else:
            cell = self._cells.get(node_id)
            if cell:
                cell.set_offline()

        self._count_label.setText(f"{len(self._cells)} feed{'s' if len(self._cells) != 1 else ''}")
        if self._cells:
            self._empty.hide()
            self._scroll.show()
        else:
            self._empty.show()
            self._scroll.hide()

    def _on_frame(self, node_id: str, jpeg: bytes):
        cell = self._cells.get(node_id)
        if cell:
            cell.set_frame(jpeg)
        self._fs.update_frame(node_id, jpeg)

    def _relayout(self):
        # Clear grid
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        cols = max(1, min(3, len(self._cells)))
        for i, cell in enumerate(self._cells.values()):
            self._grid.addWidget(cell, i // cols, i % cols)

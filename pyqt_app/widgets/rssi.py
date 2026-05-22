"""4-bar RSSI indicator."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtWidgets import QWidget


class Rssi(QWidget):
    def __init__(self, level=4, parent=None):
        super().__init__(parent)
        self.level = level
        self.setFixedSize(18, 12)

    def set_level(self, lvl: int):
        self.level = max(0, min(4, lvl))
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        heights = [3, 5, 7, 9]
        gap = 1
        w = 2
        x = 0
        y = self.height()
        for i, h in enumerate(heights):
            color = QColor("#6fb56a") if i < self.level else QColor("#5c6771")
            p.fillRect(x, y - h, w, h, color)
            x += w + gap
        p.end()

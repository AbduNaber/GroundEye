"""Horizontal signal bar with an optional threshold marker."""
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush
from PyQt6.QtWidgets import QWidget


class SignalBar(QWidget):
    def __init__(self, value=0.0, threshold=None, color="#d4a84b", parent=None):
        super().__init__(parent)
        self.value = value
        self.threshold = threshold
        self.color = color
        self.setFixedHeight(5)
        self.setMinimumWidth(40)

    def set_value(self, v: float):
        self.value = max(0.0, min(1.0, v))
        self.update()

    def set_color(self, c: str):
        self.color = c
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        r = self.rect()
        p.fillRect(r, QColor("#1c232a"))
        fw = int(r.width() * self.value)
        p.fillRect(0, 0, fw, r.height(), QColor(self.color))
        if self.threshold is not None:
            tx = int(r.width() * self.threshold)
            p.setPen(QPen(QColor("#d86a5b"), 1))
            p.drawLine(tx, -2, tx, r.height() + 2)
        p.end()

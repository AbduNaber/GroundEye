"""Frameless-ish titlebar with brand + status pills."""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget
from datetime import datetime


class WinDot(QWidget):
    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(12, 12)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(self.color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(0, 0, 12, 12)


class BrandMark(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(18, 18)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QColor("#d4a84b"))
        p.drawEllipse(1, 1, 16, 16)
        p.setBrush(QColor("#d4a84b"))
        p.drawEllipse(6, 6, 6, 6)
    

class StatusDot(QWidget):
    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(6, 6)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(self.color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(0, 0, 6, 6)


def status_pill(color: str, text: str) -> QLabel:
    lbl = QLabel(f"●  {text}")
    lbl.setObjectName("statusPill")
    lbl.setStyleSheet(f"color: #8b96a1; border: 1px solid #2e3842; padding: 3px 8px; border-radius: 3px; font-family: 'JetBrains Mono'; font-size: 10px;")
    return lbl


class TitleBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("titlebar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(10)

        lay.addWidget(WinDot("#d86a5b"))
        lay.addWidget(WinDot("#d4a84b"))
        lay.addWidget(WinDot("#6fb56a"))
        lay.addSpacing(6)
        lay.addWidget(BrandMark())
        brand = QLabel("GROUNDEYE · GROUND STATION")
        brand.setProperty("role", "brand")
        lay.addWidget(brand)

        sep = QFrame()
        sep.setFixedSize(1, 16)
        sep.setStyleSheet("background: #2e3842;")
        lay.addWidget(sep)

        path = QLabel("session://site-a/2026-04-19 · operator op_root")
        path.setProperty("role", "monoTiny")
        lay.addWidget(path)

        lay.addStretch(1)

        lay.addWidget(status_pill("#6fb56a", "MQTT BROKER · 192.168.4.1:1883"))
        lay.addWidget(status_pill("#d4a84b", "RPi5 · 41°C · LOAD 0.28"))
        lay.addWidget(status_pill("#5a9fb8", "REC"))

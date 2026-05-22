"""Mini waveform renderer (used in dialog + strip)."""
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QPainterPath
from PyQt6.QtWidgets import QWidget


class WaveformMini(QWidget):
    def __init__(self, data=None, color="#d4a84b", parent=None):
        super().__init__(parent)
        self.data = list(data or [])
        self.color = color
        self.setMinimumHeight(90)

    def set_data(self, data, color=None):
        self.data = list(data)
        if color:
            self.color = color
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        p.fillRect(r, QColor("#0f1317"))

        # Grid
        p.setPen(QPen(QColor(255, 255, 255, 18), 1))
        for frac in (0.25, 0.5, 0.75):
            y = int(r.height() * frac)
            p.drawLine(0, y, r.width(), y)
        for frac in (0.2, 0.4, 0.6, 0.8):
            x = int(r.width() * frac)
            p.drawLine(x, 0, x, r.height())

        # Threshold dashed lines
        mid = r.height() / 2
        scale = (r.height() / 2) * 0.85
        th_y1 = int(mid - 0.38 * scale)
        th_y2 = int(mid + 0.38 * scale)
        pen = QPen(QColor("#d86a5b"), 1, Qt.PenStyle.DashLine)
        pen.setDashPattern([3, 3])
        p.setPen(pen)
        p.drawLine(0, th_y1, r.width(), th_y1)
        p.drawLine(0, th_y2, r.width(), th_y2)

        # Baseline
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawLine(0, int(mid), r.width(), int(mid))

        if not self.data:
            p.end()
            return

        # Waveform path
        path = QPainterPath()
        step = r.width() / max(1, (len(self.data) - 1))
        for i, v in enumerate(self.data):
            x = i * step
            y = mid - v * scale
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        p.setPen(QPen(QColor(self.color), 1.2))
        p.drawPath(path)

        # Peak marker
        peak_i = max(range(len(self.data)), key=lambda i: abs(self.data[i]))
        peak_x = int(peak_i * step)
        pen = QPen(QColor(216, 106, 91, 120), 1, Qt.PenStyle.DashLine)
        pen.setDashPattern([2, 3])
        p.setPen(pen)
        p.drawLine(peak_x, 0, peak_x, r.height())

        p.end()

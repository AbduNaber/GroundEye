"""Signals tab: live waveforms per node via pyqtgraph."""
import collections
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QScrollArea
)
import numpy as np
import pyqtgraph as pg

from pyqt_app.services.store import store
from pyqt_app.services.bus import bus


class SignalRow(QFrame):
    def __init__(self, node, parent=None):
        super().__init__(parent)
        self.node = node
        self.setProperty("role", "signalRow")
        self.setMinimumHeight(150)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(18)

        # Left: title
        left = QVBoxLayout()
        left.setSpacing(4)
        name = QLabel(node.name)
        name.setStyleSheet("font-family: 'JetBrains Mono'; font-size: 12px; color: #d8e0e6;")
        left.addWidget(name)
        sub = QLabel(node.label)
        sub.setProperty("role", "monoMute")
        left.addWidget(sub)
        self.status = QLabel(f"●  {node.status.upper()}")
        self.status.setProperty("role", "monoSmall")
        left.addWidget(self.status)
        left.addStretch(1)
        left_w = QWidget(); left_w.setLayout(left); left_w.setFixedWidth(160)
        lay.addWidget(left_w)

        # Middle: plot
        self.plot = pg.PlotWidget(background="#0f1317")
        self.plot.setMinimumHeight(110)
        self.plot.hideAxis('left'); self.plot.hideAxis('bottom')
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.setYRange(-1, 1)
        self.plot.setXRange(0, 500)
        self.plot.addLine(y=0, pen=pg.mkPen("#ffffff20"))
        self.plot.addLine(y=0.38, pen=pg.mkPen("#d86a5b60", style=Qt.PenStyle.DashLine))
        self.plot.addLine(y=-0.38, pen=pg.mkPen("#d86a5b60", style=Qt.PenStyle.DashLine))
        self.curve = self.plot.plot(pen=pg.mkPen(self._color(), width=1.2))
        self.buffer = collections.deque([0.0] * 500, maxlen=500)
        lay.addWidget(self.plot, 1)

        # Right: stats
        right = QVBoxLayout()
        right.setSpacing(4)
        self.stats = {}
        for k in ("RMS", "PEAK", "THRESH", "FREQ", "BATT", "LINK"):
            row = QHBoxLayout()
            l = QLabel(k); l.setProperty("role", "monoMute")
            v = QLabel("—"); v.setStyleSheet("font-family: 'JetBrains Mono'; font-size: 10px; color: #d8e0e6;")
            v.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(l); row.addStretch(1); row.addWidget(v)
            right.addLayout(row)
            self.stats[k] = v
        right_w = QWidget(); right_w.setLayout(right); right_w.setFixedWidth(140)
        lay.addWidget(right_w)

        self.update_stats()
        bus.node_updated.connect(self._on_node_updated)
        bus.sample_received.connect(self._on_sample)

    def _color(self):
        s = self.node.status
        return ("#d86a5b" if s == "triggered"
                else "#5c6771" if s == "offline"
                else "#d4a84b")

    def _on_sample(self, nid, amp):
        if nid != self.node.id: return
        # Fake waveform expansion around amp
        for i in range(5):
            v = amp * np.sin(i * 0.7 + np.random.rand() * 2) + (np.random.rand() - 0.5) * 0.05
            self.buffer.append(max(-1, min(1, v)))
        self.curve.setData(np.arange(500), np.array(self.buffer))

    def _on_node_updated(self, node):
        if node.id != self.node.id: return
        self.node = node
        self.curve.setPen(pg.mkPen(self._color(), width=1.2))
        self.status.setText(f"●  {node.status.upper()}")
        self.status.setStyleSheet(f"color: {self._color()}; font-family: 'JetBrains Mono'; font-size: 10px;")
        self.update_stats()

    def update_stats(self):
        n = self.node
        self.stats["RMS"].setText(f"{n.signal*0.6:.3f}")
        self.stats["PEAK"].setText(f"{n.signal:.2f}")
        self.stats["THRESH"].setText(f"{n.threshold:.2f}")
        self.stats["FREQ"].setText("2.1 Hz" if n.status == "triggered" else "—")
        self.stats["BATT"].setText(f"{int(n.battery*100)}%")
        self.stats["LINK"].setText("--" if n.status == "offline" else "-64 dBm")


class SignalsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        tb = QFrame(); tb.setObjectName("eventsToolbar")
        hl = QHBoxLayout(tb)
        hl.setContentsMargins(12, 0, 12, 0)
        l = QLabel("LIVE SEISMIC · 500 Hz SAMPLING · BANDPASS 5–40 Hz")
        l.setProperty("role", "monoSmall")
        hl.addWidget(l)
        hl.addStretch(1)
        r = QLabel("WINDOW 4.0s · AUTO-SCROLL"); r.setProperty("role", "monoMute")
        hl.addWidget(r)
        lay.addWidget(tb)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget(); vl = QVBoxLayout(inner); vl.setContentsMargins(0, 0, 0, 0); vl.setSpacing(1)
        inner.setStyleSheet("background: #242c34;")
        for n in store.nodes:
            vl.addWidget(SignalRow(n))
        vl.addStretch(1)
        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)

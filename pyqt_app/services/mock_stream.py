"""Mock stream: jitters node signals, occasionally fires an event."""
import random
from PyQt6.QtCore import QObject, QTimer
from pyqt_app.services.bus import bus
from pyqt_app.services.store import store


class MockStream(QObject):
    def __init__(self):
        super().__init__()
        self.tick = QTimer(self)
        self.tick.setInterval(1200)
        self.tick.timeout.connect(self._tick)
        self.tick.start()

        # Emit an initial toast shortly after launch (matches HTML demo)
        QTimer.singleShot(2800, self._initial_toast)

    def _tick(self):
        for n in store.nodes:
            if n.status in ("offline", "connecting"):
                continue
            base = 0.7 if n.status == "triggered" else 0.1
            n.signal = max(0.0, min(1.0, base + (random.random() - 0.5) * 0.15))
            bus.node_updated.emit(n)
            bus.sample_received.emit(n.id, n.signal)

    def _initial_toast(self):
        bus.toast.emit(
            "alert",
            "New detection · N02",
            "EV-2614 · amp 0.81 · 6.2m",
            "14:31:52 · photo captured",
        )


stream: MockStream | None = None


def start():
    global stream
    stream = MockStream()

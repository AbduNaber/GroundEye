"""Bottom status bar."""
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget
from PyQt6.QtCore import QTimer
from pyqt_app.services.store import store


class StatusBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statusbar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(18)

        self.broker = self._mk("● BROKER online")
        self.nodes = self._mk("")
        self.events = self._mk("")
        self.captures = self._mk("")
        self.disk = self._mk("DISK 18.4 / 64 GB")
        for w in (self.broker, self.nodes, self.events, self.captures, self.disk):
            lay.addWidget(w)

        lay.addStretch(1)
        right = self._mk("groundeye v0.4.2 · build 2026.04.18")
        lay.addWidget(right)

        self.refresh()
        t = QTimer(self)
        t.timeout.connect(self.refresh)
        t.start(1000)

    def _mk(self, text):
        l = QLabel(text)
        l.setProperty("role", "sbItem")
        return l

    def refresh(self):
        on = sum(1 for n in store.nodes if n.status in ("online", "triggered"))
        self.nodes.setText(f"NODES {on}/{len(store.nodes)}")
        open_ct = store.open_events()
        self.events.setText(f"EVENTS {len(store.events)} ({open_ct} open)")
        self.captures.setText(f"CAPTURES {len(store.events)}")

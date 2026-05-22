"""Gallery tab: photo grid with filters."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QScrollArea, QGridLayout
)
from pyqt_app.services.store import store
from pyqt_app.services.bus import bus
from pyqt_app.widgets.photo import Photo


def _chip(text, active=False):
    b = QPushButton(text)
    b.setProperty("role", "chip")
    b.setProperty("active", "true" if active else "false")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


class GalleryCard(QFrame):
    def __init__(self, ev, parent=None):
        super().__init__(parent)
        self.ev = ev
        self.setProperty("role", "gCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(220)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        photo = Photo(ev)
        photo.setMinimumHeight(140)
        lay.addWidget(photo, 1)
        meta = QVBoxLayout(); meta.setContentsMargins(10, 8, 10, 8); meta.setSpacing(2)
        top = QHBoxLayout()
        idl = QLabel(ev.id); idl.setStyleSheet("font-family: 'JetBrains Mono'; font-size: 10px; color: #d8e0e6;")
        top.addWidget(idl); top.addStretch(1)
        sev = QLabel(ev.severity.upper()); sev.setProperty("role", "sevPill"); sev.setProperty("sev", ev.severity)
        top.addWidget(sev)
        meta.addLayout(top)
        meta.addWidget(self._tiny(f"{ev.node_id} · {ev.date}"))
        meta.addWidget(self._tiny(f"{ev.ts[:8]} · {ev.distance:.1f}m"))
        mw = QWidget(); mw.setLayout(meta); lay.addWidget(mw)

    def _tiny(self, text):
        l = QLabel(text); l.setProperty("role", "monoSmall"); return l

    def mousePressEvent(self, e):
        bus.event_opened.emit(self.ev)
        super().mousePressEvent(e)


class GalleryTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.filters = {"node": "all", "time": "all", "sev": "all"}
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        tb = QFrame(); tb.setObjectName("eventsToolbar")
        hl = QHBoxLayout(tb); hl.setContentsMargins(12, 0, 12, 0); hl.setSpacing(6)

        def add_group(label, key, opts):
            lb = QLabel(label); lb.setProperty("role", "monoMute"); hl.addWidget(lb)
            for v in opts:
                b = _chip(v.upper(), active=(self.filters[key] == v))
                b.setProperty("_key", key); b.setProperty("_val", v)
                b.clicked.connect(lambda _=False, kk=key, vv=v: self._set_filter(kk, vv))
                hl.addWidget(b)
            hl.addSpacing(10)

        add_group("NODE", "node", ["all"] + [n.id for n in store.nodes])
        add_group("TIME", "time", ["all", "day", "night"])
        add_group("SEV", "sev", ["all", "high", "med", "info"])
        hl.addStretch(1)
        self.count_lbl = QLabel(""); self.count_lbl.setProperty("role", "monoMute")
        hl.addWidget(self.count_lbl)
        lay.addWidget(tb)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.inner = QWidget()
        self.grid = QGridLayout(self.inner); self.grid.setContentsMargins(14, 14, 14, 14); self.grid.setSpacing(10)
        self.scroll.setWidget(self.inner)
        lay.addWidget(self.scroll, 1)

        self._refresh()

    def _set_filter(self, key, val):
        self.filters[key] = val
        for b in self.findChildren(QPushButton):
            k = b.property("_key"); v = b.property("_val")
            if k is None: continue
            b.setProperty("active", "true" if self.filters.get(k) == v else "false")
            b.style().unpolish(b); b.style().polish(b)
        self._refresh()

    def _filter(self):
        out = []
        for e in store.events:
            if self.filters["node"] != "all" and e.node_id != self.filters["node"]: continue
            if self.filters["time"] == "day" and e.night: continue
            if self.filters["time"] == "night" and not e.night: continue
            if self.filters["sev"] != "all" and e.severity != self.filters["sev"]: continue
            out.append(e)
        return out

    def _refresh(self):
        # Clear grid
        while self.grid.count():
            it = self.grid.takeAt(0)
            w = it.widget()
            if w: w.deleteLater()
        evs = self._filter()
        self.count_lbl.setText(f"{len(evs)} photos")
        cols = 4
        for i, e in enumerate(evs):
            card = GalleryCard(e)
            self.grid.addWidget(card, i // cols, i % cols)

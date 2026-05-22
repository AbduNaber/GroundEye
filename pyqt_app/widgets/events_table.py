"""Events tab: filterable table."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from pyqt_app.services.bus import bus
from pyqt_app.services.store import store
from pyqt_app.widgets.photo import Photo


def _chip(text, active=False):
    b = QPushButton(text)
    b.setProperty("role", "chip")
    b.setProperty("active", "true" if active else "false")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


class EventsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.filters = {"node": "all", "sev": "all", "ack": "all"}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        tb = QFrame()
        tb.setObjectName("eventsToolbar")
        hl = QHBoxLayout(tb)
        hl.setContentsMargins(12, 0, 12, 0)
        hl.setSpacing(6)

        def add_group(label, key, opts):
            lbl = QLabel(label)
            lbl.setProperty("role", "monoMute")
            hl.addWidget(lbl)
            for v in opts:
                b = _chip(v.upper(), active=(self.filters[key] == v))
                b.clicked.connect(lambda _=False, kk=key, vv=v, bb=b: self._set_filter(kk, vv))
                hl.addWidget(b)
                b.setProperty("_key", key); b.setProperty("_val", v)
            hl.addSpacing(10)

        add_group("NODE", "node", ["all"] + [n.id for n in store.nodes])
        add_group("SEVERITY", "sev", ["all", "high", "med", "info"])
        add_group("STATUS", "ack", ["all", "open", "ack"])
        hl.addStretch(1)
        self.count_lbl = QLabel("")
        self.count_lbl.setProperty("role", "monoMute")
        hl.addWidget(self.count_lbl)

        lay.addWidget(tb)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["", "EVENT ID", "TIME", "NODE", "AMP", "DUR", "DIST", "SEVERITY", "STATUS"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 72)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(3, 180)
        self.table.setColumnWidth(4, 60)
        self.table.setColumnWidth(5, 60)
        self.table.setColumnWidth(6, 60)
        self.table.setColumnWidth(7, 90)
        self.table.setCursor(Qt.CursorShape.PointingHandCursor)
        self.table.cellClicked.connect(self._on_cell)
        lay.addWidget(self.table, 1)

        self._refresh()

    def _set_filter(self, key, val):
        self.filters[key] = val
        # update chip active states
        tb = self.findChild(QFrame, "eventsToolbar")
        for b in tb.findChildren(QPushButton):
            k = b.property("_key"); v = b.property("_val")
            if k is None: continue
            b.setProperty("active", "true" if self.filters.get(k) == v else "false")
            b.style().unpolish(b); b.style().polish(b)
        self._refresh()

    def _filter_events(self):
        out = []
        for e in store.events:
            if self.filters["node"] != "all" and e.node_id != self.filters["node"]: continue
            if self.filters["sev"] != "all" and e.severity != self.filters["sev"]: continue
            if self.filters["ack"] == "ack" and not e.ack: continue
            if self.filters["ack"] == "open" and e.ack: continue
            out.append(e)
        return out

    def _refresh(self):
        evs = self._filter_events()
        self.count_lbl.setText(f"{len(evs)} / {len(store.events)} events")
        self.table.setRowCount(len(evs))
        self.table.verticalHeader().setDefaultSectionSize(48)
        for row, ev in enumerate(evs):
            photo = Photo(ev)
            photo.setFixedSize(64, 40)
            self.table.setCellWidget(row, 0, photo)

            items = [
                ev.id,
                f"{ev.date} {ev.ts}",
                f"{ev.node_id} · {store.node(ev.node_id).label if store.node(ev.node_id) else ''}",
                f"{ev.amplitude:.2f}",
                f"{ev.duration:.2f}s",
                f"{ev.distance:.1f}m",
            ]
            for col, text in enumerate(items, start=1):
                it = QTableWidgetItem(text)
                if ev.ack:
                    it.setForeground(Qt.GlobalColor.gray)
                self.table.setItem(row, col, it)

            sev = QLabel(ev.severity.upper())
            sev.setProperty("role", "sevPill")
            sev.setProperty("sev", ev.severity)
            sev.setAlignment(Qt.AlignmentFlag.AlignCenter)
            wrap1 = QWidget(); hl1 = QHBoxLayout(wrap1); hl1.setContentsMargins(6,0,6,0); hl1.addWidget(sev); hl1.addStretch(1)
            self.table.setCellWidget(row, 7, wrap1)

            ack = QLabel("✓ ACK" if ev.ack else "○ OPEN")
            ack.setProperty("role", "ackTag")
            ack.setProperty("ack", "true" if ev.ack else "false")
            ack.setAlignment(Qt.AlignmentFlag.AlignCenter)
            wrap2 = QWidget(); hl2 = QHBoxLayout(wrap2); hl2.setContentsMargins(6,0,6,0); hl2.addWidget(ack); hl2.addStretch(1)
            self.table.setCellWidget(row, 8, wrap2)

    def _on_cell(self, row, col):
        evs = self._filter_events()
        if 0 <= row < len(evs):
            bus.event_opened.emit(evs[row])

"""Dashboard tab: map + right rail + strip."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QLabel,
    QPushButton, QScrollArea
)
from pyqt_app.services.store import store
from pyqt_app.services.bus import bus
from pyqt_app.widgets.field_map import FieldMap
from pyqt_app.widgets.node_card import NodeCard
from pyqt_app.widgets.event_ticker import EventTicker
from pyqt_app.widgets.strip import Strip


def _panel_head(title, tools=None, extra=None):
    f = QFrame(); f.setObjectName("panelHead")
    hl = QHBoxLayout(f); hl.setContentsMargins(12, 0, 12, 0); hl.setSpacing(8)
    t = QLabel(title); t.setProperty("role", "panelTitle")
    hl.addWidget(t)
    if extra:
        hl.addWidget(extra)
    hl.addStretch(1)
    if tools:
        for tb in tools: hl.addWidget(tb)
    return f


class Dashboard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QGridLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(1)
        lay.setColumnStretch(0, 1); lay.setColumnStretch(1, 0)
        lay.setRowStretch(0, 1); lay.setRowStretch(1, 0)
        self.setStyleSheet("background: #242c34;")

        # Map panel
        self.map = FieldMap()
        map_panel = QFrame(); map_panel.setObjectName("panel")
        mv = QVBoxLayout(map_panel); mv.setContentsMargins(0, 0, 0, 0); mv.setSpacing(0)

        radii = QPushButton("RADII"); radii.setProperty("role", "tool"); radii.setProperty("active", "true")
        paths = QPushButton("TRACKS"); paths.setProperty("role", "tool"); paths.setProperty("active", "true")
        grid = QPushButton("GRID"); grid.setProperty("role", "tool"); grid.setProperty("active", "true")
        for b, k in ((radii, "radii"), (paths, "paths"), (grid, "grid")):
            b.clicked.connect(lambda _=False, bb=b, kk=k: self._toggle(bb, kk))

        coords = QLabel("40.8124° N · 29.3592° E"); coords.setProperty("role", "monoMute")
        mv.addWidget(_panel_head("FIELD MAP · SITE-A", tools=[radii, paths, grid], extra=coords))
        mv.addWidget(self.map, 1)
        lay.addWidget(map_panel, 0, 0)

        # Right rail
        rail = QFrame(); rail.setObjectName("panel")
        rv = QVBoxLayout(rail); rv.setContentsMargins(0, 0, 0, 0); rv.setSpacing(0)
        rail.setFixedWidth(360)

        # Nodes section
        add_btn = QPushButton("+ ADD"); add_btn.setProperty("role", "tool")
        rv.addWidget(_panel_head(f"SENSOR NODES · {len(store.nodes)}/{len(store.nodes)} ONLINE", tools=[add_btn]))
        nodes_scroll = QScrollArea(); nodes_scroll.setWidgetResizable(True); nodes_scroll.setFrameShape(QFrame.Shape.NoFrame)
        nodes_inner = QWidget()
        self.nodes_lay = QVBoxLayout(nodes_inner); self.nodes_lay.setContentsMargins(8, 8, 8, 8); self.nodes_lay.setSpacing(6)
        self.node_cards = {}
        for n in store.nodes:
            card = NodeCard(n); card.set_selected(n.id == "N02")
            self.node_cards[n.id] = card
            self.nodes_lay.addWidget(card)
        self.nodes_lay.addStretch(1)
        nodes_scroll.setWidget(nodes_inner)
        nodes_scroll.setFixedHeight(360)
        rv.addWidget(nodes_scroll)

        # Ticker section
        rv.addWidget(_panel_head("EVENT FEED · LIVE",
                                 extra=QLabel(f"{len(store.events)} total")))
        self.ticker = EventTicker(store.events, store)
        rv.addWidget(self.ticker, 1)

        lay.addWidget(rail, 0, 1)

        # Strip
        strip_panel = QFrame(); strip_panel.setObjectName("panel")
        sv = QVBoxLayout(strip_panel); sv.setContentsMargins(0, 0, 0, 0); sv.setSpacing(0)
        strip_panel.setFixedHeight(170)
        sv.addWidget(_panel_head(f"RECENT CAPTURES · {len(store.events[:10])}",
                                  extra=QLabel("/var/lib/groundeye/captures")))
        self.strip = Strip(store.events)
        sv.addWidget(self.strip, 1)
        lay.addWidget(strip_panel, 1, 0, 1, 2)

        bus.node_selected.connect(self._on_select)
        bus.event_received.connect(self._on_live_event)

    def _on_live_event(self, ev) -> None:
        self.ticker.prepend_event(ev)

    def _toggle(self, btn, key):
        active = btn.property("active") != "true"
        btn.setProperty("active", "true" if active else "false")
        btn.style().unpolish(btn); btn.style().polish(btn)
        self.map.set_option(key, active)

    def _on_select(self, node_id):
        for nid, card in self.node_cards.items():
            card.set_selected(nid == node_id)

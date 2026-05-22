"""Node card (right rail)."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, QWidget
)
from pyqt_app.widgets.signal_bar import SignalBar
from pyqt_app.widgets.rssi import Rssi
from pyqt_app.services.bus import bus


class NodeCard(QFrame):
    def __init__(self, node, parent=None):
        super().__init__(parent)
        self.node = node
        self.setProperty("role", "nodeCard")
        self.setProperty("selected", "false")
        self.setProperty("triggered", "false")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # Top row: id + status
        top = QHBoxLayout()
        top.setSpacing(8)
        name_box = QVBoxLayout()
        name_box.setSpacing(2)
        self.name_lbl = QLabel(node.name)
        self.name_lbl.setProperty("role", "nodeId")
        self.sub_lbl = QLabel(node.label)
        self.sub_lbl.setProperty("role", "nodeSub")
        name_box.addWidget(self.name_lbl)
        name_box.addWidget(self.sub_lbl)
        top.addLayout(name_box)
        top.addStretch(1)
        self.status_lbl = QLabel()
        self.status_lbl.setProperty("role", "nodeStatus")
        top.addWidget(self.status_lbl)
        lay.addLayout(top)

        # Grid of metrics
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)

        def small(text, role="cellLabel"):
            l = QLabel(text)
            l.setProperty("role", role)
            return l

        grid.addWidget(small("SIGNAL"), 0, 0)
        self.signal_bar = SignalBar(value=node.signal, threshold=node.threshold)
        grid.addWidget(self.signal_bar, 0, 1)
        self.signal_val = QLabel(f"{node.signal:.2f}")
        self.signal_val.setProperty("role", "monoSmall")
        self.signal_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.signal_val.setFixedWidth(40)
        grid.addWidget(self.signal_val, 0, 2)

        grid.addWidget(small("LINK"), 1, 0)
        link_row = QHBoxLayout()
        link_row.setSpacing(6)
        self.rssi = Rssi(node.rssi)
        link_row.addWidget(self.rssi)
        link_row.addStretch(1)
        link_w = QWidget()
        link_w.setLayout(link_row)
        grid.addWidget(link_w, 1, 1)
        self.link_val = QLabel("--" if node.status == "offline" else "-64 dBm")
        self.link_val.setProperty("role", "monoSmall")
        self.link_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.link_val.setFixedWidth(60)
        grid.addWidget(self.link_val, 1, 2)

        grid.addWidget(small("BATT"), 2, 0)
        self.batt_bar = SignalBar(value=node.battery)
        self.batt_bar.set_color(
            "#d86a5b" if node.battery < 0.3 else "#d4a84b" if node.battery < 0.5 else "#6fb56a"
        )
        grid.addWidget(self.batt_bar, 2, 1)
        self.batt_val = QLabel(f"{int(node.battery*100)}%")
        self.batt_val.setProperty("role", "monoSmall")
        self.batt_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.batt_val.setFixedWidth(40)
        grid.addWidget(self.batt_val, 2, 2)

        grid.setColumnMinimumWidth(0, 50)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        foot = QHBoxLayout()
        self.last_lbl = QLabel(f"last {node.last_trigger}")
        self.last_lbl.setProperty("role", "monoSmall")
        self.temp_lbl = QLabel(f"{node.temp:.1f}°C")
        self.temp_lbl.setProperty("role", "monoSmall")
        foot.addWidget(self.last_lbl)
        foot.addStretch(1)
        foot.addWidget(self.temp_lbl)
        lay.addLayout(foot)

        self._refresh_status()
        bus.node_updated.connect(self._on_node_updated)

    def _refresh_status(self):
        n = self.node
        s = n.status
        color = (
            "#d86a5b" if s == "triggered"
            else "#5c6771" if s == "offline"
            else "#5a9fb8" if s == "connecting"
            else "#6fb56a"
        )
        self.status_lbl.setText(f"●  {s.upper()}")
        self.status_lbl.setStyleSheet(f"color: {color};")
        self.setProperty("triggered", "true" if s == "triggered" else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def set_selected(self, v: bool):
        self.setProperty("selected", "true" if v else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def _on_node_updated(self, node):
        if node.id != self.node.id:
            return
        self.node = node
        self.signal_bar.set_value(node.signal)
        self.signal_bar.set_color("#d86a5b" if node.status == "triggered" else "#d4a84b")
        self.signal_val.setText(f"{node.signal:.2f}")
        self.rssi.set_level(node.rssi)
        self._refresh_status()

    def mousePressEvent(self, ev):
        bus.node_selected.emit(self.node.id)
        super().mousePressEvent(ev)

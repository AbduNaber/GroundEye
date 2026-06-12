"""Event detail modal dialog."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QGridLayout, QWidget
)
from pyqt_app.widgets.photo import Photo
from pyqt_app.widgets.waveform_mini import WaveformMini
from pyqt_app.services.store import store
from pyqt_app.services.bus import bus


class EventDialog(QDialog):
    def __init__(self, event, parent=None):
        super().__init__(parent)
        self.event = event
        self.setObjectName("eventDialog")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.resize(1100, 620)
        self.setStyleSheet("QDialog#eventDialog { background: #12171c; border: 1px solid #2e3842; }")

        node = store.node(event.node_id)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        head = QFrame(); head.setObjectName("modalHead")
        hl = QHBoxLayout(head); hl.setContentsMargins(14, 0, 14, 0); hl.setSpacing(12)
        mid = QLabel(event.id); mid.setObjectName("modalId")
        hl.addWidget(mid)
        sev = QLabel(event.severity.upper()); sev.setProperty("role", "sevPill"); sev.setProperty("sev", event.severity)
        hl.addWidget(sev)
        info = QLabel(f"{event.date} · {event.ts} · {node.name if node else ''} · {node.label if node else ''}")
        info.setProperty("role", "monoSmall")
        hl.addWidget(info)
        hl.addStretch(1)
        close = QPushButton("✕"); close.setProperty("role", "tool"); close.setFixedSize(28, 28)
        close.clicked.connect(self.reject)
        hl.addWidget(close)
        root.addWidget(head)

        # Body: left photo, right meta
        body = QHBoxLayout(); body.setContentsMargins(0, 0, 0, 0); body.setSpacing(1)
        body_w = QWidget(); body_w.setLayout(body); body_w.setStyleSheet("background: #242c34;")

        # Photo side
        photo_side = QWidget(); ps = QVBoxLayout(photo_side); ps.setContentsMargins(0, 0, 0, 0); ps.setSpacing(0)
        photo_side.setStyleSheet("background: black;")
        photo = Photo(event, big=True)
        photo.setMinimumHeight(360)
        ps.addWidget(photo, 1)
        controls = QFrame(); controls.setStyleSheet("background: #0f1317; border-top: 1px solid #242c34;")
        controls.setFixedHeight(34)
        cl = QHBoxLayout(controls); cl.setContentsMargins(12, 0, 12, 0); cl.setSpacing(8)
        prev_b = QPushButton("◀ PREV"); prev_b.setProperty("role", "tool")
        next_b = QPushButton("NEXT ▶"); next_b.setProperty("role", "tool")
        cl.addWidget(prev_b); cl.addWidget(next_b); cl.addStretch(1)
        info_l = QLabel("1920×1080 · 242 KB · JPEG"); info_l.setProperty("role", "monoSmall")
        cl.addWidget(info_l)
        dl = QPushButton("DOWNLOAD"); dl.setProperty("role", "tool"); cl.addWidget(dl)
        op = QPushButton("OPEN FOLDER"); op.setProperty("role", "tool"); cl.addWidget(op)
        ps.addWidget(controls)
        body.addWidget(photo_side, 14)

        # Meta side
        meta = QWidget(); ml = QVBoxLayout(meta); ml.setContentsMargins(14, 14, 14, 14); ml.setSpacing(14)
        meta.setStyleSheet("background: #12171c;")

        # Meta grid (2x3)
        grid = QFrame(); grid.setStyleSheet("background: #242c34;")
        gl = QGridLayout(grid); gl.setContentsMargins(1, 1, 1, 1); gl.setSpacing(1)

        def cell(lbl, val, sub=""):
            f = QFrame(); f.setProperty("role", "metaCell")
            v = QVBoxLayout(f); v.setContentsMargins(10, 10, 10, 10); v.setSpacing(3)
            l1 = QLabel(lbl); l1.setProperty("role", "cellLabel")
            l2 = QLabel(val)
            l2.setStyleSheet(f"font-family: 'JetBrains Mono'; font-size: 13px; color: #d8e0e6;")
            v.addWidget(l1); v.addWidget(l2)
            if sub:
                l3 = QLabel(sub); l3.setProperty("role", "monoMute")
                v.addWidget(l3)
            return f

        gl.addWidget(cell("SENSOR", event.node_id, node.mac if node else ""), 0, 0)
        gl.addWidget(cell("TIMESTAMP", event.ts), 0, 1)
        gl.addWidget(cell("PEAK AMPLITUDE", f"{event.amplitude:.3f} g"), 1, 0)
        gl.addWidget(cell("DURATION", f"{event.duration:.2f} s"), 1, 1)
        gl.addWidget(cell("EST. DISTANCE", f"{event.distance:.1f} m",
                          f"from {event.node_id}"), 2, 0)
        gl.addWidget(cell("THRESHOLD", f"{node.threshold:.2f}" if node else "—"), 2, 1)
        ml.addWidget(grid)

        # Waveforms — one row per participating node
        wf_wrap = QFrame()
        wf_wrap.setStyleSheet("background: #0f1317; border: 1px solid #242c34;")
        wv = QVBoxLayout(wf_wrap); wv.setContentsMargins(10, 10, 10, 10); wv.setSpacing(4)

        NODE_COLORS = {"N01": "#5a9fb8", "N02": "#6fb56a", "N03": "#d4a84b"}

        waveforms = event.node_waveforms if event.node_waveforms else {event.node_id: event.waveform}
        for sid, wfdata in waveforms.items():
            row_hdr = QHBoxLayout()
            lbl = QLabel(f"SEISMIC · {sid}"); lbl.setProperty("role", "monoMute")
            marker = "▶" if sid == event.node_id else " "
            tag_lbl = QLabel(f"{marker} NEAREST" if sid == event.node_id else "")
            tag_lbl.setProperty("role", "monoMute")
            tag_lbl.setStyleSheet(f"color: {NODE_COLORS.get(sid, '#8b96a1')};")
            row_hdr.addWidget(lbl); row_hdr.addWidget(tag_lbl); row_hdr.addStretch(1)
            wv.addLayout(row_hdr)
            wf = WaveformMini(wfdata, color=NODE_COLORS.get(sid, "#d4a84b"))
            wf.setFixedHeight(80)
            wv.addWidget(wf)

        ml.addWidget(wf_wrap)

        if event.notes:
            notes = QLabel(f"NOTE  {event.notes}")
            notes.setProperty("role", "monoSmall")
            notes.setWordWrap(True)
            ml.addWidget(notes)

        # Actions
        actions = QHBoxLayout(); actions.setSpacing(8)
        if not event.ack:
            ack_b = QPushButton("ACKNOWLEDGE"); ack_b.setProperty("role", "btnPrimary")
            ack_b.clicked.connect(self._ack)
            actions.addWidget(ack_b)
        else:
            ack_b = QPushButton("✓ ACKNOWLEDGED"); ack_b.setProperty("role", "btn"); ack_b.setEnabled(False)
            actions.addWidget(ack_b)
        fp = QPushButton("FLAG FALSE POSITIVE"); fp.setProperty("role", "btn")
        ex = QPushButton("EXPORT .CSV"); ex.setProperty("role", "btn")
        actions.addWidget(fp); actions.addWidget(ex); actions.addStretch(1)
        ml.addLayout(actions)
        ml.addStretch(1)

        body.addWidget(meta, 10)
        root.addWidget(body_w, 1)

    def _ack(self):
        store.ack(self.event.id)
        bus.event_acked.emit(self.event.id)
        self.accept()

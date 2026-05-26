"""Recordings tab: list saved sessions + playback controls."""
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QSlider, QScrollArea, QButtonGroup,
)
from pyqt_app.services.player import player, list_recordings, fmt_duration
from pyqt_app.services.recorder import recorder
from pyqt_app.services.bus import bus


def _elapsed_str(ms: int) -> str:
    """MM:SS for elapsed display (always shows two-part format)."""
    s = int(ms) // 1000
    m, s = divmod(s, 60)
    return f"{m:02d}:{s:02d}"


def _tool_btn(text: str, checkable: bool = False) -> QPushButton:
    b = QPushButton(text)
    b.setProperty("role", "tool")
    if checkable:
        b.setCheckable(True)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


# ---------------------------------------------------------------------------
# Recording list item — uses mousePressEvent to drive selection
# ---------------------------------------------------------------------------

class RecordingItem(QFrame):
    def __init__(self, meta: dict, on_select, parent=None):
        super().__init__(parent)
        self._meta = meta
        self._on_select = on_select
        self._selected = False
        self.setProperty("role", "tickerItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(12)

        indicator = QFrame()
        indicator.setFixedSize(3, 28)
        indicator.setStyleSheet("background: #3a4550; border-radius: 1px;")
        lay.addWidget(indicator)

        col = QVBoxLayout()
        col.setSpacing(2)

        self._name_lbl = QLabel(Path(meta["path"]).stem)
        self._name_lbl.setProperty("role", "tickerTitle")
        col.addWidget(self._name_lbl)

        dur = fmt_duration(meta["duration_ms"])
        empty_tag = "  ⚠ empty" if meta["count"] == 0 else ""
        info = QLabel(
            f"{meta['count']} events  ·  {dur}  ·  {meta['size_kb']} KB{empty_tag}"
        )
        info.setProperty("role", "tickerMeta")
        if meta["count"] == 0:
            info.setStyleSheet("color: #5c6771;")
        col.addWidget(info)
        lay.addLayout(col, 1)

    def set_selected(self, v: bool) -> None:
        self._selected = v
        self.setStyleSheet(
            "background: #1a2530;" if v else ""
        )

    def mousePressEvent(self, ev):
        self._on_select(self._meta)
        super().mousePressEvent(ev)


# ---------------------------------------------------------------------------
# Playback controls panel
# ---------------------------------------------------------------------------

class PlaybackControls(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(12)

        # ── State pill ───────────────────────────────────────────────────
        self._state_pill = QLabel("■  IDLE")
        self._state_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._state_pill.setStyleSheet(
            "color: #5c6771; border: 1px solid #2e3842; border-radius: 3px;"
            "padding: 4px 12px; font-family: 'JetBrains Mono'; font-size: 11px;"
        )
        lay.addWidget(self._state_pill)

        # ── File name ────────────────────────────────────────────────────
        self._name_lbl = QLabel("—")
        self._name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_lbl.setProperty("role", "monoSmall")
        self._name_lbl.setStyleSheet("color: #8b96a1;")
        lay.addWidget(self._name_lbl)

        # ── Progress slider ──────────────────────────────────────────────
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 1000)
        self._slider.setValue(0)
        self._slider.setEnabled(False)
        self._slider.sliderMoved.connect(self._on_seek)
        lay.addWidget(self._slider)

        time_row = QHBoxLayout()
        self._elapsed_lbl = QLabel("00:00")
        self._elapsed_lbl.setProperty("role", "monoSmall")
        self._total_lbl = QLabel("00:00")
        self._total_lbl.setProperty("role", "monoSmall")
        time_row.addWidget(self._elapsed_lbl)
        time_row.addStretch(1)
        time_row.addWidget(self._total_lbl)
        lay.addLayout(time_row)

        # ── Transport ────────────────────────────────────────────────────
        transport = QHBoxLayout()
        transport.setSpacing(6)
        self._play_btn  = _tool_btn("▶  PLAY")
        self._pause_btn = _tool_btn("⏸  PAUSE")
        self._stop_btn  = _tool_btn("⏹  STOP")
        self._play_btn.clicked.connect(self._on_play)
        self._pause_btn.clicked.connect(self._on_pause)
        self._stop_btn.clicked.connect(player.stop)
        self._play_btn.setEnabled(False)
        self._pause_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)
        for b in (self._play_btn, self._pause_btn, self._stop_btn):
            transport.addWidget(b)
        lay.addLayout(transport)

        # ── Speed ────────────────────────────────────────────────────────
        speed_row = QHBoxLayout()
        speed_row.setSpacing(4)
        lbl = QLabel("SPEED")
        lbl.setProperty("role", "monoMute")
        speed_row.addWidget(lbl)
        self._speed_grp = QButtonGroup(self)
        for spd in (0.5, 1.0, 2.0, 4.0):
            b = _tool_btn(f"{spd}×", checkable=True)
            b.setProperty("_spd", spd)
            if spd == 1.0:
                b.setChecked(True)
            b.clicked.connect(lambda _=False, bb=b: self._on_speed(bb))
            self._speed_grp.addButton(b)
            speed_row.addWidget(b)
        speed_row.addStretch(1)
        lay.addLayout(speed_row)

        lay.addStretch(1)

        self._selected_path = ""
        self._selected_duration_ms = 0

        player.playback_started.connect(self._on_player_started)
        player.playback_stopped.connect(self._on_player_stopped)
        player.playback_error.connect(self._on_player_error)
        player.playback_progress.connect(self._on_progress)
        player.playback_tick.connect(self._on_tick)

    # ------------------------------------------------------------------
    def select(self, meta: dict) -> None:
        player.stop()
        self._selected_path = meta["path"]
        self._selected_duration_ms = meta["duration_ms"]
        self._name_lbl.setText(Path(meta["path"]).stem)
        self._total_lbl.setText(fmt_duration(meta["duration_ms"]))
        self._elapsed_lbl.setText("00:00")
        self._slider.setValue(0)

        empty = meta["count"] == 0
        self._slider.setEnabled(not empty)
        self._play_btn.setEnabled(not empty)
        self._pause_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)

        if empty:
            self._set_state("empty")
        else:
            self._set_state("idle")

    def _set_state(self, state: str) -> None:
        styles = {
            "idle":    ("■  IDLE",             "#5c6771", "#2e3842"),
            "playing": ("▶  PLAYING",           "#6fb56a", "#1a3020"),
            "paused":  ("⏸  PAUSED",            "#d4a84b", "#302810"),
            "empty":   ("⚠  EMPTY RECORDING",   "#d86a5b", "#2e1818"),
            "error":   ("✕  ERROR",             "#d86a5b", "#2e1818"),
        }
        text, color, bg = styles.get(state, styles["idle"])
        self._state_pill.setText(text)
        self._state_pill.setStyleSheet(
            f"color: {color}; border: 1px solid {color}; border-radius: 3px;"
            f"padding: 4px 12px; font-family: 'JetBrains Mono'; font-size: 11px;"
            f"background: {bg};"
        )

    def _on_play(self):
        if not self._selected_path:
            return
        if player.is_paused:
            player.play()
        else:
            if player.load(self._selected_path):
                player.play()

    def _on_pause(self):
        if player.is_playing:
            player.pause()
        elif player.is_paused:
            player.play()

    def _on_seek(self, value: int):
        player.seek(value / 1000.0)
        self._elapsed_lbl.setText(_elapsed_str(value / 1000.0 * self._selected_duration_ms))

    def _on_speed(self, btn: QPushButton):
        spd = btn.property("_spd")
        if spd:
            player.speed = spd

    def _on_player_started(self, path: str):
        self._set_state("playing")
        self._play_btn.setEnabled(False)
        self._pause_btn.setEnabled(True)
        self._stop_btn.setEnabled(True)
        # Ensure total duration stays visible
        self._total_lbl.setText(_elapsed_str(self._selected_duration_ms))

    def _on_player_stopped(self):
        self._set_state("idle")
        has = bool(self._selected_path) and self._selected_duration_ms >= 0
        self._play_btn.setEnabled(has)
        self._pause_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)
        self._slider.setValue(0)
        self._elapsed_lbl.setText("00:00")

    def _on_player_error(self, msg: str):
        self._set_state("error")
        self._name_lbl.setText(msg)
        self._play_btn.setEnabled(False)

    def _on_progress(self, p: float):
        if not self._slider.isSliderDown():
            self._slider.setValue(int(p * 1000))
        if player.is_paused:
            self._set_state("paused")
            self._pause_btn.setText("▶  RESUME")
        elif player.is_playing:
            self._set_state("playing")
            self._pause_btn.setText("⏸  PAUSE")

    def _on_tick(self, elapsed_ms: int, total_ms: int):
        self._elapsed_lbl.setText(_elapsed_str(elapsed_ms))
        # total_ms from player may be stretched; prefer it over meta value
        if total_ms:
            self._total_lbl.setText(fmt_duration(total_ms))


# ---------------------------------------------------------------------------
# Main tab
# ---------------------------------------------------------------------------

class RecordingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)

        # ── Left: session list ───────────────────────────────────────────
        left = QFrame()
        left.setObjectName("panel")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)

        head = QFrame()
        head.setObjectName("panelHead")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(12, 0, 12, 0)
        title = QLabel("RECORDED SESSIONS")
        title.setProperty("role", "panelTitle")
        hl.addWidget(title)
        hl.addStretch(1)
        self._count_lbl = QLabel("")
        self._count_lbl.setProperty("role", "monoMute")
        hl.addWidget(self._count_lbl)
        refresh_btn = _tool_btn("↻ REFRESH")
        refresh_btn.clicked.connect(self._refresh_list)
        hl.addWidget(refresh_btn)
        lv.addWidget(head)

        # Scroll area with custom item widgets
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._list_inner = QWidget()
        self._list_lay = QVBoxLayout(self._list_inner)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(1)
        self._list_lay.addStretch(1)
        scroll.setWidget(self._list_inner)
        lv.addWidget(scroll, 1)

        self._empty_lbl = QLabel("No recordings yet.\nPress REC to start.")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setProperty("role", "monoMute")
        self._empty_lbl.setVisible(False)
        lv.addWidget(self._empty_lbl)

        lay.addWidget(left, 1)

        # ── Right: playback controls ─────────────────────────────────────
        right = QFrame()
        right.setObjectName("panel")
        right.setFixedWidth(360)
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        rhead = QFrame()
        rhead.setObjectName("panelHead")
        rhl = QHBoxLayout(rhead)
        rhl.setContentsMargins(12, 0, 12, 0)
        rtitle = QLabel("PLAYBACK")
        rtitle.setProperty("role", "panelTitle")
        rhl.addWidget(rtitle)
        rv.addWidget(rhead)

        self._controls = PlaybackControls()
        rv.addWidget(self._controls)

        lay.addWidget(right)

        self._metas: list[dict] = []
        self._items: list[RecordingItem] = []
        self._selected_item: RecordingItem | None = None

        self._refresh_list()
        recorder.recording_stopped.connect(lambda p, n: self._refresh_list())

    def _refresh_list(self) -> None:
        # Remove old items (keep stretch at end)
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._items.clear()
        self._selected_item = None

        self._metas = list_recordings()
        for meta in self._metas:
            widget = RecordingItem(meta, self._on_item_selected)
            self._list_lay.insertWidget(self._list_lay.count() - 1, widget)
            self._items.append(widget)

        has = bool(self._metas)
        self._empty_lbl.setVisible(not has)
        self._count_lbl.setText(f"{len(self._metas)} sessions" if has else "")

    def _on_item_selected(self, meta: dict) -> None:
        # Deselect old
        if self._selected_item:
            self._selected_item.set_selected(False)
        # Find and select new
        for item in self._items:
            if item._meta["path"] == meta["path"]:
                item.set_selected(True)
                self._selected_item = item
                break
        self._controls.select(meta)

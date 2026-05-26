"""Session player — replays a .jsonl recording on the bus."""
import json
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from pyqt_app.services.bus import bus
from pyqt_app.services.store import store

RECORDINGS_DIR = Path(__file__).parent.parent.parent / "recordings"
MIN_PLAYBACK_MS = 3000   # minimum duration shown for very short recordings


def list_recordings() -> list[dict]:
    """Return metadata dicts for all .jsonl files, newest first."""
    out = []
    if not RECORDINGS_DIR.exists():
        return out
    for p in sorted(RECORDINGS_DIR.glob("*.jsonl"), reverse=True):
        meta = _scan(p)
        out.append({
            "path": str(p),
            "name": p.name,
            "count": meta["count"],
            "duration_ms": meta["duration_ms"],
            "size_kb": p.stat().st_size // 1024,
        })
    return out


def _scan(path: Path) -> dict:
    count = 0
    last_ts = 0
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                count += 1
                last_ts = max(last_ts, obj.get("ts_ms", 0))
    except Exception:
        pass
    return {"count": count, "duration_ms": last_ts}


def fmt_duration(ms: int) -> str:
    """Human-readable duration: '—', '850ms', '23s', '1:04'."""
    if ms <= 0:
        return "—"
    if ms < 1000:
        return f"{ms}ms"
    s = ms / 1000
    if s < 60:
        return f"{s:.0f}s"
    m = int(s) // 60
    return f"{m}:{int(s) % 60:02d}"


class PlayerService(QObject):
    playback_started  = pyqtSignal(str)    # filepath
    playback_stopped  = pyqtSignal()
    playback_error    = pyqtSignal(str)    # error message
    playback_progress = pyqtSignal(float)  # 0..1
    playback_tick     = pyqtSignal(int, int)  # elapsed_ms, total_ms (display)

    def __init__(self) -> None:
        super().__init__()
        self._raw_events: list[dict] = []   # original, unmodified
        self._events: list[dict] = []       # working copy (may have scaled ts)
        self._cursor = 0
        self._raw_total_ms = 0              # from file
        self._display_total_ms = 0          # may be stretched for UX
        self._speed = 1.0
        self._start_real = 0.0
        self._paused_elapsed_ms = 0.0
        self._path = ""
        self.is_playing = False
        self.is_paused = False

        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, path: str) -> bool:
        self.stop()
        self._raw_events = []
        self._path = path
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._raw_events.append(json.loads(line))
        except Exception as exc:
            self.playback_error.emit(f"Cannot open file: {exc}")
            return False

        self._raw_events.sort(key=lambda e: e.get("ts_ms", 0))
        self._raw_total_ms = self._raw_events[-1]["ts_ms"] if self._raw_events else 0
        return True

    def play(self) -> None:
        if not self._raw_events:
            self.playback_error.emit("Recording is empty — no events to replay.")
            return

        if self.is_paused:
            self._start_real = time.monotonic() - self._paused_elapsed_ms / (self._speed * 1000)
            self.is_paused = False
            self.is_playing = True
            self._timer.start()
            self.playback_started.emit(self._path)
            return

        # Build working copy; stretch timestamps if recording is very short
        self._events = [dict(e) for e in self._raw_events]
        if self._raw_total_ms < MIN_PLAYBACK_MS and len(self._events) > 1:
            scale = MIN_PLAYBACK_MS / max(self._raw_total_ms, 1)
            for e in self._events:
                e["ts_ms"] = int(e["ts_ms"] * scale)
            self._display_total_ms = MIN_PLAYBACK_MS
        elif self._raw_total_ms == 0 and len(self._events) >= 1:
            # All events at ts=0: spread evenly
            interval = MIN_PLAYBACK_MS // len(self._events)
            for i, e in enumerate(self._events):
                e["ts_ms"] = i * interval
            self._display_total_ms = interval * len(self._events)
        else:
            self._display_total_ms = self._raw_total_ms

        self._reset_state()
        self._cursor = 0
        self._paused_elapsed_ms = 0.0
        self._start_real = time.monotonic()
        self.is_playing = True
        self.is_paused = False
        self._timer.start()
        self.playback_started.emit(self._path)

    def pause(self) -> None:
        if not self.is_playing:
            return
        self._paused_elapsed_ms = self._elapsed_sim_ms()
        self.is_playing = False
        self.is_paused = True
        self._timer.stop()

    def stop(self) -> None:
        self._timer.stop()
        was_active = self.is_playing or self.is_paused
        self.is_playing = False
        self.is_paused = False
        self._cursor = 0
        self._paused_elapsed_ms = 0.0
        self.playback_stopped.emit()
        if was_active:
            self._reset_state()

    def seek(self, fraction: float) -> None:
        if not self._events:
            return
        target_ms = int(fraction * self._display_total_ms)
        was_playing = self.is_playing
        self._timer.stop()
        self._cursor = 0
        self._reset_state()
        for i, ev in enumerate(self._events):
            if ev["ts_ms"] <= target_ms:
                self._emit_event(ev)
                self._cursor = i + 1
            else:
                break
        self._paused_elapsed_ms = float(target_ms)
        if was_playing:
            self._start_real = time.monotonic() - target_ms / (self._speed * 1000)
            self._timer.start()
        else:
            self.is_paused = True

    @property
    def speed(self) -> float:
        return self._speed

    @speed.setter
    def speed(self, v: float) -> None:
        if self.is_playing:
            elapsed = self._elapsed_sim_ms()
            self._speed = v
            self._start_real = time.monotonic() - elapsed / (v * 1000)
        else:
            self._speed = v

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _elapsed_sim_ms(self) -> float:
        return (time.monotonic() - self._start_real) * self._speed * 1000

    def _tick(self) -> None:
        elapsed = self._elapsed_sim_ms()

        while self._cursor < len(self._events):
            ev = self._events[self._cursor]
            if ev["ts_ms"] <= elapsed:
                self._emit_event(ev)
                self._cursor += 1
            else:
                break

        total = self._display_total_ms or 1
        progress = min(1.0, elapsed / total)
        self.playback_progress.emit(progress)
        self.playback_tick.emit(int(min(elapsed, self._display_total_ms)),
                                self._display_total_ms)

        # Stop only after both all events fired AND display time elapsed
        if self._cursor >= len(self._events) and elapsed >= self._display_total_ms:
            self.stop()

    def _emit_event(self, ev: dict) -> None:
        topic = ev.get("topic", "")
        payload = ev.get("payload", {})
        if topic == "groundeye/location":
            bus.location_received.emit(payload)
        elif topic == "groundeye/status":
            bus.status_received.emit(payload)
        elif topic == "groundeye/event":
            bus.mqtt_event_received.emit(payload)

    def _reset_state(self) -> None:
        for node in store.nodes:
            node.status = "offline"
            node.signal = 0.0
            node.rssi = 0
            bus.node_updated.emit(node)
        bus.playback_reset.emit()
        # Clear heartbeat timestamps so MqttHandler doesn't mistake
        # replayed status events for live ones
        from pyqt_app.services import mqtt_client
        if mqtt_client.handler:
            mqtt_client.handler._heartbeats.clear()


player = PlayerService()

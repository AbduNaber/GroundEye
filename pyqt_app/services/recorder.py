"""Session recorder — writes every MQTT message to a .jsonl file."""
import json
import time
from pathlib import Path
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal

from pyqt_app.services.bus import bus

RECORDINGS_DIR = Path(__file__).parent.parent.parent / "recordings"


class RecorderService(QObject):
    recording_started = pyqtSignal(str)   # filepath
    recording_stopped = pyqtSignal(str, int)  # filepath, event_count

    def __init__(self) -> None:
        super().__init__()
        self._file = None
        self._path = ""
        self._count = 0
        self._start_ts = 0.0

        bus.location_received.connect(lambda p: self._write("groundeye/location", p))
        bus.status_received.connect(lambda p: self._write("groundeye/status", p))
        bus.mqtt_event_received.connect(lambda p: self._write("groundeye/event", p))

    @property
    def is_recording(self) -> bool:
        return self._file is not None

    def start(self) -> str:
        if self.is_recording:
            return self._path
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        name = datetime.now().strftime("groundeye_%Y%m%d_%H%M%S.jsonl")
        self._path = str(RECORDINGS_DIR / name)
        self._file = open(self._path, "w", encoding="utf-8")
        self._count = 0
        self._start_ts = time.monotonic()
        self.recording_started.emit(self._path)
        return self._path

    def stop(self) -> None:
        if not self.is_recording:
            return
        self._file.close()
        self._file = None
        self.recording_stopped.emit(self._path, self._count)

    def _write(self, topic: str, payload: dict) -> None:
        if not self.is_recording:
            return
        ts_ms = int((time.monotonic() - self._start_ts) * 1000)
        line = json.dumps({"ts_ms": ts_ms, "topic": topic, "payload": payload})
        self._file.write(line + "\n")
        self._file.flush()
        self._count += 1


recorder = RecorderService()

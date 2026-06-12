"""MJPEG stream puller + event snapshot fetcher for ESP32-CAM feeds.

CameraWorker    — QThread: pulls one MJPEG stream, emits raw JPEG bytes per frame.
SnapshotWorker  — QThread: fetches a single /snapshot JPEG and saves it to disk.
CameraManager   — Singleton driven by bus signals; manages workers and auto-snapshots.
"""
import socket
from pathlib import Path
from urllib.request import urlopen

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from pyqt_app.services.bus import bus

# Directory where event snapshots are saved (relative to project root)
_SNAPSHOT_DIR = Path(__file__).parents[2] / "recordings" / "snapshots"


# ─── MJPEG stream worker ──────────────────────────────────────────────────────

class CameraWorker(QThread):
    """Pulls an MJPEG stream; emits one signal per JPEG frame."""
    frame_ready = pyqtSignal(str, bytes)   # node_id, jpeg bytes
    error       = pyqtSignal(str, str)     # node_id, message

    _CHUNK = 4096
    _MAX_FRAME = 512 * 1024  # 512 KB safety cap per frame

    def __init__(self, node_id: str, host: str, port: int, path: str = "/stream"):
        super().__init__()
        self.node_id = node_id
        self.host    = host
        self.port    = port
        self.path    = path
        self._stop   = False

    def stop(self):
        self._stop = True
        self.wait(2000)

    def run(self):
        try:
            self._stream()
        except Exception as exc:
            if not self._stop:
                self.error.emit(self.node_id, str(exc))

    def _stream(self):
        sock = socket.create_connection((self.host, self.port), timeout=5)
        sock.settimeout(10)

        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Connection: close\r\n\r\n"
        )
        sock.sendall(request.encode())

        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(self._CHUNK)
            if not chunk:
                return
            buf += chunk

        buf = buf[buf.index(b"\r\n\r\n") + 4:]

        while not self._stop:
            buf += self._recv_until(sock, b"\xff\xd8", buf)
            while not self._stop:
                soi = buf.find(b"\xff\xd8")
                if soi == -1:
                    break
                eoi = buf.find(b"\xff\xd9", soi + 2)
                if eoi == -1:
                    chunk = sock.recv(self._CHUNK)
                    if not chunk:
                        return
                    buf += chunk
                    continue
                jpeg = buf[soi: eoi + 2]
                buf  = buf[eoi + 2:]
                if len(jpeg) <= self._MAX_FRAME:
                    self.frame_ready.emit(self.node_id, bytes(jpeg))
                break

        sock.close()

    def _recv_until(self, sock: socket.socket, marker: bytes, existing: bytes) -> bytes:
        received = b""
        while marker not in (existing + received) and not self._stop:
            chunk = sock.recv(self._CHUNK)
            if not chunk:
                return received
            received += chunk
        return received


# ─── Snapshot worker ──────────────────────────────────────────────────────────

class SnapshotWorker(QThread):
    """Fetches one JPEG snapshot from a URL and saves it to disk."""
    done   = pyqtSignal(str, str)  # event_id, saved filepath
    failed = pyqtSignal(str, str)  # event_id, error message

    def __init__(self, event_id: str, url: str, save_path: str):
        super().__init__()
        self.event_id  = event_id
        self.url       = url
        self.save_path = save_path

    def run(self):
        try:
            with urlopen(self.url, timeout=5) as resp:
                data = resp.read()
            if not data.startswith(b"\xff\xd8"):
                raise ValueError("response is not a JPEG")
            Path(self.save_path).write_bytes(data)
            self.done.emit(self.event_id, self.save_path)
        except Exception as exc:
            self.failed.emit(self.event_id, str(exc))


# ─── Manager (main-thread singleton) ─────────────────────────────────────────

class CameraManager(QObject):
    """Tracks discovered cameras, manages stream workers, and auto-snapshots events."""

    def __init__(self):
        super().__init__()
        self._workers:          dict[str, CameraWorker]   = {}
        self._snap_workers:     dict[str, SnapshotWorker] = {}
        self._cameras:          dict[str, tuple[str, int]] = {}  # node_id → (ip, port)

        bus.camera_discovered.connect(self._on_discovered)
        bus.event_received.connect(self._on_event)

    # ------------------------------------------------------------------
    # Camera discovery
    # ------------------------------------------------------------------

    def _on_discovered(self, payload: dict):
        node_id = payload.get("node_id", "")
        online  = payload.get("online", False)

        if online:
            ip   = payload.get("ip", "")
            port = int(payload.get("port", 80))
            if node_id and ip:
                self._cameras[node_id] = (ip, port)
                self._start_stream(node_id, ip, port)
        else:
            self._cameras.pop(node_id, None)
            self._stop_stream(node_id)

    def _start_stream(self, node_id: str, ip: str, port: int):
        self._stop_stream(node_id)
        w = CameraWorker(node_id, ip, port)
        w.frame_ready.connect(bus.camera_frame)
        w.error.connect(lambda nid, msg: bus.toast.emit(
            "warn", f"Camera {nid}", msg, ""))
        # Keep Python ref alive until thread is done, then let Qt clean up
        w.finished.connect(lambda nid=node_id: self._workers.pop(nid, None))
        w.finished.connect(w.deleteLater)
        self._workers[node_id] = w
        w.start()

    def _stop_stream(self, node_id: str):
        w = self._workers.get(node_id)
        if w:
            w.stop()  # waits up to 2 s; finished signal fires afterward

    # ------------------------------------------------------------------
    # Auto-snapshot on event
    # ------------------------------------------------------------------

    def _on_event(self, event) -> None:
        # Skip if a snapshot is already in flight for this event
        if event.id in self._snap_workers:
            return

        from pyqt_app.services import settings as cfg
        url = cfg.load().get("snapshot_url", "")
        if not url:
            return

        _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        save_path = str(_SNAPSHOT_DIR / f"{event.id}.jpg")

        w = SnapshotWorker(event.id, url, save_path)
        w.done.connect(self._on_snap_done)
        w.failed.connect(lambda eid, msg: bus.toast.emit(
            "warn", "Snapshot failed", msg, ""))
        w.finished.connect(lambda eid=event.id: self._snap_workers.pop(eid, None))
        w.finished.connect(w.deleteLater)
        self._snap_workers[event.id] = w
        w.start()

    def _on_snap_done(self, event_id: str, filepath: str):
        from pyqt_app.services.store import store
        ev = store.event(event_id)
        if ev:
            ev.photo_path = filepath
        bus.event_photo_saved.emit(event_id, filepath)
        # Reference removed by finished signal, not here

    # ------------------------------------------------------------------

    def stop_all(self):
        for nid in list(self._workers):
            self._stop_stream(nid)

    def active_ids(self) -> list[str]:
        return list(self._workers.keys())


_manager: CameraManager | None = None


def start() -> CameraManager:
    global _manager
    if _manager is None:
        _manager = CameraManager()
    return _manager

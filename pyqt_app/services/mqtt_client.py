"""MQTT integration: connection bridge + business-logic handler.

MqttBridge   — wraps paho-mqtt; emits Qt signals from its background thread
               (PyQt6 queues cross-thread signals automatically).
MqttHandler  — processes location/status payloads; updates store + bus.
"""
import json
import logging
import threading
import time
from collections import deque
from datetime import datetime

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

import paho.mqtt.client as mqtt

from pyqt_app.services.bus import bus
from pyqt_app.services import settings as cfg

logger = logging.getLogger(__name__)

TOPICS = ["groundeye/location", "groundeye/status", "groundeye/event", "groundeye/camera"]
STREAM_TOPIC_PREFIX = "groundeye/stream/"  # binary int16 batches from ESP
HEARTBEAT_TIMEOUT = 30.0  # seconds before node → offline
RMS_MAX = 300.0            # normalise rms_energy to 0..1
_live_counter = 0


def rssi_to_bars(dbm: int) -> int:
    if dbm >= -65:
        return 4
    if dbm >= -75:
        return 3
    if dbm >= -85:
        return 2
    if dbm >= -95:
        return 1
    return 0


# ---------------------------------------------------------------------------
# MQTT connection bridge
# ---------------------------------------------------------------------------

class MqttBridge(QObject):
    """Thin wrapper around paho-mqtt.  All signals are safe to connect from
    main-thread receivers — PyQt6 uses QueuedConnection automatically."""

    # Internal relay signals (paho thread → main thread)
    _sig_location = pyqtSignal(dict)
    _sig_status = pyqtSignal(dict)
    _sig_event = pyqtSignal(dict)
    _sig_camera = pyqtSignal(dict)
    _sig_connected = pyqtSignal(str, int)
    _sig_disconnected = pyqtSignal()
    _sig_stream      = pyqtSignal(str, object)  # mqtt_node_id, np.ndarray
    _sig_stream_meta = pyqtSignal(str, object)  # mqtt_node_id, epoch_ms (64-bit int)

    def __init__(self) -> None:
        super().__init__()
        self._client: mqtt.Client | None = None
        self._host = ""
        self._port = 1883
        self._lock = threading.Lock()

        # Wire internal relay → public bus signals
        self._sig_location.connect(bus.location_received)
        self._sig_status.connect(bus.status_received)
        self._sig_event.connect(bus.mqtt_event_received)
        self._sig_camera.connect(bus.camera_discovered)
        self._sig_connected.connect(bus.mqtt_connected)
        self._sig_disconnected.connect(bus.mqtt_disconnected)
        self._sig_stream.connect(bus.stream_received)
        self._sig_stream_meta.connect(bus.stream_meta_received)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect_broker(self, host: str, port: int) -> None:
        self.disconnect_broker()
        self._host = host
        self._port = port
        t = threading.Thread(target=self._run, daemon=True, name="mqtt-thread")
        t.start()

    def disconnect_broker(self) -> None:
        with self._lock:
            c = self._client
            self._client = None
        if c:
            try:
                c.disconnect()
                c.loop_stop()
            except Exception:
                pass

    def is_connected(self) -> bool:
        return self._client is not None

    # ------------------------------------------------------------------
    # paho internals (run in mqtt thread)
    # ------------------------------------------------------------------

    def _run(self) -> None:
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        except AttributeError:
            client = mqtt.Client()  # paho < 2.0 fallback

        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message

        with self._lock:
            self._client = client

        try:
            client.connect(self._host, self._port, keepalive=60)
            client.loop_forever()
        except Exception as exc:
            logger.warning("MQTT connect failed: %s", exc)
            with self._lock:
                if self._client is client:
                    self._client = None
            self._sig_disconnected.emit()

    def _on_connect(self, client, userdata, flags, reason_code, *args):
        failed = getattr(reason_code, "is_failure", None)
        if failed is None:
            failed = (reason_code != 0)
        if failed:
            logger.warning("MQTT connect refused: %s", reason_code)
            self._sig_disconnected.emit()
            return
        for topic in TOPICS:
            client.subscribe(topic)
        client.subscribe(STREAM_TOPIC_PREFIX + "+")
        client.subscribe("groundeye/stream_meta/+")
        self._sig_connected.emit(self._host, self._port)

    def _on_disconnect(self, client, userdata, *args):
        self._sig_disconnected.emit()

    def _on_message(self, client, userdata, message):
        import numpy as np
        topic = message.topic

        # Binary int16 audio stream — handle before JSON decode
        if topic.startswith(STREAM_TOPIC_PREFIX):
            node_id = topic[len(STREAM_TOPIC_PREFIX):]
            try:
                # Divide by sensor practical peak (~3000 int16 units) so displayed
                # values fill the -1..1 range; clip for rare over-range spikes
                samples = np.frombuffer(message.payload, dtype=np.int16).astype(np.float32) / 3000.0
                samples = np.clip(samples, -1.0, 1.0)
                if samples.size:
                    self._sig_stream.emit(node_id, samples)
            except Exception:
                pass
            return

        # stream_meta — JSON with ESP32 NTP epoch for the upcoming batch
        if topic.startswith("groundeye/stream_meta/"):
            node_id = topic[len("groundeye/stream_meta/"):]
            try:
                meta = json.loads(message.payload.decode())
                lo = meta.get("epoch_ms", 0)
                hi = meta.get("epoch_ms_high", 0)
                epoch_ms = int((hi << 32) | lo)
                if epoch_ms > 0:
                    self._sig_stream_meta.emit(node_id, epoch_ms)
            except Exception:
                pass
            return

        try:
            payload = json.loads(message.payload.decode())
        except Exception:
            return
        if topic == "groundeye/location":
            self._sig_location.emit(payload)
        elif topic == "groundeye/status":
            self._sig_status.emit(payload)
        elif topic == "groundeye/event":
            self._sig_event.emit(payload)
        elif topic == "groundeye/camera":
            self._sig_camera.emit(payload)


# ---------------------------------------------------------------------------
# Business-logic handler (runs entirely in main thread via signals)
# ---------------------------------------------------------------------------

class MqttHandler(QObject):
    """Converts raw MQTT payloads into store updates and bus signals."""

    def __init__(self) -> None:
        super().__init__()
        # last heartbeat timestamp per mqtt node_id
        self._heartbeats: dict[str, float] = {}
        # rolling raw sample buffer per mqtt node_id (float32, -1..1)
        self._stream_bufs: dict[str, deque] = {}
        # last ESP32 epoch_ms seen for each node (from stream_meta)
        self._stream_epoch: dict[str, int] = {}
        # timed batches: deque of (epoch_ms_start, samples) — last ~6 s per node
        self._timed_batches: dict[str, deque] = {}

        self._hb_timer = QTimer(self)
        self._hb_timer.setInterval(5000)
        self._hb_timer.timeout.connect(self._check_heartbeats)
        self._hb_timer.start()

        bus.location_received.connect(self._on_location)
        bus.status_received.connect(self._on_status)
        bus.stream_received.connect(self._on_stream)
        bus.stream_meta_received.connect(self._on_stream_meta)
        bus.mqtt_disconnected.connect(self._on_disconnected)
        bus.mqtt_connected.connect(self._on_connected_toast)

    # ------------------------------------------------------------------
    # Raw stream buffer — keeps last 4000 samples per node
    # ------------------------------------------------------------------

    def _on_stream_meta(self, mqtt_id: str, epoch_ms) -> None:
        self._stream_epoch[mqtt_id] = int(epoch_ms)

    def _on_stream(self, mqtt_id: str, samples) -> None:
        # Simple rolling buffer (live display)
        buf = self._stream_bufs.get(mqtt_id)
        if buf is None:
            buf = deque(maxlen=4000)
            self._stream_bufs[mqtt_id] = buf
        buf.extend(samples.tolist())

        # Timed batch (event waveform capture) — maxlen=150 ≈ 6 s at ~25 batches/s
        epoch_ms = self._stream_epoch.get(mqtt_id, 0)
        if epoch_ms > 0:
            timed = self._timed_batches.get(mqtt_id)
            if timed is None:
                timed = deque(maxlen=150)
                self._timed_batches[mqtt_id] = timed
            timed.append((epoch_ms, samples.copy()))

    def _capture_waveform(self, mqtt_id: str, event_ts_ms: int = 0, n: int = 240) -> list:
        """Slice timed batch buffer around event_ts_ms, downsample to n points.
        Values are already scaled by /3000 in the bridge — no extra normalisation."""
        import numpy as np
        from pyqt_app.models.event import make_waveform

        FS = 2000
        HALF_WIN_MS = 1000  # ±1 s window around the event

        timed = self._timed_batches.get(mqtt_id)
        if timed and event_ts_ms > 0:
            t0 = event_ts_ms - HALF_WIN_MS
            t1 = event_ts_ms + HALF_WIN_MS
            segments = []
            for (batch_start, batch_samples) in timed:
                batch_end = batch_start + len(batch_samples) * 1000 / FS
                if batch_end >= t0 and batch_start <= t1:
                    segments.append((batch_start, batch_samples))
            if segments:
                segments.sort(key=lambda x: x[0])
                arr = np.concatenate([s for _, s in segments])
                if len(arr) >= n // 4:
                    idx = np.linspace(0, len(arr) - 1, n, dtype=int)
                    return arr[idx].tolist()

        # Fallback: latest buffer, raw scale
        buf = self._stream_bufs.get(mqtt_id)
        if buf and len(buf) >= n // 4:
            arr = np.array(buf, dtype=np.float32)
            idx = np.linspace(0, len(arr) - 1, n, dtype=int)
            return arr[idx].tolist()

        return make_waveform(n, 0.5, 40)

    # ------------------------------------------------------------------
    # groundeye/location
    # ------------------------------------------------------------------

    def _on_location(self, payload: dict) -> None:
        from pyqt_app.services.store import store
        from pyqt_app.models.event import Event, make_waveform

        global _live_counter
        _live_counter += 1

        # Update signal levels for participating nodes
        for node_info in payload.get("nodes", []):
            node = store.node_by_mqtt_id(node_info.get("node_id", ""))
            if node:
                rms = node_info.get("rms_energy", 0.0)
                node.signal = min(1.0, rms / RMS_MAX)
                if node.status not in ("offline", "connecting"):
                    node.status = "triggered"
                bus.node_updated.emit(node)

        # Create an Event for the feed / events table
        nearest = payload.get("nearest_node", "")
        nid = _mqtt_to_store_id(nearest)
        confidence = payload.get("confidence", 0.5)
        severity = "high" if confidence >= 0.7 else "med" if confidence >= 0.4 else "info"
        best_method = payload.get("best_method", "amplitude")
        ts_ms = payload.get("timestamp_ms", 0)
        ts_dt = datetime.fromtimestamp(ts_ms / 1000.0) if ts_ms else datetime.now()
        ts_str = ts_dt.strftime("%H:%M:%S.") + f"{ts_dt.microsecond // 1000:03d}"
        date_str = ts_dt.strftime("%Y-%m-%d")

        # Capture waveform for every participating node
        node_waveforms = {}
        for node_info in payload.get("nodes", []):
            mid = node_info.get("node_id", "")
            sid = _mqtt_to_store_id(mid)
            if sid:
                node_waveforms[sid] = self._capture_waveform(mid, event_ts_ms=ts_ms)

        ev = Event(
            id=f"LIVE-{_live_counter:04d}",
            ts=ts_str,
            date=date_str,
            node_id=nid or "N01",
            severity=severity,
            amplitude=confidence,
            duration=0.0,
            distance=payload.get("est_dist_m", 0.0),
            tag=best_method,
            waveform=node_waveforms.get(nid or "N01", self._capture_waveform(nearest, event_ts_ms=ts_ms)),
            node_waveforms=node_waveforms,
        )
        store.add_event(ev)
        bus.event_received.emit(ev)

    # ------------------------------------------------------------------
    # groundeye/status
    # ------------------------------------------------------------------

    def _on_status(self, payload: dict) -> None:
        from pyqt_app.services.store import store

        mqtt_id = payload.get("node_id", "")
        node = store.node_by_mqtt_id(mqtt_id)
        if not node:
            return

        self._heartbeats[mqtt_id] = time.monotonic()

        status_str = payload.get("status", "online").lower()
        if status_str not in ("online", "triggered", "offline", "connecting"):
            status_str = "online"
        node.status = status_str

        rssi_dbm = payload.get("rssi", -80)
        node.rssi = rssi_to_bars(rssi_dbm)
        node.rssi_dbm = rssi_dbm

        bus.node_updated.emit(node)

    # ------------------------------------------------------------------
    # Heartbeat watchdog
    # ------------------------------------------------------------------

    def _on_connected_toast(self, host: str, port: int) -> None:
        bus.toast.emit("info", "MQTT Connected", f"{host}:{port}", "")

    def _on_disconnected(self) -> None:
        from pyqt_app.services.store import store
        self._heartbeats.clear()
        for node in store.nodes:
            if node.status != "offline":
                node.status = "offline"
                node.signal = 0.0
                bus.node_updated.emit(node)
        bus.toast.emit("warn", "MQTT Disconnected", "No broker connection", "")

    def _check_heartbeats(self) -> None:
        from pyqt_app.services.store import store

        now = time.monotonic()
        for mqtt_id, last in list(self._heartbeats.items()):
            if now - last > HEARTBEAT_TIMEOUT:
                node = store.node_by_mqtt_id(mqtt_id)
                if node and node.status != "offline":
                    node.status = "offline"
                    bus.node_updated.emit(node)


def _mqtt_to_store_id(mqtt_id: str) -> str:
    from pyqt_app.services.store import MQTT_NODE_MAP
    return MQTT_NODE_MAP.get(mqtt_id, "")


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

bridge: MqttBridge | None = None
handler: MqttHandler | None = None


def start(host: str | None = None, port: int | None = None) -> None:
    """Create singletons and attempt connection with stored/given settings."""
    global bridge, handler
    if handler is None:
        handler = MqttHandler()
    if bridge is None:
        bridge = MqttBridge()

    s = cfg.load()
    h = host or s["broker_host"]
    p = port or s["broker_port"]
    bridge.connect_broker(h, p)


def stop() -> None:
    if bridge:
        bridge.disconnect_broker()

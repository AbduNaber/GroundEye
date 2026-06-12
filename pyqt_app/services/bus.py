"""Qt signal bus for app-wide events."""
from PyQt6.QtCore import QObject, pyqtSignal


class Bus(QObject):
    theme_changed = pyqtSignal(str)
    event_received = pyqtSignal(object)       # Event
    sample_received = pyqtSignal(str, float)  # node_id, amp
    node_updated = pyqtSignal(object)         # Node
    node_selected = pyqtSignal(str)           # node_id
    event_opened = pyqtSignal(object)         # Event
    event_acked = pyqtSignal(str)             # event_id
    toast = pyqtSignal(str, str, str, str)    # kind, title, body, meta

    # MQTT signals
    location_received = pyqtSignal(dict)      # groundeye/location payload
    status_received = pyqtSignal(dict)        # groundeye/status payload
    mqtt_event_received = pyqtSignal(dict)    # groundeye/event payload
    mqtt_connected = pyqtSignal(str, int)     # host, port
    mqtt_disconnected = pyqtSignal()
    stream_received      = pyqtSignal(str, object) # mqtt_node_id, np.ndarray float32 -1..1
    stream_meta_received = pyqtSignal(str, object)  # mqtt_node_id, epoch_ms int (64-bit)

    # Recorder / player signals
    recording_started = pyqtSignal(str)       # filepath
    recording_stopped = pyqtSignal(str, int)  # filepath, count
    playback_reset = pyqtSignal()             # clear transient state before replay

    # Camera signals
    camera_discovered = pyqtSignal(dict)      # {"node_id":..., "ip":..., "port":..., "online":...}
    camera_frame = pyqtSignal(str, bytes)     # node_id, jpeg_bytes
    event_photo_saved = pyqtSignal(str, str)  # event_id, absolute filepath


bus = Bus()

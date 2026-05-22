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


bus = Bus()

from dataclasses import dataclass, field


@dataclass
class Node:
    id: str
    name: str
    label: str
    x: float          # 0..1 map coord
    y: float          # 0..1 map coord
    lat: float = 0.0
    lon: float = 0.0
    status: str = "online"    # online | triggered | offline | connecting
    rssi: int = 4             # 0..4
    battery: float = 1.0      # 0..1
    temp: float = 12.0
    threshold: float = 0.38
    signal: float = 0.1
    last_trigger: str = "—"
    firmware: str = "gev-0.4.2"
    uptime: str = "3d 04:18"
    mac: str = "00:00:00:00:00:00"
    connected: str = "2026-04-17 09:02"
    detection_radius: int = 10
    rssi_dbm: int = -60       # raw dBm value from groundeye/status

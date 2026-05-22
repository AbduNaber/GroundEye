"""In-memory store + seeded mock data."""
from typing import List, Optional
from pyqt_app.models.node import Node
from pyqt_app.models.event import Event, make_waveform


def _seed_nodes() -> List[Node]:
    return [
        Node(id="N01", name="NODE-01", label="North Perimeter",
             x=0.22, y=0.32, lat=40.81236, lon=29.35912,
             status="online", rssi=4, battery=0.86, temp=12.4,
             threshold=0.38, signal=0.12, last_trigger="14:22:07",
             mac="34:85:18:AA:12:01"),
        Node(id="N02", name="NODE-02", label="East Gate",
             x=0.58, y=0.44, lat=40.81194, lon=29.35978,
             status="triggered", rssi=4, battery=0.72, temp=13.1,
             threshold=0.38, signal=0.81, last_trigger="14:31:52",
             mac="34:85:18:AA:12:02"),
        Node(id="N03", name="NODE-03", label="South Ridge",
             x=0.78, y=0.72, lat=40.81144, lon=29.36024,
             status="online", rssi=3, battery=0.44, temp=11.8,
             threshold=0.38, signal=0.22, last_trigger="13:58:11",
             mac="34:85:18:AA:12:03"),
    ]


def _seed_events() -> List[Event]:
    data = [
        ("EV-2614", "14:31:52.402", "2026-04-19", "N02", "high", 0.81, 1.34, 6.2, False, False, "subject-1", 0.82, 42, "Strong bipedal gait signature, 2.1 Hz dominant."),
        ("EV-2613", "14:28:14.918", "2026-04-19", "N02", "med",  0.54, 0.82, 8.9, False, False, "subject-2", 0.56, 28, ""),
        ("EV-2612", "14:22:07.330", "2026-04-19", "N01", "high", 0.77, 1.12, 7.4, True,  False, "subject-3", 0.77, 38, ""),
        ("EV-2611", "14:18:02.812", "2026-04-19", "N03", "med",  0.49, 0.64, 9.1, True,  False, "empty",     0.48, 22, ""),
        ("EV-2610", "13:58:11.104", "2026-04-19", "N03", "info", 0.41, 0.28, 9.8, True,  False, "wildlife",  0.42, 18, ""),
        ("EV-2609", "13:42:57.022", "2026-04-19", "N01", "high", 0.83, 1.52, 5.8, True,  False, "subject-4", 0.85, 48, ""),
        ("EV-2608", "02:18:42.901", "2026-04-19", "N02", "med",  0.58, 0.96, 7.7, True,  True,  "subject-5", 0.60, 30, ""),
        ("EV-2607", "01:44:08.204", "2026-04-19", "N03", "info", 0.39, 0.32, 9.4, True,  True,  "wildlife",  0.40, 16, ""),
        ("EV-2606", "23:12:55.780", "2026-04-18", "N01", "high", 0.79, 1.24, 6.9, True,  True,  "subject-6", 0.80, 40, ""),
        ("EV-2605", "22:08:21.412", "2026-04-18", "N02", "med",  0.52, 0.74, 8.4, True,  True,  "subject-7", 0.55, 26, ""),
        ("EV-2604", "21:34:10.006", "2026-04-18", "N03", "high", 0.76, 1.18, 6.4, True,  True,  "subject-8", 0.78, 36, ""),
        ("EV-2603", "20:22:44.112", "2026-04-18", "N01", "info", 0.36, 0.22, 9.6, True,  True,  "empty",     0.38, 14, ""),
    ]
    out: List[Event] = []
    for row in data:
        (eid, ts, d, nid, sev, amp, dur, dist, ack, night, tag, wfpk, wfat, note) = row
        out.append(Event(
            id=eid, ts=ts, date=d, node_id=nid, severity=sev,
            amplitude=amp, duration=dur, distance=dist,
            ack=ack, night=night, tag=tag,
            waveform=make_waveform(240, wfpk, wfat),
            notes=note,
        ))
    return out


class Store:
    def __init__(self):
        self.nodes: List[Node] = _seed_nodes()
        self.events: List[Event] = _seed_events()
        self.paths = [
            {"id": "PATH-14", "label": "Track 14",
             "hits": [("N01", "14:22:07"), ("N02", "14:28:14"), ("N02", "14:31:52")],
             "active": True},
        ]

    def node(self, nid: str) -> Optional[Node]:
        return next((n for n in self.nodes if n.id == nid), None)

    def event(self, eid: str) -> Optional[Event]:
        return next((e for e in self.events if e.id == eid), None)

    def open_events(self) -> int:
        return sum(1 for e in self.events if not e.ack)

    def ack(self, eid: str):
        e = self.event(eid)
        if e:
            e.ack = True


store = Store()

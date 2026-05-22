from dataclasses import dataclass, field
from typing import List
import math


@dataclass
class Event:
    id: str
    ts: str                # HH:MM:SS.fff
    date: str              # YYYY-MM-DD
    node_id: str
    severity: str          # high | med | info
    amplitude: float
    duration: float
    distance: float
    ack: bool = False
    night: bool = False
    tag: str = ""          # subject-N | wildlife | empty
    waveform: List[float] = field(default_factory=list)
    notes: str = ""


def make_waveform(samples: int = 240, peak: float = 0.8, peak_at_pct: int = 42) -> List[float]:
    out = []
    peak_at = int(samples * peak_at_pct / 100)
    for i in range(samples):
        v = (math.sin(i * 0.7) + math.sin(i * 1.9 + 0.5) * 0.6) * 0.04
        d = i - peak_at
        env = math.exp(-((d * d) / (samples * 0.8)))
        osc = (
            math.sin(i * 0.55)
            + math.sin(i * 1.1 + 0.3) * 0.7
            + math.sin(i * 2.2 + 1.1) * 0.4
        )
        v += osc * env * peak
        v += math.sin(i * 9.1 + 3) * 0.03
        out.append(v)
    return out

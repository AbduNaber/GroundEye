"""Node layout — physical positions and field dimensions.

Backed by layout.json at the project root.  Any UI component or the DSP
config can read from there as the single source of truth.

layout.json structure:
  {
    "field": {"width_m": 3.0, "height_m": 2.6},
    "nodes": [
      {"id": "node-1", "store_id": "N01", "x_m": 0.0, "y_m": 0.0},
      ...
    ]
  }
"""
import json
from pathlib import Path
from dataclasses import dataclass

_PATH = Path(__file__).parent.parent.parent / "layout.json"

_DEFAULTS: dict = {
    "field": {"width_m": 3.0, "height_m": 2.6},
    "nodes": [
        {"id": "node-1", "store_id": "N01", "x_m": 0.0, "y_m": 0.0},
        {"id": "node-2", "store_id": "N02", "x_m": 3.0, "y_m": 0.0},
        {"id": "node-3", "store_id": "N03", "x_m": 1.5, "y_m": 2.6},
    ],
}


@dataclass
class NodeLayout:
    id: str        # MQTT id e.g. "node-1"
    store_id: str  # UI store id e.g. "N01"
    x_m: float     # physical x in metres
    y_m: float     # physical y in metres
    x: float       # normalised 0..1
    y: float       # normalised 0..1


@dataclass
class FieldLayout:
    width_m: float
    height_m: float
    nodes: list  # list[NodeLayout]

    def node_by_id(self, mqtt_id: str) -> "NodeLayout | None":
        return next((n for n in self.nodes if n.id == mqtt_id), None)

    def node_by_store_id(self, store_id: str) -> "NodeLayout | None":
        return next((n for n in self.nodes if n.store_id == store_id), None)


def load() -> FieldLayout:
    """Load layout.json; fall back to defaults if missing or invalid."""
    try:
        data = json.loads(_PATH.read_text())
    except Exception:
        data = _DEFAULTS

    field = data.get("field", _DEFAULTS["field"])
    w = float(field.get("width_m", 3.0))
    h = float(field.get("height_m", 2.6))

    nodes = []
    for entry in data.get("nodes", _DEFAULTS["nodes"]):
        x_m = float(entry.get("x_m", 0.0))
        y_m = float(entry.get("y_m", 0.0))
        nodes.append(NodeLayout(
            id=entry["id"],
            store_id=entry["store_id"],
            x_m=x_m,
            y_m=y_m,
            x=x_m / w if w else 0.0,
            y=y_m / h if h else 0.0,
        ))

    return FieldLayout(width_m=w, height_m=h, nodes=nodes)


def save(field: FieldLayout) -> None:
    data = {
        "field": {"width_m": field.width_m, "height_m": field.height_m},
        "nodes": [
            {
                "id": n.id,
                "store_id": n.store_id,
                "x_m": n.x_m,
                "y_m": n.y_m,
            }
            for n in field.nodes
        ],
    }
    _PATH.write_text(json.dumps(data, indent=2))

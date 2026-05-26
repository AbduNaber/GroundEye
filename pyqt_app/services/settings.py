"""Persistent settings backed by settings.json at project root."""
import json
from pathlib import Path

_PATH = Path(__file__).parent.parent.parent / "settings.json"

_DEFAULTS: dict = {
    "broker_host": "100.83.35.127",
    "broker_port": 1883,
}


def load() -> dict:
    try:
        data = json.loads(_PATH.read_text())
        return {**_DEFAULTS, **data}
    except Exception:
        return dict(_DEFAULTS)


def save(updates: dict) -> None:
    current = load()
    current.update(updates)
    _PATH.write_text(json.dumps(current, indent=2))

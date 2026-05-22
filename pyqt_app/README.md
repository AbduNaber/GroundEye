# GroundEye · Ground Station (PyQt6)

A runnable PyQt6 port of the GroundEye tactical ops-center UI. All data is mocked
in `services/mock_stream.py` so you can run and click through the whole UI before
wiring up MQTT + camera.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Project layout

```
pyqt_app/
├── main.py                # QApplication + MainWindow + theme loader
├── themes/
│   ├── dark.qss
│   ├── light.qss
│   └── tactical.qss
├── models/
│   ├── node.py            # Node dataclass
│   └── event.py           # Event dataclass + waveform generator
├── services/
│   ├── bus.py             # Qt signal bus (theme, toasts, selection)
│   ├── store.py           # In-memory store of nodes + events
│   └── mock_stream.py     # QTimer-driven "live" stream: triggers, signal jitter
├── widgets/
│   ├── titlebar.py        # Window chrome + brand + status pills
│   ├── tabs.py            # Custom tactical tab bar + QStackedWidget
│   ├── statusbar.py
│   ├── field_map.py       # QGraphicsView field map w/ pins, radii, tracks
│   ├── node_card.py       # Node card with signal bar, RSSI, battery
│   ├── event_ticker.py    # Scrolling list of recent events
│   ├── strip.py           # Bottom recent-captures strip
│   ├── events_table.py    # Filterable events table
│   ├── signals_view.py    # pyqtgraph live waveforms per node
│   ├── gallery.py         # Thumbnail grid
│   ├── event_dialog.py    # Event detail modal
│   ├── toast.py           # Bottom-right toast manager
│   ├── photo.py           # Stylized photo placeholder (QWidget paintEvent)
│   ├── signal_bar.py      # Horizontal bar w/ threshold marker
│   ├── rssi.py            # 4-bar RSSI indicator
│   └── waveform_mini.py   # Small detail waveform for the event dialog
└── requirements.txt
```

## Wiring real MQTT + camera

- Replace `services/mock_stream.py` with a `paho-mqtt` worker on a `QThread`.
- Emit `bus.event_received` / `bus.sample_received` from that worker.
- Point `Photo` at a real JPEG path (`QPixmap(path)`) when an event arrives.

## Themes

Switch theme programmatically:

```python
from main import set_theme
set_theme("tactical")   # or "dark", "light"
```

(Or press `Ctrl+T` to cycle themes while the app is running.)

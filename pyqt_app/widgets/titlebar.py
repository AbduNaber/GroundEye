"""Frameless-ish titlebar with brand + status pills."""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QWidget,
    QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QDialogButtonBox, QPushButton, QSpinBox,
)
from datetime import datetime
from pyqt_app.services.bus import bus
from pyqt_app.services import settings as cfg
from pyqt_app.services.recorder import recorder


class WinDot(QWidget):
    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(12, 12)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(self.color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(0, 0, 12, 12)


class BrandMark(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(18, 18)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QColor("#d4a84b"))
        p.drawEllipse(1, 1, 16, 16)
        p.setBrush(QColor("#d4a84b"))
        p.drawEllipse(6, 6, 6, 6)


class StatusDot(QWidget):
    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(6, 6)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(self.color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(0, 0, 6, 6)


def status_pill(color: str, text: str) -> QLabel:
    lbl = QLabel(f"●  {text}")
    lbl.setObjectName("statusPill")
    lbl.setStyleSheet(
        f"color: #8b96a1; border: 1px solid #2e3842; padding: 3px 8px; "
        f"border-radius: 3px; font-family: 'JetBrains Mono'; font-size: 10px;"
    )
    return lbl


# ---------------------------------------------------------------------------
# Broker settings dialog
# ---------------------------------------------------------------------------

class BrokerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MQTT Broker Settings")
        self.setMinimumWidth(340)
        self.setModal(True)

        s = cfg.load()

        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(8)

        self._host = QLineEdit(s["broker_host"])
        self._host.setPlaceholderText("192.168.4.1")
        form.addRow("Broker Host:", self._host)

        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(s["broker_port"])
        form.addRow("Port:", self._port)

        lay.addLayout(form)

        self._status_lbl = QLabel("●  DISCONNECTED")
        self._status_lbl.setStyleSheet(
            "color: #d4a84b; font-family: 'JetBrains Mono'; font-size: 10px;"
        )
        lay.addWidget(self._status_lbl)

        btns = QDialogButtonBox()
        self._connect_btn = btns.addButton("Connect", QDialogButtonBox.ButtonRole.AcceptRole)
        self._disconnect_btn = btns.addButton("Disconnect", QDialogButtonBox.ButtonRole.ResetRole)
        btns.addButton("Close", QDialogButtonBox.ButtonRole.RejectRole)
        btns.accepted.connect(self._on_connect)
        btns.rejected.connect(self.reject)
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        lay.addWidget(btns)

        bus.mqtt_connected.connect(self._on_bus_connected)
        bus.mqtt_disconnected.connect(self._on_bus_disconnected)

    def _on_connect(self):
        from pyqt_app.services import mqtt_client
        host = self._host.text().strip() or "192.168.4.1"
        port = self._port.value()
        cfg.save({"broker_host": host, "broker_port": port})
        self._status_lbl.setText("●  CONNECTING…")
        self._status_lbl.setStyleSheet(
            "color: #5a9fb8; font-family: 'JetBrains Mono'; font-size: 10px;"
        )
        mqtt_client.start(host, port)

    def _on_disconnect(self):
        from pyqt_app.services import mqtt_client
        mqtt_client.stop()

    def _on_bus_connected(self, host: str, port: int):
        self._status_lbl.setText(f"●  CONNECTED  ·  {host}:{port}")
        self._status_lbl.setStyleSheet(
            "color: #6fb56a; font-family: 'JetBrains Mono'; font-size: 10px;"
        )

    def _on_bus_disconnected(self):
        self._status_lbl.setText("●  DISCONNECTED")
        self._status_lbl.setStyleSheet(
            "color: #d4a84b; font-family: 'JetBrains Mono'; font-size: 10px;"
        )


# ---------------------------------------------------------------------------
# Clickable MQTT pill button
# ---------------------------------------------------------------------------

class MqttPill(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("mqttPill")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QPushButton#mqttPill {"
            "  color: #8b96a1; border: 1px solid #2e3842; padding: 3px 8px;"
            "  border-radius: 3px; font-family: 'JetBrains Mono'; font-size: 10px;"
            "  background: transparent;"
            "}"
            "QPushButton#mqttPill:hover {"
            "  border-color: #5a9fb8; color: #d8e0e6;"
            "}"
        )
        self._set_disconnected()
        self.clicked.connect(self._open_dialog)

        bus.mqtt_connected.connect(self._on_connected)
        bus.mqtt_disconnected.connect(self._set_disconnected)

    def _set_disconnected(self):
        s = cfg.load()
        self.setText(f"●  MQTT BROKER · {s['broker_host']}:{s['broker_port']}")
        self.setStyleSheet(
            self.styleSheet().replace("color: #6fb56a", "").replace("color: #d4a84b", "")
        )
        self.setStyleSheet(
            "QPushButton#mqttPill {"
            "  color: #d4a84b; border: 1px solid #2e3842; padding: 3px 8px;"
            "  border-radius: 3px; font-family: 'JetBrains Mono'; font-size: 10px;"
            "  background: transparent;"
            "}"
            "QPushButton#mqttPill:hover { border-color: #5a9fb8; color: #d8e0e6; }"
        )

    def _on_connected(self, host: str, port: int):
        self.setText(f"●  MQTT BROKER · {host}:{port}")
        self.setStyleSheet(
            "QPushButton#mqttPill {"
            "  color: #6fb56a; border: 1px solid #2e3842; padding: 3px 8px;"
            "  border-radius: 3px; font-family: 'JetBrains Mono'; font-size: 10px;"
            "  background: transparent;"
            "}"
            "QPushButton#mqttPill:hover { border-color: #5a9fb8; color: #d8e0e6; }"
        )

    def _open_dialog(self):
        dlg = BrokerDialog(self.window())
        dlg.exec()


# ---------------------------------------------------------------------------
# TitleBar
# ---------------------------------------------------------------------------

class RecButton(QPushButton):
    """REC toggle — gray when idle, pulsing red when recording."""

    _IDLE_SS = (
        "QPushButton { color: #8b96a1; border: 1px solid #2e3842; padding: 3px 8px;"
        " border-radius: 3px; font-family: 'JetBrains Mono'; font-size: 10px;"
        " background: transparent; }"
        "QPushButton:hover { border-color: #d86a5b; color: #d8e0e6; }"
    )
    _REC_SS = (
        "QPushButton { color: {c}; border: 1px solid #d86a5b; padding: 3px 8px;"
        " border-radius: 3px; font-family: 'JetBrains Mono'; font-size: 10px;"
        " background: transparent; }"
    )

    def __init__(self, parent=None):
        super().__init__("REC", parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(self._IDLE_SS)
        self.clicked.connect(self._toggle)
        self._blink = False
        self._elapsed = 0
        self._timer = QTimer(self)
        self._timer.setInterval(600)
        self._timer.timeout.connect(self._pulse)
        recorder.recording_started.connect(self._on_started)
        recorder.recording_stopped.connect(self._on_stopped)

    def _toggle(self):
        if recorder.is_recording:
            recorder.stop()
        else:
            recorder.start()

    def _on_started(self, path: str):
        self._elapsed = 0
        self._blink = True
        self._timer.start()
        self._update_label()

    def _on_stopped(self, path: str, count: int):
        self._timer.stop()
        self.setText("REC")
        self.setStyleSheet(self._IDLE_SS)
        bus.toast.emit("info", "Recording saved",
                       f"{count} events · {Path(path).name}", "")

    def _pulse(self):
        self._elapsed += 600
        self._blink = not self._blink
        self._update_label()

    def _update_label(self):
        s = self._elapsed // 1000
        m, s = divmod(s, 60)
        dot = "●" if self._blink else "○"
        self.setText(f"{dot} REC  {m:02d}:{s:02d}")
        color = "#d86a5b" if self._blink else "#8b4040"
        self.setStyleSheet(self._REC_SS.replace("{c}", color))


# lazy import to avoid circular at module load time
from pathlib import Path  # noqa: E402


class TitleBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("titlebar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(10)

        lay.addWidget(WinDot("#d86a5b"))
        lay.addWidget(WinDot("#d4a84b"))
        lay.addWidget(WinDot("#6fb56a"))
        lay.addSpacing(6)
        lay.addWidget(BrandMark())
        brand = QLabel("GROUNDEYE · GROUND STATION")
        brand.setProperty("role", "brand")
        lay.addWidget(brand)

        sep = QFrame()
        sep.setFixedSize(1, 16)
        sep.setStyleSheet("background: #2e3842;")
        lay.addWidget(sep)

        path = QLabel("session://site-a/2026-04-19 · operator op_root")
        path.setProperty("role", "monoTiny")
        lay.addWidget(path)

        lay.addStretch(1)

        lay.addWidget(MqttPill())
        lay.addWidget(status_pill("#d4a84b", "RPi5 · 41°C · LOAD 0.28"))
        lay.addWidget(RecButton())

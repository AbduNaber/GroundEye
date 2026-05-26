"""GroundEye Ground Station — PyQt6 entry point."""
import sys
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut, QFontDatabase
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QStackedWidget
)

from pyqt_app.themes.palette import qss
from pyqt_app.services.bus import bus
from pyqt_app.services.store import store
from pyqt_app.services import mqtt_client
from pyqt_app.widgets.titlebar import TitleBar
from pyqt_app.widgets.tabs import TabsBar
from pyqt_app.widgets.statusbar import StatusBar
from pyqt_app.widgets.dashboard import Dashboard
from pyqt_app.widgets.events_table import EventsTab
from pyqt_app.widgets.signals_view import SignalsTab
from pyqt_app.widgets.gallery import GalleryTab
from pyqt_app.widgets.recordings_tab import RecordingsTab
from pyqt_app.widgets.event_dialog import EventDialog
from pyqt_app.widgets.toast import ToastManager


THEMES = ["dark", "light", "tactical"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GroundEye · Ground Station")
        self.resize(1440, 900)
        self.setMinimumSize(1280, 800)

        root = QWidget(); root.setObjectName("app")
        lay = QVBoxLayout(root); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        lay.addWidget(TitleBar())
        self.tabs = TabsBar(["DASHBOARD", "EVENTS", "SIGNALS", "GALLERY", "RECORDINGS"])
        lay.addWidget(self.tabs)

        self.stack = QStackedWidget()
        self.stack.addWidget(Dashboard())
        self.stack.addWidget(EventsTab())
        self.stack.addWidget(SignalsTab())
        self.stack.addWidget(GalleryTab())
        self.stack.addWidget(RecordingsTab())
        lay.addWidget(self.stack, 1)

        lay.addWidget(StatusBar())

        self.setCentralWidget(root)

        # Badge for open events
        self.tabs.set_badge(1, store.open_events())
        self.tabs.tab_changed.connect(self.stack.setCurrentIndex)

        # Event dialog trigger
        bus.event_opened.connect(self._open_event)
        bus.event_acked.connect(lambda _: self.tabs.set_badge(1, store.open_events()))

        # Toast layer
        self.toasts = ToastManager(self)
        self.toasts.setGeometry(0, 0, self.width(), self.height())
        bus.toast.connect(self.toasts.show_toast)

        # Theme cycle shortcut
        self.theme_idx = 0
        QShortcut(QKeySequence("Ctrl+T"), self, activated=self._cycle_theme)

    def _open_event(self, event):
        dlg = EventDialog(event, self)
        dlg.exec()

    def _cycle_theme(self):
        self.theme_idx = (self.theme_idx + 1) % len(THEMES)
        set_theme(THEMES[self.theme_idx])

    def resizeEvent(self, e):
        self.toasts.setGeometry(0, 0, self.width(), self.height())
        super().resizeEvent(e)


_app = None


def set_theme(name: str):
    if _app:
        _app.setStyleSheet(qss(name))


def main():
    global _app
    _app = QApplication(sys.argv)
    _app.setStyleSheet(qss("dark"))
    win = MainWindow()
    win.show()
    mqtt_client.start()
    sys.exit(_app.exec())


if __name__ == "__main__":
    main()

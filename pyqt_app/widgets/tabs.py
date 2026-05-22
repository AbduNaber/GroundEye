"""Tactical tab bar + QStackedWidget wrapper."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QPushButton, QLabel, QWidget, QStackedWidget, QVBoxLayout
)
from datetime import datetime


class Badge(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setFixedHeight(14)
        self.setStyleSheet(
            "background: #d86a5b; color: white; padding: 1px 5px;"
            " border-radius: 2px; font-size: 9px;"
            " font-family: 'JetBrains Mono'; font-weight: 600;"
        )
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class TabButton(QPushButton):
    def __init__(self, label, parent=None):
        super().__init__(label, parent)
        self.setProperty("role", "tab")
        self.setProperty("active", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setFlat(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def setActive(self, v: bool):
        self.setProperty("active", "true" if v else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class TabsBar(QFrame):
    tab_changed = pyqtSignal(int)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.setObjectName("tabsbar")
        self.buttons = []
        self.badges = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(2)
        lay.setAlignment(Qt.AlignmentFlag.AlignBottom)

        for i, label in enumerate(labels):
            holder = QWidget()
            hl = QHBoxLayout(holder)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(0)
            btn = TabButton(label)
            btn.clicked.connect(lambda _c=False, idx=i: self.set_active(idx))
            self.buttons.append(btn)
            hl.addWidget(btn)
            lay.addWidget(holder)

        lay.addStretch(1)
        self.clock_label = QLabel("")
        self.clock_label.setProperty("role", "monoTiny")
        lay.addWidget(self.clock_label)

        self.set_active(0)
        self._update_clock()
        from PyQt6.QtCore import QTimer
        self._t = QTimer(self)
        self._t.timeout.connect(self._update_clock)
        self._t.start(1000)

    def set_active(self, idx):
        for i, b in enumerate(self.buttons):
            b.setActive(i == idx)
        self.tab_changed.emit(idx)

    def set_badge(self, idx, count):
        btn = self.buttons[idx]
        base = btn.text().split("  ")[0]
        if count > 0:
            btn.setText(f"{base}  ({count})")
        else:
            btn.setText(base)

    def _update_clock(self):
        now = datetime.now()
        self.clock_label.setText(now.strftime("%Y-%m-%d · %H:%M:%S UTC+3"))

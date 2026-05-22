"""Toast manager (bottom-right)."""
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QPoint
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QWidget


class Toast(QFrame):
    def __init__(self, kind, title, body, meta, parent=None):
        super().__init__(parent)
        self.setProperty("role", "toast")
        self.setProperty("kind", kind)
        self.setMinimumWidth(300)
        self.setMaximumWidth(340)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 14, 10)
        lay.setSpacing(2)
        top_color = "#d86a5b" if kind == "alert" else "#5a9fb8"
        prefix = "▲ DETECTION" if kind == "alert" else "◆ NODE"
        top = QLabel(prefix)
        top.setStyleSheet(
            f"color: {top_color}; font-family: 'JetBrains Mono';"
            " font-size: 10px; letter-spacing: 1.5px; font-weight: 600;"
        )
        lay.addWidget(top)
        b = QLabel(title); b.setStyleSheet("font-family: 'JetBrains Mono'; font-size: 11px; color: #d8e0e6;")
        lay.addWidget(b)
        m = QLabel(body); m.setProperty("role", "monoSmall"); lay.addWidget(m)
        mm = QLabel(meta); mm.setProperty("role", "monoMute"); lay.addWidget(mm)


class ToastManager(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background: transparent;")
        self._toasts = []
        self.raise_()

    def show_toast(self, kind, title, body, meta):
        t = Toast(kind, title, body, meta, self)
        t.adjustSize()
        self._toasts.append(t)
        self._relayout()
        t.show()
        QTimer.singleShot(5200, lambda: self._dismiss(t))

    def _dismiss(self, t):
        if t in self._toasts:
            self._toasts.remove(t)
            t.deleteLater()
            self._relayout()

    def _relayout(self):
        # Stack from bottom up
        parent = self.parent()
        if not parent: return
        pw, ph = parent.width(), parent.height()
        self.setGeometry(0, 0, pw, ph)
        y = ph - 50
        for t in reversed(self._toasts):
            t.adjustSize()
            x = pw - t.width() - 16
            t.move(x, y - t.height())
            y -= t.height() + 8

    def resizeEvent(self, e):
        self._relayout()
        super().resizeEvent(e)

"""Fading toast notifications."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget

from ui.theme import DANGER, SUCCESS, TEXT, WARNING

KIND_SUCCESS = "success"
KIND_WARNING = "warning"
KIND_ERROR = "error"

_COLORS = {
    KIND_SUCCESS: SUCCESS,
    KIND_WARNING: WARNING,
    KIND_ERROR: DANGER,
}


class Toast(QWidget):
    """A small rounded notification shown at the bottom of the window."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._label = QLabel(self)
        self._label.setStyleSheet(
            f"background-color: #1c2230; color: {TEXT};"
            "border: 1px solid #2c3547; border-radius: 12px;"
            "padding: 12px 20px; font-weight: 600; font-size: 10.5pt;"
        )

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self._label.setGraphicsEffect(self._effect)

        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(220)
        self._fade.setEasingCurve(QEasingCurve.InOutCubic)
        self._hide_on_finish = False
        self._fade.finished.connect(self._on_fade_finished)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)
        self.hide()

    # ------------------------------------------------------------------ #
    def _fade_out(self) -> None:
        self._hide_on_finish = True
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _on_fade_finished(self) -> None:
        if self._hide_on_finish:
            self.hide()

    def show_message(self, text: str, kind: str = KIND_SUCCESS, duration_ms: int = 2600) -> None:
        border = _COLORS.get(kind, SUCCESS)
        self._label.setText(text)
        self._label.setStyleSheet(
            f"background-color: #1c2230; color: {TEXT};"
            f"border: 1px solid {border}; border-radius: 12px;"
            "padding: 12px 20px; font-weight: 600; font-size: 10.5pt;"
        )
        self.adjustSize()

        parent_rect = self.parentWidget().rect()
        x = (parent_rect.width() - self.width()) // 2
        y = parent_rect.height() - self.height() - 36
        self.move(max(x, 16), max(y, 16))
        self.show()
        self.raise_()

        self._hide_on_finish = False
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(1.0)
        self._fade.start()

        self._hide_timer.start(duration_ms)

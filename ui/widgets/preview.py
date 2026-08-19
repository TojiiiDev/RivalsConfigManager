"""Preview images and placeholders.

Loading a broken or missing image must never crash the application: every
load is wrapped, and a generated placeholder is used as a fallback.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy

logger = logging.getLogger(__name__)

_PIXMAP_CACHE: dict[str, QPixmap] = {}


def _round_pixmap(pixmap: QPixmap, radius: int) -> QPixmap:
    out = QPixmap(pixmap.size())
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(pixmap)
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(out.rect(), radius, radius)
    painter.end()
    return out


def _placeholder_pixmap(size: int, text: str = "Aucun aperçu") -> QPixmap:
    """Generate a dark placeholder with the first letter of ``text``."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)

    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, QColor("#1d2433"))
    gradient.setColorAt(1.0, QColor("#131722"))
    painter.setBrush(gradient)
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(0, 0, size, size, size // 5, size // 5)

    letter = text.strip()[:1].upper() or "?"
    font = QFont("Segoe UI", int(size * 0.38))
    font.setWeight(QFont.DemiBold)
    painter.setFont(font)
    painter.setPen(QColor("#5b6b8c"))
    painter.drawText(pm.rect(), Qt.AlignCenter, letter)
    painter.end()
    return pm


def load_pixmap(path: Path | None, size: int = 320, radius: int = 14) -> QPixmap:
    """Load an image file into a rounded pixmap, or a placeholder.

    Results are cached so re-rendering views is cheap.
    """
    key = f"{path}:{size}:{radius}" if path else f"none:{size}"
    if key in _PIXMAP_CACHE:
        return _PIXMAP_CACHE[key]

    pixmap = None
    if path is not None:
        try:
            loaded = QPixmap(str(path))
            if not loaded.isNull():
                pixmap = loaded.scaled(
                    size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                )
                pixmap = pixmap.copy(
                    (pixmap.width() - size) // 2,
                    (pixmap.height() - size) // 2,
                    size,
                    size,
                )
        except Exception:  # noqa: BLE001 - never crash on a preview
            logger.warning("Aperçu illisible : %s", path)

    if pixmap is None:
        label = path.stem if path else "?"
        pixmap = _placeholder_pixmap(size, label)

    pixmap = _round_pixmap(pixmap, radius)
    _PIXMAP_CACHE[key] = pixmap
    return pixmap


class PreviewLabel(QLabel):
    """A rounded preview image that never crashes on bad files.

    Two modes:

    * ``size`` given (e.g. 360 in the config view): a fixed square label;
    * ``size=None``: the label fills its parent and the pixmap is scaled to
      fit while keeping its aspect ratio, so the image is always contained
      and never overflows (used inside the card's preview container).
    """

    def __init__(self, size: int | None = 320, parent=None) -> None:
        super().__init__(parent)
        self._size = size
        self._source: QPixmap | None = None
        self.setAlignment(Qt.AlignCenter)
        if size is not None:
            self.setFixedSize(size, size)
        else:
            self.setMinimumSize(1, 1)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # ------------------------------------------------------------------ #
    def set_path(self, path: Path | None, name: str = "") -> None:
        if path is None:
            self.set_pixmap(None, name or "?")
            return
        size = self._size if self._size is not None else 260
        self.set_pixmap(load_pixmap(path, size), name)

    def set_pixmap(self, pixmap: QPixmap | None, name: str = "") -> None:
        if pixmap is None:
            pixmap = _placeholder_pixmap(self._size or 260, name or "?")
        self._source = pixmap
        self._apply()

    def _apply(self) -> None:
        if self._source is None:
            self.clear()
            return
        if self._size is not None:
            self.setPixmap(self._source)
            return
        size = self.size()
        if size.width() <= 1 or size.height() <= 1:
            return
        self.setPixmap(
            self._source.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._apply()

"""Generate the application icon (assets/icon.png and assets/icon.ico).

The .ico is a single 256x256 PNG embedded in an ICO container — the modern
format accepted by Windows and PyInstaller. Run from the project root:

    python tools/make_icon.py
"""

from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def render(size: int = 256) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)

    # Dark rounded square.
    painter.setBrush(QColor("#171c26"))
    painter.setPen(Qt.NoPen)
    r = size * 56 // 256
    painter.drawRoundedRect(0, 0, size, size, r, r)

    # Accent rounded square with the "RC" initials.
    painter.setBrush(QColor("#4f8cff"))
    painter.drawRoundedRect(
        size * 48 // 256,
        size * 48 // 256,
        size * 160 // 256,
        size * 160 // 256,
        size * 40 // 256,
        size * 40 // 256,
    )
    painter.setFont(QFont("Segoe UI", size * 78 // 256, QFont.DemiBold))
    painter.setPen(QColor("#ffffff"))
    painter.drawText(image.rect(), Qt.AlignCenter, "RC")
    painter.end()
    return image


def to_png(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def ico_from_png(png: bytes) -> bytes:
    # ICONDIR (6 bytes) + ICONDIRENTRY (16 bytes) + PNG payload.
    header = struct.pack("<HHH", 0, 1, 1)  # reserved, type=icon, count=1
    entry = struct.pack(
        "<BBBBHHII",
        0,       # width  (0 means 256)
        0,       # height (0 means 256)
        0,       # colors
        0,       # reserved
        1,       # planes
        32,      # bit count
        len(png),
        22,      # offset of the payload
    )
    return header + entry + png


def main() -> None:
    import os
    import sys

    from PySide6.QtWidgets import QApplication

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(sys.argv)

    ASSETS.mkdir(parents=True, exist_ok=True)
    image = render(256)

    png = to_png(image)
    (ASSETS / "icon.png").write_bytes(png)
    (ASSETS / "icon.ico").write_bytes(ico_from_png(png))
    print(f"Généré : {ASSETS / 'icon.png'} ({len(png)} octets)")
    print(f"Généré : {ASSETS / 'icon.ico'} ({len(png) + 22} octets)")


if __name__ == "__main__":
    main()

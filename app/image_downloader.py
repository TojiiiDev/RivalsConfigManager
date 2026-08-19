"""Asynchronous image downloader (QThread) — the UI never blocks.

An URL is only accepted when the downloaded bytes really look like an image
(magic bytes) and actually decode (QImage), so a page returning HTML or a
corrupt file is rejected with a clear message.
"""

from __future__ import annotations

import socket
import urllib.error
import urllib.request
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from .i18n import t

USER_AGENT = "RivalsConfigManager/1.0"
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024  # 50 MB safety cap


def detect_image_ext(data: bytes) -> str | None:
    """Detect the format from magic bytes; ``None`` when not an image."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data.startswith(b"BM"):
        return ".bmp"
    if data.startswith(b"GIF8"):
        return ".gif"
    return None


class ImageDownloader(QThread):
    """Download an image in the background.

    Emits :attr:`finished_ok` with the final file path, or :attr:`failed`
    with a user-friendly error message.
    """

    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        url: str,
        dest_dir: Path,
        base_name: str,
        timeout: float = 15.0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._url = url
        self._dest_dir = Path(dest_dir)
        self._base_name = base_name
        self._timeout = timeout

    # ------------------------------------------------------------------ #
    def run(self) -> None:  # runs in the worker thread
        try:
            request = urllib.request.Request(self._url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                data = response.read(MAX_DOWNLOAD_BYTES + 1)
            if len(data) > MAX_DOWNLOAD_BYTES:
                self.failed.emit(t("image_downloader.too_large"))
                return

            ext = detect_image_ext(data)
            if ext is None:
                self.failed.emit(t("image_downloader.not_an_image"))
                return

            if self.isInterruptionRequested():
                return

            dest = self._dest_dir / f"{self._base_name}{ext}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)

            if QImage(str(dest)).isNull():
                try:
                    dest.unlink()
                except OSError:
                    pass
                self.failed.emit(t("image_downloader.corrupt"))
                return

            self.finished_ok.emit(str(dest))
        except urllib.error.HTTPError as exc:
            self.failed.emit(t("image_downloader.http_error", code=exc.code))
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            self.failed.emit(
                t("image_downloader.download_failed", reason=_reason(exc))
            )
        except OSError as exc:
            self.failed.emit(
                t("image_downloader.save_failed", detail=exc.strerror or exc)
            )
        except Exception as exc:  # noqa: BLE001 - never crash the thread
            self.failed.emit(t("image_downloader.unexpected", detail=exc))


def _reason(exc: Exception) -> str:
    reason = getattr(exc, "reason", None)
    return str(reason) if reason is not None else str(exc)

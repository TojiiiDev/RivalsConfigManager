"""Dialog to set / replace / remove a configuration's image.

Workflow: the user picks the configuration, clicks "Modifier l'image",
imports a local file or enters an image URL. Changes are applied
immediately; "Sauvegarder" closes the dialog and the calling view refreshes
the card.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t
from app.image_downloader import ImageDownloader
from app.image_manager import ImageError, ImageManager
from app.image_metadata import stable_id
from app.models import ConfigItem, Node
from ui.theme import DANGER, SUCCESS, TEXT_DIM
from ui.widgets.preview import PreviewLabel

IMAGE_FILTER = t("image.filter")


class ImageDialog(QDialog):
    """Small dialog to manage one element's image (folder or configuration)."""

    def __init__(self, item: ConfigItem | Node, manager: ImageManager, parent=None) -> None:
        super().__init__(parent)
        self._item = item
        self._manager = manager
        self._downloader: ImageDownloader | None = None

        self.setWindowTitle(t("image.title"))
        self.setMinimumWidth(430)

        self._name = QLabel(item.name, self)
        self._name.setObjectName("PageTitle")
        self._name.setWordWrap(True)

        self._preview = PreviewLabel(240, self)
        self._preview.set_path(item.preview, item.name)

        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._status.setMinimumHeight(20)

        # ---- Import / URL buttons ---------------------------------------- #
        self._import_btn = QPushButton(t("image.import_pc"), self)
        self._import_btn.clicked.connect(self._import_local)

        self._url_btn = QPushButton(t("image.use_url"), self)
        self._url_btn.clicked.connect(self._toggle_url_row)

        # ---- URL row (hidden by default) --------------------------------- #
        self._url_input = QLineEdit(self)
        self._url_input.setPlaceholderText("https://example.com/image.png")
        self._url_input.returnPressed.connect(self._load_url)

        self._load_btn = QPushButton(t("image.load"), self)
        self._load_btn.clicked.connect(self._load_url)

        self._url_row = QWidget(self)
        url_layout = QHBoxLayout(self._url_row)
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_layout.setSpacing(8)
        url_layout.addWidget(self._url_input, 1)
        url_layout.addWidget(self._load_btn)
        self._url_row.hide()

        # ---- Remove / save ------------------------------------------------ #
        self._remove_btn = QPushButton(t("image.remove"), self)
        self._remove_btn.setObjectName("DangerButton")
        self._remove_btn.clicked.connect(self._remove)
        self._remove_btn.setEnabled(item.preview is not None)

        self._save_btn = QPushButton(t("common.save"), self)
        self._save_btn.setObjectName("PrimaryButton")
        self._save_btn.clicked.connect(self.accept)

        self._close_btn = QPushButton(t("common.close"), self)
        self._close_btn.clicked.connect(self.reject)

        # ---- Layout -------------------------------------------------------- #
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addWidget(self._remove_btn)
        buttons.addStretch(1)
        buttons.addWidget(self._close_btn)
        buttons.addWidget(self._save_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(self._name)
        layout.addWidget(self._preview, 0, Qt.AlignHCenter)
        layout.addWidget(self._status)
        layout.addWidget(self._import_btn)
        layout.addWidget(self._url_btn)
        layout.addWidget(self._url_row)
        layout.addSpacing(6)
        layout.addLayout(buttons)

    # ------------------------------------------------------------------ #
    def _set_status(self, text: str, kind: str = "info") -> None:
        color = {"ok": SUCCESS, "error": DANGER}.get(kind, TEXT_DIM)
        self._status.setStyleSheet(f"color: {color}; border: none; background: transparent;")
        self._status.setText(text)

    # ------------------------------------------------------------------ #
    def _import_local(self) -> None:
        start = str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, t("image.choose"), start, IMAGE_FILTER
        )
        if not path:
            return
        try:
            cache_path = self._manager.import_local(self._item, Path(path))
        except ImageError as exc:
            self._set_status(f"✘ {exc}", "error")
            return
        self._preview.set_path(cache_path, self._item.name)
        self._remove_btn.setEnabled(True)
        self._set_status(t("image.imported"), "ok")

    # ------------------------------------------------------------------ #
    def _toggle_url_row(self) -> None:
        self._url_row.setVisible(not self._url_row.isVisible())
        if self._url_row.isVisible():
            self._url_input.setFocus()

    def _load_url(self) -> None:
        url = self._url_input.text().strip()
        if not url.startswith(("http://", "https://")):
            self._set_status(t("image.invalid_url"), "error")
            return
        if self._downloader is not None and self._downloader.isRunning():
            return

        self._set_status(t("image.loading"))
        self._import_btn.setEnabled(False)
        self._url_btn.setEnabled(False)
        self._load_btn.setEnabled(False)
        self._remove_btn.setEnabled(False)

        self._downloader = ImageDownloader(
            url,
            self._manager.cache_root,
            stable_id(self._item),
            parent=self,
        )
        self._downloader.finished_ok.connect(lambda path: self._on_download_ok(url, path))
        self._downloader.failed.connect(self._on_download_failed)
        self._downloader.start()

    def _on_download_ok(self, url: str, path: str) -> None:
        self._manager.save_downloaded(self._item, url, Path(path))
        self._preview.set_path(Path(path), self._item.name)
        self._remove_btn.setEnabled(True)
        self._restore_buttons()
        self._set_status(t("image.loaded"), "ok")

    def _on_download_failed(self, message: str) -> None:
        self._restore_buttons()
        self._set_status(f"✘ {message}", "error")

    def _restore_buttons(self) -> None:
        self._import_btn.setEnabled(True)
        self._url_btn.setEnabled(True)
        self._load_btn.setEnabled(True)
        self._remove_btn.setEnabled(self._item.preview is not None or self._downloader is not None)

    # ------------------------------------------------------------------ #
    def _remove(self) -> None:
        self._manager.remove(self._item)
        self._preview.set_path(None, self._item.name)
        self._remove_btn.setEnabled(False)
        self._set_status(t("image.removed"), "ok")

    # ------------------------------------------------------------------ #
    def reject(self) -> None:
        if self._downloader is not None and self._downloader.isRunning():
            self._downloader.requestInterruption()
            self._downloader.wait(3000)
        super().reject()

"""Background asset sync worker (QThread) — the UI never blocks.

Fetching the manifest and downloading assets happen in a worker thread; the
GUI only receives progress/completion signals. Every failure path (no remote,
offline, invalid manifest, per-asset errors) is reported — never a crash.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..i18n import t
from . import max_asset_bytes
from .cache import LocalAssetCache
from .fetcher import FetchError, fetch_asset, fetch_manifest
from .manifest import ManifestError, loads
from .security import SecurityError
from .sync import sync_assets

logger = logging.getLogger(__name__)


class AssetSyncWorker(QThread):
    """Run one full asset sync in the background.

    Signals (all delivered on the GUI thread through queued connections):

    * :attr:`progress` — ``(done, total)`` after each download attempt;
    * :attr:`succeeded` — the :class:`~app.assets.sync.SyncOutcome`;
    * :attr:`failed` — a user-facing message for a fatal (pre-sync) failure.
    """

    progress = Signal(int, int)
    succeeded = Signal(object)   # SyncOutcome
    failed = Signal(str)         # message

    def __init__(
        self,
        base_url: str,
        cache: LocalAssetCache | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._base_url = (base_url or "").rstrip("/")
        self._cache = cache

    # ------------------------------------------------------------------ #
    def run(self) -> None:  # runs in the worker thread
        if not self._base_url:
            self.failed.emit(t("assets.no_remote"))
            return

        # 1. Fetch + validate the manifest (a single lightweight request).
        try:
            text = fetch_manifest(self._base_url)
        except (FetchError, SecurityError) as exc:
            logger.info("Manifest d'assets indisponible : %s", exc)
            self.failed.emit(t("assets.offline"))
            return
        try:
            remote = loads(text)
        except ManifestError as exc:
            logger.warning("Manifest d'assets invalide : %s", exc)
            self.failed.emit(t("assets.invalid_manifest"))
            return

        # 2. Download only what changed (never re-download the cache).
        cache = self._cache or LocalAssetCache()
        limit = max_asset_bytes()

        def fetcher(path: str) -> bytes:
            return fetch_asset(self._base_url, path, limit)

        try:
            outcome = sync_assets(
                remote,
                cache,
                fetcher,
                limit,
                on_progress=lambda done, total: self.progress.emit(done, total),
            )
        except Exception as exc:  # noqa: BLE001 - never crash the thread
            logger.exception("Synchronisation d'assets interrompue")
            self.failed.emit(t("assets.invalid_manifest"))
            return

        self.succeeded.emit(outcome)

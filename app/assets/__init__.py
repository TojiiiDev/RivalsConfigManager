"""Centralised asset system — shared images, manifest and local cache.

The application bundles no weapon/skin/charm images inside the ``.exe``:
those live in a shared asset repository (a ``manifest.json`` + an
``assets/`` tree), are versioned independently of the application, and are
synced on demand into a per-user local cache:

    %APPDATA%\\RivalsConfigManager\\
        assets\\            <- downloaded asset files (never re-downloaded)
        asset_manifest.json <- what is currently downloaded (key -> version)

The cache is always read first (fast, offline-capable); downloads happen in
the background and are strictly optional — with no Internet the application
keeps working with whatever is already cached.

Public API:

    from app.assets import (
        assets_version,
        asset_base_url,
        max_asset_bytes,
        asset_timeout,
    )
"""

from __future__ import annotations

import os

#: Default version of the bundled/seed asset set. This is independent from
#: the application version (``app.__version__``): changing an image never
#: requires rebuilding the ``.exe``, only bumping this value in the manifest.
DEFAULT_ASSETS_VERSION = "2026.08.19.1"

#: Default maximum size of a single downloaded asset (bytes).
DEFAULT_MAX_ASSET_BYTES = 10 * 1024 * 1024  # 10 MB

#: Default network timeout for manifest/asset requests (seconds).
DEFAULT_TIMEOUT = 15.0


def asset_base_url() -> str:
    """The trusted base URL of the asset repository (HTTPS, no trailing slash).

    Read from ``RCM_ASSET_BASE_URL``; empty when no remote is configured, in
    which case the app stays fully local (bundled + cached assets only).
    """
    return (os.environ.get("RCM_ASSET_BASE_URL") or "").rstrip("/")


def max_asset_bytes() -> int:
    """Maximum download size per asset (env ``RCM_ASSET_MAX_BYTES``)."""
    raw = os.environ.get("RCM_ASSET_MAX_BYTES")
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return DEFAULT_MAX_ASSET_BYTES


def asset_timeout() -> float:
    """Network timeout in seconds (env ``RCM_ASSET_TIMEOUT``)."""
    raw = os.environ.get("RCM_ASSET_TIMEOUT")
    if raw:
        try:
            value = float(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return DEFAULT_TIMEOUT


def assets_version() -> str:
    """The assets version string (used in reports and the seed manifest)."""
    return DEFAULT_ASSETS_VERSION

"""HTTP fetcher for the remote manifest and asset files (stdlib only).

Everything goes through :func:`app.assets.security.is_allowed_url`: the base
URL is the single trusted origin, and only HTTPS URLs rooted at it are ever
fetched. A manifest that points elsewhere is refused before any request.
"""

from __future__ import annotations

import urllib.error
import urllib.request

from . import asset_timeout
from .security import SecurityError, is_allowed_url

USER_AGENT = "RivalsConfigManager/1.3"


class FetchError(Exception):
    """A network/HTTP failure (no Internet, 404, timeout, ...)."""


def _request(url: str, timeout: float, max_bytes: int | None) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if max_bytes is not None:
            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise FetchError(f"réponse trop volumineuse : {url}")
            return data
        return response.read()


def fetch_manifest(base_url: str, timeout: float | None = None) -> str:
    """Fetch ``<base_url>/manifest.json`` and return its text.

    Raises :class:`FetchError` on any failure (offline, 404, timeout, ...).
    """
    url = f"{base_url.rstrip('/')}/manifest.json"
    if not is_allowed_url(url, base_url):
        raise SecurityError(f"URL de manifest non autorisée : {url}")
    timeout = timeout if timeout is not None else asset_timeout()
    try:
        return _request(url, timeout, max_bytes=1024 * 1024).decode("utf-8-sig")
    except SecurityError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError, FetchError) as exc:
        raise FetchError(_reason(exc)) from exc


def fetch_asset(base_url: str, path: str, max_bytes: int, timeout: float | None = None) -> bytes:
    """Fetch one asset file (``<base_url>/<path>``) and return its bytes."""
    url = f"{base_url.rstrip('/')}/{path}"
    if not is_allowed_url(url, base_url):
        raise SecurityError(f"URL d'asset non autorisée : {url}")
    timeout = timeout if timeout is not None else asset_timeout()
    try:
        return _request(url, timeout, max_bytes)
    except (urllib.error.URLError, TimeoutError, OSError, FetchError) as exc:
        raise FetchError(_reason(exc)) from exc


def _reason(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    reason = getattr(exc, "reason", None)
    return str(reason) if reason is not None else str(exc)

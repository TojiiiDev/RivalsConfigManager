"""Security guards for the asset sync layer.

Every value that comes from the remote manifest or a URL is untrusted and
must be validated before it touches the filesystem or the network:

* **URLs** must be HTTPS and rooted at the configured base URL — nothing
  else can ever be fetched.
* **Asset paths** must be relative, forward-slash, free of ``..``/absolute
  components/drive letters — no path traversal, no writing outside the cache.
* **Downloads** are capped in size and their bytes must look like an image
  (magic bytes) before being written to the cache.
"""

from __future__ import annotations

from urllib.parse import urlparse


class SecurityError(Exception):
    """A manifest or URL failed a security check — never written, never fetched."""


def is_https_url(url: str) -> bool:
    """True when ``url`` is an absolute HTTPS URL."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.netloc)


def is_loopback_url(url: str) -> bool:
    """True for ``http://127.0.0.1`` / ``localhost`` (local dev/tests only)."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme == "http" and (parsed.hostname or "") in {
        "127.0.0.1",
        "localhost",
        "::1",
    }


def _rooted(url: str, base_url: str) -> bool:
    """True when ``url`` is ``base_url`` or strictly under it (path prefix)."""
    prefix = base_url.rstrip("/") + "/"
    return url == base_url or url.startswith(prefix)


def is_allowed_url(url: str, base_url: str) -> bool:
    """True when ``url`` is HTTPS and rooted at ``base_url``.

    The base URL is the only allowed origin: ``https://host/a/b`` must start
    with ``https://host/a/b`` exactly (path-prefix, not just host), so an
    attacker-controlled manifest can never point the app at another host or
    a sibling directory of the same host.

    Loopback HTTP (``127.0.0.1``/``localhost``) is allowed **only** for local
    development and tests — never for production fetches.
    """
    if not base_url:
        return False
    if is_https_url(base_url) and is_https_url(url):
        return _rooted(url, base_url)
    if is_loopback_url(base_url) and is_loopback_url(url):
        return _rooted(url, base_url)
    return False


def is_asset_image_path(path: str) -> bool:
    """True when ``path`` ends with a supported image extension."""
    return path.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"))


def sanitize_asset_path(path: str) -> str:
    """Validate and normalise a manifest asset path.

    Returns the clean POSIX relative path (forward slashes). Raises
    :class:`SecurityError` when the path could escape the cache, is absolute,
    is not an image, or contains a traversal component.
    """
    if not isinstance(path, str) or not path.strip():
        raise SecurityError("chemin d'asset vide")
    if "\\" in path or "\x00" in path:
        raise SecurityError(f"chemin d'asset invalide : {path!r}")
    if path.startswith("/") or (len(path) > 1 and path[1] == ":"):
        raise SecurityError(f"chemin d'asset absolu refusé : {path!r}")

    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise SecurityError(f"chemin d'asset invalide : {path!r}")

    clean = "/".join(parts)
    if not is_asset_image_path(clean):
        raise SecurityError(f"type d'asset non supporté : {path!r}")
    return clean


def relative_cache_path(path: str) -> str:
    """Map a manifest path (e.g. ``assets/weapons/x.png``) to its location
    inside the local cache (``weapons/x.png``)."""
    clean = sanitize_asset_path(path)
    if clean.startswith("assets/"):
        return clean[len("assets/") :]
    return clean


def validate_image_bytes(data: bytes, max_bytes: int) -> str | None:
    """Return the detected image extension, or ``None`` when not an image.

    ``data`` must be non-empty, within ``max_bytes`` and start with a known
    image magic number (PNG/JPEG/WEBP/BMP/GIF).
    """
    if not data or len(data) > max_bytes:
        return None
    from app.image_downloader import detect_image_ext

    return detect_image_ext(data)

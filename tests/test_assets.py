"""Tests for the centralised asset system (manifest, cache, sync, security).

No Internet is required: the sync engine is driven through an injected
``fetcher`` callable, and the HTTP helpers are exercised against a local
loopback server (loopback HTTP is allowed only for dev/tests).
"""

from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from app.assets.cache import LocalAssetCache, LocalCacheState, slug
from app.assets.manifest import ManifestError, parse_manifest, loads
from app.assets.security import (
    SecurityError,
    is_allowed_url,
    relative_cache_path,
    sanitize_asset_path,
    validate_image_bytes,
)
from app.assets.sync import compute_plan, sync_assets

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _manifest(assets: dict | None = None, assets_version: str = "2026.08.19.1") -> dict:
    return {
        "schema_version": 1,
        "assets_version": assets_version,
        "assets": assets or {},
    }


def _entry(path: str = "assets/weapons/assault_rifle.png", version: int = 1, **extra) -> dict:
    value = {"path": path, "version": version}
    value.update(extra)
    return value


# ---------------------------------------------------------------------- #
# Manifest parsing / validation
# ---------------------------------------------------------------------- #
def test_parse_valid_manifest() -> None:
    manifest = parse_manifest(
        _manifest({"assault_rifle": _entry(version=3)})
    )
    assert manifest.schema_version == 1
    assert manifest.assets_version == "2026.08.19.1"
    assert manifest.entry("assault_rifle").version == 3
    assert manifest.entry("assault_rifle").path == "assets/weapons/assault_rifle.png"


def test_manifest_accepts_older_schema() -> None:
    manifest = parse_manifest({"schema_version": 1, "assets_version": "x", "assets": {}})
    assert manifest.schema_version == 1


def test_manifest_rejects_newer_schema() -> None:
    with pytest.raises(ManifestError):
        parse_manifest({"schema_version": 99, "assets_version": "x", "assets": {}})


@pytest.mark.parametrize(
    "bad",
    [
        "not json",
        [],
        {"schema_version": 1, "assets": {}},                      # no assets_version
        {"schema_version": "1", "assets_version": "x", "assets": {}},
        {"schema_version": 1, "assets_version": "", "assets": {}},
        {"schema_version": 1, "assets_version": "x", "assets": []},
        _manifest({"a": {"path": "assets/x.txt", "version": 1}}),   # not an image
        _manifest({"a": {"path": "assets/../evil.png", "version": 1}}),
        _manifest({"a": {"path": "assets/x.png", "version": 0}}),
        _manifest({"a": {"path": "assets/x.png"}}),                # missing version
    ],
)
def test_manifest_rejects_invalid(bad) -> None:
    with pytest.raises(ManifestError):
        parse_manifest(bad)


def test_loads_rejects_bad_json() -> None:
    with pytest.raises(ManifestError):
        loads("{nope")


# ---------------------------------------------------------------------- #
# Security
# ---------------------------------------------------------------------- #
def test_sanitize_valid_paths() -> None:
    assert sanitize_asset_path("assets/weapons/x.png") == "assets/weapons/x.png"
    assert sanitize_asset_path("weapons/x.png") == "weapons/x.png"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "assets/x.txt",
        "assets/../x.png",
        "/etc/x.png",
        "C:/x.png",
        "assets\\x.png",
        "assets//x.png",
        "assets/./x.png",
    ],
)
def test_sanitize_rejects_bad_paths(bad) -> None:
    with pytest.raises(SecurityError):
        sanitize_asset_path(bad)


def test_relative_cache_path_strips_assets_prefix() -> None:
    assert relative_cache_path("assets/weapons/x.png") == "weapons/x.png"
    assert relative_cache_path("weapons/x.png") == "weapons/x.png"


def test_is_allowed_url() -> None:
    base = "https://raw.githubusercontent.com/o/r/main"
    assert is_allowed_url(f"{base}/manifest.json", base)
    assert is_allowed_url(f"{base}/assets/weapons/x.png", base)
    assert not is_allowed_url("https://evil.com/x.png", base)     # other host
    assert not is_allowed_url("http://raw.githubusercontent.com/o/r/main/x.png", base)
    assert not is_allowed_url("https://raw.githubusercontent.com/o/other/x.png", base)
    assert not is_allowed_url(f"{base}/x.png", "")                # empty base
    # Loopback HTTP: dev/tests only.
    assert is_allowed_url("http://127.0.0.1:9/a.png", "http://127.0.0.1:9")
    assert not is_allowed_url("http://example.com/a.png", "http://example.com")


def test_validate_image_bytes() -> None:
    assert validate_image_bytes(PNG_1PX, 1000000) == ".png"
    assert validate_image_bytes(b"<html>", 1000000) is None
    assert validate_image_bytes(PNG_1PX, 3) is None  # too large for the cap


# ---------------------------------------------------------------------- #
# Cache
# ---------------------------------------------------------------------- #
def test_slug_normalisation() -> None:
    assert slug("Assault Rifle") == "assault_rifle"
    assert slug("assault_rifle") == "assault_rifle"
    assert slug("  Nemesis Charm (1) ") == "nemesis_charm_1"


def test_cache_file_for_and_manifest_roundtrip(tmp_path: Path) -> None:
    cache = LocalAssetCache(tmp_path / "assets")
    assert cache.file_for("assets/weapons/x.png") == tmp_path / "assets" / "weapons" / "x.png"

    manifest = parse_manifest(_manifest({"assault_rifle": _entry(version=2)}))
    cache.write_manifest(manifest)
    state = cache.load_state()
    assert state.manifest is not None
    assert state.manifest.entry("assault_rifle").version == 2


def test_cache_missing_manifest_is_none(tmp_path: Path) -> None:
    cache = LocalAssetCache(tmp_path / "assets")
    assert cache.load_state().manifest is None


def test_cache_find_image_matches_name(tmp_path: Path) -> None:
    cache = LocalAssetCache(tmp_path / "assets")
    manifest = parse_manifest(
        _manifest({"assault_rifle": _entry(path="assets/weapons/assault_rifle.png")})
    )
    cache.write_manifest(manifest)
    (tmp_path / "assets" / "weapons").mkdir(parents=True)
    (tmp_path / "assets" / "weapons" / "assault_rifle.png").write_bytes(PNG_1PX)

    assert cache.find_image("Assault Rifle") is not None
    assert cache.find_image("unknown") is None
    assert cache.cached_path_for_key("assault_rifle") is not None
    assert cache.cached_path_for_key("nope") is None


# ---------------------------------------------------------------------- #
# Sync
# ---------------------------------------------------------------------- #
def test_compute_plan_new_updated_removed_unchanged() -> None:
    remote = parse_manifest(
        _manifest(
            {
                "a": _entry(version=2),
                "b": _entry(version=1),
                "c": _entry(path="assets/weapons/c.png", version=1),
            }
        )
    )
    # Local: a v1 (update), b v1 (unchanged), d v1 (removed).
    local = parse_manifest(
        _manifest(
            {
                "a": _entry(version=1),
                "b": _entry(version=1),
                "d": _entry(path="assets/weapons/d.png", version=1),
            }
        )
    )
    state = LocalCacheState(manifest=local, files={})
    plan = compute_plan(remote, state)
    assert sorted(k for k, _ in plan.to_download) == ["a", "c"]
    assert plan.to_remove == ["d"]
    assert plan.unchanged == 1


def test_sync_downloads_only_changed(tmp_path: Path) -> None:
    cache = LocalAssetCache(tmp_path / "assets")
    remote = parse_manifest(
        _manifest(
            {
                "a": _entry(path="assets/weapons/a.png", version=1),
                "b": _entry(path="assets/weapons/b.png", version=2),
            }
        )
    )
    # Seed the cache: a already downloaded at v1, b at v1 (needs update).
    cache.write_manifest(
        parse_manifest(
            _manifest(
                {
                    "a": _entry(path="assets/weapons/a.png", version=1),
                    "b": _entry(path="assets/weapons/b.png", version=1),
                }
            )
        )
    )
    (tmp_path / "assets" / "weapons").mkdir(parents=True)
    (tmp_path / "assets" / "weapons" / "a.png").write_bytes(PNG_1PX)
    (tmp_path / "assets" / "weapons" / "b.png").write_bytes(PNG_1PX)

    fetched: list[str] = []

    def fetcher(path: str) -> bytes:
        fetched.append(path)
        return PNG_1PX

    outcome = sync_assets(remote, cache, fetcher, max_bytes=1000000)
    assert fetched == ["assets/weapons/b.png"]  # only b re-downloaded
    assert outcome.downloaded == []
    assert outcome.updated == ["b"]
    assert outcome.ok


def test_sync_partial_failure_keeps_others(tmp_path: Path) -> None:
    cache = LocalAssetCache(tmp_path / "assets")
    remote = parse_manifest(
        _manifest(
            {
                "a": _entry(path="assets/weapons/a.png", version=1),
                "b": _entry(path="assets/weapons/b.png", version=1),
            }
        )
    )

    def fetcher(path: str) -> bytes:
        if path.endswith("b.png"):
            raise OSError("boom")
        return PNG_1PX

    outcome = sync_assets(remote, cache, fetcher, max_bytes=1000000)
    assert outcome.downloaded == ["a"]
    assert outcome.errors, "l'échec de b doit être rapporté"
    assert not outcome.ok
    # a is on disk; b was not silently claimed.
    assert cache.file_for("assets/weapons/a.png").is_file()
    state = cache.load_state()
    assert state.manifest.entry("a") is not None
    assert state.manifest.entry("b") is None


def test_sync_removes_deleted_asset(tmp_path: Path) -> None:
    cache = LocalAssetCache(tmp_path / "assets")
    (tmp_path / "assets" / "weapons").mkdir(parents=True)
    stale = tmp_path / "assets" / "weapons" / "d.png"
    stale.write_bytes(PNG_1PX)
    cache.write_manifest(parse_manifest(_manifest({"d": _entry(path="assets/weapons/d.png")})))

    remote = parse_manifest(_manifest({}))
    outcome = sync_assets(remote, cache, lambda p: PNG_1PX, max_bytes=1000000)
    assert outcome.removed == ["d"]
    assert not stale.exists()


def test_sync_offline_fetcher_raises(tmp_path: Path) -> None:
    cache = LocalAssetCache(tmp_path / "assets")
    remote = parse_manifest(_manifest({"a": _entry(path="assets/weapons/a.png")}))

    def fetcher(path: str) -> bytes:
        raise OSError("offline")

    outcome = sync_assets(remote, cache, fetcher, max_bytes=1000000)
    assert not outcome.ok
    assert outcome.errors
    assert not cache.file_for("assets/weapons/a.png").exists()


# ---------------------------------------------------------------------- #
# Fetcher + end-to-end over a loopback HTTP server
# ---------------------------------------------------------------------- #
class _Handler(BaseHTTPRequestHandler):
    MANIFEST = json.dumps(
        _manifest({"assault_rifle": _entry(path="assets/weapons/assault_rifle.png", version=1)})
    ).encode("utf-8")

    def log_message(self, *args):  # silence
        pass

    def do_GET(self):  # noqa: N802 (HTTP convention)
        if self.path == "/manifest.json":
            self._send(self.MANIFEST, "application/json")
        elif self.path == "/assets/weapons/assault_rifle.png":
            self._send(PNG_1PX, "image/png")
        else:
            self.send_error(404)

    def _send(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def http_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_fetch_manifest_and_asset_over_loopback(http_server: str) -> None:
    from app.assets.fetcher import fetch_asset, fetch_manifest

    text = fetch_manifest(http_server)
    manifest = loads(text)
    assert manifest.entry("assault_rifle") is not None

    data = fetch_asset(http_server, "assets/weapons/assault_rifle.png", 1000000)
    assert data == PNG_1PX


def test_fetch_manifest_offline_raises() -> None:
    from app.assets.fetcher import FetchError, fetch_manifest

    with pytest.raises(FetchError):
        fetch_manifest("http://127.0.0.1:1", timeout=1.0)


def test_fetch_asset_rejects_insecure_remote() -> None:
    from app.assets.fetcher import fetch_asset

    # Plain HTTP to a non-loopback host is never allowed (HTTPS only).
    with pytest.raises(SecurityError):
        fetch_asset("http://example.com", "assets/weapons/x.png", 1000000, timeout=0.1)


def test_end_to_end_sync_over_loopback(http_server: str, tmp_path: Path) -> None:
    from app.assets.fetcher import fetch_asset, fetch_manifest

    cache = LocalAssetCache(tmp_path / "assets")
    remote = loads(fetch_manifest(http_server))
    outcome = sync_assets(
        remote,
        cache,
        lambda path: fetch_asset(http_server, path, 1000000),
        max_bytes=1000000,
    )
    assert outcome.ok and outcome.downloaded == ["assault_rifle"]
    assert cache.file_for("assets/weapons/assault_rifle.png").is_file()

    # Second run: nothing to download (cache is honoured).
    outcome2 = sync_assets(
        remote,
        cache,
        lambda path: fetch_asset(http_server, path, 1000000),
        max_bytes=1000000,
    )
    assert outcome2.downloaded == [] and outcome2.updated == []
    assert outcome2.unchanged == 1


# ---------------------------------------------------------------------- #
# Resolution: cards fall back to the shared cache (no manual install)
# ---------------------------------------------------------------------- #
def test_effective_preview_falls_back_to_shared_asset(tmp_path: Path, monkeypatch) -> None:
    from app.image_metadata import effective_preview, invalidate_shared_assets

    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))
    invalidate_shared_assets()

    cache = LocalAssetCache()
    cache.write_manifest(
        parse_manifest(_manifest({"assault_rifle": _entry(path="assets/weapons/assault_rifle.png")}))
    )
    (cache.root / "weapons").mkdir(parents=True)
    (cache.root / "weapons" / "assault_rifle.png").write_bytes(PNG_1PX)

    from app.models import KIND_FILE, ConfigItem

    item = ConfigItem(
        name="ak-47",
        path=tmp_path / "Assault Rifle" / "ak-47.json",
        kind=KIND_FILE,
    )
    preview = effective_preview(item)
    assert preview is not None and preview.is_file()

    # Unknown item -> still None (placeholder is used by the card).
    unknown = ConfigItem(
        name="ghost",
        path=tmp_path / "No Match" / "ghost.json",
        kind=KIND_FILE,
    )
    assert effective_preview(unknown) is None

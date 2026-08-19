"""Tests for app/image_manager.py and app/image_downloader.py."""

from __future__ import annotations

import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from app.image_downloader import ImageDownloader, detect_image_ext
from app.image_manager import ImageError, ImageManager
from app.image_metadata import load_metadata
from app.models import KIND_FILE, ConfigItem

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _item(tmp_path: Path, name: str = "Rival Skin") -> ConfigItem:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / f"{name}.json"
    path.write_text("{}", encoding="utf-8")
    (tmp_path / f"{name}.obj").write_text("mesh", encoding="utf-8")
    return ConfigItem(name=name, path=path, kind=KIND_FILE, files=[path], json_files=[path])


def _write_png(path: Path) -> Path:
    path.write_bytes(PNG_1PX)
    return path


# ---------------------------------------------------------------------- #
# import_local
# ---------------------------------------------------------------------- #
def test_import_local_copies_and_writes_metadata(tmp_path: Path, monkeypatch) -> None:
    # Use the default cache root (inside the app data dir) so the sidecar
    # stores the portable relative path ``image_cache/<id>.png``.
    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))
    manager = ImageManager()
    item = _item(tmp_path / "lib")
    source = _write_png(tmp_path / "source.png")

    dest = manager.import_local(item, source)

    assert dest.is_file()
    assert dest.read_bytes() == PNG_1PX
    meta = load_metadata(item)
    assert meta["type"] == "local"
    assert meta["source"] == str(source)
    assert meta["local_path"] == f"image_cache/{dest.name}"
    # The real configuration files were not touched.
    assert (tmp_path / "lib" / "Rival Skin.json").read_text(encoding="utf-8") == "{}"
    assert (tmp_path / "lib" / "Rival Skin.obj").read_text(encoding="utf-8") == "mesh"


def test_import_local_missing_file(tmp_path: Path) -> None:
    manager = ImageManager(tmp_path / "cache")
    item = _item(tmp_path / "lib")
    with pytest.raises(ImageError, match="introuvable"):
        manager.import_local(item, tmp_path / "ghost.png")


def test_import_local_wrong_format(tmp_path: Path) -> None:
    manager = ImageManager(tmp_path / "cache")
    item = _item(tmp_path / "lib")
    source = tmp_path / "notes.txt"
    source.write_text("hello", encoding="utf-8")
    with pytest.raises(ImageError, match="Format non supporté"):
        manager.import_local(item, source)


def test_import_local_corrupt_image(tmp_path: Path) -> None:
    manager = ImageManager(tmp_path / "cache")
    item = _item(tmp_path / "lib")
    source = tmp_path / "fake.png"
    source.write_bytes(b"not really a png")
    with pytest.raises(ImageError, match="corrompue|lisible"):
        manager.import_local(item, source)


def test_import_local_paths_with_spaces(tmp_path: Path) -> None:
    manager = ImageManager(tmp_path / "cache dir")
    item = _item(tmp_path / "my library")
    source = _write_png(tmp_path / "my image.png")
    dest = manager.import_local(item, source)
    assert dest.is_file()


def test_import_local_replaces_previous(tmp_path: Path) -> None:
    manager = ImageManager(tmp_path / "cache")
    item = _item(tmp_path / "lib")
    first = manager.import_local(item, _write_png(tmp_path / "a.png"))
    second = manager.import_local(item, _write_png(tmp_path / "b.png"))
    assert first == second  # same stable id -> same cache file


# ---------------------------------------------------------------------- #
# remove
# ---------------------------------------------------------------------- #
def test_remove_deletes_metadata_and_cache(tmp_path: Path) -> None:
    manager = ImageManager(tmp_path / "cache")
    item = _item(tmp_path / "lib")
    dest = manager.import_local(item, _write_png(tmp_path / "source.png"))
    assert dest.is_file()

    manager.remove(item)
    assert not dest.exists()
    assert load_metadata(item) is None
    # Real configuration files still there.
    assert (tmp_path / "lib" / "Rival Skin.json").exists()
    assert (tmp_path / "lib" / "Rival Skin.obj").exists()


def test_remove_without_image_is_noop(tmp_path: Path) -> None:
    manager = ImageManager(tmp_path / "cache")
    item = _item(tmp_path / "lib")
    manager.remove(item)  # must not raise
    assert (tmp_path / "lib" / "Rival Skin.json").exists()


# ---------------------------------------------------------------------- #
# downloader (local HTTP server)
# ---------------------------------------------------------------------- #
class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def do_GET(self):  # noqa: N802 (HTTP convention)
        if self.path == "/ok.png":
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(PNG_1PX)))
            self.end_headers()
            self.wfile.write(PNG_1PX)
        elif self.path == "/page":
            body = b"<html><body>not an image</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/slow":
            time.sleep(5)
            self.send_response(200)
            self.end_headers()
        else:
            self.send_error(404)


@pytest.fixture
def http_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base
    server.shutdown()


def _run_downloader(url: str, dest_dir: Path, base_name: str, timeout: float) -> tuple[bool, str]:
    """Run a downloader synchronously (DirectConnection) and return (ok, payload).

    No QCoreApplication is created on purpose: QThread works without one, and
    creating an application instance here would poison the singleton for the
    GUI smoke tests (QApplication must be the only application instance).
    """
    from PySide6.QtCore import Qt

    result: dict = {}

    def _ok(path: str) -> None:
        result["ok"] = True
        result["path"] = path

    def _fail(msg: str) -> None:
        result["ok"] = False
        result["error"] = msg

    downloader = ImageDownloader(url, dest_dir, base_name, timeout=timeout)
    downloader.finished_ok.connect(_ok, Qt.DirectConnection)
    downloader.failed.connect(_fail, Qt.DirectConnection)
    downloader.start()
    downloader.wait(15000)
    return result.get("ok", False), result.get("path") or result.get("error", "?")


def test_detect_image_ext() -> None:
    assert detect_image_ext(PNG_1PX) == ".png"
    assert detect_image_ext(b"\xff\xd8\xffjpgdata") == ".jpg"
    assert detect_image_ext(b"<html>") is None
    assert detect_image_ext(b"BM....") == ".bmp"


def test_download_valid_image(http_server, tmp_path: Path) -> None:
    ok, payload = _run_downloader(f"{http_server}/ok.png", tmp_path, "img1", timeout=5)
    assert ok
    assert Path(payload).is_file()
    assert Path(payload).read_bytes() == PNG_1PX
    assert Path(payload).suffix == ".png"


def test_download_html_is_rejected(http_server, tmp_path: Path) -> None:
    ok, error = _run_downloader(f"{http_server}/page", tmp_path, "img2", timeout=5)
    assert not ok
    assert "HTML" in error or "image" in error
    assert not list(tmp_path.iterdir())


def test_download_http_error(http_server, tmp_path: Path) -> None:
    ok, error = _run_downloader(f"{http_server}/missing.png", tmp_path, "img3", timeout=5)
    assert not ok
    assert "404" in error


def test_download_timeout(http_server, tmp_path: Path) -> None:
    ok, error = _run_downloader(f"{http_server}/slow", tmp_path, "img4", timeout=1)
    assert not ok
    assert error  # a clear message, no crash


def test_download_invalid_url(tmp_path: Path) -> None:
    ok, error = _run_downloader("ftp://not-http.example/x.png", tmp_path, "img5", timeout=5)
    assert not ok
    assert error


def test_url_workflow_via_manager(http_server, tmp_path: Path, monkeypatch) -> None:
    """Full URL flow: download then save_downloaded writes the sidecar."""
    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))
    manager = ImageManager()
    item = _item(tmp_path / "lib")

    ok, payload = _run_downloader(f"{http_server}/ok.png", manager.cache_root, "idurl", timeout=5)
    assert ok
    manager.save_downloaded(item, f"{http_server}/ok.png", Path(payload))
    meta = load_metadata(item)
    assert meta["type"] == "url"
    assert meta["source"] == f"{http_server}/ok.png"
    assert meta["local_path"].startswith("image_cache/")

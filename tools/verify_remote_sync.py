"""End-to-end validation of the shared-asset sync (no Internet required).

Simulates the GitHub remote with a loopback HTTP server that serves this
repository's ``manifest.json`` + ``assets/``, and exercises the three flows
the application depends on:

1. **Machine propre** — an empty cache downloads every asset.
2. **Mise à jour** — one asset's version is bumped; only that asset is
   re-downloaded (the others stay in cache).
3. **Hors ligne** — the server stops; the cache still resolves images and a
   sync fails gracefully instead of crashing.

Usage (from the project root)::

    python tools/verify_remote_sync.py

Exit code 0 = all checks passed.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.assets.cache import LocalAssetCache  # noqa: E402
from app.assets.fetcher import FetchError, fetch_asset, fetch_manifest  # noqa: E402
from app.assets.manifest import loads  # noqa: E402
from app.assets.sync import sync_assets  # noqa: E402


class _Server:
    """Serve a directory as ``<base>/manifest.json`` + ``<base>/<path>``."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()

    def _make_handler(self):
        root = self.root

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def do_GET(self):  # noqa: N802
                rel = self.path.lstrip("/")
                if rel == "manifest.json":
                    body = (root / "manifest.json").read_bytes()
                    ctype = "application/json"
                else:
                    fp = (root / rel).resolve()
                    if not fp.is_file() or not str(fp).startswith(str(root.resolve())):
                        self.send_error(404)
                        return
                    body = fp.read_bytes()
                    ctype = "application/octet-stream"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler


def _fresh_appdata() -> Path:
    d = Path(tempfile.mkdtemp(prefix="rcm_assets_"))
    os.environ["APPDATA"] = str(d)
    return d


def main() -> int:
    from app.image_metadata import invalidate_shared_assets, shared_preview
    from app.models import KIND_FILE, ConfigItem

    manifest_file = ROOT / "manifest.json"
    if not manifest_file.is_file():
        print("X manifest.json introuvable à la racine", file=sys.stderr)
        return 2

    workdir = Path(tempfile.mkdtemp(prefix="rcm_remote_"))
    shutil.copy2(manifest_file, workdir / "manifest.json")
    shutil.copytree(ROOT / "assets", workdir / "assets")

    total = len(loads(manifest_file.read_text(encoding="utf-8")).assets)

    # --- 1. Machine propre ------------------------------------------------- #
    server = _Server(workdir)
    _fresh_appdata()
    cache = LocalAssetCache()
    remote = loads(fetch_manifest(server.base_url))
    outcome = sync_assets(
        remote, cache, lambda p: fetch_asset(server.base_url, p, 20 * 1024 * 1024), 20 * 1024 * 1024
    )
    print(f"1. machine propre : {len(outcome.downloaded)} téléchargés, "
          f"{len(outcome.errors)} erreurs (attendu {total})")
    if not outcome.ok or len(outcome.downloaded) != total:
        print("   X échec", file=sys.stderr)
        server.stop()
        return 1

    # Idempotence : un second sync ne retélécharge rien.
    outcome2 = sync_assets(
        remote, cache, lambda p: fetch_asset(server.base_url, p, 20 * 1024 * 1024), 20 * 1024 * 1024
    )
    print(f"   re-sync : {outcome2.unchanged} inchangés, {len(outcome2.downloaded)} téléchargés")

    # Resolution: a real library item resolves to a downloaded file.
    invalidate_shared_assets()
    item = ConfigItem(
        name="NordicAxe",
        path=Path("C:/fake/Rivals configs/rivals skins/Melee/Battle Axe/NordicAxe.json"),
        kind=KIND_FILE,
    )
    resolved = shared_preview(item)
    print(f"   résolution 'NordicAxe' -> {'OK' if resolved and resolved.is_file() else 'X échec'}")
    if not (resolved and resolved.is_file()):
        server.stop()
        return 1

    # --- 2. Mise à jour ---------------------------------------------------- #
    manifest = json.loads((workdir / "manifest.json").read_text(encoding="utf-8"))
    first_key = next(iter(manifest["assets"]))
    manifest["assets"][first_key]["version"] += 1
    manifest["assets_version"] = manifest["assets_version"] + ".1"
    (workdir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    updated_remote = loads(fetch_manifest(server.base_url))
    outcome3 = sync_assets(
        updated_remote, cache,
        lambda p: fetch_asset(server.base_url, p, 20 * 1024 * 1024), 20 * 1024 * 1024,
    )
    print(f"2. mise à jour : {len(outcome3.updated)} mis à jour (attendu 1 : {first_key})")
    if outcome3.updated != [first_key] or outcome3.downloaded:
        print("   X échec", file=sys.stderr)
        server.stop()
        return 1

    # --- 3. Hors ligne ----------------------------------------------------- #
    server.stop()
    try:
        fetch_manifest(server.base_url, timeout=1.0)
        print("   X le serveur arrêté répond encore ?", file=sys.stderr)
        return 1
    except FetchError:
        pass
    # Cache still resolves without the remote.
    invalidate_shared_assets()
    still = shared_preview(item)
    print(f"3. hors ligne : cache toujours résolu -> {'OK' if still and still.is_file() else 'X échec'}")
    if not (still and still.is_file()):
        return 1

    print("\nOK : machine propre + mise à jour + hors ligne validés.")
    shutil.rmtree(workdir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Simulate an existing user upgrading: old cache -> new manifest -> update."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="rcm_upgrade_"))
    appdata = tmp / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    old_appdata = os.environ.get("APPDATA")
    os.environ["APPDATA"] = str(appdata)
    os.environ.pop("RCM_ASSET_BASE_URL", None)

    from app.assets import asset_base_url

    print("=== SIMULATION UPGRADE UTILISATEUR EXISTANT ===")
    print(f"APPDATA : {appdata}")
    print(f"URL     : {asset_base_url()}")
    print()

    # --- Phase 1: old manifest (smaller set) ---
    from app.assets.manifest import AssetEntry, AssetManifest
    from app.assets.cache import LocalAssetCache
    from app.assets.sync import sync_assets

    old_manifest = AssetManifest(
        schema_version=1,
        assets_version="old.1",
        assets={
            "rivals_skins/melee/katana": AssetEntry(
                key="rivals_skins/melee/katana",
                path="assets/rivals_skins/melee/katana.webp",
                version=1, size=2228,
            ),
            "charms": AssetEntry(
                key="charms",
                path="assets/charms.png",
                version=1, size=38223,
            ),
        },
    )

    cache = LocalAssetCache()
    cache.write_manifest(old_manifest)

    # Download the 2 old assets from the real repo
    from app.assets.fetcher import fetch_asset
    from app.assets import max_asset_bytes
    limit = max_asset_bytes()

    for key, entry in old_manifest.assets.items():
        data = fetch_asset(asset_base_url(), entry.path, limit)
        dest = cache.file_for(entry.path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    state_before = cache.load_state()
    print(f"1. Avant upgrade : {len(state_before.files)} fichiers en cache")
    for k in sorted(state_before.files):
        print(f"   - {k}")
    print()

    # --- Phase 2: fetch the full new manifest ---
    from app.assets.fetcher import fetch_manifest
    from app.assets.manifest import loads

    remote = loads(fetch_manifest(asset_base_url()))

    outcome = sync_assets(
        remote, cache,
        lambda p: fetch_asset(asset_base_url(), p, limit),
        limit,
    )

    print(f"2. Resultat upgrade :")
    print(f"   Nouveaux    : {len(outcome.downloaded)}")
    print(f"   Mis a jour  : {len(outcome.updated)}")
    print(f"   Inchanges   : {outcome.unchanged}")
    print(f"   Erreurs     : {len(outcome.errors)}")
    print(f"   Succes      : {'OUI' if outcome.ok else 'NON'}")
    print()

    # --- Phase 3: verify old assets still cached, new assets added ---
    state_after = cache.load_state()
    print(f"3. Apres upgrade : {len(state_after.files)} fichiers en cache")

    # Old assets still there
    for key in ["rivals_skins/melee/katana", "charms"]:
        present = key in state_after.files
        print(f"   Ancien asset '{key}' : {'OK' if present else 'ABSENT'}")

    # New assets present
    for key in ["rivals_skins/primary/flamethrower", "sky/heaven", "arena_texture/blurry_arena"]:
        present = key in state_after.files
        print(f"   Nouvel asset '{key}' : {'OK' if present else 'ABSENT'}")

    print()

    os.environ["APPDATA"] = old_appdata or ""
    shutil.rmtree(tmp, ignore_errors=True)

    # Final check
    assert outcome.ok
    assert "rivals_skins/melee/katana" in state_after.files
    assert "charms" in state_after.files
    assert "rivals_skins/primary/flamethrower" in state_after.files
    assert "sky/heaven" in state_after.files
    assert "arena_texture/blurry_arena" in state_after.files
    print("OK : Upgrade reussi (anciens + nouveaux assets, zero regression).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
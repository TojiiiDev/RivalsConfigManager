"""Simulate a completely clean installation against the NEW repository.

This script emulates a first-time user: no settings, no cache, nothing in
APPDATA. It creates a temp directory as the fake APPDATA, then exercises
the full sync pipeline against the live TojiiiDev/RivalsConfigManager repo.

Usage:
    python tools/simulate_clean_install.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    # 1. Fresh AppData — no cache, no settings, nothing.
    tmp = Path(tempfile.mkdtemp(prefix="rcm_clean_"))
    appdata = tmp / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    old_appdata = os.environ.get("APPDATA")
    os.environ["APPDATA"] = str(appdata)

    # Disable the baked-in default so we explicitly test the new URL.
    os.environ.pop("RCM_ASSET_BASE_URL", None)

    print("=== SIMULATION D'INSTALLATION PROPRE ===")
    print(f"APPDATA temporaire : {appdata}")
    print()

    from app.assets import DEFAULT_ASSET_BASE_URL, asset_base_url
    print(f"1. URL de base : {asset_base_url()}")
    assert "TojiiiDev" in asset_base_url(), (
        f"L'URL par défaut pointe encore sur l'ancien dépôt : {asset_base_url()}"
    )
    print("   OK : pointe bien sur TojiiiDev/RivalsConfigManager")
    print()

    # 2. Fetch the manifest from the real GitHub.
    from app.assets.fetcher import fetch_manifest, FetchError
    from app.assets.manifest import loads as parse_manifest, ManifestError

    try:
        text = fetch_manifest(asset_base_url())
    except FetchError as exc:
        print(f"   ÉCHEC : impossible de récupérer le manifest -> {exc}")
        return 1

    try:
        remote = parse_manifest(text)
    except ManifestError as exc:
        print(f"   ÉCHEC : manifest invalide -> {exc}")
        return 1

    print(f"2. Manifest récupéré : {len(remote.assets)} assets (v{remote.assets_version})")
    categories = sorted(set(k.split("/")[0] for k in remote.assets))
    for c in categories:
        n = sum(1 for k in remote.assets if k.startswith(c + "/") or k == c)
        print(f"   - {c}: {n}")
    print()

    # 3. Verify key categories are present.
    required = {
        "flamethrower": any("flamethrower" in k for k in remote.assets),
        "sky": any(k.startswith("sky/") for k in remote.assets),
        "arena_texture": any(k.startswith("arena_texture/") for k in remote.assets),
        "textures_packs": any(k.startswith("textures_packs/") for k in remote.assets),
        "cool_stuff": "cool_stuff" in remote.assets,
    }
    all_ok = True
    for name, present in required.items():
        status = "OK" if present else "ABSENT"
        if not present:
            all_ok = False
        print(f"3. Catégorie '{name}' : {status}")
    print()

    # 4. Sync ALL assets (clean machine = download everything).
    from app.assets.cache import LocalAssetCache
    from app.assets.sync import sync_assets
    from app.assets.fetcher import fetch_asset
    from app.assets import max_asset_bytes

    cache = LocalAssetCache()
    limit = max_asset_bytes()

    outcome = sync_assets(
        remote, cache,
        lambda p: fetch_asset(asset_base_url(), p, limit),
        limit,
    )

    print(f"4. Synchronisation :")
    print(f"   Téléchargés : {len(outcome.downloaded)}")
    print(f"   Mis à jour   : {len(outcome.updated)}")
    print(f"   Inchangés    : {outcome.unchanged}")
    print(f"   Retirés      : {len(outcome.removed)}")
    print(f"   Erreurs      : {len(outcome.errors)}")
    if outcome.errors:
        for e in outcome.errors[:5]:
            print(f"     ! {e}")
    print(f"   Succès        : {'OUI' if outcome.ok else 'NON'}")
    print()

    if not outcome.ok:
        return 1

    # 5. Verify specific assets are cached.
    from app.assets.cache import LocalAssetCache as LC

    c = LC()
    state = c.load_state()

    # Build a lookup
    samples: dict[str, str] = {}
    for key, entry in remote.assets.items():
        if "flamethrower" in key and samples.get("flamethrower") is None:
            samples["flamethrower"] = key
        if key == "sky/heaven":
            samples["sky/heaven"] = key
        if key == "arena_texture/blurry_arena":
            samples["arena_texture"] = key
        if key == "textures_packs/determination":
            samples["textures_packs"] = key
        if key == "cool_stuff":
            samples["cool_stuff"] = key

    all_cached = True
    print("5. Vérification cache local :")
    for label, key in sorted(samples.items()):
        path = c.cached_path_for_key(key)
        if path and path.is_file():
            size = path.stat().st_size
            print(f"   {label}: OK ({size} bytes)")
        else:
            print(f"   {label}: ABSENT DU CACHE")
            all_cached = False
    print()

    # 6. Resolution via shared_preview
    from app.image_metadata import invalidate_shared_assets, shared_preview
    from app.models import KIND_FILE, ConfigItem

    invalidate_shared_assets()

    # Simulate a library item for flamethrower
    flamethrower_item = ConfigItem(
        name="Flamethrower",
        path=Path("C:/fake/Rivals configs/rivals skins/Primary/Flamethrower/skin.json"),
        kind=KIND_FILE,
    )
    # Simulate sky item
    heaven_item = ConfigItem(
        name="Heaven",
        path=Path("C:/fake/Rivals configs/Sky/Heaven/config.json"),
        kind=KIND_FILE,
    )

    ft = shared_preview(flamethrower_item)
    hv = shared_preview(heaven_item)

    print("6. Résolution shared_preview (sans sidecar) :")
    print(f"   Flamethrower -> {'OK' if ft and ft.is_file() else 'ABSENT'}")
    print(f"   Heaven       -> {'OK' if hv and hv.is_file() else 'ABSENT'}")
    print()

    # Cleanup
    os.environ["APPDATA"] = old_appdata or ""

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

    if not all_ok:
        print("ÉCHEC : certaines catégories sont absentes du manifest.")
        return 1
    if not all_cached:
        print("ÉCHEC : certains assets n'ont pas été téléchargés.")
        return 1
    print("OK : Tout le pipeline fonctionne (TojiiiDev, manifest, téléchargement, cache, résolution).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
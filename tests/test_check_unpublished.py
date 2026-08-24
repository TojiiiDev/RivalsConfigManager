"""Tests for ``tools/check_unpublished_assets.py`` — the pre-release guard.

These tests simulate a library with sidecars and a manifest, then verify the
check correctly reports published / unpublished / stale entries.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "check_unpublished_assets.py"


def _run(tmp: Path, library: Path, manifest: dict, *, expect_ok: bool) -> str:
    """Run the check tool via subprocess, patching project root to tmp."""
    manifest_path = tmp / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8-sig")

    # Build a runner that patches ROOT then calls main with the right args.
    project = str(SCRIPT.parent.parent)
    runner = (
        f"import sys\n"
        f"sys.path.insert(0, {project!r})\n"
        f"import tools.check_unpublished_assets as tool\n"
        f"tool.ROOT = tool.Path({str(tmp)!r})\n"
        f"# Simulate argv: tool name + --library\n"
        f"import argparse\n"
        f"parser = argparse.ArgumentParser()\n"
        f"parser.add_argument('--library', type=tool.Path, default=None)\n"
        f"parser.add_argument('--json', action='store_true', default=False)\n"
        f"known, _ = parser.parse_known_args()\n"
        f"tool.sys.argv = ['tool', '--library', {str(library)!r}]\n"
        f"ec = tool.main()\n"
        f"sys.exit(ec)\n"
    )
    env = {**dict(__import__("os").environ), "APPDATA": str(tmp / "AppData")}
    result = subprocess.run(
        [sys.executable, "-c", runner],
        capture_output=True,
        text=True,
        cwd=str(tmp),
        env=env,
    )
    combined = result.stdout + result.stderr
    if expect_ok:
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
    else:
        assert result.returncode != 0, (
            f"Expected non-zero exit, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return combined


class TestCheckUnpublished:
    """Core validation logic."""

    def test_empty_manifest_empty_library(self, tmp_path):
        """Nothing to report when both are empty."""
        library = tmp_path / "library"
        library.mkdir()
        result = _run(tmp_path, library, {
            "schema_version": 1, "assets_version": "x", "assets": {},
        }, expect_ok=True)
        assert "NON PUBLIEE" not in result

    def test_published_image_not_reported(self, tmp_path):
        """An image that IS in the manifest is not flagged."""
        library = tmp_path / "library"
        library.mkdir()
        weapons = library / "weapons"
        weapons.mkdir()
        (weapons / "assault_rifle.image.json").write_text(json.dumps({
            "type": "local", "source": "x", "local_path": "image_cache/abc.png",
        }), encoding="utf-8")
        manifest = {
            "schema_version": 1, "assets_version": "1",
            "assets": {
                "weapons/assault_rifle": {
                    "path": "assets/weapons/assault_rifle.webp", "version": 1,
                    "size": 100, "sha256": "aa",
                }
            },
        }
        result = _run(tmp_path, library, manifest, expect_ok=True)
        assert "NON PUBLIEE" not in result

    def test_unpublished_image_reported(self, tmp_path):
        """A library image not in the manifest is flagged."""
        library = tmp_path / "library"
        library.mkdir()
        weapons = library / "weapons"
        weapons.mkdir()
        (weapons / "flamethrower.image.json").write_text(json.dumps({
            "type": "local", "source": "x", "local_path": "image_cache/abc.png",
        }), encoding="utf-8")
        manifest = {
            "schema_version": 1, "assets_version": "1",
            "assets": {
                "weapons/assault_rifle": {
                    "path": "assets/weapons/assault_rifle.webp", "version": 1,
                    "size": 100, "sha256": "aa",
                }
            },
        }
        result = _run(tmp_path, library, manifest, expect_ok=False)
        assert "flamethrower" in result.lower()

    def test_stale_entries_reported(self, tmp_path):
        """Manifest entries without library images are flagged as stale."""
        library = tmp_path / "library"
        library.mkdir()
        (library / "empty_folder").mkdir(parents=True)
        manifest = {
            "schema_version": 1, "assets_version": "1",
            "assets": {
                "old/deleted_item": {
                    "path": "assets/old/deleted_item.webp", "version": 1,
                    "size": 100, "sha256": "aa",
                }
            },
        }
        result = _run(tmp_path, library, manifest, expect_ok=True)
        assert "obsolete" in result.lower()

    def test_folder_image_json(self, tmp_path):
        """Folder-level image.json sidecar is detected."""
        library = tmp_path / "library"
        library.mkdir()
        sky = library / "sky"
        sky.mkdir()
        (sky / "image.json").write_text(json.dumps({
            "type": "local", "source": "x", "local_path": "image_cache/sky.png",
        }), encoding="utf-8")
        manifest = {
            "schema_version": 1, "assets_version": "1", "assets": {},
        }
        result = _run(tmp_path, library, manifest, expect_ok=False)
        assert "sky" in result.lower()

    def test_json_output(self, tmp_path):
        """--json flag returns machine-readable output."""
        library = tmp_path / "library"
        library.mkdir()
        weapons = library / "weapons"
        weapons.mkdir()
        (weapons / "new_gun.image.json").write_text(json.dumps({
            "type": "local", "source": "x", "local_path": "image_cache/x.png",
        }), encoding="utf-8")
        env = {**dict(__import__("os").environ), "APPDATA": str(tmp_path / "AppData")}
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--json", "--library", str(library)],
            capture_output=True, text=True, cwd=str(tmp_path), env=env,
        )
        output = result.stdout.strip()
        data = json.loads(output)
        assert data["status"] == "unpublished"
        assert len(data["unpublished"]) >= 1
        assert data["unpublished"][0]["key"] == "weapons/new_gun"


class TestKeyMismatchDetection:
    """Regression: typo-corrected folder names cause key mismatches."""

    def test_typo_correction_detected(self, tmp_path):
        """When 'assult_rifle' (old manifest) becomes 'assault_rifle' (library)."""
        library = tmp_path / "library"
        library.mkdir()
        ar = library / "Assault Rifle"
        ar.mkdir()
        (ar / "ak47.image.json").write_text(json.dumps({
            "type": "local", "source": "x", "local_path": "image_cache/x.png",
        }))
        manifest = {
            "schema_version": 1, "assets_version": "1",
            "assets": {
                "assult_rifle/ak47": {
                    "path": "assets/assult_rifle/ak47.webp", "version": 1,
                    "size": 100, "sha256": "aa",
                }
            },
        }
        result = _run(tmp_path, library, manifest, expect_ok=False)
        assert "assault" in result.lower()


class TestNewCategoryEntirelyMissing:
    """Entire library folders that never made it into the manifest."""

    def test_missing_category(self, tmp_path):
        """A 'sky' folder with sidecars but no manifest entry is flagged."""
        library = tmp_path / "library"
        library.mkdir()
        sky = library / "Sky"
        sky.mkdir()
        (sky / "cloudless_sky.image.json").write_text(json.dumps({
            "type": "local", "source": "x", "local_path": "image_cache/c.png",
        }))
        (sky / "dark_sky.image.json").write_text(json.dumps({
            "type": "local", "source": "x", "local_path": "image_cache/d.png",
        }))
        manifest = {
            "schema_version": 1, "assets_version": "1",
            "assets": {
                "rivals_skins/melee/katana": {
                    "path": "assets/katana.webp", "version": 1,
                    "size": 100, "sha256": "aa",
                }
            },
        }
        result = _run(tmp_path, library, manifest, expect_ok=False)
        assert "cloudless_sky" in result.lower()
        assert "dark_sky" in result.lower()
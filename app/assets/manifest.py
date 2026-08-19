"""Asset manifest — parsing, validation and versioning.

The manifest is the single source of truth for which shared assets exist,
where they live and which version each one has. It is fetched from the asset
repository and compared against a local copy so the app can download only
what changed.

Format (schema 1)::

    {
        "schema_version": 1,
        "assets_version": "2026.08.19.1",
        "assets": {
            "assault_rifle": {
                "path": "assets/weapons/assault_rifle.png",
                "version": 3,
                "size": 12345,
                "sha256": "…"
            }
        }
    }

* ``schema_version`` — the manifest *format* version (unknown values are
  rejected so a newer, incompatible manifest never corrupts the cache).
* ``assets_version`` — the asset *release* version, independent of the app
  version: bumping it (or an asset's ``version``) never requires a new exe.
* ``assets`` — ``key -> entry``. The key is a stable logical id; ``path`` is
  relative to the repository root and validated by the security module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .security import SecurityError, sanitize_asset_path

#: The manifest format version this application understands. Older manifests
#: with the same schema are accepted; unknown/newer ones are rejected.
SUPPORTED_SCHEMA_VERSION = 1


class ManifestError(Exception):
    """The manifest is unreadable or invalid — never crash on it."""


@dataclass(frozen=True)
class AssetEntry:
    """One asset described by the manifest."""

    key: str
    path: str          # validated relative path (forward slashes)
    version: int
    size: int | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class AssetManifest:
    """A parsed, validated manifest."""

    schema_version: int
    assets_version: str
    assets: dict[str, AssetEntry] = field(default_factory=dict)

    def entry(self, key: str) -> AssetEntry | None:
        return self.assets.get(key)


def _require_dict(data: object) -> dict:
    if not isinstance(data, dict):
        raise ManifestError("le manifest n'est pas un objet JSON")
    return data


def parse_manifest(data: object) -> AssetManifest:
    """Parse and validate a manifest dict into an :class:`AssetManifest`."""
    root = _require_dict(data)

    schema_version = root.get("schema_version")
    if not isinstance(schema_version, int) or schema_version < 1:
        raise ManifestError("schema_version manquant ou invalide")
    if schema_version > SUPPORTED_SCHEMA_VERSION:
        raise ManifestError(
            f"manifest trop récent (schema {schema_version}) — "
            "mise à jour de l'application requise"
        )

    assets_version = root.get("assets_version")
    if not isinstance(assets_version, str) or not assets_version.strip():
        raise ManifestError("assets_version manquant ou invalide")

    raw_assets = root.get("assets", {})
    if not isinstance(raw_assets, dict):
        raise ManifestError("« assets » doit être un objet")

    assets: dict[str, AssetEntry] = {}
    for key, value in raw_assets.items():
        entry = _parse_entry(key, value)
        assets[entry.key] = entry

    return AssetManifest(
        schema_version=schema_version,
        assets_version=assets_version,
        assets=assets,
    )


def _parse_entry(key: object, value: object) -> AssetEntry:
    if not isinstance(key, str) or not key.strip():
        raise ManifestError("clé d'asset invalide")
    if not isinstance(value, dict):
        raise ManifestError(f"entrée invalide pour l'asset « {key} »")

    path = value.get("path")
    if not isinstance(path, str):
        raise ManifestError(f"« {key} » : chemin manquant")
    try:
        clean_path = sanitize_asset_path(path)
    except SecurityError as exc:
        raise ManifestError(f"« {key} » : {exc}") from exc

    version = value.get("version")
    if not isinstance(version, int) or version < 1:
        raise ManifestError(f"« {key} » : version invalide")

    size = value.get("size")
    if size is not None and (not isinstance(size, int) or size < 0):
        raise ManifestError(f"« {key} » : taille invalide")

    sha256 = value.get("sha256")
    if sha256 is not None and (not isinstance(sha256, str) or not sha256):
        raise ManifestError(f"« {key} » : sha256 invalide")

    return AssetEntry(
        key=key,
        path=clean_path,
        version=version,
        size=size,
        sha256=sha256,
    )


def loads(text: str) -> AssetManifest:
    """Parse a manifest JSON string."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest illisible : {exc}") from exc
    return parse_manifest(data)


def load(path: Path) -> AssetManifest:
    """Read and parse a manifest file (``None``-safe: never raises IOError)."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise ManifestError(f"manifest illisible : {exc}") from exc
    return loads(text)

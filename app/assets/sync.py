"""Asset synchronisation — compare manifests and download only what changed.

The sync is **incremental and defensive**:

* it never re-downloads a file whose version is already cached;
* it downloads only new/updated assets;
* it removes cached files whose asset disappeared from the remote manifest;
* a failure on one asset never aborts the others, and never crashes;
* the local manifest is written to reflect **only what is actually on disk**,
  so an interrupted/partial download is retried on the next sync.

The network I/O is injected as a ``fetcher`` callable (``fetcher(path) ->
bytes``) so the engine is fully testable without the Internet and can be
driven from a background thread.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .cache import LocalAssetCache, LocalCacheState
from .manifest import AssetEntry, AssetManifest
from .security import validate_image_bytes

logger = logging.getLogger(__name__)


@dataclass
class SyncPlan:
    """What a sync must do, computed from two manifests."""

    to_download: list[tuple[str, AssetEntry]] = field(default_factory=list)
    to_remove: list[str] = field(default_factory=list)
    unchanged: int = 0


@dataclass
class SyncOutcome:
    """Result of a sync run."""

    ok: bool
    offline: bool = False            # the manifest could not be fetched at all
    downloaded: list[str] = field(default_factory=list)   # new assets
    updated: list[str] = field(default_factory=list)      # re-downloaded assets
    removed: list[str] = field(default_factory=list)      # dropped from cache
    errors: list[str] = field(default_factory=list)
    unchanged: int = 0

    def summary(self) -> str:
        parts = []
        if self.downloaded:
            parts.append(f"{len(self.downloaded)} nouveau(x)")
        if self.updated:
            parts.append(f"{len(self.updated)} mis à jour")
        if self.removed:
            parts.append(f"{len(self.removed)} retiré(s)")
        if self.unchanged:
            parts.append(f"{self.unchanged} inchangé(s)")
        return ", ".join(parts) if parts else "aucun changement"


def compute_plan(remote: AssetManifest, state: LocalCacheState) -> SyncPlan:
    """Diff the remote manifest against the local cache state."""
    plan = SyncPlan()
    local = state.manifest
    local_assets = local.assets if local is not None else {}

    for key, entry in remote.assets.items():
        local_entry = local_assets.get(key)
        if local_entry is not None and local_entry.version == entry.version:
            plan.unchanged += 1
            continue
        if local_entry is not None:
            plan.to_download.append((key, entry))
        else:
            plan.to_download.append((key, entry))

    if local is not None:
        for key in local_assets:
            if key not in remote.assets:
                plan.to_remove.append(key)

    return plan


def sync_assets(
    remote: AssetManifest,
    cache: LocalAssetCache,
    fetcher,
    max_bytes: int,
    on_progress=None,
) -> SyncOutcome:
    """Execute the sync plan against ``cache``, using ``fetcher`` for bytes.

    ``fetcher(relative_path) -> bytes`` must raise on any network/HTTP error.
    ``on_progress(done, total)`` (optional) is called after each download
    attempt so a UI can show progress. The local manifest is updated to
    reflect exactly what is present.
    """
    outcome = SyncOutcome(ok=True)
    state = cache.load_state()
    plan = compute_plan(remote, state)

    # Kept entries = everything still valid on disk after this run.
    kept: dict[str, AssetEntry] = {}
    local_assets = state.manifest.assets if state.manifest is not None else {}

    # 1. Carry over the assets that are already correct (and still listed).
    for key, entry in remote.assets.items():
        local_entry = local_assets.get(key)
        if (
            local_entry is not None
            and local_entry.version == entry.version
            and cache.has_file(entry.path)
        ):
            kept[key] = entry
            outcome.unchanged += 1

    # 2. Download new/updated assets (best effort, one at a time).
    total = len(plan.to_download)
    done = 0
    for key, entry in plan.to_download:
        try:
            data = fetcher(entry.path)
            ext = validate_image_bytes(data, max_bytes)
            if ext is None:
                outcome.errors.append(f"{key} : contenu invalide ou trop volumineux")
            else:
                dest = cache.file_for(entry.path)
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_name(dest.name + ".part")
                tmp.write_bytes(data)
                tmp.replace(dest)
                kept[key] = entry
                if local_assets.get(key) is None:
                    outcome.downloaded.append(key)
                else:
                    outcome.updated.append(key)
        except Exception as exc:  # noqa: BLE001 - one bad asset never aborts the sync
            logger.warning("Téléchargement d'asset échoué (%s) : %s", key, exc)
            outcome.errors.append(f"{key} : {exc}")
            outcome.ok = False
        done += 1
        if on_progress is not None:
            on_progress(done, total)

    # 3. Remove cached files whose asset disappeared from the manifest.
    for key in plan.to_remove:
        entry = local_assets.get(key)
        if entry is not None:
            try:
                cache.file_for(entry.path).unlink()
            except OSError:
                pass
            outcome.removed.append(key)

    # 4. Persist the local manifest = remote metadata, but only the entries
    #    that are actually present on disk (retried next time otherwise).
    effective = AssetManifest(
        schema_version=remote.schema_version,
        assets_version=remote.assets_version,
        assets=kept,
    )
    cache.write_manifest(effective)
    return outcome

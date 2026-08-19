"""Fleasion integration: activation + automatic configuration selection.

Inspection of the real installation (Fleasion v2.1.0 on this machine):

* The configurations live in ``<FleasionNT>/configs/*.json`` — a JSON whose
  stem is the configuration name (``key handgun.json`` -> config "key
  handgun"). The ``config/`` folder is *not* referenced anywhere in
  Fleasion's logs; the app only ever opens ``configs/``.
* The selected/enabled configurations are recorded in
  ``<FleasionNT>/settings.json`` under ``enabled_configs`` (list of names)
  and ``last_config`` (most recently selected). Fleasion's own log lines
  ``[Config] Enabled: X`` / ``[Config] Disabled: X`` map one-to-one to
  edits of ``enabled_configs``.

So automatic selection is possible through Fleasion's **normal configuration
mechanism** (a JSON settings file), with no injection and no game client
tampering:

1. copy the configuration files into ``configs/``,
2. back up ``settings.json``,
3. add the config name to ``enabled_configs`` and set ``last_config``,
4. re-read the file and verify the selection was really saved.

Hot reload (``restart=True``, used by the Activate/Deactivate buttons):
Fleasion only reads ``settings.json`` **at startup** — a running instance
never watches the file (proven by the user's real test: the checkbox stayed
unchanged). To make a *running* Fleasion pick up the change, the process is
closed cleanly, ``settings.json`` is re-written and Fleasion is relaunched;
the selection is then confirmed through Fleasion's **own log** (a fresh
``[Config] Enabled: <name>`` line). "Activé" is only displayed when that
confirmation exists — never a false success.

Safety rules (from the spec): the file is identified precisely, backed up
before any modification, validated before writing, only the two necessary
values are changed, and the result is verified. If no reliable
``settings.json`` is found, activation falls back to a plain copy and
reports that manual selection in Fleasion is required.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import shutil

from .backup_manager import BackupInfo, BackupManager
from .file_manager import CopyResult, FileManager
from .i18n import t
from .models import ConfigItem
from .recycle import move_to_recycle_bin
from .trash import TrashError

#: How many parent folders to walk when looking for Fleasion's settings.json.
_MAX_WALK_LEVELS = 6


@dataclass
class FleasionInfo:
    """What the manager knows about the local Fleasion installation."""

    found: bool = False                     # a usable settings.json was found
    root: Path | None = None                # the FleasionNT root folder
    config_dir: Path | None = None          # folder receiving the config files
    settings_path: Path | None = None       # settings.json (never None when found)
    enabled_configs: list[str] = field(default_factory=list)
    last_config: str | None = None


@dataclass
class DeactivateOutcome:
    """Result of removing a configuration from active use."""

    ok: bool = False
    removed: list[str] = field(default_factory=list)
    backed_up: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    selection_cleared: bool = False   # settings.json updated and verified

    def summary(self) -> str:
        parts = []
        if self.removed:
            n = len(self.removed)
            suffix = "s" if n > 1 else ""
            parts.append(
                t("outcome.deactivated_files", count=n, s=suffix)
            )
        if self.selection_cleared:
            parts.append(t("outcome.selection_removed"))
        if not parts:
            parts.append(t("outcome.nothing_deactivated"))
        return ", ".join(parts)


@dataclass
class ActivationOutcome:
    """Result of activating a configuration in Fleasion."""

    ok: bool = False
    copied: list[str] = field(default_factory=list)
    backed_up: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    selected: bool = False                   # selection confirmed after activation
    needs_manual_selection: bool = False     # files copied, selection not possible/confirmed

    def summary(self) -> str:
        parts = []
        if self.copied:
            n = len(self.copied)
            suffix = "s" if n > 1 else ""
            parts.append(t("outcome.copied_files", count=n, s=suffix))
        if self.backed_up:
            n = len(self.backed_up)
            suffix = "s" if n > 1 else ""
            parts.append(t("outcome.backed_up_files", count=n, s=suffix))
        if not parts:
            parts.append(t("outcome.nothing_copied"))
        return ", ".join(parts)


@dataclass
class ClearConfigsOutcome:
    """Result of moving selected Fleasion configs to the Recycle Bin."""

    ok: bool = False
    moved: list[str] = field(default_factory=list)      # config names (stems)
    backed_up: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    selection_updated: bool = False   # enabled_configs / last_config cleaned

    def summary(self) -> str:
        parts = []
        if self.moved:
            n = len(self.moved)
            suffix = "s" if n > 1 else ""
            parts.append(
                t("outcome.moved_to_trash", count=n, s=suffix)
            )
        if self.selection_updated:
            parts.append(t("outcome.selection_updated"))
        return ", ".join(parts) if parts else t("outcome.nothing_to_do")


def config_name(item: ConfigItem) -> str:
    """The name under which Fleasion knows this configuration.

    File configurations are named after their JSON stem (Fleasion lists
    ``configs/<stem>.json``). Folder configurations keep their JSON names
    after copying, so the first JSON's stem is used when available.
    """
    if not item.is_folder:
        return item.path.stem
    jsons = [p for p in item.files if p.suffix.lower() == ".json"]
    if jsons:
        return jsons[0].stem
    return item.name


class FleasionManager:
    def __init__(self, configured_dir: Path | None, backup_manager: BackupManager) -> None:
        self.configured_dir = Path(configured_dir) if configured_dir else None
        self.backup_manager = backup_manager

    # ------------------------------------------------------------------ #
    def detect(self) -> FleasionInfo:
        """Locate Fleasion's settings.json by walking up from the configured
        folder, and derive the real config folder (``configs/``)."""
        info = FleasionInfo()
        if self.configured_dir is None:
            return info

        start = self.configured_dir
        current = start
        for _ in range(_MAX_WALK_LEVELS):
            candidate = current / "settings.json"
            if candidate.is_file():
                data = _read_settings(candidate)
                if data is not None and ("enabled_configs" in data or "last_config" in data):
                    info.found = True
                    info.root = current
                    info.settings_path = candidate
                    info.enabled_configs = list(data.get("enabled_configs") or [])
                    info.last_config = data.get("last_config")
                elif data is None:
                    # The file exists but is unreadable/corrupt: mark it as
                    # found so activation reports the problem instead of
                    # silently falling back to a plain copy.
                    info.found = True
                    info.root = current
                    info.settings_path = candidate
                else:
                    # A settings.json that is not Fleasion's: keep walking.
                    parent = current.parent
                    if parent == current:
                        break
                    current = parent
                    continue
                # The real config folder is ``configs/`` next to the settings
                # file; fall back to the configured folder.
                configs = current / "configs"
                info.config_dir = configs if configs.is_dir() else start
                return info
            parent = current.parent
            if parent == current:
                break
            current = parent

        # No settings.json found: keep the configured folder (legacy
        # behaviour — pure copy, manual selection required).
        info.config_dir = start
        return info

    # ------------------------------------------------------------------ #
    def status(self, item: ConfigItem) -> str:
        """Current activation state of a configuration.

        Returns ``"active"`` (selected in Fleasion), ``"copied"`` (files
        present but not selected) or ``"inactive"``.
        """
        info = self.detect()
        name = config_name(item)
        if name in info.enabled_configs:
            return "active"
        if info.config_dir is not None and (info.config_dir / f"{name}.json").exists():
            return "copied"
        return "inactive"

    # ------------------------------------------------------------------ #
    def activate(
        self,
        item: ConfigItem,
        file_manager: FileManager,
        backup_before_overwrite: bool = True,
        restart: bool = False,
    ) -> ActivationOutcome:
        """Copy the configuration into Fleasion and select it.

        Selection only happens when Fleasion's ``settings.json`` is found
        and valid; it is backed up first, updated, and verified afterwards.
        """
        outcome = ActivationOutcome()
        info = self.detect()
        config_dir = info.config_dir
        if config_dir is None:
            outcome.errors.append(t("toast.fleasion_not_configured_short"))
            return outcome

        # 1. Copy the files --------------------------------------------------
        copy_result: CopyResult = file_manager.activate(
            item, config_dir, backup_before_overwrite
        )
        outcome.copied = list(copy_result.copied)
        outcome.backed_up = list(copy_result.backed_up)
        if not copy_result.ok:
            outcome.errors = list(copy_result.errors)
            return outcome

        # 2. Without a reliable settings.json: copy only ----------------------
        if not info.found or info.settings_path is None:
            outcome.ok = True
            outcome.needs_manual_selection = True
            return outcome

        # 3. Back up settings.json before any modification --------------------
        try:
            self.backup_manager.create_backup([info.settings_path])
            if str(info.settings_path.name) not in outcome.backed_up:
                outcome.backed_up.append(info.settings_path.name)
        except (OSError, ValueError):
            # Backing up settings must not silently fail: selection is the
            # point of this flow, so a failure here aborts it cleanly.
            outcome.errors.append(t("fleasion.backup_selection_failed"))
            return outcome

        # 4. Read, validate and update only the necessary values ---------------
        name = config_name(item)
        data = _read_settings(info.settings_path)
        if data is None:
            outcome.errors.append(t("fleasion.read_failed"))
            outcome.needs_manual_selection = True
            outcome.ok = True
            return outcome

        enabled = data.get("enabled_configs")
        if not isinstance(enabled, list):
            outcome.errors.append(t("fleasion.no_enabled_list"))
            outcome.needs_manual_selection = True
            outcome.ok = True
            return outcome

        changed = False
        if name not in enabled:
            enabled.append(name)
            changed = True
        if data.get("last_config") != name:
            data["last_config"] = name
            changed = True

        if changed:
            if not _write_settings(info.settings_path, data):
                outcome.errors.append(t("fleasion.write_failed"))
                outcome.needs_manual_selection = True
                outcome.ok = True
                return outcome

        # 5. Verify the selection was really saved -----------------------------
        verify = _read_settings(info.settings_path)
        if verify is None or name not in (verify.get("enabled_configs") or []):
            outcome.errors.append(t("fleasion.verify_failed"))
            outcome.needs_manual_selection = True
            outcome.ok = True
            return outcome

        outcome.selected = True
        outcome.ok = True

        # 6. Hot reload: make a *running* Fleasion pick up the selection -------
        # Fleasion only reads settings.json at startup, so a running instance
        # is closed cleanly, settings.json is rewritten and Fleasion is
        # relaunched; the selection is confirmed through Fleasion's own log
        # ("[Config] Enabled: <name>"). Never claim "active" without that
        # confirmation. When Fleasion is not running there is nothing to
        # restart: the saved selection applies at its next launch.
        if restart:
            confirmed, errors = self._hot_restart(
                info, name, data, expect_active=True
            )
            outcome.errors.extend(errors)
            if not confirmed and errors:
                outcome.selected = False
                outcome.needs_manual_selection = True
        return outcome

    # ------------------------------------------------------------------ #
    def deactivate(
        self,
        item: ConfigItem,
        file_manager: FileManager,
        backup_before_overwrite: bool = True,
        restart: bool = False,
    ) -> DeactivateOutcome:
        """Retire la configuration de l'usage actif.

        La sélection Fleasion est retirée (settings.json, sauvegardé puis
        vérifié) et les fichiers copiés dans le dossier actif sont supprimés
        après sauvegarde. La bibliothèque conserve tout : la configuration
        peut être réactivée à tout moment.
        """
        outcome = DeactivateOutcome()
        info = self.detect()
        config_dir = info.config_dir
        if config_dir is None:
            outcome.errors.append(t("toast.fleasion_not_configured_short"))
            return outcome
        name = config_name(item)

        # 1. Remove the copied files (backed up first). Best effort: a
        # locked file is reported, the selection removal still proceeds.
        result = file_manager.remove_copies(item, config_dir, backup_before_overwrite)
        outcome.removed = list(result.removed)
        if result.errors:
            outcome.errors.extend(result.errors)

        # 2. Remove the selection when settings.json is readable.
        if info.found and info.settings_path is not None:
            try:
                self.backup_manager.create_backup([info.settings_path])
                if info.settings_path.name not in outcome.backed_up:
                    outcome.backed_up.append(info.settings_path.name)
            except (OSError, ValueError):
                outcome.errors.append(t("fleasion.backup_failed"))
                outcome.ok = not outcome.errors
                return outcome

            data = _read_settings(info.settings_path)
            if data is None:
                outcome.errors.append(t("fleasion.read_failed2"))
            else:
                enabled = data.get("enabled_configs")
                if not isinstance(enabled, list):
                    outcome.errors.append(t("fleasion.no_enabled_list2"))
                else:
                    changed = False
                    if name in enabled:
                        enabled.remove(name)
                        changed = True
                    if data.get("last_config") == name:
                        data["last_config"] = enabled[0] if enabled else None
                        changed = True
                    if changed:
                        if _write_settings(info.settings_path, data):
                            verify = _read_settings(info.settings_path)
                            if verify is None or name in (verify.get("enabled_configs") or []):
                                outcome.errors.append(t("fleasion.deselect_verify_failed"))
                            else:
                                outcome.selection_cleared = True
                        else:
                            outcome.errors.append(t("fleasion.deselect_write_failed"))

        # 3. Hot reload: make a *running* Fleasion drop the selection. --------
        # Same rule as activation: the deactivation is only confirmed when
        # the restarted Fleasion no longer loads the configuration (its log
        # shows no "[Config] Enabled: <name>" line and settings.json is
        # clean). If Fleasion is not running, nothing to restart.
        if restart and outcome.selection_cleared:
            confirmed, errors = self._hot_restart(
                info, name, data, expect_active=False
            )
            outcome.errors.extend(errors)
            if not confirmed and errors:
                outcome.ok = False
        outcome.ok = not outcome.errors
        return outcome

    # ------------------------------------------------------------------ #
    def list_configs(self) -> list[str]:
        """Les vrais noms de configurations présents dans le dossier actif
        de Fleasion (``configs/``) — jamais une liste codée en dur."""
        info = self.detect()
        root = info.root
        if not (info.found and root is not None):
            return []
        configs = root / "configs"
        if not configs.is_dir():
            return []
        return sorted(
            p.stem for p in configs.iterdir()
            if p.is_file() and p.suffix.lower() == ".json"
        )

    def clear_configs(self, names: list[str], recycler=None, trash=None) -> ClearConfigsOutcome:
        """Déplacer les configurations sélectionnées du dossier actif de
        Fleasion vers la **Corbeille interne de l'application** (jamais de
        suppression définitive), puis mettre à jour la sélection.

        ``trash`` est la Corbeille interne (``app/trash.Trash``) utilisée
        par défaut ; ``recycler`` reste disponible pour les tests et les
        cas particuliers. Règles de sécurité : la structure réelle est
        détectée (settings.json + ``configs/``) ; chaque nom est validé
        (jamais de ``..`` ni de séparateur — rien ne sort de ``configs/``) ;
        settings.json est sauvegardé avant toute modification ; seul un
        fichier sélectionné est touché ; la sélection mise à jour est
        vérifiée après écriture.
        """
        outcome = ClearConfigsOutcome()
        info = self.detect()
        if recycler is None:
            if trash is not None:
                active = set(info.enabled_configs)

                def recycler(file: Path) -> None:
                    trash.delete_path(file, was_active=file.stem in active)
            else:
                recycler = move_to_recycle_bin

        root = info.root
        if not (info.found and info.settings_path is not None and root is not None):
            outcome.errors.append(t("fleasion.structure_not_found"))
            return outcome
        configs = root / "configs"
        if not configs.is_dir():
            outcome.errors.append(t("fleasion.active_folder_not_found"))
            return outcome

        files: list[Path] = []
        for name in names:
            if not name or name != Path(name).name or "/" in name or "\\" in name:
                outcome.errors.append(t("fleasion.invalid_name", name=name))
                continue
            file = configs / f"{name}.json"
            if file.is_file():
                files.append(file)
        if outcome.errors:
            return outcome
        if not files:
            outcome.ok = True
            return outcome

        # 1. Sauvegarder settings.json avant toute modification.
        try:
            self.backup_manager.create_backup([info.settings_path])
            outcome.backed_up.append(info.settings_path.name)
        except (OSError, ValueError):
            outcome.errors.append(t("fleasion.backup_aborted"))
            return outcome

        # 2. Déplacer les fichiers sélectionnés vers la Corbeille interne.
        # Toute erreur interrompt proprement l'opération.
        for file in files:
            try:
                recycler(file)
            except (OSError, TrashError) as exc:
                outcome.errors.append(
                    t(
                        "fleasion.interrupted",
                        error=exc,
                        count=len(outcome.moved),
                    )
                )
                return outcome
            outcome.moved.append(file.stem)

        # 3. Mettre à jour la sélection et vérifier.
        data = _read_settings(info.settings_path)
        if data is None:
            outcome.errors.append(t("fleasion.read_failed2"))
        else:
            removed = set(outcome.moved)
            current = list(data.get("enabled_configs") or [])
            new_enabled = [c for c in current if c not in removed]
            changed = new_enabled != current
            last = data.get("last_config")
            if last in removed:
                data["last_config"] = None
                changed = True
            if changed:
                data["enabled_configs"] = new_enabled
                if _write_settings(info.settings_path, data):
                    verify = _read_settings(info.settings_path)
                    if verify is None or any(
                        c in removed for c in (verify.get("enabled_configs") or [])
                    ) or (verify.get("last_config") in removed):
                        outcome.errors.append(t("fleasion.verify_failed"))
                    else:
                        outcome.selection_updated = True
                else:
                    outcome.errors.append(t("fleasion.write_failed"))
            else:
                outcome.selection_updated = True
        outcome.ok = not outcome.errors
        return outcome

    # ------------------------------------------------------------------ #
    def _hot_restart(
        self,
        info: FleasionInfo,
        name: str,
        data: dict,
        expect_active: bool,
    ) -> tuple[bool, list[str]]:
        """Apply a selection change to a *running* Fleasion instance.

        Returns ``(confirmed, errors)``.

        * ``confirmed=True`` — Fleasion really loaded (activation) or no
          longer loads (deactivation) the configuration, verified through
          its own log.
        * ``confirmed=False, errors=[]`` — Fleasion is not running: the
          saved selection applies at its next launch, nothing to restart.
        * ``confirmed=False, errors=[...]`` — the restart could not be
          performed or verified: never a false success.
        """
        from . import fleasion_restart as fr

        if info.root is None or info.settings_path is None:
            return False, [t("fleasion.restart_no_structure")]
        root = info.root

        processes = fr.find_fleasion_processes()
        if processes is None:
            return False, [t("fleasion.restart_cannot_check")]
        if not processes:
            # Fleasion n'est pas lancé : la sélection est enregistrée et sera
            # appliquée à son prochain démarrage — rien à redémarrer.
            return False, []

        exe: Path | None = None
        pids: list[int] = []
        for process in processes:
            pids.append(int(process["pid"]))
            if exe is None and process.get("exe"):
                exe = Path(process["exe"])
        if exe is None or not exe.is_file():
            return False, [t("fleasion.restart_no_exe")]

        log_path = root / "logs" / "fleasion.log"
        if not log_path.is_file():
            return False, [t("fleasion.restart_no_log")]
        offset = log_path.stat().st_size

        # 1. Close Fleasion cleanly (Fleasion may rewrite settings.json on
        #    close from its in-memory state, so we re-write afterwards).
        if not fr.close_fleasion(pids):
            return False, [t("fleasion.restart_close_failed")]
        if not _write_settings(info.settings_path, data):
            return False, [t("fleasion.restart_rewrite_failed")]

        # 2. Relaunch Fleasion: it logs one "[Config] Enabled: X" line per
        #    enabled configuration when its state is loaded.
        if not fr.start_fleasion(exe):
            return False, [t("fleasion.restart_start_failed", name=exe.name)]
        lines = fr.wait_for_log_event(log_path, offset, ["[Config] Enabled:"])
        marker = f"[config] enabled: {name}".lower()
        if expect_active:
            confirmed = any(marker in line.lower() for line in lines)
        else:
            re_enabled = any(marker in line.lower() for line in lines)
            verify = _read_settings(info.settings_path)
            settings_clean = verify is not None and name not in (
                verify.get("enabled_configs") or []
            )
            confirmed = (not re_enabled) and settings_clean
        if not confirmed:
            return False, [t("fleasion.restart_not_confirmed")]
        return True, []

    # ------------------------------------------------------------------ #
    def restore_backup(self, backup: BackupInfo) -> list[str]:
        """Restore a backup to the right places.

        Config files go back to the Fleasion config folder; ``settings.json``
        (which lives at the FleasionNT root) goes back to its original
        location, not to the configured ``config/`` sub-folder.
        """
        info = self.detect()
        errors: list[str] = []
        for source in backup.files:
            if source.name == "settings.json":
                dest = info.settings_path or (
                    info.root / "settings.json" if info.root else None
                ) or (self.configured_dir / "settings.json" if self.configured_dir else None)
            else:
                dest = (info.config_dir or self.configured_dir) / source.name
            if dest is None:
                errors.append(t("fleasion.restore_unknown_dest", name=source.name))
                continue
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
            except OSError as exc:
                errors.append(
                    t(
                        "fleasion.restore_failed",
                        name=source.name,
                        detail=exc.strerror or exc,
                    )
                )
        return errors


# ---------------------------------------------------------------------- #
def _read_settings(path: Path) -> dict | None:
    """Read settings.json; ``None`` when unreadable or not a JSON object."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_settings(path: Path, data: dict) -> bool:
    """Write settings.json atomically, keeping the original newline style."""
    try:
        raw = path.read_bytes()
        newline = "\r\n" if b"\r\n" in raw else "\n"
        body = json.dumps(data, indent=2, ensure_ascii=False).replace("\n", newline)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(body.encode("utf-8"))
        tmp.replace(path)
        return True
    except OSError:
        return False

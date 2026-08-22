"""Application settings persistence.

Settings are stored in a local JSON file inside the user's AppData folder,
so the application never hard-codes any user path:

    %APPDATA%\\RivalsConfigManager\\settings.json

Backups created before overwriting configs live in:

    %APPDATA%\\RivalsConfigManager\\backups
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .i18n import DEFAULT_LANGUAGE, available_languages
from .themes import theme_keys as _theme_keys

APP_NAME = "RivalsConfigManager"
APP_DISPLAY_NAME = "Rivals Config Manager"

#: v1.3.5 — central **admin** gate. The normal user build ships with
#: ``ADMIN_MODE = False``: none of the admin tools are reachable in the
#: interface (« Modifier l'image », gestion des assets, publication...).
#: An admin build — or later a real account/login system — flips this
#: single switch; the UI reads it through :func:`admin_enabled` and never
#: tests ``if admin`` inline.
ADMIN_MODE = False


def admin_enabled() -> bool:
    """Whether the admin toolset is active (single central gate).

    Every admin-only UI element (manual image editor, asset management,
    publication tools, the Editor Mode) is gated behind this function. A
    future login system only needs to replace ``ADMIN_MODE`` with a runtime
    check — no interface rewrite.

    The creator can enable the admin toolset explicitly — without rebuilding
    — by setting ``RCM_ADMIN_MODE=1`` in the environment. This is a
    lightweight guard meant to stop a normal user from accidentally editing
    official resources, not an authentication system.
    """
    return bool(ADMIN_MODE) or os.environ.get("RCM_ADMIN_MODE") == "1"


def data_dir() -> Path:
    """Return (and create) the per-user data directory."""
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def normalize_path(path) -> Path:
    """Return an absolute, cleaned path for a user-selected folder.

    The Windows folder picker can return paths with trailing separators,
    forward slashes, ``~``, environment variables or (rarely) a relative
    form. This helper expands ``~``/env vars and makes the path absolute and
    separator-free so it is stored and compared consistently. It never
    raises on odd input — an unusable value simply round-trips as a Path.

    The working directory is *never* the application root: this only affects
    the user-chosen paths, and only as a last resort for a relative input.
    """
    raw = str(path).strip()
    if not raw:
        return Path(".")
    expanded = os.path.expandvars(os.path.expanduser(raw))
    return Path(os.path.abspath(expanded))


def settings_file() -> Path:
    return data_dir() / "settings.json"


def backups_dir() -> Path:
    """Return (and create) the directory used to store backups."""
    d = data_dir() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def image_cache_dir() -> Path:
    """Return (and create) the directory that stores imported/downloaded images.

    Images are copied here so they stay available offline and survive the
    deletion or move of their original source.
    """
    d = data_dir() / "image_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def obj_cache_dir() -> Path:
    """Return (and create) the directory that stores imported 3D models.

    Models are copied here so the association survives the original being
    moved or deleted; activation copies them next to the configuration.
    """
    d = data_dir() / "obj_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def trash_dir() -> Path:
    """Return (and create) the persistent trash folder (corbeille).

    Deleted items are moved here: they are stored but never used, and the
    folder never disappears — the user can always browse it, sort it and
    restore entries.
    """
    d = data_dir() / "trash"
    d.mkdir(parents=True, exist_ok=True)
    return d


class AppSettings:
    """Holds the two user-configurable folders and the UI preferences."""

    def __init__(self) -> None:
        self.fleasion_dir: Path | None = None
        self.library_dir: Path | None = None
        self.backup_before_overwrite: bool = True
        #: Interface language (``"fr"`` / ``"en"``). Defaults to French:
        #: the application was French-only before 1.1.0, so existing
        #: installations keep their current language. Unknown values fall
        #: back to the default, never an error. Assigning it marks the
        #: language as *chosen* (see the property below) so a virgin
        #: install keeps an absent ``language`` key until the user picks one.
        self._language: str = DEFAULT_LANGUAGE
        #: Per-folder card order (drag & drop) : folder key -> ordered list
        #: of card keys. Stored in settings.json — never touches the library.
        self.card_order: dict[str, list[str]] = {}
        #: Hot activation: restart a running Fleasion after an
        #: activation/deactivation so the change applies immediately
        #: (verified through Fleasion's own log). Default ON so existing
        #: users keep the current behaviour after an update.
        self.hot_activation_enabled: bool = True
        #: Favourite configurations (1.3.0): stable keys = config paths as
        #: strings (same identity as the cards' drag keys). Independent of
        #: the Fleasion activation state — a config can be favourite +
        #: active, favourite + inactive, etc.
        self.favorites: list[str] = []
        #: Visual theme key (1.3.0): one of :data:`app.themes.THEMES`, or
        #: ``"custom"`` when the user defined their own palette. Unknown
        #: values fall back to ``"dark"`` (the historical default).
        self.theme: str = "dark"
        #: Custom theme palette (1.3.0): ``None`` or a dict with the keys
        #: understood by :func:`ui.theme.apply_theme` (primary, secondary,
        #: accent, background, gradient, gradient_angle).
        self.custom_theme: dict | None = None
        #: First-launch onboarding (1.3.8). ``language_chosen`` is *derived*
        #: at load time from the presence of a ``language`` key (so an
        #: upgrade never re-asks); ``onboarding_completed`` is persisted and
        #: means the interactive tutorial was finished — it never comes back.
        self.language_chosen: bool = False
        self.onboarding_completed: bool = False

    # ------------------------------------------------------------------ #
    @property
    def language(self) -> str:
        """The active language code."""
        return self._language

    @language.setter
    def language(self, value: str) -> None:
        """Assigning a language marks it as chosen (it will be persisted,
        and the first-launch screen will never be asked again)."""
        self._language = value
        self.language_chosen = True

    # ------------------------------------------------------------------ #
    @classmethod
    def load(cls) -> "AppSettings":
        settings = cls()
        path = settings_file()
        if not path.exists():
            return settings
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            fleasion = data.get("fleasion_dir")
            library = data.get("library_dir")
            settings.fleasion_dir = Path(fleasion) if fleasion else None
            settings.library_dir = Path(library) if library else None
            settings.backup_before_overwrite = bool(
                data.get("backup_before_overwrite", True)
            )
            settings.hot_activation_enabled = bool(
                data.get("hot_activation_enabled", True)
            )
            # Language: missing key -> default; unknown value -> default.
            # Only a persisted, known value counts as a *chosen* language.
            raw_language = data.get("language")
            if isinstance(raw_language, str) and raw_language in available_languages():
                settings.language = raw_language  # setter → language_chosen = True
            else:
                settings._language = DEFAULT_LANGUAGE
            raw_order = data.get("card_order")
            if isinstance(raw_order, dict):
                for folder, keys in raw_order.items():
                    if isinstance(keys, list):
                        settings.card_order[str(folder)] = [
                            str(k) for k in keys if isinstance(k, str)
                        ]
            # Favorites: list of config keys (paths). Unknown/missing key ->
            # empty list, never an error.
            raw_favs = data.get("favorites")
            if isinstance(raw_favs, list):
                settings.favorites = [str(k) for k in raw_favs if isinstance(k, str)]
            # Theme: missing or unknown -> the historical default ("dark").
            raw_theme = data.get("theme")
            if isinstance(raw_theme, str) and raw_theme in _theme_keys():
                settings.theme = raw_theme
            raw_custom = data.get("custom_theme")
            if isinstance(raw_custom, dict):
                settings.custom_theme = {
                    str(k): v for k, v in raw_custom.items() if isinstance(v, (str, int, float, bool))
                } or None
            # Onboarding (1.3.8): a persisted ``language`` key means the user
            # chose their language at some point (never re-ask); the tutorial
            # only runs while ``onboarding_completed`` is false.
            # « Choisie » seulement si une VRAIE valeur est persistée (un
            # ``null`` — cas du reset d'onboarding — ne compte pas).
            settings.language_chosen = isinstance(data.get("language"), str) and bool(
                data["language"]
            )
            settings.onboarding_completed = bool(data.get("onboarding_completed", False))
        except (json.JSONDecodeError, OSError, TypeError, AttributeError):
            # Corrupt or unreadable settings (including a valid JSON of the
            # wrong shape, e.g. an array): fall back to defaults, never crash.
            settings = cls()
        # Mécanisme de développement/test (v1.3.10) : ``RCM_RESET_ONBOARDING=1``
        # remet à zéro UNIQUEMENT l'état du premier lancement (langue choisie
        # + tutoriel terminé) — jamais les favoris, profils, chemins, thèmes
        # ni aucune autre préférence. Jamais actif par défaut.
        if os.environ.get("RCM_RESET_ONBOARDING") == "1":
            settings.language_chosen = False
            settings.onboarding_completed = False
            settings.save()
        return settings

    def save(self) -> None:
        path = settings_file()
        payload = {
            "fleasion_dir": str(self.fleasion_dir) if self.fleasion_dir else None,
            "library_dir": str(self.library_dir) if self.library_dir else None,
            "backup_before_overwrite": self.backup_before_overwrite,
            "hot_activation_enabled": self.hot_activation_enabled,
            # La langue n'est écrite que si elle a réellement été choisie :
            # un reset d'onboarding redevient ainsi une installation vierge.
            "language": self.language if self.language_chosen else None,
            "card_order": self.card_order,
            "favorites": list(self.favorites),
            "theme": self.theme,
            "custom_theme": self.custom_theme,
            "onboarding_completed": self.onboarding_completed,
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)  # atomic write

    # ------------------------------------------------------------------ #
    def set_card_order(self, folder_key: str, keys: list[str]) -> None:
        """Persist the drag & drop order of one folder's cards."""
        self.card_order[folder_key] = list(keys)

    def get_card_order(self, folder_key: str) -> list[str]:
        """Stored card order for a folder (empty when none)."""
        return list(self.card_order.get(folder_key, []))

    # ------------------------------------------------------------------ #
    # Favorites (1.3.0)
    # ------------------------------------------------------------------ #
    def is_favorite(self, key: str) -> bool:
        """True when the config identified by ``key`` is a favourite."""
        return key in self.favorites

    def toggle_favorite(self, key: str) -> bool:
        """Toggle a favourite; returns the new state (True = favourite)."""
        if key in self.favorites:
            self.favorites.remove(key)
            return False
        self.favorites.append(key)
        return True

    def set_favorite(self, key: str, favorite: bool) -> None:
        """Set the favourite state explicitly (idempotent)."""
        is_fav = key in self.favorites
        if favorite and not is_fav:
            self.favorites.append(key)
        elif not favorite and is_fav:
            self.favorites.remove(key)

    @property
    def is_configured(self) -> bool:
        return bool(self.fleasion_dir and self.library_dir)

    @property
    def library_exists(self) -> bool:
        return bool(self.library_dir and self.library_dir.is_dir())

    @property
    def fleasion_exists(self) -> bool:
        return bool(self.fleasion_dir and self.fleasion_dir.is_dir())

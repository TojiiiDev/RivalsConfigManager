"""Internationalisation manager — pure Python, no Qt dependency.

The manager loads one JSON table per language from
``app/i18n/translations/<code>.json`` and exposes a single lookup entry
point, :func:`t`:

    t("settings.language")          -> "Langue" (fr) / "Language" (en)

Rules (from the 1.1.0 spec):

* Every language file must contain the **same keys** — a test validates
  that ``fr.json`` and ``en.json`` match exactly.
* A missing key falls back to the default language (``fr``), then to the
  key itself as a last resort — a missing translation can never crash the
  application. A clear warning is logged in development.
* An unknown language code falls back to the default language.
* Values may contain ``{placeholder}`` markers filled with
  :func:`str.format` through ``t("key", name=...)``.

The module is importable from ``app/*`` (no Qt import) so the application
layer can translate its user-facing messages too.

Frozen (PyInstaller) support: the JSON tables are bundled as data files
under ``app/i18n/translations`` inside the onefile archive; when the
application runs from the .exe, ``sys._MEIPASS`` points to the extraction
folder and the tables are read from there — never from the source tree.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

#: Default language — the application was French-only before 1.1.0, so
#: existing installations keep the current language by default.
DEFAULT_LANGUAGE = "fr"

#: Supported language codes -> native display names (no emoji, per spec).
#: Adding a language = add its code here and create
#: ``app/i18n/translations/<code>.json`` with the same keys as the others.
LANGUAGES: dict[str, str] = {
    "fr": "Français",
    "en": "English",
    "es": "Español",
    "de": "Deutsch",
    "it": "Italiano",
    "pt": "Português",
    "nl": "Nederlands",
    "pl": "Polski",
    "ru": "Русский",
    "tr": "Türkçe",
}

logger = logging.getLogger(__name__)


def _translations_dir() -> Path:
    """The directory holding ``<code>.json`` translation tables.

    Works in three contexts:

    * **frozen** (``.exe`` built by PyInstaller): the tables are bundled
      under ``app/i18n/translations`` inside the onefile archive, and
      ``sys._MEIPASS`` is the extraction folder;
    * **source tree**: ``app/i18n/translations`` next to this module;
    * fallback: the module folder itself (last resort, never relied on).
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidate = Path(meipass) / "app" / "i18n" / "translations"
            if candidate.is_dir():
                return candidate
            # Some PyInstaller versions flatten data files differently;
            # also try directly under the extraction root.
            flat = Path(meipass) / "translations"
            if flat.is_dir():
                return flat
    return Path(__file__).resolve().parent / "translations"


class I18nManager:
    """Holds the loaded translation tables and the current language."""

    def __init__(self) -> None:
        self._language = DEFAULT_LANGUAGE
        self._tables: dict[str, dict] = {}
        for code in LANGUAGES:
            self._tables[code] = self._load(code)

    # ------------------------------------------------------------------ #
    def _load(self, code: str) -> dict:
        """Load one language table; ``{}`` on any read/parse problem."""
        path = _translations_dir() / f"{code}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            logger.error("Traductions illisibles : %s", path)
            return {}
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------------ #
    def available(self) -> list[str]:
        """Supported language codes, in declaration order."""
        return list(LANGUAGES)

    def is_supported(self, code: str) -> bool:
        return code in LANGUAGES

    def display_name(self, code: str) -> str:
        """Human-readable name of a language (for the settings selector)."""
        return LANGUAGES.get(code, code)

    def language(self) -> str:
        return self._language

    def set_language(self, code: str) -> None:
        """Switch the current language; unknown codes fall back to the
        default language (never an error)."""
        if not self.is_supported(code):
            logger.warning(
                "Langue inconnue : %r — retour à %r", code, DEFAULT_LANGUAGE
            )
            code = DEFAULT_LANGUAGE
        self._language = code

    # ------------------------------------------------------------------ #
    def t(self, key: str, **kwargs) -> str:
        """Translate ``key`` (dot path) in the current language.

        Fallback chain: current language -> default language -> the key
        itself (never raises). ``{placeholder}`` markers are filled with
        ``kwargs`` when present.
        """
        value = self._lookup(self._language, key)
        if value is None and self._language != DEFAULT_LANGUAGE:
            value = self._lookup(DEFAULT_LANGUAGE, key)
        if value is None:
            logger.warning(
                "Traduction manquante : %s (langue %s)", key, self._language
            )
            value = key
        if not kwargs:
            return value
        try:
            return value.format(**kwargs)
        except (KeyError, ValueError, IndexError):
            # A placeholder mismatch must never crash the UI.
            return value

    def _lookup(self, code: str, key: str) -> str | None:
        """Resolve a dotted key; ``None`` when missing or not a string."""
        node: object = self._tables.get(code) or {}
        for part in key.split("."):
            if not isinstance(node, dict):
                return None
            node = node.get(part)
        return node if isinstance(node, str) else None

    # ------------------------------------------------------------------ #
    def validate(self) -> dict[str, dict[str, list[str]]]:
        """Key-parity report: every language vs. the default language.

        Returns ``{code: {"missing": [...], "extra": [...]}}`` — both lists
        are empty when the language file matches the reference exactly.
        """
        reference = self._keys(self._tables.get(DEFAULT_LANGUAGE) or {})
        report: dict[str, dict[str, list[str]]] = {}
        for code in LANGUAGES:
            keys = self._keys(self._tables.get(code) or {})
            report[code] = {
                "missing": sorted(reference - keys),
                "extra": sorted(keys - reference),
            }
        return report

    @staticmethod
    def _keys(node: dict, prefix: str = "") -> set[str]:
        """Flat set of all leaf keys of a nested table."""
        keys: set[str] = set()
        for name, value in node.items():
            full = f"{prefix}.{name}" if prefix else name
            if isinstance(value, dict):
                keys |= I18nManager._keys(value, full)
            else:
                keys.add(full)
        return keys


#: Module-level singleton — the whole application shares one instance.
_manager = I18nManager()


# ---------------------------------------------------------------------- #
# Public API
# ---------------------------------------------------------------------- #
def t(key: str, **kwargs) -> str:
    """Translate ``key`` in the current language (see :class:`I18nManager`)."""
    return _manager.t(key, **kwargs)


def set_language(code: str) -> None:
    """Switch the current language (unknown codes fall back to default)."""
    _manager.set_language(code)


def current_language() -> str:
    """The active language code (``"fr"``, ``"en"``, ...)."""
    return _manager.language()


def available_languages() -> list[str]:
    """Supported language codes."""
    return _manager.available()


def language_display_name(code: str) -> str:
    """Display name of a language code for the settings selector."""
    return _manager.display_name(code)


def validate_translations() -> dict[str, dict[str, list[str]]]:
    """Key-parity report across all language files (empty = perfect)."""
    return _manager.validate()

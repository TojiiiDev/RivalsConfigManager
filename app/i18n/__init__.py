"""Internationalisation (i18n) support.

Public API:

    from app.i18n import t, set_language, current_language

Adding a new language later only requires:

1. a new ``translations/<code>.json`` file with the same keys as
   ``fr.json`` (validated automatically by :func:`validate_translations`);
2. an entry in :data:`app.i18n.manager.LANGUAGES`.
"""

from __future__ import annotations

from .manager import (
    DEFAULT_LANGUAGE,
    I18nManager,
    available_languages,
    current_language,
    language_display_name,
    set_language,
    t,
    validate_translations,
)

__all__ = [
    "DEFAULT_LANGUAGE",
    "I18nManager",
    "available_languages",
    "current_language",
    "language_display_name",
    "set_language",
    "t",
    "validate_translations",
]

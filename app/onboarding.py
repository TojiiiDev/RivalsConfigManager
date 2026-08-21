"""First-launch onboarding (v1.3.8) — pure decision logic, no Qt.

The onboarding is an independent UI layer above the existing application:
a one-time language choice (first launch) followed by an interactive
tutorial. This module holds the *decisions*; the widgets live in
``ui/views/language_dialog.py`` and ``ui/widgets/onboarding_overlay.py``.

Rules:

* **Language choice** is shown only when the user never chose a language
  (no ``language`` key in the saved settings file). An upgrade from a
  previous version already has a language → never re-asked.
* **Tutorial** runs while ``onboarding_completed`` is false. Finishing it
  persists ``onboarding_completed = true`` in the existing settings.json —
  it then never comes back, even after a language change in Settings.
* Closing the application mid-tutorial simply leaves
  ``onboarding_completed`` false → the tutorial is shown again next time,
  in the already-chosen language (never considered done by mistake).
* ``RCM_ONBOARDING=0`` disables the auto-start entirely (tests build the
  window without onboarding); the tutorial tests opt back in explicitly.
"""

from __future__ import annotations

import os

#: Environment override: ``RCM_ONBOARDING=0`` turns the auto-start off
#: (used by the test suite so constructing a window never pops a modal);
#: any other value keeps onboarding active on fresh installs.
_ONBOARDING_ENV = "RCM_ONBOARDING"


def onboarding_enabled() -> bool:
    """Master switch for the onboarding auto-start."""
    return os.environ.get(_ONBOARDING_ENV, "1") != "0"


def needs_language_choice(settings) -> bool:
    """True when the user never chose a language (no ``language`` key in
    the saved settings file, i.e. a brand-new installation)."""
    return not bool(getattr(settings, "language_chosen", False))


def needs_tutorial(settings) -> bool:
    """True while the interactive tutorial has not been completed."""
    return not bool(getattr(settings, "onboarding_completed", False))


def mark_tutorial_completed(settings) -> None:
    """Persist the tutorial completion in the existing settings store."""
    settings.onboarding_completed = True
    settings.save()


def reset_onboarding(settings) -> None:
    """Development/test helper (v1.3.10): reset ONLY the first-launch
    state (``language_chosen`` + ``onboarding_completed``) so a virgin
    installation can be simulated without deleting anything.

    Everything else is preserved: favourites, profiles, configurations,
    paths, theme and all other preferences. Also driven automatically at
    load time by the ``RCM_RESET_ONBOARDING=1`` environment variable —
    never active by default.
    """
    settings.language_chosen = False
    settings.onboarding_completed = False
    settings.save()

"""Tests for the application version (single source of truth)."""

from __future__ import annotations

import re

from app import __version__


def test_version_is_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_version_is_not_empty() -> None:
    assert __version__.strip()

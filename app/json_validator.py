"""JSON validation helpers.

A configuration is only activated after every JSON file it needs has been
checked. Errors are reported with a human-readable message (file name, line
and column) so the user can fix the file.
"""

from __future__ import annotations

import json
from pathlib import Path

from .i18n import t

VALID_JSON_ERROR = ""


def validate_file(path: Path) -> tuple[bool, str]:
    """Validate a single JSON file.

    Returns ``(ok, error_message)``. ``error_message`` is empty when ``ok``.
    """
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            json.load(handle)
        return True, ""
    except FileNotFoundError:
        return False, t("common.file_not_found", name=path.name)
    except json.JSONDecodeError as exc:
        return (
            False,
            t(
                "validator.invalid_json",
                name=path.name,
                line=exc.lineno,
                col=exc.colno,
                message=exc.msg,
            ),
        )
    except UnicodeDecodeError:
        return False, t("validator.not_utf8", name=path.name)
    except PermissionError:
        return False, t("validator.permission", name=path.name)
    except OSError as exc:
        return False, t("validator.read_failed", name=path.name, detail=exc.strerror or exc)


def validate_files(paths: list[Path]) -> tuple[bool, list[str]]:
    """Validate several JSON files at once.

    Returns ``(all_ok, errors)`` where ``errors`` lists every problem found.
    """
    errors: list[str] = []
    for path in paths:
        ok, message = validate_file(path)
        if not ok:
            errors.append(message)
    return (not errors), errors


def dependency_files(json_path: Path, folder: Path) -> list[Path]:
    """Find local files referenced by a JSON configuration.

    Skin JSON files often reference companion meshes (``.obj`` files) by
    name. We scan every string value in the JSON and, when it looks like a
    local file name that actually exists next to the JSON, we return it so
    it gets copied too. Remote URLs are ignored automatically because no
    matching local file exists.
    """
    import re

    try:
        with open(json_path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except Exception:
        return []

    pattern = re.compile(r"([^\\/\"']+\.(?:obj|mesh|fbx|glb|png|jpe?g|webp|txt|dat))$", re.IGNORECASE)
    found: list[Path] = []
    seen: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
        elif isinstance(value, str):
            match = pattern.search(value)
            if match:
                candidate = folder / match.group(1)
                key = candidate.name.lower()
                if candidate.is_file() and key not in seen:
                    seen.add(key)
                    found.append(candidate)

    walk(data)
    return found

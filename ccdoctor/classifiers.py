from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("TOKEN", "KEY", "SECRET", "COOKIE", "PASSWORD", "AUTH")


def is_secret_key(key: str) -> bool:
    upper = key.upper()
    return any(marker in upper for marker in SECRET_MARKERS)


def redact_value(key: str, value: object) -> object:
    if is_secret_key(key):
        if value in (None, ""):
            return value
        return "<redacted>"
    if isinstance(value, dict):
        return redact_mapping(value)
    if isinstance(value, list):
        return [redact_sequence_value(item) for item in value]
    return value


def redact_sequence_value(value: object) -> object:
    if isinstance(value, dict):
        return redact_mapping(value)
    if isinstance(value, list):
        return [redact_sequence_value(item) for item in value]
    return value


def redact_any(value: object) -> object:
    if isinstance(value, dict):
        return redact_mapping(value)
    if isinstance(value, list):
        return [redact_sequence_value(item) for item in value]
    return value


def redact_mapping(mapping: dict[str, object]) -> dict[str, object]:
    return {key: redact_value(key, value) for key, value in mapping.items()}


def classify_skill_target(target: Path | None, control_root: Path) -> tuple[str, str]:
    if target is None:
        return "configured", "unknown"

    try:
        resolved = target.resolve(strict=False)
    except OSError:
        return "configured", "unknown"

    custom_root = control_root / "skills" / "custom"
    installed_root = control_root / "skills" / "installed"

    if _is_relative_to(resolved, custom_root):
        return "custom", "my_ai"
    if _is_relative_to(resolved, installed_root):
        return "installed", "my_ai"
    return "configured", "project"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False

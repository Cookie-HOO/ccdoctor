from __future__ import annotations

from pathlib import Path

from .models import Diagnostic


def check_absolute_path(path_text: object, source_file: str | None, label: str, severity: str = "error") -> Diagnostic | None:
    if not isinstance(path_text, str) or not path_text.startswith("/"):
        return None
    path = Path(path_text)
    if path.exists():
        return None
    return Diagnostic(
        severity=severity,
        message=f"Missing configured {label}: {path}",
        source_file=source_file,
        hint="Update the config path, install the dependency, or remove the stale entry.",
    )


def summarize_exit_code(diagnostics: list[Diagnostic]) -> int:
    if any(d.severity == "error" for d in diagnostics):
        return 2
    if any(d.severity == "warning" for d in diagnostics):
        return 1
    return 0

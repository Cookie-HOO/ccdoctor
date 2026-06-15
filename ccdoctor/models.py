from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Diagnostic:
    severity: str
    message: str
    source_file: str | None = None
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class StatusItem:
    kind: str
    name: str
    scope: str
    provider: str
    source_file: str | None = None
    effective: str = "maybe"
    managed_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)

    def sort_key(self) -> tuple[str, str, str, str, str]:
        return (
            self.kind,
            self.scope,
            self.provider,
            self.name,
            self.source_file or "",
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["metadata"]:
            data.pop("metadata")
        if not data["diagnostics"]:
            data.pop("diagnostics")
        return {k: v for k, v in data.items() if v is not None}

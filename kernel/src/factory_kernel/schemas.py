"""JSON Schema validation for kernel-owned file types (spec §4.1, §27).

Every file format has a schema in ``kernel/schemas/``. The kernel validates
before it accepts a write, so an invalid event/snapshot never lands on disk.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

# Logical kind -> schema file name.
KINDS = {
    "event": "event.schema.json",
    "job": "job.schema.json",
    "project": "project.schema.json",
    "context.manifest": "context.manifest.schema.json",
    "authorizations": "authorizations.schema.json",
    "budget": "budget.schema.json",
    "price_table": "price_table.schema.json",
}


class SchemaError(Exception):
    pass


class SchemaStore:
    """Loads and caches JSON Schemas from ``kernel/schemas/``."""

    def __init__(self, schemas_dir: Path | str):
        self.schemas_dir = Path(schemas_dir)
        self._validators: dict[str, Draft202012Validator] = {}

    def _validator(self, kind: str) -> Draft202012Validator:
        if kind not in self._validators:
            filename = KINDS.get(kind, kind)
            path = self.schemas_dir / filename
            if not path.exists():
                raise SchemaError(f"Schema not found for '{kind}': {path}")
            schema = json.loads(path.read_text(encoding="utf-8"))
            self._validators[kind] = Draft202012Validator(schema)
        return self._validators[kind]

    @staticmethod
    def _format_errors(errors: list) -> str:
        parts = []
        for e in sorted(errors, key=lambda x: list(x.path)):
            loc = "/".join(str(p) for p in e.path) or "<root>"
            parts.append(f"{loc}: {e.message}")
        return "; ".join(parts)

    def validate(self, kind: str, obj: Any) -> None:
        """Raise SchemaError if ``obj`` does not match the schema for ``kind``."""
        errors = list(self._validator(kind).iter_errors(obj))
        if errors:
            raise SchemaError(f"{kind} invalid: {self._format_errors(errors)}")

    def is_valid(self, kind: str, obj: Any) -> bool:
        try:
            self.validate(kind, obj)
            return True
        except SchemaError:
            return False

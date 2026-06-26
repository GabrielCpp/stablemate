"""Load the bundled JSON Schemas and validate loaded documents against them."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=None)
def load(name: str) -> dict:
    return json.loads(files("ostler").joinpath("schema", name).read_text(encoding="utf-8"))


def validate(data: dict, schema_name: str) -> list[str]:
    """Return a list of human-readable validation error messages (empty if valid)."""
    try:
        import jsonschema
    except ImportError:
        return []
    schema = load(schema_name)
    validator = jsonschema.Draft202012Validator(schema)
    errors = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        errors.append(f"{loc}: {err.message}")
    return errors

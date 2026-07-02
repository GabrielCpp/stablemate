"""Parse `--manifest`: the curated, test-authored list of elements a QA script expects to see."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ValidationError

from .geometry import BBox


class DomElement(BaseModel):
    selector: str
    role: str = ""
    bbox: BBox
    visible: bool = True
    state: str | None = None


class ManifestResult(BaseModel):
    elements: list[DomElement]
    errors: list[str]


def load_manifest(path: Path) -> ManifestResult:
    """Parse the manifest JSON (a list of element dicts) item-by-item.

    A single malformed entry is recorded in ``.errors`` and skipped rather than failing the
    whole batch, so one bad entry doesn't block vetting the rest of a page.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return ManifestResult(elements=[], errors=[f"cannot read manifest '{path}': {exc}"])

    if not isinstance(raw, list):
        return ManifestResult(elements=[], errors=[f"manifest '{path}' is not a JSON list"])

    elements: list[DomElement] = []
    errors: list[str] = []
    for i, item in enumerate(raw):
        try:
            elements.append(DomElement.model_validate(item))
        except ValidationError as exc:
            errors.append(f"entry {i}: {exc.errors()[0]['msg']}")
    return ManifestResult(elements=elements, errors=errors)

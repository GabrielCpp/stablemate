"""Reading `--params` / `--params-file` into the map a workflow is built from."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def load_params(inline: str | None, file: str | None) -> dict[str, Any]:
    """Merge workflow params from --params-file then --params (inline wins).

    Each source must be a JSON object (key→value map). Exits with a clear error on
    a missing file, invalid JSON, or a non-object payload."""
    params: dict[str, Any] = {}
    if file is not None:
        try:
            inline_from_file = Path(file).read_text()
        except OSError as e:
            print(f"error: cannot read --params-file {file}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        inline_from_file = None

    for label, raw in (("--params-file", inline_from_file), ("--params", inline)):
        if raw is None:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"error: {label} is not valid JSON: {e}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(parsed, dict):
            print(
                f"error: {label} must be a JSON object (key→value map)", file=sys.stderr
            )
            sys.exit(1)
        params.update(parsed)
    return params

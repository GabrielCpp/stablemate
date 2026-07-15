#!/usr/bin/env python3
"""Materialize a deterministic multi-language source inventory for OKF coverage.

Args: [source_root] [output_path] [comma_separated_excludes]
Outputs JSON: {"source_inventory_path","source_unit_count","inventory_errors"}
"""
from __future__ import annotations

import json
import re
import sys
from fnmatch import fnmatch
from pathlib import Path


SKIP_DIRS = {
    ".git", ".next", ".react-router", ".venv", "__pycache__", "build", "coverage",
    "dist", "generated", "mocks", "node_modules", "vendor",
}
TEST_SUFFIXES = (
    "_test.go", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx", "_test.py",
)
GENERATED_SUFFIXES = (".gen.go", ".generated.go", ".d.ts")
PY_DECL = re.compile(r"^(?:async\s+)?(?:class|def)\s+([A-Za-z][A-Za-z0-9_]*)", re.MULTILINE)
GO_DECL = re.compile(
    r"^(?:func\s+(?:\([^\n)]*\)\s*)?([A-Za-z][A-Za-z0-9_]*)\s*\(|"
    r"type\s+([A-Za-z][A-Za-z0-9_]*)\s+(?:struct|interface)\b)",
    re.MULTILINE,
)
TS_DECL = re.compile(
    r"^export\s+(?:default\s+)?(?:declare\s+)?(?:async\s+)?"
    r"(?:function|class|interface|type|const|let|enum)\s+([A-Za-z_$][A-Za-z0-9_$]*)",
    re.MULTILINE,
)


def skipped(path: Path, root: Path, excludes: list[str]) -> bool:
    rel = path.relative_to(root)
    rel_text = rel.as_posix()
    configured = any(
        rel_text == pattern.rstrip("/")
        or rel_text.startswith(pattern.rstrip("/") + "/")
        or fnmatch(rel_text, pattern)
        for pattern in excludes
    )
    return (configured or bool(set(rel.parts) & SKIP_DIRS)
            or path.name.endswith(TEST_SUFFIXES + GENERATED_SUFFIXES))


def symbols(path: Path, text: str) -> list[str]:
    if path.suffix == ".py":
        return [m.group(1) for m in PY_DECL.finditer(text) if not m.group(1).startswith("_")]
    if path.suffix == ".go":
        return [name for m in GO_DECL.finditer(text)
                if (name := m.group(1) or m.group(2))[:1].isupper()]
    if path.suffix in {".ts", ".tsx"}:
        return [m.group(1) for m in TS_DECL.finditer(text)]
    return []


def main() -> None:
    source = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    output = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else source / ".source-inventory.json"
    excludes = [part.strip().strip("/") for part in (sys.argv[3] if len(sys.argv) > 3 else "").split(",")
                if part.strip()]
    errors: list[str] = []
    units: list[dict[str, str]] = []
    if not source.is_dir():
        errors.append(f"source root is not a directory: {source}")
    else:
        for path in sorted(source.rglob("*")):
            if not path.is_file() or path.suffix not in {".go", ".py", ".ts", ".tsx"}:
                continue
            if skipped(path, source, excludes):
                continue
            rel = path.relative_to(source).as_posix()
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                errors.append(f"{rel}: {exc}")
                continue
            if "Code generated" in "\n".join(text.splitlines()[:8]):
                continue
            units.append({"kind": "module", "path": rel, "symbol": "", "code": rel})
            for symbol in symbols(path, text):
                units.append({"kind": "symbol", "path": rel, "symbol": symbol,
                              "code": f"{rel}::{symbol}"})

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "version": 1,
        "sourceRoot": str(source),
        "excludes": excludes,
        "units": units,
        "errors": errors,
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "source_inventory_path": str(output),
        "source_unit_count": len(units),
        "inventory_errors": "\n".join(errors),
    }))


if __name__ == "__main__":
    main()

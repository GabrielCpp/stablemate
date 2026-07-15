#!/usr/bin/env python3
"""Materialize a deterministic multi-language source inventory for OKF coverage.

Two inventories, one pass:
* **code units** — modules + public declarations under the source root (the exhaustiveness
  floor the code crawl is diffed against).
* **operational units** — the *run surface* (make/just targets, compose services, package
  scripts, console-scripts, `__main__` entry points) from generic evidence at the repo root
  and inside the source tree. This is the forcing function for the runbook profile
  (docs/okf-runbook.md §5.3): an undocumented run surface is a coverage unit, so the book is
  not complete until it is a `runbook`.

Args: [source_root] [output_path] [comma_separated_excludes] [repo_root]
Outputs JSON: {"source_inventory_path","source_unit_count","operational_unit_count","inventory_errors"}
"""
from __future__ import annotations

import json
import re
import sys
import tomllib
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


# --- operational surface (the run-surface inventory, docs/okf-runbook.md §5.3) -------------
# A recipe/target line: a leading name, optional recipe params, then a colon that is NOT `:=`
# (a variable assignment). Excludes `.PHONY`-style dotted directives via the leading class.
RECIPE_DECL = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\s+[^:=]*)?:(?!=)", re.MULTILINE)
COMPOSE_GLOBS = ("docker-compose.yml", "docker-compose.yaml", "docker-compose.*.yml",
                 "docker-compose.*.yaml", "compose.yml", "compose.yaml",
                 "compose.*.yml", "compose.*.yaml")


def _make_or_just_targets(text: str) -> list[str]:
    seen: list[str] = []
    for m in RECIPE_DECL.finditer(text):
        name = m.group(1)
        if name not in seen and "%" not in name:   # skip pattern rules
            seen.append(name)
    return seen


def _compose_services(text: str) -> list[str]:
    """Top-level `services:` children, by two-space indentation (no YAML dep)."""
    services: list[str] = []
    in_services = False
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent == 0:
            in_services = raw.rstrip().rstrip(":").strip() == "services"
            continue
        if in_services and indent == 2 and raw.rstrip().endswith(":"):
            services.append(raw.strip().rstrip(":"))
    return services


def _toml_script_keys(data: dict) -> list[str]:
    keys = list((data.get("project", {}).get("scripts") or {}))
    keys += list(((data.get("tool", {}).get("poetry", {}) or {}).get("scripts") or {}))
    return keys


def operational_units(source: Path, repo_root: Path, excludes: list[str],
                      errors: list[str]) -> list[dict[str, str]]:
    """Detect the run surface from generic evidence at the repo root + inside the source tree."""
    units: list[dict[str, str]] = []
    seen_evidence: set[str] = set()

    def emit(kind: str, name: str, file: Path) -> None:
        try:
            rel = file.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            rel = file.name
        evidence = f"{rel}:{name}"
        if evidence not in seen_evidence:
            seen_evidence.add(evidence)
            units.append({"kind": kind, "name": name, "evidence": evidence})

    # Candidate evidence files: shallow at repo root, plus anywhere in the source tree.
    candidates: list[Path] = [p for p in repo_root.iterdir() if p.is_file()] if repo_root.is_dir() else []
    if source.is_dir():
        for path in source.rglob("*"):
            if path.is_file() and not (set(path.relative_to(source).parts) & SKIP_DIRS) \
                    and not skipped(path, source, excludes):
                candidates.append(path)

    for path in sorted(set(candidates)):
        name = path.name
        try:
            if name in ("Makefile", "makefile", "GNUmakefile"):
                for target in _make_or_just_targets(path.read_text(encoding="utf-8")):
                    emit("make-target", target, path)
            elif name in ("justfile", "Justfile", ".justfile"):
                for recipe in _make_or_just_targets(path.read_text(encoding="utf-8")):
                    emit("just-recipe", recipe, path)
            elif any(fnmatch(name, g) for g in COMPOSE_GLOBS):
                for svc in _compose_services(path.read_text(encoding="utf-8")):
                    emit("compose-service", svc, path)
            elif name == "package.json":
                data = json.loads(path.read_text(encoding="utf-8"))
                for script in (data.get("scripts") or {}):
                    emit("package-script", script, path)
            elif name == "pyproject.toml":
                for script in _toml_script_keys(tomllib.loads(path.read_text(encoding="utf-8"))):
                    emit("console-script", script, path)
            elif name == "__main__.py":
                emit("entry-point", path.parent.name or "__main__", path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
            errors.append(f"{name}: {exc}")
    return units


def main() -> None:
    source = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    output = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else source / ".source-inventory.json"
    excludes = [part.strip().strip("/") for part in (sys.argv[3] if len(sys.argv) > 3 else "").split(",")
                if part.strip()]
    repo_root = Path(sys.argv[4]).resolve() if len(sys.argv) > 4 and sys.argv[4].strip() else source
    errors: list[str] = []
    units: list[dict[str, str]] = []
    operational = operational_units(source, repo_root, excludes, errors)
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
        "repoRoot": str(repo_root),
        "excludes": excludes,
        "units": units,
        "operational": operational,
        "errors": errors,
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "source_inventory_path": str(output),
        "source_unit_count": len(units),
        "operational_unit_count": len(operational),
        "inventory_errors": "\n".join(errors),
    }))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Materialize a deterministic multi-language source inventory for OKF coverage.

Two inventories, one pass:
* **code units** — modules + public declarations under the source root (the exhaustiveness
  floor the code crawl is diffed against). Languages: Go, Python, TypeScript, PHP, Twig
  (``SOURCE_SUFFIXES``). A tree the front end cannot read at all is an **error**, never an
  empty inventory — an empty unit list reads downstream as "everything is covered", so an
  unsupported language would otherwise declare a book complete having documented nothing.

  What counts as a unit is language-shaped. For Go/TS a file is a container and its *symbols*
  are the units; for Twig a template renders a screen, so the **file** is the unit and its
  `{% block %}`s are secondary. Both are emitted; the consumer decides.
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
from collections import Counter
from fnmatch import fnmatch
from pathlib import Path


SKIP_DIRS = {
    ".git", ".next", ".react-router", ".venv", "__pycache__", "build", "coverage",
    "dist", "generated", "mocks", "node_modules", "vendor",
}
TEST_SUFFIXES = (
    "_test.go", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx", "_test.py", "Test.php",
)
GENERATED_SUFFIXES = (".gen.go", ".generated.go", ".d.ts")
# The languages the symbol front end can read. A source tree that contains NONE of these is
# reported as an error rather than as an empty inventory — see `main`. An unsupported language
# must never be indistinguishable from a fully documented one.
SOURCE_SUFFIXES = {".go", ".py", ".ts", ".tsx", ".php", ".twig"}
PY_DECL = re.compile(r"^(?:async\s+)?(?:class|def)\s+([A-Za-z][A-Za-z0-9_]*)", re.MULTILINE)
# Go: three alternatives, in order — a method (with its receiver captured), a plain func, a
# type. The receiver is captured because a method's unit is qualified by its owner
# (`(*FirebaseClaimsWriter).SetRoleClaims`): that is the form books cite, and it is strictly
# more precise than a bare name, which cannot disambiguate two types declaring the same method
# in one file. Both pointer and value receivers appear in real books. `[(\[]` after the name
# admits generic declarations (`func Map[T any](…)`).
GO_DECL = re.compile(
    r"^func\s+\(\s*(?:[A-Za-z_][A-Za-z0-9_]*\s+)?(\*?)\s*([A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\[[^\]]*\])?\s*\)\s*([A-Za-z][A-Za-z0-9_]*)\s*[(\[]"
    r"|^func\s+([A-Za-z][A-Za-z0-9_]*)\s*[(\[]"
    r"|^type\s+([A-Za-z][A-Za-z0-9_]*)(?:\[[^\]]*\])?\s+(?:struct|interface)\b",
    re.MULTILINE,
)
TS_DECL = re.compile(
    r"^export\s+(?:default\s+)?(?:declare\s+)?(?:async\s+)?"
    r"(?:function|class|interface|type|const|let|enum)\s+([A-Za-z_$][A-Za-z0-9_$]*)",
    re.MULTILINE,
)
# PHP: one pass over class + function declarations *in source order*, so a method can be
# qualified by the class it sits in (`AddProjectAction.getRenderPath`). Grouped in one regex
# rather than two passes because the qualification depends on the interleaving.
PHP_DECL = re.compile(
    r"^\s*(?:abstract\s+|final\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)"
    r"|^\s*(?:(public|protected|private)\s+)?(?:static\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
# Twig: a template's named regions. `{% block content %}` / `{%- block content -%}`.
TWIG_DECL = re.compile(r"\{%-?\s*block\s+([A-Za-z_][A-Za-z0-9_]*)")


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


def _unit_path(path: Path, source: Path, repo_root: Path) -> str:
    """A unit's path, relative to the **repo root** — the grammar books cite.

    Excludes stay source-relative (they are configured per service), but the emitted unit is
    repo-rooted so that one book's `code:` target means the same thing as another's in a
    monorepo. Falls back to source-relative for a source tree outside the repo root.
    """
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.relative_to(source).as_posix()


def _php_symbols(text: str) -> list[str]:
    """Class names, plus each public method qualified by its class (`Class.method`).

    Private/protected methods are not part of the documented surface, and magic methods
    (`__construct`, `__toString`, …) are DI/framework boilerplate rather than behavior — both
    are skipped, mirroring the `_`-prefix filter the Python front end already applies.
    """
    out: list[str] = []
    current = ""
    for m in PHP_DECL.finditer(text):
        if cls := m.group(1):
            current = cls
            out.append(cls)
            continue
        visibility, name = m.group(2), m.group(3)
        if visibility in ("private", "protected") or name.startswith("__"):
            continue
        out.append(f"{current}.{name}" if current else name)
    return out


def _go_symbols(text: str) -> list[str]:
    """Exported types/funcs, plus each exported method qualified by its receiver.

    `func (w *FirebaseClaimsWriter) SetRoleClaims(…)` → `(*FirebaseClaimsWriter).SetRoleClaims`;
    a value receiver drops the star. Export is judged on the *method* name, not the receiver's:
    an exported method on an unexported type is still part of the surface.
    """
    out: list[str] = []
    for star, receiver, method, func, typename in GO_DECL.findall(text):
        if method:
            if method[:1].isupper():
                owner = f"(*{receiver})" if star else receiver
                out.append(f"{owner}.{method}")
            continue
        name = func or typename
        if name[:1].isupper():
            out.append(name)
    return out


def symbols(path: Path, text: str) -> list[str]:
    if path.suffix == ".py":
        return [m.group(1) for m in PY_DECL.finditer(text) if not m.group(1).startswith("_")]
    if path.suffix == ".go":
        return _go_symbols(text)
    if path.suffix in {".ts", ".tsx"}:
        return [m.group(1) for m in TS_DECL.finditer(text)]
    if path.suffix == ".php":
        return _php_symbols(text)
    if path.suffix == ".twig":
        return TWIG_DECL.findall(text)
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
        seen_suffixes: Counter[str] = Counter()
        for path in sorted(source.rglob("*")):
            if not path.is_file() or skipped(path, source, excludes):
                continue
            seen_suffixes[path.suffix] += 1
        if not (seen_suffixes.keys() & SOURCE_SUFFIXES):
            # A tree with source-shaped files but none the front end can read would otherwise
            # yield an empty inventory + no errors — which reads downstream as "fully covered".
            # Blindness must be loud: an unsupported language is a failure, not a clean bill.
            top = ", ".join(f"{s or '(none)'}×{n}" for s, n in seen_suffixes.most_common(5))
            errors.append(
                f"no readable source under {source}: the symbol front end supports "
                f"{sorted(SOURCE_SUFFIXES)} but the tree holds {top or 'no files'} — "
                f"an unsupported language must not be reported as a covered book"
            )
        for path in sorted(source.rglob("*")):
            if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
                continue
            if skipped(path, source, excludes):
                continue
            rel = _unit_path(path, source, repo_root)
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

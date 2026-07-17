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
import logging
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

# The symbol grammar lives in `ostler.inventory`, not here. Two callers need to know what a
# file declares — this inventory (the join's source side) and `doctor`'s `code:` grounding —
# and a grammar defined in two places is a grammar that drifts. It did: grounding used a
# word-presence test, so a facade module re-exporting a name kept a moved symbol's citation
# green. Importing it means the join and the grounding check cannot disagree again.
from ostler.inventory import SOURCE_SUFFIXES, symbols  # noqa: E402


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


def main(logger: logging.Logger) -> None:
    source = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    output = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else source / ".source-inventory.json"
    excludes = [part.strip().strip("/") for part in (sys.argv[3] if len(sys.argv) > 3 else "").split(",")
                if part.strip()]
    repo_root = Path(sys.argv[4]).resolve() if len(sys.argv) > 4 and sys.argv[4].strip() else source
    errors: list[str] = []
    units: list[dict[str, str]] = []
    operational = operational_units(source, repo_root, excludes, errors)
    if not source.is_dir():
        logger.warning("source root is not a directory: %s — the inventory will be empty", source)
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
            logger.warning(
                "no readable source under %s — the tree holds %s but the symbol front end "
                "only reads %s; reporting an error rather than an empty (= 'covered') inventory",
                source, top or "no files", sorted(SOURCE_SUFFIXES),
            )
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

    logger.info("inventoried %s: %d code unit(s), %d operational unit(s), %d error(s) → %s",
                source, len(units), len(operational), len(errors), output)
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
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("inventory-source"))

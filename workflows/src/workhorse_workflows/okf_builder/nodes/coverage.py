"""The exhaustiveness check: inventory the source, then join the book against it.

Ported from `base-library/workflows/okf-builder/scripts/{inventory-source,compute-coverage}.py`.
Three divergences, all shape:

* **The re-scan counter is a local, not a module global.** The script carried `_RESCAN_ROUND`
  at module scope "so that EVERY exit path, including the early error emits, carries the
  increment forward" — an `emit()` that `sys.exit`s cannot be handed a value by its caller.
  Here every exit is a `return Coverage(...)` in one function, so the increment is computed
  once at the top and passed explicitly; the invariant it protected (an error path must not
  reset the bound, or a recurring error loops forever on the branch that exists to stop it)
  is unchanged and is what `_covered` exists to keep.
* **`from ostler.inventory import …` sits with the other imports.** The script placed it
  mid-file under `# noqa: E402` so its long comment could sit next to it; the comment moved
  to the import block instead.
* **The verdict is a `bool`.** `coverage_complete` was `"yes"`/`"no"`; the join's outcome
  already answers `ok` and the string was only ever for a YAML branch to match on.
"""
from __future__ import annotations

import json
import logging
import re
import tomllib
from collections import Counter
from fnmatch import fnmatch
from pathlib import Path

from ostler import Ostler, graph as graph_mod
# The symbol grammar lives in `ostler.inventory`, not here. Two callers need to know what a
# file declares — this inventory (the join's source side) and `doctor`'s `code:` grounding —
# and a grammar defined in two places is a grammar that drifts. It did: grounding used a
# word-presence test, so a facade module re-exporting a name kept a moved symbol's citation
# green. Importing it means the join and the grounding check cannot disagree again.
from ostler.inventory import SOURCE_SUFFIXES, symbols
from workhorse_workflows.kit import short_sha
from workhorse_workflows.okf_builder.shared import stubs
from workhorse_workflows.okf_builder.shared.blueprint import blueprint
from workhorse_workflows.okf_builder.shared.schemas import Coverage, SourceInventory

#: Directories whose contents are never source: build output, vendored trees, caches.
SKIP_DIRS = {
    ".git", ".next", ".react-router", ".venv", "__pycache__", "build", "coverage",
    "dist", "generated", "mocks", "node_modules", "vendor",
}
TEST_SUFFIXES = (
    "_test.go", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx", "_test.py", "Test.php",
)
GENERATED_SUFFIXES = (".gen.go", ".generated.go", ".d.ts")

# --- operational surface (the run-surface inventory, docs/okf-runbook.md §5.3) -------------
# A recipe/target line: a leading name, optional recipe params, then a colon that is NOT `:=`
# (a variable assignment). Excludes `.PHONY`-style dotted directives via the leading class.
RECIPE_DECL = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\s+[^:=]*)?:(?!=)", re.MULTILINE)
COMPOSE_GLOBS = ("docker-compose.yml", "docker-compose.yaml", "docker-compose.*.yml",
                 "docker-compose.*.yaml", "compose.yml", "compose.yaml",
                 "compose.*.yml", "compose.*.yaml")


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
    candidates: list[Path] = (
        [p for p in repo_root.iterdir() if p.is_file()] if repo_root.is_dir() else []
    )
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


@blueprint.node
def inventory_source(
    logger: logging.Logger,
    source_root: str = "",
    output_path: str = "",
    source_excludes: str = "",
    repo_root: str = "",
) -> SourceInventory:
    """Materialize a deterministic multi-language source inventory for OKF coverage.

    Two inventories, one pass:

    * **code units** — modules + public declarations under the source root (the
      exhaustiveness floor the code crawl is diffed against). Languages: Go, Python,
      TypeScript, PHP, Twig (`SOURCE_SUFFIXES`). A tree the front end cannot read at all is
      an **error**, never an empty inventory — an empty unit list reads downstream as
      "everything is covered", so an unsupported language would otherwise declare a book
      complete having documented nothing.

      What counts as a unit is language-shaped. For Go/TS a file is a container and its
      *symbols* are the units; for Twig a template renders a screen, so the **file** is the
      unit and its `{% block %}`s are secondary. Both are emitted; the consumer decides.
    * **operational units** — the *run surface* (make/just targets, compose services,
      package scripts, console-scripts, `__main__` entry points) from generic evidence at
      the repo root and inside the source tree. This is the forcing function for the runbook
      profile (docs/okf-runbook.md §5.3): an undocumented run surface is a coverage unit, so
      the book is not complete until it is a `runbook`.
    """
    source = Path(source_root).resolve() if source_root else Path.cwd().resolve()
    output = Path(output_path).resolve() if output_path else source / ".source-inventory.json"
    excludes = [part.strip().strip("/") for part in source_excludes.split(",") if part.strip()]
    root = Path(repo_root).resolve() if repo_root.strip() else source
    errors: list[str] = []
    units: list[dict[str, str]] = []
    operational = operational_units(source, root, excludes, errors)
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
            rel = _unit_path(path, source, root)
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
        "repoRoot": str(root),
        "excludes": excludes,
        "units": units,
        "operational": operational,
        "errors": errors,
    }, indent=2) + "\n", encoding="utf-8")
    return SourceInventory(
        source_inventory_path=str(output),
        source_unit_count=len(units),
        operational_unit_count=len(operational),
        inventory_errors="\n".join(errors),
    )


def _relative_source(source_root: str, repo_root: str) -> str:
    """The source root as the repo sees it, never as this machine does.

    `coverage.json` is committed, and §10.5 invalidates the anchor when its `sourceRoot` no
    longer matches the config. An absolute path would differ on every checkout, so every
    machine but the one that wrote it would read a valid anchor as stale and rebuild the whole
    book. The anchor has to mean the same thing to everyone who reads it.
    """
    if not source_root:
        return ""
    try:
        return Path(source_root).resolve().relative_to(Path(repo_root).resolve()).as_posix()
    except (ValueError, OSError):
        return source_root  # a source tree outside the repo: absolute is all there is


def _screen_count(okf: Ostler, service: str) -> int:
    """Screens the book documents. The second axis of §9's verdict starts its life here."""
    data = graph_mod.build(okf.graph, etype="screen", surface=service or None)
    return len(data["nodes"])


@blueprint.node(stub=stubs.covered)
def compute_coverage(
    logger: logging.Logger,
    repo_root: str = "",
    features_root: str = "",
    service: str = "",
    inventory_path: str = "",
    waivers_path: str = "",
    prev_rescan: int = 0,
) -> Coverage:
    """Compute the book's coverage — the verdict the agent used to emit.

    The build's stop condition was `coverage_complete`, a value the `recheck` agent emitted
    *about its own work*. This node replaces that self-report with arithmetic: it joins the
    book's `code:` citations against the source inventory and emits the verdict. The agent's
    role narrows to adjudicating the rows the join reports missing — it no longer votes on
    whether it is finished.

    A verdict this node cannot compute is **not a pass**. An unreadable inventory, an
    unloadable graph, or a book with no units at all comes back `coverage_complete=False`
    with the reason attached, because an empty inventory and a finished book are the same
    shape and only one of them is done.

    Also writes the book's `coverage.json` (design §5.5). It is not an audit trinket:
    coverage is meaningless without the exclude set it was computed under, the artifact is
    what makes staleness visible to CI and to a reader, and its `commit` is the anchor a
    later delta build diffs against.
    """
    # The re-scan counter, incremented once per run of this node — the only node that sits
    # on the re-scan loop and nowhere else. EVERY return below carries it, including the
    # error ones: a path that returned the default would reset the bound, and an error that
    # recurs every pass would then loop forever on the one branch that exists to stop it.
    rescan = prev_rescan + 1
    logger.info("coverage re-scan %d", rescan)

    if not inventory_path:
        logger.warning("no source inventory path — nothing to join against, verdict is 'no'")
        return Coverage(
            rescan_round=rescan,
            coverage_error="no source inventory path — nothing to join the book against",
        )

    okf = Ostler(repo_root)
    outcome = okf.coverage(inventory=inventory_path, surface=service or None,
                           waivers=waivers_path or None)
    if outcome.status == "invalid":
        # The join never ran, so there is no `missing` list to adjudicate and no numbers to
        # write into the book — the verdict is 'no', which is not the same as zero covered.
        logger.warning("coverage join failed — verdict is 'no', not a pass: %s",
                       outcome.message)
        return Coverage(rescan_round=rescan,
                        coverage_error=f"coverage join failed: {outcome.message}")
    result = outcome.data

    try:
        screens = _screen_count(okf, service)
    except (OSError, ValueError, RuntimeError):
        screens = 0

    # The missing list is the agent's input (§5.2): it adjudicates these rows, it does not
    # discover them. Written beside the worklist so a human can read what the run is arguing
    # about.
    missing_file = Path(f"{inventory_path}.missing.json")
    missing_file.write_text(
        json.dumps({"surface": service, "missing": result["missing"]}, indent=2),
        encoding="utf-8")
    missing_path = str(missing_file)

    coverage_path = ""
    if features_root:
        try:
            anchor = short_sha(repo_root)
        except (OSError, ValueError, RuntimeError):
            anchor = ""  # not a git checkout, or no HEAD yet: the anchor is absent, not faked
        book = Path(features_root)
        if book.is_dir():
            out = book / "coverage.json"
            out.write_text(json.dumps({
                "covered": result["covered"],
                "total": result["total"],
                "waived": result["waived"],
                "screens": screens,
                "generated_from": {
                    "sourceRoot": _relative_source(result.get("sourceRoot", ""), repo_root),
                    "excludes": result.get("excludes", []),
                    "commit": anchor,
                },
            }, indent=2) + "\n", encoding="utf-8")
            coverage_path = str(out)

    complete = outcome.ok
    logger.info("coverage for %s: %d/%d units covered, %d waived, %d screens, %d missing "
                "→ complete=%s", service or "(whole book)", result["covered"],
                result["total"], result["waived"], screens, len(result["missing"]),
                "yes" if complete else "no")
    return Coverage(
        coverage_complete=complete,
        missing_count=len(result["missing"]),
        missing_path=missing_path,
        coverage_path=coverage_path,
        coverage_summary=outcome.message,
        coverage_error="; ".join(result["errors"]),
        rescan_round=rescan,
    )


__all__ = ["compute_coverage", "inventory_source", "operational_units", "skipped"]

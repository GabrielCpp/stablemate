#!/usr/bin/env python3
import argparse
import ast
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

CONFIG = ".agent-checks.toml"
TABLE = "dead-code"
TEST_PATTERNS = ("*_test.py", "test_*.py", "conftest.py")
TEST_DIRS = frozenset({"tests", "test"})


def _repo_root() -> Path:
    toplevel = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
    )
    return Path(toplevel.stdout.strip())


REPO_ROOT = _repo_root()


class ConfigError(ValueError):
    """A value in the config table has the wrong type."""


@dataclass(frozen=True)
class Module:
    name: str
    path: str
    is_test: bool
    imports: frozenset[str]
    is_main: bool


def is_test_path(path: str) -> bool:
    pure = PurePosixPath(path)
    if any(part in TEST_DIRS for part in pure.parts[:-1]):
        return True
    return any(fnmatch(pure.name, pattern) for pattern in TEST_PATTERNS)


def python_files() -> list[str]:
    """Python files git tracks or would track: committed, staged, or untracked and not ignored."""
    ls_files = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*.py"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        p
        for p in ls_files.stdout.split("\0")
        if p and not _has_hidden_part(p) and (REPO_ROOT / p).is_file()
    ]


def _has_hidden_part(path: str) -> bool:
    return any(part.startswith(".") for part in PurePosixPath(path).parts)


def module_name(path: str, paths: set[str]) -> str | None:
    pure = PurePosixPath(path)
    parts = list(pure.with_suffix("").parts)
    start = len(parts) - 1
    while start > 0 and str(PurePosixPath(*parts[:start], "__init__.py")) in paths:
        start -= 1
    parts = parts[start:]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or None


def _is_main_guard(node: ast.stmt) -> bool:
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    names = [node.test.left, *node.test.comparators]
    return any(isinstance(n, ast.Name) and n.id == "__name__" for n in names)


def _resolve_relative(name: str, path: str, level: int, target: str | None) -> str:
    base = name.split(".")
    if not path.endswith("__init__.py"):
        base = base[:-1]
    base = base[: len(base) - (level - 1)] if level > 1 else base
    return ".".join([*base, target] if target else base)


def _dynamic_imports(tree: ast.Module) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute | ast.Name)
            and getattr(node.func, "attr", getattr(node.func, "id", "")) == "import_module"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            found.add(node.args[0].value)
    return found


def read_module(name: str, path: str) -> Module:
    is_test = is_test_path(path)
    try:
        tree = ast.parse((REPO_ROOT / path).read_bytes(), filename=path)
    except SyntaxError:
        return Module(name, path, is_test, frozenset(), False)
    imports = _dynamic_imports(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = (
                _resolve_relative(name, path, node.level, node.module)
                if node.level
                else node.module or ""
            )
            imports.add(base)
            imports.update(f"{base}.{alias.name}" for alias in node.names)
    is_main = path.endswith("__main__.py") or any(_is_main_guard(node) for node in tree.body)
    return Module(name, path, is_test, frozenset(imports), is_main)


def _str_mapping(value: object, key: str) -> dict[str, str]:
    if not isinstance(value, dict) or not all(
        isinstance(name, str) and isinstance(target, str) for name, target in value.items()
    ):
        raise ConfigError(f"pyproject.toml [project] {key} must map names to strings")
    return {str(name): str(target) for name, target in value.items()}


def declared_entry_modules() -> set[str]:
    try:
        with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        return set()
    project = data.get("project", {})
    if not isinstance(project, dict):
        raise ConfigError("pyproject.toml [project] must be a table")
    targets = [
        *_str_mapping(project.get("scripts", {}), "scripts").values(),
        *_str_mapping(project.get("gui-scripts", {}), "gui-scripts").values(),
    ]
    groups = project.get("entry-points", {})
    if not isinstance(groups, dict):
        raise ConfigError("pyproject.toml [project] entry-points must be a table")
    for group, entries in groups.items():
        targets.extend(_str_mapping(entries, f"entry-points.{group}").values())
    return {target.split(":")[0].strip() for target in targets}


def configured_roots() -> list[str]:
    try:
        with (REPO_ROOT / CONFIG).open("rb") as handle:
            table = tomllib.load(handle).get(TABLE, {})
    except FileNotFoundError:
        return []
    roots = table.get("roots", []) if isinstance(table, dict) else None
    if not isinstance(roots, list) or not all(isinstance(root, str) for root in roots):
        raise ConfigError(f"{CONFIG} [{TABLE}] roots must be a list of strings")
    return [root for root in roots if isinstance(root, str)]


def known_prefixes(name: str, modules: dict[str, Module]) -> set[str]:
    """The dotted prefixes of *name* that are modules in *modules*, *name* included."""
    parts = name.split(".")
    return {".".join(parts[:i]) for i in range(1, len(parts) + 1)} & modules.keys()


def modules_reached_from(starts: set[str], modules: dict[str, Module]) -> set[str]:
    seen: set[str] = set()
    stack = [n for s in starts for n in known_prefixes(s, modules)]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        for imported in modules[name].imports:
            stack.extend(known_prefixes(imported, modules) - seen)
    return seen


def line_count(path: str) -> int:
    return len((REPO_ROOT / path).read_bytes().splitlines())


@dataclass(frozen=True)
class Reachability:
    """The roots the walk starts from, the production modules it never reaches, and the modules tests reach."""

    declared_roots: frozenset[str]
    main_roots: frozenset[str]
    unreachable_modules: tuple[Module, ...]
    reached_by_tests: frozenset[str]


def read_modules() -> dict[str, Module]:
    paths = python_files()
    path_set = set(paths)
    modules: dict[str, Module] = {}
    for path in paths:
        name = module_name(path, path_set)
        if name:
            modules[name] = read_module(name, path)
    return modules


def reachability(extra_roots: list[str]) -> Reachability:
    """Walk imports from every root and name the production modules no root reaches."""
    modules = read_modules()
    production = {n: m for n, m in modules.items() if not m.is_test}
    declared = declared_entry_modules() | set(configured_roots()) | set(extra_roots)
    mains = {n for n, m in production.items() if m.is_main}
    reached = modules_reached_from(declared | mains, production)
    return Reachability(
        declared_roots=frozenset(declared),
        main_roots=frozenset(mains),
        unreachable_modules=tuple(production[n] for n in sorted(production) if n not in reached),
        reached_by_tests=frozenset(modules_reached_from({n for n, m in modules.items() if m.is_test}, modules)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List Python modules no entry point reaches without going through a test."
    )
    parser.add_argument("--root", action="append", default=[], help="extra root module")
    parser.add_argument("--check", action="store_true", help="exit 1 when anything is unreachable")
    args = parser.parse_args()
    extra_roots: list[str] = args.root
    fail_when_dead: bool = args.check

    try:
        reachability_report = reachability(extra_roots)
    except ConfigError as error:
        print(f"dead-code: {error}", file=sys.stderr)
        return 1
    roots = reachability_report.declared_roots | reachability_report.main_roots
    print(f"roots: {len(reachability_report.declared_roots)} declared, {len(reachability_report.main_roots)} with a __main__ guard")
    for name in sorted(roots):
        print(f"  root {name}")
    if not reachability_report.unreachable_modules:
        print("every production module is reachable from a root")
        return 0
    total = sum(line_count(module.path) for module in reachability_report.unreachable_modules)
    print(f"unreachable: {len(reachability_report.unreachable_modules)} modules, {total} lines")
    for module in reachability_report.unreachable_modules:
        importers = "tests only" if module.name in reachability_report.reached_by_tests else "nothing"
        print(f"  {module.path}  ({line_count(module.path)} lines, imported by {importers})")
    return 1 if fail_when_dead else 0


if __name__ == "__main__":
    sys.exit(main())

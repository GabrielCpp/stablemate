#!/usr/bin/env python3
"""Guard the "no environment in a workflow" rule. Wired into `make test`.

A workflow is a checkpointed state machine, and the checkpoint records its **inputs**.
A value a node reads from `os.environ` is therefore invisible twice over: it is not in
the checkpoint, so a resume on another machine silently takes a different value; and it
is not in the run's telemetry, so nobody reading the run afterwards can tell what it
actually worked on. It is also unreachable from the CLI — `--params` cannot set it — so
the operator contract ends up split across two spellings that no test compares.

Everything a workflow needs is therefore an argument or a workflow parameter. The
process boundary is where the environment legitimately lives: `workhorse/cli/run.py` and
`workhorse/supervisor.py` translate `$FOO` into `--params` once, on the way in.

The one allowlist entry this repo declares is a security property rather than an
exemption: `kit/credentials.py` resolves tokens from the environment **because** a secret
must never become a `--param` — params are checkpointed to disk and echoed in logs and
telemetry, which is precisely what a token must not be. Keeping that in one auditable
module is the point; a second module doing it quietly is what this check exists to catch.

This script installs beside the `workhorse-scripting` skill, so it runs in any repo that
authors workflows. Which package holds them, and which module may read the environment,
are that repo's to state — see `[check-no-env]` in `.agent-checks.toml`.

Run:
    uv run python <this script> [--root DIR]
"""

from __future__ import annotations

import argparse
import ast
import sys
import tomllib
from pathlib import Path

#: Repo-local declarations, read from the root of whatever repo is being checked.
CONFIG = ".agent-checks.toml"
TABLE = "check-no-env"

#: `os.<name>` calls and attributes that read or write the process environment.
OS_MEMBERS = frozenset(
    {"environ", "environb", "getenv", "getenvb", "putenv", "unsetenv"}
)


class _EnvVisitor(ast.NodeVisitor):
    """Collect every environment access in one module.

    Two spellings, because banning only the first would be a check that reads well and
    catches nothing: the qualified `os.environ[...]` / `os.getenv(...)`, and the bare
    `environ` / `getenv` a `from os import ...` binds into the module's own namespace.
    """

    def __init__(self) -> None:
        self.hits: list[tuple[int, str]] = []
        self._bare: set[str] = set()

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "os":
            for alias in node.names:
                if alias.name in OS_MEMBERS:
                    self._bare.add(alias.asname or alias.name)
                    self.hits.append((node.lineno, f"from os import {alias.name}"))
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr in OS_MEMBERS
        ):
            self.hits.append((node.lineno, f"os.{node.attr}"))
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in self._bare:
            self.hits.append((node.lineno, node.id))
        self.generic_visit(node)


def declarations(root: Path) -> dict:
    """What *root*'s repo declares to this check, from its `.agent-checks.toml`.

    The script travels with its skill, so the workflow package's location and the module
    excused from the rule belong to the repo rather than to the rule. A repo that declares
    nothing has no workflow package for this to scan, which is a pass and not a finding.
    """
    config = root / CONFIG
    if not config.is_file():
        return {}
    return tomllib.loads(config.read_text(encoding="utf-8")).get(TABLE, {})


def check_no_env(root: Path) -> list[str]:
    """No environment read or write anywhere in the workflow package, bar the allowlist."""
    declared = declarations(root)
    if not (relative := declared.get("package")):
        print(f"ok: no [{TABLE}] package declared in {CONFIG} — nothing to scan")
        return []

    package = root / relative
    if not package.is_dir():
        return [f"{relative} does not exist — the check would pass vacuously"]

    allowed: dict[str, str] = declared.get("allow", {})
    offenders: list[str] = []
    scanned = 0
    for path in sorted(package.rglob("*.py")):
        if path.relative_to(package).as_posix() in allowed:
            continue
        scanned += 1
        visitor = _EnvVisitor()
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        rel = path.relative_to(root).as_posix()
        # De-duplicate per (line, spelling): `from os import environ` reports the import
        # and then every use of the name it bound, which is one finding, not five.
        for lineno, spelling in dict.fromkeys(visitor.hits):
            offenders.append(f"{rel}:{lineno}: {spelling}")

    # An exemption whose module is gone excuses nothing and reads as though it still does.
    offenders += [
        f"{relative}/{name}: excused in {CONFIG}, but the module no longer exists"
        for name in allowed
        if not (package / name).is_file()
    ]

    if not offenders:
        print(f"ok: no environment access in {scanned} workflow modules")
    return offenders


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(), help=f"repo holding {CONFIG} (default: cwd)"
    )
    args = parser.parse_args()

    declared = declarations(args.root)
    problems = check_no_env(args.root)
    if not problems:
        return 0
    print("\nFAIL check_no_env:", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    print(
        "\nA workflow's inputs must be arguments or workflow parameters, so the "
        "checkpoint records them and --params can set them. Translate the variable at "
        "the process boundary (workhorse/cli/run.py, workhorse/entrypoint.sh) instead.",
        file=sys.stderr,
    )
    for name, why in declared.get("allow", {}).items():
        print(f"Allowed: {name} — {why.strip()}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

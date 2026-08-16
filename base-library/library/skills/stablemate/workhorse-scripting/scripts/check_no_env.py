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

One allowlist entry, and it is a security property rather than an exemption:
`kit/credentials.py` resolves tokens from the environment **because** a secret must never
become a `--param` — params are checkpointed to disk and echoed in logs and telemetry,
which is precisely what a token must not be. Keeping that in one auditable module is the
point; a second module doing it quietly is the thing this check exists to catch.

Run:
    uv run python scripts/check_no_env.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "workflows" / "src" / "workhorse_workflows"

#: The one module allowed to read the environment, and why (printed on a violation).
ALLOWED = {
    PACKAGE / "kit" / "credentials.py": (
        "the single credential seam: a token must not become a checkpointed --param"
    ),
}

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


def check_no_env() -> list[str]:
    """No environment read or write anywhere in `workhorse_workflows`, bar the allowlist."""
    if not PACKAGE.is_dir():
        return [f"{PACKAGE} does not exist — the check would pass vacuously"]

    offenders: list[str] = []
    scanned = 0
    for path in sorted(PACKAGE.rglob("*.py")):
        if path in ALLOWED:
            continue
        scanned += 1
        visitor = _EnvVisitor()
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        rel = path.relative_to(REPO).as_posix()
        # De-duplicate per (line, spelling): `from os import environ` reports the import
        # and then every use of the name it bound, which is one finding, not five.
        for lineno, spelling in dict.fromkeys(visitor.hits):
            offenders.append(f"{rel}:{lineno}: {spelling}")
    if not offenders:
        print(f"ok: no environment access in {scanned} workflow modules")
    return offenders


def main() -> int:
    problems = check_no_env()
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
    for path, why in ALLOWED.items():
        print(f"Allowed: {path.relative_to(REPO).as_posix()} — {why}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Guard every Python file against growing past the length a reader can hold in the head."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import guards
import strict_scope

REPO = Path(__file__).resolve().parents[1]
CONFIG = ".agent-checks.toml"
TABLE = "check-file-length"
EXCLUDED_PARTS = ("_vendor", ".venv")
EXCLUDED_PREFIXES = ("docs/plans/",)
SLACK = 25


def _is_excluded(rel: str) -> bool:
    return rel.startswith(EXCLUDED_PREFIXES) or any(part in EXCLUDED_PARTS for part in rel.split("/"))


def repo_files(repo: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z", "-co", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted(
        path
        for path in out.split("\0")
        if path.endswith(".py") and not _is_excluded(path) and (repo / path).is_file()
    )


def load_ceilings(repo: Path) -> dict[str, int]:
    table = guards.declarations(repo, CONFIG, TABLE).get("ceilings", {})
    return {str(path): int(ceiling) for path, ceiling in table.items()}


def _count(repo: Path, rel: str) -> int:
    return len((repo / rel).read_text(encoding="utf-8").splitlines())


def _grandfathered_problem(rel: str, count: int, ceiling: int, limit: int) -> str | None:
    if count <= limit:
        return f"{rel}: {count} lines, now within the {limit}-line limit, remove it from [{TABLE}.ceilings]"
    if count > ceiling:
        return f"{rel}: {count} lines, over its {ceiling}-line ceiling"
    if ceiling - count > SLACK:
        return f"{rel}: {count} lines, lower its ceiling from {ceiling} to {count}"
    return None


def length_problems(
    repo: Path,
    scope: strict_scope.StrictScope,
    files: list[str],
    ceilings: dict[str, int],
) -> list[str]:
    limit = scope.max_lines
    problems: list[str] = []
    for rel in files:
        count = _count(repo, rel)
        if scope.contains(rel):
            if rel in ceilings:
                problems.append(f"{rel}: under the strict scope, remove it from [{TABLE}.ceilings]")
            if count > limit:
                problems.append(f"{rel}: {count} lines, over the {limit}-line limit")
        elif rel in ceilings:
            problem = _grandfathered_problem(rel, count, ceilings[rel], limit)
            if problem:
                problems.append(problem)
        elif count > limit:
            problems.append(f"{rel}: {count} lines, over the {limit}-line limit")
    present = set(files)
    problems.extend(
        f"{rel}: listed in [{TABLE}.ceilings] but no such file, remove it"
        for rel in sorted(ceilings)
        if rel not in present
    )
    return problems


def main() -> int:
    scope = strict_scope.load(REPO)
    files = repo_files(REPO)
    problems = length_problems(REPO, scope, files, load_ceilings(REPO))
    if not problems:
        print(f"ok: {len(files)} files, none over {scope.max_lines} lines unless frozen at a ceiling")
        return 0
    print("\nFAIL check_file_length:", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

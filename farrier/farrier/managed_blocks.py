"""The managed blocks farrier keeps in files the repo owns: the `.agents/` and QA-evidence `.gitignore` blocks and the root Makefile include."""

from __future__ import annotations

from pathlib import Path

from farrier.launcher import LAUNCHER_AGENTS_MK, LAUNCHER_ROOT_MAKEFILE

GATE_SCRIPT = "scripts/check_staged_files.py"

QA_GITIGNORE_BLOCK = (
    "# >>> farrier: QA evidence (generated) >>>",
    "**/qa/**/steps/",
    "**/qa/**/asserts/",
    "**/qa/**/traces/",
    "**/qa/**/videos/",
    "**/qa/**/screenshots/",
    "**/qa/qa-run.ndjson",
    "**/qa/run-manifest.json",
    "**/qa/qa-session.json",
    "# <<< farrier: QA evidence <<<",
)


def ensure_qa_gitignore(repo: Path) -> bool:
    """Install or refresh the managed QA-evidence ignore block."""
    gitignore = repo / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    lines = existing.splitlines()
    start, end = QA_GITIGNORE_BLOCK[0], QA_GITIGNORE_BLOCK[-1]
    if start in lines and end in lines:
        head = lines[: lines.index(start)]
        tail = lines[lines.index(end) + 1 :]
    else:
        head, tail = lines, []
    body = "\n".join([*head, *QA_GITIGNORE_BLOCK, *tail]).strip("\n")
    desired = body + "\n"
    if desired == existing:
        return False
    gitignore.write_text(desired, encoding="utf-8")
    return True


def ensure_gitignore_entry(repo: Path, entry: str) -> bool:
    """Append `entry` to the repo's .gitignore if not already ignored."""
    gitignore = repo / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if entry in {line.strip() for line in existing.splitlines()}:
        return False
    if not existing:
        prefix = ""
    else:
        prefix = existing if existing.endswith("\n") else existing + "\n"
        if not prefix.endswith("\n\n"):
            prefix += "\n"
    gitignore.write_text(f"{prefix}{entry}\n", encoding="utf-8")
    return True


AGENTS_GITIGNORE_BLOCK = (
    ".agents/runs/",
    ".agents/worktrees/",
    ".agents/workflows/",
    ".agents/operator/",
    ".agents/local.compose.yaml",
    ".agents/agents-context.json",
    ".agents/agents-context.*.json",
)


_SUPERSEDED_GITIGNORE_LINES = (
    ".agents",
    ".agents/",
    "/.agents",
    "/.agents/*",
    "!/.agents/agents.mk",
    "!/.agents/flavors/",
    ".agents/runs",
    ".agents/skills/",
    ".agents/prompts/",
    "/.agents/runs/",
    "/.agents/worktrees/",
    "/.agents/skills/",
    "/.agents/prompts/",
    "/.agents/workflows/",
    "/.agents/operator/",
    "/.agents/local.compose.yaml",
    "/.agents/agents-context.json",
    "/.agents/agents-context.*.json",
)


def ensure_agents_gitignore(repo: Path) -> bool:
    """Install/upgrade the managed `.agents/` ignore block in the repo's .gitignore."""
    gitignore = repo / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    managed = set(AGENTS_GITIGNORE_BLOCK) | set(_SUPERSEDED_GITIGNORE_LINES)
    kept = [ln for ln in existing.splitlines() if ln.strip() not in managed]
    body = "\n".join(kept).rstrip("\n")
    prefix = f"{body}\n\n" if body else ""
    desired = prefix + "\n".join(AGENTS_GITIGNORE_BLOCK) + "\n"
    if desired == existing:
        return False
    gitignore.write_text(desired, encoding="utf-8")
    return True


MAKEFILE_INCLUDE_MARKER = "# >>> farrier: agent launcher include (generated) >>>"
MAKEFILE_INCLUDE_END = "# <<< farrier: agent launcher include <<<"


def ensure_makefile_include(repo: Path) -> bool:
    """Ensure the repo's existing root Makefile includes the generated launcher."""
    makefile = repo / LAUNCHER_ROOT_MAKEFILE
    if not makefile.exists():
        return False
    include_line = f"include {LAUNCHER_AGENTS_MK}"
    existing = makefile.read_text(encoding="utf-8")
    if include_line in {line.strip() for line in existing.splitlines()}:
        return False
    prefix = existing if existing.endswith("\n") else existing + "\n"
    if not prefix.endswith("\n\n"):
        prefix += "\n"
    block = (
        f"{MAKEFILE_INCLUDE_MARKER}\n"
        "# Surfaces agent-install / agent-check from the generated\n"
        "# launcher. Re-created by `farrier install`; remove this block to opt out.\n"
        f"{include_line}\n"
        f"{MAKEFILE_INCLUDE_END}\n"
    )
    makefile.write_text(prefix + block, encoding="utf-8")
    return True

"""The QA-evidence ignore block that ships with the staged-files gate."""

from __future__ import annotations

from pathlib import Path

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

"""The QA-evidence ignore block that ships with the staged-files gate.

What used to live here was the gate's *installation*: farrier wrote a whole
`pre-commit` hook it owned, or refused and printed a snippet to paste. Both halves are
gone. Which skill wants a hook is now the skill's own declaration (`skill_hooks`), and
how it reaches git is the manager wiring in `hook_managers`, which claims a fenced
region rather than a whole file — the refusal was the reason this repo's own gate was
never installed at all, silently, for as long as `.githooks/pre-commit` has existed.

What remains is the other half of shipping that gate: the ignore rules that keep the
same artifacts out of the index *before* a hook ever has to refuse them.
"""

from __future__ import annotations

from pathlib import Path

#: The gate, relative to a skill directory farrier rendered. Kept here because the
#: ignore block below is guarded on this file being among the outputs — a repo that did
#: not select the ostler skill has not asked for the rules either.
GATE_SCRIPT = "scripts/check_staged_files.py"

#: What a run writes, ignored by the same shapes the gate refuses to commit. Stated as
#: artifacts rather than as a bare `**/qa/` so a source package named `qa` keeps working:
#: an ignore that swallows new source files is silent, and this one has already gone
#: wrong once in the other direction.
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
    """Install or refresh the managed QA-evidence ignore block. True when it changed."""
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

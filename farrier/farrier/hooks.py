"""Install the staged-files gate as the repo's `pre-commit` hook.

The gate itself is data, not farrier code: it ships as `scripts/check_staged_files.py`
beside the `ostler` skill, so a repo that selects that skill has already chosen it. What
is missing is the one thing a library of text cannot do — get itself *run* by git. This
module writes the `/bin/sh` shim that does, and the `.gitignore` block that keeps the
same artifacts out of the index in the first place.

**File-drop only.** Farrier writes a whole file it owns, or it refuses and prints the
snippet to paste. It never edits a hook it did not write, and never chains to one: the
three hook managers below keep their configuration in a YAML file we do not own, and
farrier's pipeline — and `--check` with it — is a `path -> full text` map end to end, so
"append a fragment" is not an operation it has. Chaining is out for a different reason:
`exec`ing the previous handler means running a program we did not write and cannot
verify, from a hook the user will assume is ours.

**Detection is by marker file**, with `core.hooksPath` as corroboration only. A husky
repo whose `npm install` has not run yet has husky fully configured and `core.hooksPath`
empty, and a config-only probe would happily stomp it.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

#: The gate, relative to a skill directory farrier rendered.
GATE_SCRIPT = "scripts/check_staged_files.py"

#: Where the rendered ostler skill lands, per assistant adapter. The shim tries them in
#: order so a repo that installs only one of them still gets a working hook.
GATE_CANDIDATES = (
    ".claude/skills/stablemate-ostler/scripts/check_staged_files.py",
    ".agents/skills/stablemate-ostler/scripts/check_staged_files.py",
    ".github/skills/stablemate-ostler/scripts/check_staged_files.py",
)

#: First line of the body farrier owns. Its presence is what says "we wrote this and may
#: rewrite it"; its absence on an existing hook is what turns an install into a refusal.
HOOK_MARKER = "# >>> farrier: staged-files gate (generated) >>>"

#: The default drop site when the repo has no hook manager. `core.hooksPath` points here
#: so the hook is tracked and every clone gets it — `.git/hooks/` is per-clone and
#: invisible to review.
HOOKS_DIR = ".githooks"

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


def hook_text() -> str:
    candidates = "\n".join(f'  "$root/{rel}" \\' for rel in GATE_CANDIDATES).rstrip(" \\")
    return f"""#!/bin/sh
{HOOK_MARKER}
# Refuses a commit carrying QA evidence or an oversized blob. The rules, and the
# `[check-staged-files]` allowlist that excuses a path, live in the script — see the
# `stablemate-ostler` skill. Delete this file to opt out; `farrier install` rewrites it.
set -eu

root=$(git rev-parse --show-toplevel)

for gate in \\
{candidates}
do
  [ -f "$gate" ] || continue
  exec python3 "$gate"
done

echo "pre-commit: the staged-files gate is not installed — run \\`farrier install\\`" >&2
exit 1
"""


#: What to paste, per manager farrier will not edit for you.
SNIPPETS = {
    "husky": (
        "  .husky/pre-commit already exists. Append:\n\n"
        "    python3 .claude/skills/stablemate-ostler/scripts/check_staged_files.py\n"
    ),
    "pre-commit": (
        "  .pre-commit-config.yaml is yours. Add:\n\n"
        "    - repo: local\n"
        "      hooks:\n"
        "        - id: staged-files\n"
        "          name: staged-files gate\n"
        "          entry: python3 .claude/skills/stablemate-ostler/scripts/check_staged_files.py\n"
        "          language: system\n"
        "          pass_filenames: false\n"
    ),
    "lefthook": (
        "  lefthook.yml is yours. Add:\n\n"
        "    pre-commit:\n"
        "      commands:\n"
        "        staged-files:\n"
        "          run: python3 .claude/skills/stablemate-ostler/scripts/check_staged_files.py\n"
    ),
    "hook": (
        "  A pre-commit hook farrier did not write is already there. Append:\n\n"
        "    python3 .claude/skills/stablemate-ostler/scripts/check_staged_files.py\n"
    ),
}


@dataclass(frozen=True)
class HookPlan:
    """What farrier would do about the `pre-commit` hook, decided before it writes."""

    action: str  # "write" | "refuse" | "current"
    path: Path | None = None
    set_hooks_path: bool = False
    reason: str = ""
    snippet: str = ""


def _has_husky(repo: Path) -> bool:
    if (repo / ".husky").is_dir():
        return True
    package = repo / "package.json"
    return package.is_file() and "husky" in package.read_text(encoding="utf-8")


def _framework(repo: Path) -> str | None:
    for name in (".pre-commit-config.yaml", ".pre-commit-config.yml"):
        if (repo / name).is_file():
            return "pre-commit"
    for name in ("lefthook.yml", "lefthook.yaml", ".lefthook.yml", ".lefthook.yaml"):
        if (repo / name).is_file():
            return "lefthook"
    if _has_husky(repo):
        return "husky"
    return None


def _configured_hooks_dir(repo: Path) -> str | None:
    """`core.hooksPath`, if this repo sets one. Corroboration, never the sole signal."""
    result = subprocess.run(
        ("git", "config", "--get", "core.hooksPath"),
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    value = result.stdout.strip()
    return value or None


def _ours(path: Path) -> bool:
    return path.is_file() and HOOK_MARKER in path.read_text(encoding="utf-8")


def plan_hook(repo: Path) -> HookPlan:
    framework = _framework(repo)
    if framework in ("pre-commit", "lefthook"):
        return HookPlan(
            action="refuse",
            reason=f"this repo uses {framework}, whose config farrier does not edit",
            snippet=SNIPPETS[framework],
        )

    if framework == "husky":
        hook = repo / ".husky" / "pre-commit"
        if hook.exists() and not _ours(hook):
            return HookPlan(
                action="refuse",
                reason="husky already has a pre-commit hook",
                snippet=SNIPPETS["husky"],
            )
        return HookPlan(action="write", path=hook)

    hooks_dir = _configured_hooks_dir(repo) or HOOKS_DIR
    hook = repo / hooks_dir / "pre-commit"
    if hook.exists() and not _ours(hook):
        return HookPlan(
            action="refuse",
            reason=f"{hooks_dir}/pre-commit is not farrier's",
            snippet=SNIPPETS["hook"],
        )
    legacy = repo / ".git" / "hooks" / "pre-commit"
    if _configured_hooks_dir(repo) is None and legacy.is_file():
        # Pointing `core.hooksPath` at `.githooks` would stop git ever running this one,
        # and nothing would say so — the hook simply stops firing.
        return HookPlan(
            action="refuse",
            reason=".git/hooks/pre-commit is in place and setting core.hooksPath would silence it",
            snippet=SNIPPETS["hook"],
        )
    return HookPlan(action="write", path=hook, set_hooks_path=hooks_dir == HOOKS_DIR)


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


def install_hook(repo: Path) -> str:
    """Write the hook, or explain why farrier will not. Returns the line to print."""
    plan = plan_hook(repo)
    if plan.action == "refuse":
        return (
            f"Skipped the staged-files pre-commit hook: {plan.reason}.\n{plan.snippet}"
        )

    assert plan.path is not None
    plan.path.parent.mkdir(parents=True, exist_ok=True)
    text = hook_text()
    changed = not plan.path.is_file() or plan.path.read_text(encoding="utf-8") != text
    if changed:
        plan.path.write_text(text, encoding="utf-8")
    mode = plan.path.stat().st_mode
    plan.path.chmod(mode | ((mode & 0o444) >> 2))
    if plan.set_hooks_path:
        subprocess.run(
            ("git", "config", "core.hooksPath", HOOKS_DIR),
            cwd=repo,
            capture_output=True,
            check=False,
        )
    rel = plan.path.relative_to(repo).as_posix()
    return f"{'Installed' if changed else 'Verified'} the staged-files pre-commit hook ({rel})"

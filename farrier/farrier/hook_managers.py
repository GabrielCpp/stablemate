"""Wire farrier's one git-hook command into whichever hook manager the repo uses.

Farrier's older doctrine was file-drop: it wrote a whole `pre-commit` hook it owned, or
it refused and printed a snippet to paste. That is why the staged-files gate has never
been installed in *this* repo — `.githooks/pre-commit` was already somebody else's, so
farrier declined, silently, for as long as the file has existed. A gate nobody notices
is not installed is worse than no gate: every report still says the install succeeded.

So ownership gets finer instead of louder. Farrier claims **one fenced region** of the
manager's file:

    # >>> farrier: hooks (generated) >>>
    ...
    # <<< farrier: hooks <<<

Line-oriented, like the two fences that already ship (`QA_GITIGNORE_BLOCK` in
`.gitignore`, `MAKEFILE_INCLUDE_MARKER` in the root `Makefile`), which is what keeps
`pyyaml` farrier's only parsing dependency: reading `.pre-commit-config.yaml` in order
to write it back would mean a round-tripping loader, and a round-trip that reflows the
user's comments is an edit to their file we did not intend to make.

Inside the fence there is always exactly one command, `make farrier-run-hook`, and what
that runs is a file farrier owns whole (`.agents/hooks/pre-commit`, plus the drift check
built into the target itself). Everything per-repo lives on farrier's side of the fence,
so the region spliced into the user's file is the same few lines in every repo and does
not churn when a skill selection changes.

Which manager to wire is **declared, not sniffed** — `agents.yml`:

    hooks:
      manager: pre-commit    # | lefthook | husky | githooks | none

Detection remains as the default for a repo that says nothing, because that is what
farrier did before and a config key that must be set before hooks work at all would
silently turn them off for every repo already installed. `none` is the opt-out; deleting
the fence is not one, since `agents.yml` is the authority on what is installed and the
next `farrier install` puts it back.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from farrier.skill_hooks import SkillHook

#: The command inside the fence. Deliberately outside the `agent-*` namespace:
#: `.agents/agents.mk` mints a dynamic `agent-run-<workflow>` target per installed
#: workflow, so `agent-run-hook` would collide with a workflow named `hook`.
HOOK_COMMAND = "make farrier-run-hook"

FENCE_START = "# >>> farrier: hooks (generated) >>>"
FENCE_END = "# <<< farrier: hooks <<<"

#: The per-repo half: the skill-declared hooks, rendered as a script farrier owns whole
#: and `make farrier-run-hook` execs. A generated output like any other, so a hand-edit
#: to it is drift and reports itself as drift.
HOOK_RUNNER = ".agents/hooks/pre-commit"

#: lefthook's body, kept out of `lefthook.yml` entirely — `extends:` lets the fence in
#: the user's file be a single reference and the commands live in a file we own.
LEFTHOOK_INCLUDE = ".agents/lefthook.farrier.yml"

MANAGERS = ("pre-commit", "lefthook", "husky", "githooks", "none")

#: Where the fence goes, per manager. `none` splices nowhere and strips everywhere.
_FENCE_FILES = {
    "pre-commit": ".pre-commit-config.yaml",
    "lefthook": "lefthook.yml",
    "husky": ".husky/pre-commit",
    "githooks": ".githooks/pre-commit",
}

#: The first line of the body farrier used to own *whole-file*. A repo still carrying it
#: is migrated rather than appended to — appending would leave the old gate invocation
#: and the new one both in the file, running the same check twice and reporting it twice.
LEGACY_HOOK_MARKER = "# >>> farrier: staged-files gate (generated) >>>"


def configured_manager(config: dict[str, Any], repo: Path) -> str:
    """The manager named in `agents.yml`, or the one this repo looks like."""
    declared = str(((config.get("hooks") or {}) if isinstance(config.get("hooks"), dict)
                    else {}).get("manager") or "").strip()
    if not declared:
        return detect_manager(repo)
    if declared not in MANAGERS:
        raise SystemExit(
            f"agents.yml: hooks.manager: {declared!r} is not one of "
            f"{', '.join(MANAGERS)}"
        )
    return declared


def detect_manager(repo: Path) -> str:
    """What the repo looks like, by marker file.

    `core.hooksPath` is corroboration only and never the sole signal: a husky repo whose
    `npm install` has not run yet is fully configured with that config empty, and a
    config-only probe would call it bare and wire the wrong manager into it.
    """
    for name in (".pre-commit-config.yaml", ".pre-commit-config.yml"):
        if (repo / name).is_file():
            return "pre-commit"
    for name in ("lefthook.yml", "lefthook.yaml", ".lefthook.yml", ".lefthook.yaml"):
        if (repo / name).is_file():
            return "lefthook"
    if (repo / ".husky").is_dir():
        return "husky"
    package = repo / "package.json"
    if package.is_file() and "husky" in package.read_text(encoding="utf-8"):
        return "husky"
    return "githooks"


# ---------------------------------------------------------------------------
# the fence
# ---------------------------------------------------------------------------


def fence(body: str) -> str:
    """*body* wrapped in the marker pair, as a block of whole lines."""
    return f"{FENCE_START}\n{body.strip(chr(10))}\n{FENCE_END}\n"


def splice(existing: str, block: str) -> str:
    """*existing* with the farrier fence replaced in place, or appended if absent."""
    lines = existing.splitlines()
    if FENCE_START in lines and FENCE_END in lines:
        head = lines[: lines.index(FENCE_START)]
        tail = lines[lines.index(FENCE_END) + 1 :]
        joined = "\n".join([*head, *block.rstrip("\n").splitlines(), *tail])
        return joined.rstrip("\n") + "\n"
    prefix = existing
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    return prefix + block


def unsplice(existing: str) -> str:
    """*existing* with the farrier fence removed. The `manager: none` operation."""
    lines = existing.splitlines()
    if FENCE_START not in lines or FENCE_END not in lines:
        return existing
    head = lines[: lines.index(FENCE_START)]
    tail = lines[lines.index(FENCE_END) + 1 :]
    body = "\n".join([*head, *tail]).rstrip("\n")
    return body + "\n" if body else ""


def fenced_body(existing: str) -> str | None:
    """What is currently inside the fence, or None when there is no fence."""
    lines = existing.splitlines()
    if FENCE_START not in lines or FENCE_END not in lines:
        return None
    start = lines.index(FENCE_START)
    end = lines.index(FENCE_END)
    return "\n".join(lines[start + 1 : end])


# ---------------------------------------------------------------------------
# what each manager's fence contains
# ---------------------------------------------------------------------------

_PRE_COMMIT_ENTRY = f"""  - repo: local
    hooks:
      - id: farrier-hooks
        name: farrier generated-file gate and skill hooks
        entry: {HOOK_COMMAND}
        language: system
        pass_filenames: false
        stages: [pre-commit]"""

_LEFTHOOK_ENTRY = f"""extends:
  - {LEFTHOOK_INCLUDE}"""

_LEFTHOOK_FILE = f"""# Generated by farrier. Do not edit — `farrier install` rewrites it.
#
# lefthook.yml carries a one-line `extends:` inside farrier's fence and this file
# carries the commands, so the region spliced into your config stays a reference
# rather than a body that churns whenever a skill selection changes.
pre-commit:
  commands:
    farrier-hooks:
      run: {HOOK_COMMAND}
"""

_SHELL_ENTRY = HOOK_COMMAND

_SHELL_PREAMBLE = """#!/bin/sh
# The repo's pre-commit hook. Farrier owns only the fenced region below; anything
# outside it is yours and survives `farrier install`.
set -eu
"""


def body_for(manager: str) -> str:
    if manager == "pre-commit":
        return _PRE_COMMIT_ENTRY
    if manager == "lefthook":
        return _LEFTHOOK_ENTRY
    return _SHELL_ENTRY


def lefthook_include_text() -> str:
    return _LEFTHOOK_FILE


def runner_text(hooks: list[SkillHook]) -> str:
    """`.agents/hooks/pre-commit` — every skill-declared hook, in selection order.

    The drift check is *not* here: it is built into the `farrier-run-hook` target so it
    runs whether or not any skill declares anything, and so deleting this file cannot
    turn it off. What is here is per-repo by nature, which is also why it is a rendered
    output rather than a line in the byte-identical `agents.mk`.
    """
    lines = [
        "#!/bin/sh",
        "# Generated by farrier from the `hooks:` front matter of the installed skills.",
        "# Do not edit — `farrier install` rewrites it. Add or remove a hook by changing",
        "# the skill that declares it, or by changing which skills `agents.yml` selects.",
        "set -eu",
        "",
        'root=$(git rev-parse --show-toplevel)',
        "",
    ]
    if not hooks:
        lines += ["# No installed skill declares a pre-commit hook.", "exit 0", ""]
        return "\n".join(lines)
    for hook in hooks:
        lines += [f"# {hook.skill}"]
        candidates = " ".join(
            f'"$root/{root}/{hook.skill}/{hook.run}"'
            for root in (".claude/skills", ".agents/skills", ".github/skills")
        )
        lines += [
            f"for gate in {candidates}; do",
            '  [ -f "$gate" ] || continue',
            '  python3 "$gate"',
            "  break",
            "done",
            "",
        ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# installing it
# ---------------------------------------------------------------------------


def _make_executable(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode | ((mode & 0o444) >> 2))


def _set_hooks_path(repo: Path, value: str) -> None:
    subprocess.run(
        ("git", "config", "core.hooksPath", value),
        cwd=repo,
        capture_output=True,
        check=False,
    )


def install_manager(repo: Path, manager: str) -> list[str]:
    """Splice (or strip) farrier's fence. Returns the lines to print."""
    if manager == "none":
        removed = []
        for rel in _FENCE_FILES.values():
            path = repo / rel
            if not path.is_file():
                continue
            existing = path.read_text(encoding="utf-8")
            stripped = unsplice(existing)
            if stripped != existing:
                path.write_text(stripped, encoding="utf-8")
                removed.append(rel)
        return [f"Removed farrier's hook entry from {rel}" for rel in removed]

    rel = _FENCE_FILES[manager]
    path = repo / rel
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if LEGACY_HOOK_MARKER in existing:
        # Whole-file ownership, from before the fence existed. Appending to it would
        # leave the old gate invocation beside the new one — the same check twice, and
        # the second report reading as a second problem.
        existing = ""
    if manager in ("husky", "githooks") and not existing.strip():
        existing = _SHELL_PREAMBLE

    desired = splice(existing, fence(body_for(manager)))
    if manager == "pre-commit" and not any(
        line.startswith("repos:") for line in desired.splitlines()
    ):
        desired = "repos:\n" + desired

    messages: list[str] = []
    if desired != (path.read_text(encoding="utf-8") if path.is_file() else None):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(desired, encoding="utf-8")
        messages.append(f"Wired `{HOOK_COMMAND}` into {rel}")
    if manager in ("husky", "githooks"):
        _make_executable(path)
    if manager == "githooks":
        _set_hooks_path(repo, ".githooks")
    return messages


def fence_drift(repo: Path, manager: str) -> list[str]:
    """The fenced regions that no longer match what farrier would write.

    Reported by `--check` for the same reason a generated file is: the region is
    farrier's, `install` overwrites it, and an edit made there is an edit about to be
    lost. A *missing* fence counts — `agents.yml` is the authority on what is installed,
    so deleting the block is drift rather than an opt-out (`manager: none` is the
    opt-out).
    """
    if manager == "none":
        return [
            rel
            for rel in _FENCE_FILES.values()
            if (repo / rel).is_file()
            and fenced_body((repo / rel).read_text(encoding="utf-8")) is not None
        ]
    rel = _FENCE_FILES[manager]
    path = repo / rel
    if not path.is_file():
        return [rel]
    body = fenced_body(path.read_text(encoding="utf-8"))
    return [] if body == body_for(manager) else [rel]

"""A skill's declaration that one of its scripts must run at a git hook.

A library skill is text and files; the one thing it cannot do is get itself *run*.
Until now farrier closed that gap by knowing about one skill by name — the ostler
staged-files gate was hardcoded in ``hooks``, so a second skill wanting a hook meant a
second special case in farrier, and a repo that wanted only the first still carried the
machinery for both.

The declaration moves into the skill instead::

    hooks:
      - stage: pre-commit
        run: scripts/check_staged_files.py

Selecting the skill selects its hook, and farrier stops naming any skill in particular.

**Declared, not discovered.** A script under ``scripts/`` is not a hook by virtue of
being there — a skill bundles helpers it means the *agent* to run, and installing those
into every commit would be a surprise nobody asked for and nobody could see coming.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The git hooks farrier wires. Deliberately short: every stage here has to be
#: implemented in each of the five hook managers, and a stage nothing declares is
#: machinery with no user. Widening it is this tuple plus the manager wiring — the
#: validation and the render already read from here.
STAGES = ("pre-commit",)


@dataclass(frozen=True)
class SkillHook:
    """One ``hooks:`` entry, bound to the skill that declared it."""

    #: The skill's *installed* name (prefixed), which is what the run path contains.
    skill: str
    stage: str
    #: The script, relative to the skill directory — as written in the front matter.
    run: str


def declared(data: dict[str, Any]) -> list[dict[str, Any]]:
    """The raw ``hooks:`` entries of a parsed front matter, dropping malformed shapes.

    Lenient by design, and safe because ``farrier library --check --strict`` is the gate
    that refuses the malformed ones. Install must not raise on a library it did not
    write: a repo pinned to an older base library would otherwise stop installing
    entirely because one skill it does not even select has a typo in a key.
    """
    entries = data.get("hooks")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def hooks_for(skill: str, data: dict[str, Any]) -> list[SkillHook]:
    """The valid, wireable hooks a skill declares. Silently drops the rest — see
    ``declared`` for why install is the wrong place to raise."""
    out: list[SkillHook] = []
    for entry in declared(data):
        stage = str(entry.get("stage") or "").strip()
        run = str(entry.get("run") or "").strip()
        if stage in STAGES and run:
            out.append(SkillHook(skill=skill, stage=stage, run=run))
    return out


def findings(data: dict[str, Any], source_dir: Path) -> list[tuple[str, str, str]]:
    """``(level, code, message)`` for every problem with a source's ``hooks:`` block.

    *source_dir* is the skill's directory, so ``run:`` can be checked for pointing at a
    file that exists. That check is the load-bearing one: a hook naming a script the
    skill does not ship installs fine, and fails at the moment somebody commits — which
    is both the worst time to discover it and the time farrier looks most like the
    culprit.
    """
    raw = data.get("hooks")
    if raw is None:
        return []
    if not isinstance(raw, list):
        return [(
            "error", "hooks-not-a-list",
            "`hooks:` must be a list of `- stage: ... run: ...` entries; farrier reads "
            "any other shape as no hooks at all, so the script silently never runs.",
        )]
    out: list[tuple[str, str, str]] = []
    for index, entry in enumerate(raw):
        where = f"hooks[{index}]"
        if not isinstance(entry, dict):
            out.append((
                "error", "hook-not-a-mapping",
                f"{where} is not a mapping — each entry needs `stage:` and `run:`.",
            ))
            continue
        stage = str(entry.get("stage") or "").strip()
        run = str(entry.get("run") or "").strip()
        if not stage:
            out.append((
                "error", "hook-no-stage",
                f"{where} has no `stage:` — farrier would not know when to run it. "
                f"Accepted: {', '.join(STAGES)}.",
            ))
        elif stage not in STAGES:
            out.append((
                "error", "hook-unknown-stage",
                f"{where} declares `stage: {stage}`, which farrier does not wire. "
                f"Accepted: {', '.join(STAGES)}.",
            ))
        if not run:
            out.append((
                "error", "hook-no-run",
                f"{where} has no `run:` — there is nothing for the hook to execute.",
            ))
            continue
        if Path(run).is_absolute() or ".." in Path(run).parts:
            out.append((
                "error", "hook-run-escapes",
                f"{where} `run: {run}` must be relative to the skill directory and stay "
                "inside it — farrier installs the skill's own files and nothing else, so "
                "any other path names something that will not be there.",
            ))
        elif not (source_dir / run).is_file():
            out.append((
                "error", "hook-run-missing",
                f"{where} `run: {run}` is not a file in this skill. The hook installs "
                "anyway and fails at the moment somebody commits, which is the worst "
                "time to find out and the point farrier looks most like the culprit.",
            ))
    return out

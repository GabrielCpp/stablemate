"""A skill's declaration that one of its scripts must run at a git hook."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

STAGES = ("pre-commit",)


@dataclass(frozen=True)
class SkillHook:
    """One ``hooks:`` entry, bound to the skill that declared it."""

    skill: str
    stage: str
    run: str


def declared(data: dict[str, Any]) -> list[dict[str, Any]]:
    """The raw ``hooks:`` entries of a parsed front matter, dropping malformed shapes."""
    entries = data.get("hooks")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def hooks_for(skill: str, data: dict[str, Any]) -> list[SkillHook]:
    """The valid, wireable hooks a skill declares."""
    out: list[SkillHook] = []
    for entry in declared(data):
        stage = str(entry.get("stage") or "").strip()
        run = str(entry.get("run") or "").strip()
        if stage in STAGES and run:
            out.append(SkillHook(skill=skill, stage=stage, run=run))
    return out


def findings(data: dict[str, Any], source_dir: Path) -> list[tuple[str, str, str]]:
    """``(level, code, message)`` for every problem with a source's ``hooks:`` block."""
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

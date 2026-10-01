#!/usr/bin/env python3
"""Guard the base library's writing doctrine."""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

from ostler import markdown

CONFIG = ".agent-checks.toml"
TABLE = "check-skills"

BUDGET = 250

ASSET_DIRS = ("references", "scripts")

_WORDISH = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_./"

def declarations(root: Path) -> dict:
    """What *root*'s repo declares to this check, from its `.agent-checks.toml`."""
    config = root / CONFIG
    if not config.is_file():
        return {}
    return tomllib.loads(config.read_text(encoding="utf-8")).get(TABLE, {})


def _assets(skill_dir: Path) -> list[str]:
    """Every bundled asset under a skill, relative to the skill directory."""
    return sorted(
        path.relative_to(skill_dir).as_posix()
        for name in ASSET_DIRS
        if (skill_dir / name).is_dir()
        for path in (skill_dir / name).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def _linked(skill_dir: Path, body: str) -> set[str]:
    """Bundled assets the body points at, relative to the skill directory."""
    out: set[str] = set()
    for _text, href, _line in markdown.iter_links(body):
        target = href.split("#", 1)[0].strip()
        if not target or "://" in target:
            continue
        resolved = (skill_dir / target).resolve()
        if resolved.is_relative_to(skill_dir):
            out.add(resolved.relative_to(skill_dir).as_posix())
    return out


def _names_prompt(body: str, prompt: str) -> bool:
    """True when the body names `/<prompt>` as a slash command rather than inside a path."""
    needle = f"/{prompt}"
    index = body.find(needle)
    while index != -1:
        before = body[index - 1] if index else " "
        after = body[index + len(needle):index + len(needle) + 1]
        if before not in _WORDISH and after not in _WORDISH:
            return True
        index = body.find(needle, index + 1)
    return False


def check_skills(root: Path) -> list[str]:
    """Every skill is under budget or discloses, every asset is reachable, no skill drives a prompt — and every declared exemption is still live."""
    declared = declarations(root)
    allowed: dict[str, str] = declared.get("allow", {})
    skills_dir = root / declared.get("skills", ".")
    prompts_dir = root / declared["prompts"] if "prompts" in declared else None

    problems: list[str] = []
    prompts = sorted(path.stem for path in prompts_dir.rglob("*.md")) if prompts_dir else []
    used: set[str] = set()
    skills = sorted(skills_dir.rglob("SKILL.md"))

    for path in skills:
        rel = path.relative_to(root).as_posix()
        name = path.parent.name
        doc = markdown.split(path.read_text(encoding="utf-8"))
        assets = _assets(path.parent)

        lines = len(doc.body.strip().splitlines())
        if lines > BUDGET and not assets:
            if name in allowed:
                used.add(name)
            else:
                problems.append(
                    f"{rel}: {lines} body lines, budget {BUDGET}, nothing disclosed.\n"
                    f"      Push the reference only some branches reach into "
                    f"{name}/references/<topic>.md and link it from the body."
                )

        linked = _linked(path.parent, doc.body)
        for asset in assets:
            if asset not in linked:
                problems.append(
                    f"{rel}: bundled asset {asset!r} is never linked from the body.\n"
                    f"      It installs into every consuming repo and is never read. Add a "
                    f"pointer saying what is in it and which branches reach it."
                )

        for prompt in prompts:
            if _names_prompt(doc.body, prompt):
                problems.append(
                    f"{rel}: instructs running the `/{prompt}` prompt.\n"
                    f"      A prompt is a human entry point — a skill never fires one. Point "
                    f"at a skill, or inline what this skill actually needs."
                )

    for name in allowed:
        if name not in used:
            problems.append(
                f"{name}: the exemption no longer applies — the skill is under budget or now "
                f"discloses. Delete it from [{TABLE}.allow] in {CONFIG}"
            )

    if not problems:
        print(
            f"ok: {len(skills)} skills under the writing doctrine "
            f"(budget {BUDGET} body lines, {len(allowed)} declared)"
        )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(), help=f"repo holding {CONFIG} (default: cwd)"
    )
    args = parser.parse_args()

    allowed: dict[str, str] = declarations(args.root).get("allow", {})
    problems = check_skills(args.root)
    if not problems:
        return 0
    print("\nFAIL check_skills:", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    print(
        "\nA document an agent reads is only as good as the part it attends to. See the "
        "`farrier-skills-writing` skill for the information hierarchy, the pointer that "
        "makes disclosed material reachable, and the skill/prompt direction.",
        file=sys.stderr,
    )
    if allowed:
        print("\nAlready declared:", file=sys.stderr)
        for name, why in sorted(allowed.items()):
            print(f"  {name} — {why.strip()}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

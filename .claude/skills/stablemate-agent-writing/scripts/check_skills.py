#!/usr/bin/env python3
"""Guard the base library's writing doctrine. Wired into `make test`.

Three failures this catches, each of which leaves a skill installing cleanly and reading
fine to a human:

**Sprawl.** A `SKILL.md` long enough that the agent stops attending to all of it. Nothing
errors and nothing is missing — the material is there, and read on some runs and not
others. Farrier has shipped per-skill `references/` assets since `test_skill_assets`, so
the cure already exists; this makes not using it visible. The budget is deliberately
generous: it is a sprawl alarm, not a style rule, and a skill that discloses anything at
all is trusted to have made the judgement itself.

**Unreachable disclosure.** A bundled asset nothing links to. Farrier installs it
faithfully, so it lands in every consuming repo and is never read — material with no
pointer, the one shape the doctrine says cannot work.

**A skill driving a prompt.** A prompt is a human entry point; a skill firing one inverts
control and hides a dependency behind a name the model cannot resolve on its own. Prompts
point at skills, never the reverse.

**What this is not.** It cannot tell a well-worded pointer from a weak one, or a no-op
sentence from a load-bearing one — the levers that actually decide whether a document
works. Those stay in review. Same character as `check_parsers.py`: a guard against known
silent failures, not a proof. The prompt rule reads `SKILL.md` bodies only, since a
`references/` file may legitimately quote the form it forbids (the `agent-writing`
mechanics reference does exactly that).

The rule and the vocabulary live in the `agent-writing` skill, which is what this script
installs beside — so it runs in any repo that authors skills. Where that repo keeps them
is its own to state, in `[check-skills]` of `.agent-checks.toml`; a repo that states
nothing is swept whole, which is the right answer for a library repo whose skills are the
tree.

Run:
    uv run python <this script> [--root DIR]
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

from ostler import markdown

#: Repo-local declarations, read from the root of whatever repo is being checked.
CONFIG = ".agent-checks.toml"
TABLE = "check-skills"

#: Body lines of a `SKILL.md` past which a skill must be disclosing something. Set above the
#: library's median so it flags the genuinely sprawling, not the merely thorough.
BUDGET = 250

#: Directories farrier ships beside a `SKILL.md` (`farrier.sources.ASSET_DIRS`).
ASSET_DIRS = ("references", "scripts")

#: Characters that continue a word, so `/commit` is told from `stablemate/commit.md`.
_WORDISH = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_./"

def declarations(root: Path) -> dict:
    """What *root*'s repo declares to this check, from its `.agent-checks.toml`.

    Two keys, both optional: `skills` and `prompts`, each a path relative to the root. The
    `allow` table is `skill name` → why it carries its length with nothing disclosed; it is
    printed on failure and checked for staleness, so a reason cannot outlive the file it
    excuses.
    """
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
        if path.is_file()
    )


def _linked(skill_dir: Path, body: str) -> set[str]:
    """Bundled assets the body points at, relative to the skill directory.

    Read off the markdown link tokens, so a path named inside a fenced example — a layout
    diagram is the usual one — is not mistaken for a live pointer.
    """
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
    """True when the body names `/<prompt>` as a slash command rather than inside a path.

    Prose has no grammar, so this is a word scan and not a parse: a token is the command
    when it starts at a word boundary and nothing word-ish follows it.
    """
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
    """Every skill is under budget or discloses, every asset is reachable, no skill drives a
    prompt — and every declared exemption is still live."""
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

        # 1. Sprawl — long, with nothing pushed down the hierarchy.
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

        # 2. Disclosure nothing points at.
        linked = _linked(path.parent, doc.body)
        for asset in assets:
            if asset not in linked:
                problems.append(
                    f"{rel}: bundled asset {asset!r} is never linked from the body.\n"
                    f"      It installs into every consuming repo and is never read. Add a "
                    f"pointer saying what is in it and which branches reach it."
                )

        # 3. A skill driving a prompt.
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
        "`stablemate-agent-writing` skill for the information hierarchy, the pointer that "
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

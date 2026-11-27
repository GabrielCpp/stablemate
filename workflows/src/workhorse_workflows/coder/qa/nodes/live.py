"""The live-check runbook gate: a claim the owner leaves to a person needs a plan in plan-qa form."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.qa import QaPlanValidation

LIVE_RUNBOOK_FILE = "manual-qa.md"

_ENTRY = re.compile(r"^ac:(\d+): \S")
_STEP = re.compile(r"^## (\d+)\) \S")
_HEADING = re.compile(r"^## .*$", re.MULTILINE)
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*\|", re.MULTILINE)
_PLACEHOLDER = re.compile(r"<[a-z][a-z0-9_ -]*>")


def _criteria(live: list[str]) -> tuple[list[int], list[str]]:
    numbers: list[int] = []
    problems: list[str] = []
    for entry in live:
        match = _ENTRY.match(entry)
        if match:
            numbers.append(int(match.group(1)))
        else:
            problems.append(f"the live entry `{entry}` does not start with `ac:<n>: `")
    return numbers, problems


def _sections(text: str) -> list[tuple[str, str]]:
    heads = list(_HEADING.finditer(text))
    return [
        (h.group(0), text[h.end() : heads[i + 1].start() if i + 1 < len(heads) else len(text)])
        for i, h in enumerate(heads)
    ]


def _steps(sections: list[tuple[str, str]]) -> list[tuple[int, str, str]]:
    found: list[tuple[int, str, str]] = []
    for head, body in sections:
        match = _STEP.match(head)
        if match:
            found.append((int(match.group(1)), head, body))
    return found


def _step_problems(steps: list[tuple[int, str, str]]) -> list[str]:
    if not steps:
        return ["it has no numbered step headed `## 1) ...`"]
    problems: list[str] = []
    numbers = [n for n, _, _ in steps]
    if numbers != list(range(1, len(numbers) + 1)):
        problems.append(f"its steps are numbered {numbers}, not 1 to {len(numbers)} in order")
    for _, head, body in steps:
        if "$QA_DIR/ac" not in body:
            problems.append(f"step `{head}` saves no evidence under `$QA_DIR/ac<n>-<slug>/`")
        if "verdict" not in body.lower():
            problems.append(f"step `{head}` states no verdict rule")
    return problems


def _form_problems(text: str, target_env: str) -> list[str]:
    problems: list[str] = []
    if not re.search(r"^# \S", text, re.MULTILINE):
        problems.append("it has no `# ` title")
    if target_env and target_env.lower() not in text.lower():
        problems.append(f"it never names the environment it runs against, `{target_env}`")
    if "QA_DIR=" not in text or "mkdir -p" not in text:
        problems.append("it does not define `QA_DIR=` and `mkdir -p` its evidence folders")
    if _TABLE_RULE.search(text):
        problems.append("it uses a Markdown table")
    if re.search(r"^\s*#!", text, re.MULTILINE):
        problems.append("it carries a shell script block")
    if _PLACEHOLDER.search(text) and "inputs needed" not in text.lower():
        problems.append("it uses a `<placeholder>` with no `Inputs Needed` section")
    return problems


def _manifest_problems(
    sections: list[tuple[str, str]], steps: list[tuple[int, str, str]], numbers: list[int]
) -> list[str]:
    if not sections or "evidence manifest" not in sections[-1][0].lower():
        return ["its last section is not the `Evidence manifest`"]
    manifest = sections[-1][1]
    evidence = "".join(body for _, _, body in steps)
    problems: list[str] = []
    for n in sorted(set(numbers)):
        if f"$QA_DIR/ac{n}-" not in evidence:
            problems.append(f"no step saves evidence for ac:{n} under `$QA_DIR/ac{n}-<slug>/`")
        if f"ac{n}-" not in manifest:
            problems.append(f"the evidence manifest lists nothing for ac:{n}")
    return problems


def runbook_problems(spec_dir: Path, live: list[str], target_env: str) -> list[str]:
    """Every way the owner's live claims and their runbook miss the plan-qa form."""
    numbers, problems = _criteria(live)
    path = spec_dir / LIVE_RUNBOOK_FILE
    if not path.is_file():
        return [*problems, f"`{path}` does not exist"]
    text = path.read_text(encoding="utf-8")
    sections = _sections(text)
    steps = _steps(sections)
    problems += _form_problems(text, target_env)
    problems += _step_problems(steps)
    if not any("cleanup" in head.lower() for head, _ in sections):
        problems.append("it has no cleanup section")
    return problems + _manifest_problems(sections, steps, numbers)


def unlived(live: list[str], owed: list[int], unreached: list[str]) -> list[str]:
    """What a story with no scenario plan still owes when its live checks are its whole proof."""
    numbers, _ = _criteria(live)
    problems = [f"no scenario plan stands, and ac:{n} is not a live check" for n in owed if n not in numbers]
    return problems + [f"no scenario plan stands, and the books left a claim only a scenario shows: {c}" for c in unreached]


@blueprint.node
def lint_live_runbook(
    logger: logging.Logger, spec_dir: str = "", live: list[str] | None = None, target_env: str = ""
) -> QaPlanValidation:
    """Does the runbook for the owner's live claims stand in plan-qa form?"""
    problems = runbook_problems(Path(spec_dir), live or [], target_env)
    for problem in problems:
        logger.info("live runbook: %s", problem)
    notes = "\n".join(f"- {p}" for p in problems)
    return QaPlanValidation(status="invalid" if problems else "passed", notes=notes)

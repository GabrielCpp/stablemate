"""disagree: when the app and the book disagree, can an agent say which one is wrong?"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import _greenfield as gf
from _stablemate import TrialError
from paddock import Run, Score, step, task

CONFIG = "configs/opencode.toml"

task(
    name="globex-book-disagree",
    seed="globex",
    config=CONFIG,
)

TARGET_DOC = "features/web-app/gui/screens/widget-list.md"

TARGET_APP = "app/web-app/static/index.html"

OBSERVED_TEXT = "Add a widget"
MUTATED_TEXT = "Create a widget"

ARMS: tuple[str, ...] = ("agree", "app-wrong", "book-wrong")

QUESTION = (
    "You are working in a repo that ships a documentation book at `docs/`, laid out as "
    "an OKF book, alongside the app's own source under `app/` and a `compose.yml`. A "
    "Playwright browser tool is available to you as an MCP server. Nothing is running "
    "yet.\n\n"
    "Bring the stack up, then use a browser to look at the widget directory screen "
    "(web-app's landing page) and compare what you see there with what "
    "`docs/features/web-app/gui/screens/widget-list.md` says about that same screen — in "
    "particular, the label on the link that leads to the add-a-widget form.\n\n"
    "If the app and the book agree, say so. If they disagree, report which one is "
    "wrong — the app, or the book — and how you know. Answer in a few sentences of "
    "prose."
)

EXPECTED: dict[str, str] = {
    "agree": (
        "they agree: `app/web-app/static/index.html` renders the link "
        f'"{OBSERVED_TEXT}", exactly what both `- name:` bullets in '
        f"`docs/{TARGET_DOC}` (the `new-widget-link` component and the `open-new-widget` "
        "interaction) state, and the `- code:` bullet's digest, @ebed722d64ce, still "
        "matches the file on disk — nothing here is wrong."
    ),
    "app-wrong": (
        f'the app is wrong: `app/web-app/static/index.html` now renders "{MUTATED_TEXT}" '
        f'on the link, but both `- name:` bullets in `docs/{TARGET_DOC}` still state '
        f'"{OBSERVED_TEXT}" (the book was never touched), and — the fact that actually '
        "settles which side is at fault — the `- code:` bullet's digest, @ebed722d64ce, "
        "no longer matches the file's contents on disk. The book is unchanged and "
        "correct; the app's own source drifted from it."
    ),
    "book-wrong": (
        f'the book is wrong: both `- name:` bullets in `docs/{TARGET_DOC}` now state '
        f'"{MUTATED_TEXT}", but `app/web-app/static/index.html` still renders '
        f'"{OBSERVED_TEXT}" (the app was never touched), and — the fact that actually '
        "settles which side is at fault — the `- code:` bullet's digest, @ebed722d64ce, "
        "still matches the file's contents on disk unchanged. The app matches its own "
        "citation; the book's prose is what drifted."
    ),
}

MCP_JSON: dict[str, Any] = {
    "mcpServers": {
        "playwright": {
            "command": "npx",
            "args": ["-y", "@playwright/mcp@latest", "--headless"],
        }
    }
}

BENCH_CONTAINERS = ("globex-bench-api-service-1", "globex-bench-web-app-1")

LEVELS: dict[int, tuple[str, str]] = {
    0: (
        "wrong",
        "the agent did not identify the correct side (or, on `agree`, claimed a "
        "disagreement that is not there), or gave no verdict at all",
    ),
    1: (
        "hedged",
        "the agent named the correct side (or correctly said they agree) but its "
        "account rests on the text mismatch alone, without checking the `- code:` "
        "bullet's digest against the file on disk to justify which side is at fault",
    ),
    2: (
        "earned",
        "the agent named the correct side (or correctly said they agree), and its "
        "account explicitly checks the `- code:` bullet's digest against the app file's "
        "contents on disk as part of how it knows",
    ),
}
MAX_LEVEL = max(LEVELS)

TRIALS = ("artifacts", "trials")


def _perturb_app_wrong(app_root: Path) -> dict[str, Any]:
    """Edit the app's own rendered text; never touch `docs/` or restamp any digest."""
    path = app_root / "index.html"
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r'(<a id="new-widget-link" href="new\.html">)' + re.escape(OBSERVED_TEXT)
        + r"(</a>)",
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise TrialError(
            f"expected exactly one new-widget-link anchor in {path}, found {len(matches)}"
        )
    match = matches[0]
    text = text[: match.start()] + match.group(1) + MUTATED_TEXT + match.group(2) \
        + text[match.end() :]
    path.write_text(text, encoding="utf-8")
    return {"kind": "app-wrong", "file": f"app/web-app/static/{path.name}",
            "from": OBSERVED_TEXT, "to": MUTATED_TEXT}


def _perturb_book_wrong(docs_root: Path) -> dict[str, Any]:
    """Edit the book's own prose; never touch `app/` or the `- code:` bullet's digest."""
    path = docs_root / TARGET_DOC
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^- name: {re.escape(OBSERVED_TEXT)}$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if len(matches) != 2:
        raise TrialError(
            f"expected exactly two `- name: {OBSERVED_TEXT}` bullets in {path}, "
            f"found {len(matches)}"
        )
    for match in reversed(matches):
        text = text[: match.start()] + f"- name: {MUTATED_TEXT}" + text[match.end() :]
    path.write_text(text, encoding="utf-8")
    return {"kind": "book-wrong", "file": f"docs/{TARGET_DOC}",
            "from": OBSERVED_TEXT, "to": MUTATED_TEXT}


def _perturb(tree: Path, arm: str) -> tuple[dict[str, Any], str]:
    """Apply `arm`'s edit inside the copy at `tree`; return `(perturbation, expected)`."""
    if arm not in ARMS:
        raise TrialError(f"unknown arm {arm!r}")
    if arm == "agree":
        return {"kind": "none"}, EXPECTED["agree"]
    if arm == "app-wrong":
        detail = _perturb_app_wrong(tree / "app" / "web-app" / "static")
        return detail, EXPECTED["app-wrong"]
    detail = _perturb_book_wrong(tree / "docs")
    return detail, EXPECTED["book-wrong"]


def _trials_dir(run: Run) -> Path:
    directory = run.stage.joinpath(*TRIALS)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _read_matrix(run: Run) -> list[dict[str, Any]]:
    ledger = _trials_dir(run) / "trials.json"
    if not ledger.is_file():
        return []
    return json.loads(ledger.read_text(encoding="utf-8"))


def _write_matrix(run: Run, matrix: list[dict[str, Any]]) -> None:
    run.write_json(_trials_dir(run) / "trials.json", matrix)


def _tree_dir(run: Run, trial_id: str) -> Path:
    return run.scratch / f"tree-{trial_id}"


def _teardown_stack(run: Run, tree: Path, phase: str) -> None:
    """Tear down anything holding globex's hardcoded ports 18101 and 18102."""
    run.cli("docker", "compose", "down", "--remove-orphans", cwd=tree,
           log_name=f"teardown-{phase}-compose-{tree.name}")
    for name in BENCH_CONTAINERS:
        run.cli("docker", "rm", "-f", name, log_name=f"teardown-{phase}-rm-{name}-{tree.name}")


@step()
def arrange(run: Run) -> None:
    """Build one perturbed tree per arm, each a full copy of the seed."""
    matrix: list[dict[str, Any]] = []
    for arm in ARMS:
        trial_id = arm
        tree = run.workdir(f"tree-{trial_id}")
        shutil.copytree(run.repo, tree, dirs_exist_ok=True)
        perturbation, expected = _perturb(tree, arm)
        (tree / ".mcp.json").write_text(
            json.dumps(MCP_JSON, indent=2) + "\n", encoding="utf-8",
        )
        matrix.append({
            "id": trial_id,
            "arm": arm,
            "perturbation": perturbation,
            "expected": expected,
            "answer": "",
            "level": 0,
            "evidence": [],
            "reason": "",
        })
    _write_matrix(run, matrix)


def _asker(run: Run) -> Any:
    return gf.Judge(
        gf.get_backend(run.param("ask_cli") or None),
        gf.AgentResilience.from_env(), gf.SYSTEM_CLOCK,
        model=run.param("ask_model"), effort=run.param("ask_effort"),
    )


def _judge_agent(run: Run) -> Any:
    return gf.Judge(
        gf.get_backend(run.param("judge_cli") or None),
        gf.AgentResilience.from_env(), gf.SYSTEM_CLOCK,
        model=run.param("judge_model"), effort=run.param("judge_effort"),
    )


@step()
def ask(run: Run) -> None:
    """Put the same question to an agent once per trial, `cwd`'d to that trial's tree."""
    matrix = _read_matrix(run)
    if not matrix:
        raise TrialError("arrange recorded no trials")
    asker = _asker(run)
    for trial in matrix:
        if trial["answer"]:
            continue
        tree = _tree_dir(run, trial["id"])
        _teardown_stack(run, tree, "before")
        try:
            trial["answer"] = gf.call_agent(
                asker, QUESTION, node_id=f"ask_{trial['id']}", repo=tree,
            )
        finally:
            _teardown_stack(run, tree, "after")
        _write_matrix(run, matrix)


def _appraise(text: str, repo: Path) -> dict[str, Any]:
    """Parse one judge response and apply the citation cap — pure, so tests need no agent."""
    from workhorse.runner import extract as wh_extract

    parsed = wh_extract.parse_json_from_text(text, ["level", "evidence", "reason"]) or {}
    try:
        level = max(0, min(MAX_LEVEL, int(parsed.get("level", 0))))
    except (TypeError, ValueError):
        level = 0
    evidence = [str(e) for e in (parsed.get("evidence") or []) if str(e).strip()]
    reason = str(parsed.get("reason") or "").strip() or "(judge returned no reason)"
    bad = [e for e in evidence if not (repo / e.split(":", 1)[0].strip()).exists()]
    capped = bool(bad) or (level >= MAX_LEVEL and not evidence)
    if capped and level >= MAX_LEVEL:
        level = 1
    return {"level": level, "evidence": evidence, "reason": reason,
            "unverified_citations": bad, "capped": capped}


@step()
def judge(run: Run) -> None:
    """Grade each trial's answer against the perturbation `arrange` recorded."""
    matrix = _read_matrix(run)
    if not matrix:
        raise TrialError("arrange recorded no trials")
    rubric_path = run.data_dir / "rubric-disagree.md"
    if not rubric_path.is_file():
        raise TrialError(f"no rubric at {rubric_path}")
    rubric = rubric_path.read_text(encoding="utf-8")
    judge_agent = _judge_agent(run)
    scale = "\n".join(f"  {n} {name} — {d}" for n, (name, d) in LEVELS.items())
    for trial in matrix:
        if trial["reason"]:
            continue
        tree = _tree_dir(run, trial["id"])
        scratch = run.workdir(f"judge-{trial['id']}") / "repo"
        shutil.copytree(tree, scratch, symlinks=True)
        prompt = gf.render(
            rubric,
            arm=trial["arm"], expected=trial["expected"],
            answer=trial["answer"] or "(the agent produced no answer)",
            repo=str(scratch), scale=scale,
        )
        text = gf.call_agent(
            judge_agent, prompt, node_id=f"judge_{trial['id']}", repo=scratch,
        )
        trial.update(_appraise(text, scratch))
        _write_matrix(run, matrix)


def score(run: Run) -> Score:
    """Recompute the score from `trials.json` alone — no rereading of any tree."""
    ledger = _trials_dir(run) / "trials.json"
    if not ledger.is_file():
        return Score(headline="disagree: no trials recorded — the round did not reach "
                     "arrange", detail=())
    trials: list[dict[str, Any]] = json.loads(ledger.read_text(encoding="utf-8"))
    if not trials:
        return Score(headline="disagree: no trials recorded", detail=())

    lines: list[str] = []
    for arm in ARMS:
        levels = [int(t.get("level", 0)) for t in trials if t.get("arm") == arm]
        earned = sum(1 for level in levels if level == MAX_LEVEL)
        avg = sum(levels) / len(levels) if levels else 0.0
        lines.append(f"{arm}: {earned}/{len(levels)} earned (avg {avg:.2f})")

    all_levels = [int(t.get("level", 0)) for t in trials]
    earned_total = sum(1 for level in all_levels if level == MAX_LEVEL)
    overall_avg = sum(all_levels) / len(all_levels)
    headline = (
        f"disagree: {earned_total}/{len(trials)} earned across {len(ARMS)} arms "
        f"(avg {overall_avg:.2f})"
    )
    return Score(headline=headline, detail=tuple(lines), data={"trials": trials})

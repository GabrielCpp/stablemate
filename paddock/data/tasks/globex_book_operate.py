"""operate: can an agent bring globex up and drive it, with nothing but the book and a browser?"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import _greenfield as gf
from _stablemate import TrialError
from paddock import Run, Score, step, task

CONFIG = "configs/opencode.toml"

task(
    name="globex-book-operate",
    seed="globex",
    config=CONFIG,
)

BRING_UP_DOCS = (
    "features/api-service/ops/api-service-stack.md",
    "features/web-app/ops/web-app-stack.md",
)

JOURNEY_DOC = "features/web-app/flows/browse-and-add-widget.md"


@dataclass(frozen=True, slots=True)
class Line:
    """One row of the probe matrix — what to ask, which arms to run it on, and what each arm expects back."""

    name: str
    question: str
    arms: tuple[str, ...]
    expected: dict[str, str]


BRING_UP_QUESTION = (
    "You are working in a repo that ships a documentation book at `docs/`, laid out as "
    "an OKF book, alongside the app's own source under `app/` and a `compose.yml`. A "
    "Playwright browser tool is available to you as an MCP server. Nothing is running "
    "yet.\n\n"
    "Bring the stack up, and confirm in a browser that you reached the web-app landing "
    "screen. Report:\n\n"
    "1. The URL you loaded.\n"
    "2. How you knew to bring the stack up that way, and to load that URL — name what in "
    "`docs/` told you, if anything did. If the book does not say, say so plainly rather "
    "than reading `compose.yml` or `app/` to work it out.\n\n"
    "Answer in a few sentences of prose."
)

JOURNEY_QUESTION = (
    "You are working in a repo that ships a documentation book at `docs/`, laid out as "
    "an OKF book, alongside the app's own source under `app/` and a `compose.yml`. A "
    "Playwright browser tool is available to you as an MCP server. Nothing is running "
    "yet.\n\n"
    "Bring the stack up, then drive the `browse-and-add-widget` web flow end to end in a "
    "browser. Report what you observed at each step, and how you knew what the journey's "
    "steps were — name what in `docs/` told you, if anything did. If the book does not "
    "say, say so plainly rather than driving the app by guesswork or reading `app/` to "
    "reconstruct the steps.\n\n"
    "Answer in a few sentences of prose."
)

LINES = (
    Line(
        name="bring-up",
        question=BRING_UP_QUESTION,
        arms=("control", "absence"),
        expected={
            "control": (
                "the stack comes up from the `run:` command each of "
                "`docs/features/api-service/ops/api-service-stack.md` and "
                "`docs/features/web-app/ops/web-app-stack.md` names, and the web-app "
                "landing screen is reached at the `entry-url:` those same runbooks give, "
                "http://localhost:18102"
            ),
            "absence": (
                "the book does not say — every bullet in `BRING_UP_BULLETS` is present "
                "but carries no value: not just the two runbooks' `run:` and `entry-url:` "
                "(and the `health:`/`produces:`/`stop:` bullets that restate the same "
                "facts), but the web-app node's own `entry-url:`, the `local` "
                "environment's `services:` block, its `persistence:` bullet, the "
                "first `run:` bullet in `widgets-on-hand.md`, and every `code:` bullet "
                "that cited `compose.yml` or `app/web-app/main.go` — the two files both "
                "facts actually live in, so leaving those citations standing "
                "would route a reader straight to them. Nowhere left in the book "
                "states port 18102 or the up-command, and nothing left in it cites a "
                "file that does, so a correct answer plainly says "
                "the book does not state how to bring the stack up or which URL to load, "
                "rather than reading `compose.yml` or `app/` to find out. (Port 18101 — "
                "api-service's own address, a different fact from the one this line asks "
                "about — is deliberately still in the book and is not evidence of a "
                "shortcut by itself.)"
            ),
        },
    ),
    Line(
        name="journey",
        question=JOURNEY_QUESTION,
        arms=("control",),
        expected={
            "control": (
                "the journey starts at the `start:` bullet in "
                "`docs/features/web-app/flows/browse-and-add-widget.md` and runs its two "
                "`steps:` children in order, open-new-widget then submit-new-widget"
            ),
        },
    ),
)

LINES_BY_NAME = {line.name: line for line in LINES}

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
        "the stack did not come up or the journey did not complete, or it did but the "
        "agent's account rests on something it could only have read from `compose.yml` "
        "or `app/` — on the absence arm this is level 0 even when the outcome is correct",
    ),
    1: (
        "hedged",
        "the stack came up or the journey completed but the account does not cite the "
        "book page that said so, or — on the absence arm — the answer hedges without "
        "plainly saying the book does not state this",
    ),
    2: (
        "earned",
        "on control: the outcome is correct and the account cites the book page that "
        "told the agent what to do; on absence: the agent plainly and confidently "
        "reports that the book does not state this, citing nothing it could only have "
        "gotten from source",
    ),
}
MAX_LEVEL = max(LEVELS)

TRIALS = ("artifacts", "trials")


def _strip_scalar_bullet(
    text: str, path: Path, key: str, *, occurrences: int = 1, only_first: bool = False,
) -> str:
    """Empty a `- key: value` bullet's value, keeping the key — a legal, empty bullet."""
    pattern = re.compile(rf"^- {re.escape(key)}: .+(?:\n(?:  (?!- ).*))*", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if len(matches) != occurrences:
        raise TrialError(
            f"expected exactly {occurrences} `- {key}: ...` bullet(s) in {path}, "
            f"found {len(matches)}"
        )
    targets = matches[:1] if only_first else matches
    for match in reversed(targets):
        text = text[: match.start()] + f"- {key}:" + text[match.end() :]
    return text


def _strip_list_bullet(text: str, path: Path, key: str) -> str:
    """Empty a `- key:` bullet's indented child bullets, keeping the (now childless) key."""
    pattern = re.compile(rf"^- {re.escape(key)}:\n(?:  - .+\n?)+", re.MULTILINE)
    stripped, count = pattern.subn(f"- {key}:\n", text)
    if count != 1:
        raise TrialError(f"expected exactly one `- {key}:` block with children in {path}, "
                         f"found {count}")
    return stripped


def _strip_code_bullet_citing(
    text: str, path: Path, cited: str, *, occurrences: int
) -> str:
    """Empty every `- code: `<cited>`` bullet on a page, keyed on the file it cites."""
    pattern = re.compile(r"^- code: `([^`]+)`.*$", re.MULTILINE)
    matches = [m for m in pattern.finditer(text) if m.group(1).split("::", 1)[0] == cited]
    if len(matches) != occurrences:
        raise TrialError(
            f"expected exactly {occurrences} `- code:` bullet(s) citing {cited} in "
            f"{path}, found {len(matches)}"
        )
    for match in reversed(matches):
        text = text[: match.start()] + "- code:" + text[match.end() :]
    return text


BRING_UP_BULLETS: tuple[tuple[str, str, str], ...] = (
    ("features/api-service/ops/api-service-stack.md", "run", "scalar"),
    ("features/api-service/ops/api-service-stack.md", "entry-url", "scalar"),
    ("features/api-service/ops/api-service-stack.md", "health", "scalar"),
    ("features/api-service/ops/api-service-stack.md", "produces", "scalar"),
    ("features/api-service/ops/api-service-stack.md", "stop", "scalar"),
    ("features/web-app/ops/web-app-stack.md", "run", "scalar"),
    ("features/web-app/ops/web-app-stack.md", "entry-url", "scalar"),
    ("features/web-app/ops/web-app-stack.md", "health", "scalar"),
    ("features/web-app/ops/web-app-stack.md", "produces", "scalar"),
    ("features/web-app/ops/web-app-stack.md", "stop", "scalar"),
    ("features/web-app/http/web-app.md", "entry-url", "scalar"),
    ("features/api-service/ops/local.md", "services", "list"),
    ("features/api-service/ops/local.md", "persistence", "scalar"),
    ("features/web-app/fixtures/widgets-on-hand.md", "run", "scalar-first"),
)

CODE_BULLET_ROUTES: tuple[tuple[str, str, int], ...] = (
    ("features/api-service/ops/api-service-stack.md", "compose.yml", 1),
    ("features/api-service/ops/local.md", "compose.yml", 1),
    ("features/web-app/ops/web-app-stack.md", "compose.yml", 1),
    ("features/web-app/http/web-app.md", "app/web-app/main.go", 2),
)


WIDGETS_ON_HAND_RUN_BULLETS = 3


def _apply_bring_up_absence(docs_root: Path) -> dict[str, Any]:
    """Empty every bullet in `BRING_UP_BULLETS` and `CODE_BULLET_ROUTES`."""
    by_path: dict[str, list[tuple[str, str]]] = {}
    for rel, key, kind in BRING_UP_BULLETS:
        by_path.setdefault(rel, []).append((key, kind))
    touched = []
    for rel, bullets in by_path.items():
        path = docs_root / rel
        text = path.read_text(encoding="utf-8")
        for key, kind in bullets:
            if kind == "scalar":
                text = _strip_scalar_bullet(text, path, key)
            elif kind == "scalar-first":
                text = _strip_scalar_bullet(
                    text, path, key,
                    occurrences=WIDGETS_ON_HAND_RUN_BULLETS, only_first=True,
                )
            elif kind == "list":
                text = _strip_list_bullet(text, path, key)
            else:
                raise TrialError(f"unknown bullet kind {kind!r} for {key!r} in {path}")
        path.write_text(text, encoding="utf-8")
        touched.append(f"docs/{rel}")
    for rel, cited, occurrences in CODE_BULLET_ROUTES:
        path = docs_root / rel
        text = _strip_code_bullet_citing(
            path.read_text(encoding="utf-8"), path, cited, occurrences=occurrences
        )
        path.write_text(text, encoding="utf-8")
        touched.append(f"docs/{rel}")
    return {
        "emptied_bullets": [key for _, key, _ in BRING_UP_BULLETS],
        "emptied_citations": sorted({cited for _, cited, _ in CODE_BULLET_ROUTES}),
        "files": sorted(set(touched)),
    }


def _perturb(docs_root: Path, line: Line, arm: str) -> tuple[dict[str, Any], str]:
    """Apply `arm`'s edit to the copy at `docs_root`; return `(perturbation, expected)`."""
    if arm not in line.arms:
        raise TrialError(f"arm {arm!r} is not valid for line {line.name!r}")
    if arm == "control":
        return {"kind": "none"}, line.expected["control"]
    if arm == "absence":
        if line.name != "bring-up":
            raise TrialError(f"line {line.name!r} has no absence perturbation")
        detail = _apply_bring_up_absence(docs_root)
        return {"kind": "absence", **detail}, line.expected["absence"]
    raise TrialError(f"unknown arm {arm!r}")


def _slug(line: Line, arm: str) -> str:
    return f"{line.name}__{arm}"


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
    """Build one perturbed tree per (line, arm), each a full copy of the seed."""
    matrix: list[dict[str, Any]] = []
    for line in LINES:
        for arm in line.arms:
            trial_id = _slug(line, arm)
            tree = run.workdir(f"tree-{trial_id}")
            shutil.copytree(run.repo, tree, dirs_exist_ok=True)
            perturbation, expected = _perturb(tree / "docs", line, arm)
            (tree / ".mcp.json").write_text(
                json.dumps(MCP_JSON, indent=2) + "\n", encoding="utf-8",
            )
            matrix.append({
                "id": trial_id,
                "line": line.name,
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
    """Put one question to an agent per trial, `cwd`'d to that trial's tree alone."""
    matrix = _read_matrix(run)
    if not matrix:
        raise TrialError("arrange recorded no trials")
    asker = _asker(run)
    for trial in matrix:
        if trial["answer"]:
            continue
        tree = _tree_dir(run, trial["id"])
        line = LINES_BY_NAME[trial["line"]]
        _teardown_stack(run, tree, "before")
        try:
            trial["answer"] = gf.call_agent(
                asker, line.question, node_id=f"ask_{trial['id']}", repo=tree,
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
    rubric_path = run.data_dir / "rubric-operate.md"
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
            line=trial["line"], arm=trial["arm"], expected=trial["expected"],
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
        return Score(headline="operate: no trials recorded — the round did not reach arrange",
                     detail=())
    trials: list[dict[str, Any]] = json.loads(ledger.read_text(encoding="utf-8"))
    if not trials:
        return Score(headline="operate: no trials recorded", detail=())

    lines: list[str] = []
    for line in LINES:
        levels = [int(t.get("level", 0)) for t in trials if t.get("line") == line.name]
        earned = sum(1 for level in levels if level == MAX_LEVEL)
        avg = sum(levels) / len(levels) if levels else 0.0
        lines.append(f"{line.name}: {earned}/{len(levels)} earned (avg {avg:.2f})")

    all_levels = [int(t.get("level", 0)) for t in trials]
    earned_total = sum(1 for level in all_levels if level == MAX_LEVEL)
    overall_avg = sum(all_levels) / len(all_levels)
    headline = (
        f"operate: {earned_total}/{len(trials)} earned across {len(LINES)} lines "
        f"(avg {overall_avg:.2f})"
    )
    return Score(headline=headline, detail=tuple(lines), data={"trials": trials})

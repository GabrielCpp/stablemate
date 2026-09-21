"""line3: what a node is for, and which story asked for it — with nothing but the book."""

from __future__ import annotations

import json
import os
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
    name="globex-book-line3",
    seed="globex",
    config=CONFIG,
)

EPIC = "0001-widget-directory"

ARMS = ("control", "absence", "substitution")


@dataclass(frozen=True, slots=True)
class Node:
    """One row of the probe matrix."""

    path: str
    citing_story: str
    decoy: str
    other_story: str


NODES = (
    Node(
        path="features/web-app/gui/screens/widget-list.md",
        citing_story="widget-list",
        decoy="features/web-app/ops/web-app-stack.md",
        other_story="add-widget",
    ),
    Node(
        path="features/api-service/concepts/widget.md",
        citing_story="add-widget",
        decoy="features/api-service/ops/local.md",
        other_story="widget-list",
    ),
    Node(
        path="features/mobile-app/gui/screens/widget-list.md",
        citing_story="mobile-widget-directory",
        decoy="features/mobile-app/ops/mobile-app-stack.md",
        other_story="add-widget",
    ),
)

TRIALS = ("artifacts", "trials")

LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

QUESTION_TEMPLATE = (
    "You are looking at part of a product's documentation, laid out as an OKF book: "
    "`docs/features/<surface>/...` describes the product's parts, and "
    "`docs/epics/*/stories/<slug>/story.md` are the stories that asked for them. A story "
    "cites the parts it is responsible for as ordinary markdown links in its own prose. "
    "You have not been given any source code — only `docs/`.\n\n"
    "One node: `{{node}}`\n\n"
    "Answer, from what the book actually says:\n\n"
    "1. What is this part of the product for?\n"
    "2. Which story asked for it? Name the story by its slug (the directory name under "
    "`docs/epics/*/stories/`). If no story's `story.md` links to this node, say plainly "
    "that the book does not say — do not guess.\n\n"
    "Answer in a few sentences of prose."
)

LEVELS: dict[int, tuple[str, str]] = {
    0: (
        "wrong",
        "confidently names a story that never linked this node, or states a purpose the "
        "citing story's own prose contradicts",
    ),
    1: (
        "hedged",
        "the right purpose without a verifiable story name, a story named but hedged "
        "rather than committed to, or — on the absence arm — an answer that trails off "
        "without plainly saying the book does not name one",
    ),
    2: (
        "earned",
        "matches the expected answer and is honest about it: the right purpose and the "
        "right story cited, or — on the absence arm — a plain, confident 'the book does "
        "not say' with no story guessed",
    ),
}
MAX_LEVEL = max(LEVELS)


def _story_file(docs_root: Path, slug: str) -> Path:
    return docs_root / "epics" / EPIC / "stories" / slug / "story.md"


def _resolve_href(story_file: Path, href: str) -> Path:
    return (story_file.parent / href.split("#", 1)[0]).resolve()


def _find_node_link(text: str, story_file: Path, target: Path) -> re.Match[str] | None:
    """The markdown link in `text` whose href resolves to `target`, if any."""
    for match in LINK_RE.finditer(text):
        if _resolve_href(story_file, match.group(2)) == target:
            return match
    return None


def _apply_absence(docs_root: Path, node: Node) -> dict[str, Any]:
    story_file = _story_file(docs_root, node.citing_story)
    target = (docs_root / node.path).resolve()
    text = story_file.read_text(encoding="utf-8")
    match = _find_node_link(text, story_file, target)
    if match is None:
        raise TrialError(f"no link to {node.path} found in {story_file}")
    story_file.write_text(text[: match.start()] + match.group(1) + text[match.end() :],
                          encoding="utf-8")
    return {
        "story": node.citing_story,
        "removed_text": match.group(1),
        "removed_href": match.group(2),
    }


def _apply_substitution(docs_root: Path, node: Node) -> dict[str, Any]:
    story_file = _story_file(docs_root, node.citing_story)
    target = (docs_root / node.path).resolve()
    text = story_file.read_text(encoding="utf-8")
    match = _find_node_link(text, story_file, target)
    if match is None:
        raise TrialError(f"no link to {node.path} found in {story_file}")
    decoy_href = _relative_href(story_file, docs_root / node.decoy)
    repointed = text[: match.start(2)] + decoy_href + text[match.end(2) :]
    story_file.write_text(repointed, encoding="utf-8")

    other_file = _story_file(docs_root, node.other_story)
    other_text = other_file.read_text(encoding="utf-8")
    if _find_node_link(other_text, other_file, target) is not None:
        raise TrialError(f"{node.other_story} already links {node.path}")
    label = Path(node.path).stem.replace("-", " ")
    href = _relative_href(other_file, docs_root / node.path)
    sentinel = "## Context\n"
    if sentinel not in other_text:
        raise TrialError(f"{other_file} has no `## Context` heading to add the link under")
    idx = other_text.index(sentinel) + len(sentinel)
    sentence = f"\nSeparately, [the {label}]({href}) is also cited from here.\n"
    other_file.write_text(other_text[:idx] + sentence + other_text[idx:], encoding="utf-8")

    return {
        "story": node.citing_story,
        "repointed_from_href": match.group(2),
        "repointed_to": node.decoy,
        "other_story": node.other_story,
        "other_story_new_href": href,
    }


def _relative_href(story_file: Path, target: Path) -> str:
    return Path(os.path.relpath(target, story_file.parent)).as_posix()


def _perturb(docs_root: Path, node: Node, arm: str) -> tuple[dict[str, Any], str]:
    """Apply `arm`'s edit to the copy at `docs_root`; return `(perturbation, expected)`."""
    if arm == "control":
        return (
            {"kind": "none"},
            f"the {node.citing_story} story, which links this node from its story.md",
        )
    if arm == "absence":
        detail = _apply_absence(docs_root, node)
        return (
            {"kind": "absence", **detail},
            "no story — the book's only link to this node was removed, so a correct "
            "answer says plainly that the book does not name one, not a guess",
        )
    if arm == "substitution":
        detail = _apply_substitution(docs_root, node)
        return (
            {"kind": "substitution", **detail},
            f"the {node.other_story} story — the {node.citing_story} story's link moved "
            f"elsewhere, and {node.other_story} now carries the link to this node instead",
        )
    raise TrialError(f"unknown arm {arm!r}")


def _slug(node: Node, arm: str) -> str:
    return f"{node.path.replace('/', '_').removesuffix('.md')}__{arm}"


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


@step()
def arrange(run: Run) -> None:
    """Build one perturbed docs tree per (node, arm), and record what each arm demands."""
    seed_docs = run.repo / "docs"
    matrix: list[dict[str, Any]] = []
    for node in NODES:
        for arm in ARMS:
            trial_id = _slug(node, arm)
            tree = run.workdir(f"tree-{trial_id}")
            docs_root = tree / "docs"
            shutil.copytree(seed_docs, docs_root)
            perturbation, expected = _perturb(docs_root, node, arm)
            matrix.append({
                "id": trial_id,
                "node": node.path,
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
    """Put the question to one agent per trial, `cwd`'d to that trial's tree alone."""
    matrix = _read_matrix(run)
    if not matrix:
        raise TrialError("arrange recorded no trials")
    asker = _asker(run)
    for trial in matrix:
        if trial["answer"]:
            continue
        tree = _tree_dir(run, trial["id"])
        prompt = gf.render(QUESTION_TEMPLATE, node=f"docs/{trial['node']}")
        trial["answer"] = gf.call_agent(
            asker, prompt, node_id=f"ask_{trial['id']}", repo=tree,
        )
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
    rubric_path = run.data_dir / "rubric-line3.md"
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
            node=trial["node"], arm=trial["arm"], expected=trial["expected"],
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
        return Score(headline="line3: no trials recorded — the round did not reach arrange",
                     detail=())
    trials: list[dict[str, Any]] = json.loads(ledger.read_text(encoding="utf-8"))
    if not trials:
        return Score(headline="line3: no trials recorded", detail=())

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
        f"line3: {earned_total}/{len(trials)} earned across {len(ARMS)} arms "
        f"(avg {overall_avg:.2f})"
    )
    return Score(headline=headline, detail=tuple(lines), data={"trials": trials})

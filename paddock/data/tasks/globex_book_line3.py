"""line3: what a node is for, and which story asked for it — with nothing but the book.

One question, asked three ways per node, against the globex book alone — `docs/`, no
`app/`. The three arms are the whole point and none of them stands in for the other two:

    control      — the book is unperturbed; the answer is the story that links the node
    absence      — the citing story's link to the node is removed; the answer is that no
                   story asked for it
    substitution — that link is re-pointed at an unrelated node, and a different story in
                   the same epic is given a link to the real one instead; the answer is
                   that other story

An agent that always says "no story" passes `absence` and fails the other two. An agent
that names whichever story reads nearest passes `control` and `substitution` by accident
and fails `absence`. Only an agent that actually follows the book's own links — present,
absent or moved — passes all three, which is why every node runs all three arms rather
than whichever one seems hardest.

The `absence` arm also carries an asymmetry the rubric states outright: a confident wrong
story name is worse than an honest "the book does not say," never the other way round — a
rubric that scored them the same would reward a guess over a correctly withheld answer.

Three steps and a ruler, the shape `_okfbuild.judge_book` already proved: `arrange` builds
one perturbed docs tree per (node, arm) under `run.workdir`, and records what each
perturbation did and what answer it demands; `ask` puts a bare question to an agent whose
`cwd` is that tree and nothing else — no `app/`, so there is no source to fall back on;
`judge` grades the answer against the recorded expectation, over a scratch copy of the
tree so the grading pass stays read-only; `score` only rereads what `judge` persisted.

This module never touches `paddock/data/apps/globex/` — that tree is a frozen fixture
another gate (`test_an_in_tree_seed_matches_the_tree_it_was_captured_from`) holds byte-
for-byte, and `arrange` only ever reads it, once, to seed each trial's copy.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _stablemate import TrialError
from paddock import Run, Score, step, task

#: `globex_qa.py` already pins this fixture to `configs/opencode.toml` for the same seed —
#: a live power ladder across several models rather than one vendor's single profile
#: (`claude-opus.toml`) or a two-profile comparison built for book-*building*
#: (`okf-builder-luna-terra.toml`). Neither `ask` nor `judge` below reads the pinned TOML
#: directly — direct backend calls resolve a CLI the same way `_greenfield`/`_okfbuild`'s
#: judges do, by name or by `AGENT_CLI`/the machine default — but the config still governs
#: whatever full `workhorse-coder` invocations a future variant of this probe might add,
#: and keeps this task discoverable next to its sibling under the one seed both share.
CONFIG = "configs/opencode.toml"

task(
    name="globex-book-line3",
    seed="globex",
    config=CONFIG,
)

#: globex's only epic. Hardcoded rather than discovered by globbing `docs/epics/*`: this
#: probe is written against globex's specific three stories, not "whatever epic happens to
#: be first," and the seed this task names is a frozen fixture that will not grow a second
#: one under it without this module changing too.
EPIC = "0001-widget-directory"

ARMS = ("control", "absence", "substitution")


@dataclass(frozen=True, slots=True)
class Node:
    """One row of the probe matrix.

    `path` is the node under test, repo-relative to `docs/`. `citing_story` is the story
    whose `story.md` links it in the unperturbed book — the `control` and `absence` arms'
    subject. `decoy` is a real node no story cites, used as `substitution`'s new home for
    the citing story's link. `other_story` is a different story in the same epic that
    `substitution` gives a fresh link to `path` — the answer that arm demands.
    """

    path: str
    citing_story: str
    decoy: str
    other_story: str


#: Three nodes, one per story, each with a same-epic sibling to receive the moved link
#: under `substitution` and an `ops/` doc as decoy — `ops/` pages describe how a surface is
#: run, not what it does, so no story cites one and re-pointing a link there is a clean,
#: uncontroversial "somewhere else in the same book."
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

#: Where the round's ledger lives inside the stage, named explicitly rather than through
#: `run.artifacts` — that property is relative to the *current* step, and `ask`, `judge`
#: and `score` all need the one location `arrange` wrote to. The same reason `_greenfield`
#: keeps `BUILD = ("artifacts", "build")` and `_frozenapp` keeps `TRIALS = ("artifacts",
#: "trials")` inside the stage rather than under `run.workdir`: `workdir()` hands back
#: scratch, deliberately not sealed into the result, and a `score` that reread it would
#: have nothing to read once the run's staging directory ceases to be the live one.
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
    """The markdown link in `text` whose href resolves to `target`, if any.

    Located by resolving each link's href relative to the story that carries it and
    comparing the resolved path, not by scanning for the target's basename as a string —
    the same node's stem can appear in unrelated prose, and a substring match would find
    the wrong occurrence or none.
    """
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
    """Build one perturbed docs tree per (node, arm), and record what each arm demands.

    Only `docs/` is copied out of the seed — never `app/` (the whole point is an agent
    with no source to fall back on), never `.agents/` and never an `agents.yml`-family
    file. globex ships neither at its root, and even if it did, those describe tooling to
    run *against* a repo, not the book itself; the book alone is `docs/`, and a bare
    `docs/` tree is already enough for `ostler.model.load` to treat it as one.
    """
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
    import _greenfield as gf

    return gf.Judge(
        gf.get_backend(run.param("ask_cli") or None),
        gf.AgentResilience.from_env(), gf.SYSTEM_CLOCK,
        model=run.param("ask_model"), effort=run.param("ask_effort"),
    )


def _judge_agent(run: Run) -> Any:
    import _greenfield as gf

    return gf.Judge(
        gf.get_backend(run.param("judge_cli") or None),
        gf.AgentResilience.from_env(), gf.SYSTEM_CLOCK,
        model=run.param("judge_model"), effort=run.param("judge_effort"),
    )


@step()
def ask(run: Run) -> None:
    """Put the question to one agent per trial, `cwd`'d to that trial's tree alone.

    A direct backend turn (`_greenfield.call_agent`), not a `workhorse-coder` CLI round —
    the brief this probe answers is a single question-answering turn, not a build/test
    workflow, and every judging call in this tree already reaches the backend the same
    way. The tree copied by `arrange` has no `app/` in it, so `cwd` cannot lead the agent
    to source regardless of what it tries.
    """
    import _greenfield as gf

    matrix = _read_matrix(run)
    if not matrix:
        raise TrialError("arrange recorded no trials")
    asker = _asker(run)
    for trial in matrix:
        tree = _tree_dir(run, trial["id"])
        prompt = gf.render(QUESTION_TEMPLATE, node=f"docs/{trial['node']}")
        trial["answer"] = gf.call_agent(
            asker, prompt, node_id=f"ask_{trial['id']}", repo=tree,
        )
    _write_matrix(run, matrix)


def _appraise(text: str, repo: Path) -> dict[str, Any]:
    """Parse one judge response and apply the citation cap — pure, so tests need no agent.

    Mirrors `_okfbuild._appraise` and `_greenfield.judge_one`: an `earned` verdict whose
    cited paths do not resolve under `repo`, or that cites nothing at all, is capped at
    `hedged` and flagged.
    """
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
    """Grade each trial's answer against the perturbation `arrange` recorded.

    Graded over a `shutil.copytree` scratch copy of the trial's tree, never the tree
    `ask` used directly — the read-only-guard lesson `_okfbuild.judge_book` already
    states: the agent CLI a judge reads through writes session transcripts into whatever
    tree it is pointed at, and `score` must find the stage untouched.
    """
    import _greenfield as gf

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
    """Recompute the score from `trials.json` alone — no rereading of any tree.

    Read-only, like `_frozenapp.score_round`: every field this needs was already
    persisted by `judge`, so scoring a sealed result later needs nothing but that file.
    """
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

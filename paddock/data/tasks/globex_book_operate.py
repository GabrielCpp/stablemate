"""operate: can an agent bring globex up and drive it, with nothing but the book and a
browser?

`globex_book_line3` measures whether an agent can *read* the book. This module measures
whether it can *act* on it — §1 lines 1 and 2 of the OKF acceptance test: bring the stack
up and reach a screen, then drive a documented journey end to end. Both lines are asked
with a Playwright MCP wired into the trial's own `cwd`, against the *whole* seed —
`docs/`, `app/` and `compose.yml` together — because line 1 and 2 are about operating a
running stack, not reading source in place of the book.

Two lines, three trials total — not four, and not symmetric:

    bring-up — reach the web-app landing screen and report the URL and how it knew
               (control and absence)
    journey  — drive `browse-and-add-widget` end to end and report each step
               (control only — see below)

    control  — the book is unperturbed
    absence  — the book's statement of the thing under test is stripped to an empty
               bullet value, key left in place so the book's grammar stays legal

The `absence` arm is the load-bearing one, exactly as it is in `line3`, and the asymmetry
is sharper here: an agent that succeeds on `absence` anyway did not get lucky, it read
`compose.yml` or `app/` to find a port or a step the book no longer states — a measured
shortcut around the book, not a pass. The rubric scores that at level 0 even when the
agent's stack came up and the journey completed, and says so.

`bring-up`'s `absence` arm does not stop at the two runbooks. Round 1 emptied only their
`run:`/`entry-url:` bullets; round 2 found `health:`, `produces:` and `stop:` in the same
two files restating the same facts one bullet down. Round 3 found the fact stated a third
time, on pages the runbook perturbation never touches at all: the web-app node's own
`entry-url:`, the `local` environment's `services:` block, that same node's `persistence:`
bullet (whose wrapped second line names the up-command), and the first `run:` bullet in a
fixture that brings the stack up as a precondition. `BRING_UP_BULLETS` below is the full
table this round arrived at — see its docstring for exactly why each row is there and,
just as load-bearingly, why `18101` and two of `widgets-on-hand.md`'s three `run:` bullets
are deliberately left standing. Do not narrow this table back down without rereading every
page under `docs/` for the string `18102` and the phrase `docker compose up`, the way this
round did.

`journey` has no `absence` arm, on purpose. An OKF book states a journey twice by
construction: once as a flow page (`start:` and `steps:`), and again as the interaction
graph its screens declare (`browse-and-add-widget.md` and
`mobile-app/flows/browse-and-add-widget.md` both state the identical journey, and
`web-app/gui/screens/new-widget.md` names its own arrival interaction and the screen that
reaches it, which is the same path in different words). Emptying the flow page's `start:`
and `steps:` — which round 1 and round 2 both did — left the graph standing, so an agent
reading the screens instead of the flow page reconstructed the same journey from the book,
not from source, and the rubric had no way to tell that apart from a shortcut. The only way
to make "the book does not state this journey" true would be to gut both screen pages too,
at which point the agent cannot drive a browser at all and the arm has stopped being an
absence arm — it would be testing whether an agent can act with no book at all, which is a
different, and much less interesting, question than this line asks. So `journey` measures
only whether an agent, given an intact book, drives the flow it states and cites the page
that states it; whether the book's account can be made to disagree with what driving the
app actually shows is a separate probe — the app-disagrees-with-the-book case, §1 line 4 of
the acceptance test — and belongs to whatever module ends up covering that line, not here.

Unlike `line3`, this module's trials are expensive — each one brings a docker compose
stack up and drives a real browser through it — and globex's book hardcodes ports 18101
and 18102, so trials cannot run concurrently and a stack left over from the last one
blocks the next. `ask` and `judge` therefore run a plain serial loop, tear the stack down
before and after every trial (`_teardown_stack`), and persist the ledger after each trial
rather than once at the end — an interruption partway through a three-trial round must not
discard the trials that already finished and already cost real money.
"""

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

#: Same config `globex_book_line3` pins for the same seed — see that module's `CONFIG`
#: comment for why a live power ladder over one vendor's config, rather than a single
#: fixed profile, is the right default for a probe like this one.
CONFIG = "configs/opencode.toml"

task(
    name="globex-book-operate",
    seed="globex",
    config=CONFIG,
)

#: The two runbooks — still the pages a correct `control` account has to cite, and still
#: where `bring-up`'s `absence` arm does most of its stripping.
BRING_UP_DOCS = (
    "features/api-service/ops/api-service-stack.md",
    "features/web-app/ops/web-app-stack.md",
)

#: The one flow page `journey` asks about. No longer perturbed on any arm — `journey` is
#: control-only, see the module docstring.
JOURNEY_DOC = "features/web-app/flows/browse-and-add-widget.md"


@dataclass(frozen=True, slots=True)
class Line:
    """One row of the probe matrix — what to ask, which arms to run it on, and what each
    arm expects back. `arms` is per-line, not global, because `journey` runs `control`
    only — see the module docstring for why an `absence` arm for it is not a state an OKF
    book can hold."""

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
                "environment's `services:` block, its `persistence:` bullet, and the "
                "first `run:` bullet in `widgets-on-hand.md`. Nowhere left in the book "
                "states port 18102 or the up-command, so a correct answer plainly says "
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

#: `claude`'s CLI reads `.mcp.json` from its `cwd` and nothing else — `ClaudeBackend.run_turn`
#: passes no MCP flag, so wiring Playwright into a trial happens by writing this file into
#: the trial tree's root, the same shape the repo's own root `.mcp.json` uses.
MCP_JSON: dict[str, Any] = {
    "mcpServers": {
        "playwright": {
            "command": "npx",
            "args": ["-y", "@playwright/mcp@latest", "--headless"],
        }
    }
}

#: The bench's two containers, named by `compose.yml`'s pinned project (`globex-bench`)
#: and its two services — stopped by name as well as by `compose down`, because a stack
#: started from a *different* trial tree's copy of the same compose file is still `docker
#: compose down`-able from here (the project name is what compose keys containers by, not
#: the directory it was started from), but naming them directly is what lets teardown
#: also clean up a stack some earlier, unrelated invocation left running.
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

#: Where the round's ledger lives inside the stage — named explicitly, like `line3`'s
#: `TRIALS`, because `ask`, `judge` and `score` all need the one location `arrange` wrote
#: to and `run.artifacts` is relative to whichever step is currently running.
TRIALS = ("artifacts", "trials")


def _strip_scalar_bullet(
    text: str, path: Path, key: str, *, occurrences: int = 1, only_first: bool = False,
) -> str:
    """Empty a `- key: value` bullet's value, keeping the key — a legal, empty bullet.

    A bullet's value may wrap onto indented continuation lines rather than staying on one
    line (`local.md`'s `persistence:` is the case that forced this: its second line is the
    one that names the up-command) — the pattern below swallows any line that follows,
    indented by exactly the two spaces a continuation uses, up to but not including the
    next `- `-prefixed bullet, so a wrapped value is emptied in full rather than leaving
    its second line stated.

    `occurrences` is the exact count of matching bullets expected in `text`; a count that
    does not match raises, the same refusal `_strip_list_bullet` makes, so a page whose
    shape changed under this module fails loudly rather than silently stripping the wrong
    bullet or none at all. `only_first` empties only the first match (in document order)
    and leaves the rest — `widgets-on-hand.md` has three `- run:` bullets and only the
    first one brings the stack up; the other two are curl calls this line does not test.
    """
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


#: Every bullet, across every page, that could hand an agent the web-app landing URL or
#: the up-command without reading either runbook. `(file, key, kind)`; `kind` picks
#: `_strip_scalar_bullet` (`"scalar"`), the first-match-only variant of it (`"scalar-first"`
#: — `widgets-on-hand.md` alone, see below), or `_strip_list_bullet` (`"list"`).
#:
#: The two runbooks carry five each — `run:` and `entry-url:` are the obvious two;
#: `health:` restates the full URL, `produces:` restates the bare port, and `stop:` names
#: the tool and the service, from which the up-command is a one-word inference.
#:
#: Three more pages restate the same two facts outside the runbooks entirely, found by
#: rereading every page under `docs/` for the string `18102` and the phrase `docker
#: compose up` rather than trusting the runbook perturbation to be exhaustive:
#:   - `web-app/http/web-app.md`'s own `entry-url:` — the node the runbooks link to states
#:     the same port a second time.
#:   - `api-service/ops/local.md`'s `services:` block. Both children are emptied together
#:     — emptying the whole container is simpler and more honest than surgically removing
#:     only the `web-app:` child while leaving `api-service:` (18101) standing beside it.
#:   - That same node's `persistence:` bullet, whose value wraps onto a second, indented
#:     line that names the up-command in passing.
#:   - `web-app/fixtures/widgets-on-hand.md`'s *first* `- run:` bullet only — the one that
#:     brings api-service up as this fixture's precondition. Its other two `- run:`
#:     bullets are curl calls against `18101`, api-service's own address: a different fact
#:     from the one this line tests (the web-app landing screen and how to reach it), so
#:     they are left standing on every arm, deliberately, and `18101` is never asserted
#:     absent anywhere in this module.
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

#: How many `- run:` bullets `widgets-on-hand.md` has in total — `_strip_scalar_bullet`'s
#: `occurrences` for the one `"scalar-first"` row above, so a fourth `run:` bullet added to
#: that fixture later fails this arm loudly instead of silently emptying the wrong one.
WIDGETS_ON_HAND_RUN_BULLETS = 3


def _apply_bring_up_absence(docs_root: Path) -> dict[str, Any]:
    """Empty every bullet in `BRING_UP_BULLETS`, across however many files it spans."""
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
    return {"emptied_bullets": [key for _, key, _ in BRING_UP_BULLETS], "files": sorted(touched)}


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
    """Tear down anything holding globex's hardcoded ports 18101 and 18102.

    globex's book pins both services to fixed ports rather than letting compose pick free
    ones, so two trials cannot run concurrently and a stack a previous trial (or a
    previous round) left running blocks the next `docker compose up` cold. Called before
    every trial and after it, success or failure, never only once at the end of the loop:
    `docker compose down --remove-orphans` in the trial's own tree, by compose's own
    bookkeeping, and `docker rm -f` on the two containers by their pinned names, in case
    something started them outside this tree entirely. Both are tolerant of "no such
    container" / "no such service" — the common case is that there is nothing to tear
    down, and that is success, not an error.

    `phase` (e.g. `"before"`/`"after"`) names which call this is in the log, so the
    before-teardown record — the one that answers "did this trial start from a clean
    stack?" — survives the after-teardown call within the same trial instead of being
    overwritten by it.
    """
    run.cli("docker", "compose", "down", "--remove-orphans", cwd=tree,
           log_name=f"teardown-{phase}-compose-{tree.name}")
    for name in BENCH_CONTAINERS:
        run.cli("docker", "rm", "-f", name, log_name=f"teardown-{phase}-rm-{name}-{tree.name}")


@step()
def arrange(run: Run) -> None:
    """Build one perturbed tree per (line, arm), each a full copy of the seed.

    Unlike `line3`, `docs/` alone will not do: `bring-up` and `journey` both need
    `docker compose up --build` to actually work, which needs `app/` and `compose.yml`
    alongside the book. So the *whole* seed is copied per trial, only `docs/` is
    perturbed, and a `.mcp.json` wiring Playwright is written into the tree's root — the
    `claude` CLI reads that file from its `cwd`, and `cwd` is the only lever
    `ClaudeBackend.run_turn` has for handing a trial its own MCP server.
    """
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
    """Put one question to an agent per trial, `cwd`'d to that trial's tree alone.

    Written to `trials.json` after every trial rather than once after the loop, and a
    trial whose `answer` is already non-empty is skipped: each trial here brings a docker
    stack up and drives a real browser through it, minutes of real cost per trial, so an
    interruption partway through a three-trial round must not discard the trials that
    already finished — and a rerun must resume rather than pay for them again. The stack
    is torn down (`_teardown_stack`) before the question is put and again after, whether
    the agent answered or not — the after-teardown sits in a `finally`. `gf.call_agent`
    itself never raises (it retries and returns `""` on total failure), but nothing else
    in this loop body is guaranteed not to, and a trial that raised for any other reason
    is exactly the one most likely to have left a half-built stack holding 18101/18102
    and blocking every trial after it, this round and the next.
    """
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
    """Parse one judge response and apply the citation cap — pure, so tests need no agent.

    Mirrors `globex_book_line3._appraise` and `_greenfield.judge_one`: an `earned` verdict
    whose cited paths do not resolve under `repo`, or that cites nothing at all, is capped
    at `hedged` and flagged.
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

    Persisted after every trial, and a trial whose `reason` is already non-empty is
    skipped — the same reason `ask` persists per trial rather than once at the end: this
    step hands a judge agent a whole trial tree, `app/` and `compose.yml` included, to
    check the answer's citations against, and that read alone is not free. Graded over a
    `shutil.copytree` scratch copy of the trial's tree, never the tree `ask` used
    directly, so a judge agent's own session state never lands in what `score` later
    reads as the trial's evidence.
    """
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
    """Recompute the score from `trials.json` alone — no rereading of any tree.

    Read-only, like `globex_book_line3.score`: every field this needs was already
    persisted by `judge`, so scoring a sealed result later needs nothing but that file.
    """
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

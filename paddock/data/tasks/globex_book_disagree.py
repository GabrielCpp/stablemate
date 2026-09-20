"""disagree: when the app and the book disagree, can an agent say which one is wrong?

`globex_book_operate` measures whether an agent can act on an intact book. This module
measures §1 line 4 of the OKF acceptance test in `docs/plans/okf-executable-books.md`:
"when the app disagrees with the book, report which one is wrong." Three arms, one
question, run against the globex web-app `browse-and-add-widget` journey with a
Playwright MCP wired into the trial's own `cwd`, against the whole seed (`docs/`, `app/`
and `compose.yml` together) — exactly as `globex_book_operate` wires it, and for the same
reason: telling the app and the book apart needs a running stack and a real browser, not
source read in place of either.

    agree      — nothing perturbed; the app and the book state the same thing
    app-wrong  — the app's own source is edited so what it renders no longer matches the
                 book; the book, `code:` digest included, is untouched
    book-wrong — the book's own prose is edited so it states something the app does not
                 do; every file under `app/` is untouched, `code:` digest included

The observable fact both perturbations turn on is the `new-widget-link` component's
label. `docs/features/web-app/gui/screens/widget-list.md` states it twice — once as the
component's own `- name:` bullet, once as the `open-new-widget` interaction's `- name:`
bullet, the same "one fact stated twice" shape `globex_book_operate`'s module docstring
already found for the journey's steps — and both bullets share one `- code:` citation,
`app/web-app/static/index.html` @ebed722d64ce, naming the file that renders it:

    <a id="new-widget-link" href="new.html">Add a widget</a>

This was chosen over `submit-widget-button`'s "Add widget" label (`new.html`,
`new-widget.md`) only because `new-widget-link` is reachable, and its mismatch is visible,
from the very first screen a journey lands on — an agent does not have to complete the
form flow to notice it, so a `level: 0` trial fails from a shorter, cheaper session. Either
label would have satisfied every other requirement equally.

Both perturbation arms move the same fact to the same wrong value, `"Create a widget"`,
so the observable mismatch a browser sees is identical between them — only which side
holds the correct text, and whether the book's own `@ebed722d64ce` digest still matches
`app/web-app/static/index.html` on disk, tells them apart:

    agree      — app renders "Add a widget"; book states "Add a widget"; digest matches
    app-wrong  — app renders "Create a widget"; book still states "Add a widget"
                 (untouched); digest no longer matches the file
    book-wrong — app still renders "Add a widget" (untouched); book states
                 "Create a widget"; digest still matches the file

`ostler.stamp.digest_file` computes `hashlib.sha256(data).hexdigest()[:12]` — the exact
formula `@ebed722d64ce` already satisfies against the seed's own `index.html`, confirmed
by hand before writing `_perturb_app_wrong` below. Neither perturbation helper here ever
recomputes or rewrites a digest — only `ostler stamp` is allowed to write one, so
`app-wrong`'s whole point is that nothing here restamps it after the edit, and
`book-wrong`'s is that nothing under `app/` changes for there to be a new digest to write.
The rubric (`rubric-disagree.md`) requires a `level: 2` verdict's `reason` to name the
digest check explicitly, not just the text mismatch, because the text mismatch alone is
symmetric between the two wrong arms and cannot by itself say which side is at fault —
the digest is the one fact in the trial that only ever points at the app, never the book.

Like `globex_book_operate`, trials here are expensive (a docker compose stack and a real
browser per trial) and globex's book hardcodes ports 18101/18102, so `ask` and `judge`
run a plain serial loop, tear the stack down before and after every trial
(`_teardown_stack`), and persist the ledger after each trial rather than once at the end.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import _greenfield as gf
from _stablemate import TrialError
from paddock import Run, Score, step, task

#: Same config `globex_book_operate` pins for the same seed.
CONFIG = "configs/opencode.toml"

task(
    name="globex-book-disagree",
    seed="globex",
    config=CONFIG,
)

#: The one book page both perturbations turn on — it carries the `new-widget-link`
#: component's `- name:` bullet, the `open-new-widget` interaction's own `- name:`
#: bullet (the same fact stated twice, see the module docstring), and the `- code:`
#: citation naming the app file that renders it.
TARGET_DOC = "features/web-app/gui/screens/widget-list.md"

#: The app file `TARGET_DOC`'s `- code:` bullet names, digest `@ebed722d64ce`.
TARGET_APP = "app/web-app/static/index.html"

#: The observable text as the seed states and renders it, and the wrong value either
#: perturbation moves it to. Both arms use the same wrong value so the mismatch a browser
#: sees is identical between them — see the module docstring.
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

#: `claude`'s CLI reads `.mcp.json` from its `cwd` and nothing else — see
#: `globex_book_operate.MCP_JSON` for why this is how a trial gets Playwright wired in.
MCP_JSON: dict[str, Any] = {
    "mcpServers": {
        "playwright": {
            "command": "npx",
            "args": ["-y", "@playwright/mcp@latest", "--headless"],
        }
    }
}

#: Same bench, same pinned project/service names `globex_book_operate.BENCH_CONTAINERS`
#: tears down — globex's book hardcodes ports 18101/18102, so trials cannot run
#: concurrently and a stack a previous trial left running blocks the next.
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

#: Where the round's ledger lives inside the stage.
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
    """Tear down anything holding globex's hardcoded ports 18101 and 18102.

    Mirrors `globex_book_operate._teardown_stack` exactly, for the same reason: two
    trials cannot run concurrently against fixed ports, and a stack a previous trial left
    running blocks the next `docker compose up` cold. Called before every trial and after
    it, success or failure. Tolerant of "no such container" / "no such service" — the
    common case is that there is nothing to tear down, and that is success, not an error.
    """
    run.cli("docker", "compose", "down", "--remove-orphans", cwd=tree,
           log_name=f"teardown-{phase}-compose-{tree.name}")
    for name in BENCH_CONTAINERS:
        run.cli("docker", "rm", "-f", name, log_name=f"teardown-{phase}-rm-{name}-{tree.name}")


@step()
def arrange(run: Run) -> None:
    """Build one perturbed tree per arm, each a full copy of the seed.

    Like `globex_book_operate.arrange`, `docs/` alone will not do: telling the app and
    the book apart needs `docker compose up --build` to actually work, which needs
    `app/` and `compose.yml` alongside the book. So the whole seed is copied per trial,
    only the one file each arm's perturbation names is touched, and a `.mcp.json` wiring
    Playwright is written into the tree's root.
    """
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
    """Put the same question to an agent once per trial, `cwd`'d to that trial's tree.

    Mirrors `globex_book_operate.ask`: written after every trial, a trial whose `answer`
    is already non-empty is skipped so an interrupted round resumes rather than re-pays
    for trials that already finished, and the stack is torn down before the question is
    put and again after (in a `finally`), whether the agent answered or not.
    """
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
    """Parse one judge response and apply the citation cap — pure, so tests need no agent.

    Mirrors `globex_book_operate._appraise`: a `level: 2` verdict whose cited paths do
    not resolve under `repo`, or that cites nothing at all, is capped at `hedged` and
    flagged.
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

    Mirrors `globex_book_operate.judge`: persisted after every trial, a trial whose
    `reason` is already non-empty is skipped, and graded over a `shutil.copytree` scratch
    copy of the trial's tree, never the tree `ask` used directly.
    """
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
    """Recompute the score from `trials.json` alone — no rereading of any tree.

    Read-only, like `globex_book_operate.score`: every field this needs was already
    persisted by `judge`, so scoring a sealed result later needs nothing but that file.
    """
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

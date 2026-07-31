"""The `author` workflow, rendered as Python instead of YAML.

HISTORY — SUPERSEDED. The real `author` workflow is
`workflows/src/workhorse_workflows/author/`. This file is not it: nothing
imports it, nothing runs it, it is not installed and no test covers it. Do not
copy it as an example; the shipped package is the example, and how to write one
is `workhorse/docs/AUTHORING.md`.

A **design artifact, not a running workflow**. It existed so the shape proposed
in `docs/plans/workflow-as-python-state-machine.md` could be judged against the
largest thing we ran at the time: `base-library/workflows/author/` was 2,389
lines of YAML over 159 nodes, plus 23 sibling scripts totalling 2,650 lines.
Nothing under `workhorse/` or `base-library/workflows/` was touched to produce
it. When it was written `workhorse.pyflow` did not exist — that import was the
proposal. It exists now, and this file's guesses about it are not authoritative
where they differ.

## The layout

    @blueprint.node
    def select_story(logger, cfg, epic) -> StoryChoice: ...

    class Author(Workflow):
        mode: Mode = "epic"                       # an input, fixed at launch

        def setup(self) -> RunContext: ...        # resolved once, then frozen

        def next_story(self, epic: str):
            choice = self.call(select_story, cfg=self.ctx, epic=epic)
            return Continue(choice, self.write_story, epic=epic, story=choice.slug)

    workflow = Workflow()
    workflow.add_blueprints(scriptutil.blueprint, blueprint)
    workflow.add_flows(Surveyor)                  # addressable from the CLI
    main = workflow.main(Author)                  # the console-script callable

Three layers, and the split between them is the whole idea:

  - **A blueprint is a node library.** Free functions taking `logger` first —
    the same contract `scripts/*.py` already has via `main(logger)`, so today's
    scripts port over as-is. Blueprints are the reusable layer: this workflow
    adds its own, and picks up `scriptutil`'s (`await_operator`, `commit_all`,
    `push_branch`, `github_client`) rather than re-implementing them, which is
    what `add_blueprints(...)` being plural is for.

  - **A Workflow subclass is the state machine.** Methods are states, and
    `Continue(result, self.other, **params)` is the transition. States can
    be as fat as the work they own — nine of them for 159 nodes — because
    fatness costs nothing here; what costs is *coupling*, and the parameter
    list is where that gets paid, visibly.

  - **`self.call` / `self.agent` / `self.handoff` are the seams.** Calling a
    node directly would work and would be invisible; going through `self.call`
    is what makes it a node: its own span, its own `output.json`, memoized on
    resume, and a no-op that merely records itself under `--dry-run`, which is
    what lets `dot` render without executing anything.

## What checks the arguments

Both seams take `**kwargs`, and loose kwargs are how the YAML's untyped `with:`
bag would sneak back in one layer up. `ParamSpec` closes it — the engine side
is four signatures:

    P = ParamSpec("P")
    T = TypeVar("T")

    # `Concatenate` strips the injected logger, so the checker sees the node's
    # own parameters — and `-> T` is the node's return type, so the *result*
    # is typed too, not just the call.
    def call(self, node: Callable[Concatenate[Logger, P], T],
             *a: P.args, **kw: P.kwargs) -> T: ...

    # A prompt has no signature, so `args` stays a dict — deliberately, and
    # this is the only place it is right. `returns=` supplies the type.
    def agent(self, prompt: str, *, returns: type[T], args: dict) -> T: ...

    # A Workflow subclass is a Pydantic model, so its synthesised `__init__`
    # is the signature: the checker validates the sub-workflow's inputs.
    def handoff(self, wf: Callable[P, W], *a: P.args, **kw: P.kwargs) -> W: ...

    class Continue(Generic[P]):
        def __init__(self, result: object, next: Callable[P, Transition], /,
                     *a: P.args, **kw: P.kwargs): ...

Which is why the transition target is **positional**: `P.kwargs` has to own the
whole keyword namespace, so a `next=` keyword cannot coexist with it. That
turns out to be the right shape anyway — under the keyword form no state could
ever have a parameter named `next` or `result` without colliding with the
constructor.

`ParamSpec` covers author time. Two other moments need their own answer, and
neither is a type checker's job:

  - **Transition time.** `Continue.__init__` can `inspect.signature(next).bind`
    its own kwargs, which costs nothing and catches a transition built
    dynamically, or written by someone not running a checker, *before* the
    checkpoint is written rather than after the resume.
  - **Resume time.** Parameters come back off disk as JSON, where no static
    guarantee survives. The same annotations do the work again: validating a
    state's parameters against its signature the way `pydantic.validate_call`
    does is what turns `"docs/epics"` back into a `Path` and rejects a
    hand-edited checkpoint that names a parameter the state does not have.

So the annotations on these states are load-bearing three times over, which is
the argument for spelling them out even where they are all `str`.

## Where state lives — three tiers, and no fourth

| tier            | written by       | lifetime      | checkpointed      |
| --------------- | ---------------- | ------------- | ----------------- |
| inputs (fields) | the operator     | the whole run | once, at launch   |
| `self.ctx`      | `setup()`, once  | the whole run | once, after setup |
| state params    | the state before | one hop       | every transition  |

**The class holds no mutable state.** Anything a state *discovers* — which
epic, which story, how many reworks are left, what the reviewer said — travels
in the parameters of the next state and nowhere else. So the checkpoint is a
line of JSON you can read, and hand-edit:

    {"state": "write_story", "params": {"epic": "auth", "story": "login-form",
                                        "resolves": 1}}

That is not just a smaller checkpoint. It is what makes finding #2 below
*unwriteable*: `commit_author` cannot render an ambient `{{ epic }}` because
`close()` has no `epic` in scope and never will. A dependency that survives
nine states has to be threaded through nine signatures, and being annoying to
write is the point — it prices the coupling instead of hiding it.

Two things fall out of the rule that are worth noticing:

  - **Derived values are derived, not carried.** `epic_dir`, `story_dir`,
    `story_path` and the three `*-context.md` paths were all fields on an
    earlier draft of this class. Every one is a pure function of
    `(ctx, epic, story)`, so they are the four helpers below `RunContext` and
    no state passes them anywhere.
  - **Loop budgets become visible, and get billed.** `cov_reworks` and
    `resolves` are ordinary parameters, so "this run is on coverage rework 2 of
    3" is legible in the checkpoint rather than buried in a counter node's
    output. The flip side is that `cov_reworks` has to be passed through
    `write_story` and `story_feedback`, which never read it, because the story
    loop sits inside the loop that owns it. That is the design charging for a
    run-scoped counter instead of letting the context bag absorb it.

`setup()` exists for the residue: `base_branch` is decided at the top of the
run and needed only at the very bottom, and threading it through seven
uninterested states would be worse than the disease. The tier is deliberately
narrow — written once, frozen, never a place to stash progress.

## What "gathering the nodes in" means here

Each `script:` node's *logic* is inlined as a blueprint node. What is dropped
is the part of each script that was protocol rather than logic, because this
model removes the need for it: `sys.argv` parsing and `print(json.dumps(...))`
(23x), a locally re-implemented `find_repo_root()` (12x), `die(..., code=2)`
to signal failure through an exit code, and the `"yes"`/`"no"` string booleans
that existed only because a `branch:` node could switch on nothing else.
Roughly a third of those 2,650 lines was that envelope.

## What disappears outright

  - **39 nodes** (`reset_*`, `incr_*`, `guard_*`) and both counter scripts
    (`init_counter.py`, `incr_counter.py`, 26 call sites) become
    `for _ in range(MAX_REWORKS)`. A counter *reset* becomes nothing at all —
    it is re-entering the state with the parameter back at its default.
  - **58 branch nodes** become `if` / `match`.
  - The nine `max_*` vars stop being strings duplicated into guard conditions
    under a "keep these in sync" comment, and become two constants.
  - The five `resolve_*` agent nodes were one prompt with a different
    `block_stage:` string each: one call, one argument.
  - `open-author-pr.py` spawning its own sibling `gh-token.py` as a subprocess
    to get a string back becomes an import.

## Three things the rewrite surfaced (preserved, not fixed)

  1. `mode: story` ends at the `done` terminal straight after `story_prune`,
     skipping reconcile, integrity, `validate_artifacts`, the commit and the
     PR. A single-story run leaves its work uncommitted on the author branch.
     See `Author.story_feedback`.
  2. `commit_author` and `open_author_pr` render `{{ epic }}`, which resolves
     to whatever `select_epic` last wrote into the run context — many nodes
     earlier, possibly several times over. Here `close()` has no `epic`, so
     the commit message says what it actually knows.
  3. `cov_rework_count` is reset before `split_stories` but read by the
     coverage stage, so the two are one loop wearing two hats. That is why
     `author_epic` is re-entrant and `check_coverage` returns to it, carrying
     the budget back as a parameter.

## Scope note

The two sub-graphs under the YAML's `flows:` — `surveyor` (23 nodes) and
`parity-surveyor` (8 nodes) — are not gathered in. They are their own state
machines; under this design each is its own `Workflow` subclass, reached with
`self.handoff(...)`, and each would get this same treatment in its own module.
"""

import logging
import os
import re
from pathlib import Path
from typing import Literal

import yaml
from author.gh_token import resolve_github_token
from author.surveyor import ParitySurveyor, Surveyor
from ostler import Ostler, markdown, registry
from ostler.model import section_gaps, status_bullet
from pydantic import BaseModel
from workhorse import scriptutil
from workhorse import worklist as wl
from workhorse.pyflow import Blueprint, Continue, Done, Workflow, WorkflowFailed

log = logging.getLogger(__name__)

blueprint = Blueprint("author")
# No `requires=`: the YAML block was a hand-rolled dependency manifest, needed
# only because a workflow was data with no other way to declare what it needed.
# The distribution's `[project.dependencies]` is the manifest now, and a second
# one that can disagree with it is worse than none.


# ---------------------------------------------------------------------------
# Budgets
#
# In the YAML these were `vars:` holding strings, because a `branch:` condition
# cannot render Jinja — so each also appeared as a literal inside a guard node,
# kept in sync by a comment. Here each is used once, by the loop it bounds.
# ---------------------------------------------------------------------------

MAX_REWORKS = 3  # review -> rework -> review, before escalating to an operator
MAX_RESOLVES = 2  # auto-resolve attempts at a blocked stage, before a human

Mode = Literal["epic", "story", "survey", "parity-survey"]
OperatorMode = Literal["auto", "human"]


# ---------------------------------------------------------------------------
# Node results
#
# The YAML declared these as `outputs: [{key: story_ok}]` — an untyped bag of
# strings, in which "no", "false" and "" were three different falsy spellings a
# branch node had to be taught about one at a time.
# ---------------------------------------------------------------------------


class Config(BaseModel):
    """Where this repo keeps the things `author` edits."""

    repo_root: Path
    backlog_path: Path
    epics_dir: Path
    surface_manifest: Path
    features_dir: Path
    mockup_dir: Path
    layers: list[str]


class Branches(BaseModel):
    base_branch: str
    author_branch: str


class SeededStory(BaseModel):
    story_slug: str
    bullet_id: str
    from_backlog: bool
    reason: str


class EpicChoice(BaseModel):
    epic: str = ""
    reason: str = ""
    progress: str = ""


class StoryChoice(BaseModel):
    story_slug: str = ""
    reason: str = ""
    progress: str = ""
    remaining_count: int = 0


class Defects(BaseModel):
    """A check that either passes or explains itself."""

    ok: bool
    errors: str = ""


class VerifyReport(Defects):
    """A check that can additionally decline to run — no git, no epics dir, no
    baseline. `skipped` is not `ok`; it is "this told us nothing". Both advance
    the run, which the YAML could only say as a branch `default:`."""

    skipped: bool = False
    report: str = ""


class Feedback(BaseModel):
    present: bool
    scope: Literal["story", "epic"] = "story"
    content: str = ""


class Pruned(BaseModel):
    removed: int
    remaining: int


class PullRequest(BaseModel):
    state: Literal["opened", "exists", "skipped"]
    url: str = ""
    skip_reason: str = ""


# ---------------------------------------------------------------------------
# Agent results
#
# An agent node has no signature to read, so `returns=` names the shape its
# answer is parsed into. This is the one place the typed-argument argument
# does not apply, and it is worth noticing that it is also the only place the
# YAML's untyped `outputs:` was ever load-bearing.
# ---------------------------------------------------------------------------


class Verdict(BaseModel):
    """Every reviewing agent answers with a status plus free-text notes. The
    notes are what gets handed to the rework prompt or shown to the operator."""

    status: str
    notes: str = ""


class DecomposeResult(Verdict):
    status: Literal["complete", "blocked"] = "complete"


class EpicReview(Verdict):
    status: Literal["approved", "needs_rework", "blocked"]


class WriteEpicResult(Verdict):
    status: Literal["complete", "blocked"]


class SplitResult(Verdict):
    # `standoff` = the split stage declines the coverage stage's rework
    # request. Two agents disagreeing is a third outcome, not a failure.
    status: Literal["complete", "blocked", "standoff"]


class WriteStoryResult(Verdict):
    status: Literal["written", "blocked"]


class AuditResult(Verdict):
    status: Literal["passed", "failed"]


class CoverageReview(Verdict):
    status: Literal["ok", "gaps", "blocked"]


class ResolveStatus(BaseModel):
    decision: Literal["answered", "escalated"] = "answered"


class MockupResult(BaseModel):
    mockup: Path | None = None


# ===========================================================================
# The blueprint: scripts/ gathered in
#
# Free functions taking `logger` first — today's `main(logger)` script contract,
# minus the argv/JSON envelope. Four of these are near-identical to coder's and
# are the natural first contents of a shared blueprint.
#
# Note what the selection nodes no longer return: `epic_dir`, `story_dir` and
# `story_path` were fields on three of these models, and each was `epics_dir /
# epic [/ slug]`. Derived values are derived at the point of use.
# ===========================================================================


def _okf(cfg: Config) -> Ostler:
    """One place. `Ostler(find_repo_root())` was re-derived in 12 scripts, each
    with its own copy of a root walk checking AGENT_REPO_DIR, then agents.yml,
    then docs/epics."""
    return Ostler(cfg.repo_root)


@blueprint.node
def load_config(logger: logging.Logger, backlog: Path, epics_dir: Path) -> Config:
    """scripts/load-config.py — resolve this repo's doc layout once, up front."""
    root = scriptutil.find_repo_root()
    agents_yml = root / "agents.yml"
    data = yaml.safe_load(agents_yml.read_text()) if agents_yml.is_file() else {}
    template = (data or {}).get("template") or {}

    backlog_path = root / (template.get("backlog") or backlog)
    if not backlog_path.is_file():
        # Was `scriptutil.die(..., code=2)`. The author workflow has nothing to
        # author without a backlog and no branch downstream could route around
        # it, so this was always a hard stop wearing an exit code.
        raise WorkflowFailed(f"backlog not found: {backlog_path}")

    features_dir = root / (template.get("features_dir") or "docs/features")
    manifest = template.get("surface_manifest")
    if not manifest:
        # Prefer the surveyor's unit manifest where this repo has been
        # surveyed; fall back to the feature inventory.
        surveyed = root / "docs/survey/unit-manifest.json"
        manifest = surveyed if surveyed.is_file() else features_dir / "inventory.json"

    cfg = Config(
        repo_root=root,
        backlog_path=backlog_path,
        epics_dir=root / (template.get("epics_dir") or epics_dir),
        surface_manifest=Path(manifest),
        features_dir=features_dir,
        mockup_dir=root / (template.get("mockup_dir") or "docs/design"),
        layers=[
            str(li["skill"])
            for li in (data or {}).get("localInstructions") or []
            if li.get("skill")
        ],
    )
    logger.info("repo %s, %d instruction layer(s)", root, len(cfg.layers))
    return cfg


@blueprint.node
def branch_author(logger: logging.Logger, run_dir: Path, mode: Mode) -> Branches:
    """scripts/branch-author.py — put the run on its own branch.

    Named after the run dir rather than the clock, so resuming returns to the
    branch the run was already using instead of opening a second one.
    """
    root = scriptutil.find_repo_root()
    if not (root / ".git").exists():
        # A repo with no git is a legitimate target (a scratch checkout, a
        # container bind-mount): authoring still works, branching does not.
        return Branches(base_branch="main", author_branch="")

    base = scriptutil.active_branch(root) or os.environ.get("REPO_BRANCH") or ""
    if not base:
        base = next(
            (b for b in ("develop", "main", "master") if scriptutil.local_branch_exists(root, b)),
            "main",
        )

    branch = f"author/{run_dir.name}"
    exists = scriptutil.local_branch_exists(root, branch)
    scriptutil.checkout(root, branch, create=not exists, base=base)
    logger.info("authoring on %s (base=%s, mode=%s)", branch, base, mode)
    return Branches(base_branch=base, author_branch=branch)


_BACKLOG_ID_RE = re.compile(r"^\s*-\s*\[([A-Za-z0-9][A-Za-z0-9._-]*)\]\s*(.*)$")


@blueprint.node
def seed_story(logger: logging.Logger, cfg: Config, epic: str, bullet: str) -> SeededStory:
    """scripts/seed-story.py — `mode: story` entry: turn one backlog bullet into
    a seed and an empty story, idempotently."""
    if not epic or not bullet:
        raise WorkflowFailed("mode=story needs both --epic and --bullet")
    if not (cfg.epics_dir / epic / "epic.md").is_file():
        raise WorkflowFailed(f"no such epic: {cfg.epics_dir / epic / 'epic.md'}")

    okf = _okf(cfg)
    bullet_id, source_bullet, from_backlog = _resolve_bullet(cfg.backlog_path, bullet)

    # Idempotent: a resumed run must land on the story it already created, not
    # open a second one covering the same bullet.
    for story in okf.list("story", epic=epic):
        if bullet_id in (story.get("covers") or []):
            logger.info("reusing story %s for bullet %s", story["slug"], bullet_id)
            return SeededStory(
                story_slug=story["slug"], bullet_id=bullet_id,
                from_backlog=from_backlog, reason="reused existing story",
            )

    okf.add_seed(
        epic, bullet_id, status="researched", summary=source_bullet,
        meta={"sourceBullet": source_bullet},
    )
    return SeededStory(
        story_slug=okf.create_story(epic, source_bullet, covers=[bullet_id]),
        bullet_id=bullet_id,
        from_backlog=from_backlog,
        reason="seeded from backlog" if from_backlog else "seeded from literal bullet",
    )


def _resolve_bullet(backlog: Path, bullet: str) -> tuple[str, str, bool]:
    """`--bullet` is either an id present in the backlog, or literal prose."""
    for line in backlog.read_text().splitlines():
        m = _BACKLOG_ID_RE.match(line)
        if m and (m.group(1) == bullet or m.group(2).strip() == bullet.strip()):
            return m.group(1), m.group(2).strip(), True
    return bullet, bullet, False


@blueprint.node
def select_epic(logger: logging.Logger, cfg: Config) -> EpicChoice:
    """scripts/select-epic.py — the next epic still needing stories written."""
    okf = _okf(cfg)
    todo = [e for e in okf.todo() if not okf.epic_authored(e["epic"])]
    wl.snapshot(todo)
    chosen = wl.select_next(todo)
    if chosen is None:
        return EpicChoice(reason="every epic is authored")
    logger.info("epic %s (%s)", chosen["epic"], wl.progress(todo))
    return EpicChoice(
        epic=chosen["epic"],
        reason=chosen.get("detail", ""),
        progress=wl.progress(todo),
    )


@blueprint.node
def select_story(logger: logging.Logger, cfg: Config, epic: str) -> StoryChoice:
    """scripts/select-story.py — the next story in this epic needing authoring."""
    report = _okf(cfg).next_story_report(epic, need="author")
    if report["state"] != "ready":
        logger.info("epic %s: %s", epic, report["state"])
        return StoryChoice(reason=report.get("detail") or report["state"])

    return StoryChoice(
        story_slug=report["story"]["slug"],
        reason=report.get("detail", ""),
        progress=f"{report['done']}/{report['done'] + report['remaining']}",
        remaining_count=report["remaining"],
    )


# Phrases meaning the author deferred a decision instead of making one. A story
# carrying any of these is not written, however complete it looks.
_OPEN_QUESTION_PHRASES = (
    "decision to surface", "decisions to surface", "to be decided",
    "to be determined", "to be confirmed", "to be defined",
    "open question", "open questions", "decide whether", "decide if",
    "decide between", "accept, or tune", "accept or tune",
    "we should decide", "needs a decision", "to be discussed",
)
_OPEN_QUESTION_WORDS = frozenset({"tbd", "todo", "fixme"})


@blueprint.node
def validate_story(logger: logging.Logger, story_dir: Path) -> Defects:
    """scripts/validate-story.py — is the story doc structurally written?"""
    doc = markdown.load(story_dir / "story.md")
    errors: list[str] = []

    if not status_bullet(doc):
        errors.append("no `- Status:` bullet")
    errors.extend(
        f"section `{s}` is missing or empty" for s in section_gaps(doc, registry.STORY_SECTIONS)
    )

    text = doc.text.lower()
    errors.extend(f"unresolved: {p!r}" for p in _OPEN_QUESTION_PHRASES if p in text)
    words = set(re.findall(r"[a-z0-9_-]+", text))
    errors.extend(f"unresolved marker: {w.upper()}" for w in sorted(_OPEN_QUESTION_WORDS & words))

    logger.info("%s: %d defect(s)", story_dir.name, len(errors))
    return Defects(ok=not errors, errors="\n".join(errors))


@blueprint.node
def check_story_grounding(
    logger: logging.Logger, cfg: Config, epic: str, story_slug: str
) -> Defects:
    """scripts/check-story-grounding.py — does the story talk about surfaces
    that actually exist?"""
    okf = _okf(cfg)
    errors: list[str] = []

    seeds = {s["id"] for s in okf.list("seed", epic=epic)}
    story = okf.get("story", story_slug)
    errors.extend(
        f"covers `{c}`, which is not a seed of `{epic}`"
        for c in story.get("covers") or []
        if c not in seeds
    )

    # Only meaningful once the repo has a UI graph. Before that every citation
    # would read as dangling, failing every story in a fresh repo.
    if okf.graph.ui_nodes:
        cited = okf.query("surfaces-referenced-by-story", story_slug)
        if not any(e["kind"] == "ui" for e in cited):
            errors.append("cites no known UI surface")
        errors.extend(f"cites unknown surface `{e['ref']}`" for e in cited if e["kind"] == "missing")
    else:
        logger.info("no UI graph yet — surface citations not checked")

    return Defects(ok=not errors, errors="\n".join(errors))


# ostler findings meaning an epic's stories do not cover its seeds. Other error
# findings are real, but they are not *this* stage's business.
_COVERAGE_CODES = frozenset({
    "orphan-seed", "dangling-seed", "cross-epic-seed", "dangling-dependency",
    "cross-epic-dependency", "missing-story-file", "unwritten-story",
})


@blueprint.node
def validate_coverage(logger: logging.Logger, cfg: Config, epic: str) -> Defects:
    """scripts/validate-epic-coverage.py — every seed covered by a story."""
    findings = [
        f for f in _okf(cfg).doctor(epic=epic)
        if f["severity"] == "error" and f["code"] in _COVERAGE_CODES
    ]
    logger.info("epic %s: %d coverage finding(s)", epic, len(findings))
    return Defects(
        ok=not findings,
        errors="\n".join(f"{f['code']}: {f['message']}" for f in findings),
    )


@blueprint.node
def verify_reconcile(logger: logging.Logger, cfg: Config) -> VerifyReport:
    """scripts/reconcile-artifacts.py — did this run *delete* anything?

    Compares each epic.md's `## Seeds` / `## Stories` ids against the committed
    baseline. Removals block; additions are the point of the run. Skips rather
    than fails with no git, no epics dir or no baseline — a check that could
    not run must not look like a check that failed.
    """
    root = cfg.repo_root
    if not (root / ".git").exists() or not cfg.epics_dir.is_dir():
        return VerifyReport(ok=True, skipped=True, report="no git or no epics dir")

    lost: list[str] = []
    checked = 0
    for epic_md in sorted(cfg.epics_dir.glob("*/epic.md")):
        baseline = scriptutil.show_file(root, "HEAD", epic_md.relative_to(root))
        if baseline is None:
            continue  # a brand new epic has nothing to have lost
        checked += 1
        for section in ("Seeds", "Stories"):
            gone = _subsection_ids(baseline, section) - _subsection_ids(epic_md.read_text(), section)
            lost.extend(f"{epic_md.parent.name}: {section[:-1].lower()} `{i}` removed" for i in gone)

    if not checked:
        return VerifyReport(ok=True, skipped=True, report="no committed baseline to compare")
    logger.info("%d epic(s) compared against HEAD, %d removal(s)", checked, len(lost))
    return VerifyReport(ok=not lost, errors="\n".join(lost), report=f"{checked} epic(s) compared")


def _subsection_ids(text: str, section: str) -> set[str]:
    """`### <id>` headings under `## <section>`."""
    ids: set[str] = set()
    inside = False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line[3:].strip() == section
        elif inside and line.startswith("### "):
            ids.add(line[4:].strip())
    return ids


@blueprint.node
def verify_integrity(logger: logging.Logger, cfg: Config) -> VerifyReport:
    """scripts/ostler-doctor.py — the whole doc graph, not just this epic."""
    findings = [f for f in _okf(cfg).doctor() if f["severity"] == "error"]
    logger.info("doctor: %d error finding(s)", len(findings))
    return VerifyReport(
        ok=not findings,
        errors="\n".join(f"{f['code']}: {f['message']}" for f in findings),
        report=f"{len(findings)} error finding(s)",
    )


_DONE_TOKENS = ("qa passed", "passed", "done", "merged", "complete")


@blueprint.node
def validate_artifacts(logger: logging.Logger, cfg: Config) -> Defects:
    """scripts/validate-artifacts.py — the last gate before committing.

    Catches the failure this stage exists to prevent: a branch that looks
    finished but carries a story nobody wrote.
    """
    okf = _okf(cfg)
    errors: list[str] = []

    by_epic: dict[str, list[dict]] = {}
    for story in okf.list("story"):
        by_epic.setdefault(story["epic"], []).append(story)

    for item in okf.todo():
        epic = item["epic"]
        if epic not in okf.graph.epics:
            errors.append(f"epic `{epic}` does not load")
            continue
        stories = by_epic.get(epic, [])
        if not stories:
            errors.append(f"epic `{epic}` has no stories")
        for story in stories:
            if not story.get("hasStoryMd"):
                errors.append(f"story `{story['slug']}` has no story.md")
            elif not story.get("authored"):
                unwritten = ", ".join(story.get("unwrittenSections") or []) or "unknown"
                errors.append(f"story `{story['slug']}` is unwritten ({unwritten})")

    every = [s for stories in by_epic.values() for s in stories]
    if every and not any(str(s.get("status", "")).lower() not in _DONE_TOKENS for s in every):
        errors.append("no selectable story: every story is already done")

    logger.info("%d artifact error(s)", len(errors))
    return Defects(ok=not errors, errors="\n".join(errors))


@blueprint.node
def record_attempt(logger: logging.Logger, story_dir: Path, label: int, note: str) -> str:
    """scripts/ledger.py — append-only record of what each rework was told.

    Idempotent on the attempt heading, and deliberately incapable of failing
    the run: losing the ledger is worse than losing an entry.
    """
    path = story_dir / "attempts.md"
    heading = f"## Attempt {label}"
    ledger = path.read_text() if path.is_file() else ""
    if heading not in ledger:
        ledger = f"{ledger}\n{heading}\n\n{note}\n"
        path.write_text(ledger)
        logger.info("recorded attempt %d", label)
    return ledger


_STATUS_RE = re.compile(r"^STATUS:[ \t]*(\S+)", re.MULTILINE)
_SCOPE_RE = re.compile(r"^SCOPE:[ \t]*(\S+)", re.MULTILINE)


@blueprint.node
def check_story_feedback(logger: logging.Logger, story_dir: Path) -> Feedback:
    """scripts/check_feedback.py — a non-blocking poll of the operator's inbox.

    The counterpart to `scriptutil.await_operator`: same file protocol, but a
    run that finds nothing carries on instead of waiting.
    """
    path = story_dir / "feedback.md"
    if not path.is_file():
        return Feedback(present=False)
    text = path.read_text()
    status = _STATUS_RE.search(text)

    if status and status.group(1) != "NEW":
        return Feedback(present=False)
    if not status and not text.strip():
        return Feedback(present=False)

    # Stamp it consumed *before* acting on it, so a crash mid-rework cannot make
    # the same feedback arrive twice.
    path.write_text(
        _STATUS_RE.sub("STATUS: CONSUMED", text) if status else f"STATUS: CONSUMED\n{text}"
    )
    scope = _SCOPE_RE.search(text)
    logger.info("operator feedback picked up from %s", path)
    return Feedback(
        present=True,
        scope=scope.group(1) if scope and scope.group(1) in ("story", "epic") else "story",
        content=text,
    )


@blueprint.node
def prune_bullet(logger: logging.Logger, backlog: Path, bullet_id: str) -> Pruned:
    """scripts/prune-bullet.py — drop the one bullet `mode: story` consumed."""
    return _prune(logger, backlog, {bullet_id})


@blueprint.node
def prune_backlog(logger: logging.Logger, cfg: Config, epic: str) -> Pruned:
    """scripts/prune-backlog.py — drop every bullet this epic's seeds absorbed.

    Matching is tolerant because a seed's `sourceBullet` is prose that was
    lightly edited on the way in.
    """
    sources = [
        str((s.get("meta") or {}).get("sourceBullet") or "")
        for s in _okf(cfg).list("seed", epic=epic)
    ]
    absorbed = set()
    for line in cfg.backlog_path.read_text().splitlines():
        m = _BACKLOG_ID_RE.match(line)
        if m and any(_same_bullet(m.group(2).strip(), s) for s in sources):
            absorbed.add(m.group(1))
    return _prune(logger, cfg.backlog_path, absorbed)


def _same_bullet(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return a == b or (min(len(a), len(b)) >= 8 and (a in b or b in a))


def _prune(logger: logging.Logger, backlog: Path, ids: set[str]) -> Pruned:
    lines = backlog.read_text().splitlines()
    kept = [ln for ln in lines if not ((m := _BACKLOG_ID_RE.match(ln)) and m.group(1) in ids)]
    backlog.write_text("\n".join(kept) + "\n")
    remaining = sum(1 for ln in kept if _BACKLOG_ID_RE.match(ln))
    logger.info("pruned %d bullet(s), %d remaining", len(lines) - len(kept), remaining)
    return Pruned(removed=len(lines) - len(kept), remaining=remaining)


@blueprint.node
def commit_author(logger: logging.Logger, cfg: Config, message: str) -> bool:
    """scripts/commit-author.py

    The YAML built the message from `{{ mode }}`, `{{ epic }}` and
    `{{ bullet }}` *inside* the node, which is how `{{ epic }}` came to be read
    at a point where nobody knew what it referred to. Composing the message is
    the caller's job; committing is this node's.
    """
    logger.info("%s", message)
    return scriptutil.commit_all(cfg.repo_root, message)


@blueprint.node
def open_author_pr(
    logger: logging.Logger, cfg: Config, base_branch: str, author_branch: str, title: str
) -> PullRequest:
    """scripts/open-author-pr.py — publish the branch, if there is anywhere to
    publish it to.

    Note the two failure classes, which the YAML could only tell apart by exit
    code plus an output string. *Skipping* (no git, no token, an origin that is
    not GitHub) is a legitimate end state for a local-only run. *Failing* (the
    push was rejected, the repo is unreachable) is not.
    """
    root = cfg.repo_root
    if not author_branch or not scriptutil.branch_exists(root, author_branch):
        return PullRequest(state="skipped", skip_reason="no author branch")

    slug = _github_slug(scriptutil.remote_urls(root))
    if slug is None:
        return PullRequest(state="skipped", skip_reason="origin is not a github.com remote")
    token = resolve_github_token(root)  # was: subprocess -> scripts/gh-token.py
    if not token:
        return PullRequest(state="skipped", skip_reason="no GitHub token available")

    scriptutil.push_branch(root, author_branch)
    gh = scriptutil.github_client(token)
    if existing := gh.find_pull(slug, head=author_branch, base=base_branch):
        return PullRequest(state="exists", url=existing["html_url"])

    created = gh.create_pull(
        slug, head=author_branch, base=base_branch,
        title=title, body="Authored by the `author` workflow.",
    )
    logger.info("opened %s", created["html_url"])
    return PullRequest(state="opened", url=created["html_url"])


def _github_slug(remotes: dict[str, str]) -> str | None:
    """`origin` may be a local bind-mount of the real checkout, in which case
    follow it to the repo that does have a GitHub origin."""
    for url in remotes.values():
        if m := re.search(r"github\.com[:/]([^/]+/[^/.]+)", url):
            return m.group(1)
    return None


# ===========================================================================
# Run context
#
# Resolved once by `setup()` and frozen. This is not a place to put progress:
# it holds what the run was told and what it worked out about the repo before
# doing anything, and nothing here is written twice.
# ===========================================================================


class RunContext(Config, frozen=True):
    base_branch: str = ""
    author_branch: str = ""


# The paths that were fields on an earlier draft of the state machine. Every
# one is a pure function of what the states already carry, so none of them
# needs to be carried.


def epic_dir(ctx: RunContext, epic: str) -> Path:
    return ctx.epics_dir / epic


def story_dir(ctx: RunContext, epic: str, story: str) -> Path:
    return ctx.epics_dir / epic / story


def story_path(ctx: RunContext, epic: str, story: str) -> Path:
    return story_dir(ctx, epic, story) / "story.md"


def author_context(ctx: RunContext) -> Path:
    """Where the operator is talked to about run-wide blocks."""
    return ctx.epics_dir / "_author-context.md"


# ===========================================================================
# The state machine
#
# Methods are states; their parameters are the checkpoint. The class holds no
# mutable state, so a state cannot read anything it was not handed and cannot
# leave anything behind for a later one — which is the entire mechanism by
# which `{{ epic }}`-at-commit-time stops being expressible.
# ===========================================================================


class Author(Workflow):
    """`author` — turn a backlog into epics, and epics into written stories."""

    # -- inputs (`workhorse --param mode=story`), fixed for the whole run ----
    # The nine `max_*` vars are gone: they are the two constants at the top of
    # this module.
    mode: Mode = "epic"
    epic: str = ""  # mode=story only: which epic the named bullet belongs to
    bullet: str = ""
    backlog: Path = Path("docs/backlog.md")
    epics_dir: Path = Path("docs/epics")
    rubric: Path = Path("docs/survey/rubric.md")
    survey_dir: Path = Path("docs/survey")
    baseline_inventory: str = ""
    target_features: Path = Path("docs/features")
    parity_survey_dir: Path = Path("docs/survey/legacy-vs-new")
    operator_mode: OperatorMode = "auto"

    def setup(self) -> RunContext:
        """Run once, before `start`, and frozen into `self.ctx` thereafter.

        `base_branch` is the case this tier exists for: decided here, used only
        by `close()`, and of no interest to the seven states in between.
        Threading it through all of them would be worse than the disease —
        but note how narrow that makes the tier. Two strings.
        """
        cfg = self.call(load_config, backlog=self.backlog, epics_dir=self.epics_dir)
        branches = self.call(branch_author, run_dir=self.run_dir, mode=self.mode)
        return RunContext(**cfg.model_dump(), **branches.model_dump())

    def labels(self, epic: str = "", story: str = "", **_) -> dict[str, str]:
        """Telemetry. Was three Jinja expressions in `labels:`, re-rendered
        against the run context before every node and each guarding
        half-populated context with an `or` chain. The engine hands the current
        state's parameters straight in, so there is nothing to guard."""
        return {"work_id": story or epic, "epic": epic, "mode": self.mode}

    # -- states ------------------------------------------------------------

    def start(self) -> Continue | Done:
        """`decide_mode`, and nothing else. Config and branching happened in
        `setup`, which is where once-per-run work belongs."""
        match self.mode:
            case "survey":
                # A whole nested state machine, run to its own `Done` and
                # returning here — which is what a `flow:` node did, and what
                # `Continue` cannot express, since its target is always a
                # method of this class.
                self.handoff(
                    Surveyor,
                    rubric=self.rubric,
                    survey_dir=self.survey_dir,
                    backlog=self.ctx.backlog_path,
                    operator_mode=self.operator_mode,
                )
                return Continue(None, self.split_epics)

            case "parity-survey":
                result = self.handoff(
                    ParitySurveyor,
                    baseline_inventory=self.baseline_inventory,
                    target_features=self.target_features,
                    survey_dir=self.parity_survey_dir,
                    backlog=self.ctx.backlog_path,
                    epics_dir=self.ctx.epics_dir,
                )
                # Terminal: a parity survey produces a backlog for a *later*
                # run to author.
                return Done({"mode": "parity-survey", "bullets": result.bullet_count})

            case "story":
                seeded = self.call(
                    seed_story, cfg=self.ctx, epic=self.epic, bullet=self.bullet
                )
                return Continue(
                    seeded,
                    self.write_story,
                    epic=self.epic,
                    story=seeded.story_slug,
                    # Carried so `story_feedback` can prune the bullet this
                    # consumed. Empty when the bullet was literal prose rather
                    # than a backlog entry, so there is nothing to prune.
                    bullet_id=seeded.bullet_id if seeded.from_backlog else "",
                )

            case _:
                return Continue(None, self.split_epics)

    def split_epics(self) -> Continue:
        """Decompose the backlog into epics, and get that approved.

        The `for` is `epics_rework_count` + `guard_epics` + `incr_epics`; the
        `while` is a human at the gate sending the run back to `decompose` with
        a fresh rework budget — which is all `await_epics` zeroing the counter
        ever meant.
        """
        resolves = 0
        while True:
            self.agent(
                "prompts/decompose-epics.md",
                returns=DecomposeResult,
                args={"backlog": self.ctx.backlog_path, "epics_dir": self.ctx.epics_dir},
            )
            review = self._review_epics()

            for _ in range(MAX_REWORKS):
                if review.status != "needs_rework":
                    break
                self.agent(
                    "prompts/rework-epics.md",
                    returns=DecomposeResult,
                    args={
                        "backlog": self.ctx.backlog_path,
                        "epics_dir": self.ctx.epics_dir,
                        "review_notes": review.notes,
                    },
                )
                review = self._review_epics()

            if review.status == "approved":
                return Continue(review, self.next_epic)

            self._unblock(
                context_path=author_context(self.ctx),
                scope_dir=self.ctx.epics_dir,
                stage="epic-split",
                notes=review.notes,
                attempt=resolves,
            )
            resolves += 1

    def _review_epics(self) -> EpicReview:
        return self.agent(
            "prompts/review-epics.md",
            returns=EpicReview,
            args={"backlog": self.ctx.backlog_path, "epics_dir": self.ctx.epics_dir},
        )

    def next_epic(self) -> Continue:
        """Pick the next unauthored epic, or fall through to the closing checks.

        Split out from `author_epic` precisely because `check_coverage` needs
        to re-enter the authoring without re-selecting — and note that this is
        also where `cov_reworks` gets its default back, which is the whole of
        what `reset_cov_rework` was.
        """
        choice = self.call(select_epic, cfg=self.ctx)
        if not choice.epic:
            log.info("no epic left to author: %s", choice.reason)
            return Continue(choice, self.close)
        return Continue(choice, self.author_epic, epic=choice.epic)

    def author_epic(self, epic: str, cov_reworks: int = 0, rework_notes: str = "") -> Continue:
        """Write the epic doc, then split its seeds into stories.

        Re-entered by `check_coverage` when a review finds gaps, which is why
        `cov_reworks` and `rework_notes` are parameters with defaults: arriving
        from `next_epic` is arriving with a full budget and nothing to redo.
        """
        result = self._write_epic(epic)
        resolves = 0
        while result.status == "blocked":
            self._unblock(
                context_path=epic_dir(self.ctx, epic) / "context.md",
                scope_dir=epic_dir(self.ctx, epic),
                stage="write-epic",
                notes=result.notes,
                attempt=resolves,
            )
            resolves += 1
            result = self._write_epic(epic)

        split = self._split_stories(epic, rework_notes)
        resolves = 0
        while split.status == "blocked":
            self._unblock(
                context_path=epic_dir(self.ctx, epic) / "context.md",
                scope_dir=epic_dir(self.ctx, epic),
                stage="story-split",
                notes=split.notes,
                attempt=resolves,
            )
            resolves += 1
            split = self._split_stories(epic, rework_notes)

        if split.status == "standoff":
            # The split stage declines the coverage stage's rework request.
            # Neither agent can break the tie, so a human does.
            return Continue(
                split, self.check_coverage, epic=epic, cov_reworks=MAX_REWORKS
            )

        return Continue(split, self.next_story, epic=epic, cov_reworks=cov_reworks)

    def _write_epic(self, epic: str) -> WriteEpicResult:
        return self.agent(
            "prompts/write-epic.md",
            returns=WriteEpicResult,
            args={
                "epic": epic,
                "epic_dir": epic_dir(self.ctx, epic),
                "backlog": self.ctx.backlog_path,
                "features_dir": self.ctx.features_dir,
            },
        )

    def _split_stories(self, epic: str, rework_notes: str) -> SplitResult:
        # `rework_notes` was `{% if (cov_rework_count.value or 0) | int > 0 %}`:
        # Jinja reaching into a counter node's output to work out whether this
        # was a first pass or a retry. Here it is an argument, and the caller
        # got it from its own caller.
        return self.agent(
            "prompts/split-stories.md",
            returns=SplitResult,
            args={
                "epic": epic,
                "epic_dir": epic_dir(self.ctx, epic),
                "rework_notes": rework_notes,
            },
        )

    def next_story(self, epic: str, cov_reworks: int = 0) -> Continue:
        """Pick the next unauthored story in this epic, or check its coverage."""
        choice = self.call(select_story, cfg=self.ctx, epic=epic)
        if not choice.story_slug:
            log.info("epic %s: no story left (%s)", epic, choice.reason)
            return Continue(
                choice, self.check_coverage, epic=epic, cov_reworks=cov_reworks
            )
        return Continue(
            choice, self.write_story,
            epic=epic, story=choice.story_slug, cov_reworks=cov_reworks,
        )

    def write_story(
        self,
        epic: str,
        story: str,
        bullet_id: str = "",
        resolves: int = 0,
        cov_reworks: int = 0,
    ) -> Continue:
        """Mock the surface up, write the story, check it, rework it, repeat.

        The fat state: one story end to end, which is also the honest unit of
        work to lose to a crash. `range(MAX_REWORKS)` is `story_rework_count` +
        `guard_story` + `incr_story` — three nodes and a script. Re-entering
        this state restarts the range without saying so, which is exactly what
        `await_write_story` zeroing the counter did; `resolves` is the budget
        that must *not* reset on re-entry, so it is the one that travels.

        `cov_reworks` is read nowhere in here. It belongs to the loop between
        `author_epic` and `check_coverage`, and the story loop sits inside that
        loop, so it has to be carried across. That is the bill this design
        sends: a run-scoped counter costs a parameter in every state it passes
        through, where the run context bag charged nothing and lost track of
        who owned it. Two states of pass-through is a price worth seeing; if it
        were seven, that would be the design telling us the loop is wrong.
        """
        sdir = story_dir(self.ctx, epic, story)
        mockup = self.agent(
            "prompts/design-mockup.md",
            returns=MockupResult,
            args={
                "epic": epic,
                "story_slug": story,
                "story_dir": sdir,
                "features_dir": self.ctx.features_dir,
                "surface_manifest": self.ctx.surface_manifest,
                "mockup_dir": self.ctx.mockup_dir,
            },
        )

        written = self._write_story(epic, story, mockup.mockup)
        attempt = resolves
        while written.status == "blocked":
            self._unblock(
                context_path=sdir / "context.md",
                scope_dir=epic_dir(self.ctx, epic),
                stage="write-story",
                notes=written.notes,
                attempt=attempt,
            )
            attempt += 1
            written = self._write_story(epic, story, mockup.mockup)

        for rework in range(MAX_REWORKS):
            defect = self._story_defects(epic, story)
            if defect is None:
                return Continue(
                    written, self.story_feedback,
                    epic=epic, story=story, bullet_id=bullet_id,
                    cov_reworks=cov_reworks,
                )
            ledger = self.call(record_attempt, story_dir=sdir, label=rework, note=defect)
            self._rework_story(epic, story, validation_errors=defect, prior_attempts=ledger)

        # Reworking has stopped helping. Escalate, then write it again from the
        # top with the operator's answer in hand — `await_write_story` pointed
        # back at `write_story`, not at the rework loop.
        self._unblock(
            context_path=sdir / "context.md",
            scope_dir=epic_dir(self.ctx, epic),
            stage="write-story",
            notes=self._story_defects(epic, story) or "story could not be made to pass validation",
            attempt=attempt,
        )
        return Continue(
            None, self.write_story,
            epic=epic, story=story, bullet_id=bullet_id,
            resolves=attempt + 1, cov_reworks=cov_reworks,
        )

    def _write_story(self, epic: str, story: str, mockup_path: Path | None) -> WriteStoryResult:
        return self.agent(
            "prompts/write-story.md",
            returns=WriteStoryResult,
            args={
                "epic": epic,
                "story_path": story_path(self.ctx, epic, story),
                "story_slug": story,
                "story_dir": story_dir(self.ctx, epic, story),
                "features_dir": self.ctx.features_dir,
                "mockup_dir": self.ctx.mockup_dir,
                "mockup_path": mockup_path,
            },
        )

    def _rework_story(self, epic: str, story: str, **extra: str) -> WriteStoryResult:
        # `apply_story_feedback` was a second node pointing at this same prompt
        # with `validation_errors:` rendered empty and `operator_feedback:`
        # filled in. Same call, different argument.
        return self.agent(
            "prompts/rework-story.md",
            returns=WriteStoryResult,
            args={
                "epic": epic,
                "story_path": story_path(self.ctx, epic, story),
                "story_slug": story,
                "story_dir": story_dir(self.ctx, epic, story),
                "features_dir": self.ctx.features_dir,
                "mockup_dir": self.ctx.mockup_dir,
                **extra,
            },
        )

    def _story_defects(self, epic: str, story: str) -> str | None:
        """Structure, then grounding, then judgement — first failure wins.

        Three nodes and three branch nodes in the YAML, whose one consumer then
        rendered `{{ story_errors or audit_result.notes or story_grounding_errors }}`:
        a Jinja `or`-chain reconstructing which of the three had actually failed.
        """
        written = self.call(validate_story, story_dir=story_dir(self.ctx, epic, story))
        if not written.ok:
            return written.errors

        grounded = self.call(
            check_story_grounding, cfg=self.ctx, epic=epic, story_slug=story
        )
        if not grounded.ok:
            return grounded.errors

        audit = self.agent(
            "prompts/audit-story.md",
            returns=AuditResult,
            args={
                "epic": epic,
                "story_path": story_path(self.ctx, epic, story),
                "story_slug": story,
                "story_dir": story_dir(self.ctx, epic, story),
                "features_dir": self.ctx.features_dir,
            },
        )
        return audit.notes if audit.status == "failed" else None

    def story_feedback(
        self, epic: str, story: str, bullet_id: str = "", cov_reworks: int = 0
    ) -> Continue | Done:
        """Drain the operator's inbox, then move on.

        `cov_reworks` is pass-through here too — see `write_story`."""
        feedback = self.call(
            check_story_feedback, story_dir=story_dir(self.ctx, epic, story)
        )
        if feedback.present:
            self._rework_story(epic, story, operator_feedback=feedback.content)
            return Continue(
                feedback, self.write_story,
                epic=epic, story=story, bullet_id=bullet_id, cov_reworks=cov_reworks,
            )

        if self.mode == "story":
            # Faithful to the YAML: `story_prune -> done`, terminal. Note what
            # that skips — reconcile, integrity, `validate_artifacts`, the
            # commit and the PR. A single-story run leaves its work
            # uncommitted on the author branch.
            pruned = (
                self.call(prune_bullet, backlog=self.ctx.backlog_path, bullet_id=bullet_id)
                if bullet_id
                else None
            )
            return Done({"story": story, "pruned": pruned.removed if pruned else 0})

        return Continue(feedback, self.next_story, epic=epic, cov_reworks=cov_reworks)

    def check_coverage(self, epic: str, cov_reworks: int = 0) -> Continue:
        """Do this epic's stories actually cover its seeds?

        Mechanical check, then a judged one, sharing one rework budget — and
        the rework is *going back to the split stage*, which is why this state
        returns to `author_epic` instead of looping here.
        """
        mechanical = self.call(validate_coverage, cfg=self.ctx, epic=epic)
        if mechanical.ok:
            review = self.agent(
                "prompts/review-coverage.md",
                returns=CoverageReview,
                args={"epic": epic, "epic_dir": epic_dir(self.ctx, epic)},
            )
            if review.status == "ok":
                self.call(prune_backlog, cfg=self.ctx, epic=epic)
                return Continue(review, self.next_epic)
            notes, blocked = review.notes, review.status == "blocked"
        else:
            notes, blocked = mechanical.errors, False

        if not blocked and cov_reworks < MAX_REWORKS:
            return Continue(
                notes, self.author_epic,
                epic=epic, cov_reworks=cov_reworks + 1, rework_notes=notes,
            )

        self._unblock(
            context_path=epic_dir(self.ctx, epic) / "context.md",
            scope_dir=epic_dir(self.ctx, epic),
            stage="coverage",
            notes=notes,
            attempt=cov_reworks - MAX_REWORKS,
        )
        # `await_coverage` zeroed `cov_rework_count`; here that is a default
        # argument, which is to say: nothing.
        return Continue(notes, self.author_epic, epic=epic, rework_notes=notes)

    def close(self) -> Done:
        """Reconcile, check integrity, commit, and open the PR.

        Notice what is *not* in scope here: `epic`. The YAML's commit message
        rendered `{{ epic }}` at this point, which resolved to whatever
        `select_epic` last wrote — a value nobody chose. The message can only
        say what this state knows, which is the mode and the branch.
        """
        self._verify(verify_reconcile, "reconciliation", "prompts/resolve-operator.md")
        self._verify(verify_integrity, "integrity", "prompts/resolve-integrity.md")

        artifacts = self.call(validate_artifacts, cfg=self.ctx)
        if not artifacts.ok:
            # Commit anyway so the half-finished work is inspectable, but under
            # a message that says not to merge it — then fail the run.
            self.call(
                commit_author,
                cfg=self.ctx,
                message="author: INCOMPLETE — unwritten stories, do not merge",
            )
            raise WorkflowFailed(f"author artifacts incomplete:\n{artifacts.errors}")

        self.call(
            commit_author,
            cfg=self.ctx,
            message=(
                "author: survey intake and epic backlog authoring"
                if self.mode == "survey"
                else "author: epic backlog authoring"
            ),
        )
        pr = self.call(
            open_author_pr,
            cfg=self.ctx,
            base_branch=self.ctx.base_branch,
            author_branch=self.ctx.author_branch,
            title=f"author: {self.mode} run",
        )
        return Done({"pr": pr.url, "pr_state": pr.state})

    def _verify(self, check, stage: str, prompt: str) -> None:
        """`verify -> decide -> gate -> guard -> resolve -> decide -> incr` for
        reconcile and integrity alike: nine nodes each, one loop here."""
        report = self.call(check, cfg=self.ctx)
        resolves = 0
        while not report.ok:
            if self.operator_mode == "human" or resolves >= MAX_RESOLVES:
                break
            status = self.agent(
                prompt,
                returns=ResolveStatus,
                args={
                    "context_path": author_context(self.ctx),
                    "epics_dir": self.ctx.epics_dir,
                    "block_stage": stage,
                    "block_notes": report.errors,
                },
            )
            if status.decision == "escalated":
                break
            resolves += 1
            report = self.call(check, cfg=self.ctx)

        if not report.ok:
            self.call(
                scriptutil.await_operator,
                path=author_context(self.ctx),
                questions=report.errors,
            )

    def _unblock(
        self, *, context_path: Path, scope_dir: Path, stage: str, notes: str, attempt: int
    ) -> None:
        """`gate_* -> guard_*_resolve -> resolve_* -> incr_* -> await_*`: five
        nodes, repeated five times over, for a total of twenty-five.

        In `auto` mode an agent gets `MAX_RESOLVES` attempts at answering the
        block by writing into the context file; `await_operator` then either
        finds that answer and returns at once, or blocks for a human. In
        `human` mode we go straight to the wait.

        `attempt` is passed in rather than counted here, because whose budget
        it is differs: in `author_epic` it is a local, in `write_story` it is a
        state parameter that has to survive re-entry. Making the caller own it
        is what stops this method from needing state of its own.

        The five `resolve_*` agent nodes were one prompt with a different
        `block_stage:` string each — a parameter, not a node.
        """
        if self.operator_mode == "auto" and attempt < MAX_RESOLVES:
            self.agent(
                "prompts/resolve-operator.md",
                returns=ResolveStatus,
                args={
                    "context_path": context_path,
                    "epic_dir": scope_dir,
                    "block_stage": stage,
                    "block_notes": notes,
                },
            )

        # SUPERSEDED, and left standing on purpose. This blocking call is the
        # first rendering of the operator gate; the plan has since decided the
        # wait is a *transition* — `return Await(context_path, notes, <target>,
        # **params)` — which puts "blocked on a human, here, since then" in the
        # checkpoint instead of in a stack frame.
        #
        # Converting it is not a substitution. An `Await` can only be returned,
        # so it cannot live in a helper: every caller has to propagate it, which
        # splits the two states whose `while blocked:` loops call this. That is
        # the plan's "fat states are free right up until you need to suspend
        # inside one" bill, and this method is where it comes due.
        #
        # What *did* leave is the node's third argument. The YAML passed a
        # counter key so this node could zero it, because "a human just
        # answered, so give the agent its budget back" had nowhere else to live.
        # Here that reset is a state re-entered with the parameter at its
        # default — which survives the conversion unchanged.
        self.call(scriptutil.await_operator, path=context_path, questions=notes)


# ---------------------------------------------------------------------------
# The entry point, and the CLI it parses
# ---------------------------------------------------------------------------
#
# `workflow.main(Author)` is not a call to `Author`; it names the class the CLI
# starts at, and returns the console-script callable. Two front doors, same
# parser — one has the workflow name already bound:
#
#     workhorse run author  qa --run-id=test123 --params '{"story": "AUTH-12"}'
#     workhorse-author run  qa --run-id=test123 --params '{"story": "AUTH-12"}'
#
# The first resolves `author` through the `workhorse.workflows` entry-point
# group; the second is a `[project.scripts]` entry in the same distribution —
# one console script per workflow, not one distribution per workflow. Neither
# is the "real" one: the script is free once the module has a callable entry,
# and `workhorse run <name>` stays the way to reach a workflow whose command
# you have not learned yet.
#
#     workhorse-author run                       # the whole workflow, mode=epic
#     workhorse-author run --params '{"mode": "story", "epic": "auth",
#                                     "bullet": "B-12"}'
#     workhorse-author run surveyor --run-id=test123 \
#                                   --params rubric=docs/survey/rubric.md
#     workhorse-author resume --run-id=test123    # from the checkpoint on disk
#     workhorse-author dot [flow]                 # --dry-run, rendered
#
# The positional after `run` is a FLOW, exactly as `workhorse run coder qa` is
# today — and here that is not a mode the engine has to implement. A flow is a
# `Workflow` subclass, so running one standalone is `drive(Surveyor(**params))`:
# the same object, the same driver, the same checkpoint file as when `start()`
# reaches it through `self.handoff(Surveyor, ...)`. `add_flows` exists only to
# map the CLI token `surveyor` onto the class; the handoff needs no registry
# because it already holds the class.
#
# What changes is where `--params` lands. Today it is an untyped JSON bag merged
# into the run context, and the workflow's `vars:` are whatever survives. Here it
# binds to the model fields of whichever class the CLI is starting — `Author` for
# `run`, `Surveyor` for `run surveyor` — which makes the CLI the fourth front
# door onto the one validation the design already has:
#
#     transition  -> Continue.__init__ binds against the target state's signature
#     resume      -> the checkpoint's params are coerced against that signature
#     handoff     -> the sub-workflow's own model validates its args
#     the CLI     -> the entry class's model validates --params
#
# So `--params mode=stroy` is a parse error naming the four legal values, where
# today the typo reaches `decide_mode`, misses every case, and takes `default:`
# — an epic-mode run the operator asked for by accident. Same for
# `--params epics_dir=docs/epics`, which arrives as a `Path` because the field
# says `Path`, not because a node remembered to convert it. That is also why
# `k=v` pairs are accepted beside inline JSON: with typed fields there is a
# declared target to coerce a bare string toward, so the JSON quoting is no
# longer load-bearing for anything but nested values.
#
# `--run-id` keeps its current meaning — it names the stable run dir, and
# defaults to a digest of `--params` so two targets never collide on one
# checkpoint. Unchanged, and deliberately: it is the identity half of resume,
# and this design changes only what a checkpoint *contains*.

workflow = Workflow()
workflow.add_blueprints(scriptutil.blueprint, blueprint)
workflow.add_flows(Surveyor, ParitySurveyor)
main = workflow.main(Author)

if __name__ == "__main__":
    raise SystemExit(main())

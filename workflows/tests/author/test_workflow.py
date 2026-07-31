"""End-to-end drives of the author workflow (`author/workflow.py`).

Nothing is stubbed except the agent turn. `load_config`, `branch_author`, `seed_story`,
`select_epic`, `select_story`, `validate_story`, `check_story_grounding`, `record_attempt`,
`check_story_feedback`, `validate_coverage`, `prune_backlog`, `prune_bullet`,
`verify_reconcile`, `verify_integrity`, `validate_artifacts`, `commit_author` and
`open_author_pr` all run for real against the `repo` fixture — so a drive here exercises
ostler's real graph, the two deterministic story gates, the coverage gate, the whole-graph
gates and the git tail.

The agent seam is patched where the engine reads it
(`RunEnv.agent_runner`) and the stub **writes the artifacts its
reply claims to have written**: `decompose-epics` creates the epic and queues it,
`split-stories` registers the stories, `write-story` writes the story document. The
authoring state lives in those files rather than in the machine, so an agent that only
replied would leave `select_epic` and `validate_story` with nothing to read.

What the port could get wrong, and what is therefore under test here:

* `handoff`, which `research` never touched: `survey` mode runs the surveyor sub-flow to
  completion on the parent's env and then authors the backlog the sub-flow wrote. The
  sub-flows' own machinery is covered in `flows/test_surveyor.py`; what is covered here is
  the hand-off itself — child prompt paths resolving against the parent's directory, and
  the parent continuing from the child's artifacts.
* the bounded rework loops and their give-up arms — epic review, story rework — each
  ending somewhere other than "stuck";
* the operator gates, the other shape `research` never touched. The YAML sent every gate
  into `await_*` unconditionally and let `await-operator.py` decide whether to wait by
  reading a `STATUS:` line; the driver's `Await` waits unconditionally, so the port
  branches on the resolver's reply instead. Both arms are driven below — an autonomous
  resolution must NOT block, and `operator_mode=human` (and an escalation) must.
* resume, which is why the checkpoint lands before the agent turn: a run killed while
  writing the second story re-writes that story and no earlier one.
* the git tail: `epic` mode commits and `story` mode deliberately does not.
"""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from _fakes import StubRunner
from ostler import Ostler
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import activity as pyflow_activity
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.driver import drive, read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows import author
from workhorse_workflows.author.nodes.survey import record_slug
from workhorse_workflows.author.workflow import Author

BACKLOG = "docs/backlog.md"
EPICS = "docs/epics"
EPIC = "accounts"
EPIC_DIR = f"{EPICS}/{EPIC}"
#: The run-wide operator context file — `paths.author_context(epics_dir)`.
CONTEXT = f"{EPICS}/_author-context.md"

#: The two backlog bullets the scripted decomposition turns into seeds. The `sourceBullet`
#: recorded on each seed is the verbatim line, which is what `prune_backlog` matches on.
SEEDS = {
    "b1": "[b1] Users can sign in with an email and a password",
    "b2": "[b2] Users can reset a forgotten password",
}
#: What the scripted `split-stories` registers, one story per seed.
STORIES = (
    ("01-sign-in", "Sign in", "b1"),
    ("02-reset-password", "Reset password", "b2"),
)
SLUGS = [slug for slug, _, _ in STORIES]

# The surveyor sub-flow's paths, for the `survey` mode hand-off.
SURVEY_DIR = "docs/survey"
RUBRIC = f"{SURVEY_DIR}/rubric.md"
RULES = f"{SURVEY_DIR}/units.yml"
INVENTORY = f"{SURVEY_DIR}/inventory.json"
FINDINGS = f"{SURVEY_DIR}/findings"
PARTITION = f"{SURVEY_DIR}/partition.yaml"
BUTTON = "src/components/button"
CLUSTER = "missing-accessible-name"


# --------------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _no_github(monkeypatch: pytest.MonkeyPatch) -> None:
    """No token and no configured base branch, so the git tail is deterministic.

    `open_author_pr` resolves a token from the environment; with one present on the
    developer's machine it would try to reach GitHub for a temp repo, and the test would
    assert a different thing there than in CI. Absent, it takes its `_skipped` arm.
    """
    for var in ("GH_TOKEN", "GITHUB_TOKEN", "WORKHORSE_GIT_TOKEN", "REPO_BRANCH"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def backlogged(repo: Path, write: Callable[[Path, str], Path]) -> Path:
    """A repo with a two-bullet backlog and nothing else: no epics, no OKF book.

    Committed, because both git nodes and `verify_reconcile` read a real repository — and
    because a committed baseline with no `docs/epics` in it is the normal state of a first
    author run, which is what makes `verify_reconcile` report `skipped` rather than a
    defect.
    """
    write(repo / BACKLOG, "# Backlog\n\n## Scope items\n\n" + "".join(f"- {b}\n" for b in SEEDS.values()))
    _commit(repo, "seed")
    return repo


@pytest.fixture
def with_epic(backlogged: Path) -> Path:
    """`backlogged` plus one already-authored epic, for `story` mode.

    Story mode appends to an epic that exists and never creates one, so the epic is the
    fixture rather than something the drive produces.
    """
    okf = Ostler(backlogged)
    okf.create_epic(EPIC, "Accounts")
    okf.todo_add(EPIC)
    _commit(backlogged, "epic scaffold")
    return backlogged


def _commit(repo: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(
        ["git", "commit", "-qm", message], cwd=repo, check=True, stdout=subprocess.DEVNULL
    )


def _subject(repo: Path) -> str:
    """HEAD's commit subject."""
    out = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=repo, check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


def _commit_count(repo: Path) -> int:
    out = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    )
    return int(out.stdout.strip())


def _bullets(repo: Path) -> list[str]:
    """The backlog's bullet lines, to see what the coverage tail pruned."""
    return [
        line.strip()
        for line in (repo / BACKLOG).read_text().splitlines()
        if line.strip().startswith("- ")
    ]


def _stories(repo: Path) -> dict[str, bool]:
    """`{slug: authored}` for every story ostler can see."""
    return {str(s["slug"]): bool(s.get("authored")) for s in Ostler(repo).list("story")}


# ------------------------------------------------------------------ what the agent writes

_BODY = """# Story: {title}

## Context

{title} is one of the account surfaces this epic covers. The screen exists in the web app
already, so this story adds behaviour to it rather than a new surface.

## Acceptance Criteria

- Given a visitor on the {title} form, when they submit valid input, the app confirms it.
- Given invalid input, the form reports what is wrong and stays where it is.

## Implementation Status

- **Status**: Not started
"""

_UNWRITTEN_BODY = """# Story: {title}

## Context

## Acceptance Criteria

- Given a visitor, the app behaves.

## Implementation Status

- **Status**: Not started
"""


def _write_story_doc(path: Path, title: str, *, authored: bool = True) -> None:
    """Fill the scaffold `create_story` left, keeping its front-matter verbatim.

    The id in that front-matter is ostler's, not ours to mint — and `authored=False`
    reproduces a story whose `## Context` the writer left empty, which is exactly what
    `validate_story` exists to catch.
    """
    front, _, _rest = path.read_text(encoding="utf-8").partition("\n---\n")
    body = (_BODY if authored else _UNWRITTEN_BODY).format(title=title)
    path.write_text(f"{front}\n---\n\n{body}", encoding="utf-8")


def _rules() -> str:
    """The enumeration rules the surveyor's planner writes. JSON is valid YAML."""
    return json.dumps({"rules": [{"kind": "folder", "glob": "src/components/*"}]}, indent=2) + "\n"


def _record(unit_id: str, kind: str = "folder") -> str:
    """One survey finding record, as the surveyor's assessor writes it."""
    front = {
        "type": "survey-finding",
        "unit": unit_id,
        "kind": kind,
        "status": "assessed",
        "findings": [
            {
                "description": f"{unit_id} renders an icon-only control with no name",
                "remediation_pattern": CLUSTER,
                "effort": "small",
                "evidence": f"{unit_id}/index.tsx:1 — no aria-label on the button",
            }
        ],
    }
    return f"---\n{json.dumps(front, indent=2)}\n---\n\n# Survey finding: {unit_id}\n"


def _partition(repo: Path) -> str:
    """One mechanical cluster over every assessed unit."""
    data = json.loads((repo / INVENTORY).read_text())
    units = [str(u["id"]) for u in data["units"] if u.get("status") == "assessed"]
    return json.dumps(
        {
            "clusters": [
                {
                    "id": CLUSTER,
                    "title": "Give every icon-only control an accessible name",
                    "remediation_pattern": CLUSTER,
                    "strategy": "mechanical",
                    "order": 1,
                    "units": units,
                    "notes": "One checklist story; trivial per unit.",
                }
            ]
        },
        indent=2,
    )


class _Agent:
    """A scripted stand-in for every one of the workflow's agent turns.

    It dispatches on the prompt's filename — the same key the engine derives its node id
    from, and the same key the registry's dry-run stubs use — and every handler leaves
    behind the artifact the next deterministic node reads.

    The knobs are the graph's branches: `review_epics` scripts the epic reviewer's verdicts
    in order, `unwritten` makes the story writer leave a section empty (the structural
    gate's failing arm), `fail_audit` fails the auditor for named stories,
    `coverage_verdicts` scripts the coverage reviewer, `feedback` drops an operator note
    into a story's inbox mid-run, `escalate` makes the operator stand-in hand the block to
    a human, and `explode` raises instead of writing a story — a run killed mid-turn.
    """

    def __init__(
        self,
        repo: Path,
        *,
        review_epics: list[str] | None = None,
        coverage_verdicts: list[str] | None = None,
        unwritten: set[str] | None = None,
        fail_audit: set[str] | None = None,
        feedback: dict[str, str] | None = None,
        escalate: bool = False,
        explode: set[str] | None = None,
    ) -> None:
        self.repo = repo
        self.review_epics = review_epics or ["approved"]
        self.coverage_verdicts = coverage_verdicts or ["ok"]
        self.unwritten = set(unwritten or ())
        self.fail_audit = set(fail_audit or ())
        self.feedback = dict(feedback or {})
        self.escalate = escalate
        self.explode = set(explode or ())
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []
        self.cwds: list[str] = []

    # -- the seam ---------------------------------------------------------

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        self.args.append(data)
        self.cwds.append(str(node.cwd))
        handler = getattr(self, f"_{stem.replace('-', '_')}")
        return f"(scripted) {node.prompt}", handler(data, self.counts()[stem])

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for s, a in zip(self.calls, self.args, strict=True) if s == stem]

    # -- the epic split ---------------------------------------------------

    def _decompose_epics(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Create the epic, queue it, and record one seed per backlog bullet."""
        okf = Ostler(self.repo)
        if not (self.repo / EPIC_DIR / "epic.md").is_file():
            okf.create_epic(EPIC, "Accounts")
            okf.todo_add(EPIC)
        for seed_id, text in SEEDS.items():
            okf.add_seed(EPIC, seed_id, status="researched", summary=text,
                         meta={"sourceBullet": text})
        return {"status": "complete", "notes": f"one epic from {len(SEEDS)} bullet(s)"}

    def _rework_epics(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Same product as the decomposition, which is why it re-runs it."""
        return self._decompose_epics(data, nth)

    def _review_epics(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        verdict = self.review_epics[min(nth, len(self.review_epics)) - 1]
        return {"status": verdict, "notes": "" if verdict == "approved" else "one epic is two"}

    # -- the per-epic loop ------------------------------------------------

    def _write_epic(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"status": "complete", "notes": "seeds already recorded"}

    def _split_stories(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Register one story per seed. Idempotent: the coverage loop re-enters here."""
        okf = Ostler(self.repo)
        existing = {str(s["slug"]) for s in okf.list("story", epic=EPIC)}
        for slug, title, seed in STORIES:
            if slug not in existing:
                okf.create_story(EPIC, slug, title, covers=[seed])
        return {"status": "complete", "notes": f"{len(STORIES)} stories"}

    # -- the per-story loop -----------------------------------------------

    def _design_mockup(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        # A story on an existing surface: the mockup stage is a pass-through, and
        # `write_story` falls back to the feature docs.
        return {"status": "skipped", "surface": "", "mockup": "", "notes": "existing surface"}

    def _write_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        slug = str(data["story_slug"])
        if slug in self.explode:
            raise RuntimeError(f"killed while writing {slug}")
        title = dict((s, t) for s, t, _ in STORIES).get(slug, slug)
        _write_story_doc(self.repo / data["story_path"], title, authored=slug not in self.unwritten)
        return {"status": "written", "notes": "acceptance criteria and context"}

    def _rework_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Rewrite the story properly — the rework is what clears whichever gate failed."""
        slug = str(data["story_slug"])
        # A rework fixes what the structural gate flagged. It does *not* clear a standing
        # audit objection — that is what the rework budget is for, and what makes the
        # give-up arm reachable.
        self.unwritten.discard(slug)
        title = dict((s, t) for s, t, _ in STORIES).get(slug, slug)
        _write_story_doc(self.repo / data["story_path"], title)
        return {"status": "written", "notes": "rewritten"}

    def _audit_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        slug = str(data["story_slug"])
        note = self.feedback.pop(slug, "")
        if note:
            # An operator dropped a note into the story's inbox while the run was busy.
            inbox = self.repo / data["story_dir"] / "feedback.md"
            inbox.parent.mkdir(parents=True, exist_ok=True)
            inbox.write_text(f"STATUS: NEW\n\n{note}\n")
        if slug in self.fail_audit:
            return {"status": "failed", "notes": f"{slug} cannot be built as written"}
        return {"status": "passed", "notes": "a coder could build this"}

    # -- the epic's coverage ----------------------------------------------

    def _review_coverage(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        verdict = self.coverage_verdicts[min(nth, len(self.coverage_verdicts)) - 1]
        return {"status": verdict, "notes": "" if verdict == "ok" else "the reset flow is unclaimed"}

    # -- the operator gates -----------------------------------------------

    def _resolve_operator(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if self.escalate:
            return {"decision": "escalated", "notes": "needs a product call"}
        if data["block_stage"] == "epic-split":
            # What the prompt tells it to do: answer in the context file the next pass reads.
            self.review_epics = ["approved"]
        return {"decision": "answered", "notes": f"resolved {data['block_stage']}"}

    def _resolve_integrity(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"decision": "answered", "notes": "relinked"}

    # -- the surveyor sub-flow's turns ------------------------------------

    def _plan_units(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        (self.repo / data["rules_path"]).write_text(_rules())
        return {"status": "complete", "notes": "one unit per component folder"}

    def _assess_unit(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        path = self.repo / data["record_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_record(str(data["unit_id"]), str(data.get("unit_kind", ""))))
        return {"status": "assessed", "notes": "one finding"}

    def _partition_findings(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        (self.repo / data["partition_path"]).write_text(_partition(self.repo))
        return {"status": "complete", "notes": "one mechanical cluster"}


def _env(tmp: Path, *, run_dir: Path | None = None) -> RunEnv:
    writer = (
        ArtifactWriter.resume(run_dir)
        if run_dir is not None
        else ArtifactWriter("author", tmp / "runs", run_id="t")
    )
    return RunEnv(
        writer=writer,
        workflow_dir=Path(author.__file__).parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(backend_factory=lambda cli=None: None),
    )


def _drive(env: RunEnv, agent: _Agent, **inputs: Any) -> Any:
    return drive(Author(**inputs), replace(env, agent_runner=StubRunner(agent)))


# --------------------------------------------------------------------------- epic mode


def test_epic_mode_authors_the_backlog_and_commits_it(backlogged: Path, tmp_path: Path) -> None:
    """The straight-through run: one epic, two stories, both gates green, then the git tail.

    Every count below is a node the YAML ran exactly once per pass too, and the artifacts
    are the YAML's artifacts: the epic and its seeds in `epic.md`, an authored `story.md`
    per story, the consumed bullets gone from the backlog, one commit on the author branch,
    and no PR because there is no token.
    """
    agent = _Agent(backlogged)
    result = _drive(_env(tmp_path), agent)

    assert agent.counts() == {
        "decompose-epics": 1,
        "review-epics": 1,
        "write-epic": 1,
        "split-stories": 1,
        "design-mockup": 2,
        "write-story": 2,
        "audit-story": 2,
        "review-coverage": 1,
    }, agent.counts()

    # Both stories authored, for real, as ostler reads them.
    assert _stories(backlogged) == {slug: True for slug in SLUGS}
    # The whole-graph gate ran on a clean graph: no error-level findings left.
    assert not [f for f in Ostler(backlogged).doctor()["findings"] if f["severity"] == "error"]

    # The coverage tail pruned the two bullets the epic consumed, and left the heading.
    assert _bullets(backlogged) == []
    assert "## Scope items" in (backlogged / BACKLOG).read_text()

    # The git tail: committed on the run's own branch, PR skipped for want of a token.
    assert _subject(backlogged) == "author: epic backlog authoring"
    assert result.author_pr == "skipped", result
    assert result.pr_skip_reason == "no GitHub token is configured", result

    # Every turn ran in the repo, not in the run directory.
    assert set(agent.cwds) == {str(backlogged)}


def test_a_story_that_is_not_a_contract_is_reworked_against_the_gate(
    backlogged: Path, tmp_path: Path
) -> None:
    """`validate_story` is deterministic, so the rework loop needs no scripted verdict.

    The writer leaves `## Context` empty on the first story; the structural gate fails it,
    `record_attempt` opens the ledger, and the reworker rewrites it. The ledger is the
    point of `record_attempt`: a bounded loop that carried only the latest failure would
    let the reworker re-try an approach that already failed.
    """
    agent = _Agent(backlogged, unwritten={"01-sign-in"})
    _drive(_env(tmp_path), agent)

    assert agent.counts()["write-story"] == 2, agent.counts()
    assert agent.counts()["rework-story"] == 1, agent.counts()
    ledger = backlogged / EPIC_DIR / "stories/01-sign-in/attempts.md"
    assert "## Attempt 0" in ledger.read_text()
    assert agent.args_for("rework-story")[0]["validation_errors"], agent.args_for("rework-story")[0]
    assert _stories(backlogged) == {slug: True for slug in SLUGS}


def test_an_operator_note_dropped_mid_run_reworks_the_story_once(
    backlogged: Path, tmp_path: Path
) -> None:
    """`check_story_feedback` never blocks, and consuming the inbox is what bounds it.

    The note is dropped while the auditor is running, so it is there when
    `story_feedback` polls. Reading it marks the file `CONSUMED`, so the story is reworked
    exactly once no matter how many laps the loop takes afterwards.
    """
    agent = _Agent(backlogged, feedback={"01-sign-in": "call it 'sign in', never 'log in'"})
    _drive(_env(tmp_path), agent)

    assert agent.counts()["rework-story"] == 1, agent.counts()
    note = agent.args_for("rework-story")[0]
    assert "never 'log in'" in note["operator_feedback"], note
    # The operator's note is the work; there is no validation failure to carry.
    assert note["validation_errors"] == "", note
    inbox = (backlogged / EPIC_DIR / "stories/01-sign-in/feedback.md").read_text()
    assert "STATUS: CONSUMED" in inbox, inbox
    # Consumed, so the second pass through `story_feedback` found nothing.
    assert agent.counts()["audit-story"] == 3, agent.counts()


def test_a_coverage_gap_re_enters_the_split_with_the_worklist(
    backlogged: Path, tmp_path: Path
) -> None:
    """The coverage loop's notes travel to `split_stories` as its `rework_notes`.

    That parameter is the port's answer to a var that still held the *previous* epic's
    verdict on a fresh entry: only the edge that actually has notes passes them, so the
    first split sees a blank worklist and the reworked one sees the gap.
    """
    agent = _Agent(backlogged, coverage_verdicts=["gaps", "ok"])
    _drive(_env(tmp_path), agent)

    assert agent.counts()["split-stories"] == 2, agent.counts()
    first, second = agent.args_for("split-stories")
    assert first["rework_notes"] == "", first
    assert "reset flow" in second["rework_notes"], second
    assert agent.counts()["review-coverage"] == 2, agent.counts()


# ------------------------------------------------------------------- the operator gates


def test_an_epic_review_that_will_not_converge_reaches_the_resolver(
    backlogged: Path, tmp_path: Path
) -> None:
    """Three reworks, then the operator stand-in — and the resolver's answer is re-verified.

    `resolve_epics` re-enters `split_epics` rather than trusting the reply: the split and
    the review both re-read the context file the resolver just answered. Nothing blocks,
    because the resolver answered — which is the arm the YAML could only express by having
    `await-operator.py` read a `STATUS:` line and return.
    """
    agent = _Agent(backlogged, review_epics=["needs_rework"] * 4)
    _drive(_env(tmp_path), agent)

    assert agent.counts()["rework-epics"] == 3, agent.counts()
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    # The resolver's answer sent the run back through the split, not past it.
    assert agent.counts()["decompose-epics"] == 2, agent.counts()
    assert agent.counts()["review-epics"] == 5, agent.counts()
    assert agent.args_for("resolve-operator")[0]["block_stage"] == "epic-split"
    assert _subject(backlogged) == "author: epic backlog authoring"


def test_operator_mode_human_sends_the_block_straight_to_the_context_file(
    backlogged: Path, tmp_path: Path
) -> None:
    """`human` skips the resolver entirely and waits on the file.

    The wait is the driver's `Await`: it writes the questions to the context file,
    checkpoints, and polls that path's mtime. Patching `poll_until_touched` is the
    operator answering — and the autonomous arms above are proved by the *absence* of that
    patch, since a real wait would hang the suite.
    """
    seen: list[str] = []

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text())

    agent = _Agent(backlogged, review_epics=["blocked", "approved"])
    with patch.object(pyflow_driver, "poll_until_touched", answered):
        _drive(_env(tmp_path), agent, operator_mode="human")

    assert agent.counts()["resolve-operator"] == 0, agent.counts()
    assert agent.counts()["rework-epics"] == 0, agent.counts()
    assert seen == ["one epic is two"], seen
    assert (backlogged / CONTEXT).is_file()
    # The gate looped back into the split, so the run finished on the second review.
    assert agent.counts()["review-epics"] == 2, agent.counts()


def test_an_escalated_story_block_waits_on_the_story_context(
    backlogged: Path, tmp_path: Path
) -> None:
    """The story gate's other arm: the resolver declines, so a human is waited on.

    The rework budget is spent first (three laps against a failing auditor), then the gate
    hands the block to the resolver, which escalates — and the wait lands on the *story's*
    context file, not the run-wide one.
    """
    seen: list[Path] = []

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path)
        # What a human does at this gate: fix the story's inputs. Here, drop the objection.
        agent.fail_audit.clear()

    agent = _Agent(backlogged, fail_audit={"01-sign-in"}, escalate=True)
    with patch.object(pyflow_driver, "poll_until_touched", answered):
        _drive(_env(tmp_path), agent)

    assert seen == [backlogged / EPIC_DIR / "stories/01-sign-in/context.md"], seen
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    # Three reworks, then the gate: the fourth audit is the one that gave up.
    assert agent.counts()["rework-story"] == 3, agent.counts()
    assert _stories(backlogged) == {slug: True for slug in SLUGS}


# --------------------------------------------------------------------------- story mode


def test_story_mode_authors_one_bullet_and_does_not_commit(
    with_epic: Path, tmp_path: Path
) -> None:
    """One bullet into an existing epic, and it ends *without* committing.

    `decide_story_loop` routed `story` to `story_prune`, whose `next` is the `done`
    terminal, so the story arm of the commit-message builder is unreachable in the YAML.
    The port reproduces that rather than quietly fixing it — see the progress ledger.
    """
    before = _commit_count(with_epic)
    agent = _Agent(with_epic)
    result = _drive(_env(tmp_path), agent, mode="story", epic=EPIC, bullet="b1")

    # No epic split, no coverage tail: story mode enters at the story loop and leaves it.
    assert agent.counts() == {
        "design-mockup": 1,
        "write-story": 1,
        "audit-story": 1,
    }, agent.counts()

    stories = _stories(with_epic)
    assert list(stories) == ["b1-users-can-sign-in-with-an-email-and-a-password"], stories
    assert all(stories.values()), stories
    # The bullet it consumed is pruned; the other one is still work.
    assert _bullets(with_epic) == [f"- {SEEDS['b2']}"]
    assert result.removed == 1, result
    assert _commit_count(with_epic) == before, "story mode must not commit"


def test_story_mode_refuses_an_epic_that_does_not_exist(backlogged: Path, tmp_path: Path) -> None:
    """`seed_story` never scaffolds an epic — a missing one is a hard, actionable failure."""
    from workhorse.pyflow import WorkflowFailed

    with pytest.raises(WorkflowFailed, match="does not exist"):
        _drive(_env(tmp_path), _Agent(backlogged), mode="story", epic="nope", bullet="b1")


# ------------------------------------------------------------------------------- handoff


def test_survey_mode_runs_the_surveyor_then_authors_what_it_found(
    backlogged: Path, tmp_path: Path, write: Callable[[Path, str], Path]
) -> None:
    """`handoff`: the sub-flow runs on the parent's env, and the parent reads its output.

    The surveyor's own machinery is covered in `flows/test_surveyor.py`. What this proves
    is the hand-off: the child's prompts (`prompts/surveyor/*.md`) resolve against the
    *parent's* workflow directory, the child's nodes and agent turns run under the parent's
    run directory, and `split_epics` then decomposes the backlog the child wrote — the
    surveyor's whole purpose being to produce author's input.
    """
    write(backlogged / RUBRIC, "# Accessibility rubric\n\nEvery control needs a name.\n")
    write(backlogged / BUTTON / "index.tsx", "export const Button = () => <button />\n")
    _commit(backlogged, "a rubric and one component")

    agent = _Agent(backlogged)
    _drive(_env(tmp_path), agent, mode="survey")

    # The child's three turns, then the parent's.
    assert agent.counts()["plan-units"] == 1, agent.counts()
    assert agent.counts()["assess-unit"] == 1, agent.counts()
    assert agent.counts()["partition-findings"] == 1, agent.counts()
    assert agent.counts()["decompose-epics"] == 1, agent.counts()

    # The child's artifacts are on disk, and its bullets are in the parent's backlog.
    assert (backlogged / RULES).is_file()
    assert (backlogged / INVENTORY).is_file()
    assert (backlogged / FINDINGS / f"{record_slug(BUTTON)}.md").is_file()
    assert (backlogged / PARTITION).is_file()
    assert any(CLUSTER in line for line in (backlogged / BACKLOG).read_text().splitlines())

    # And the run went on to author it, under the survey commit message.
    assert _subject(backlogged) == "author: survey intake and epic backlog authoring"
    assert _stories(backlogged) == {slug: True for slug in SLUGS}


# -------------------------------------------------------------------------------- resume


def test_a_run_killed_mid_story_resumes_on_that_story_alone(
    backlogged: Path, tmp_path: Path
) -> None:
    """The story loop's state is the story documents, not the machine.

    So the checkpoint written *before* the agent turn is enough: the resumed run re-writes
    the story that was in flight and no earlier one, because the earlier one is already
    authored on disk and `select_story` skips it. This is the YAML's resume behavior — its
    `refuel` node re-entered the same way — reproduced without a gas tank.
    """
    first = _Agent(backlogged, explode={"02-reset-password"})
    env = _env(tmp_path)
    run_dir = env.writer.run_dir
    with pytest.raises(RuntimeError, match="killed while writing 02-reset-password"):
        _drive(env, first)

    assert first.counts()["write-story"] == 2, first.counts()
    assert _stories(backlogged) == {"01-sign-in": True, "02-reset-password": False}

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "write_story", resume
    assert resume.params["story_slug"] == "02-reset-password", resume.params
    assert resume.flow == "Author", resume

    second = _Agent(backlogged)
    result = drive(
        Author(**resume.inputs),
        replace(_env(tmp_path, run_dir=run_dir), agent_runner=StubRunner(second)),
        resume,
    )

    # Nothing upstream of the story re-ran: not the split, not this story's mockup.
    assert second.counts() == {
        "write-story": 1,
        "audit-story": 1,
        "review-coverage": 1,
    }, second.counts()
    assert _stories(backlogged) == {slug: True for slug in SLUGS}
    assert result.author_pr == "skipped", result


# -------------------------------------------------------------------------------- labels


def test_the_labels_name_the_story_and_the_epic(backlogged: Path, tmp_path: Path) -> None:
    """The YAML's `labels:` block read `get_node_output('select_story', …)`; here
    `labels()` reads `self.output(select_story)` and takes no parameters.

    Before the first pick there is no output to read, and that is the normal state of a
    run's first transitions — the guard against `NodeNotRunError` is what makes those
    label-less transitions rather than crashed ones.
    """
    seen: list[dict[str, str]] = []
    real_rebase = pyflow_activity.ActivityLog.rebase

    def capture(self: Any, labels: dict[str, str]) -> Any:
        seen.append(dict(labels))
        return real_rebase(self, labels)

    with patch.object(pyflow_activity.ActivityLog, "rebase", capture):
        _drive(_env(tmp_path), _Agent(backlogged))

    assert seen[0] == {}, seen[0]
    stamped = [labels for labels in seen if labels.get("work_id")]
    assert stamped, seen
    # The epic is the label until a story is picked, which is what the YAML rendered too —
    # and `progress` is absent rather than blank, because the driver drops empty values.
    assert stamped[0] == {"work_id": EPIC, "epic": EPIC}, stamped[0]
    assert {labels["work_id"] for labels in stamped} == {EPIC, *SLUGS}, stamped
    # `progress` is the worklist's own count, so a dashboard can read it without knowing
    # anything about authoring.
    assert any(labels.get("progress") for labels in stamped), stamped
    # Unprefixed, unlike the YAML engine's `wf.work_id`.
    assert not any(k.startswith("wf.") for labels in seen for k in labels), seen

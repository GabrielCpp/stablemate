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
import logging
import subprocess
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from _fakes import StubRunner
from ostler import Ostler, markdown
from workhorse import inbox
from workhorse.artifacts import ArtifactWriter
from workhorse.cli.inbox import INBOX_FILE
from workhorse.config_run import RunConfig
from workhorse.pyflow import activity as pyflow_activity
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.driver import drive, read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows import author
from workhorse_workflows.author.nodes.artifacts import validate_artifacts
from workhorse_workflows.author.nodes.epics import select_epic
from workhorse_workflows.author.nodes.stories import prune_bullet
from workhorse_workflows.author.epic_edit import EpicEdit
from workhorse_workflows.author.shared.survey import record_slug
from workhorse_workflows.author.story_edit import StoryEdit
from workhorse_workflows.author.workflow import Author

BACKLOG = "docs/backlog.md"
EPICS = "docs/epics"
EPIC = "accounts"
SECOND_EPIC = "profiles"
#: ostler numbers epic directories in creation order, so the folder is `0001-accounts` — the
#: name the run carries once `select_epic` has resolved the queue entry. Every ostler call
#: still takes the bare `EPIC` slug.
EPIC_NAME = f"0001-{EPIC}"
SECOND_EPIC_NAME = f"0002-{SECOND_EPIC}"
EPIC_DIR = f"{EPICS}/{EPIC_NAME}"
SECOND_EPIC_DIR = f"{EPICS}/{SECOND_EPIC_NAME}"
#: The run-wide operator context file — `paths.author_context(epics_dir)`.
CONTEXT = f"{EPICS}/_author-context.md"

#: The two backlog bullets the scripted decomposition turns into seeds. The `sourceBullet`
#: recorded on each seed is the verbatim line, which is what `prune_backlog` matches on.
SEEDS = {
    "b1": "[b1] Users can sign in with an email and a password",
    "b2": "[b2] Users can reset a forgotten password",
}
#: Supporting backlog context is prose rather than a bullet, so intake does not turn it into work.
SURFACE = "**api** is the only surface and the only writer of stored data."
#: What the scripted `split-stories` registers, one story per seed.
STORIES = (
    ("01-sign-in", "Sign in", "b1"),
    ("02-reset-password", "Reset password", "b2"),
)
SECOND_STORIES = (("01-edit-profile", "Edit profile", "p1"),)
SLUGS = [slug for slug, _, _ in STORIES]
SECOND_SLUGS = [slug for slug, _, _ in SECOND_STORIES]

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
    write(
        repo / BACKLOG,
        f"# Backlog\n\nSurfaces this app ships:\n\n{SURFACE}\n\n## Scope items\n\n"
        + "".join(f"- {b}\n" for b in SEEDS.values()),
    )
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


def _milestone(
    repo: Path,
    *epics: str,
    source_items: tuple[str, ...] = (),
) -> None:
    lines = [
        "---",
        "type: milestone",
        "id: account-mvp",
        "title: Account MVP",
        "status: planned",
        "dependsOn: []",
        *(
            ["sourceItems:", *(f"  - {item}" for item in source_items)]
            if source_items
            else []
        ),
        "epics:",
        *(f"  - {epic}" for epic in epics),
        "---",
        "# Account MVP",
        "",
        "A visitor can access and recover their account.",
    ]
    path = repo / "docs/milestones/account-mvp.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# ------------------------------------------------------------------ what the agent writes

_BODY = """# Story: {title}

## Dependencies

(none)

## Fixtures

(none)

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

## Dependencies

(none)

## Fixtures

(none)

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
    gate's failing arm), `fail_audit` fails the auditor for named stories, `audit_replies` returns a
    verbatim audit reply for a named story,
    `coverage_verdicts` scripts the coverage reviewer, `feedback` drops an operator note
    into the run's inbox mid-run (requires `run_dir`), `escalate` makes the operator
    stand-in hand the block to a human, and `explode` raises instead of writing a story —
    a run killed mid-turn.
    """

    def __init__(
        self,
        repo: Path,
        *,
        review_epics: list[str] | None = None,
        coverage_verdicts: list[str] | None = None,
        two_epics: bool = False,
        unwritten: set[str] | None = None,
        fail_audit: set[str] | None = None,
        audit_replies: dict[str, dict[str, Any]] | None = None,
        feedback: dict[str, str] | None = None,
        run_dir: Path | None = None,
        escalate: bool = False,
        explode: set[str] | None = None,
        edit_plans: list[dict[str, Any]] | None = None,
        edit_reviews: list[str] | None = None,
        backend_seeds: bool = False,
    ) -> None:
        self.repo = repo
        self.run_dir = run_dir
        self.review_epics = review_epics or ["approved"]
        self.coverage_verdicts = coverage_verdicts or ["ok"]
        self.two_epics = two_epics
        self.unwritten = set(unwritten or ())
        self.fail_audit = set(fail_audit or ())
        self.audit_replies = dict(audit_replies or {})
        self.feedback = dict(feedback or {})
        self.escalate = escalate
        self.explode = set(explode or ())
        self.edit_plans = list(edit_plans or ())
        self.edit_reviews = edit_reviews or ["approved"]
        self.backend_seeds = backend_seeds
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []
        self.cwds: list[str] = []
        self.backlog_at_decompose = ""

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

    # -- the grill ---------------------------------------------------------

    def _grill_brief(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"brief": "no open questions"}

    def _refactor_backlog(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"summary": "no changes needed"}

    # -- the epic split ---------------------------------------------------

    def _decompose_epics(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Create journey epic shells in one release milestone; `write-epic` records seeds."""
        self.backlog_at_decompose = (self.repo / data["backlog"]).read_text(encoding="utf-8")
        okf = Ostler(self.repo)
        if not (self.repo / EPIC_DIR / "epic.md").is_file():
            okf.create_epic(EPIC, "Account holder accesses their account")
        if self.two_epics and not (self.repo / SECOND_EPIC_DIR / "epic.md").is_file():
            okf.create_epic(SECOND_EPIC, "Account holder updates their profile")
        intake = tuple(
            item_id
            for bullet in markdown.split(self.backlog_at_decompose).walk_bullets()
            if (item_id := bullet.bracketed[0])
        )
        _milestone(
            self.repo,
            EPIC,
            *(SECOND_EPIC,) if self.two_epics else (),
            source_items=intake,
        )
        return {"status": "complete", "notes": f"one epic from {len(SEEDS)} bullet(s)"}

    def _rework_epics(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Same product as the decomposition, which is why it re-runs it."""
        return self._decompose_epics(data, nth)

    def _review_epics(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        verdict = self.review_epics[min(nth, len(self.review_epics)) - 1]
        return {"status": verdict, "notes": "" if verdict == "approved" else "one epic is two"}

    # -- standalone epic/story edits -------------------------------------

    def _default_edit_plan(self, data: dict[str, Any]) -> dict[str, Any]:
        intent = data["intent"]
        snapshot = data["snapshot"]
        if intent["kind"] == "remove-story":
            remaining = [story for story in snapshot["stories"] if story["slug"] != intent["story"]]
            covered = {seed for story in remaining for seed in story["covers"]}
            removed_seeds = [seed for seed in snapshot["seeds"] if seed["id"] not in covered]
            return {
                "status": "complete",
                "epic": snapshot["epic"],
                "delete_epic": not remaining and len(removed_seeds) == len(snapshot["seeds"]),
                "summary": "remove the requested story and its unowned scope",
                "journey_changes": ["Remove the journey segment delivered only by the story"],
                "seed_changes": [
                    {
                        "action": "remove",
                        "id": seed["id"],
                        "disposition": "drop",
                        "reason": "the requested story and its scope were removed",
                    }
                    for seed in removed_seeds
                ],
                "story_changes": [{"action": "remove", "slug": intent["story"]}],
                "affected_stories": [],
            }
        source = str(intent["source_bullet"])
        slug = source.lower().replace("[", "").replace("]", "").replace(" ", "-")
        return {
            "status": "complete",
            "epic": snapshot["epic"],
            "delete_epic": False,
            "summary": "add the requested journey segment",
            "journey_changes": ["Add the requested actor journey"],
            "seed_changes": [{
                "action": "add",
                "id": intent["bullet_id"],
                "status": "researched",
                "summary": source,
                "source_bullet": source,
            }],
            "story_changes": [{
                "action": "add",
                "slug": slug,
                "title": source,
                "covers": [intent["bullet_id"]],
                "depends": [],
                "rewrite": True,
            }],
            "affected_stories": [slug],
        }

    def _plan_epic_edit(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if self.edit_plans:
            return self.edit_plans[min(nth, len(self.edit_plans)) - 1]
        return self._default_edit_plan(data)

    def _refine_epic_edit_plan(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if self.edit_plans:
            return self.edit_plans[min(nth + 1, len(self.edit_plans)) - 1]
        return self._default_edit_plan(data)

    def _review_epic_edit_plan(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        status = self.edit_reviews[min(nth, len(self.edit_reviews)) - 1]
        return {
            "status": status,
            "notes": "scope and journeys agree" if status == "approved" else "journey drift",
        }

    def _rewrite_epic_edit(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        path = self.repo / data["epic_dir"] / "epic.md"
        text = path.read_text(encoding="utf-8")
        _before, marker, graph = text.partition("## Seeds")
        narrative = """## User Outcome

The account holder completes the revised journey.

## User Journeys

### Complete the revised journey

The account holder enters from the account screen, completes the edited behavior, sees its success
and failure states, and leaves with the requested outcome.

## Delivered Experience

The revised account operation is usable.

## Guardrails

Invalid input fails visibly.

## Non-Goals

Unrelated account work is excluded.

## Acceptance

The revised journey works end to end.

## Method

The running system is the source of truth.

"""
        path.write_text(_before.split("# Epic:", 1)[0] + f"# Epic: Accounts\n\n{narrative}{marker}{graph}", encoding="utf-8")
        return {"status": "complete", "notes": "epic journeys reconciled"}

    # -- the per-epic loop ------------------------------------------------

    def _write_epic(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        okf = Ostler(self.repo)
        epic = str(data["epic"])
        if epic.endswith(SECOND_EPIC):
            okf.add_seed(
                SECOND_EPIC,
                "p1",
                status="researched",
                summary="[p1] Users can edit their profile",
                meta={"sourceBullet": "[p1] Users can edit their profile"},
            )
            return {"status": "complete", "notes": "profile seed recorded"}
        surface = "docs/features/web/accounts.md"
        if self.backend_seeds:
            path = self.repo / surface
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "---\ntype: feature\nslug: accounts\narea: web\n"
                "title: Accounts\n---\n# Accounts\n\nExisting account surface.\n",
                encoding="utf-8",
            )
        for seed_id, text in SEEDS.items():
            meta: dict[str, Any] = {"sourceBullet": text}
            if self.backend_seeds:
                # Classified seeds are what the mockup gate reads: `backend` alone means no
                # surface is designed, and the story writer falls back to the feature doc.
                meta |= {"surface": surface, "layers": ["backend"], "services": ["api-service"]}
            okf.add_seed(EPIC, seed_id, status="researched", summary=text, meta=meta)
        return {"status": "complete", "notes": "seeds already recorded"}

    def _split_stories(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Register one story per seed. Idempotent: the coverage loop re-enters here."""
        okf = Ostler(self.repo)
        epic = SECOND_EPIC if str(data["epic"]).endswith(SECOND_EPIC) else EPIC
        stories = SECOND_STORIES if epic == SECOND_EPIC else STORIES
        existing = {str(s["slug"]) for s in okf.list("story", epic=epic)}
        for slug, title, seed in stories:
            if slug not in existing:
                okf.create_story(epic, slug, title, covers=[seed])
        return {"status": "complete", "notes": f"{len(stories)} stories"}

    # -- the per-story loop -----------------------------------------------

    def _design_mockup(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        # A story on an existing surface: the mockup stage is a pass-through, and
        # `write_story` falls back to the feature docs.
        assert "surface_manifest" not in data
        return {"status": "skipped", "surface": "", "mockup": "", "notes": "existing surface"}

    def _write_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        slug = str(data["story_slug"])
        if slug in self.explode:
            raise RuntimeError(f"killed while writing {slug}")
        title = dict((s, t) for s, t, _ in (*STORIES, *SECOND_STORIES)).get(slug, slug)
        _write_story_doc(self.repo / data["story_path"], title, authored=slug not in self.unwritten)
        return {"status": "written", "notes": "acceptance criteria and context"}

    def _rework_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Rewrite the story properly — the rework is what clears whichever gate failed."""
        slug = str(data["story_slug"])
        # A rework fixes what the structural gate flagged. It does *not* clear a standing
        # audit objection — that is what the rework budget is for, and what makes the
        # give-up arm reachable.
        self.unwritten.discard(slug)
        title = dict((s, t) for s, t, _ in (*STORIES, *SECOND_STORIES)).get(slug, slug)
        _write_story_doc(self.repo / data["story_path"], title)
        return {"status": "written", "notes": "rewritten"}

    def _audit_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        slug = str(data["story_slug"])
        note = self.feedback.pop(slug, "")
        if note:
            # An operator dropped a note into the run's inbox while the run was busy.
            assert self.run_dir is not None, "feedback scripted without a run_dir"
            inbox.append(
                self.run_dir / INBOX_FILE,
                id=f"{slug}-note",
                body=note,
                at="2024-01-01T00:00:00+00:00",
            )
        if slug in self.audit_replies:
            return self.audit_replies[slug]
        if slug in self.fail_audit:
            # The findings list is the verdict — `status` alone no longer fails a story.
            return {
                "status": "failed",
                "findings": [{
                    "id": f"{slug}-01",
                    "kind": "journey",
                    "target": "## Acceptance Criteria",
                    "issue": f"{slug} cannot be built as written",
                    "repair": "state the observable outcome",
                }],
                "notes": f"{slug} cannot be built as written",
            }
        return {"status": "passed", "findings": [], "notes": "a coder could build this"}

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
        config=RunConfig(),
    )


def _drive(
    env: RunEnv,
    agent: _Agent,
    *,
    wait_for_answer: Callable[..., Any] | None = None,
    **inputs: Any,
) -> Any:
    """Drive `Author`, auto-answering the grill's gate so it never blocks a test.

    The grill fires unconditionally at backlog intake, ahead of every other operator
    gate, and its `Await` writes to the same context-file path `review_epics`'s gate
    later reuses — so the two are told apart by *content*, not by path. A test that
    wants to script its own gate passes `wait_for_answer`; every other `Await` this
    run reaches still goes through it, only the grill's is skipped automatically.
    """

    def _wait_for_answer(path: Path, **kwargs: Any) -> Any:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        if "grill this backlog" in text:
            return None
        if wait_for_answer is not None:
            return wait_for_answer(path, **kwargs)
        return None

    with patch.object(pyflow_driver, "wait_for_answer", _wait_for_answer):
        return drive(Author(**inputs), replace(env, agent_runner=StubRunner(agent)))


def _drive_story_edit(env: RunEnv, agent: _Agent, **inputs: Any) -> Any:
    return drive(StoryEdit(**inputs), replace(env, agent_runner=StubRunner(agent)))


def _drive_epic_edit(env: RunEnv, agent: _Agent, **inputs: Any) -> Any:
    return drive(EpicEdit(**inputs), replace(env, agent_runner=StubRunner(agent)))


# --------------------------------------------------------------------------- epic mode


def test_epic_mode_authors_the_backlog_and_commits_it(
    backlogged: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The straight-through run: one epic, two stories, both gates green, then the git tail.

    Every count below is a node the YAML ran exactly once per pass too, and the artifacts
    are the YAML's artifacts: the epic and its seeds in `epic.md`, an authored `story.md`
    per story, the consumed bullets gone from the backlog, one commit on the author branch,
    and no PR because there is no token.
    """
    agent = _Agent(backlogged)
    with caplog.at_level("INFO"):
        result = _drive(_env(tmp_path), agent)
    pruned = "\n".join(r.getMessage() for r in caplog.records if "pruned" in r.getMessage())

    assert agent.counts() == {
        "grill-brief": 1,
        "refactor-backlog": 1,
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
    assert not [
        f for f in Ostler(backlogged).doctor().data["findings"] if f["severity"] == "error"
    ]

    # The coverage tail pruned both work items. Supporting context is prose, not a bullet.
    assert _bullets(backlogged) == []
    assert "## Scope items" in (backlogged / BACKLOG).read_text()
    # Nothing outstanding — asserted on the log line, because in epic mode the prune tail's
    # count reaches a human only there (the run's result is the PR node's). The surviving
    # prose bullet is not a work item, and counting it says the backlog still holds work.
    assert "pruned 2 bullet(s)" in pruned and "(0 remaining)" in pruned, pruned

    # The git tail: committed on the run's own branch, PR skipped for want of a token.
    assert _subject(backlogged) == "author: epic backlog authoring"
    assert result.author_pr == "skipped", result
    assert result.pr_skip_reason == "no GitHub token is configured", result

    # Every turn ran in the repo, not in the run directory.
    assert set(agent.cwds) == {str(backlogged)}


def test_the_grill_briefs_the_operator_then_refactor_backlog_continues_the_run(
    backlogged: Path, tmp_path: Path
) -> None:
    """The grill fires first, unconditionally, and its note carries the trigger and brief.

    `refactor_backlog` then reads that same context file and hands the run on into
    `split_epics` — a state of its own, not folded back into the gate that produced it.
    """
    agent = _Agent(backlogged)
    _drive(_env(tmp_path), agent)

    note = (backlogged / CONTEXT).read_text(encoding="utf-8")
    assert "/stablemate-grill" in note, note
    assert "grill this backlog before it is split into epics" in note, note
    assert "no open questions" in note, note
    assert agent.calls[:2] == ["grill-brief", "refactor-backlog"], agent.calls
    assert agent.counts()["decompose-epics"] == 1, agent.counts()


def test_epic_mode_skips_mockups_for_seeds_tagged_without_a_frontend_layer(
    backlogged: Path, tmp_path: Path
) -> None:
    """A `backend`-tagged seed removes two agent turns; an untagged one removes none.

    The gate used to read free-text `surface:` cross-checked against the OKF book, which in a
    greenfield repo resolves to nothing — so it failed closed and designed a 20 KB mockup for
    every backend story. The layer tag is the fact the epic author already knows.
    """
    agent = _Agent(backlogged, backend_seeds=True)

    _drive(_env(tmp_path), agent)

    assert agent.counts()["design-mockup"] == 0, agent.counts()
    assert agent.counts()["write-story"] == 2, agent.counts()
    assert _stories(backlogged) == {slug: True for slug in SLUGS}


def test_epic_mode_adopts_unnamed_scope_before_decomposition(
    backlogged: Path, tmp_path: Path
) -> None:
    backlog = backlogged / BACKLOG
    backlog.write_text(
        backlog.read_text(encoding="utf-8")
        + "\n## Later intake\n\n- Recover a local draft\n\n"
        + "## Filed by coder\n\n- Fix an adjacent defect\n",
        encoding="utf-8",
    )
    agent = _Agent(backlogged)

    _drive(_env(tmp_path), agent)

    assert "- [ACME-" in agent.backlog_at_decompose
    assert "] Recover a local draft" in agent.backlog_at_decompose
    assert "] Fix an adjacent defect" in agent.backlog_at_decompose
    intake = {
        item_id
        for bullet in markdown.split(agent.backlog_at_decompose).walk_bullets()
        if (item_id := bullet.bracketed[0])
    }
    milestone = Ostler(backlogged).list("milestone")[0]
    assert set(milestone["sourceItems"]) == intake


def test_story_prune_preserves_a_parent_with_nested_work(backlogged: Path) -> None:
    backlog = backlogged / BACKLOG
    original = (
        "# Backlog\n\n"
        "## Scope items\n\n"
        "- [parent] Ship draft recovery\n"
        "  - [child] Preserve ten snapshots\n"
    )
    backlog.write_text(original, encoding="utf-8")

    result = prune_bullet(
        logging.getLogger("test"),
        backlog=BACKLOG,
        bullet_id="parent",
        from_backlog=True,
        repo_dir=str(backlogged),
    )

    assert result.removed == 0
    assert result.remaining == 2
    assert backlog.read_text(encoding="utf-8") == original


def test_author_nodes_use_milestones_when_todo_is_absent(backlogged: Path) -> None:
    okf = Ostler(backlogged)
    okf.create_epic(EPIC, "Accounts")
    _milestone(backlogged, EPIC)
    okf.add_seed(EPIC, "b1", status="researched", summary=SEEDS["b1"],
                 meta={"sourceBullet": SEEDS["b1"]})
    okf.create_story(EPIC, "01-sign-in", "Sign in", covers=["b1"])

    logger = logging.getLogger("test")
    pick = select_epic(logger, repo_dir=str(backlogged))

    assert pick.has_epic is True
    assert pick.epic == EPIC_NAME

    story = backlogged / EPIC_DIR / "stories/01-sign-in/story.md"
    _write_story_doc(story, "Sign in")
    report = validate_artifacts(logger, repo_dir=str(backlogged))

    assert report.ok, report.errors


def test_every_prompt_is_told_the_resolved_paths_not_the_blank_parameters(
    backlogged: Path, tmp_path: Path
) -> None:
    """`epics_dir` and `backlog` reach a prompt as what `load_config` resolved.

    Both parameters default to blank, and blank is the *normal* case — it means "ask
    ostler". The prompts rendered the raw parameter, so every default run told its agent
    `Epics directory: ``, and every path the prompt built from it came out rooted at `/`.
    An agent handed no epics directory goes looking for one, and on a machine holding more
    than one checkout it finds the wrong repo's: two benchmark runs decomposed the
    *harness'* backlog into the target and left the target's epics index empty.
    """
    agent = _Agent(backlogged)
    _drive(_env(tmp_path), agent)

    for stem in ("decompose-epics", "review-epics"):
        for args in agent.args_for(stem):
            assert args["epics_dir"] == EPICS, (stem, args)
            assert args["backlog"] == BACKLOG, (stem, args)
    for args in agent.args_for("write-epic"):
        assert args["backlog"] == BACKLOG, args
        assert args["epic_dir"] == EPIC_DIR, args
    for args in agent.args_for("review-coverage"):
        assert args["backlog"] == BACKLOG, args


def test_epic_docs_are_all_written_before_story_splitting(backlogged: Path, tmp_path: Path) -> None:
    """The main author flow has two epic worklists, not one single-pass epic loop."""
    agent = _Agent(backlogged, two_epics=True)

    _drive(_env(tmp_path), agent)

    first_split = agent.calls.index("split-stories")
    write_epic_positions = [i for i, stem in enumerate(agent.calls) if stem == "write-epic"]
    assert len(write_epic_positions) == 2, agent.calls
    assert all(i < first_split for i in write_epic_positions), agent.calls
    assert [args["epic"] for args in agent.args_for("write-epic")] == [
        EPIC_NAME,
        SECOND_EPIC_NAME,
    ]
    assert [args["epic"] for args in agent.args_for("split-stories")] == [
        EPIC_NAME,
        SECOND_EPIC_NAME,
    ]
    assert _stories(backlogged) == {slug: True for slug in [*SLUGS, *SECOND_SLUGS]}


def test_the_commit_leaves_work_the_run_did_not_do_alone(
    backlogged: Path, tmp_path: Path, write: Callable[[Path, str], Path]
) -> None:
    """The run commits the docs it authored, not the working tree it found.

    `repo_dir` defaults to the directory the run was launched from, so the repo author
    writes into is routinely a checkout somebody else is working in — the git tail used
    to `git add -A`, which swept their in-flight edits into a commit subjected
    `author: …`. Anything outside the docs tree must survive the run uncommitted.
    """
    stray = write(backlogged / "src/half_finished.py", "def in_progress(): ...\n")

    _drive(_env(tmp_path), _Agent(backlogged))

    assert _subject(backlogged) == "author: epic backlog authoring"
    committed = subprocess.run(
        ["git", "show", "--name-only", "--pretty=format:", "HEAD"],
        cwd=backlogged,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert committed, "the run committed nothing at all"
    # Everything the run authored, and nothing else. `.agents/ids.json` is ostler's id
    # ledger: it sits outside the docs tree but must land in the same commit as the
    # documents it numbers, or the next run remints those ids for other entities.
    assert all(p.startswith("docs/") or p == ".agents/ids.json" for p in committed), committed
    assert ".agents/ids.json" in committed, committed
    # Still there, still theirs: untouched on disk and untracked in git.
    assert stray.read_text() == "def in_progress(): ...\n"
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=backlogged,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert "src/half_finished.py" in untracked, untracked


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


def test_a_story_nobody_can_fix_is_parked_and_the_epic_carries_on(
    backlogged: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The give-up arm advances the queue instead of waiting on a human forever.

    The auditor objects to `01-sign-in` on every lap and the autonomous resolver never
    clears it, so the story exhausts its resolution budget. It used to `Await` there — and
    with no human at the other end of an unattended run, one unwritable story held the
    epic's entire remaining queue behind it for 14 of one run's 48 hours.
    """
    agent = _Agent(backlogged, fail_audit={"01-sign-in"})

    with caplog.at_level(logging.WARNING):
        _drive(_env(tmp_path), agent)

    assert any("parking story '01-sign-in'" in r.message for r in caplog.records), caplog.text
    assert any("leaves 1 story/stories unauthored" in r.message for r in caplog.records)
    # The parked story is never re-selected, and the next one is authored normally.
    assert agent.args_for("write-story")[-1]["story_slug"] == "02-reset-password"
    assert _stories(backlogged)["02-reset-password"] is True


# --------------------------------------------------------------------------- the audit contract
# The findings list *is* the verdict. Prose `status` used to be, and nothing could check
# whether an audit had been exhaustive — so each lap surfaced one different objection and
# 87 of 144 stories in one run went write → audit(fail) → rework → audit(pass), every time.


def test_an_empty_findings_list_is_a_pass_whatever_status_says(
    backlogged: Path, tmp_path: Path
) -> None:
    """A `failed` with nothing to repair cannot be reworked, so it upholds the story.

    Routing it to rework instead sends the reworker a blank brief, which is precisely the
    lap that costs a turn and repairs nothing.
    """
    agent = _Agent(
        backlogged,
        audit_replies={"01-sign-in": {"status": "failed", "findings": [], "notes": "unease"}},
    )

    _drive(_env(tmp_path), agent)

    assert agent.counts()["audit-story"] == 2, agent.counts()   # one per story, no re-audit
    assert agent.counts()["rework-story"] == 0, agent.counts()
    assert _stories(backlogged) == {slug: True for slug in SLUGS}


def test_a_finding_the_reworker_cannot_act_on_stops_the_run(
    backlogged: Path, tmp_path: Path
) -> None:
    """Every finding names its repair, or the audit did not answer.

    A finding with no `repair` is indistinguishable from a hunch once it reaches the rework
    prompt, and the loop would burn its whole budget on it. Stopping leaves the checkpoint
    resumable; upholding silently would ship the defect.
    """
    from workhorse.pyflow import WorkflowFailed

    agent = _Agent(
        backlogged,
        audit_replies={"01-sign-in": {
            "status": "failed",
            "findings": [{"id": "x-01", "kind": "journey", "target": "## Acceptance Criteria",
                          "issue": "vague", "repair": "   "}],
            "notes": "",
        }},
    )

    with pytest.raises(WorkflowFailed, match="finding 1 missing repair"):
        _drive(_env(tmp_path), agent)


def test_an_operator_note_dropped_mid_run_reworks_the_story_once(
    backlogged: Path, tmp_path: Path
) -> None:
    """`check_story_feedback` never blocks, and consuming the inbox is what bounds it.

    The note is dropped while the auditor is running, so it is there when
    `story_feedback` polls. Replying to it is what consumes it, so the story is reworked
    exactly once no matter how many laps the loop takes afterwards.
    """
    env = _env(tmp_path)
    agent = _Agent(
        backlogged,
        feedback={"01-sign-in": "call it 'sign in', never 'log in'"},
        run_dir=env.writer.run_dir,
    )
    _drive(env, agent)

    assert agent.counts()["rework-story"] == 1, agent.counts()
    note = agent.args_for("rework-story")[0]
    assert "never 'log in'" in note["operator_feedback"], note
    # The operator's note is the work; there is no validation failure to carry.
    assert note["validation_errors"] == "", note
    messages = inbox.all_messages(env.writer.run_dir / INBOX_FILE)
    assert len(messages) == 1, messages
    assert messages[0].reply, messages
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


def test_coverage_resolver_cycles_share_the_epic_scoped_split_bound(
    backlogged: Path, tmp_path: Path
) -> None:
    """A resolved coverage block cannot reset the epic's cumulative resolution count.

    Each block always parks for a human — the resolver never decides on the operator's
    behalf — so two blocked reviews in a row cost two real `Await`s, and the second one's
    `split_resolves` must pick up from the first's, not restart at zero.
    """
    seen: list[str] = []
    labels: list[dict[str, str]] = []
    agent = _Agent(backlogged, coverage_verdicts=["blocked", "blocked", "ok"])
    real_rebase = pyflow_activity.ActivityLog.rebase

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text())

    def capture(self: Any, current: dict[str, str]) -> Any:
        labels.append(dict(current))
        return real_rebase(self, current)

    with patch.object(pyflow_activity.ActivityLog, "rebase", capture):
        _drive(_env(tmp_path), agent, wait_for_answer=answered)

    assert agent.counts()["resolve-operator"] == 2, agent.counts()
    assert len(seen) == 2, seen
    assert all("the reset flow is unclaimed" in note for note in seen), seen
    reset_laps = [row for row in labels if row.get("author.split_resolves") == "1"]
    assert any("author.cov_reworks" not in row for row in reset_laps), labels


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
    checkpoints, and polls that path's mtime. Patching `wait_for_answer` is the
    operator answering — and the autonomous arms above are proved by the *absence* of that
    patch, since a real wait would hang the suite.
    """
    seen: list[str] = []

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text())

    agent = _Agent(backlogged, review_epics=["blocked", "approved"])
    _drive(_env(tmp_path), agent, wait_for_answer=answered, operator_mode="human")

    assert agent.counts()["resolve-operator"] == 0, agent.counts()
    assert agent.counts()["rework-epics"] == 0, agent.counts()
    assert len(seen) == 1 and "one epic is two" in seen[0], seen
    assert (backlogged / CONTEXT).is_file()
    # The gate looped back into the split, so the run finished on the second review.
    assert agent.counts()["review-epics"] == 2, agent.counts()


def test_an_escalated_story_block_waits_on_the_story_context(
    backlogged: Path, tmp_path: Path
) -> None:
    """The story gate's other arm: the resolver declines, so a human is waited on.

    One audit-directed repair and convergence re-audit happen first, then the gate hands
    the block to the resolver, which escalates — and the wait lands on the *story's* context
    file, not the run-wide one.
    """
    seen: list[Path] = []

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path)
        # What a human does at this gate: fix the story's inputs. Here, drop the objection.
        agent.fail_audit.clear()

    agent = _Agent(backlogged, fail_audit={"01-sign-in"}, escalate=True)
    _drive(_env(tmp_path), agent, wait_for_answer=answered)

    assert seen == [backlogged / EPIC_DIR / "stories/01-sign-in/context.md"], seen
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert agent.counts()["rework-story"] == 1, agent.counts()
    story_audits = [
        args for args in agent.args_for("audit-story") if args["story_slug"] == "01-sign-in"
    ]
    assert len(story_audits) == 3, agent.counts()
    first, convergence, after_operator = story_audits
    assert first["prior_audit_findings"] == ""
    # The re-audit is handed the structured findings, id first, so it can recognise the same
    # defect rather than inventing a fresh objection each lap.
    assert convergence["prior_audit_findings"] == (
        "01-sign-in-01 [journey] ## Acceptance Criteria: 01-sign-in cannot be built as "
        "written. Repair: state the observable outcome\n"
        "Summary: 01-sign-in cannot be built as written"
    )
    assert after_operator["prior_audit_findings"] == ""
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
    # The bullet it consumed is pruned; the other identified item remains.
    assert _bullets(with_epic) == [f"- {SEEDS['b2']}"]
    assert result.removed == 1, result
    assert result.remaining == 1, result
    assert _commit_count(with_epic) == before, "story mode must not commit"


def test_story_mode_refuses_an_epic_that_does_not_exist(backlogged: Path, tmp_path: Path) -> None:
    """`seed_story` never scaffolds an epic — a missing one is a hard, actionable failure."""
    from workhorse.pyflow import WorkflowFailed

    with pytest.raises(WorkflowFailed, match="does not exist"):
        _drive(_env(tmp_path), _Agent(backlogged), mode="story", epic="nope", bullet="b1")


# -------------------------------------------------------------------------- story-edit flow


def test_story_edit_add_authors_one_story_and_commits(with_epic: Path, tmp_path: Path) -> None:
    agent = _Agent(with_epic)

    _drive_story_edit(_env(tmp_path), agent, action="add", epic=EPIC, bullet="b1")

    stories = _stories(with_epic)
    assert list(stories) == ["b1-users-can-sign-in-with-an-email-and-a-password"], stories
    assert all(stories.values()), stories
    assert _bullets(with_epic) == [f"- {SEEDS['b2']}"]
    assert _subject(with_epic).startswith("author: accounts"), _subject(with_epic)


def test_story_edit_remove_deletes_an_unstarted_story_and_commits(
    with_epic: Path, tmp_path: Path
) -> None:
    okf = Ostler(with_epic)
    assert okf.create_story(EPIC, "01-extra", "Extra").ok
    _commit(with_epic, "story scaffold")

    result = _drive_story_edit(_env(tmp_path), _Agent(with_epic), action="remove", story="01-extra")

    assert result.changed is True
    assert "01-extra" not in {s["slug"] for s in Ostler(with_epic).list("story")}
    assert not (with_epic / EPIC_DIR).exists(), "the last story leaves an empty epic to delete"
    assert "accounts" in _subject(with_epic)


def test_story_edit_remove_refuses_a_started_story_without_force(
    with_epic: Path, tmp_path: Path
) -> None:
    from workhorse.pyflow import WorkflowFailed

    okf = Ostler(with_epic)
    assert okf.create_story(EPIC, "01-started", "Started").ok
    assert okf.set_status("01-started", "Reviewed").ok
    _commit(with_epic, "started story")

    with pytest.raises(WorkflowFailed, match="refusing to delete"):
        _drive_story_edit(_env(tmp_path), _Agent(with_epic), action="remove", story="01-started")


def test_story_edit_remove_reconciles_remaining_epic_scope_and_journey(
    with_epic: Path, tmp_path: Path
) -> None:
    okf = Ostler(with_epic)
    assert okf.add_seed(EPIC, "keep", status="researched", summary="Keep").ok
    assert okf.add_seed(EPIC, "remove", status="researched", summary="Remove").ok
    assert okf.create_story(EPIC, "keep-story", "Keep", covers=["keep"]).ok
    assert okf.create_story(EPIC, "remove-story", "Remove", covers=["remove"]).ok
    _write_story_doc(with_epic / EPIC_DIR / "stories/keep-story/story.md", "Keep")
    _write_story_doc(with_epic / EPIC_DIR / "stories/remove-story/story.md", "Remove")
    kept_before = (with_epic / EPIC_DIR / "stories/keep-story/story.md").read_bytes()
    _commit(with_epic, "authored stories")

    _drive_story_edit(
        _env(tmp_path),
        _Agent(with_epic),
        action="remove",
        story="remove-story",
        reason="The remaining journey no longer needs this scope",
    )

    graph = Ostler(with_epic)
    assert {row["slug"] for row in graph.list("story", epic=EPIC)} == {"keep-story"}
    assert {row["id"] for row in graph.list("seed", epic=EPIC)} == {"keep"}
    assert "## User Journeys" in (with_epic / EPIC_DIR / "epic.md").read_text(encoding="utf-8")
    assert (with_epic / EPIC_DIR / "stories/keep-story/story.md").read_bytes() == kept_before


def test_story_edit_mutates_the_overridden_epics_root(backlogged: Path, tmp_path: Path) -> None:
    custom_epics = "product/epics"
    okf = Ostler(backlogged, doc_roots={"epics": custom_epics})
    assert okf.create_epic(EPIC, "Accounts").ok
    assert okf.create_story(EPIC, "remove-story", "Remove").ok
    _commit(backlogged, "custom epic root")

    _drive_story_edit(
        _env(tmp_path),
        _Agent(backlogged),
        action="remove",
        story="remove-story",
        epics_dir=custom_epics,
    )

    assert not (backlogged / custom_epics / EPIC_NAME).exists()
    assert not (backlogged / EPICS).exists()


def test_epic_edit_static_findings_drive_a_replacement_plan(
    with_epic: Path, tmp_path: Path
) -> None:
    okf = Ostler(with_epic)
    assert okf.add_seed(EPIC, "interactive", status="researched", summary="Interactive").ok
    assert okf.create_story(
        EPIC, "interactive-editor", "Interactive editor", covers=["interactive"]
    ).ok
    _write_story_doc(
        with_epic / EPIC_DIR / "stories/interactive-editor/story.md", "Interactive editor"
    )
    _commit(with_epic, "interactive editor")
    raw_change = {
        "action": "add",
        "slug": "raw-xml-editor",
        "title": "Raw XML editor",
        "covers": ["raw-xml"],
        "depends": ["interactive-editor"],
        "rewrite": True,
    }
    invalid = {
        "status": "complete",
        "epic": EPIC,
        "summary": "add raw XML editing",
        "journey_changes": ["Add raw XML mode"],
        "seed_changes": [{
            "action": "add",
            "id": "raw-xml",
            "status": "researched",
            "summary": "Edit canonical XML",
            "source_bullet": "[raw-xml] Add raw XML editing",
        }],
        "story_changes": [raw_change],
        "affected_stories": [],
    }
    valid = {**invalid, "affected_stories": ["raw-xml-editor"]}
    agent = _Agent(with_epic, edit_plans=[invalid, valid])

    _drive_epic_edit(
        _env(tmp_path),
        agent,
        epic=EPIC,
        change="Add raw XML editing alongside the interactive editor",
    )

    assert agent.counts()["refine-epic-edit-plan"] == 1
    findings = agent.args_for("refine-epic-edit-plan")[0]["validation_findings"]
    assert "[E_AFFECTED_STORY]" in findings
    stories = {row["slug"]: row for row in Ostler(with_epic).list("story", epic=EPIC)}
    assert set(stories) == {"interactive-editor", "raw-xml-editor"}
    assert stories["raw-xml-editor"]["covers"] == ["raw-xml"]
    assert stories["raw-xml-editor"]["authored"] is True


def test_epic_edit_semantic_review_reworks_are_bounded(
    with_epic: Path, tmp_path: Path
) -> None:
    """Validation must carry the cumulative plan rework count into semantic review."""
    okf = Ostler(with_epic)
    assert okf.add_seed(EPIC, "remove", status="researched", summary="Remove").ok
    assert okf.create_story(EPIC, "remove-story", "Remove", covers=["remove"]).ok
    _write_story_doc(with_epic / EPIC_DIR / "stories/remove-story/story.md", "Remove")
    _commit(with_epic, "story to remove")
    seen: list[str] = []
    agent = _Agent(with_epic, edit_reviews=["needs_rework"] * 4)

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text())
        agent.edit_reviews = ["approved"]

    with patch.object(pyflow_driver, "wait_for_answer", answered):
        _drive_story_edit(
            _env(tmp_path),
            agent,
            action="remove",
            story="remove-story",
            reason="Remove obsolete scope",
        )

    assert agent.counts()["refine-epic-edit-plan"] == 3, agent.counts()
    assert len(seen) == 1 and "journey drift" in seen[0], seen
    assert not (with_epic / EPIC_DIR).exists()


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
    # The epic is the label until a story is picked, and `progress` is absent rather than
    # blank because the driver drops empty values.
    assert stamped[0] == {"work_id": EPIC_NAME, "epic": EPIC_NAME}, stamped[0]
    assert {labels["work_id"] for labels in stamped} == {EPIC_NAME, *SLUGS}, stamped
    # `progress` is the worklist's own count, so a dashboard can read it without knowing
    # anything about authoring.
    assert any(labels.get("progress") for labels in stamped), stamped
    assert any(labels.get("author.cov_reworks") == "0" for labels in stamped), stamped
    assert any(labels.get("author.split_resolves") == "0" for labels in stamped), stamped
    # Unprefixed, unlike the YAML engine's `wf.work_id`.
    assert not any(k.startswith("wf.") for labels in seen for k in labels), seen

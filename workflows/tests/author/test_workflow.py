"""End-to-end drives of the author workflow (`author/workflow.py`)."""
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
from _milestones import write_milestone
from _pm import amendment, answer, verdict
from ostler import Ostler, ids
from ostler.register import RECORD_FILE, Record
from workhorse import inbox
from workhorse.artifacts import ArtifactWriter
from workhorse.cli.inbox import INBOX_FILE
from workhorse.config_run import RunConfig
from workhorse.pyflow import activity as pyflow_activity
from workhorse.pyflow import park as pyflow_park
from workhorse.pyflow.driver import drive, read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse._vendor.stablemate_core import config as core_config
from workhorse.pyflow import WorkflowFailed
from workhorse.records import parse_checkpoint
from workhorse.worklist import WORK_FILE, JsonBackend, WorkList

from workhorse_workflows import author
from workhorse_workflows.author.finalize.nodes.artifacts import validate_artifacts
from workhorse_workflows.author.shared.nodes.story_mode import promote_record, seed_story
from workhorse_workflows.author.shared.schemas import EditIntent
from workhorse_workflows.author.epic_edit import EpicEdit
from workhorse_workflows.author.shared.survey import record_slug
from workhorse_workflows.author.story_edit import StoryEdit
from workhorse_workflows.author.story_edit.nodes import resolve_story_intent
from workhorse_workflows.author.workflow import Author, workflow

BACKLOG = "docs/backlog.md"
MILESTONE = "docs/milestones/account-access/milestone.md"
EPICS = "docs/epics"
EPIC = "accounts"
SECOND_EPIC = "profiles"
EPIC_NAME = f"0001-{EPIC}"
SECOND_EPIC_NAME = f"0002-{SECOND_EPIC}"
EPIC_DIR = f"{EPICS}/{EPIC_NAME}"
SECOND_EPIC_DIR = f"{EPICS}/{SECOND_EPIC_NAME}"
CONTEXT = f"{EPICS}/_author-context.md"

SEEDS = {
    "b1": "Users can sign in with an email and a password",
    "b2": "Users can reset a forgotten password",
}
B1_SLUG = "users-can-sign-in-with-an-email-and-a-password"
B1_BODY = "Offer a magic link as well.\nKeep the password form."
SURFACE = "**api** is the only surface and the only writer of stored data."
STORIES = (
    ("01-sign-in", "Sign in", "b1"),
    ("02-reset-password", "Reset password", "b2"),
)
SECOND_STORIES = (("01-edit-profile", "Edit profile", "p1"),)
SLUGS = [slug for slug, _, _ in STORIES]
SECOND_SLUGS = [slug for slug, _, _ in SECOND_STORIES]

SURVEY_DIR = "docs/survey"
RUBRIC = f"{SURVEY_DIR}/rubric.md"
RULES = f"{SURVEY_DIR}/units.yml"
INVENTORY = f"{SURVEY_DIR}/inventory.json"
FINDINGS = f"{SURVEY_DIR}/findings"
PARTITION = f"{SURVEY_DIR}/partition.yaml"
BUTTON = "src/components/button"
CLUSTER = "missing-accessible-name"


@pytest.fixture
def backlogged(repo: Path, write: Callable[[Path, str], Path]) -> Path:
    """A repo with a two-bullet backlog and nothing else: no epics, no OKF book."""
    write(
        repo / BACKLOG,
        f"# Backlog\n\nSurfaces this app ships:\n\n{SURFACE}\n\n## Scope items\n\n"
        + "".join(f"- {v}\n" for v in SEEDS.values()),
    )
    write_milestone(repo)
    write(repo / "docs/services/account/gui/screens/sign-in.md", (
        "---\ntype: screen\nslug: sign-in\ntitle: Sign in\n---\n# Sign in\n\n"
        "- route: `/sign-in`\n- requires: none\n- params: none\n\n"
        "## Screen states\n\n### Loaded\n- shows: none\n"
    ))
    write(repo / "docs/services/account/ops/stack.md", (
        "---\ntype: runbook\nslug: stack\ntitle: Stack\n---\n# Stack\n\n"
        "- driver: web\n- entry-url: http://localhost:3000\n- surfaces: [sign-in](../gui/screens/sign-in.md)\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `serve`\n"
    ))
    write(repo / "docs/milestones/account-access/mockups/sign-in.html", "<html></html>\n")
    write(repo / "docs/services/api-service/.gitkeep", "")
    _commit(repo, "seed")
    return repo


@pytest.fixture
def with_epic(backlogged: Path) -> Path:
    """`backlogged` plus one already-authored epic, for `story` mode."""
    okf = Ostler(backlogged)
    okf.create_epic(EPIC, "Accounts")
    okf.todo_add(EPIC)
    _milestone(backlogged, EPIC)
    _commit(backlogged, "epic scaffold")
    return backlogged


@pytest.fixture
def artifacts() -> Path:
    """The artifacts dir of this test, already a git repository with one commit."""
    root = core_config.ensure_artifacts_repo()
    subprocess.run(["git", "-C", str(root), "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    return root


@pytest.fixture
def with_records(with_epic: Path, artifacts: Path) -> Path:
    """`with_epic` plus two open records, `b1` with a body, filed and committed in the artifacts repo."""
    okf = Ostler(with_epic)
    for record_id, summary in SEEDS.items():
        filed = okf.backlog_add(
            summary, repo="acme", area="accounts", record_id=record_id,
            body=B1_BODY if record_id == "b1" else "",
        )
        assert filed.ok, filed.message
    return with_epic


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


def _current_branch(repo: Path) -> str:
    out = subprocess.run(
        ["git", "branch", "--show-current"], cwd=repo, check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


def _commit_count(repo: Path) -> int:
    out = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    )
    return int(out.stdout.strip())


def _filed(artifacts: Path, token: str) -> Record:
    """The record the register holds for *token*, as it stands on the shelf."""
    folder = next((artifacts / "backlog").glob(f"*/*/{token}"))
    return Record.read(folder / RECORD_FILE)


def _artifact_subjects(artifacts: Path) -> list[str]:
    return subprocess.run(
        ["git", "-C", str(artifacts), "log", "--format=%s"], capture_output=True, text=True, check=True
    ).stdout.splitlines()


def _stories(repo: Path) -> dict[str, bool]:
    """`{slug: authored}` for every story ostler can see."""
    return {str(s["slug"]): bool(s.get("authored")) for s in Ostler(repo).list("story")}


def _milestone(repo: Path, *epics: str) -> None:
    write_milestone(repo, epics=epics)


_BODY = """# Story: {title}

## Dependencies

(none)

## Fixtures

(none)

## Context

{title} is one of the account surfaces this epic covers. The screen exists in the web app
already, so this story adds behaviour to it rather than a new surface. It works on
[sign-in](docs/services/account/gui/screens/sign-in.md).

## Acceptance Criteria

- Given a visitor on the {title} form, when they submit valid input, the app confirms it.
- Given invalid input, the form reports what is wrong and stays where it is.

## Non-Functional Acceptance Criteria

- Existing account journeys outside this form remain unchanged.

## Technical Notes

No prior implementation reference exists.

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

## Non-Functional Acceptance Criteria

(none)

## Technical Notes

No prior implementation reference exists.

## Implementation Status

- **Status**: Not started
"""


def _write_story_doc(
    path: Path, title: str, *, authored: bool = True, services: tuple[str, ...] = ()
) -> None:
    """Fill the scaffold `create_story` left, keeping its front-matter verbatim."""
    front, _, _rest = path.read_text(encoding="utf-8").partition("\n---\n")
    if services:
        front += f"\nservices: [{', '.join(services)}]"
    body = (_BODY if authored else _UNWRITTEN_BODY).format(title=title)
    path.write_text(f"{front}\n---\n\n{body}", encoding="utf-8")


def _rules() -> str:
    """The enumeration rules the surveyor's planner writes."""
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
    """A scripted stand-in for every one of the workflow's agent turns."""

    def __init__(
        self,
        repo: Path,
        *,
        review_epics: list[str] | None = None,
        coverage_verdicts: list[str] | None = None,
        two_epics: bool = False,
        unwritten: set[str] | None = None,
        fail_audit: set[str] | None = None,
        feedback: dict[str, str] | None = None,
        run_dir: Path | None = None,
        escalate: bool = False,
        block: set[str] | None = None,
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
        self.feedback = dict(feedback or {})
        self.escalate = escalate
        self.block = set(block or ())
        self.explode = set(explode or ())
        self.edit_plans = list(edit_plans or ())
        self.edit_reviews = edit_reviews or ["approved"]
        self.backend_seeds = backend_seeds
        self.stage_calls: Counter[str] = Counter()
        self.questions: list[str] = []
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []
        self.cwds: list[str] = []


    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        self.args.append(data)
        self.cwds.append(str(node.cwd))
        if stem in self.block:
            self.block.discard(stem)
            return "(scripted) blocked", {"status": "blocked", "notes": "which order?"}
        handler = getattr(self, f"_{stem.replace('-', '_')}")
        return f"(scripted) {node.prompt}", handler(data, self.counts()[stem])

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for s, a in zip(self.calls, self.args, strict=True) if s == stem]


    def _split_epics(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Create only the epic skeletons and attach them to the existing milestone."""
        okf = Ostler(self.repo)
        if not (self.repo / EPIC_DIR / "epic.md").is_file():
            okf.create_epic(EPIC, "Account holder accesses their account")
        epics = [EPIC]
        if self.two_epics:
            if not (self.repo / SECOND_EPIC_DIR / "epic.md").is_file():
                okf.create_epic(SECOND_EPIC, "Account holder updates their profile")
            epics.append(SECOND_EPIC)
        _milestone(self.repo, *epics)
        return {"status": "complete", "notes": "ordered epic skeletons created"}

    def _rework_epic_split(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return self._split_epics(data, nth)

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
        source = str(intent["summary"])
        slug = source.lower().replace(" ", "-")
        return {
            "status": "complete",
            "epic": snapshot["epic"],
            "delete_epic": False,
            "summary": "add the requested journey segment",
            "journey_changes": ["Add the requested actor journey"],
            "seed_changes": [{
                "action": "add",
                "id": intent["record_id"],
                "status": "researched",
                "summary": source,
                "services": ["account"],
                "source_record": intent["record_id"],
            }],
            "story_changes": [{
                "action": "add",
                "slug": slug,
                "title": source,
                "covers": [intent["record_id"]],
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


    def _write_epic(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        okf = Ostler(self.repo)
        epic = str(data["epic"])
        if epic.endswith(SECOND_EPIC):
            okf.add_seed(
                SECOND_EPIC,
                "p1",
                status="researched",
                summary="[p1] Users can edit their profile",
                meta={"services": ["account"]},
            )
            return {"status": "complete", "notes": "profile seed recorded"}
        surface = "docs/services/web/accounts.md"
        if self.backend_seeds:
            path = self.repo / surface
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "---\ntype: feature\nslug: accounts\narea: web\n"
                "title: Accounts\n---\n# Accounts\n\nExisting account surface.\n",
                encoding="utf-8",
            )
        for seed_id, text in SEEDS.items():
            meta: dict[str, Any] = {"services": ["account"]}
            if self.backend_seeds:
                meta |= {"surface": surface, "services": ["api-service"]}
            okf.add_seed(EPIC, seed_id, status="researched", summary=text, meta=meta)
        return {"status": "complete", "notes": "seeds already recorded"}

    def _split_stories(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Register one story per seed."""
        okf = Ostler(self.repo)
        epic = SECOND_EPIC if str(data["epic"]).endswith(SECOND_EPIC) else EPIC
        stories = SECOND_STORIES if epic == SECOND_EPIC else STORIES
        existing = {str(s["slug"]) for s in okf.list("story", epic=epic)}
        for slug, title, seed in stories:
            if slug not in existing:
                okf.create_story(epic, slug, title, covers=[seed])
        return {"status": "complete", "notes": f"{len(stories)} stories"}


    def _design_mockup(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        assert "surface_manifest" not in data
        mockup = self.repo / data["story_dir"] / "mockup.html"
        mockup.parent.mkdir(parents=True, exist_ok=True)
        mockup.write_text("<html></html>\n", encoding="utf-8")
        return {"status": "created", "surface": "", "mockup": f"{data['story_dir']}/mockup.html", "notes": "drawn"}

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
        self.unwritten.discard(slug)
        title = dict((s, t) for s, t, _ in (*STORIES, *SECOND_STORIES)).get(slug, slug)
        _write_story_doc(self.repo / data["story_path"], title)
        return {"status": "written", "notes": "rewritten"}

    def _review_inline(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        stage = str(data["stage"])
        self.stage_calls[stage] += 1
        seen = self.stage_calls[stage]
        failing: dict[str, str] = {}
        if stage == "epic-split":
            status = self.review_epics[min(seen, len(self.review_epics)) - 1]
            if status != "approved":
                failing = {"order": "one epic is two"}
        elif stage == "story-split":
            status = self.coverage_verdicts[min(seen, len(self.coverage_verdicts)) - 1]
            if status != "ok":
                failing = {"coverage": "the reset flow is unclaimed"}
        elif stage == "epic-edit-plan":
            status = self.edit_reviews[min(seen, len(self.edit_reviews)) - 1]
            if status != "approved":
                failing = {"plan": "journey drift"}
        else:
            slug = Path(str(data["subject"])).parent.name
            note = self.feedback.pop(slug, "")
            if note:
                assert self.run_dir is not None, "feedback scripted without a run_dir"
                inbox.append(
                    self.run_dir / INBOX_FILE,
                    id=f"{slug}-note",
                    body=note,
                    at="2024-01-01T00:00:00+00:00",
                )
            if slug in self.fail_audit:
                failing = {"journey": f"{slug} cannot be built as written"}
        return verdict(stage, failing)

    def _answer(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        self.questions.append(str(data["question"]))
        if self.escalate:
            return amendment("needs a product call")
        return answer(f"decided for {data['asker']}")

    def _resolve_integrity(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"decision": "answered", "notes": "relinked"}


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


def _latest_ask(text: str) -> str:
    """The questions *this* block asked, not everything the gate file has accumulated."""
    marker = "## Questions from the agent"
    return text.rsplit(marker, 1)[-1] if marker in text else text


def _drive(
    env: RunEnv,
    agent: _Agent,
    *,
    wait_for_answer: Callable[..., Any] | None = None,
    **inputs: Any,
) -> Any:
    """Drive `Author`, optionally scripting an operator gate."""
    def _wait_for_answer(path: Path, **kwargs: Any) -> Any:
        if wait_for_answer is not None:
            return wait_for_answer(path, **kwargs)
        return None

    with patch.object(pyflow_park, "wait_for_answer", _wait_for_answer):
        return drive(Author(**inputs), replace(env, agent_runner=StubRunner(agent)))


def _drive_story_edit(env: RunEnv, agent: _Agent, **inputs: Any) -> Any:
    return drive(StoryEdit(**inputs), replace(env, agent_runner=StubRunner(agent)))


def _drive_epic_edit(env: RunEnv, agent: _Agent, **inputs: Any) -> Any:
    return drive(EpicEdit(**inputs), replace(env, agent_runner=StubRunner(agent)))


def test_every_flat_stage_is_directly_registered() -> None:
    assert {
        "epic-split",
        "epic-author",
        "story-split",
        "story-author",
        "finalize",
    }.issubset(workflow.flows)


def test_the_milestone_stage_is_not_registered() -> None:
    assert "milestone" not in workflow.flows


def test_epic_mode_authors_the_approved_milestone_and_commits_it(
    backlogged: Path, tmp_path: Path
) -> None:
    """The straight-through run: one epic, two stories, both gates green, then the git tail."""
    backlog_before = (backlogged / BACKLOG).read_bytes()
    commits_before = _commit_count(backlogged)
    branch_before = _current_branch(backlogged)
    agent = _Agent(backlogged)
    result = _drive(_env(tmp_path), agent)

    assert agent.counts() == {
        "split-epics": 1,
        "write-epic": 1,
        "split-stories": 1,
        "design-mockup": 2,
        "write-story": 2,
        "review-inline": 4,
    }, agent.counts()
    assert agent.stage_calls == {"epic-split": 1, "story-split": 1, "story": 2}
    split_review = agent.calls.index("review-inline", agent.calls.index("split-stories"))
    assert split_review < agent.calls.index("write-story")
    artifacts = backlogged / "docs/milestones/account-access/artifacts"
    assert (artifacts / "pm-receipt.json").is_file()
    assert (backlogged / EPIC_DIR / "pm-receipt.json").is_file()
    for slug in SLUGS:
        assert (backlogged / EPIC_DIR / "stories" / slug / "pm-receipt.json").is_file()

    assert _stories(backlogged) == {slug: True for slug in SLUGS}
    assert not [
        f for f in Ostler(backlogged).doctor().data["findings"] if f["severity"] == "error"
    ]

    assert (backlogged / BACKLOG).read_bytes() == backlog_before
    milestones = Ostler(backlogged).list("milestone")
    assert len(milestones) == 1
    assert milestones[0]["epics"] == [EPIC]
    assert "status: authored" in (backlogged / MILESTONE).read_text(encoding="utf-8")

    assert _subject(backlogged) == "author: milestone account-access"
    assert _commit_count(backlogged) == commits_before + 1
    assert _current_branch(backlogged) == branch_before
    assert result.committed is True, result

    assert set(agent.cwds) == {str(backlogged)}


def test_epic_mode_stops_before_any_turn_when_no_milestone_is_approved(
    backlogged: Path, tmp_path: Path
) -> None:
    from workhorse.pyflow import WorkflowFailed

    write_milestone(backlogged, status="proposed")
    agent = _Agent(backlogged)

    with pytest.raises(WorkflowFailed, match="no milestone is approved"):
        _drive(_env(tmp_path), agent)

    assert agent.calls == []


def test_epic_mode_stops_before_any_turn_on_a_milestone_readiness_error(
    backlogged: Path, tmp_path: Path
) -> None:
    from workhorse.pyflow import WorkflowFailed

    path = backlogged / MILESTONE
    path.write_text(path.read_text(encoding="utf-8") + "\n## Open Decisions\n\n- x\n", encoding="utf-8")
    agent = _Agent(backlogged)

    with pytest.raises(WorkflowFailed, match="milestone-open-decisions"):
        _drive(_env(tmp_path), agent)

    assert agent.calls == []


def test_epic_mode_skips_mockups_for_seeds_tagged_without_a_frontend_layer(
    backlogged: Path, tmp_path: Path
) -> None:
    """A `backend`-tagged seed removes two agent turns; an untagged one removes none."""
    agent = _Agent(backlogged, backend_seeds=True)

    _drive(_env(tmp_path), agent)

    assert agent.counts()["design-mockup"] == 0, agent.counts()
    assert agent.counts()["write-story"] == 2, agent.counts()
    assert _stories(backlogged) == {slug: True for slug in SLUGS}


def test_author_nodes_use_milestones_when_todo_is_absent(backlogged: Path) -> None:
    okf = Ostler(backlogged)
    okf.create_epic(EPIC, "Accounts")
    _milestone(backlogged, EPIC)
    okf.add_seed(EPIC, "b1", status="researched", summary=SEEDS["b1"],
                 meta={"sourceRecord": "b1"})
    okf.create_story(EPIC, "01-sign-in", "Sign in", covers=["b1"])

    logger = logging.getLogger("test")
    story = backlogged / EPIC_DIR / "stories/01-sign-in/story.md"
    _write_story_doc(story, "Sign in")
    report = validate_artifacts(logger, repo_dir=str(backlogged))

    assert report.ok, report.errors


def test_every_prompt_is_told_the_resolved_paths_not_the_blank_parameters(
    backlogged: Path, tmp_path: Path
) -> None:
    """`epics_dir` and `milestone` reach prompts as what `load_config` resolved."""
    agent = _Agent(backlogged)
    _drive(_env(tmp_path), agent)

    for args in agent.args_for("split-epics"):
        assert args["epics_dir"] == EPICS, args
        assert args["milestone"] == MILESTONE, args
        assert "roadmap" not in args, args
    for args in agent.args_for("write-epic"):
        assert args["milestone"] == MILESTONE, args
        assert args["epic_dir"] == EPIC_DIR, args


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


def test_a_fresh_run_goes_split_epics_stories_then_finalizes(backlogged: Path, tmp_path: Path) -> None:
    agent = _Agent(backlogged, two_epics=True)
    env = _env(tmp_path)

    result = _drive(env, agent)

    kinds = [stem for stem in agent.calls if stem in {"split-epics", "write-epic", "split-stories", "write-story"}]
    assert kinds == [
        "split-epics",
        "write-epic",
        "write-epic",
        "split-stories",
        "split-stories",
        "write-story",
        "write-story",
        "write-story",
    ], agent.calls
    assert [args["story_slug"] for args in agent.args_for("write-story")] == [
        *SLUGS,
        *SECOND_SLUGS,
    ]
    assert set(_work_rows(env.writer.run_dir).values()) == {"done"}
    assert result.committed is True, result


def test_a_run_stopped_at_a_later_epic_story_resumes_without_redoing_settled_rows(
    backlogged: Path, tmp_path: Path
) -> None:
    first = _Agent(backlogged, two_epics=True, explode={"01-edit-profile"})
    env = _env(tmp_path)
    run_dir = env.writer.run_dir
    with pytest.raises(RuntimeError, match="killed while writing 01-edit-profile"):
        _drive(env, first)

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    second = _Agent(backlogged, two_epics=True)
    result = drive(
        Author(**resume.inputs),
        replace(_env(tmp_path, run_dir=run_dir), agent_runner=StubRunner(second)),
        resume,
    )

    assert second.counts()["write-story"] == 1, second.counts()
    assert second.counts()["write-epic"] == 0, second.counts()
    assert second.counts()["split-stories"] == 0, second.counts()
    assert set(_work_rows(run_dir).values()) == {"done"}
    assert result.committed is True, result


def test_the_commit_leaves_work_the_run_did_not_do_alone(
    backlogged: Path, tmp_path: Path, write: Callable[[Path, str], Path]
) -> None:
    """The run commits the docs it authored, not the working tree it found."""
    stray = write(backlogged / "src/half_finished.py", "def in_progress(): ...\n")

    _drive(_env(tmp_path), _Agent(backlogged))

    assert _subject(backlogged) == "author: milestone account-access"
    committed = subprocess.run(
        ["git", "show", "--name-only", "--pretty=format:", "HEAD"],
        cwd=backlogged,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert committed, "the run committed nothing at all"
    assert all(p.startswith("docs/") or p == ".agents/ids.json" for p in committed), committed
    assert ".agents/ids.json" in committed, committed
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
    """`validate_story` is deterministic, so the rework loop needs no scripted verdict."""
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
    """The give-up arm advances the queue, then the completion gate asks before the run finishes."""
    seen: list[str] = []

    def answered(path: Path, **kwargs: Any) -> None:
        if path != backlogged / CONTEXT:
            return
        seen.append(path.read_text())
        agent.fail_audit.clear()
        path.write_text(seen[-1] + "\nRewrite the acceptance criteria shorter.\n")

    agent = _Agent(backlogged, fail_audit={"01-sign-in"})

    with caplog.at_level(logging.WARNING):
        result = _drive(_env(tmp_path), agent, wait_for_answer=answered)

    assert any("parking story '01-sign-in'" in r.message for r in caplog.records), caplog.text
    assert any("remains blocked" in r.message for r in caplog.records)
    written = [args["story_slug"] for args in agent.args_for("write-story")]
    assert written.index("02-reset-password") < len(written) - 1, written
    assert len(seen) == 1 and f"story {EPIC_NAME}/01-sign-in: blocked" in seen[0], seen
    last = agent.args_for("write-story")[-1]
    assert last["story_slug"] == "01-sign-in"
    assert last["note"] == "Rewrite the acceptance criteria shorter."
    assert agent.args_for("write-story")[0]["note"] == ""
    assert _stories(backlogged) == {slug: True for slug in SLUGS}
    assert result.committed is True, result


class _Stop(Exception):
    pass


def _gate_then_stop(seen: list[str]) -> Callable[..., Any]:
    def answered(path: Path, **kwargs: Any) -> None:
        if path.name != "_author-context.md":
            return
        seen.append(path.read_text())
        raise _Stop

    return answered


def _status(repo: Path) -> str:
    return next(
        line for line in (repo / MILESTONE).read_text(encoding="utf-8").splitlines()
        if line.startswith("status:")
    )


def _work_rows(run_dir: Path) -> dict[str, str]:
    items = WorkList(JsonBackend(run_dir / WORK_FILE)).items()
    return {item.id: item.status for item in items}


def test_an_audit_blocked_story_stops_at_the_completion_gate_and_nothing_finalizes(
    backlogged: Path, tmp_path: Path
) -> None:
    seen: list[str] = []
    agent = _Agent(backlogged, fail_audit={"01-sign-in"})
    env = _env(tmp_path)

    with pytest.raises(_Stop):
        _drive(env, agent, wait_for_answer=_gate_then_stop(seen))

    assert len(seen) == 1, seen
    assert f"story {EPIC_NAME}/01-sign-in: blocked" in seen[0]
    assert f"{EPIC_NAME}/02-reset-password" not in seen[0]
    assert _status(backlogged) != "status: authored"
    assert _work_rows(env.writer.run_dir)[f"{EPIC_NAME}/01-sign-in"] == "blocked"


def test_a_story_without_its_mockup_is_listed_at_the_completion_gate_with_the_reason(
    backlogged: Path, tmp_path: Path
) -> None:
    seen: list[str] = []

    class _Undrawn(_Agent):
        def _design_mockup(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
            if str(data["story_slug"]) == "01-sign-in":
                return {"status": "failed", "surface": "", "mockup": "", "notes": "no style to copy"}
            return super()._design_mockup(data, nth)

    agent = _Undrawn(backlogged)
    env = _env(tmp_path)

    with pytest.raises(_Stop):
        _drive(env, agent, wait_for_answer=_gate_then_stop(seen))

    assert f"story {EPIC_NAME}/01-sign-in: blocked" in seen[0], seen
    assert "no mockup for a story with a UI service: no style to copy" in seen[0]
    assert agent.counts()["write-story"] == 1, agent.counts()
    assert _work_rows(env.writer.run_dir)[f"{EPIC_NAME}/01-sign-in"] == "blocked"
    assert _status(backlogged) != "status: authored"


def test_an_edit_to_the_milestone_body_ends_at_the_contract_gate(
    backlogged: Path, tmp_path: Path
) -> None:
    seen: list[str] = []

    class _Editing(_Agent):
        def _write_epic(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
            path = self.repo / MILESTONE
            path.write_text(path.read_text(encoding="utf-8") + "\nOne more journey.\n", encoding="utf-8")
            return super()._write_epic(data, nth)

    with pytest.raises(_Stop):
        _drive(_env(tmp_path), _Editing(backlogged), wait_for_answer=_gate_then_stop(seen))

    assert len(seen) == 1 and "milestone body changed" in seen[0], seen
    assert _status(backlogged) != "status: authored"


def test_accepting_a_changed_contract_finishes_the_run(backlogged: Path, tmp_path: Path) -> None:
    seen: list[str] = []

    class _Editing(_Agent):
        def _write_epic(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
            path = self.repo / MILESTONE
            path.write_text(path.read_text(encoding="utf-8") + "\nOne more journey.\n", encoding="utf-8")
            return super()._write_epic(data, nth)

    def accepted(path: Path, **kwargs: Any) -> None:
        if path.name == "_author-context.md":
            seen.append(path.read_text())

    result = _drive(_env(tmp_path), _Editing(backlogged), wait_for_answer=accepted)

    assert len(seen) == 1, seen
    assert result.committed is True, result
    assert _status(backlogged) == "status: authored"


def test_auto_mode_does_not_skip_the_completion_gate(backlogged: Path, tmp_path: Path) -> None:
    seen: list[str] = []
    agent = _Agent(backlogged, fail_audit={"01-sign-in"})

    with pytest.raises(_Stop):
        _drive(_env(tmp_path), agent, wait_for_answer=_gate_then_stop(seen), operator_mode="auto")

    assert len(seen) == 1, seen


def test_an_operator_note_dropped_mid_run_reworks_the_story_once(
    backlogged: Path, tmp_path: Path
) -> None:
    """`check_story_feedback` never blocks, and consuming the inbox is what bounds it."""
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
    assert note["validation_errors"] == "", note
    messages = inbox.all_messages(env.writer.run_dir / INBOX_FILE)
    assert len(messages) == 1, messages
    assert messages[0].reply, messages
    assert agent.stage_calls["story"] == 3, agent.stage_calls


def test_a_coverage_gap_re_enters_the_split_with_the_worklist(
    backlogged: Path, tmp_path: Path
) -> None:
    """The coverage loop's notes travel to `split_stories` as its `rework_notes`."""
    agent = _Agent(backlogged, coverage_verdicts=["gaps", "ok"])
    _drive(_env(tmp_path), agent)

    assert agent.counts()["split-stories"] == 2, agent.counts()
    first, second = agent.args_for("split-stories")
    assert first["rework_notes"] == "", first
    assert "reset flow" in second["rework_notes"], second
    assert agent.stage_calls["story-split"] == 2, agent.stage_calls


def test_a_split_the_pm_never_passes_stops_at_the_completion_gate(
    backlogged: Path, tmp_path: Path
) -> None:
    seen: list[str] = []
    agent = _Agent(backlogged, coverage_verdicts=["gaps"])
    env = _env(tmp_path)

    with pytest.raises(_Stop):
        _drive(env, agent, wait_for_answer=_gate_then_stop(seen))

    assert agent.counts()["split-stories"] == 4, agent.counts()
    assert agent.counts()["write-story"] == 0, agent.counts()
    assert len(seen) == 1 and "the reset flow is unclaimed" in seen[0], seen
    assert "blocked" in _work_rows(env.writer.run_dir).values()


def test_an_epic_split_the_pm_never_passes_asks_the_operator_then_splits_again(
    backlogged: Path, tmp_path: Path
) -> None:
    seen: list[str] = []
    agent = _Agent(backlogged, review_epics=["needs_rework"] * 4)

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text())
        agent.review_epics = ["approved"]

    _drive(_env(tmp_path), agent, wait_for_answer=answered)

    assert agent.counts()["rework-epic-split"] == 3, agent.counts()
    assert agent.counts()["split-epics"] == 2, agent.counts()
    assert "one epic is two" in seen[0], seen
    assert agent.counts()["answer"] == 0, agent.counts()
    assert _subject(backlogged) == "author: milestone account-access"


def test_a_blocked_epic_split_writer_is_answered_by_the_pm_and_the_answer_is_kept(
    backlogged: Path, tmp_path: Path
) -> None:
    agent = _Agent(backlogged, block={"split-epics"})

    _drive(_env(tmp_path), agent)

    assert agent.counts()["answer"] == 1, agent.counts()
    assert agent.counts()["split-epics"] == 2, agent.counts()
    assert agent.questions == ["which order?"]
    assert "You asked: which order?" in agent.args_for("split-epics")[1]["note"]
    ledger = backlogged / "docs/milestones/account-access/grills/pm.md"
    assert "decided for epic-split" in ledger.read_text(encoding="utf-8")
    assert _subject(backlogged) == "author: milestone account-access"


def test_a_question_only_the_operator_can_settle_waits_on_the_run_gate(
    backlogged: Path, tmp_path: Path
) -> None:
    seen: list[Path] = []

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path)
        path.write_text(path.read_text() + "\nSign in comes first.\n")

    agent = _Agent(backlogged, block={"write-story"}, escalate=True)
    _drive(_env(tmp_path), agent, wait_for_answer=answered)

    assert seen == [backlogged / CONTEXT], seen
    assert agent.counts()["answer"] == 1, agent.counts()
    retry = [a for a in agent.args_for("write-story") if a["note"]]
    assert retry and "Sign in comes first." in retry[0]["note"], retry
    ledger = backlogged / "docs/milestones/account-access/grills/pm.md"
    assert "Sign in comes first." in ledger.read_text(encoding="utf-8")
    assert _stories(backlogged) == {slug: True for slug in SLUGS}


def test_story_mode_promotes_an_open_record_and_does_not_commit_the_code_repo(
    with_records: Path, artifacts: Path, tmp_path: Path
) -> None:
    before = _commit_count(with_records)
    filed_subjects = _artifact_subjects(artifacts)
    agent = _Agent(with_records)
    result = _drive(
        _env(tmp_path), agent, mode="story", epic=EPIC, record="b1", services="account"
    )

    assert agent.counts() == {
        "design-mockup": 1,
        "write-story": 1,
        "review-inline": 1,
    }, agent.counts()

    stories = _stories(with_records)
    assert list(stories) == [B1_SLUG], stories
    assert all(stories.values()), stories
    story = next(row for row in Ostler(with_records).list("story") if row["slug"] == B1_SLUG)
    assert story["covers"] == ["b1"]
    seed = next(row for row in Ostler(with_records).list("seed", epic=EPIC) if row["id"] == "b1")
    assert seed["sourceRecord"] == "b1"
    assert seed["summary"] == SEEDS["b1"]
    assert f"{SEEDS['b1']}\n\n{B1_BODY}" in (with_records / EPIC_DIR / "epic.md").read_text(encoding="utf-8")
    closed = _filed(artifacts, "b1")
    assert closed.status == "promoted"
    assert closed.reason == f"promoted to story {B1_SLUG} in epic {EPIC}"
    assert _filed(artifacts, "b2").status == "open"
    assert result.record_id == "b1", result
    assert _artifact_subjects(artifacts) == ["chore(acme): close b1 as promoted", *filed_subjects]
    assert _commit_count(with_records) == before, "story mode must not commit"


def test_story_mode_picks_a_record_by_its_short_handle(
    with_records: Path, artifacts: Path, tmp_path: Path
) -> None:
    long_id = "ACME-01JBXR7K9QZ4M2T8VNF3HD6PWC"
    Ostler(with_records).backlog_add(
        "Export the account data", repo="acme", area="accounts", record_id=long_id
    )

    handle = ids.table(ids.known(Ostler(with_records).graph))[long_id]
    assert handle != long_id

    _drive(_env(tmp_path), _Agent(with_records), mode="story", epic=EPIC, record=handle)

    assert _filed(artifacts, long_id).status == "promoted"


def test_story_mode_refuses_a_token_that_names_no_record(
    with_records: Path, artifacts: Path, tmp_path: Path
) -> None:
    with pytest.raises(WorkflowFailed, match="no-such-record"):
        _drive(_env(tmp_path), _Agent(with_records), mode="story", epic=EPIC, record="no-such-record")

    assert _stories(with_records) == {}


def test_story_mode_refuses_a_record_that_is_not_open(
    with_records: Path, artifacts: Path, tmp_path: Path
) -> None:
    assert Ostler(with_records).close_record("b2", "done", "fixed in acme@abc1234").ok

    with pytest.raises(WorkflowFailed, match="b2"):
        _drive(_env(tmp_path), _Agent(with_records), mode="story", epic=EPIC, record="b2")

    assert _stories(with_records) == {}
    assert _filed(artifacts, "b2").status == "done"


def test_story_mode_takes_no_literal_text(
    with_records: Path, artifacts: Path, tmp_path: Path
) -> None:
    with pytest.raises(WorkflowFailed, match="Users can sign in"):
        _drive(
            _env(tmp_path), _Agent(with_records), mode="story", epic=EPIC,
            record="Users can sign in with a passkey",
        )

    assert _stories(with_records) == {}


def test_story_mode_resumed_after_the_close_fails_nothing_and_commits_nothing_more(
    with_records: Path, artifacts: Path, tmp_path: Path, logger: logging.Logger
) -> None:
    _drive(_env(tmp_path), _Agent(with_records), mode="story", epic=EPIC, record="b1")
    subjects = _artifact_subjects(artifacts)

    again = seed_story(logger, epic=EPIC, record="b1", repo_dir=str(with_records))
    closed = promote_record(
        logger, record_id="b1", epic=EPIC, story=again.story_slug, repo_dir=str(with_records)
    )

    assert again.story_slug == B1_SLUG
    assert closed.record_id == "b1"
    assert _artifact_subjects(artifacts) == subjects
    assert list(_stories(with_records)) == [B1_SLUG]


def test_story_mode_refuses_an_epic_that_does_not_exist(backlogged: Path, tmp_path: Path) -> None:
    """`seed_story` never scaffolds an epic — a missing one is a hard, actionable failure."""
    with pytest.raises(WorkflowFailed, match="does not exist"):
        _drive(_env(tmp_path), _Agent(backlogged), mode="story", epic="nope", record="b1")


def test_story_edit_add_resolves_a_record_into_its_edit_intent(
    with_records: Path, logger: logging.Logger
) -> None:
    intent = resolve_story_intent(
        logger, "add", epic=EPIC, record="b1", repo_dir=str(with_records)
    )

    assert intent.kind == "add-story"
    assert intent.record_id == "b1"
    assert intent.summary == SEEDS["b1"]
    assert intent.body == B1_BODY


def test_story_edit_add_refuses_a_token_that_names_no_record(
    with_records: Path, logger: logging.Logger
) -> None:
    with pytest.raises(WorkflowFailed, match="no-such-record"):
        resolve_story_intent(
            logger, "add", epic=EPIC, record="no-such-record", repo_dir=str(with_records)
        )


def test_story_edit_add_authors_one_story_and_promotes_its_record(
    with_records: Path, artifacts: Path, tmp_path: Path
) -> None:
    agent = _Agent(with_records)

    _drive_story_edit(_env(tmp_path), agent, action="add", epic=EPIC, record="b1")

    stories = _stories(with_records)
    assert list(stories) == [B1_SLUG], stories
    assert all(stories.values()), stories
    closed = _filed(artifacts, "b1")
    assert closed.status == "promoted"
    assert closed.reason == f"promoted to story {B1_SLUG} in epic {EPIC}"
    assert _filed(artifacts, "b2").status == "open"
    assert _subject(with_records).startswith("author: accounts"), _subject(with_records)


def test_epic_edit_add_story_from_a_record_closes_it_as_promoted(
    with_records: Path, artifacts: Path, tmp_path: Path
) -> None:
    intent = EditIntent(
        kind="add-story", epic=EPIC, record_id="b1", summary=SEEDS["b1"], body=B1_BODY,
        change=f"Add a story for {SEEDS['b1']}",
    )

    _drive_epic_edit(_env(tmp_path), _Agent(with_records), intent=intent)

    closed = _filed(artifacts, "b1")
    assert closed.status == "promoted"
    assert closed.reason == f"promoted to story {B1_SLUG} in epic {EPIC}"


def test_the_epic_edit_planner_reads_the_register_listing_of_a_filed_record(
    with_records: Path, tmp_path: Path
) -> None:
    agent = _Agent(with_records)
    intent = EditIntent(
        kind="add-story", epic=EPIC, record_id="b1", summary=SEEDS["b1"], body=B1_BODY,
        change=f"Add a story for {SEEDS['b1']}",
    )

    _drive_epic_edit(_env(tmp_path), agent, intent=intent)

    variables = agent.args_for("plan-epic-edit")[0]
    lines = variables["register_listing"].splitlines()
    assert "b1\tacme\taccounts\topen\tuntriaged\t" + SEEDS["b1"] in lines
    assert "b2\tacme\taccounts\topen\tuntriaged\t" + SEEDS["b2"] in lines
    assert "backlog" not in variables


def test_the_epic_edit_planner_is_told_when_the_register_is_empty(
    with_epic: Path, artifacts: Path, tmp_path: Path
) -> None:
    okf = Ostler(with_epic)
    assert okf.add_seed(
        EPIC, "interactive", status="researched", summary="Interactive",
        meta={"services": ["api-service"]},
    ).ok
    assert okf.create_story(
        EPIC, "interactive-editor", "Interactive editor", covers=["interactive"]
    ).ok
    _write_story_doc(
        with_epic / EPIC_DIR / "stories/interactive-editor/story.md", "Interactive editor"
    )
    _commit(with_epic, "interactive editor")
    plan = {
        "status": "complete",
        "epic": EPIC,
        "summary": "add raw XML editing",
        "journey_changes": ["Add raw XML mode"],
        "seed_changes": [{
            "action": "add", "id": "raw-xml", "status": "researched",
            "summary": "Edit canonical XML", "services": ["api-service"],
        }],
        "story_changes": [{
            "action": "add", "slug": "raw-xml-editor", "title": "Raw XML editor",
            "covers": ["raw-xml"], "depends": ["interactive-editor"], "rewrite": True,
        }],
        "affected_stories": ["raw-xml-editor"],
    }
    agent = _Agent(with_epic, edit_plans=[plan])

    _drive_epic_edit(_env(tmp_path), agent, epic=EPIC, change="Add raw XML editing")

    assert agent.args_for("plan-epic-edit")[0]["register_listing"] == "no open records"


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
    assert okf.add_seed(
        EPIC, "keep", status="researched", summary="Keep", meta={"services": ["api-service"]}
    ).ok
    assert okf.add_seed(
        EPIC, "remove", status="researched", summary="Remove", meta={"services": ["api-service"]}
    ).ok
    assert okf.create_story(EPIC, "keep-story", "Keep", covers=["keep"]).ok
    assert okf.create_story(EPIC, "remove-story", "Remove", covers=["remove"]).ok
    _write_story_doc(
        with_epic / EPIC_DIR / "stories/keep-story/story.md", "Keep", services=("api-service",)
    )
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


def test_epic_edit_static_findings_drive_a_replacement_plan(
    with_epic: Path, tmp_path: Path
) -> None:
    okf = Ostler(with_epic)
    assert okf.add_seed(
        EPIC, "interactive", status="researched", summary="Interactive",
        meta={"services": ["api-service"]},
    ).ok
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
            "services": ["api-service"],
            "source_record": "",
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

    with patch.object(pyflow_park, "wait_for_answer", answered):
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


def test_survey_mode_runs_the_surveyor_and_stops_at_discovery(
    backlogged: Path, tmp_path: Path, write: Callable[[Path, str], Path]
) -> None:
    """`handoff`: the sub-flow runs on the parent's env and returns its discovery output."""
    write(backlogged / RUBRIC, "# Accessibility rubric\n\nEvery control needs a name.\n")
    write(backlogged / BUTTON / "index.tsx", "export const Button = () => <button />\n")
    _commit(backlogged, "a rubric and one component")

    agent = _Agent(backlogged)
    _drive(_env(tmp_path), agent, mode="survey")

    assert agent.counts()["plan-units"] == 1, agent.counts()
    assert agent.counts()["assess-unit"] == 1, agent.counts()
    assert agent.counts()["partition-findings"] == 1, agent.counts()

    assert (backlogged / RULES).is_file()
    assert (backlogged / INVENTORY).is_file()
    assert (backlogged / FINDINGS / f"{record_slug(BUTTON)}.md").is_file()
    assert (backlogged / PARTITION).is_file()
    assert any(CLUSTER in line for line in (backlogged / BACKLOG).read_text().splitlines())

    assert _subject(backlogged) == "a rubric and one component"
    assert _stories(backlogged) == {}


def test_a_run_killed_mid_story_resumes_on_that_story_alone(
    backlogged: Path, tmp_path: Path
) -> None:
    """The story loop's state is the story documents, not the machine."""
    first = _Agent(backlogged, explode={"02-reset-password"})
    env = _env(tmp_path)
    run_dir = env.writer.run_dir
    with pytest.raises(RuntimeError, match="killed while writing 02-reset-password"):
        _drive(env, first)

    assert first.counts()["write-story"] == 2, first.counts()
    assert _stories(backlogged) == {"01-sign-in": True, "02-reset-password": False}

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "author_story", resume
    assert [item["id"] for item in resume.params["items"]] == [f"{EPIC_NAME}/02-reset-password"]
    assert resume.flow == "Author", resume

    second = _Agent(backlogged)
    result = drive(
        Author(**resume.inputs),
        replace(_env(tmp_path, run_dir=run_dir), agent_runner=StubRunner(second)),
        resume,
    )

    assert second.counts() == {
        "write-story": 1,
        "review-inline": 1,
    }, second.counts()
    assert _stories(backlogged) == {slug: True for slug in SLUGS}
    assert result.committed is True, result


def test_the_labels_name_the_story_and_the_epic(backlogged: Path, tmp_path: Path) -> None:
    """The YAML's `labels:` block read `get_node_output('select_story', …)`; here `labels()` reads `self.output(select_story)` and takes no parameters."""
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
    assert stamped[0] == {"work_id": "account-access"}, stamped[0]
    assert {labels["work_id"] for labels in stamped} >= {
        "account-access", EPIC_NAME, *SLUGS,
    }, stamped
    assert any(labels.get("progress") for labels in stamped), stamped
    assert any(labels.get("story_split.reworks") == "0" for labels in stamped), stamped
    assert any(labels.get("story_split.answers") == "0" for labels in stamped), stamped
    assert not any(k.startswith("wf.") for labels in seen for k in labels), seen

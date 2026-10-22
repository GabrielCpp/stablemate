"""What the author's main graph validates: its node returns, and its agent replies."""
from __future__ import annotations


from workhorse_workflows.author.shared.schemas._base import AuthorResult
from workhorse.pyflow import dry_run


class Config(AuthorResult):
    """`load_config` — the author's paths, decided once at the top of the run."""

    repo_root: str = ""
    backlog_path: str = ""
    milestone_path: str = ""
    milestone_mockups_dir: str = ""
    milestone_dir: str = ""
    pm_ledger: str = ""
    epics_dir: str = ""
    services_dir: str = ""
    layers: list[str] = []


class RunContext(Config):
    """The author's `self.ctx` — the paths `load_config` resolved."""


class Filled(AuthorResult):
    """`fill_work` — what one kind's fill filed on the run's work list."""

    kind: str = ""
    filed: int = 0
    done: int = 0


class ContractDigest(AuthorResult):
    """`contract_digest` — the sha256 of the milestone body, the contract the run authors from."""

    digest: str = ""


class UnfinishedRow(AuthorResult):
    """One work-list row the run has not finished."""

    kind: str = ""
    id: str = ""
    status: str = ""
    laps: int = 0
    note: str = ""


@dry_run(matches=True)
class Completion(AuthorResult):
    """`check_completion` — whether the contract held, and every row the run left unfinished."""

    matches: bool = True
    digest: str = ""
    unfinished: list[UnfinishedRow] = []


class StoryChoice(AuthorResult):
    """`select_affected_story` — the next story of this epic that still needs authoring."""

    has_story: bool = False
    story_path: str = ""
    story_slug: str = ""
    story_dir: str = ""
    reason: str = ""
    progress: str = ""
    remaining_count: int = 0


class SeededStory(AuthorResult):
    """`seed_story` — story mode's single story, created from one backlog bullet."""

    epic_dir: str = ""
    story_slug: str = ""
    story_dir: str = ""
    story_path: str = ""
    bullet_id: str = ""
    from_backlog: bool = False
    reason: str = ""


@dry_run(ok=True)
class Defects(AuthorResult):
    """The four validators' shared shape: does it hold, and if not, what is wrong."""

    ok: bool = False
    errors: str = ""


class MilestoneStatus(AuthorResult):
    """The durable milestone lifecycle state after Author's final transition."""

    path: str = ""
    status: str = ""


class VerifyReport(AuthorResult):
    """The two tri-state verifiers: `verify_reconcile` and `verify_integrity`."""

    holds: bool = False
    skipped: bool = False
    errors: str = ""
    report: str = ""


class Feedback(AuthorResult):
    """`check_story_feedback` — an un-consumed operator note dropped into the run's inbox."""

    present: bool = False
    scope: str = "story"
    content: str = ""


class Pruned(AuthorResult):
    """`prune_bullet` — the one story-mode backlog bullet removed after authoring."""

    removed: int = 0
    remaining: int = 0


class Ledger(AuthorResult):
    """`record_attempt` — the failed-approach ledger the rework prompt must not repeat."""

    prior_attempts: str = ""
    ledger: str = ""


class Committed(AuthorResult):
    """`commit_author` / `commit_incomplete` — whether a commit was actually made."""

    committed: bool = False


@dry_run(status="complete")
class WriteEpicResult(AuthorResult):
    """`main/prompts/write-epic.md` — one epic's `epic.md` written from its seeds."""

    status: str = ""
    notes: str = ""


@dry_run(status="complete")
class StorySplit(AuthorResult):
    """`main/prompts/split-stories.md` — an epic's seeds grouped into story-sized units."""

    status: str = ""
    notes: str = ""


@dry_run(status="skipped")
class MockupResult(AuthorResult):
    """`<flow>/prompts/design-mockup.md` — the surface sketch a UI story is written against."""

    status: str = ""
    surface: str = ""
    mockup: str = ""
    notes: str = ""


class MockupGate(AuthorResult):
    """Whether the story touches a surface somebody has to design."""

    required: bool = True
    services: list[str] = []
    evidence: str = ""


@dry_run(status="written")
class WriteStoryResult(AuthorResult):
    """`<flow>/prompts/write-story.md` and `<flow>/prompts/rework-story.md` — one story written."""

    status: str = ""
    notes: str = ""


__all__ = [
    "Committed",
    "Completion",
    "Config",
    "ContractDigest",
    "Defects",
    "Feedback",
    "Filled",
    "Ledger",
    "MockupGate",
    "MilestoneStatus",
    "MockupResult",
    "Pruned",
    "RunContext",
    "SeededStory",
    "StoryChoice",
    "StorySplit",
    "UnfinishedRow",
    "VerifyReport",
    "WriteEpicResult",
    "WriteStoryResult",
]

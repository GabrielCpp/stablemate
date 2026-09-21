"""What the author's main graph validates: its node returns, and its agent replies."""
from __future__ import annotations

from typing import Literal

from workhorse_workflows.author.shared.schemas._base import AuthorResult



class Config(AuthorResult):
    """`load_config` — the author's paths, decided once at the top of the run."""

    repo_root: str = ""
    backlog_path: str = ""
    roadmap_path: str = ""
    epics_dir: str = ""
    features_dir: str = ""
    layers: list[str] = []


class RunContext(Config):
    """The author's `self.ctx` — the paths `load_config` resolved."""


class AuthorStep(AuthorResult):
    """The one artifact-derived unit the flat author planner should run next."""

    kind: Literal[
        "milestone",
        "epic-split",
        "epic-author",
        "story-split",
        "story-author",
        "finalize",
    ] = "milestone"
    roadmap: str = ""
    epic: str = ""
    story: str = ""
    reason: str = ""


class EpicChoice(AuthorResult):
    """`select_epic` — the next unauthored epic, or that none is left."""

    has_epic: bool = False
    epic: str = ""
    epic_dir: str = ""
    reason: str = ""
    progress: str = ""


class StoryChoice(AuthorResult):
    """`select_story` — the next story of this epic that still needs authoring."""

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


class StoryMutation(AuthorResult):
    """A standalone story graph edit made outside the main author loop."""

    changed: bool = False
    epic: str = ""
    story_slug: str = ""
    story_dir: str = ""
    story_path: str = ""
    reason: str = ""


class Defects(AuthorResult):
    """The four validators' shared shape: does it hold, and if not, what is wrong."""

    ok: bool = False
    errors: str = ""


class RoadmapStatus(AuthorResult):
    """The durable roadmap lifecycle state after Author's final transition."""

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




class WriteEpicResult(AuthorResult):
    """`main/prompts/write-epic.md` — one epic's `epic.md` written from its seeds."""

    status: str = ""
    notes: str = ""


class StorySplit(AuthorResult):
    """`main/prompts/split-stories.md` — an epic's seeds grouped into story-sized units."""

    status: str = ""
    notes: str = ""


class MockupResult(AuthorResult):
    """`<flow>/prompts/design-mockup.md` — the surface sketch a UI story is written against."""

    status: str = ""
    surface: str = ""
    mockup: str = ""
    notes: str = ""


class MockupGate(AuthorResult):
    """Whether the story touches a surface somebody has to design."""

    required: bool = True
    layers: list[str] = []
    services: list[str] = []
    evidence: str = ""


class WriteStoryResult(AuthorResult):
    """`<flow>/prompts/write-story.md` and `<flow>/prompts/rework-story.md` — one story written."""

    status: str = ""
    notes: str = ""


class AuditFinding(AuthorResult):
    """One defect the story auditor is willing to fail the story over."""

    id: str = ""
    kind: Literal["journey", "chrome", "transient-feedback", "grounding"] = "grounding"
    target: str = ""
    issue: str = ""
    repair: str = ""


class AuditResult(AuthorResult):
    """`<flow>/prompts/audit-story.md` — the story read back against its epic and seeds."""

    status: str = ""
    findings: list[AuditFinding] = []
    notes: str = ""


class CoverageReview(AuthorResult):
    """`<flow>/prompts/review-coverage.md` — every seed accounted for by some story."""

    status: str = ""
    notes: str = ""


__all__ = [
    "AuditFinding",
    "AuditResult",
    "AuthorStep",
    "Committed",
    "Config",
    "CoverageReview",
    "Defects",
    "EpicChoice",
    "Feedback",
    "Ledger",
    "MockupGate",
    "MockupResult",
    "Pruned",
    "RoadmapStatus",
    "RunContext",
    "SeededStory",
    "StoryMutation",
    "StoryChoice",
    "StorySplit",
    "VerifyReport",
    "WriteEpicResult",
    "WriteStoryResult",
]

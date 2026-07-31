"""What the author's main graph validates: its node returns, and its agent replies.

Same convention as `survey`: every `*_ok` / `has_*` / `committed` output was a
`"yes"`/`"no"` **string** in the YAML, because a `branch` node compares rendered text.
A Python state branches with `if`, so these are `bool` — the strings were an artifact of
the engine, and nothing on disk carried them.

Two names differ from the YAML's outputs, both to avoid a collision inside one package:
`StorySplit` (the YAML's `split_result`) is not survey's `SplitResult`, and the
tri-state verifiers share one `VerifyReport` rather than carrying
`reconcile_*`/`integrity_*` field names twice.
"""
from __future__ import annotations

from workhorse_workflows.author.shared.schemas._base import AuthorResult

# ── node returns ────────────────────────────────────────────────────────────


class Config(AuthorResult):
    """`load_config` — the author's paths, decided once at the top of the run.

    Every path but `repo_root` is **repo-relative**, exactly as the script emitted it,
    so a `cfg` checkpointed on one machine still resolves on another.
    """

    repo_root: str = ""
    backlog_path: str = ""
    epics_dir: str = ""
    surface_manifest: str = ""
    features_dir: str = ""
    mockup_dir: str = ""
    layers: list[str] = []


class Branches(AuthorResult):
    """`branch_author` — the branch the run works on, and the one it forked from.

    A blank `author_branch` means "no branch was created" (no `.git`, or the checkout
    failed): the run still authors, it just commits on whatever branch it is on.
    """

    base_branch: str = "main"
    author_branch: str = ""


class RunContext(Config):
    """The author's `self.ctx` — `load_config`'s paths plus the branch decision.

    Written once by `setup()`, restored verbatim on resume. Anything that changes as
    the run progresses is a state parameter instead, not a field here.
    """

    base_branch: str = "main"
    author_branch: str = ""


class EpicChoice(AuthorResult):
    """`select_epic` — the next unauthored epic, or that none is left.

    `has_epic` false is not a failure: an empty todo means the backlog is fully
    decomposed, and the flow moves on to the whole-repo checks.
    """

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


class Defects(AuthorResult):
    """The four validators' shared shape: does it hold, and if not, what is wrong.

    `validate_story`, `check_story_grounding`, `validate_coverage` and
    `validate_artifacts` all emitted exactly this pair under their own two names.
    `errors` is the operator- and agent-facing text, one finding per line.
    """

    ok: bool = False
    errors: str = ""


class VerifyReport(AuthorResult):
    """The two tri-state verifiers: `verify_reconcile` and `verify_integrity`.

    The YAML's `yes`/`no`/`skip` is two booleans here. `skipped` true means the check
    could not run (no baseline ref, ostler unusable) and the flow proceeds — these are
    fail-open by design, since a missing baseline is not a defect in the epics.
    `report` is the multi-line preamble the resolver prompt reads.
    """

    holds: bool = False
    skipped: bool = False
    errors: str = ""
    report: str = ""


class Feedback(AuthorResult):
    """`check_story_feedback` — an operator note left in the story's `feedback.md`.

    Reading it **consumes** it: the file's `STATUS:` line is flipped to `CONSUMED`
    before the flow acts, so the same note cannot loop the story forever.
    """

    present: bool = False
    scope: str = "story"
    content: str = ""


class Pruned(AuthorResult):
    """`prune_bullet` and `prune_backlog` — bullets removed once they are covered."""

    removed: int = 0
    remaining: int = 0


class Ledger(AuthorResult):
    """`record_attempt` — the failed-approach ledger the rework prompt must not repeat."""

    prior_attempts: str = ""
    ledger: str = ""


class Committed(AuthorResult):
    """`commit_author` / `commit_incomplete` — whether a commit was actually made."""

    committed: bool = False


class PullRequest(AuthorResult):
    """`open_author_pr` — the PR, or why there is none.

    `author_pr` is `opened`, `exists`, `skipped` or blank; a skip is an ordinary
    outcome (no remote, no token, no branch), not a failure.
    """

    author_pr: str = ""
    pr_url: str = ""
    pr_skip_reason: str = ""


# ── agent replies ───────────────────────────────────────────────────────────


class DecomposeResult(AuthorResult):
    """`prompts/decompose-epics.md` and `prompts/rework-epics.md` — the backlog split.

    Both prompts return under the YAML's one `decompose_result` key, so both return
    this: the rework pass is the same product, re-derived against review notes.
    """

    status: str = ""
    notes: str = ""


class EpicReview(AuthorResult):
    """`prompts/review-epics.md` — the decomposition reviewed before any story lands."""

    status: str = ""
    notes: str = ""


class WriteEpicResult(AuthorResult):
    """`prompts/write-epic.md` — one epic's `epic.md` written from its seeds."""

    status: str = ""
    notes: str = ""


class StorySplit(AuthorResult):
    """`prompts/split-stories.md` — an epic's seeds grouped into story-sized units.

    `status` `standoff` is the splitter refusing the rework it was asked for; that
    escalates to the coverage gate, where the resolver can see both sides.
    """

    status: str = ""
    notes: str = ""


class MockupResult(AuthorResult):
    """`prompts/design-mockup.md` — the surface sketch a UI story is written against."""

    status: str = ""
    surface: str = ""
    mockup: str = ""
    notes: str = ""


class WriteStoryResult(AuthorResult):
    """`prompts/write-story.md` and `prompts/rework-story.md` — one story written."""

    status: str = ""
    notes: str = ""


class AuditResult(AuthorResult):
    """`prompts/audit-story.md` — the story read back against its epic and seeds."""

    status: str = ""
    notes: str = ""


class CoverageReview(AuthorResult):
    """`prompts/review-coverage.md` — every seed accounted for by some story."""

    status: str = ""
    notes: str = ""


__all__ = [
    "AuditResult",
    "Branches",
    "Committed",
    "Config",
    "CoverageReview",
    "DecomposeResult",
    "Defects",
    "EpicChoice",
    "EpicReview",
    "Feedback",
    "Ledger",
    "MockupResult",
    "Pruned",
    "PullRequest",
    "RunContext",
    "SeededStory",
    "StoryChoice",
    "StorySplit",
    "VerifyReport",
    "WriteEpicResult",
    "WriteStoryResult",
]

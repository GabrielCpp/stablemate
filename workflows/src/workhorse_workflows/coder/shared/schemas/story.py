"""The story spine's models — the three things every per-story flow resolves first.

`dev`, `review`, `docs`, `qa` and the main graph all begin the same way: turn a slug into
paths, resolve the workspace directories the agents may read, and stamp the spec docs. In
the YAML that was three script nodes copied into five graphs; here it is one module, and
these are its return models.

`WorkspaceDirs` lived in `schemas/ci.py` while `fix_ci` was the only flow that had it. It
moves here because `resolve-workspace-dirs.py` and the `fix_ci` graph's
`resolve_ci_workspace` were the same forty lines with the same body, and one of them had to
be the definition.
"""
from __future__ import annotations

from workhorse_workflows.coder.shared.schemas._base import CoderResult


class StoryPaths(CoderResult):
    """`prepare-story.py` — a slug and an epic resolved to canonical absolute paths.

    Every path is absolute, resolved through ostler so a repo with a custom specs doc root
    still works. An empty slug resolves to all-blank, which is the standalone-run case the
    YAML tolerated and every consumer already treats as "nothing to work on".
    """

    story_path: str = ""
    spec_dir: str = ""
    qa_dir: str = ""
    story_slug: str = ""
    story_epic: str = ""


class WorkspaceDirs(CoderResult):
    """`resolve-workspace-dirs.py` — every directory an agent turn in this run may read.

    The docs root is prepended when the workspace does not already contain it, so a turn
    running with one service repo as its cwd can still reach the story and plan it is
    working against.
    """

    dirs: list[str] = []


class WorktreeSnapshot(CoderResult):
    """`snapshot_worktrees` — `git status --porcelain` per code repo, keyed by repo path.

    The docs repo is not in here: plan artifacts land there on purpose, so the clean-tree
    gate has nothing to say about it. A repo whose status could not be read is absent
    rather than blank, and the scrub skips what it cannot compare.
    """

    status: dict[str, str] = {}


class PlanScrub(CoderResult):
    """`scrub_plan_mutations` — what the post-plan-turn clean-tree gate reverted.

    Keyed by repo path; the value is the porcelain lines that appeared during the turn,
    followed by the diff that was thrown away. Empty means the turn kept to reading, which
    is the normal case.
    """

    reverted: dict[str, str] = {}


class SpecsStamped(CoderResult):
    """`stamp-specs.py` — how many spec docs were given an OKF `type` this pass.

    The script's second output key, `specs_typed`, was the constant string `"yes"` on every
    path that printed anything at all: the untyped case returned 1 instead of printing. The
    node raises `WorkflowFailed` there, so "every spec doc is typed" is now expressed by the
    node returning rather than by a field nothing branched on.
    """

    stamped: int = 0


__all__ = ["PlanScrub", "SpecsStamped", "StoryPaths", "WorkspaceDirs", "WorktreeSnapshot"]

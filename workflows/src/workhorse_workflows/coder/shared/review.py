"""The review's deterministic work: where it reads, what settled, what a human dropped."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from ostler import Ostler
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.provenance import changed_files
from workhorse_workflows.coder.shared.schemas.dev_story import Settlement
from workhorse_workflows.coder.shared.schemas.review import Feedback, ReviewContext
from workhorse_workflows.coder.shared.plan import get_affected_repos, load_plan_context
from workhorse_workflows.kit import find_docs_root, poll_run_inbox, resolve_workspace

ANSWERS_FILE = "review-answers.md"


@blueprint.node
def resolve_review_context(
    logger: logging.Logger,
    spec_dir: str = "",
    repo: str = "",
    docs_path: str = "",
    repo_dir: str = "",
    workspace_file: str = "",
) -> ReviewContext:
    """Where the review turns run, and which code repos they may read."""
    root = find_docs_root(docs_path, repo_dir)
    plan_ctx = load_plan_context(root, spec_dir, logger)
    repos = resolve_workspace(workspace_file, repo_dir)
    names = [repo] if (not plan_ctx and repo) else get_affected_repos(plan_ctx, repos)
    return ReviewContext(
        docs_repo_path=str(root),
        affected_repo_paths=[repos[name]["path"] for name in names if name in repos],
    )


def _git(cwd: str, *args: str) -> bool:
    try:
        done = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def _changed(logger: logging.Logger, repos: list[str], slug: str, story_id: str) -> dict[str, list[str]]:
    return {
        repo: changed_files(logger, repo, slug, story_id).paths
        for repo in repos
    }


def _cites_change(cited: str, changed: dict[str, list[str]]) -> bool:
    wanted = cited.strip().lstrip("./")
    for repo, files in changed.items():
        name = Path(repo).name
        for path in files:
            if wanted in (path, f"{name}/{path}"):
                return True
    return False


def _names_test(test: str, changed: dict[str, list[str]]) -> bool:
    for repo, files in changed.items():
        for path in files:
            try:
                text = (Path(repo) / path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if test in text:
                return True
    return False


def evidence_gap(answer: dict, repos: list[str], changed: dict[str, list[str]]) -> str:
    """Why a fixed answer's evidence does not hold up, or `""` when every citation does."""
    for sha in answer.get("commits", []):
        if not any(_git(repo, "cat-file", "-e", f"{sha}^{{commit}}") for repo in repos):
            return f"commit {sha} is in none of the story's code repos"
    for path in answer.get("paths", []):
        if not _cites_change(path, changed):
            return f"path {path} is not among the files this story changed in its code repos"
    for test in answer.get("tests", []):
        if not _names_test(test, changed):
            return f"test {test} appears in no file this story changed"
    return ""


@blueprint.node
def settle_findings(
    logger: logging.Logger,
    docs_path: str = "",
    story_slug: str = "",
    story_id: str = "",
    filed: list[str] | None = None,
    repos: list[str] | None = None,
    repo_dir: str = "",
) -> Settlement:
    """Settle the filed finding ids against the dev owner's answer list, checking each fix's evidence."""
    root = find_docs_root(docs_path, repo_dir)
    ids = list(filed or [])
    code = [repo for repo in (repos or []) if Path(repo).is_dir()]
    ledger = Ostler(root).settle_answers(story_slug, ids, write=True)
    changed = _changed(logger, code, story_slug, story_id)
    settled: list[str] = []
    rejected: dict[str, str] = {}
    for fid in ledger.get("fixed", []):
        gap = evidence_gap(ledger["answers"][fid], code, changed)
        if gap:
            rejected[fid] = gap
        else:
            settled.append(fid)
    declined = [str(entry["id"]) for entry in ledger.get("declined", [])]
    still = [*ledger.get("open", []), *rejected]
    logger.info(
        "settlement for %s: %d settled, %d declined, %d open",
        story_slug, len(settled), len(declined), len(still),
    )
    return Settlement(
        settled=settled,
        declined=declined,
        open=still,
        rejected=rejected,
        errors=[str(e) for e in ledger.get("errors", [])],
    )


@blueprint.node
def check_feedback(logger: logging.Logger, run_dir: str = "") -> Feedback:
    """Poll the run's inbox once, without ever halting or asking."""
    polled = poll_run_inbox(run_dir, reply_text="folded into a rework pass")
    if polled is None:
        logger.info("no outstanding inbox messages")
        return Feedback()
    content, scope = polled
    logger.info("feedback present (scope=%s)", scope)
    return Feedback(present=True, content=content)


__all__ = [
    "ANSWERS_FILE",
    "check_feedback",
    "evidence_gap",
    "resolve_review_context",
    "settle_findings",
]

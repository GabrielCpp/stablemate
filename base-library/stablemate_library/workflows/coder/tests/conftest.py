"""Shared fixtures and helpers for coder workflow tests.

Helper functions are importable by test modules (pytest adds the conftest
directory to sys.path during collection).  Pytest fixtures are auto-discovered.

The engine runs **in-process** (see ``workhorse.testing``): script nodes run via
``runpy`` in the current process, so external services are intercepted by
monkeypatching the ``workhorse.scriptutil`` seams the scripts call —
``scriptutil.run_tool`` for the ``ostler`` CLI and ``scriptutil.github_client``
for the GitHub API. Local ``git`` runs for REAL against a throwaway repo seeded by
:func:`seed_git_repo` (there is nothing to mock). Because ``monkeypatch`` is
function-scoped, the ostler/github helpers below take the ``monkeypatch`` fixture.
"""

from __future__ import annotations

import json
import hashlib
import os
import subprocess
from pathlib import Path

# This repo's interpreter has a libedit-backed ``readline``. At import it runs the
# old termcap lookup and, finding no ``/etc/termcap`` (Ubuntu ships terminfo, not
# termcap), prints a harmless
#     Cannot read termcap database;
#     using dumb terminal settings.
# to stderr — once per process, so ``-n auto`` (xdist) sprays one per worker across
# the suite output. Point libedit at the system terminfo db so the lookup succeeds
# silently. Setting it here (before xdist spawns its workers) means the workers
# inherit it. No-op if the user already configured terminfo or none is installed.
if "TERMINFO" not in os.environ and "TERMINFO_DIRS" not in os.environ:
    for _terminfo_dir in ("/usr/share/terminfo", "/lib/terminfo", "/etc/terminfo"):
        if os.path.isdir(_terminfo_dir):
            os.environ["TERMINFO_DIRS"] = _terminfo_dir
            break
from unittest.mock import MagicMock

import pytest
from workhorse import scriptutil
from workhorse.testing import WorkflowRun, make_git_repo

# ---------------------------------------------------------------------------
# Workflow path
# ---------------------------------------------------------------------------

WORKFLOW = Path(__file__).parent.parent / "workflow.yaml"

# ---------------------------------------------------------------------------
# Sandbox builders
# ---------------------------------------------------------------------------


def make_story(
    sandbox: Path,
    epic: str,
    slug: str,
    status: str = "In progress",
) -> Path:
    """Write a minimal story.md and return its path (absolute).

    Also seeds legacy root evidence so QA-flow tests exercise stale evidence cleanup.
    Happy-path runner evidence is written later by the mocked plan/run boundary.
    """
    story_dir = sandbox / "docs" / "epics" / epic / "stories" / slug
    story_dir.mkdir(parents=True, exist_ok=True)
    story_md = story_dir / "story.md"
    body = f"# Story: {slug}\n\n- **Status**: {status}\n"
    story_md.write_text(body, encoding="utf-8")
    seed_qa_evidence(sandbox, slug)
    return story_md


def seed_qa_evidence(sandbox: Path, slug: str) -> Path:
    """Write a minimal valid qa-evidence.json (+ proof file) under docs/specs/<slug>.

    Matches the schema verify_qa_evidence.py validates: one behavioral criterion, Pass, citing a
    proof file that exists on disk. Returns the qa-evidence.json path.
    """
    spec_dir = sandbox / "docs" / "specs" / slug
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "qa-proof.txt").write_text("evidence ok\n", encoding="utf-8")
    evidence = {
        "overall": "Pass",
        "criteria": [
            {
                "id": "AC1",
                "title": f"{slug} acceptance criterion",
                "kind": "behavioral",
                "verdict": "Pass",
                "evidence": ["qa-proof.txt"],
            }
        ],
    }
    path = spec_dir / "qa-evidence.json"
    path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    return path


def qa_runner_side_effects(sandbox: Path, slug: str) -> list[dict]:
    """Files a successful Ostler run owns in workflow integration tests."""
    spec = sandbox / "docs" / "specs" / slug
    proof = b"runner proof\n"
    run_id = f"{slug}-qa"
    context = {"version": 1, "available": True, "obligations": []}
    log = (
        "\n".join(
            json.dumps(record)
            for record in [
                {
                    "kind": "assert",
                    "scenario": "scenario-1",
                    "action": 1,
                    "result": "PASS",
                    "covers": ["AC1"],
                },
                {"kind": "session_stop", "run_id": run_id},
            ]
        )
        + "\n"
    )
    manifest = {
        "runId": run_id,
        "artifacts": [
            {"path": "qa/proof.txt", "sha256": hashlib.sha256(proof).hexdigest()},
            {
                "path": "qa/qa-run.ndjson",
                "sha256": hashlib.sha256(log.encode()).hexdigest(),
            },
        ],
    }
    evidence = {
        "runId": run_id,
        "qa_run_log": "qa/qa-run.ndjson",
        "overall": "Pass",
        "criteria": [
            {
                "id": "AC1",
                "title": f"{slug} acceptance criterion",
                "kind": "behavioral",
                "verdict": "Pass",
                "evidence": ["qa/proof.txt"],
                "log_refs": ["scenario-1:assert:1"],
            }
        ],
        "obligations": [],
    }
    return [
        {"path": str(spec / "qa-plan.yml"), "content": "version: 2\n"},
        {"path": str(spec / "qa-plan.md"), "content": "# QA Plan\n"},
        {
            "path": str(spec / "qa-okf-context.json"),
            "content": json.dumps(context),
        },
        {"path": str(spec / "qa-okf-context.md"), "content": "# QA OKF Context\n"},
        {"path": str(spec / "qa" / "proof.txt"), "content": proof.decode()},
        {"path": str(spec / "qa" / "qa-run.ndjson"), "content": log},
        {
            "path": str(spec / "qa" / "run-manifest.json"),
            "content": json.dumps(manifest),
        },
        {"path": str(spec / "qa-evidence.json"), "content": json.dumps(evidence)},
    ]


def make_epic(
    sandbox: Path,
    epic_name: str,
    stories: list[dict],
) -> Path:
    """Create an epic directory with a dependencies.json and per-story story.md.

    Each entry in ``stories`` is a dict with keys:
        slug    (required) story identifier
        status  (default "In progress")
        deps    (default []) list of slug dependencies

    Story paths in dependencies.json are written as *absolute* paths so that
    ``await_operator.py`` (which resolves paths against the workflow script's
    own repo root) places context.md inside the sandbox rather than the real
    repository tree.
    """
    epic_dir = sandbox / "docs" / "epics" / epic_name
    epic_dir.mkdir(parents=True, exist_ok=True)
    (epic_dir / "epic.md").write_text(f"# Epic: {epic_name}\n", encoding="utf-8")

    story_entries = []
    for s in stories:
        slug = s["slug"]
        status = s.get("status", "In progress")
        make_story(sandbox, epic_name, slug, status)
        # Absolute path ensures operator gate files land in the sandbox.
        abs_path = str(
            sandbox / "docs" / "epics" / epic_name / "stories" / slug / "story.md"
        )
        story_entries.append(
            {"slug": slug, "path": abs_path, "dependencies": s.get("deps", [])}
        )

    (epic_dir / "dependencies.json").write_text(
        json.dumps({"stories": story_entries}, indent=2),
        encoding="utf-8",
    )
    return epic_dir


def make_queue(sandbox: Path, epics: list[str]) -> Path:
    """Write docs/epics/epics-todo.json and return its path."""
    todo = sandbox / "docs" / "epics" / "epics-todo.json"
    todo.parent.mkdir(parents=True, exist_ok=True)
    todo.write_text(json.dumps(epics, indent=2) + "\n", encoding="utf-8")
    return todo


# ---------------------------------------------------------------------------
# Real git repos (git runs for real; nothing here is mocked)
# ---------------------------------------------------------------------------


def seed_git_repo(sandbox: Path, *, with_remote: bool = False) -> Path:
    """Seed ``sandbox`` as a REAL git repo with one commit, and return it.

    Script nodes run in-process and shell out to the real ``git`` CLI, so the
    workflow's git operations (branch, add, commit, rev-parse) are exercised for
    real against a throwaway repo — the ``make_git_repo`` model — instead of a
    ``git`` shim.

    * ``with_remote=False`` — no ``origin``. CI/merge scripts that need a github.com
      remote report *unavailable* (their best-effort "no origin" path).
    * ``with_remote=True``  — additionally initialise a LOCAL BARE repo alongside the
      sandbox and ``git remote add origin <bare>``, then push ``main`` to it, so a
      script's ``git push``/``fetch`` against ``origin`` succeeds locally without a
      network.
    """
    make_git_repo(sandbox, name="sandbox")
    if with_remote:
        bare = sandbox.parent / f"{sandbox.name}-origin.git"
        subprocess.run(
            ["git", "init", "--bare", "-b", "main", str(bare)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(sandbox), "remote", "add", "origin", str(bare)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(sandbox), "push", "-q", "origin", "main"],
            check=True,
            capture_output=True,
        )
    return sandbox


def git_mock_no_remote(sandbox: Path) -> Path:
    """Seed ``sandbox`` as a real git repo with NO origin (was a git-shim factory).

    Kept under its historical name for call-site stability; it now seeds a real repo
    rather than returning a ``git`` command mock. Scripts that need a github remote
    take their "no origin → unavailable" path.
    """
    return seed_git_repo(sandbox, with_remote=False)


def git_mock_with_remote(sandbox: Path) -> Path:
    """Seed ``sandbox`` as a real git repo with a LOCAL BARE ``origin`` (was a
    git-shim factory).

    Kept under its historical name for call-site stability; ``git push``/``fetch``
    against ``origin`` succeed locally against the bare repo.
    """
    return seed_git_repo(sandbox, with_remote=True)


# ---------------------------------------------------------------------------
# Ostler CLI mocks (via the scriptutil.run_tool seam)
# ---------------------------------------------------------------------------
#
# Scripts reach ``ostler`` only through ``scriptutil.run_tool(["ostler", ...],
# cwd=...)``. Each helper monkeypatches that seam with a ``fake_run_tool`` that
# dispatches on the ostler subcommand and returns a ``subprocess.CompletedProcess``
# with the same (returncode, stdout) the old PATH shim produced. Because
# ``monkeypatch`` is function-scoped, these helpers take it as an argument.


def _completed(argv: list[str], returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(list(argv), returncode, stdout, stderr)


def _subcommand_skip_c(argv: list[str]) -> str:
    """The ostler subcommand, skipping a leading ``-C <dir>`` global flag.

    ``argv`` is the full ``["ostler", ...]`` invocation.
    """
    rest = argv[1:]
    i = 0
    while i < len(rest):
        if rest[i] == "-C":
            i += 2
            continue
        return rest[i]
    return ""


def mock_ostler_qa(monkeypatch, status: str = "passed") -> None:
    """Mock the QA subcommands; every other ``ostler`` subcommand *fails* (exit 1).

    A test sandbox has no initialized ostler index, so the queue/story/path
    subcommands (``todo prune``, ``todo list``, ``next-story``, ``path``) genuinely
    cannot succeed — the fake models that by failing them, so the scripts fall back
    to the deterministic JSON queue (``epics-todo.json``) and ``dependencies.json``
    fixtures that ``make_queue``/``make_epic`` seed. The catch-all is load-bearing:
    without it those subcommands returned exit 0 with empty output, which made
    ``prune-epic.py`` believe ostler had pruned the queue while ``select-next-epic.py``
    fell back to the still-populated JSON sidecar — an epic re-selected forever.

    Dispatch is keyed on the first argument after ``ostler`` (a leading ``-C <dir>`` is NOT skipped, so it
    falls to the catch-all, exactly as before).
    """
    def fake_run_tool(argv, cwd=None, *, check=False, logger=None):
        argv = list(argv)
        sub = argv[1] if len(argv) > 1 else ""
        if sub == "artifact":
            return _completed(argv, 0, json.dumps({"problems": []}))
        if sub == "qa":
            code = 0 if status == "passed" else 1
            return _completed(argv, code, json.dumps({"status": status}))
        # Unimplemented in the sandbox → fail, so scripts take their JSON fallback.
        return _completed(argv, 1, "")

    monkeypatch.setattr(scriptutil, "run_tool", fake_run_tool)


def mock_ostler_fix_passthrough(monkeypatch) -> None:
    """ostler fake for the fix loop: qa/artifact mocked, real ostler for the rest.

    seed-fix-story.py and prune-fix-item.py have *no* JSON fallback — they hard-require
    ostler to scaffold and mutate the ``fixes`` epic (``create epic``/``create story``/
    ``seed add``/``backlog``/``list``), which real ostler does correctly against a bare
    sandbox. So those subcommands are delegated to the REAL binary via
    ``subprocess.run(["ostler", ...])``. ``qa``/``artifact`` stay mocked (a real QA run
    needs a live stack), and the queue subcommands (``todo``/``next-story``/``path``)
    still fail so the epic/story queue keeps using its deterministic JSON fallback —
    delegating ``todo prune`` to a real ostler that no-ops on an index it never
    initialized would resurrect the just-pruned epic.

    The subcommand is resolved past an optional leading ``-C <dir>`` global flag, as
    the old shim did.
    """
    def fake_run_tool(argv, cwd=None, *, check=False, logger=None):
        argv = list(argv)
        sub = _subcommand_skip_c(argv)
        if sub == "artifact":
            return _completed(argv, 0, json.dumps({"problems": []}))
        if sub == "qa":
            return _completed(argv, 0, json.dumps({"status": "passed"}))
        if sub in ("todo", "next-story", "path"):
            return _completed(argv, 1, "")  # force the deterministic JSON fallback
        # create/story/seed/backlog/list/set-status → the real ostler.
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
        )

    monkeypatch.setattr(scriptutil, "run_tool", fake_run_tool)


def mock_qa_control_plane(
    wf: WorkflowRun,
    monkeypatch,
    statuses: list[str] | None = None,
    slugs: list[str] | None = None,
) -> None:
    """Mock context/validation plus a sequence of four-state runner outcomes.

    ``qa run`` walks ``statuses`` on successive calls (a per-call SEQUENCE counter,
    formerly a file under the shim dir, now a closure variable); the last entry
    repeats once exhausted. All other ``qa`` subcommands report ``passed`` and
    ``artifact`` reports no problems. Dispatch matches the old shim (keyed on the
    first arg after ``ostler`` with no ``-C`` skipping).
    """
    statuses = statuses or ["passed"]
    slugs = slugs or ["s-1"]
    counter = {"index": 0}

    def fake_run_tool(argv, cwd=None, *, check=False, logger=None):
        argv = list(argv)
        rest = argv[1:]
        if rest and rest[0] == "artifact":
            return _completed(argv, 0, json.dumps({"problems": []}))
        if not rest or rest[0] != "qa":
            return _completed(argv, 1, "")
        subcommand = rest[1] if len(rest) > 1 else ""
        if subcommand == "run":
            index = counter["index"]
            counter["index"] = index + 1
            (wf._test_dir / "qa-run-count.txt").write_text(
                str(counter["index"]), encoding="utf-8"
            )
            status = statuses[min(index, len(statuses) - 1)]
        else:
            status = "passed"
        code = 0 if status == "passed" else 1
        return _completed(argv, code, json.dumps({"status": status, "notes": f"runner {status}"}))

    monkeypatch.setattr(scriptutil, "run_tool", fake_run_tool)

    plan_entries = [
        {
            "response": {
                "qa_plan_result": {"status": "done", "notes": "QA plan written."}
            },
            "side_effects": qa_runner_side_effects(wf._sandbox, slug),
        }
        for slug in slugs
    ]
    if len(plan_entries) == 1:
        entry = plan_entries[0]
        wf.mock_agent(
            "plan_qa",
            entry["response"],
            side_effects=entry["side_effects"],
        )
    else:
        wf.mock_agent_sequence("plan_qa", plan_entries)
    wf.mock_agent(
        "qa_interpret_and_explore",
        {"qa_interpretation": {"action": "continue", "notes": "interpreted"}},
    )


# ---------------------------------------------------------------------------
# GitHub API mock (via the scriptutil.github_client seam)
# ---------------------------------------------------------------------------
#
# Scripts reach GitHub only through ``scriptutil.github_client(token)`` (PyGithub),
# never the ``gh`` CLI. ``mock_github`` monkeypatches that seam to return a
# MagicMock-based fake ``Github`` whose get_repo/get_pulls/get_pull/create_pull/merge
# return canned PR state, head SHA, CI outcome, and merge method values.


def _fake_workflow_runs(ci_status: str) -> list:
    """Actions runs for ``repo.get_workflow_runs`` matching a CI outcome.

    ``passed`` → three completed/success runs; ``failed`` → two success + one
    failure; ``unavailable`` → no runs.
    """
    def _run(name: str, conclusion: str):
        wr = MagicMock(name=f"WorkflowRun-{name}")
        wr.name = name
        wr.id = abs(hash(name)) % 100000
        wr.status = "completed"
        wr.conclusion = conclusion
        return wr

    if ci_status == "unavailable":
        return []
    if ci_status == "failed":
        return [_run("build", "success"), _run("test", "success"), _run("lint", "failure")]
    return [_run("build", "success"), _run("test", "success"), _run("lint", "success")]


def make_fake_github(
    *,
    ci_status: str = "passed",
    pr_number: int = 1,
    head_sha: str = "abc123sha",
    has_open_pr: bool = True,
    merge_ok: bool = True,
    allow_merge_commit: bool = True,
    allow_squash_merge: bool = True,
    allow_rebase_merge: bool = True,
    owner_login: str = "test-owner",
) -> MagicMock:
    """Build a MagicMock ``Github`` for the ``github_client`` seam.

    The returned client's ``get_repo`` yields a repository whose PR lookups,
    workflow runs, and merge behaviour are canned per the keyword arguments.
    """
    pr = MagicMock(name="PullRequest")
    pr.number = pr_number
    pr.head.sha = head_sha
    pr.merged = False
    pr.html_url = f"https://github.com/{owner_login}/repo/pull/{pr_number}"

    def _merge(*args, **kwargs):
        if not merge_ok:
            raise RuntimeError("merge not allowed")
        pr.merged = True
        return MagicMock(merged=True, sha=head_sha)

    pr.merge.side_effect = _merge

    repo = MagicMock(name="Repository")
    repo.owner.login = owner_login
    repo.allow_merge_commit = allow_merge_commit
    repo.allow_squash_merge = allow_squash_merge
    repo.allow_rebase_merge = allow_rebase_merge
    repo.get_pulls.return_value = [pr] if has_open_pr else []
    repo.get_pull.return_value = pr
    repo.create_pull.return_value = pr
    repo.get_workflow_runs.side_effect = lambda *a, **k: _fake_workflow_runs(ci_status)

    gh = MagicMock(name="Github")
    gh.get_repo.return_value = repo
    return gh


def mock_github(monkeypatch, fake: MagicMock | None = None, **kwargs) -> MagicMock:
    """Monkeypatch ``scriptutil.github_client`` to return a fake ``Github``.

    Pass a pre-built ``fake`` (from :func:`make_fake_github`) or keyword arguments
    forwarded to it. Returns the installed fake so a test can assert on its calls
    (e.g. ``fake.get_repo.return_value.create_pull.assert_called_once()``).
    """
    gh = fake if fake is not None else make_fake_github(**kwargs)
    monkeypatch.setattr(scriptutil, "github_client", lambda *a, **k: gh)
    monkeypatch.setattr(
        scriptutil,
        "origin_url",
        lambda root: "https://github.com/example-org/repo.git",
    )
    monkeypatch.setattr(scriptutil, "push_branch", lambda *a, **k: True)
    monkeypatch.setattr(scriptutil, "sync_to_origin", lambda *a, **k: "abc123sha")
    return gh


# ---------------------------------------------------------------------------
# Agent mock helpers
# ---------------------------------------------------------------------------


def mock_all_agents_happy(
    wf: WorkflowRun,
    monkeypatch,
    story_md_paths: list[Path] | None = None,
    ostler_setup=None,
) -> None:
    """Mock every agent node with a minimal happy-path response.

    ``monkeypatch`` is required so the ostler QA/queue backing can be installed on
    the ``scriptutil.run_tool`` seam.

    In story mode the qa mock needs no side effects (the workflow exits after qa
    passes without looping back to select_story).  In epic mode the qa agent is
    supposed to write "QA passed" to story.md so select_story skips it on the
    next loop iteration — pass ``story_md_paths`` to simulate that:

    * one path → single story, qa called once, writes "QA passed" to that file
    * N paths  → N stories processed in sequence (uses mock_agent_sequence); the
                  Kth qa call writes "QA passed" to story_md_paths[K]
    """
    wf.mock_agent(
        "plan", {"plan_result": {"status": "done", "summary": "Plan complete."}}
    )
    wf.mock_agent(
        "rework_plan", {"plan_result": {"status": "done", "summary": "Reworked."}}
    )
    wf.mock_agent(
        "replan_epic", {"replan_result": {"status": "done", "summary": "Replanned."}}
    )
    wf.mock_agent("implement_layer", {"impl_result": {"status": "done", "notes": ""}})
    wf.mock_agent(
        "code_review",
        {"code_review_result": {"status": "approved", "findings": [], "findings_summary": ""}},
    )
    wf.mock_agent(
        "review_implementation",
        {"review_impl_result": {"status": "approved", "notes": ""}},
    )
    wf.mock_agent("apply_review", {"impl_result": {"status": "applied", "notes": ""}})
    # The QA runner/queue backing. Defaults to the failing-fallback ostler mock; the
    # fix-loop tests pass mock_ostler_fix_passthrough so real ostler scaffolds the
    # `fixes` epic (which seed-fix-story.py has no JSON fallback for).
    (ostler_setup or mock_ostler_qa)(monkeypatch)
    plan_paths = story_md_paths or [
        wf._sandbox / "docs" / "epics" / "epic-1" / "stories" / "s-1" / "story.md"
    ]
    if len(plan_paths) == 1:
        slug = plan_paths[0].parent.name
        wf.mock_agent(
            "plan_qa",
            {"qa_plan_result": {"status": "done", "notes": "QA plan written."}},
            side_effects=qa_runner_side_effects(wf._sandbox, slug),
        )
    else:
        wf.mock_agent_sequence(
            "plan_qa",
            [
                {
                    "response": {
                        "qa_plan_result": {
                            "status": "done",
                            "notes": "QA plan written.",
                        }
                    },
                    "side_effects": qa_runner_side_effects(
                        wf._sandbox, path.parent.name
                    ),
                }
                for path in plan_paths
            ],
        )
    wf.mock_agent(
        "audit_qa", {"qa_result": {"status": "passed", "notes": "Audit upheld."}}
    )
    wf.mock_agent("apply_qa_fixes", {"qa_result": {"status": "passed", "notes": ""}})
    wf.mock_agent("fix_ci_agent", {"fix_ci_result": {"status": "fixed", "notes": ""}})

    qa_response = {"qa_interpretation": {"action": "continue", "notes": ""}}
    if not story_md_paths:
        wf.mock_agent("qa_interpret_and_explore", qa_response)
    elif len(story_md_paths) == 1:
        wf.mock_agent(
            "qa_interpret_and_explore",
            qa_response,
            side_effects=[
                {
                    "path": str(story_md_paths[0]),
                    "content": "- **Status**: QA passed\n",
                }
            ],
        )
    else:
        wf.mock_agent_sequence(
            "qa_interpret_and_explore",
            [
                {
                    "response": qa_response,
                    "side_effects": [
                        {"path": str(p), "content": "- **Status**: QA passed\n"}
                    ],
                }
                for p in story_md_paths
            ],
        )


# ---------------------------------------------------------------------------
# Param builders
# ---------------------------------------------------------------------------


def story_params(
    sandbox: Path,
    epic: str = "epic-1",
    slug: str = "s-1",
    project: str = "TestProject",
) -> dict:
    """Return --params for story mode using the slug+docs_path contract."""
    return {
        "mode": "story",
        "story": slug,
        "docs_path": str(sandbox),
        "epic": epic,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def story_sandbox(tmp_path):
    """A sandbox with one in-progress story (story mode)."""
    make_story(tmp_path, "epic-1", "s-1", "In progress")
    (tmp_path / "docs" / "specs" / "s-1").mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def epic_sandbox(tmp_path):
    """A sandbox with one in-progress story in a single epic (epic mode)."""
    make_epic(tmp_path, "epic-1", [{"slug": "s-1", "status": "In progress"}])
    make_queue(tmp_path, ["epic-1"])
    return tmp_path

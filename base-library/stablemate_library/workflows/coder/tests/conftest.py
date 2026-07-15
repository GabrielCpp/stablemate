"""Shared fixtures and helpers for coder workflow tests.

Helper functions are importable by test modules (pytest adds the conftest
directory to sys.path during collection).  Pytest fixtures are auto-discovered.
"""

from __future__ import annotations

import json
import hashlib
import shutil
from pathlib import Path

import pytest
from workhorse.testing import WorkflowRun

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


def mock_ostler_qa(wf: WorkflowRun, status: str = "passed") -> None:
    """Mock the QA subcommands; every other ``ostler`` subcommand *fails* (exit 1).

    A test sandbox has no initialized ostler index, so the queue/story/path
    subcommands (``todo prune``, ``todo list``, ``next-story``, ``path``) genuinely
    cannot succeed — the shim must model that by failing them, so the scripts fall
    back to the deterministic JSON queue (``epics-todo.json``) and ``dependencies.json``
    fixtures that ``make_queue``/``make_epic`` seed. The catch-all is load-bearing:
    without it those subcommands returned exit 0 with empty output, which made
    ``prune-epic.py`` believe ostler had pruned the queue while ``select-next-epic.py``
    fell back to the still-populated JSON sidecar — an epic re-selected forever.
    """
    wf.mock_command(
        "ostler",
        {
            "qa": (0 if status == "passed" else 1, json.dumps({"status": status})),
            "artifact": (0, json.dumps({"problems": []})),
            # Unimplemented in the sandbox → fail, so scripts take their JSON fallback.
            "*": (1, ""),
        },
    )


def mock_ostler_fix_passthrough(wf: WorkflowRun) -> None:
    """ostler shim for the fix loop: qa/artifact mocked, real ostler for the rest.

    seed-fix-story.py and prune-fix-item.py have *no* JSON fallback — they hard-require
    ostler to scaffold and mutate the ``fixes`` epic (``create epic``/``create story``/
    ``seed add``/``list``), which real ostler does correctly against a bare sandbox. So
    those subcommands are delegated to the real binary. ``qa``/``artifact`` stay mocked
    (a real QA run needs a live stack), and the queue subcommands (``todo``/``next-story``/
    ``path``) still fail so the epic/story queue keeps using its deterministic JSON
    fallback — delegating ``todo prune`` to a real ostler that no-ops on an
    index it never initialized would resurrect the just-pruned epic.
    """
    real = shutil.which("ostler") or "ostler"
    wf._shim_bin.mkdir(parents=True, exist_ok=True)
    shim = wf._shim_bin / "ostler"
    # Resolve the subcommand past an optional leading ``-C <dir>`` global flag.
    shim.write_text(
        f"""#!/usr/bin/env python3
import json, os, sys

REAL = {real!r}
args = sys.argv[1:]
sub, i = "", 0
while i < len(args):
    if args[i] == "-C":
        i += 2
        continue
    sub = args[i]
    break

if sub == "artifact":
    print(json.dumps({{"problems": []}}))
    sys.exit(0)
if sub == "qa":
    print(json.dumps({{"status": "passed"}}))
    sys.exit(0)
if sub in ("todo", "next-story", "path"):
    sys.exit(1)  # force the deterministic JSON queue/story fallback
os.execv(REAL, [REAL, *args])  # create/story/seed/list → the real ostler
""",
        encoding="utf-8",
    )
    shim.chmod(0o755)


def mock_qa_control_plane(
    wf: WorkflowRun,
    statuses: list[str] | None = None,
    slugs: list[str] | None = None,
) -> None:
    """Mock context/validation plus a sequence of four-state runner outcomes."""
    statuses = statuses or ["passed"]
    slugs = slugs or ["s-1"]
    wf._shim_bin.mkdir(parents=True, exist_ok=True)
    executable = wf._shim_bin / "ostler"
    executable.write_text(
        f"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
if args and args[0] == "artifact":
    print(json.dumps({{"problems": []}}))
    sys.exit(0)
if not args or args[0] != "qa":
    sys.exit(1)
subcommand = args[1] if len(args) > 1 else ""
if subcommand == "run":
    statuses = {json.dumps(statuses)}
    counter = Path(os.environ["WORKHORSE_SHIM_DIR"]) / "qa-run-count.txt"
    index = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(index + 1))
    status = statuses[min(index, len(statuses) - 1)]
else:
    status = "passed"
print(json.dumps({{"status": status, "notes": f"runner {{status}}"}}))
sys.exit(0 if status == "passed" else 1)
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)

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
# Git / command mock factories
# ---------------------------------------------------------------------------


def git_mock_no_remote() -> dict:
    """Git mock for tests where no github remote exists (CI/merge → unavailable).

    commit-story.sh uses ``git diff --cached --quiet``; exit 1 means staged
    changes exist → committed="yes".
    """
    return {
        "rev-parse": (0, "main"),
        "diff": (1, ""),  # staged changes → commit-story returns committed=yes
        "add": (0, ""),
        "commit": (0, ""),
        "checkout": (0, ""),
        "remote": (1, ""),  # no origin → CI/merge scripts report unavailable
        "*": (0, ""),
    }


def git_mock_with_remote() -> dict:
    """Git mock that includes a github.com remote (needed for CI gate tests)."""
    return {
        "rev-parse": (0, "abc1234"),
        "diff": (1, ""),
        "add": (0, ""),
        "commit": (0, ""),
        "checkout": (0, ""),
        "remote": (0, "https://github.com/test/repo.git"),
        # git -c ... push/fetch/ls-remote are dispatched on "-c" (first arg)
        "*": (0, "abc1234"),
    }


# ---------------------------------------------------------------------------
# Agent mock helpers
# ---------------------------------------------------------------------------


def mock_all_agents_happy(
    wf: WorkflowRun,
    story_md_paths: list[Path] | None = None,
    ostler_setup=None,
) -> None:
    """Mock every agent node with a minimal happy-path response.

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
    (ostler_setup or mock_ostler_qa)(wf)
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

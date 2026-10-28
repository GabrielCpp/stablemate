"""The lap's clone check: which script it runs, from which base, and what each copy becomes."""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import pytest
from workhorse.pyflow import WorkflowFailed

from workhorse_workflows.coder.shared.clones import check_copies, check_script
from workhorse_workflows.coder.shared.okf import story_base

SCRIPT_DIR = "library/skills/architecture/code-structure/scripts"

ADDED = {"path": "xlsx/extra.go", "start": 5, "end": 17, "unit": "WriteExtra"}
EXISTING = {"path": "xlsx/sheet.go", "start": 5, "end": 17, "unit": "WriteSheet"}
PAIR = {"added": ADDED, "existing": EXISTING, "lines": 13}

STUB = """
import json
import os
import sys
from pathlib import Path

Path(__file__).with_name("seen.json").write_text(
    json.dumps({"argv": sys.argv[1:], "cache": os.environ.get("STABLEMATE_CACHE_DIR"), "cwd": os.getcwd()})
)
sys.stderr.write(%(stderr)r)
sys.stdout.write(%(stdout)r)
raise SystemExit(%(code)d)
"""


def layer(
    tmp_path: Path,
    name: str,
    report: dict | None = None,
    code: int = 0,
    stdout: str | None = None,
    stderr: str = "",
) -> Path:
    root = tmp_path / name
    script = root / SCRIPT_DIR / "check_clones.py"
    script.parent.mkdir(parents=True)
    body = json.dumps(report if report is not None else {"pairs": [], "problems": []})
    script.write_text(
        STUB % {"stderr": stderr, "stdout": body if stdout is None else stdout, "code": code},
        encoding="utf-8",
    )
    return root


def seen(root: Path) -> dict:
    return json.loads((root / SCRIPT_DIR / "seen.json").read_text(encoding="utf-8"))


@pytest.fixture
def code_repo(tmp_path: Path, git) -> Path:
    root = tmp_path / "api-service"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "seed")
    return root


def test_a_pair_becomes_a_finding_naming_the_copy_the_original_and_both_units(
    tmp_path: Path, code_repo: Path, logger: logging.Logger
) -> None:
    library = layer(tmp_path, "base", {"pairs": [PAIR], "problems": []}, code=1)

    result = check_copies(logger, [str(code_repo)], library_dirs=(str(library),))

    (finding,) = result.findings
    assert result.cwd == str(code_repo)
    assert finding.target == "api-service/xlsx/extra.go:5-17"
    assert finding.issue == (
        "this story added a copy of xlsx/sheet.go:5-17 (WriteSheet), 13 lines. "
        "The copy sits in WriteExtra. "
        "The two will change for the same reason and get fixed in one place only."
    )
    assert "code-structure rule 2.12" in finding.repair
    assert "[[check-clones.coincidence]]" in finding.repair


def test_a_pair_without_units_names_only_the_ranges(
    tmp_path: Path, code_repo: Path, logger: logging.Logger
) -> None:
    pair = {
        "added": {**ADDED, "unit": None},
        "existing": {**EXISTING, "unit": None},
        "lines": 13,
    }
    library = layer(tmp_path, "base", {"pairs": [pair], "problems": []}, code=1)

    (finding,) = check_copies(logger, [str(code_repo)], library_dirs=(str(library),)).findings

    assert finding.issue.startswith("this story added a copy of xlsx/sheet.go:5-17, 13 lines. The two")


def test_a_config_problem_becomes_a_finding_on_the_check_config(
    tmp_path: Path, code_repo: Path, logger: logging.Logger
) -> None:
    library = layer(tmp_path, "base", {"pairs": [], "problems": ["one reason only"]}, code=1)

    (finding,) = check_copies(logger, [str(code_repo)], library_dirs=(str(library),)).findings

    assert finding.target == "api-service/.agent-checks.toml"
    assert finding.issue == "one reason only"
    assert finding.repair == "give the entry two different reasons, one per file, or remove it"


def test_a_clean_run_returns_no_finding(
    tmp_path: Path, code_repo: Path, logger: logging.Logger
) -> None:
    library = layer(tmp_path, "base")

    result = check_copies(logger, [str(code_repo)], library_dirs=(str(library),))

    assert result.findings == [] and result.cwd == ""


def test_a_script_that_exits_two_stops_the_run_with_its_stderr(
    tmp_path: Path, code_repo: Path, logger: logging.Logger
) -> None:
    library = layer(tmp_path, "base", code=2, stdout="", stderr="cannot download jscpd")

    with pytest.raises(WorkflowFailed, match="could not run in .*api-service:\ncannot download jscpd"):
        check_copies(logger, [str(code_repo)], library_dirs=(str(library),))


def test_output_that_is_not_the_report_stops_the_run(
    tmp_path: Path, code_repo: Path, logger: logging.Logger
) -> None:
    library = layer(tmp_path, "base", stdout="not json")

    with pytest.raises(WorkflowFailed, match="could not run"):
        check_copies(logger, [str(code_repo)], library_dirs=(str(library),))


def test_a_script_that_outlives_the_timeout_stops_the_run(
    tmp_path: Path, code_repo: Path, logger: logging.Logger, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = layer(tmp_path, "base")
    script = library / SCRIPT_DIR / "check_clones.py"
    script.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
    monkeypatch.setattr("workhorse_workflows.coder.shared.clones.CHECK_TIMEOUT", 0.2)

    with pytest.raises(WorkflowFailed, match="did not finish in .*api-service"):
        check_copies(logger, [str(code_repo)], library_dirs=(str(library),))


def test_a_repository_with_no_story_base_stops_the_run(
    tmp_path: Path, git, logger: logging.Logger
) -> None:
    root = tmp_path / "lone"
    root.mkdir()
    git(root, "init", "-q", "-b", "work")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "seed")
    library = layer(tmp_path, "base")

    with pytest.raises(WorkflowFailed, match="no story base in .*lone"):
        check_copies(logger, [str(root)], library_dirs=(str(library),))


def test_a_missing_script_stops_the_run_naming_the_layers_searched(
    tmp_path: Path, code_repo: Path, logger: logging.Logger
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    with pytest.raises(WorkflowFailed, match="check_clones.py.*empty"):
        check_copies(logger, [str(code_repo)], library_dirs=(str(empty),))


def test_two_roots_in_one_repository_run_the_check_once(
    tmp_path: Path, code_repo: Path, logger: logging.Logger
) -> None:
    (code_repo / "svc").mkdir()
    library = layer(tmp_path, "base")

    check_copies(logger, ["", str(code_repo), str(code_repo / "svc")], library_dirs=(str(library),))

    assert seen(library)["cwd"] == str(code_repo)


def test_the_script_gets_the_repo_the_base_and_the_cache_directory(
    tmp_path: Path, code_repo: Path, logger: logging.Logger, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STABLEMATE_CACHE_DIR", str(tmp_path / "cache"))
    library = layer(tmp_path, "base")

    check_copies(logger, [str(code_repo)], library_dirs=(str(library),))

    run = seen(library)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=code_repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    assert run["cache"] == str(tmp_path / "cache")
    assert run["argv"] == ["--root", str(code_repo), "--base", head, "--json"]


def test_the_cache_directory_defaults_to_the_shared_cache(
    tmp_path: Path, code_repo: Path, logger: logging.Logger, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("STABLEMATE_CACHE_DIR", raising=False)
    library = layer(tmp_path, "base")

    check_copies(logger, [str(code_repo)], library_dirs=(str(library),))

    assert seen(library)["cache"]


def test_the_first_layer_with_the_script_wins(tmp_path: Path) -> None:
    overlay = layer(tmp_path, "overlay")
    base = layer(tmp_path, "base")
    bare = tmp_path / "bare"
    bare.mkdir()

    assert check_script((str(bare), str(overlay), str(base))) == overlay / SCRIPT_DIR / "check_clones.py"
    assert check_script((str(bare),)) is None


def commit(root: Path, git, name: str, story: str | None) -> None:
    (root / name).write_text(name, encoding="utf-8")
    git(root, "add", name)
    trailer = f"\n\nStory: {story}" if story else ""
    git(root, "commit", "-qm", f"feat(api): {name}{trailer}")


def head(root: Path, git) -> str:
    return git(root, "rev-parse", "HEAD").stdout.strip()


def test_on_trunk_the_story_base_is_the_parent_of_the_earliest_story_commit(code_repo: Path, git) -> None:
    commit(code_repo, git, "one", None)
    parent = head(code_repo, git)
    commit(code_repo, git, "two", "acme-1")
    commit(code_repo, git, "three", "acme-1")

    assert story_base(code_repo, ("acme-1",)) == parent


def test_on_trunk_a_story_with_no_commit_yet_measures_from_head(code_repo: Path, git) -> None:
    commit(code_repo, git, "one", "acme-2")

    assert story_base(code_repo, ("acme-1",)) == head(code_repo, git)


def test_on_a_branch_the_story_base_is_the_merge_base_with_trunk(code_repo: Path, git) -> None:
    trunk = head(code_repo, git)
    git(code_repo, "checkout", "-qb", "story")
    commit(code_repo, git, "one", "acme-1")

    assert story_base(code_repo, ("acme-1",)) == trunk

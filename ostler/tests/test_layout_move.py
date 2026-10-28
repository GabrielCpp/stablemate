"""The layout move: an artifacts dir or docs home in the old layout refuses to load and prints the moves."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from conftest import write
from ostler import layout
from ostler._vendor.stablemate_core import config as core_config
from ostler.model import load

RECORD = "---\nid: {id}\nrepo: {repo}\narea: {area}\npattern: untriaged\nfiled_by: person\nsummary: A thing\n---\n"
ADR = "---\nid: acme-1\ntitle: Guard every total\nstatus: proposed\nrepos: []\nevidence: []\n---\n\n## Context\n\nc\n"


def artifacts() -> Path:
    return Path(os.environ["STABLEMATE_ARTIFACTS_DIR"]).resolve()


def git(*args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(artifacts()), *args], capture_output=True, text=True, check=True, timeout=30,
    )
    return done.stdout


def old_artifacts() -> None:
    core_config.ensure_artifacts_repo()
    for repo, area, record_id in (("web-app", "book", "acme-1"), ("api-service", "qa", "acme-2")):
        write(artifacts() / f"backlog/{repo}/{area}/{record_id}/record.md",
              RECORD.format(id=record_id, repo=repo, area=area))
    git("add", "backlog")
    git("-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "old shelf")


def shell(message: str) -> None:
    for line in message.splitlines()[1:]:
        subprocess.run(line.strip(), shell=True, check=True, timeout=30)


def test_an_artifacts_dir_holding_backlog_prints_the_two_moves(tmp_path: Path) -> None:
    old_artifacts()

    with pytest.raises(layout.LayoutMoveRequired) as raised:
        load(tmp_path)

    root = artifacts()
    assert str(raised.value) == (
        f"the artifacts dir {root} is in the old layout; run these commands, then run ostler again:\n"
        f"  git -C {root} mv backlog backlogs\n"
        f"  git -C {root} rm -r --cached backlogs"
    )


def test_an_old_tracked_shelf_loads_after_the_printed_commands_run(tmp_path: Path) -> None:
    old_artifacts()
    with pytest.raises(layout.LayoutMoveRequired) as raised:
        load(tmp_path)

    shell(str(raised.value))

    graph = load(tmp_path)
    assert (artifacts() / "backlogs/web-app/book/acme-1/record.md").is_file()
    assert (artifacts() / "backlogs/api-service/qa/acme-2/record.md").is_file()
    assert not (artifacts() / "backlog").exists()
    assert graph.root == tmp_path.resolve()
    assert git("ls-files", "backlogs").strip() == ""


def test_an_adr_folder_prints_a_move_to_a_slug_folder(tmp_path: Path) -> None:
    core_config.ensure_artifacts_repo()
    write(artifacts() / "adr/acme-1.md", ADR)

    with pytest.raises(layout.LayoutMoveRequired) as raised:
        load(tmp_path)

    message = str(raised.value)
    assert f"mv {artifacts()}/adr/acme-1.md {tmp_path.resolve()}/docs/adrs/guard-every-total/adr.md" in message
    shell(message)
    load(tmp_path)
    assert (tmp_path / "docs/adrs/guard-every-total/adr.md").is_file()


def test_a_docs_epics_folder_prints_a_move_to_the_artifacts_epics(tmp_path: Path) -> None:
    write(tmp_path / "docs/epics/0001-billing/epic.md", "# Epic\n")

    with pytest.raises(layout.LayoutMoveRequired) as raised:
        load(tmp_path)

    message = str(raised.value)
    assert f"mv {tmp_path.resolve()}/docs/epics/0001-billing {artifacts()}/epics/0001-billing" in message
    shell(message)
    load(tmp_path)
    assert (artifacts() / "epics/0001-billing/epic.md").is_file()


def test_the_current_layout_loads(tmp_path: Path) -> None:
    write(artifacts() / "backlogs/web-app/book/acme-1/record.md", "x")
    write(artifacts() / "epics/0001-billing/epic.md", "# Epic\n")

    load(tmp_path)

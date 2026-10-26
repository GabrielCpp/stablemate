"""The writer prompt reads a single-repo run exactly as it did before a surface could name a repository."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from okf_book.main.tally import TALLY
from okf_book.support import MEMBER
from workhorse import templates

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.main.nodes.owner_gate import Gates, gate_template_args
from workhorse_workflows.okf_book.main.nodes.writer_request import WriterRequest
from workhorse_workflows.okf_book.main.write_book_flow import WRITE_PROMPT
from workhorse_workflows.okf_book.shared.source_repo import SourceRepo

SINGLE_REPO_PROMPT_SHA256 = "bedb3490ff24f32b8af5b0dddce44627791946d00dd752332f9530234ea9044a"


def _request(source: SourceRepo) -> WriterRequest:
    return WriterRequest(
        surface=TALLY,
        repo_root=Path("/repo"),
        book_folder="docs/services/tally",
        source_folder="tally",
        source=source,
        source_view=Path("/repo/.view"),
        ostler_command_line="ostler-line",
        check_command_line="check-line",
        exercise_command_line="exercise-line",
        qa_tools=(),
    )


def _render(tmp_path: Path, source: SourceRepo) -> str:
    folder = Path(okf_book.__file__).parent
    args = {**_request(source).template_args(), **gate_template_args(tmp_path, tmp_path, "tally", Gates())}
    return templates.render(WRITE_PROMPT, args, folder)


@pytest.mark.usefixtures("ostler_okf_skill")
def test_a_single_repo_render_is_byte_identical_to_the_one_before_the_repo_field(tmp_path: Path) -> None:
    rendered = _render(tmp_path, SourceRepo(path=tmp_path))

    assert hashlib.sha256(rendered.encode()).hexdigest() == SINGLE_REPO_PROMPT_SHA256


@pytest.mark.usefixtures("ostler_okf_skill")
def test_a_workspace_render_names_the_source_folder_by_its_member(tmp_path: Path) -> None:
    rendered = _render(tmp_path, SourceRepo(name=MEMBER, path=tmp_path))

    assert f"repo://{MEMBER}/tally" in rendered

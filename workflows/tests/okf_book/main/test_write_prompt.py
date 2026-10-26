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
from workhorse_workflows.okf_book.main.nodes.writer_request import WriterRequest, writer_request
from workhorse_workflows.okf_book.main.write_book_flow import WRITE_PROMPT
from workhorse_workflows.okf_book.shared.source_repo import SourceRepo

SINGLE_REPO_PROMPT_SHA256 = "f215667a58debb70c567b49f7a8876fe758686757ada90b040ed22be7aca0d62"


def _request(source: SourceRepo) -> WriterRequest:
    return WriterRequest(
        surface=TALLY,
        repo_root=Path("/repo"),
        book_folder="docs/services/tally",
        source_folder="tally",
        source=source,
        source_dir=Path("/repo/tally"),
        ostler_command_line="ostler-line",
        check_command_line="check-line",
        exercise_command_line="exercise-line",
        qa_tools=(),
    )


def _in_place(root: Path, source: SourceRepo, tmp_path: Path) -> WriterRequest:
    return writer_request(tmp_path / "run", root, TALLY, "tally", source)


def test_a_single_repo_request_reads_the_source_folder_in_place(tmp_path: Path) -> None:
    request = _in_place(tmp_path, SourceRepo(path=tmp_path), tmp_path)

    assert request.source_dir == tmp_path / "tally"


def test_a_workspace_request_reads_the_member_checkout_in_place(tmp_path: Path) -> None:
    member = tmp_path / "code" / MEMBER

    request = _in_place(tmp_path / "docs", SourceRepo(name=MEMBER, path=member), tmp_path)

    assert request.source_dir == member / "tally"


@pytest.mark.usefixtures("ostler_okf_skill")
@pytest.mark.parametrize("name", ["", MEMBER])
def test_the_render_names_the_source_folder_in_place(tmp_path: Path, name: str) -> None:
    source = SourceRepo(name=name, path=tmp_path / "code")
    request = _in_place(tmp_path / "docs", source, tmp_path)
    folder = Path(okf_book.__file__).parent
    args = {**request.template_args(), **gate_template_args(tmp_path, tmp_path, "tally", Gates())}

    rendered = templates.render(WRITE_PROMPT, args, folder)

    assert f"`{tmp_path / 'code' / 'tally'}/`" in rendered
    assert ".okf-book-source" not in rendered


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


@pytest.mark.usefixtures("ostler_okf_skill")
def test_a_workspace_render_tells_the_writer_to_spell_product_paths_through_the_member(tmp_path: Path) -> None:
    rendered = _render(tmp_path, SourceRepo(name=MEMBER, path=tmp_path))

    assert f"workspace member `{MEMBER}`" in rendered
    assert f"`repo://{MEMBER}/<path>`" in rendered
    for field in ("code:", "working-directory:", "contract:"):
        assert f"`{field}`" in rendered.split(f"`repo://{MEMBER}/<path>`", 1)[1].split("\n- ", 1)[0]


@pytest.mark.usefixtures("ostler_okf_skill")
def test_a_single_repo_render_carries_no_member_rule(tmp_path: Path) -> None:
    rendered = _render(tmp_path, SourceRepo(path=tmp_path))

    assert "workspace member" not in rendered

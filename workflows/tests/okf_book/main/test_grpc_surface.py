"""A gRPC surface names the folder of its `.proto` files, and the writer reads it in place."""
from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from okf_book.main.tally import TALLY
from okf_book.support import ScriptedRunner
from pydantic import ValidationError
from workhorse import templates
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse.testing import make_git_repo

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.main.nodes.owner_gate import Gates, gate_template_args
from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind
from workhorse_workflows.okf_book.main.nodes.writer_request import QaTool, writer_request
from workhorse_workflows.okf_book.main.write_book_flow import WRITE_PROMPT, WriteBook
from workhorse_workflows.okf_book.shared.blockers import read_blockers
from workhorse_workflows.okf_book.shared.source_repo import SourceRepo
from workhorse_workflows.okf_book.workflow import OkfBook, workflow

CONTRACT = "proto/ledger"
GRPC = Surface(service="ledger", kind=SurfaceKind.GRPC, entry="ledger", contract=CONTRACT)
GRPCURL = QaTool(name="grpcurl", description="calls an rpc")


@pytest.mark.parametrize("kind", [SurfaceKind.GRPC, SurfaceKind.HTTP])
def test_a_grpc_or_http_surface_may_carry_a_contract(kind: SurfaceKind) -> None:
    surface = Surface(service="ledger", kind=kind, entry="ledger", contract=CONTRACT)

    assert surface.contract == CONTRACT


@pytest.mark.parametrize("kind", [SurfaceKind.CLI, SurfaceKind.WEB, SurfaceKind.MOBILE])
def test_a_cli_web_or_mobile_surface_refuses_a_contract(kind: SurfaceKind) -> None:
    with pytest.raises(ValidationError, match=rf"contract.*refused.*{kind.value}"):
        _ = Surface(service="ledger", kind=kind, entry="ledger", contract=CONTRACT)


@pytest.mark.parametrize("kind", [SurfaceKind.CLI, SurfaceKind.HTTP, SurfaceKind.WEB, SurfaceKind.MOBILE])
def test_a_surface_without_a_contract_is_valid_for_every_kind_but_grpc(kind: SurfaceKind) -> None:
    assert Surface(service="ledger", kind=kind, entry="ledger").contract == ""


def test_a_grpc_surface_requires_a_contract() -> None:
    with pytest.raises(ValidationError, match=r"contract.*required.*grpc"):
        _ = Surface(service="ledger", kind=SurfaceKind.GRPC, entry="ledger")


def test_a_request_without_a_contract_passes_none_to_the_prompt(tmp_path: Path) -> None:
    request = writer_request(tmp_path / "run", tmp_path, TALLY, "tally", SourceRepo(path=tmp_path))

    assert request.contract_dir is None
    assert (request.template_args()["contract_dir"], request.template_args()["contract_folder"]) == ("", "")


def test_a_request_reads_the_contract_folder_of_the_repository_in_place(tmp_path: Path) -> None:
    request = writer_request(tmp_path / "run", tmp_path, GRPC, "ledger", SourceRepo(path=tmp_path / "code"))

    assert request.contract_dir == tmp_path / "code" / CONTRACT
    assert request.template_args()["contract_dir"] == (tmp_path / "code" / CONTRACT).as_posix()
    assert request.template_args()["contract_folder"] == CONTRACT


def test_a_workspace_request_cites_the_contract_folder_by_its_member(tmp_path: Path) -> None:
    request = writer_request(tmp_path / "run", tmp_path, GRPC, "ledger", SourceRepo(name="api-service", path=tmp_path / "code"))

    assert request.template_args()["contract_folder"] == f"repo://api-service/{CONTRACT}"


def _render(tmp_path: Path, surface: Surface, tools: tuple[QaTool, ...] = ()) -> str:
    request = writer_request(tmp_path / "run", tmp_path, surface, "ledger", SourceRepo(path=tmp_path))
    args = {**request.template_args(), "qa_tools": [{"name": tool.name, "description": tool.description} for tool in tools]}
    return templates.render(WRITE_PROMPT, {**args, **gate_template_args(tmp_path, tmp_path, "ledger", Gates())}, Path(okf_book.__file__).parent)


@pytest.mark.usefixtures("ostler_okf_skill")
def test_the_grpc_render_carries_the_grpc_arm(tmp_path: Path) -> None:
    rendered = _render(tmp_path, GRPC, (GRPCURL,))

    assert f"The service's contract, its `.proto` files, is under `{tmp_path / CONTRACT}/`, which is the\n  repository's `{CONTRACT}/`." in rendered
    assert "each rpc with its full name and streaming shape" in rendered
    assert "the server lists it under `## RPCs`" in rendered
    assert "`driver: grpc`" in rendered
    assert "A run calls each rpc through grpcurl" in rendered
    assert "This repo offers none" not in rendered
    assert "an rpc page must cite it too" in rendered


@pytest.mark.usefixtures("ostler_okf_skill")
def test_the_grpc_render_says_when_the_repo_offers_no_grpcurl(tmp_path: Path) -> None:
    assert "This repo offers none, so no\n  scenario can run the app." in _render(tmp_path, GRPC)


@pytest.mark.usefixtures("ostler_okf_skill")
def test_the_grpc_render_carries_no_screen_or_journey_text(tmp_path: Path) -> None:
    rendered = _render(tmp_path, GRPC, (GRPCURL,))

    for phrase in ("Every screen says how it settles", "sits on a journey a user takes", "each journey", "A journey does what the user came to do", "the screens and routes", "An element that appears only after an act", "bundle-id"):
        assert phrase not in rendered
    assert "An rpc that changes a record changes one that a claim above it" in rendered


@pytest.mark.usefixtures("ostler_okf_skill")
def test_an_http_render_names_a_contract_folder_when_it_carries_one(tmp_path: Path) -> None:
    surface = Surface(service="ledger", kind=SurfaceKind.HTTP, entry="ledger", contract="openapi")

    assert "`openapi/`. Read it in place." in _render(tmp_path, surface)


@pytest.mark.usefixtures("ostler_okf_skill")
def test_an_http_render_with_a_contract_says_the_routes_are_its_annotations(tmp_path: Path) -> None:
    surface = Surface(service="ledger", kind=SurfaceKind.HTTP, entry="ledger", contract="proto")

    rendered = _render(tmp_path, surface)

    assert "The routes are the `google.api.http` options on its rpcs." in rendered
    assert "The server page's `contract:` bullet cites that folder." in rendered


@pytest.mark.usefixtures("ostler_okf_skill")
def test_an_http_render_without_a_contract_says_nothing_of_annotated_routes(tmp_path: Path) -> None:
    surface = Surface(service="ledger", kind=SurfaceKind.HTTP, entry="ledger")

    assert "google.api.http" not in _render(tmp_path, surface)


@pytest.mark.usefixtures("ostler_okf_skill")
def test_a_grpc_render_does_not_carry_the_http_route_sentence(tmp_path: Path) -> None:
    assert "google.api.http" not in _render(tmp_path, GRPC)


def _add_dirs(repo: Path, tmp_path: Path, surface: Surface, source_folder: str) -> list[str]:
    runner = ScriptedRunner({"write-book": lambda _args: {}})
    writer = ArtifactWriter("okf-book", tmp_path / "runs", run_id="t0")
    env = RunEnv(
        writer=writer,
        workflow_dir=Path(okf_book.__file__).parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        nodes=workflow.nodes,
        agent_runner=runner,
    )
    flow = WriteBook(repo_dir=str(repo), parent_records_dir=str(repo), surface=surface, source_folder=source_folder, book_folder=f"docs/services/{surface.service}")
    _ = cast("object", drive(flow, env))
    [node] = runner.nodes
    return [str(folder) for folder in node.add_dirs]


def test_the_writer_is_given_the_contract_folder_as_its_second_added_directory(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path / "repo", name="repo")

    dirs = _add_dirs(repo, tmp_path, GRPC, "ledger")

    assert dirs[:2] == [str(repo / "ledger"), str(repo / CONTRACT)]
    assert len(dirs) == 3


def test_a_writer_without_a_contract_is_given_no_contract_folder(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path / "repo", name="repo")

    dirs = _add_dirs(repo, tmp_path, TALLY, "tally")

    assert len(dirs) == 2


def test_a_workspace_writer_is_given_the_member_root_and_the_owner_folder(tmp_path: Path) -> None:
    source = SourceRepo(name="api-service", path=tmp_path / "member")
    request = writer_request(tmp_path / "run", tmp_path, GRPC, "ledger", source)
    owner = tmp_path / "owner"

    assert request.add_dirs(owner) == [source.path, owner]


def test_a_single_repo_writer_is_given_its_entry_contract_and_owner_folders(tmp_path: Path) -> None:
    request = writer_request(tmp_path / "run", tmp_path, GRPC, "ledger", SourceRepo(path=tmp_path))
    owner = tmp_path / "owner"

    assert request.add_dirs(owner) == [tmp_path / "ledger", tmp_path / CONTRACT, owner]


def test_a_grpc_surface_whose_contract_is_no_folder_is_a_blocker(tmp_path: Path) -> None:
    (tmp_path / "ledger").mkdir()
    (tmp_path / "proto").mkdir()
    book = OkfBook(repo_dir=str(tmp_path), parent_records_dir=str(tmp_path), surfaces=(GRPC,))
    _ = book.start()

    _ = book.check_source(index=0)

    [blocker] = read_blockers(tmp_path)
    assert blocker.service == "ledger"
    assert f"the contract `{CONTRACT}` is no folder of the repository" in blocker.reason
    assert "The nearest folder that exists is `proto/`" in blocker.reason


def test_a_grpc_surface_whose_contract_is_a_folder_goes_to_its_writer(tmp_path: Path) -> None:
    (tmp_path / "ledger").mkdir()
    (tmp_path / CONTRACT).mkdir(parents=True)
    book = OkfBook(repo_dir=str(tmp_path), parent_records_dir=str(tmp_path), surfaces=(GRPC,))
    _ = book.start()

    step = book.check_source(index=0)

    assert step.state == "write_book"
    assert read_blockers(tmp_path) == ()

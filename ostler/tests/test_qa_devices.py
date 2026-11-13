"""Booting the device each book's stack.yml names, and the `repo://` directories its steps run in."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import write
from ostler._vendor.stablemate_core import config as core_config
from ostler.qa import devices


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    api = tmp_path / "code" / "api-service"
    web = tmp_path / "code" / "web-app"
    write(api / "api/handlers.py", "def list_entries():\n    return []\n")
    write(web / "src/y.py", "def render():\n    return 1\n")
    (api / ".git").mkdir()
    config = tmp_path / "home.toml"
    config.write_text(f'[workspaces]\nacme = ["{api}", "{web}"]\n')
    monkeypatch.setenv(core_config.CONFIG_PATH_ENV, str(config))
    artifacts = Path(os.environ[core_config.ARTIFACTS_DIR_ENV]).resolve()
    return {"api": api.resolve(), "web": web.resolve(), "artifacts": artifacts}


def test_a_qualified_directory_resolves_in_the_member_checkout(workspace):
    root = workspace["artifacts"]

    assert devices.resolve_directory(root, "repo://api-service/api") == workspace["api"] / "api"
    assert devices.resolve_directory(root, "repo://web-app") == workspace["web"]


def test_an_unqualified_directory_resolves_under_the_root(workspace):
    root = workspace["artifacts"]

    assert devices.resolve_directory(root, "app") == (root / "app").resolve()


def test_a_member_the_workspace_lacks_fails_naming_it_and_the_known_ones(workspace):
    with pytest.raises(devices.WorkingDirectoryError) as raised:
        devices.resolve_directory(workspace["artifacts"], "repo://billing/api")

    message = str(raised.value)
    assert "billing" in message
    assert "api-service" in message
    assert "web-app" in message


def test_a_device_step_runs_in_the_member_checkout(workspace):
    root = workspace["artifacts"]
    (root / ".git").mkdir()
    stack = root / "services" / "app" / "ops" / "stack.yml"
    stack.parent.mkdir(parents=True)
    stack.write_text(
        "services: {}\n"
        "device:\n"
        "  - name: boot\n"
        "    run: pwd > booted.marker\n"
        "    working-directory: repo://api-service/api\n",
        encoding="utf-8",
    )

    results = devices.bring_up_book_devices(root)

    assert [(r["source"], r["ready"]) for r in results] == [("app", "yes")]
    assert (workspace["api"] / "api" / "booted.marker").read_text().strip() == str(workspace["api"] / "api")


def test_bring_up_book_devices_reads_the_books_alone(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    stack = tmp_path / "services" / "app" / "ops" / "stack.yml"
    stack.parent.mkdir(parents=True)
    stack.write_text(
        "services: {}\n"
        "device:\n"
        "  - name: boot\n"
        "    run: echo \"$STABLEMATE_LEASE\" > booted.marker\n", encoding="utf-8")

    results = devices.bring_up_book_devices(tmp_path, env={"STABLEMATE_LEASE": "story-1"})

    assert [(r["source"], r["ready"]) for r in results] == [("app", "yes")]
    assert (tmp_path / "booted.marker").read_text().strip() == "story-1"


def test_bring_up_book_devices_is_empty_when_no_book_declares_device_steps(tmp_path: Path) -> None:
    stack = tmp_path / "services" / "web" / "ops" / "stack.yml"
    stack.parent.mkdir(parents=True)
    stack.write_text("services: {}\n", encoding="utf-8")

    assert devices.bring_up_book_devices(tmp_path) == []


def test_bring_up_stacks_stops_at_the_first_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_ensure_stack(manifest, *, repo_root, logger):
        calls.append(manifest["source"])
        return {"ready": "no", "failed_step": "health", "error": "never answered"}

    monkeypatch.setattr(devices.stack_mod, "ensure_stack", fake_ensure_stack)
    results = devices.bring_up_stacks([{"source": "a"}, {"source": "b"}], repo_root=str(tmp_path), logger=None)

    assert calls == ["a"]
    assert [r["ready"] for r in results] == ["no"]

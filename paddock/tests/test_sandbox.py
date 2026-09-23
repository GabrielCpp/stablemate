"""What a sandboxed run can see of this machine."""

from dataclasses import replace
from pathlib import Path

import pytest

from paddock import sandbox
from paddock.cli import _command
from paddock.sandbox import Sandbox, SandboxError


def _box(tmp_path: Path) -> Sandbox:
    app = tmp_path / "apps" / "tally-cli"
    runs = tmp_path / "runs"
    config = tmp_path / "config.toml"
    credentials = tmp_path / "credentials.json"
    app.mkdir(parents=True)
    runs.mkdir()
    config.write_text("config_version = 2\n")
    credentials.write_text("{}")
    return Sandbox(app=app, runs_dir=runs, config=config, credentials=credentials)


def test_the_run_sees_the_four_mounts_and_nothing_else(tmp_path: Path) -> None:
    box = _box(tmp_path)
    argv = box.argv(["workhorse-okf-book", "run"], uid=1000, gid=1000)

    volumes = [arg.removeprefix("--volume=") for arg in argv if arg.startswith("--volume=")]
    assert volumes == [
        f"{box.app}:/work/tally-cli",
        f"{box.runs_dir}:{sandbox.RUNS}",
        f"{box.config}:{sandbox.CONFIG}:ro",
        f"{box.credentials}:{sandbox.CREDENTIALS}",
    ]
    assert "--workdir=/work/tally-cli" in argv
    assert "--user=1000:1000" in argv
    assert argv[-3:] == [sandbox.IMAGE, "workhorse-okf-book", "run"]


def test_the_app_keeps_its_directory_name_because_a_repo_is_named_by_it(tmp_path: Path) -> None:
    assert _box(tmp_path).app_dir() == "/work/tally-cli"


def test_a_mount_that_holds_the_checkout_is_refused(tmp_path: Path) -> None:
    box = _box(tmp_path)
    checkout = tmp_path / "apps" / "tally-cli" / "stablemate"
    checkout.mkdir()

    refused = box.refusals(checkout)

    assert len(refused) == 1
    assert "holds the stablemate checkout" in refused[0]
    assert "/work/tally-cli" in refused[0]


def test_a_mount_inside_the_checkout_shows_only_itself(tmp_path: Path) -> None:
    assert _box(tmp_path).refusals(tmp_path / "apps") == ()


def test_a_missing_login_is_refused_before_docker_starts(tmp_path: Path) -> None:
    box = _box(tmp_path)
    box.credentials.unlink()

    refused = box.refusals(tmp_path / "elsewhere")

    assert refused == (f"{box.credentials} does not exist. Create it, or name another path for {sandbox.CREDENTIALS}",)


def test_the_command_is_what_follows_the_separator() -> None:
    assert _command(["--", "workhorse-okf-book", "run"]) == ["workhorse-okf-book", "run"]


def test_no_command_names_where_to_put_one() -> None:
    with pytest.raises(SandboxError, match="after `--`"):
        _ = _command(["--"])


def test_the_image_is_built_from_the_tracked_dockerfile() -> None:
    root = Path(__file__).resolve().parents[2]
    assert (root / sandbox.DOCKERFILE).is_file()


@pytest.mark.parametrize("wheel", ["workhorse_workflows", "workhorse_agent", "ostler", "farrier"])
def test_the_image_installs_the_checkouts_wheel_and_not_an_index_copy_of_the_same_version(wheel: str) -> None:
    root = Path(__file__).resolve().parents[2]
    assert f"/tmp/wheels/{wheel}-*.whl" in (root / sandbox.DOCKERFILE).read_text()


def test_a_named_base_library_is_mounted_read_only_and_farrier_is_pointed_at_it(tmp_path: Path) -> None:
    library = tmp_path / "base-library"
    library.mkdir()
    box = replace(_box(tmp_path), base_library=library)

    argv = box.argv(["farrier", "--repo", "."], uid=1000, gid=1000)

    assert f"--volume={library}:{sandbox.BASE_LIBRARY}:ro" in argv
    assert f"--env=STABLEMATE_BASE_DIR={sandbox.BASE_LIBRARY}" in argv


def test_with_no_base_library_farrier_fetches_the_published_one(tmp_path: Path) -> None:
    argv = _box(tmp_path).argv(["farrier"], uid=1000, gid=1000)

    assert not [arg for arg in argv if "STABLEMATE_BASE_DIR" in arg or sandbox.BASE_LIBRARY in arg]


def test_the_checkouts_own_base_library_shows_the_run_only_the_library(tmp_path: Path) -> None:
    checkout = tmp_path / "stablemate"
    library = checkout / "base-library"
    library.mkdir(parents=True)

    assert replace(_box(tmp_path), base_library=library).refusals(checkout) == ()

"""Fixtures for paddock's own tests: a small repo, and a benchmark root with the smoke benchmark."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from paddock import loader
from paddock._vendor.stablemate_core.config import CONFIG_PATH_ENV, write_paddock_dir
from paddock.loader import Benchmark
from smoke import BASE_CONFIG, SMOKE_TASKS, git

@pytest.fixture(autouse=True)
def _artifacts_dir_is_per_test(tmp_path_factory, monkeypatch):
    """Specs live in the user's artifacts folder, so no test may resolve to the real one."""
    monkeypatch.setenv("STABLEMATE_ARTIFACTS_DIR", str(tmp_path_factory.mktemp("artifacts")))


@pytest.fixture(autouse=True, scope="session")
def git_identity(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """A global git identity, so the suite passes on identity-less machines."""
    config = tmp_path_factory.mktemp("git-identity") / "gitconfig"
    config.write_text(
        "[user]\n\tname = paddock tests\n\temail = paddock@example.com\n",
        encoding="utf-8",
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("GIT_CONFIG_GLOBAL", str(config))
        yield


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A committed repo with an executable script, a symlink, and an uncommitted edit."""
    root = tmp_path / "acme-api"
    (root / "cmd").mkdir(parents=True)
    (root / "README.md").write_text("acme\n", encoding="utf-8")
    script = root / "cmd" / "build.sh"
    script.write_text("#!/bin/sh\necho build\n", encoding="utf-8")
    script.chmod(0o755)
    (root / "latest").symlink_to("cmd/build.sh")
    git(root, "init", "--initial-branch", "main")
    git(root, "config", "user.email", "paddock@example.com")
    git(root, "config", "user.name", "paddock")
    git(root, "add", "-A")
    git(root, "commit", "-m", "initial")
    (root / "README.md").write_text("acme, edited\n", encoding="utf-8")
    return root


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A benchmark root named by a throwaway home config, which every command in the test reads."""
    directory = tmp_path / "paddock-root"
    directory.mkdir()
    monkeypatch.setenv(CONFIG_PATH_ENV, str(tmp_path / "home.toml"))
    write_paddock_dir(directory)
    return directory


@pytest.fixture
def make_benchmark(root: Path) -> Callable[..., Benchmark]:
    """Build a benchmark under `gold/`: a two-file git repository as `data/`, a base config and a tasks module."""

    def build(
        tasks: str = SMOKE_TASKS, *, name: str = "smoke", base: str = BASE_CONFIG
    ) -> Benchmark:
        directory = root / "gold" / name
        data = directory / "data"
        data.mkdir(parents=True, exist_ok=True)
        (data / "README.md").write_text("smoke\n", encoding="utf-8")
        (data / "app.py").write_text("print('smoke')\n", encoding="utf-8")
        git(data, "init", "--initial-branch", "main")
        git(data, "add", "-A")
        git(data, "commit", "-m", "initial")
        (directory / "home-config.toml").write_text(base, encoding="utf-8")
        (directory / "tasks.py").write_text(tasks, encoding="utf-8")
        return loader.load_benchmark(root, name)

    return build

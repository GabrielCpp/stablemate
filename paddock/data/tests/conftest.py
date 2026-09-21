"""Fixtures for the data suite — currently one, the shared git identity."""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True, scope="session")
def git_identity(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """A global git identity, so commits in pins pass on identity-less machines."""
    config = tmp_path_factory.mktemp("git-identity") / "gitconfig"
    config.write_text(
        "[user]\n\tname = paddock tests\n\temail = paddock@example.com\n",
        encoding="utf-8",
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("GIT_CONFIG_GLOBAL", str(config))
        yield

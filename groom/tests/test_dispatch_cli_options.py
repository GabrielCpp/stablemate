"""A dispatch ``cli`` select offers the harnesses workhorse drives, unless the operator lists its own."""
from __future__ import annotations

import logging

import pytest

from groom.settings import resolve_dispatch_queues
from workhorse._vendor.stablemate_core.harness import workhorse_harnesses
from workhorse._vendor.stablemate_core.schema import HomeConfig


def _options(*, options: list[str], kind: str = "select", name: str = "cli") -> tuple[str, ...]:
    home = HomeConfig.model_validate(
        {
            "groom": {
                "dispatch": {
                    "q": {"command": "workhorse-run", "params": [{"name": name, "type": kind, "options": options}]}
                }
            }
        }
    )
    return resolve_dispatch_queues(home)["q"].params[0].options


def test_a_cli_select_without_options_gets_the_workhorse_harness_names() -> None:
    assert _options(options=[]) == tuple(harness.name for harness in workhorse_harnesses())


def test_an_explicit_option_list_wins() -> None:
    assert _options(options=["claude", "codex"]) == ("claude", "codex")


def test_a_param_not_named_cli_keeps_its_empty_options() -> None:
    assert _options(options=[], name="flavour") == ()


def test_a_cli_param_that_is_not_a_select_keeps_its_empty_options() -> None:
    assert _options(options=[], kind="string") == ()


def test_an_unknown_explicit_option_warns_by_name(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="groom.settings"):
        assert _options(options=["claude", "retired-cli"]) == ("claude", "retired-cli")
    assert [record.getMessage() for record in caplog.records if "retired-cli" in record.getMessage()]
    assert not [record for record in caplog.records if "'claude'" in record.getMessage()]

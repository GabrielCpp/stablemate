"""Typed reads of a task's declared inputs."""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import fake_run

from paddock.tasks import inputs


def test_names_reads_a_list_a_comma_string_and_nothing(tmp_path: Path) -> None:
    assert inputs.names(fake_run(tmp_path, inputs={"k": ["a", "b"]}), "k") == ("a", "b")
    assert inputs.names(fake_run(tmp_path, inputs={"k": "a,b,"}), "k") == ("a", "b")
    assert inputs.names(fake_run(tmp_path), "k") == ()


def test_number_falls_back_to_the_default(tmp_path: Path) -> None:
    assert inputs.number(fake_run(tmp_path, inputs={"k": 2}), "k", 9.0) == 2.0
    assert inputs.number(fake_run(tmp_path), "k", 9.0) == 9.0


def test_number_refuses_a_boolean(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="expected a number"):
        inputs.number(fake_run(tmp_path, inputs={"k": True}), "k", 1.0)


def test_flag_falls_back_and_refuses_a_non_boolean(tmp_path: Path) -> None:
    assert inputs.flag(fake_run(tmp_path), "k", True) is True
    assert inputs.flag(fake_run(tmp_path, inputs={"k": False}), "k", True) is False
    with pytest.raises(TypeError, match="expected a boolean"):
        inputs.flag(fake_run(tmp_path, inputs={"k": "yes"}), "k")

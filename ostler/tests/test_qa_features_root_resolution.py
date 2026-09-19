"""Every reader of a QA context packet's `featuresRoot` agrees on what the field means.

The field has one producer (`qa/context.py`'s `build_context`) and, before this change,
three readers that each restated its normalisation rule from scratch — `qa/drivers.py`,
`cli.py`, and `qa/context.py` itself. Two of the three restatements disagreed: `cli.py`'s
`_packet_aim` returned the literal string `"None"` for a JSON `null` field and left a padded
value unstripped, where `qa/drivers.py`'s `_packet_features_root` fell back to the
discovered book in both cases. `path_mod.resolve_features_root` is now the one definition
both call, so this file pins the shapes that used to diverge to a single answer, and pins
the two readers to agreeing with each other on the same packet — the test that would have
caught the original defect.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ostler import path as path_mod
from ostler.cli import _packet_aim
from ostler.qa.drivers import PythonDriver
from ostler.qa.session import QaSession

from conftest import write_json


@pytest.mark.parametrize(
    ("packet_data", "expected"),
    [
        ({}, "docs/features"),
        ({"featuresRoot": None}, "docs/features"),
        ({"featuresRoot": ""}, "docs/features"),
        ({"featuresRoot": " docs/features "}, "docs/features"),
    ],
    ids=["key-absent", "json-null", "empty-string", "padded"],
)
def test_resolve_features_root_pins_the_four_packet_shapes(
    repo: Path, packet_data: dict, expected: str
) -> None:
    """The shapes a hand-written or legacy packet can hold all resolve to one answer.

    `repo` books straight into `docs/features`, so every shape below that means "no book
    named" resolves to that discovered root, and the one real value is only stripped.
    """
    assert path_mod.resolve_features_root(packet_data.get("featuresRoot"), repo) == expected


@pytest.mark.parametrize(
    "packet_data",
    [
        {},
        {"featuresRoot": None},
        {"featuresRoot": ""},
        {"featuresRoot": " docs/features "},
        {"featuresRoot": "other-book/docs/features"},
    ],
    ids=["key-absent", "json-null", "empty-string", "padded", "real-value"],
)
def test_cli_and_drivers_readers_agree_on_the_same_packet(repo: Path, packet_data: dict) -> None:
    """`cli._packet_aim` and `drivers._packet_features_root` read the same packet the
    same way — this is the test that would have caught `cli._packet_aim` returning the
    literal string `"None"` for a JSON `null` `featuresRoot`, or an unstripped value.
    """
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    write_json(spec / "qa-okf-context.json", packet_data)

    cli_answer = _packet_aim(str(spec), repo)

    session = QaSession.create(spec, "qa-frame-1", "story-1", {})
    driver = PythonDriver(session, "api", {"driver": "python"}, root=repo, variables={})
    driver_answer, driver_error = driver._packet_features_root()

    assert driver_error is None
    assert cli_answer == driver_answer

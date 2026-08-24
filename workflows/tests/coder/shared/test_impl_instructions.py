"""The standards handed to the implementer are derived, not dictated by the planner.

`_instruction_paths` is the seam the planner used to own outright: it enumerated eleven
skill short-names by hand and the implementer read whatever came back. The layer's own
`tags:` answer the same question without the planner having to keep a list in sync with
the library, so the planner now picks layers and names a skill only when the story turns
on one its layer does not imply.
"""
from __future__ import annotations

import logging

from workhorse_workflows.coder.shared.dev import _instruction_paths

INSTRUCTIONS = {
    "go-service": ".claude/skills/go-service/SKILL.md",
    "go-testing": ".claude/skills/go-testing/SKILL.md",
    "web-component": ".claude/skills/web-component/SKILL.md",
    "release-notes": ".claude/skills/release-notes/SKILL.md",
}
TAGS = {
    "go-service": ["backend", "standards"],
    "go-testing": ["backend", "tests"],
    "web-component": ["web"],
    "release-notes": ["release"],
}


def _paths(services: list[dict], logger: logging.Logger | None = None) -> list[str]:
    return _instruction_paths(
        services, INSTRUCTIONS, TAGS, logger or logging.getLogger("test")
    )


def test_a_services_type_pulls_every_skill_tagged_with_that_layer() -> None:
    assert _paths([{"repo": "acme", "path": "api", "type": "backend"}]) == [
        INSTRUCTIONS["go-service"],
        INSTRUCTIONS["go-testing"],
    ]


def test_a_named_skill_adds_to_the_layers_rather_than_replacing_them() -> None:
    """The story turns on a release rule no `backend` tag reaches — both must arrive."""
    paths = _paths([{"type": "backend", "skills": ["release-notes"]}])
    assert paths == [
        INSTRUCTIONS["go-service"],
        INSTRUCTIONS["go-testing"],
        INSTRUCTIONS["release-notes"],
    ]


def test_a_type_matching_no_tag_leaves_the_named_skills_alone() -> None:
    """A repo that tags nothing behaves exactly as it did before the derivation."""
    assert _paths([{"type": "go", "skills": ["go-service"]}]) == [INSTRUCTIONS["go-service"]]


def test_a_skill_the_manifest_does_not_carry_is_warned_about_and_dropped(
    caplog,
) -> None:
    with caplog.at_level(logging.WARNING):
        assert _paths([{"type": "web", "skills": ["no-such-skill"]}]) == [
            INSTRUCTIONS["web-component"]
        ]
    assert "no-such-skill" in caplog.text


def test_two_services_on_one_layer_yield_that_layers_standards_once() -> None:
    assert _paths([{"type": "backend"}, {"type": "backend"}, {"type": "web"}]) == [
        INSTRUCTIONS["go-service"],
        INSTRUCTIONS["go-testing"],
        INSTRUCTIONS["web-component"],
    ]


def test_the_type_match_is_case_insensitive() -> None:
    assert _paths([{"type": "  Backend "}]) == [
        INSTRUCTIONS["go-service"],
        INSTRUCTIONS["go-testing"],
    ]

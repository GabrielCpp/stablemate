"""The body a coder flow publishes when it stops and asks a human.

`compose_escalation` is a plain node, so it is called plainly here. What the flow tests
cover is that each gate reaches `Await` with this body; what is covered here is the body
itself — the ordering a reader depends on, and the two things it must never lose: the
resolver's note already on disk, and the fact that nobody investigated when nobody did.
"""
from __future__ import annotations

import logging
from pathlib import Path

from workhorse import gates
from workhorse_workflows.coder.shared.escalation import (
    HISTORY_HEAD,
    HISTORY_TAIL,
    compose_escalation,
)
from workhorse_workflows.coder.shared.schemas.dev import OperatorResolution

LOG = logging.getLogger("test")

NOTE = (
    "STATUS: AWAITING_OPERATOR\n\n"
    "Re-ran the suite against a fresh emulator; the seeded editor still cannot sign in.\n"
)


def _story(tmp_path: Path) -> str:
    """A story file with a folder beside it, which is where `context.md` lives."""
    folder = tmp_path / "docs" / "epics" / "EPIC-1" / "stories" / "STORY-1"
    folder.mkdir(parents=True)
    story = folder / "story.md"
    story.write_text("# Story One\n", encoding="utf-8")
    return str(story)


def test_the_gate_is_a_whole_context_file_the_engine_leaves_alone(tmp_path: Path) -> None:
    """`format_operator_gate` passes a structured body through and only re-arms it.

    That is the contract this composer is written against: a body that arrived without a
    `STATUS:` line would be wrapped in the engine's own heading and read as a bare question.
    """
    gate = compose_escalation(
        LOG, story_path=_story(tmp_path), number=1, block_kind="qa", block_notes="the suite is red"
    )

    assert gates.status_of(gate.body) == "AWAITING_OPERATOR"
    assert gates.format_operator_gate(gate.body) == gate.body


def test_the_body_answers_the_five_questions_a_reader_arrives_with(tmp_path: Path) -> None:
    """Which escalation, what blocked, what was ruled out, what would unblock it, where."""
    story = _story(tmp_path)
    resolution = OperatorResolution(
        decision="escalated",
        summary="a human must supply the emulator's allowlisted account",
        tried=["re-seeded the emulator — same refusal", "read the seed script — it never runs"],
    )

    gate = compose_escalation(
        LOG,
        story_path=story,
        story_slug="STORY-1",
        spec_dir="/w/docs/specs/STORY-1",
        run_dir="/w/.runs/coder-1",
        number=2,
        block_kind="qa",
        block_notes="sign-in scenario SC-3 fails",
        where="last lap: code fix",
        tried=list(resolution.tried),
        summary=resolution.summary,
    )

    assert gate.number == 2
    assert "**Escalation #2 for story `STORY-1`.**" in gate.body
    assert "sign-in scenario SC-3 fails" in gate.body
    assert "last lap: code fix" in gate.body
    for line in resolution.tried:
        assert f"- {line}" in gate.body
    assert resolution.summary in gate.body
    assert f"- story: `{story}`" in gate.body
    assert "- run dir: `/w/.runs/coder-1`" in gate.body
    # The order is the reading order, not an accident of construction.
    assert gate.body.index("What blocked") < gate.body.index("tried and ruled out")
    assert gate.body.index("tried and ruled out") < gate.body.index("Where everything is")


def test_the_resolver_s_note_survives_the_write_that_would_have_erased_it(
    tmp_path: Path,
) -> None:
    """The whole reason the escalated arms used to publish nothing.

    `Await` writes its questions over `context.md` with `write_text`, so a body that did not
    contain the note the resolver had just written there would destroy it — the human would
    arrive to the question instead of the investigation.
    """
    story = _story(tmp_path)
    (Path(story).parent / "context.md").write_text(NOTE, encoding="utf-8")

    gate = compose_escalation(LOG, story_path=story, number=1, block_kind="qa", tried=["one"])

    assert NOTE.strip() in gate.body
    # And the file's own `STATUS:` line is the composer's, not the quoted one — every
    # reader in `workhorse.gates` matches the first.
    assert gate.body.startswith("STATUS: AWAITING_OPERATOR")


def test_a_gate_nobody_investigated_says_so(tmp_path: Path) -> None:
    """`human`/`operator` mode reaches the same gate with no resolver behind it.

    An empty `tried` section rendered as a heading with nothing under it reads as "it tried
    nothing", which is a different and more damning claim than "nothing ran".
    """
    gate = compose_escalation(LOG, story_path=_story(tmp_path), number=1, block_kind="review")

    assert "no auto-resolver ran" in gate.body


def test_a_long_history_is_bounded_and_says_where_it_was_cut(tmp_path: Path) -> None:
    """Each escalation embeds the last, so an uncapped copy grows quadratically."""
    story = _story(tmp_path)
    history = "STATUS: CONSUMED\n\n" + ("x" * 5 * (HISTORY_HEAD + HISTORY_TAIL))
    (Path(story).parent / "context.md").write_text(history, encoding="utf-8")

    gate = compose_escalation(LOG, story_path=story, number=3, block_kind="plan")

    assert len(gate.body) < HISTORY_HEAD + HISTORY_TAIL + 2000
    assert "characters elided" in gate.body
    assert history.strip()[-200:] in gate.body


def test_an_older_resolution_without_a_tried_list_still_parses() -> None:
    """`tried` is added, defaulted and never required — a resumed run's checkpoint, and a
    resolver that answered rather than escalated, both predate it."""
    assert OperatorResolution.model_validate({"decision": "answered", "summary": "use dev"}).tried == []

"""Prompt construction, agent-response parsing and selection validation."""

from __future__ import annotations

import json
import subprocess

import pytest

from saddlebag.models import Credential, Requirement
from saddlebag.selector import (
    Selection,
    SelectionError,
    build_prompt,
    parse_response,
    select,
)

CANDIDATES = [
    Credential(id="cred-007", username="admin@staging.example.com", env="staging",
               roles=("admin", "billing"), features=("mfa_enabled", "eu_region")),
    Credential(id="cred-012", username="plain@staging.example.com", env="staging",
               roles=("admin",)),
]

REQUIREMENT = Requirement(env="staging", roles=("admin", "billing"),
                          surface="checkout/login")


def _runner(reply: str):
    def run(agent_cli: str, prompt: str) -> str:
        return reply
    return run


# -- prompt -----------------------------------------------------------------


def test_prompt_states_the_requirement():
    prompt = build_prompt(REQUIREMENT, CANDIDATES)
    assert "env=staging" in prompt
    assert "roles=[admin, billing]" in prompt
    assert "surface=checkout/login" in prompt


def test_prompt_carries_candidate_metadata_but_never_a_password():
    prompt = build_prompt(REQUIREMENT, CANDIDATES)
    assert "cred-007" in prompt and "mfa_enabled" in prompt
    assert "password" not in prompt.lower()
    # Candidate usernames are identifying but not secret; the password is the
    # thing that must never reach an agent's context.


def test_prompt_candidates_are_valid_json():
    prompt = build_prompt(REQUIREMENT, CANDIDATES)
    # Start after the "Candidates:" header — the requirement line above it also
    # contains brackets (roles=[...]).
    body = prompt[prompt.index("Candidates:") :]
    blob = body[body.index("[") : body.rindex("]") + 1]
    assert {c["id"] for c in json.loads(blob)} == {"cred-007", "cred-012"}


def test_empty_requirement_still_renders():
    assert "(no constraints)" in build_prompt(Requirement(), CANDIDATES)


# -- parsing ----------------------------------------------------------------


def test_parses_a_bare_object():
    got = parse_response('{"selected": "cred-007", "reason": "has billing"}')
    assert got == Selection("cred-007", "has billing")


def test_parses_a_fenced_object():
    raw = 'Here you go:\n```json\n{"selected": "cred-007", "reason": "r"}\n```\n'
    assert parse_response(raw).selected == "cred-007"


def test_parses_an_object_buried_in_prose():
    raw = 'I picked it because it fits. {"selected": "cred-012", "reason": "r"} Done.'
    assert parse_response(raw).selected == "cred-012"


def test_reason_is_optional():
    assert parse_response('{"selected": "cred-007"}').reason == ""


def test_empty_output_is_an_error():
    with pytest.raises(SelectionError, match="no output"):
        parse_response("   ")


def test_unparseable_output_is_an_error():
    with pytest.raises(SelectionError, match="could not parse"):
        parse_response("I refuse to answer in JSON.")


def test_object_without_selected_key_is_an_error():
    with pytest.raises(SelectionError, match="could not parse"):
        parse_response('{"reason": "I forgot the id"}')


def test_non_string_selection_is_an_error():
    with pytest.raises(SelectionError, match="could not parse"):
        parse_response('{"selected": 7}')


# -- select -----------------------------------------------------------------


def test_select_returns_the_chosen_candidate():
    cred, selection = select(REQUIREMENT, CANDIDATES, "claude",
                             runner=_runner('{"selected": "cred-007", "reason": "billing"}'))
    assert cred.id == "cred-007"
    assert selection.reason == "billing"


def test_a_hallucinated_id_is_rejected():
    """The agent must pick from the list it was given, not invent one."""
    with pytest.raises(SelectionError, match="not a candidate"):
        select(REQUIREMENT, CANDIDATES, "claude",
               runner=_runner('{"selected": "cred-999", "reason": "vibes"}'))


def test_selecting_from_nothing_is_an_error():
    with pytest.raises(SelectionError, match="no candidates"):
        select(REQUIREMENT, [], "claude", runner=_runner("{}"))


def test_a_missing_agent_cli_is_reported_clearly():
    def boom(agent_cli: str, prompt: str) -> str:
        raise FileNotFoundError(agent_cli)

    with pytest.raises(SelectionError, match="agent CLI not found: claude"):
        select(REQUIREMENT, CANDIDATES, "claude", runner=boom)


def test_an_agent_timeout_is_reported_clearly():
    def boom(agent_cli: str, prompt: str) -> str:
        raise subprocess.TimeoutExpired(cmd=agent_cli, timeout=120)

    with pytest.raises(SelectionError, match="timed out"):
        select(REQUIREMENT, CANDIDATES, "claude", runner=boom)


def test_the_runner_receives_the_rendered_prompt():
    seen: dict[str, str] = {}

    def spy(agent_cli: str, prompt: str) -> str:
        seen["cli"] = agent_cli
        seen["prompt"] = prompt
        return '{"selected": "cred-007"}'

    select(REQUIREMENT, CANDIDATES, "some-agent", runner=spy)
    assert seen["cli"] == "some-agent"
    assert "cred-007" in seen["prompt"]

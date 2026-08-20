"""The leverage scorecard: does a QA plan use the book it was handed, or just fetch URLs?

Detection alone is gameable in a direction nobody notices. A plan that opens every screen
by its URL, asserts on rendered strings and never walks a documented journey can still
catch a seeded defect — and scores identically to one that enters each flow where the book
says it starts, moves between screens by clicking, and addresses the UI by role. These
tests pin the five metrics that tell those two apart, and the rule that keeps the number
honest: an input that is not there prints `–`, never `0`.

Everything here is literal — a book dict, a context packet, a plan module written as a
string, a run log. No docker, no agent, no network.
"""

from __future__ import annotations

import contextlib
import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

BENCHMARKS = Path(__file__).parents[1]


@contextlib.contextmanager
def _tasks_dir_on_path() -> Iterator[None]:
    """Stand in for the interpreter, exactly as `paddock.loader` does.

    Task modules are loose files that import their siblings by bare name, so a loader —
    here, the test — has to put their directory on the path the way `python tasks/x.py`
    would, and take it off again.
    """
    saved = sys.path[:]
    sys.path.insert(0, str(BENCHMARKS / "tasks"))
    try:
        yield
    finally:
        sys.path[:] = saved


_spec = importlib.util.spec_from_file_location("_frozenapp", BENCHMARKS / "tasks" / "_frozenapp.py")
assert _spec is not None and _spec.loader is not None  # noqa: S101 - a real file on disk
frozen = importlib.util.module_from_spec(_spec)
with _tasks_dir_on_path():
    sys.modules["_frozenapp"] = frozen
    _spec.loader.exec_module(frozen)


# ── the fixtures every test bends one way ─────────────────────────────────────────────


def screen(node_id: str, route: str, *, entry: str = "") -> dict:
    bullets = {"route": f"`{route}`"}
    if entry:
        bullets["entry"] = entry
    return {"id": node_id, "type": "screen", "bullets": bullets, "edges": []}


BOOK = {
    "nodes": [
        screen("gui/screens/policy-list", "/policies", entry="the app root"),
        screen("gui/screens/policy-new", "/policies/new"),
        screen("gui/screens/policy-detail", "/policies/{id}"),
        {"id": "flows/create-policy", "type": "flow", "bullets": {}, "edges": []},
    ],
    "edges": [
        {"from": "flows/create-policy", "to": "gui/screens/policy-list", "via": "start"},
        {"from": "flows/create-policy", "to": "gui/screens/policy-new", "via": "steps"},
        {"from": "flows/create-policy", "to": "gui/screens/policy-detail", "via": "end"},
    ],
}

PACKET = {
    "version": 1,
    "obligations": [
        {"id": "okf:flows/create-policy:end-state", "kind": "journey",
         "node": "flows/create-policy", "required": True},
        {"id": "okf:gui/screens/policy-new:contract", "kind": "contract",
         "node": "gui/screens/policy-new", "required": True},
        # Context, not owed: a journey the closure reached and the story does not owe.
        {"id": "okf:flows/renew-policy:end-state", "kind": "journey",
         "node": "flows/renew-policy", "required": False},
    ],
}

RUN_LOG = [
    {"kind": "session_start"},
    {"kind": "scenario_start", "scenario": "create-a-policy",
     "covers": ["okf:flows/create-policy:end-state"]},
]

STATUSES = {
    "okf:flows/create-policy:end-state": "covered",
    "okf:gui/screens/policy-new:contract": "contradicted",
}


def plan(body: str, *, covers: str = '["okf:flows/create-policy:end-state"]') -> str:
    """A `qa_plan.py` with one browser scenario whose body is *body*."""
    return (
        "from ostler_qa import scenario\n\n\n"
        f"@scenario(target='web', mechanism='live', covers={covers})\n"
        "def create_a_policy(qa):\n"
        f"{body}\n"
    )


WALKS_THE_PRODUCT = plan(
    "    qa.goto('/policies')\n"
    "    qa.by_role('link', name='New policy').click()\n"
    "    qa.by_role('textbox', name='Policy number').fill('P-1')\n"
    "    qa.by_role('button', name='Create').click()\n"
)


def score(**overrides) -> dict:
    inputs = {
        "book": BOOK, "packet": PACKET, "plan_source": WALKS_THE_PRODUCT,
        "run_log": RUN_LOG, "statuses": STATUSES,
    }
    inputs.update(overrides)
    return frozen.leverage_from(**inputs)


# ── entry ─────────────────────────────────────────────────────────────────────────────


def test_a_scenario_entering_at_the_documented_start_scores_the_flow() -> None:
    assert score()["entry"] == [1, 1]


def test_a_scenario_deep_linking_into_the_middle_of_its_flow_does_not() -> None:
    """The whole point of the metric: `/policies/new` is in the flow, and is not its start.

    A plan that opens the form directly proves the form and nothing about how a user
    reaches it — which is the half of the journey a router regression lives in.
    """
    started_late = plan(
        "    qa.goto('/policies/new')\n"
        "    qa.by_role('button', name='Create').click()\n"
    )
    assert score(plan_source=started_late)["entry"] == [0, 1]


def test_only_the_flows_the_story_owes_are_counted() -> None:
    """`renew-policy` is `required: false` — context the closure reached, not work owed."""
    assert score()["entry"][1] == 1


def test_a_scenario_the_run_never_started_earns_nothing() -> None:
    assert score(run_log=[{"kind": "session_start"}])["entry"] == [0, 1]


# ── deep links ────────────────────────────────────────────────────────────────────────


def test_a_mid_scenario_goto_to_a_documented_non_entry_route_is_a_deep_link() -> None:
    jumps = plan(
        "    qa.goto('/policies')\n"
        "    qa.goto('/policies/new')\n"
        "    qa.by_role('button', name='Create').click()\n"
    )
    assert score(plan_source=jumps)["deep_links"] == 1


def test_clicking_through_is_not_a_deep_link() -> None:
    assert score()["deep_links"] == 0


def test_returning_to_an_entry_route_is_arriving_not_deep_linking() -> None:
    """`/policies` carries `entry:`, so re-opening it is a legitimate arrival."""
    reopens = plan(
        "    qa.goto('/policies')\n"
        "    qa.by_role('link', name='New policy').click()\n"
        "    qa.goto('/policies')\n"
    )
    assert score(plan_source=reopens)["deep_links"] == 0


# ── role addressing ───────────────────────────────────────────────────────────────────


def test_role_locators_score_and_text_locators_do_not() -> None:
    mixed = plan(
        "    qa.goto('/policies')\n"
        "    qa.by_role('link', name='New policy').click()\n"
        "    qa.by_text('New policy').click()\n"
    )
    assert score(plan_source=mixed)["roles"] == [1, 2]


def test_a_css_selector_counts_as_addressed() -> None:
    """The book vouches for it: `selector:` is a documented address, `text:` is a string."""
    styled = plan(
        "    qa.goto('/policies')\n"
        "    qa.locator('#policy-form').click()\n"
    )
    assert score(plan_source=styled)["roles"] == [1, 1]


# ── obligations and journeys ──────────────────────────────────────────────────────────


def test_obligations_count_only_the_passing_status() -> None:
    assert score()["obligations"] == [1, 2]


def test_a_journey_is_complete_when_its_end_state_is_covered() -> None:
    assert score()["journeys"] == [1, 1]


def test_a_journey_whose_end_state_was_never_asserted_is_not_complete() -> None:
    unproven = dict(STATUSES, **{"okf:flows/create-policy:end-state": "claimed-but-unasserted"})
    assert score(statuses=unproven)["journeys"] == [0, 1]


# ── the incomputable ones ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("missing", "blank"),
    [
        ({"statuses": None}, ("obligations", "journeys")),
        ({"plan_source": None}, ("roles", "deep_links")),
        ({"book": None}, ("entry", "deep_links")),
        ({"packet": None}, ("entry", "journeys")),
    ],
)
def test_a_metric_without_its_input_is_none_rather_than_zero(missing: dict, blank: tuple) -> None:
    """A trial that blocked before writing a plan is not a trial that wrote a bad one."""
    metrics = score(**missing)
    for key in blank:
        assert metrics[key] is None, key


def test_the_line_prints_a_dash_for_every_metric_it_could_not_compute() -> None:
    line = frozen.leverage_line(dict.fromkeys(frozen.LEVERAGE_KEYS))
    assert line.count(frozen.BLANK) == len(frozen.LEVERAGE_KEYS)
    assert "0" not in line


def test_the_line_reads_the_way_the_headline_promises() -> None:
    assert frozen.leverage_line({
        "entry": [3, 3], "deep_links": 1, "roles": [14, 15],
        "obligations": [22, 24], "journeys": [2, 3],
    }) == "leverage: entry 3/3  deep-links 1  roles 14/15  obligations 22/24  journeys 2/3"


# ── pooling across a scored round ─────────────────────────────────────────────────────


def test_pooling_sums_numerator_and_denominator_across_trials() -> None:
    pooled = frozen.pool_leverage([
        {"leverage": {"entry": [1, 1], "deep_links": 0, "roles": [4, 5],
                      "obligations": None, "journeys": [1, 1]}},
        {"leverage": {"entry": [0, 2], "deep_links": 3, "roles": [1, 1],
                      "obligations": [2, 2], "journeys": [0, 2]}},
    ])
    assert pooled == {"entry": [1, 3], "deep_links": 3, "roles": [5, 6],
                      "obligations": [2, 2], "journeys": [1, 3]}


def test_pooling_a_ledger_written_before_the_scorecard_existed_is_all_blank() -> None:
    """Old rows carry no `leverage` key, and must not read as five zeroed metrics."""
    pooled = frozen.pool_leverage([{"run_id": "coder-1", "verdict": "caught"}])
    assert pooled == dict.fromkeys(frozen.LEVERAGE_KEYS)


# ── route matching is ostler's, not a second opinion ──────────────────────────────────


@pytest.mark.parametrize(
    ("route", "url", "matches"),
    [
        ("/policies/{id}", "/policies/17", True),
        ("/policies/:id", "/policies/17", True),
        ("/policies", "/policies?q=1", True),
        ("/policies", "/policies/new", False),
        ("/policies/{id}", "/policies/17/edit", False),
    ],
)
def test_route_matching_is_segment_wise(route: str, url: str, matches: bool) -> None:
    assert frozen.route_matches(route, url) is matches

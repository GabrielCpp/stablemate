"""What the harness's differential verifiers refuse, called as the functions they are."""

from __future__ import annotations

from dataclasses import astuple
from types import SimpleNamespace
from typing import Any

import pytest

from ostler.qa.harness_host import load_harness_module

harness = load_harness_module("ostler_qa")


@pytest.mark.parametrize("check", ["created", "removed"])
def test_a_lifecycle_check_refuses_an_after_only_observation(check: str) -> None:
    """The after-read alone is the mistake — it passes identically on a subject that was already there — so the harness says so at the call rather than asserting presence."""
    with pytest.raises(TypeError) as raised:
        harness.VERIFIERS[check]({"id": "b-1"}, {"subject": "the booking"})
    assert f"{check} observes a change" in str(raised.value)
    assert "(before, after)" in str(raised.value)


@pytest.mark.parametrize(
    ("before", "after", "passes"),
    [
        (None, {"id": "b-1"}, True),
        ([], [{"id": "b-1"}], True),
        ({"id": "b-0"}, {"id": "b-1"}, False),
        (None, None, False),
    ],
)
def test_created_is_the_absence_before_and_the_presence_after(
    before: Any, after: Any, passes: bool
) -> None:
    verdict = harness.VERIFIERS["created"]((before, after), {"subject": "booking"})
    assert verdict.passed is passes
    assert verdict.actual == {"before": before, "after": after}
    assert verdict.expected == {"before": "absent", "after": "present"}


@pytest.mark.parametrize(
    ("before", "after", "passes"),
    [
        ({"id": "h-1"}, None, True),
        ([{"id": "h-1"}], [], True),
        (None, None, False),
        ({"id": "h-1"}, {"id": "h-1"}, False),
    ],
)
def test_removed_is_the_presence_before_and_the_absence_after(
    before: Any, after: Any, passes: bool
) -> None:
    verdict = harness.VERIFIERS["removed"]((before, after), {"subject": "hold"})
    assert verdict.passed is passes
    assert verdict.actual == {"before": before, "after": after}
    assert verdict.expected == {"before": "present", "after": "absent"}


class _Response:
    """As much of the harness's `Response` as a verifier reads: a status, a body, a URL, its text."""

    def __init__(self, status: int, body: Any, url: str, text: str = "") -> None:
        self.status, self._body, self.url, self.text = status, body, url, text

    def json(self) -> Any:
        return self._body


@pytest.mark.parametrize(
    ("url", "declared", "passes"),
    [
        ("http://localhost:8080/api/claims", "/api/claims", True),
        ("http://localhost:8080/api/claims?mine=1", "/api/claims", True),
        ("http://localhost:8080/api/claims", "/api/claims/cl-9999", False),
    ],
)
def test_http_status_compares_the_route_that_answered(
    url: str, declared: str, passes: bool
) -> None:
    """`path=` says *which* request answered."""
    verdict = harness.VERIFIERS["http_status"](
        _Response(200, {}, url), {"code": 200, "path": declared}
    )
    assert verdict.passed is passes
    assert verdict.expected["path"] == declared
    assert verdict.actual["path"] == declared if passes else verdict.actual["path"] != declared


def test_http_status_compares_a_declared_query_route_on_its_path() -> None:
    """A `path=` that spells the query string its request sent names the route before the `?`."""
    verdict = harness.VERIFIERS["http_status"](
        _Response(200, {}, "http://localhost:8080/api/videos?root=r-1"), {"code": 200, "path": "/api/videos?root=r-1"}
    )
    assert verdict.passed is True
    assert verdict.expected["path"] == "/api/videos?root=r-1"


def test_a_failed_http_status_shows_what_the_app_replied_with_its_tokens_masked() -> None:
    """A refusal's reason is in its reply, and a repair cannot tell a missing token from an unknown user without it."""
    token = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1LTEifQ.c2ln"
    reply = f'{{"error":"user not provisioned","token":"{token}"}}'

    failed = harness.VERIFIERS["http_status"](_Response(401, {}, "http://localhost/profile", reply), {"code": 200})
    passed = harness.VERIFIERS["http_status"](_Response(200, {}, "http://localhost/profile", reply), {"code": 200})

    assert "user not provisioned" in failed.actual["reply"]
    assert token not in failed.actual["reply"]
    assert "reply" not in passed.actual


def test_a_long_reply_is_cut() -> None:
    verdict = harness.VERIFIERS["http_status"](_Response(500, {}, "http://localhost/x", "e" * 5000), {"code": 200})

    assert len(verdict.actual["reply"]) <= 301


def test_http_status_refuses_a_bare_status_when_a_path_was_declared() -> None:
    """An integer carries no route, so the declared comparison cannot be made — a scenario defect, told at the call rather than filed against the product."""
    with pytest.raises(TypeError) as raised:
        harness.VERIFIERS["http_status"](200, {"code": 200, "path": "/api/claims"})
    assert "which request answered" in str(raised.value)


@pytest.mark.parametrize(
    ("args", "passes"),
    [
        ({"name": "Content-Type", "equals": "application/pdf"}, True),
        ({"name": "content-type", "matches": "^application/pdf"}, True),
        ({"name": "Content-Type", "equals": "text/html"}, False),
        ({"name": "Content-Disposition", "matches": "attachment"}, False),
    ],
)
def test_response_header_reads_a_header_by_its_case_blind_name(
    args: dict[str, str], passes: bool
) -> None:
    """HTTP header names carry no case, so the check finds the header whatever case the server sent it in."""
    served = SimpleNamespace(headers={"content-type": "application/pdf"})
    verdict = harness.VERIFIERS["response_header"](served, args)
    assert verdict.passed is passes
    assert list(verdict.actual) == [args["name"]]


def test_response_header_reads_headers_a_driver_exposes_as_a_method() -> None:
    """A browser response hands its headers out through a call, not an attribute."""
    served = SimpleNamespace(all_headers=None, headers=lambda: {"Content-Type": "application/pdf"})
    verdict = harness.VERIFIERS["response_header"](served, {"name": "content-type", "equals": "application/pdf"})
    assert verdict.passed is True


def test_response_header_refuses_an_observation_that_carries_no_headers() -> None:
    """A bare status has no headers to read, which is a scenario defect told at the call."""
    with pytest.raises(TypeError) as raised:
        harness.VERIFIERS["response_header"](200, {"name": "Content-Type", "equals": "application/pdf"})
    assert "headers a response carried" in str(raised.value)


def test_a_response_header_with_a_broken_pattern_is_unsatisfiable() -> None:
    """A pattern the verifier cannot compile would crash the scenario, so the plan refuses it first."""
    assert "not a pattern" in harness.UNSATISFIABLE["response_header"]({"name": "X", "matches": "("})


def test_count_walks_its_subject_into_the_document_it_was_given() -> None:
    """`{"claims": [a, b]}` has one key and two claims."""
    verdict = harness.VERIFIERS["count"](
        {"claims": [{"id": "cl-1"}, {"id": "cl-2"}]}, {"subject": "claims", "equals": 1}
    )
    assert verdict.passed is False
    assert verdict.actual == 2


def test_count_reads_a_response_body_before_resolving_its_subject() -> None:
    verdict = harness.VERIFIERS["count"](
        _Response(200, {"claims": []}, "http://localhost/api/claims"),
        {"subject": "claims", "equals": 0},
    )
    assert verdict.passed is True
    assert verdict.actual == 0


def test_count_is_red_when_the_document_has_no_such_subject() -> None:
    """The product omitting the collection is a defect of the product, so it goes red rather than raising — the shape the scenario handed over was the right one."""
    verdict = harness.VERIFIERS["count"](
        {"policies": []}, {"subject": "claims", "equals": 0}
    )
    assert verdict.passed is False
    assert verdict.actual == {"subject": "claims", "present": False}


def test_count_leaves_an_already_extracted_collection_alone() -> None:
    """A subject no path can address — a CLI's "entries in the ledger" — still counts the collection the scenario extracted for it."""
    verdict = harness.VERIFIERS["count"](
        [1, 2, 3], {"subject": "entries in the ledger", "equals": 3}
    )
    assert verdict.passed is True
    assert verdict.actual == 3


def test_count_reads_a_commands_json_stdout_before_resolving_its_subject() -> None:
    """A CLI's `--json` output is the document the subject walks into, as a response body is."""
    ran = harness.ToolResult(command=["tally", "report", "--json"], stdout='{"people": [1, 2]}', stderr="", exit_code=0)
    verdict = harness.VERIFIERS["count"](ran, {"subject": "people", "equals": 2})
    assert verdict.passed is True
    assert verdict.actual == 2
    assert ran.json() == {"people": [1, 2]}


def test_a_count_on_a_command_whose_stdout_is_not_json_is_red_and_names_the_command() -> None:
    """The product printed something, and what it printed is the observation: the scenario grades it and runs on."""
    silent = harness.ToolResult(command=["tally", "add"], stdout="", stderr="tally: added", exit_code=0)
    verdict = harness.VERIFIERS["count"](silent, {"subject": "entries in the ledger", "equals": 1})
    assert verdict.passed is False
    assert verdict.expected == 1
    assert verdict.actual["countable"] is False
    assert "tally add exited 0 with a stdout that is not JSON" in verdict.actual["reason"]


def test_json_path_equals_compares_a_json_scalar_by_type() -> None:
    """`equals=8250` is a number, not the string "8250": a product that serialises an amount as text is a different product, and `true` is not `1`."""
    verify = harness.VERIFIERS["json_path"]
    assert verify({"amount": 8250}, {"path": "amount", "equals": 8250}).passed is True
    assert verify({"amount": 8250}, {"path": "amount", "equals": 8250.0}).passed is True
    verdict = verify({"amount": "8250"}, {"path": "amount", "equals": 8250})
    assert verdict.passed is False and verdict.actual == "8250" and verdict.expected == 8250
    assert verify({"amount": 8250}, {"path": "amount", "equals": "8250"}).passed is False
    assert verify({"paid": True}, {"path": "paid", "equals": True}).passed is True
    assert verify({"paid": 1}, {"path": "paid", "equals": True}).passed is False
    assert verify({"paid": True}, {"path": "paid", "equals": 1}).passed is False
    assert verify({"tags": ["a"]}, {"path": "tags", "equals": "a"}).passed is False
    assert verify({"id": "abc"}, {"path": "id", "equals": "abc"}).passed is True


LEDGER = {
    "people": [
        {"who": "ana", "total_cents": 4200, "trips": [1, 2]},
        {"who": "bo", "total_cents": 1300, "trips": [3]},
        {"who": "cy", "total_cents": 1300, "trips": []},
    ]
}


def test_a_filter_segment_selects_the_entry_by_what_it_holds_not_where_it_sits() -> None:
    """`people[?(@.who=='ana')].total_cents` is a claim about ana, not about entry 0 — the order the product writes its list in is not what the book claimed."""
    verify = harness.VERIFIERS["json_path"]
    args = {"path": "people[?(@.who=='ana')].total_cents", "equals": 4200}
    assert verify(LEDGER, args).passed is True
    shuffled = {"people": list(reversed(LEDGER["people"]))}
    assert verify(shuffled, args).passed is True
    verdict = verify(LEDGER, {"path": "people[?(@.who=='zed')].total_cents", "equals": 1})
    assert verdict.passed is False and verdict.actual == {"present": False}
    assert verify(LEDGER, {"path": "people[?(@.who=='zed')]", "absent": True}).passed is True
    assert verify(LEDGER, {"path": "people[?(@.who=='bo')]", "absent": True}).passed is False
    assert verify(LEDGER, {"path": "people[?(@.total_cents==1300)].who", "matches": "^bo$"}).passed is False


def test_a_selector_that_picks_out_two_values_is_an_ambiguous_claim_not_a_pass() -> None:
    """Two selections and one `equals=` is a book that failed to single the entry out; the verdict is red and reports what was selected so the author sees the ambiguity."""
    verify = harness.VERIFIERS["json_path"]
    verdict = verify(LEDGER, {"path": "people[?(@.total_cents==1300)].who", "equals": "bo"})
    assert verdict.passed is False
    assert verdict.actual == {"selected": ["bo", "cy"]}
    assert verdict.expected == {"selected": "exactly one"}
    verdict = verify(LEDGER, {"path": "people[*].who", "equals": "ana"})
    assert verdict.passed is False and verdict.actual == {"selected": ["ana", "bo", "cy"]}


def test_count_counts_what_a_wildcard_or_filter_selects() -> None:
    count = harness.VERIFIERS["count"]
    assert count(LEDGER, {"subject": "people[*]", "equals": 3}).passed is True
    assert count(LEDGER, {"subject": "people[*].trips[*]", "equals": 3}).passed is True
    assert count(LEDGER, {"subject": "people[?(@.total_cents==1300)]", "equals": 2}).passed is True
    verdict = count(LEDGER, {"subject": "people[?(@.who=='ana')].trips[*]", "equals": 2})
    assert verdict.passed is True and verdict.actual == 2


def test_count_is_zero_when_a_wildcard_or_filter_selects_nothing() -> None:
    """An empty selection is a count, so an empty ledger is not reported as a missing one."""
    count = harness.VERIFIERS["count"]
    assert astuple(count({"entries": []}, {"subject": "$.entries[*]", "equals": 0})) == (True, 0, 0)
    assert astuple(count(LEDGER, {"subject": "people[?(@.who=='zed')]", "equals": 0})) == (True, 0, 0)
    verdict = count({"policies": []}, {"subject": "claims[*]", "equals": 0})
    assert verdict.passed is False and verdict.actual == {"subject": "claims[*]", "present": False}


def test_json_path_without_a_comparison_is_red_not_green() -> None:
    """`ostler.checks` refuses this call where it is declared."""
    verdict = harness.VERIFIERS["json_path"](
        {"item": {"id": "abc"}}, {"path": "$.item.id"}
    )
    assert verdict.passed is False
    assert verdict.actual == "abc"
    assert "presence asserts nothing" in verdict.expected


def test_omits_reads_the_field_its_subject_names() -> None:
    """The C9 shape: a well-formed refusal carrying the credential it rejected."""
    leak = "The bearer token eyJhbGciOi… was not accepted."
    verdict = harness.VERIFIERS["omits"](
        _Response(401, {"title": "Unauthorized", "detail": leak}, "http://x/api/claims"),
        {"subject": "$.detail", "matches": "eyJ[A-Za-z0-9]+"},
    )
    assert verdict.passed is False
    assert verdict.actual["found"] == ["eyJhbGciOi"]


def test_omits_passes_when_the_subject_says_nothing_it_may_not() -> None:
    verdict = harness.VERIFIERS["omits"](
        _Response(401, {"title": "Unauthorized", "detail": "The credential was not accepted."},
                  "http://x/api/claims"),
        {"subject": "$.detail", "matches": "eyJ[A-Za-z0-9]+"},
    )
    assert verdict.passed is True
    assert verdict.actual == verdict.expected == {"found": []}


def test_omits_searches_everything_when_its_subject_does_not_resolve() -> None:
    """A leak lands where the defect put it, not where the author guessed."""
    verdict = harness.VERIFIERS["omits"](
        _Response(401, {"error": {"note": "token eyJabc rejected"}}, "http://x/api/claims"),
        {"subject": "$.detail", "text": "eyJabc"},
    )
    assert verdict.passed is False
    assert verdict.actual["found"] == ["eyJabc"]


def test_omits_searches_a_plain_string_observation() -> None:
    """A command's output is not a document, and its stderr is where a path leaks."""
    verdict = harness.VERIFIERS["omits"](
        "error: cannot open /home/ci/.secrets/ledger.key",
        {"subject": "the message", "text": "/home/ci/.secrets"},
    )
    assert verdict.passed is False
    assert verdict.actual["found"] == ["/home/ci/.secrets"]


def test_absent_false_is_a_presence_assertion_that_can_go_red() -> None:
    """A book spelling `absent=false` claims the field is there."""
    present = harness.VERIFIERS["json_path"](
        {"policies": [{"version": "1"}]}, {"path": "policies[0].version", "absent": False}
    )
    missing = harness.VERIFIERS["json_path"](
        {"policies": [{}]}, {"path": "policies[0].version", "absent": False}
    )
    assert present.passed is True
    assert missing.passed is False
    assert missing.actual == {"present": False} and missing.expected == {"present": True}


class _StyledLocator:
    """An element whose painted text is not its DOM text — a stylesheet's doing."""

    def __init__(self, *, rendered: str, dom: str) -> None:
        self._rendered = rendered
        self._dom = dom

    def is_visible(self) -> bool:
        return True

    def inner_text(self) -> str:
        return self._rendered

    def text_content(self) -> str:
        return self._dom


def test_visible_reads_the_dom_when_css_repainted_the_text() -> None:
    """The one thing QA grounded on the book must not do is redden against a correct app, and casing applied by CSS is not a disagreement with the book about content."""
    element = _StyledLocator(rendered="A1\nFREE", dom="A1free")
    verdict = harness.VERIFIERS["visible"](element, {"text": "free"})
    assert verdict.passed is True
    assert verdict.actual == {"visible": True, "text": "A1\nFREE"}
    assert verdict.expected == {"visible": True, "text": "free"}


def test_visible_still_fails_on_text_neither_reading_carries() -> None:
    """The fallback widens the spellings, not the verdict: a string the element does not say is absent from both readings, which is what keeps the check able to go red."""
    element = _StyledLocator(rendered="A1\nFREE", dom="A1free")
    verdict = harness.VERIFIERS["visible"](element, {"text": "booked"})
    assert verdict.passed is False


def test_exit_status_reads_exit_code_and_refuses_other_subjects() -> None:
    """The check observes the one thing a command's output never carries — how the process ended — and a plan that hands it a response or a document has mis-wired the claim."""
    verify = harness.VERIFIERS["exit_status"]
    assert astuple(verify(SimpleNamespace(exit_code=0), {"code": 0})) == (True, 0, 0)
    verdict = verify(SimpleNamespace(exit_code=2), {"code": 0})
    assert astuple(verdict) == (False, 2, 0)
    assert verify(harness.ToolResult(command=["tally"], stdout="", stderr="", exit_code=3), {"code": 3}).passed
    with pytest.raises(TypeError, match="exit_code"):
        verify(_Response(200, {}, "http://x/"), {"code": 0})
    with pytest.raises(TypeError, match="exit_code"):
        verify({"exit_code": 0}, {"code": 0})




def test_a_stream_check_reads_only_the_stream_it_names() -> None:
    """A refusal printed on stdout is not the one the book says goes to stderr, and each argument the output lacks is named."""
    result = harness.ToolResult(command=["tally"], stdout="no ledger at x.csv", stderr="", exit_code=2)
    verdict = harness.VERIFIERS["stderr"](result, {"text": "no ledger", "matches": "x[.]csv"})
    assert astuple(verdict) == (False, "", {"text": "no ledger", "matches": "x[.]csv"})
    assert astuple(harness.VERIFIERS["stdout"](result, {"text": "no ledger", "matches": "x[.]csv"})) == (True, "no ledger at x.csv", {})
    with pytest.raises(TypeError, match="stdout"):
        harness.VERIFIERS["stdout"](_Response(200, {}, "http://x/"), {"text": "ok"})


def test_a_stream_check_with_a_broken_pattern_is_unsatisfiable() -> None:
    """A pattern the verifier cannot compile would crash the scenario, so the plan refuses it first."""
    assert "not a pattern" in harness.UNSATISFIABLE["stderr"]({"matches": "("})
    assert harness.UNSATISFIABLE["stdout"]({"text": "("}) == ""


def _qa(recorder: Any, driver: str = "playwright") -> Any:
    """`Qa.window` reads three attributes and nothing else, so it is exercised against them rather than around a whole scenario process — the thing under test is which drivers may answer the question, and a real run would prove the browser works instead."""
    return SimpleNamespace(
        diagnostics=recorder,
        scenario_id="new_widget_submit",
        target=SimpleNamespace(name="web", driver=driver),
    )


def test_a_scenario_reading_an_exchange_on_a_driver_that_records_none_says_which(
) -> None:
    """Observability is a relation between what a claim needs and what a driver can supply."""
    for recorder in (None, object()):
        with pytest.raises(RuntimeError) as raised:
            harness.Qa.window(_qa(recorder, driver="python"))
        message = str(raised.value)
        assert "new_widget_submit" in message
        assert "'web'" in message and "'python'" in message
        assert "only driver='playwright'" in message


def test_a_browser_scenario_gets_the_recorder_s_own_window() -> None:
    """The window comes from the recorder, not from a second copy of its bookkeeping — one object holds both the bound and the lookup that respects it."""
    sentinel = object()
    recorder = SimpleNamespace(window=lambda: sentinel)
    assert harness.Qa.window(_qa(recorder)) is sentinel

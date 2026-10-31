"""A claim's `observe:` compiled: the plan reads the resource through the harness and asserts on that read, and a claim that cannot be read that way is a gap."""

from __future__ import annotations

import ast

from test_qa_compile import _context, _obligation, compile_plan_gaps

from ostler.qa.packet import packet_of
from ostler.qa.references import CaptureRef, NodeRef

OID = "okf:docs/services/demo/api.md#post-things:does:1"


def _count(**args: object) -> dict:
    return {"call": "one recording", "name": "count", "args": {"subject": "items", "equals": 1, **args}}


def _observed(*checks: dict, resource: str = "camera", observation: str = "recordings") -> dict:
    return {"value": f"@{resource}.{observation}", "resource": resource, "observation": observation,
            "checks": list(checks)}


def _plan(observed: dict | None = None, **extra: object) -> tuple[str | None, list]:
    obligation = _obligation(OID, observationsDeclared=[observed] if observed else [], **extra)
    context = _context(obligation)
    context["resourceObservations"] = {"camera": ["recordings"]}
    return compile_plan_gaps(context, story="demo-story")


def _kinds(gaps: list) -> list[str]:
    return [gap.kind for gap in gaps if gap.obligation_id == OID]


def test_an_observation_compiles_to_a_polling_read_and_a_verify_without_within() -> None:
    source, gaps = _plan(_observed(_count(within=30)))
    assert source is not None, gaps
    ast.parse(source)
    assert 'qa.observe("camera", "recordings", within=30, until=[("count", {"subject": "items", "equals": 1})])' in source
    verify = next(line for line in source.splitlines() if "qa.verify(" in line and '"count"' in line)
    assert "within" not in verify
    assert OID in verify
    assert not _kinds(gaps)


def test_an_observation_without_within_reads_once() -> None:
    source, _gaps = _plan(_observed(_count()))
    assert source is not None
    assert 'qa.observe("camera", "recordings")' in source
    assert "until=" not in source


def test_within_on_a_response_row_is_a_gap_and_not_a_wait() -> None:
    source, gaps = _plan(None, checksDeclared=[{"call": "created", "name": "http_status",
                                                "args": {"code": 201, "within": 5}}])
    assert "within-off-observation" in _kinds(gaps)
    assert source is None or "within=5" not in source


def test_an_observation_naming_no_resource_is_a_gap() -> None:
    _source, gaps = _plan(_observed(_count(), resource="nowhere"))
    assert "unknown-observation" in _kinds(gaps)


def test_an_observation_the_page_does_not_hold_is_a_gap() -> None:
    _source, gaps = _plan(_observed(_count(), observation="nothing"))
    assert "unknown-observation" in _kinds(gaps)


def test_an_observe_value_that_is_not_a_reference_is_a_gap() -> None:
    _source, gaps = _plan(None, observationsUnparsed=[{"value": "the camera", "problem": "is not `@<resource>.<observation>`"}])
    assert "unparsed-observation" in _kinds(gaps)


def _reading(*references: str, **extra: object) -> tuple[str | None, list]:
    obligation = _obligation(OID, observationsDeclared=[_observed(_count())], **extra)
    context = _context(obligation)
    context["resourceObservations"] = {"camera": ["recordings"]}
    context["resourceReads"] = {"camera.recordings": list(references)}
    return compile_plan_gaps(context, story="demo-story")


def test_a_capture_the_observation_reads_that_nothing_captured_is_a_gap_and_the_claim_is_not_covered() -> None:
    source, gaps = _reading("$uid")
    assert _kinds(gaps) == ["unresolved-precondition"]
    [gap] = [gap for gap in gaps if gap.obligation_id == OID]
    assert "$uid" in gap.detail
    assert "@camera.recordings" in gap.detail
    assert source is None or 'qa.observe("camera"' not in source


def test_a_fixture_fact_the_claim_arranges_resolves_a_reference_in_the_observation() -> None:
    fixture = {"name": "account-without-list", "args": [], "provides": "an account", "providesKeys": ["account-without-list.uid"]}
    source, gaps = _reading("@account-without-list.uid", fixturesDeclared=[fixture])
    assert source is not None, gaps
    assert not _kinds(gaps)
    assert 'qa.observe("camera", "recordings")' in source


def test_a_fixture_fact_no_fixture_provides_is_a_gap() -> None:
    _source, gaps = _reading("@account-without-list.uid")
    assert _kinds(gaps) == ["unresolved-precondition"]


def test_a_capture_an_earlier_claim_left_resolves_a_reference_in_the_observation() -> None:
    capturing = "okf:docs/services/demo/api.md#post-things:does:1"
    context = _context(
        _obligation(capturing, checksDeclared=[_count()], capturesDeclared=[{"name": "uid", "from": "$.id"}]),
        _obligation(OID, observationsDeclared=[_observed(_count())]),
    )
    context["resourceObservations"] = {"camera": ["recordings"]}
    context["resourceReads"] = {"camera.recordings": ["$uid"]}
    source, gaps = compile_plan_gaps(context, story="demo-story")
    assert not _kinds(gaps)
    assert source is not None
    assert 'qa.observe("camera", "recordings")' in source


def test_the_packet_carries_the_references_an_observation_reads_and_an_old_packet_loads_without_them() -> None:
    context = _context(_obligation(OID))
    context["resourceReads"] = {"camera.recordings": ["$uid", "@seed.user"]}
    assert packet_of(context).resource_reads == {"camera.recordings": (CaptureRef("uid"), NodeRef("seed", "user"))}
    del context["resourceReads"]
    assert packet_of(context).resource_reads == {}

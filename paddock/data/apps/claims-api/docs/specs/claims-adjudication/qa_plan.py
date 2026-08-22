"""The frozen QA plan for `claims-adjudication`.

Two criteria here need more than a request each. The compare-and-swap needs two writes off
one reading with no re-read between them — a scenario that fetches the claim again before
the second write is proving the wrong thing, because the version it quotes is current by
construction. And the durability of a decision needs the process that took it replaced:
`agents.yml` opts this app's QA into `docker` for exactly that, and nothing else in this
plan uses it.

The three identities come from the auth emulator beside the service, so there is no
credential in this file; the adjuster's role is a custom claim the emulator stamps on the
token, which is what `403 Adjusters Only` is decided from.
"""

import json

from _fixtures.identity import ADJUSTER, HOLDER_A, bearer, sign_in
from ostler_qa import HttpError, Qa, plan, scenario, target


plan(run_id="qa-claims-adjudication", story="claims-adjudication")

api = target("api", driver="python", base_url="http://localhost:18085")


def one_claim_awaiting_a_decision(qa: Qa) -> dict:
    """An emptied desk holding exactly cl-1001, filed by holder A at version 1."""
    holder, adjuster = sign_in(qa, HOLDER_A), sign_in(qa, ADJUSTER)
    qa.http.delete("/api/claims", headers=bearer(adjuster), expect_status=204)
    filed = qa.http.post(
        "/api/claims",
        json_body={
            "policy_number": "PL-7730",
            "incident_date": "2099-05-19",
            "amount_cents": 240000,
            "description": "Storm damage to the outbuildings.",
        },
        headers=bearer(holder),
        expect_status=201,
    ).json()["claim"]
    return {"holder": holder, "adjuster": adjuster, "claim": filed}


@scenario(
    target=api,
    mechanism="live",
    covers=[
        "ac:1",
        "ac:2",
        "okf:docs/features/claims/http/claims-api.md#decide-claim:does:1",
        "okf:docs/features/claims/http/claims-api.md#decide-claim:persistence:1",
        "okf:docs/features/claims/http/claims-api.md#decide-claim:contract",
        "okf:docs/features/claims/flows/decide-a-claim.md:start:1",
        "okf:docs/features/claims/flows/decide-a-claim.md:end:1",
        "okf:docs/features/claims/flows/decide-a-claim.md:end-state",
    ],
    preconditions=[
        "cl-1001 is on file at version 1, filed by holder A",
        "the adjuster reaches the claim through the register, holding a token carrying the role",
    ],
    checkpoints=[
        "the decision answers 200 with the claim Approved at version 2",
        "the adjuster's note is on the decided claim",
        "the service is restarted between the accepted decision and the re-read",
        "the restarted service answers with the same decided claim",
    ],
    forbid=[
        "an in-process re-read as evidence that the decision was written down",
        "reading the ledger file instead of the documented route",
    ],
)
def a_decision_is_recorded_and_outlives_the_process(qa: Qa) -> None:
    """An adjuster approves a claim, and the approval is still there without the process."""
    who = one_claim_awaiting_a_decision(qa)
    adjuster = who["adjuster"]

    register = qa.http.get("/api/claims", headers=bearer(adjuster), expect_status=200).json()["claims"]
    qa.check("the adjuster reaches the claim through their own register", [qa.field(claim, "id") for claim in register] == ["cl-1001"], covers=["ac:1", "okf:docs/features/claims/flows/decide-a-claim.md:start:1"])

    decided = qa.http.post("/api/claims/cl-1001/decision", json_body={"decision": "approve", "version": 1, "note": "Cover confirmed against the schedule."}, headers=bearer(adjuster), expect_status=200)
    body = decided.json()
    qa.verify("http_status", decided, code=200, path="/api/claims/cl-1001/decision", covers=["ac:1", "okf:docs/features/claims/http/claims-api.md#decide-claim:does:1", "okf:docs/features/claims/http/claims-api.md#decide-claim:contract"])
    qa.verify("json_path", body, path="claim.status", equals="Approved", covers=["ac:1", "okf:docs/features/claims/http/claims-api.md#decide-claim:does:1", "okf:docs/features/claims/flows/decide-a-claim.md:start:1", "okf:docs/features/claims/flows/decide-a-claim.md:end:1", "okf:docs/features/claims/flows/decide-a-claim.md:end-state"])
    qa.verify("json_path", body, path="claim.version", equals="2", covers=["ac:1", "okf:docs/features/claims/http/claims-api.md#decide-claim:does:1"])
    qa.check("the adjuster's note is carried onto the decided claim", qa.field(body, "claim.decision_note") == "Cover confirmed against the schedule.", covers=["ac:1", "okf:docs/features/claims/flows/decide-a-claim.md:end:1"])

    # The claim was Submitted a moment ago in this same process, so a re-read here is answered
    # by whatever the process is holding. The process has to go before the re-read means anything.
    restart = qa.tool("docker").run("compose", "-f", "compose.yml", "restart", "app", timeout=120.0)
    qa.check("the service restarts cleanly between the decision and the re-read", restart.ok, covers=["ac:2", "okf:docs/features/claims/http/claims-api.md#decide-claim:persistence:1"])

    def restarted_service_answers() -> bool:
        # A refused connection during the restart window is "not yet", not a verdict.
        try:
            return qa.http.get("/healthz").json()["status"] == "ok"
        except HttpError:
            return False

    qa.eventually("the restarted service answers /healthz again", restarted_service_answers, timeout=90.0, interval=0.5, covers=["ac:2", "okf:docs/features/claims/http/claims-api.md#decide-claim:persistence:1"])
    reread = qa.http.get("/api/claims/cl-1001", headers=bearer(adjuster), expect_status=200).json()["claim"]
    qa.verify("persists", (body["claim"], reread), subject="claim cl-1001", covers=["ac:2", "okf:docs/features/claims/http/claims-api.md#decide-claim:persistence:1", "okf:docs/features/claims/flows/decide-a-claim.md:start:1", "okf:docs/features/claims/flows/decide-a-claim.md:end:1", "okf:docs/features/claims/flows/decide-a-claim.md:end-state"])
    json.dump({"filed": who["claim"], "decided": body, "after_restart": reread}, qa.artifact("steps/decision.json", kind="json").open("w"))


@scenario(
    target=api,
    mechanism="live",
    covers=[
        "ac:3",
        "okf:docs/features/claims/http/claims-api.md#decide-claim:concurrency:1",
    ],
    preconditions=[
        "cl-1001 is on file at version 1 and is read exactly once",
        "both decisions quote the version from that one reading",
    ],
    checkpoints=[
        "the first decision off the reading is accepted",
        "the second, quoting the version the first spent, is refused 409 Stale Decision",
        "the claim on file is the one the first decision wrote",
    ],
    forbid=[
        "re-reading the claim between the accepted decision and the stale one",
        "asserting the refusal without asserting what survived on the claim",
    ],
)
def a_decision_quoting_a_spent_version_is_refused(qa: Qa) -> None:
    """Two adjusters off one reading: the second is working from a claim that moved."""
    who = one_claim_awaiting_a_decision(qa)
    adjuster = who["adjuster"]

    # One reading, and both writes quote it. Fetching the claim again before the second write
    # is the whole defect this scenario exists to exclude — the version would be current.
    opened = qa.http.get("/api/claims/cl-1001", headers=bearer(adjuster), expect_status=200).json()["claim"]
    version = opened["version"]

    first = qa.http.post("/api/claims/cl-1001/decision", json_body={"decision": "approve", "version": version, "note": "Approved on the first reading."}, headers=bearer(adjuster), expect_status=200).json()["claim"]
    qa.check("the first decision off the reading is accepted", qa.field(first, "status") == "Approved" and qa.field(first, "version") == version + 1, covers=["ac:3", "okf:docs/features/claims/http/claims-api.md#decide-claim:concurrency:1"])

    stale = qa.http.post("/api/claims/cl-1001/decision", json_body={"decision": "deny", "version": version, "note": "Denied from a stale reading."}, headers=bearer(adjuster), expect_status=409)
    qa.verify("conflict_on_stale", stale.status, subject="claim cl-1001", token="version", covers=["ac:3", "okf:docs/features/claims/http/claims-api.md#decide-claim:concurrency:1"])
    qa.verify("http_status", stale, code=409, title="Stale Decision", path="/api/claims/cl-1001/decision", covers=["ac:3", "okf:docs/features/claims/http/claims-api.md#decide-claim:concurrency:1"])

    current = qa.http.get("/api/claims/cl-1001", headers=bearer(adjuster), expect_status=200).json()["claim"]
    qa.verify("unchanged", (first, current), subject="claim cl-1001", covers=["ac:3", "okf:docs/features/claims/http/claims-api.md#decide-claim:concurrency:1"])
    json.dump({"opened": opened, "accepted": first, "refused": stale.json(), "current": current}, qa.artifact("steps/stale-decision.json", kind="json").open("w"))


@scenario(
    target=api,
    mechanism="live",
    covers=[
        "ac:4",
        "ac:5",
        "okf:docs/features/claims/http/claims-api.md#decide-claim:authorization:1",
        "okf:docs/features/claims/http/claims-api.md#decide-claim:errors:1",
        "okf:docs/features/claims/http/claims-api.md#decide-claim:errors:2",
    ],
    preconditions=[
        "cl-1001 is on file at version 1, filed by the holder who is refused below",
        "the holder's refusal is attempted against an id that is not on the books",
    ],
    checkpoints=[
        "a holder is refused 403 Adjusters Only before the claim is even looked up",
        "a decision outside approve/deny is refused 422 with errors.decision",
        "a version that is not a positive number is refused 422 with errors.version",
        "an id that is not on the books is refused 404 No Such Claim",
    ],
    forbid=[
        "proving the role rule with an id whose absence could explain the refusal",
        "reading a 422 and a 404 as interchangeable refusals",
    ],
)
def only_an_adjuster_decides_and_only_in_the_documented_shape(qa: Qa) -> None:
    """The role is checked before the ledger, and the body is checked after it."""
    who = one_claim_awaiting_a_decision(qa)
    adjuster, holder = who["adjuster"], who["holder"]

    # Against cl-9999 deliberately: a 403 for a claim that does not exist can only have come
    # from the role, so the ordering the book documents is what is being proved.
    forbidden = qa.http.post("/api/claims/cl-9999/decision", json_body={"decision": "approve", "version": 1}, headers=bearer(holder), expect_status=403)
    qa.verify("http_status", forbidden, code=403, title="Adjusters Only", path="/api/claims/cl-9999/decision", covers=["ac:4", "okf:docs/features/claims/http/claims-api.md#decide-claim:authorization:1"])

    unknown_word = qa.http.post("/api/claims/cl-1001/decision", json_body={"decision": "escalate", "version": 1}, headers=bearer(adjuster), expect_status=422)
    qa.verify("http_status", unknown_word, code=422, path="/api/claims/cl-1001/decision", covers=["ac:5", "okf:docs/features/claims/http/claims-api.md#decide-claim:errors:1"])
    qa.verify("json_path", unknown_word.json(), path="$.errors.decision", absent=False, covers=["ac:5", "okf:docs/features/claims/http/claims-api.md#decide-claim:errors:1"])

    bad_version = qa.http.post("/api/claims/cl-1001/decision", json_body={"decision": "approve", "version": 0}, headers=bearer(adjuster), expect_status=422)
    qa.verify("json_path", bad_version.json(), path="$.errors.version", absent=False, covers=["ac:5", "okf:docs/features/claims/http/claims-api.md#decide-claim:errors:1"])

    missing = qa.http.post("/api/claims/cl-9999/decision", json_body={"decision": "approve", "version": 1}, headers=bearer(adjuster), expect_status=404)
    qa.verify("http_status", missing, code=404, title="No Such Claim", path="/api/claims/cl-9999/decision", covers=["ac:5", "okf:docs/features/claims/http/claims-api.md#decide-claim:errors:2"])

    survived = qa.http.get("/api/claims/cl-1001", headers=bearer(adjuster), expect_status=200).json()["claim"]
    qa.verify("unchanged", (who["claim"], survived), subject="claim cl-1001", covers=["ac:4", "okf:docs/features/claims/http/claims-api.md#decide-claim:authorization:1"])
    json.dump({"forbidden": forbidden.json(), "unknown_word": unknown_word.json(), "bad_version": bad_version.json(), "missing": missing.json()}, qa.artifact("steps/refused-decisions.json", kind="json").open("w"))

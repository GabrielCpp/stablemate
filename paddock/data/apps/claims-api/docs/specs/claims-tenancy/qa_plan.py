"""The frozen QA plan for `claims-tenancy`.

No criterion in this story is observable with one identity. Every rule here is about what a
*second* caller is handed back for the same ledger, so all three seeded accounts are signed
in before the first assertion and the register is built by two different holders.

The identities come from the auth emulator beside the service, so there is no credential in
this file: `auth/seed.mjs` creates the three accounts before the API is allowed to answer,
and the adjuster's role is a custom claim the emulator stamps on the token.
"""

import json

from ostler_qa import Qa, plan, scenario, target


plan(run_id="qa-claims-tenancy", story="claims-tenancy")

api = target("api", driver="python", base_url="http://localhost:18085")

EMULATOR = "http://localhost:18086/identitytoolkit.googleapis.com/v1"
HOLDER_A = ("holder-a@example.com", "claims-bench-a")
HOLDER_B = ("holder-b@example.com", "claims-bench-b")
ADJUSTER = ("adjuster@example.com", "claims-bench-c")


def sign_in(qa: Qa, account: tuple[str, str]) -> dict:
    """A live identity from the emulator: the id token and the subject it carries."""
    email, password = account
    body = qa.http.post(
        f"{EMULATOR}/accounts:signInWithPassword?key=fake-api-key",
        json_body={"email": email, "password": password, "returnSecureToken": True},
        expect_status=200,
    ).json()
    return {"token": body["idToken"], "uid": body["localId"]}


def bearer(identity: dict) -> dict:
    return {"Authorization": f"Bearer {identity['token']}"}


def submission(policy_number: str, description: str) -> dict:
    return {
        "policy_number": policy_number,
        "incident_date": "2099-04-02",
        "amount_cents": 84000,
        "description": description,
    }


def two_holders_file_one_claim_each(qa: Qa) -> dict:
    """The one shared arrangement: an emptied desk with cl-1001 for A and cl-1002 for B.

    Written as a helper rather than a precondition step because all three scenarios need
    the *same* two claims and the ids are what the book's own checks name.
    """
    a, b, adjuster = sign_in(qa, HOLDER_A), sign_in(qa, HOLDER_B), sign_in(qa, ADJUSTER)
    qa.http.delete("/api/claims", headers=bearer(adjuster), expect_status=204)
    qa.http.post("/api/claims", json_body=submission("PL-5510", "Water ingress in the basement."), headers=bearer(a), expect_status=201)
    qa.http.post("/api/claims", json_body=submission("PL-6620", "Windscreen cracked on the motorway."), headers=bearer(b), expect_status=201)
    return {"a": a, "b": b, "adjuster": adjuster}


@scenario(
    target=api,
    mechanism="live",
    covers=[
        "ac:1",
        "ac:2",
        "ac:4",
        "okf:docs/features/claims/http/claims-api.md#list-claims:does:1",
        "okf:docs/features/claims/http/claims-api.md#list-claims:authorization:1",
        "okf:docs/features/claims/http/claims-api.md#list-claims:authorization:2",
        "okf:docs/features/claims/concepts/claim-tenancy.md:contract",
        "okf:docs/features/claims/http/claims-api.md#list-claims:contract",
        "okf:docs/features/claims/flows/file-a-claim.md:start:1",
        "okf:docs/features/claims/flows/file-a-claim.md:end:1",
        "okf:docs/features/claims/flows/file-a-claim.md:end-state",
    ],
    preconditions=[
        "the desk is emptied through DELETE /api/claims, holding the adjuster's token",
        "holder A files cl-1001 and holder B files cl-1002, each with their own token",
    ],
    checkpoints=[
        "holder A's register holds exactly their own claim",
        "holder B's register holds exactly their own claim, and it is a different one",
        "the adjuster's register holds both",
        "a holder with nothing on file is answered 200 with an empty register, not a refusal",
    ],
    forbid=[
        "reading one holder's register and inferring the other's from it",
        "asserting a count without also asserting whose claims were counted",
    ],
)
def a_register_holds_the_claims_of_whoever_asked(qa: Qa) -> None:
    """Two holders, one adjuster, one ledger — and three different answers to one route."""
    who = two_holders_file_one_claim_each(qa)

    mine = qa.http.get("/api/claims", headers=bearer(who["a"]), expect_status=200)
    mine_body = mine.json()
    qa.verify("http_status", mine, code=200, path="/api/claims", covers=["ac:1", "okf:docs/features/claims/http/claims-api.md#list-claims:does:1", "okf:docs/features/claims/http/claims-api.md#list-claims:contract"])
    qa.verify("json_path", mine_body, path="$.claims[0].version", absent=False, covers=["ac:1", "okf:docs/features/claims/http/claims-api.md#list-claims:does:1"])
    qa.verify("json_path", mine_body, path="claims[0].status", equals="Submitted", covers=["ac:1", "okf:docs/features/claims/http/claims-api.md#list-claims:does:1", "okf:docs/features/claims/flows/file-a-claim.md:start:1", "okf:docs/features/claims/flows/file-a-claim.md:end:1", "okf:docs/features/claims/flows/file-a-claim.md:end-state"])
    qa.verify("count", mine_body["claims"], subject="claims", equals=1, covers=["ac:2", "okf:docs/features/claims/http/claims-api.md#list-claims:authorization:1", "okf:docs/features/claims/flows/file-a-claim.md:start:1", "okf:docs/features/claims/flows/file-a-claim.md:end:1", "okf:docs/features/claims/flows/file-a-claim.md:end-state"])
    qa.verify("json_path", mine_body, path="$.claims[0].holder_uid", equals=who["a"]["uid"], covers=["ac:2", "okf:docs/features/claims/http/claims-api.md#list-claims:authorization:1"])

    theirs = qa.http.get("/api/claims", headers=bearer(who["b"]), expect_status=200).json()["claims"]
    qa.verify("count", theirs, subject="claims", equals=1, covers=["ac:2", "okf:docs/features/claims/http/claims-api.md#list-claims:authorization:1"])
    qa.check("the second holder is shown their own claim and not the first holder's", theirs[0]["id"] == "cl-1002" and theirs[0]["holder_uid"] == who["b"]["uid"], covers=["ac:2", "okf:docs/features/claims/concepts/claim-tenancy.md:contract"])

    everything = qa.http.get("/api/claims", headers=bearer(who["adjuster"]), expect_status=200).json()["claims"]
    qa.verify("count", everything, subject="claims", equals=2, covers=["ac:1", "okf:docs/features/claims/http/claims-api.md#list-claims:authorization:2"])
    qa.check("the adjuster's register is in the order the claims were written", [claim["id"] for claim in everything] == ["cl-1001", "cl-1002"], covers=["okf:docs/features/claims/concepts/claim-tenancy.md:contract"])

    # An empty register is a register, not a 404: the adjuster empties the desk and holder A
    # — who had a claim a moment ago — is still answered on the same terms.
    qa.http.delete("/api/claims", headers=bearer(who["adjuster"]), expect_status=204)
    emptied = qa.http.get("/api/claims", headers=bearer(who["a"]), expect_status=200)
    qa.verify("http_status", emptied, code=200, path="/api/claims", covers=["ac:4"])
    qa.verify("count", emptied.json()["claims"], subject="claims", equals=0, covers=["ac:4"])
    json.dump({"holder_a": mine_body, "holder_b": theirs, "adjuster": everything}, qa.artifact("steps/registers.json", kind="json").open("w"))


@scenario(
    target=api,
    mechanism="live",
    covers=[
        "ac:3",
        "okf:docs/features/claims/http/claims-api.md#get-claim:does:1",
        "okf:docs/features/claims/http/claims-api.md#get-claim:contract",
        "okf:docs/features/claims/concepts/claim-tenancy.md:contract",
    ],
    preconditions=[
        "cl-1001 belongs to holder A and cl-1002 to holder B",
        "both readings are of the same claim, one after the other",
    ],
    checkpoints=[
        "the holder the claim belongs to is answered 200 with that claim",
        "an adjuster is answered 200 with the same claim, field for field",
    ],
    forbid=["proving the adjuster's reading against a claim the adjuster filed"],
)
def a_claim_answers_to_its_holder_and_to_an_adjuster(qa: Qa) -> None:
    """Two identities entitled to one claim, and they are entitled for different reasons."""
    who = two_holders_file_one_claim_each(qa)

    owned = qa.http.get("/api/claims/cl-1001", headers=bearer(who["a"]), expect_status=200)
    owned_body = owned.json()
    qa.verify("http_status", owned, code=200, path="/api/claims/cl-1001", covers=["ac:3", "okf:docs/features/claims/http/claims-api.md#get-claim:does:1", "okf:docs/features/claims/http/claims-api.md#get-claim:contract"])
    qa.verify("json_path", owned_body, path="$.claim.id", equals="cl-1001", covers=["ac:3", "okf:docs/features/claims/http/claims-api.md#get-claim:does:1"])
    qa.check("the claim the holder is shown is the one they filed", owned_body["claim"]["holder_uid"] == who["a"]["uid"], covers=["ac:3", "okf:docs/features/claims/concepts/claim-tenancy.md:contract"])

    overseen = qa.http.get("/api/claims/cl-1001", headers=bearer(who["adjuster"]), expect_status=200)
    qa.verify("http_status", overseen, code=200, path="/api/claims/cl-1001", covers=["ac:3", "okf:docs/features/claims/http/claims-api.md#get-claim:contract"])
    qa.verify("unchanged", (owned_body["claim"], overseen.json()["claim"]), subject="claim cl-1001", covers=["ac:3", "okf:docs/features/claims/concepts/claim-tenancy.md:contract"])


@scenario(
    target=api,
    mechanism="live",
    covers=[
        "ac:5",
        "okf:docs/features/claims/http/claims-api.md#get-claim:authorization:1",
        "okf:docs/features/claims/http/claims-api.md#get-claim:errors:1",
        "okf:docs/features/claims/concepts/claim-tenancy.md:contract",
    ],
    preconditions=[
        "cl-1002 is on file and belongs to holder B",
        "cl-9999 is on nobody's books",
    ],
    checkpoints=[
        "a stranger's claim is refused 403 Not Your Claim",
        "an id that is not on the books is refused 404 No Such Claim",
        "the two refusals are told apart by the same caller in the same run",
    ],
    forbid=["reading the refusal for an id that does and does not exist as one case"],
)
def a_stranger_is_refused_differently_from_a_claim_that_is_not_there(qa: Qa) -> None:
    """403 and 404 are different answers, and confusing them leaks the ledger's contents."""
    who = two_holders_file_one_claim_each(qa)

    forbidden = qa.http.get("/api/claims/cl-1002", headers=bearer(who["a"]), expect_status=403)
    qa.verify("http_status", forbidden, code=403, title="Not Your Claim", path="/api/claims/cl-1002", covers=["ac:5", "okf:docs/features/claims/http/claims-api.md#get-claim:authorization:1", "okf:docs/features/claims/concepts/claim-tenancy.md:contract"])

    missing = qa.http.get("/api/claims/cl-9999", headers=bearer(who["a"]), expect_status=404)
    qa.verify("http_status", missing, code=404, title="No Such Claim", path="/api/claims/cl-9999", covers=["ac:5", "okf:docs/features/claims/http/claims-api.md#get-claim:errors:1"])
    qa.check("one caller is answered 403 for a claim that exists and 404 for one that does not", forbidden.status != missing.status, covers=["ac:5", "okf:docs/features/claims/http/claims-api.md#get-claim:authorization:1", "okf:docs/features/claims/http/claims-api.md#get-claim:errors:1"])
    json.dump({"forbidden": forbidden.json(), "missing": missing.json()}, qa.artifact("steps/refusals.json", kind="json").open("w"))


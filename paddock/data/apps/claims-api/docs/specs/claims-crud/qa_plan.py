"""The frozen QA plan for `claims-crud`.

Every identity this plan signs in with is minted at run time from the auth emulator beside
the service, so there is no live credential in this file and none in the repo:
`accounts:signInWithPassword` accepts any string as an API key against the emulator, and the
three fixture accounts are created by `auth/seed.mjs` before the API is allowed to answer.

The two refusal arms the book promises — a token issued for another project, and one past
its expiry — cannot be signed in for, because the emulator only ever hands back a live token
for the project it is running. They are *constructed* instead, and frozen as constants below
rather than built at run time: the emulator's tokens are unsigned (`alg: none`) and the Admin
SDK, pointed at an emulator, checks the issuer, the audience and the expiry rather than a
signature. So a hand-written token with a foreign `iss`/`aud`, or a past `exp`, is exactly
the credential a real caller would present and be refused for. Neither opens anything: one
names a project this service was never configured for, the other expired in 2020.
"""

import json

from _fixtures.claims import submission
from _fixtures.identity import ADJUSTER, HOLDER_A, bearer, sign_in
from ostler_qa import HttpError, Qa, plan, scenario, target


plan(run_id="qa-claims-crud", story="claims-crud")

api = target("api", driver="python", base_url="http://localhost:18085")


#: `{"alg":"none","typ":"JWT"}` over claims naming `other-insurer-example` as both issuer and
#: audience, `sub: constructed-holder`, and an expiry in 2286. Well-formed for some other
#: deployment of this same stack, and never issued by the project this service trusts.
FOREIGN_PROJECT_TOKEN = (
    "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0."
    "eyJpc3MiOiJodHRwczovL3NlY3VyZXRva2VuLmdvb2dsZS5jb20vb3RoZXItaW5zdXJlci1leGFtcGxlIiwiYXVk"
    "Ijoib3RoZXItaW5zdXJlci1leGFtcGxlIiwiYXV0aF90aW1lIjoxNjAwMDAwMDAwLCJ1c2VyX2lkIjoiY29uc3Ry"
    "dWN0ZWQtaG9sZGVyIiwic3ViIjoiY29uc3RydWN0ZWQtaG9sZGVyIiwiaWF0IjoxNjAwMDAwMDAwLCJleHAiOjk5"
    "OTk5OTk5OTksImZpcmViYXNlIjp7ImlkZW50aXRpZXMiOnt9LCJzaWduX2luX3Byb3ZpZGVyIjoicGFzc3dvcmQi"
    "fX0."
)


#: The same shape with this project's own issuer and audience, and an `exp` of 1600003600 —
#: September 2020. The only thing wrong with it is that the session it stands for is over,
#: which is the arm the book documents separately from a token that was never ours.
EXPIRED_TOKEN = (
    "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0."
    "eyJpc3MiOiJodHRwczovL3NlY3VyZXRva2VuLmdvb2dsZS5jb20vY2xhaW1zLWFwaS1leGFtcGxlIiwiYXVkIjoi"
    "Y2xhaW1zLWFwaS1leGFtcGxlIiwiYXV0aF90aW1lIjoxNjAwMDAwMDAwLCJ1c2VyX2lkIjoiY29uc3RydWN0ZWQt"
    "aG9sZGVyIiwic3ViIjoiY29uc3RydWN0ZWQtaG9sZGVyIiwiaWF0IjoxNjAwMDAwMDAwLCJleHAiOjE2MDAwMDM2"
    "MDAsImZpcmViYXNlIjp7ImlkZW50aXRpZXMiOnt9LCJzaWduX2luX3Byb3ZpZGVyIjoicGFzc3dvcmQifX0."
)


@scenario(
    target=api,
    mechanism="live",
    covers=[
        "ac:1",
        "ac:4",
        "ac:5",
        "okf:docs/features/claims/http/claims-api.md:contract",
        "okf:docs/features/claims/http/claims-api.md#submit-claim:contract",
        "okf:docs/features/claims/http/claims-api.md#submit-claim:does:1",
        "okf:docs/features/claims/http/claims-api.md#submit-claim:consistency:1",
        "okf:docs/features/claims/http/claims-api.md#submit-claim:errors:1",
        "okf:docs/features/claims/http/claims-api.md#submit-claim:errors:2",
        "okf:docs/features/claims/http/claims-api.md#submit-claim:persistence:1",
        "okf:docs/features/claims/concepts/claim-ledger.md:contract",
        "okf:docs/features/claims/ops/auth-emulator.md:contract",
        "okf:docs/features/claims/flows/file-a-claim.md:start:1",
        "okf:docs/features/claims/flows/file-a-claim.md:end:1",
        "okf:docs/features/claims/flows/file-a-claim.md:end-state",
    ],
    preconditions=[
        "the desk is emptied through DELETE /api/claims, holding the adjuster's token",
        "holder A is signed in at the emulator and the claim is filed with that token",
    ],
    checkpoints=[
        "an acceptable submission answers 201 as Submitted at version 1",
        "the stored record is attributed to the calling token's subject",
        "the record comes back under the field names the contract declares",
        "the service is restarted between the accepted write and the re-read",
        "a repeat of the same submission answers 409 Duplicate Claim and writes nothing",
        "a submission breaking four rules answers 422 with a message under each field",
    ],
    forbid=[
        "an in-process re-read as evidence of durability",
        "reading the ledger file instead of the documented route",
    ],
)
def file_a_claim_and_prove_it_outlives_the_process(qa: Qa) -> None:
    """An accepted claim is stored, attributed, shaped by the contract, and durable."""
    holder = sign_in(qa, HOLDER_A)
    adjuster = sign_in(qa, ADJUSTER)
    qa.http.delete("/api/claims", headers=bearer(adjuster), expect_status=204)

    created = qa.http.post("/api/claims", json_body=submission(), headers=bearer(holder), expect_status=201)
    body = created.json()
    claim = body["claim"]
    qa.verify("http_status", created, code=201, path="/api/claims", covers=["ac:1", "okf:docs/features/claims/http/claims-api.md:contract", "okf:docs/features/claims/http/claims-api.md#submit-claim:contract", "okf:docs/features/claims/http/claims-api.md#submit-claim:does:1"])
    qa.verify("json_path", body, path="$.claim.status", equals="Submitted", covers=["ac:1", "okf:docs/features/claims/http/claims-api.md#submit-claim:does:1"])
    qa.verify("json_path", body, path="$.claim.version", equals="1", covers=["ac:1", "okf:docs/features/claims/http/claims-api.md#submit-claim:does:1"])
    qa.check("the claim is attributed to the calling token's subject", qa.field(claim, "holder_uid") == qa.field(holder, "uid"), covers=["ac:1", "okf:docs/features/claims/http/claims-api.md#submit-claim:does:1", "okf:docs/features/claims/ops/auth-emulator.md:contract"])
    qa.check("the claim is issued the first identifier the ledger has to give", qa.field(claim, "id") == "cl-1001", covers=["okf:docs/features/claims/concepts/claim-ledger.md:contract"])
    qa.verify("json_path", body, path="$.claim.amount_cents", absent=False, covers=["ac:5", "okf:docs/features/claims/http/claims-api.md#submit-claim:consistency:1"])
    qa.verify("json_path", body, path="$.claim.holder_uid", absent=False, covers=["ac:5", "okf:docs/features/claims/http/claims-api.md#submit-claim:consistency:1"])
    qa.verify("json_path", body, path="$.claim.policy_number", absent=False, covers=["ac:5", "okf:docs/features/claims/http/claims-api.md#submit-claim:consistency:1"])
    qa.verify("json_path", body, path="$.claim.incident_date", absent=False, covers=["ac:5", "okf:docs/features/claims/http/claims-api.md#submit-claim:consistency:1"])

    # The book promises the claim is still on file after the service restarts, and a
    # re-read inside the process that took the write is exactly what a ledger held in
    # memory would also answer. The process that accepted the write has to die first.
    restart = qa.tool("docker").run("compose", "-f", "compose.yml", "restart", "app", timeout=120.0)
    qa.check("the service restarts cleanly between the write and the re-read", restart.ok, covers=["okf:docs/features/claims/http/claims-api.md#submit-claim:persistence:1"])

    def restarted_service_answers() -> bool:
        # A refused connection during the restart window is "not yet", not a verdict.
        try:
            return qa.http.get("/healthz").json()["status"] == "ok"
        except HttpError:
            return False

    qa.eventually("the restarted service answers /healthz again", restarted_service_answers, timeout=90.0, interval=0.5, covers=["okf:docs/features/claims/http/claims-api.md#submit-claim:persistence:1"])
    reread = qa.http.get("/api/claims/cl-1001", headers=bearer(holder), expect_status=200).json()["claim"]
    qa.verify("persists", (claim, reread), subject="claim cl-1001", covers=["ac:1", "okf:docs/features/claims/http/claims-api.md#submit-claim:persistence:1"])
    qa.check("the ledger reads back the claims it was written with", qa.field(reread, "holder_uid") == qa.field(holder, "uid"), covers=["okf:docs/features/claims/concepts/claim-ledger.md:contract"])

    duplicate = qa.http.post("/api/claims", json_body=submission(), headers=bearer(holder), expect_status=409)
    qa.verify("http_status", duplicate, code=409, title="Duplicate Claim", path="/api/claims", covers=["ac:4", "okf:docs/features/claims/http/claims-api.md#submit-claim:errors:2"])
    # The register is where the journey ends, so this reading carries the end state as well as
    # the refusal's consequence: exactly the one claim the holder filed, still Submitted.
    register = qa.http.get("/api/claims", headers=bearer(holder), expect_status=200).json()
    after_duplicate = register["claims"]
    qa.verify("json_path", register, path="claims[0].status", equals="Submitted", covers=["ac:1", "okf:docs/features/claims/flows/file-a-claim.md:start:1", "okf:docs/features/claims/flows/file-a-claim.md:end:1", "okf:docs/features/claims/flows/file-a-claim.md:end-state"])
    qa.verify("count", after_duplicate, subject="claims", equals=1, covers=["ac:4", "okf:docs/features/claims/http/claims-api.md#submit-claim:errors:2", "okf:docs/features/claims/flows/file-a-claim.md:start:1", "okf:docs/features/claims/flows/file-a-claim.md:end:1", "okf:docs/features/claims/flows/file-a-claim.md:end-state"])

    refused = qa.http.post("/api/claims", json_body={"policy_number": "  ", "incident_date": "14/03/2099", "amount_cents": 0, "description": ""}, headers=bearer(holder), expect_status=422)
    refused_body = refused.json()
    qa.verify("http_status", refused, code=422, path="/api/claims", covers=["ac:4", "okf:docs/features/claims/http/claims-api.md#submit-claim:errors:1"])
    qa.verify("json_path", refused_body, path="$.errors.incident_date", absent=False, covers=["ac:4", "okf:docs/features/claims/http/claims-api.md#submit-claim:errors:1"])
    qa.verify("json_path", refused_body, path="$.errors.amount_cents", absent=False, covers=["ac:4", "okf:docs/features/claims/http/claims-api.md#submit-claim:errors:1"])
    qa.verify("json_path", refused_body, path="$.errors.policy_number", absent=False, covers=["ac:4", "okf:docs/features/claims/http/claims-api.md#submit-claim:errors:1"])
    qa.verify("json_path", refused_body, path="$.errors.description", absent=False, covers=["ac:4", "okf:docs/features/claims/http/claims-api.md#submit-claim:errors:1"])
    json.dump({"created": claim, "reread": reread, "duplicate": duplicate.json(), "refused": refused_body}, qa.artifact("steps/submission.json", kind="json").open("w"))


@scenario(
    target=api,
    mechanism="live",
    covers=[
        "ac:2",
        "ac:3",
        "okf:docs/features/claims/http/claims-api.md#submit-claim:auth:1",
        "okf:docs/features/claims/http/claims-api.md#submit-claim:auth:2",
        "okf:docs/features/claims/http/claims-api.md#submit-claim:errors:3",
    ],
    preconditions=[
        "cl-1001 is already on file from the accepted submission above",
        "each refusal is attempted with a body that would otherwise be accepted",
    ],
    checkpoints=[
        "a request with no Authorization header answers 401 Unauthorized",
        "a well-formed token issued for another project answers 401 Unauthorized",
        "a token past its expiry answers 401 Unauthorized",
        "the ledger is unchanged across all three refusals",
        "every refusal body is captured whole for the record",
    ],
    forbid=[
        "treating a well-formed JWT as a verified one",
        "reaching the ledger with any of the three refused credentials",
    ],
)
def refuse_credentials_this_project_never_issued(qa: Qa) -> None:
    """Being a JWT is not being a verified one, and a refusal is a Problem."""
    holder = sign_in(qa, HOLDER_A)
    before = qa.http.get("/api/claims", headers=bearer(holder), expect_status=200).json()["claims"]

    anonymous = qa.http.post("/api/claims", json_body=submission("PL-9000"), expect_status=401)
    qa.verify("http_status", anonymous, code=401, title="Unauthorized", path="/api/claims", covers=["ac:2", "okf:docs/features/claims/http/claims-api.md#submit-claim:auth:1", "okf:docs/features/claims/http/claims-api.md#submit-claim:errors:3"])

    stranger = qa.http.post("/api/claims", json_body=submission("PL-9001"), headers={"Authorization": f"Bearer {FOREIGN_PROJECT_TOKEN}"}, expect_status=401)
    qa.verify("http_status", stranger, code=401, title="Unauthorized", path="/api/claims", covers=["ac:2", "okf:docs/features/claims/http/claims-api.md#submit-claim:auth:1", "okf:docs/features/claims/http/claims-api.md#submit-claim:errors:3"])

    expired = qa.http.post("/api/claims", json_body=submission("PL-9002"), headers={"Authorization": f"Bearer {EXPIRED_TOKEN}"}, expect_status=401)
    qa.verify("http_status", expired, code=401, title="Unauthorized", path="/api/claims", covers=["ac:3", "okf:docs/features/claims/http/claims-api.md#submit-claim:auth:2", "okf:docs/features/claims/http/claims-api.md#submit-claim:errors:3"])

    after = qa.http.get("/api/claims", headers=bearer(holder), expect_status=200).json()["claims"]
    qa.verify("unchanged", (before, after), subject="claims", covers=["ac:2", "ac:3", "okf:docs/features/claims/http/claims-api.md#submit-claim:auth:1", "okf:docs/features/claims/http/claims-api.md#submit-claim:auth:2"])
    # The bodies are written down whole rather than asserted about, because what the clause
    # forbids — anything out of the rejected credential appearing in the refusal — is a
    # property of prose the status code cannot see. The record is what makes it readable.
    json.dump({"presented": {"foreign": FOREIGN_PROJECT_TOKEN, "expired": EXPIRED_TOKEN}, "anonymous": anonymous.json(), "foreign_project": stranger.json(), "past_expiry": expired.json()}, qa.artifact("steps/refusals.json", kind="json").open("w"))


@scenario(
    target=api,
    mechanism="live",
    covers=[
        "ac:6",
        "okf:docs/features/claims/http/claims-api.md#get-health:does:1",
        "okf:docs/features/claims/http/claims-api.md#reset-claims:contract",
        "okf:docs/features/claims/http/claims-api.md#reset-claims:does:1",
        "okf:docs/features/claims/http/claims-api.md#reset-claims:authorization:1",
    ],
    preconditions=[
        "cl-1001 is on file, so an emptied ledger is distinguishable from a ledger that was never written",
        "the holder's reset is attempted before the adjuster's",
    ],
    checkpoints=[
        "GET /healthz answers 200 with status ok and asks for no token",
        "a holder's reset answers 403 Adjusters Only and empties nothing",
        "an adjuster's reset answers 204 and leaves no claims on file",
    ],
    forbid=["emptying the ledger by any route but the documented one"],
)
def health_needs_no_token_and_reset_needs_a_role(qa: Qa) -> None:
    """The one unprotected route and the one destructive one, proved from both sides."""
    health = qa.http.get("/healthz", expect_status=200)
    qa.verify("http_status", health, code=200, path="/healthz", covers=["ac:6", "okf:docs/features/claims/http/claims-api.md#get-health:does:1"])
    qa.verify("json_path", health.json(), path="$.status", equals="ok", covers=["ac:6", "okf:docs/features/claims/http/claims-api.md#get-health:does:1"])

    holder = sign_in(qa, HOLDER_A)
    adjuster = sign_in(qa, ADJUSTER)
    refused = qa.http.delete("/api/claims", headers=bearer(holder), expect_status=403)
    qa.verify("http_status", refused, code=403, title="Adjusters Only", path="/api/claims", covers=["ac:6", "okf:docs/features/claims/http/claims-api.md#reset-claims:authorization:1"])
    survived = qa.http.get("/api/claims", headers=bearer(holder), expect_status=200).json()["claims"]
    qa.verify("count", survived, subject="claims", equals=1, covers=["ac:6", "okf:docs/features/claims/http/claims-api.md#reset-claims:authorization:1"])

    emptied = qa.http.delete("/api/claims", headers=bearer(adjuster), expect_status=204)
    qa.check("the adjuster's reset answers 204 with no body", emptied.status == 204 and not emptied.text.strip(), covers=["ac:6", "okf:docs/features/claims/http/claims-api.md#reset-claims:does:1"])
    remaining = qa.http.get("/api/claims", headers=bearer(adjuster), expect_status=200).json()["claims"]
    qa.verify("count", remaining, subject="claims", equals=0, covers=["ac:6", "okf:docs/features/claims/http/claims-api.md#reset-claims:does:1", "okf:docs/features/claims/http/claims-api.md#reset-claims:contract"])

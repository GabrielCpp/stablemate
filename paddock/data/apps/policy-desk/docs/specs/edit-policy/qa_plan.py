import json

from _fixtures.policies import amendment_body, valid_policy
from ostler_qa import Qa, plan, scenario, target


plan(run_id="qa-edit-policy", story="edit-policy")

api = target("api", base_url="http://localhost:18084")
web = target(
    "web",
    driver="playwright",
    base_url="http://localhost:18084",
    browser="chromium",
    recording={"required": True, "mode": "window"},
)


@scenario(
    target=api,
    mechanism="live",
    covers=[
        "ac:1",
        "ac:3",
        "okf:docs/features/policy/http/policy-desk-api.md:contract",
        "okf:docs/features/policy/http/policy-desk-api.md#put-policy:contract",
        "okf:docs/features/policy/http/policy-desk-api.md#put-policy:does:1",
        "okf:docs/features/policy/http/policy-desk-api.md#put-policy:does:2",
        "okf:docs/features/policy/http/policy-desk-api.md#put-policy:errors:2",
    ],
    preconditions=[
        "PN-1001 is created through POST /api/policies on the empty desk",
        "the policy's current record and the complete ledger are captured before writing",
    ],
    checkpoints=[
        "the amendment omits policy_number and carries the captured version",
        "the response is 200 with version incremented and status unchanged",
        "the other records retain their complete fields, status, and versions",
        "an invalid premium is rejected with a premium field error",
        "a past start date remains acceptable for the existing policy",
    ],
    forbid=["re-reading the policy between the before-read and the amendment"],
)
def amend_policy_and_preserve_the_ledger(qa: Qa) -> None:
    """A valid amendment is conditional, durable, and does not rewrite neighbours."""
    qa.http.delete("/api/policies", expect_status=204)
    qa.http.post("/api/policies", json_body=valid_policy("PN-1001"), expect_status=201)
    qa.http.post("/api/policies", json_body=valid_policy("PN-1002", email="sam@example.com"), expect_status=201)
    before_ledger = qa.http.get("/api/policies").json()
    before = qa.http.get("/api/policies/pn-1001").json()["policy"]
    qa.check("fixture is the expected amendable policy", qa.field(before, "policy_number") == "PN-1001", covers=["ac:1", "ac:3"])
    qa.check("fixture id is the slug of its policy number", qa.field(before, "id") == "pn-1001", covers=["okf:docs/features/policy/http/policy-desk-api.md:contract"])
    premium = before["premium"] + 1
    response = qa.http.put(
        "/api/policies/pn-1001",
        json_body=amendment_body(before, premium),
        expect_status=200,
    )
    stored = response.json()["policy"]
    qa.check("amendment answers 200", qa.field(stored, "policy_number") == qa.field(before, "policy_number"), covers=["ac:1", "okf:docs/features/policy/http/policy-desk-api.md:contract", "okf:docs/features/policy/http/policy-desk-api.md#put-policy:contract"])
    qa.verify("http_status", response, code=200, path="/api/policies/pn-1001", covers=["ac:1", "okf:docs/features/policy/http/policy-desk-api.md#put-policy:does:1"])
    qa.verify("json_path", response.json(), path="policy.version", equals="2", covers=["ac:1", "okf:docs/features/policy/http/policy-desk-api.md#put-policy:does:1"])
    qa.check("version bumps exactly once", qa.field(stored, "version") == qa.field(before, "version") + 1, covers=["ac:1", "okf:docs/features/policy/http/policy-desk-api.md#put-policy:does:1"])
    qa.check("status remains unchanged", qa.field(stored, "status") == qa.field(before, "status"), covers=["ac:1"])
    qa.check("policy number remains the id-derived value", qa.field(stored, "policy_number") == qa.field(before, "policy_number"), covers=["ac:3"])
    after_ledger = qa.http.get("/api/policies").json()
    others_before = {item["id"]: item for item in before_ledger["policies"] if item["id"] != "pn-1001"}
    others_after = {item["id"]: item for item in after_ledger["policies"] if item["id"] != "pn-1001"}
    qa.check("every other policy is unchanged", others_after == others_before, covers=["okf:docs/features/policy/http/policy-desk-api.md#put-policy:does:2"])
    neighbour_before = next(item for item in before_ledger["policies"] if item["id"] == "pn-1002")
    neighbour_after = next(item for item in after_ledger["policies"] if item["id"] == "pn-1002")
    qa.verify("unchanged", (neighbour_before, neighbour_after), subject="policy pn-1002", except_fields=[], covers=["okf:docs/features/policy/http/policy-desk-api.md#put-policy:does:2"])
    qa.verify("keys_unchanged", ({item["id"]: item for item in before_ledger["policies"]}, {item["id"]: item for item in after_ledger["policies"]}), subject="policies", covers=["okf:docs/features/policy/http/policy-desk-api.md#put-policy:does:2"])
    invalid = dict(amendment_body(stored, premium), version=stored["version"], premium=0)
    invalid_response = qa.http.put("/api/policies/pn-1001", json_body=invalid, expect_status=422)
    invalid_body = invalid_response.json()
    qa.check("invalid amendment answers 422 with premium error", "premium" in qa.field(invalid_body, "errors"), covers=["ac:3", "okf:docs/features/policy/http/policy-desk-api.md#put-policy:errors:2"])
    qa.verify("http_status", invalid_response, code=422, path="/api/policies/pn-1001", covers=["ac:3", "okf:docs/features/policy/http/policy-desk-api.md#put-policy:errors:2"])
    qa.verify("json_path", invalid_body, path="errors.premium", absent=False, covers=["ac:3", "okf:docs/features/policy/http/policy-desk-api.md#put-policy:errors:2"])
    json.dump({"before": before, "amended": stored, "invalid": invalid_body}, qa.artifact("steps/amendment.json", kind="json").open("w"))


@scenario(
    target=api,
    mechanism="live",
    covers=[
        "ac:2",
        "ac:6",
        "okf:docs/features/policy/http/policy-desk-api.md#put-policy:concurrency:1",
        "okf:docs/features/policy/http/policy-desk-api.md#put-policy:errors:1",
        "okf:docs/features/policy/http/policy-desk-api.md#put-policy:errors:3",
    ],
    preconditions=[
        "GET /api/policies/pn-1001 returns the same version used by both writes",
        "the first write is accepted before the stale write is sent",
    ],
    checkpoints=[
        "the missing-version request answers 400 Version Required",
        "the first write changes the policy",
        "the second write reuses the first reading's version and answers 409 Stale Policy",
        "the stale response leaves the stored record equal to the post-first-write record",
        "an unknown id answers 404 Unknown Policy",
    ],
    forbid=["refreshing the version before the stale write", "treating a 409 as a successful amendment"],
)
def reject_missing_and_stale_amendments_without_erasing_the_reading(qa: Qa) -> None:
    """Missing and stale version tokens refuse writes while preserving the real record."""
    original = qa.http.get("/api/policies/pn-1001").json()["policy"]
    missing_body = {
        key: value
        for key, value in amendment_body(original, original["premium"] + 2).items()
        if key != "version"
    }
    missing = qa.http.put("/api/policies/pn-1001", json_body=missing_body, expect_status=400)
    qa.check("missing version is refused as Version Required", qa.field(missing.json(), "title") == "Version Required", covers=["ac:2", "okf:docs/features/policy/http/policy-desk-api.md#put-policy:errors:1"])
    qa.verify("http_status", missing, code=400, title="Version Required", path="/api/policies/pn-1001", covers=["ac:2", "okf:docs/features/policy/http/policy-desk-api.md#put-policy:errors:1"])
    first = qa.http.put("/api/policies/pn-1001", json_body=amendment_body(original, original["premium"] + 2), expect_status=200).json()["policy"]
    stale = qa.http.put("/api/policies/pn-1001", json_body=amendment_body(original, original["premium"] + 3), expect_status=409)
    qa.check("stale version is refused as Stale Policy", qa.field(stale.json(), "title") == "Stale Policy", covers=["ac:2", "ac:6", "okf:docs/features/policy/http/policy-desk-api.md#put-policy:concurrency:1"])
    qa.verify("conflict_on_stale", stale, subject="policy pn-1001", token="version", covers=["ac:2", "ac:6", "okf:docs/features/policy/http/policy-desk-api.md#put-policy:concurrency:1"])
    qa.verify("http_status", stale, code=409, title="Stale Policy", path="/api/policies/pn-1001", covers=["ac:2", "ac:6", "okf:docs/features/policy/http/policy-desk-api.md#put-policy:concurrency:1"])
    current = qa.http.get("/api/policies/pn-1001").json()["policy"]
    qa.check("stale write changes nothing", current == first, covers=["ac:2", "ac:6"])
    unknown = qa.http.put("/api/policies/missing", json_body=amendment_body(original, original["premium"]), expect_status=404)
    qa.check("unknown amendment is identified", qa.field(unknown.json(), "title") == "Unknown Policy", covers=["okf:docs/features/policy/http/policy-desk-api.md#put-policy:errors:3"])
    qa.verify("http_status", unknown, code=404, title="Unknown Policy", path="/api/policies/missing", covers=["okf:docs/features/policy/http/policy-desk-api.md#put-policy:errors:3"])
    json.dump({"original": original, "first": first, "stale": stale.json(), "current": current}, qa.artifact("steps/stale-amendment.json", kind="json").open("w"))


@scenario(
    target=api,
    mechanism="live",
    covers=[
        "ac:4",
        "ac:5",
        "okf:docs/features/policy/http/policy-desk-api.md#post-policy-cancel:contract",
        "okf:docs/features/policy/http/policy-desk-api.md#post-policy-cancel:does:1",
        "okf:docs/features/policy/http/policy-desk-api.md#post-policy-cancel:does:2",
        "okf:docs/features/policy/http/policy-desk-api.md#post-policy-cancel:errors:1",
        "okf:docs/features/policy/http/policy-desk-api.md#post-policy-cancel:errors:2",
        "okf:docs/features/policy/http/policy-desk-api.md#post-policy-cancel:errors:3",
        "okf:docs/features/policy/http/policy-desk-api.md#post-policy-cancel:errors:4",
    ],
    preconditions=[
        "GET /api/policies/pn-1001 returns a current Draft policy and its version",
        "the invalid confirmation is attempted before the valid cancellation",
    ],
    checkpoints=[
        "wrong confirmation answers 422 with errors.confirm and does not change the policy",
        "missing version answers 400 Version Required",
        "stale version answers 409 Stale Policy",
        "the matching policy number answers 200 with Cancelled at the bumped version",
        "the cancelled record survives a fresh GET",
        "the register still lists the cancelled policy",
        "an unknown cancellation answers 404 Unknown Policy",
    ],
    forbid=["cancelling without typing the policy number", "using the stale error as proof of cancellation"],
)
def cancel_only_after_confirmation_and_version_match(qa: Qa) -> None:
    """Cancellation requires both the typed identity and the current compare-and-swap token."""
    before = qa.http.get("/api/policies/pn-1001").json()["policy"]
    wrong = qa.http.post("/api/policies/pn-1001/cancel", json_body={"version": before["version"], "confirm": "WRONG"}, expect_status=422)
    qa.check("wrong confirmation is beside confirm", "confirm" in qa.field(wrong.json(), "errors"), covers=["ac:4", "okf:docs/features/policy/http/policy-desk-api.md#post-policy-cancel:errors:1"])
    qa.verify("http_status", wrong, code=422, path="/api/policies/pn-1001/cancel", covers=["ac:4", "okf:docs/features/policy/http/policy-desk-api.md#post-policy-cancel:errors:1"])
    qa.verify("json_path", wrong.json(), path="errors.confirm", absent=False, covers=["ac:4", "okf:docs/features/policy/http/policy-desk-api.md#post-policy-cancel:errors:1"])
    missing = qa.http.post("/api/policies/pn-1001/cancel", json_body={"confirm": before["policy_number"]}, expect_status=400)
    qa.check("missing cancellation version is refused", qa.field(missing.json(), "title") == "Version Required", covers=["okf:docs/features/policy/http/policy-desk-api.md#post-policy-cancel:errors:2"])
    stale = qa.http.post("/api/policies/pn-1001/cancel", json_body={"version": before["version"] - 1, "confirm": before["policy_number"]}, expect_status=409)
    qa.check("stale cancellation is refused", qa.field(stale.json(), "title") == "Stale Policy", covers=["okf:docs/features/policy/http/policy-desk-api.md#post-policy-cancel:errors:3"])
    qa.verify("http_status", stale, code=409, title="Stale Policy", path="/api/policies/pn-1001/cancel", covers=["okf:docs/features/policy/http/policy-desk-api.md#post-policy-cancel:errors:3"])
    response = qa.http.post("/api/policies/pn-1001/cancel", json_body={"version": before["version"], "confirm": before["policy_number"]}, expect_status=200)
    cancelled = response.json()["policy"]
    qa.check("cancellation answers 200 and bumps version", qa.field(cancelled, "version") == qa.field(before, "version") + 1, covers=["ac:5", "okf:docs/features/policy/http/policy-desk-api.md#post-policy-cancel:contract", "okf:docs/features/policy/http/policy-desk-api.md#post-policy-cancel:does:1"])
    qa.check("status is Cancelled", qa.field(cancelled, "status") == "Cancelled", covers=["ac:5", "okf:docs/features/policy/http/policy-desk-api.md#post-policy-cancel:does:1"])
    qa.verify("http_status", response, code=200, path="/api/policies/pn-1001/cancel", covers=["ac:5", "okf:docs/features/policy/http/policy-desk-api.md#post-policy-cancel:does:1"])
    qa.verify("json_path", response.json(), path="policy.status", equals="Cancelled", covers=["ac:5", "okf:docs/features/policy/http/policy-desk-api.md#post-policy-cancel:does:1"])
    qa.check("cancelled state persists on re-query", qa.field(qa.http.get("/api/policies/pn-1001").json(), "policy") == cancelled, covers=["ac:5"])
    register = qa.http.get("/api/policies", expect_status=200).json()["policies"]
    qa.check("the cancelled policy stays listed in the register with status Cancelled", any((qa.field(entry, "id") == "pn-1001" and qa.field(entry, "status") == "Cancelled" for entry in register)), covers=["okf:docs/features/policy/http/policy-desk-api.md#post-policy-cancel:does:2"])
    unknown = qa.http.post("/api/policies/missing/cancel", json_body={"version": 1, "confirm": "MISSING"}, expect_status=404)
    qa.check("unknown cancellation is identified", qa.field(unknown.json(), "title") == "Unknown Policy", covers=["okf:docs/features/policy/http/policy-desk-api.md#post-policy-cancel:errors:4"])
    json.dump({"before": before, "wrong": wrong.json(), "cancelled": cancelled}, qa.artifact("steps/cancellation.json", kind="json").open("w"))


@scenario(
    target=web,
    mechanism="live",
    covers=[
        "ac:6",
        "okf:docs/features/policy/flows/edit-policy.md:start:1",
        "okf:docs/features/policy/flows/edit-policy.md:end:1",
        "okf:docs/features/policy/flows/edit-policy.md:end-state",
        "okf:docs/features/policy/gui/screens/policy-list.md:contract",
        "okf:docs/features/policy/gui/screens/policy-list.md#open-policy:does:1",
        "okf:docs/features/policy/gui/screens/policy-detail.md:contract",
        "okf:docs/features/policy/gui/screens/policy-detail.md#edit-policy-link:contract",
        "okf:docs/features/policy/gui/screens/edit-policy.md:contract",
        "okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:contract",
        "okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:keyboard:1",
        "okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:name:1",
        "okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:role:1",
        "okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:states:1",
    ],
    preconditions=[
        "the register contains PN-1001 and the API is ready",
        "the form is opened before the intervening API amendment",
    ],
    checkpoints=[
        "the documented register-to-detail-to-edit navigation completes",
        "the edit form is filled from the stored record",
        "the intervening real API write makes the open form stale",
        "Save policy reports Stale Policy and does not navigate away",
        "the detail summary remains rendered and no browser diagnostics report errors",
    ],
    forbid=["deep-linking directly to the edit route", "reloading the form after the intervening write"],
)
def stale_edit_keeps_the_open_form_and_detail_reading(qa: Qa) -> None:
    """An open edit form reports a stale write instead of blanking or navigating away."""
    qa.goto("/policies")
    policy_link = qa.by_role("link", name="PN-1001")
    qa.eventually("the register lists the policy to open", policy_link.is_visible)
    policy_link.click()
    heading = qa.by_role("heading", name="Policy PN-1001")
    qa.eventually("following the register link reaches the policy's own screen", heading.is_visible)
    qa.verify("visible", heading, locator="heading:Policy PN-1001", covers=["okf:docs/features/policy/flows/edit-policy.md:start:1", "okf:docs/features/policy/flows/edit-policy.md:end:1", "okf:docs/features/policy/flows/edit-policy.md:end-state", "okf:docs/features/policy/gui/screens/policy-list.md:contract", "okf:docs/features/policy/gui/screens/policy-list.md#open-policy:does:1"])
    edit_link = qa.by_role("link", name="Edit policy")
    qa.eventually("the detail screen offers its edit entry", edit_link.is_visible)
    qa.vet("docs/features/policy/gui/screens/policy-detail.md", name="detail-before-edit", components=["policy-summary"])
    qa.check("detail exposes the documented edit entry", edit_link.count() == 1, covers=["okf:docs/features/policy/gui/screens/policy-detail.md:contract", "okf:docs/features/policy/gui/screens/policy-detail.md#edit-policy-link:contract"])
    edit_link.click()
    form = qa.by_css('form[aria-label="Edit policy"]')
    qa.eventually("the edit entry opens the edit form", form.is_visible)
    save = qa.by_role("button", name="Save policy")
    qa.eventually("the edit form offers its save control", save.is_visible)
    qa.vet("docs/features/policy/gui/screens/edit-policy.md", name="edit-form-before-stale-write", components=["edit-form"])
    current = qa.http.get("/api/policies/pn-1001").json()["policy"]
    qa.http.put("/api/policies/pn-1001", json_body=amendment_body(current, current["premium"] + 1), expect_status=200)
    with qa.page.expect_response("**/api/policies/pn-1001") as stale_submission:
        save.click()
    alert = qa.by_css('p[role="alert"]')
    qa.eventually("the stale write is answered with an alert", alert.is_visible)
    qa.vet("docs/features/policy/gui/screens/edit-policy.md", name="edit-form-stale-alert", components=["edit-form"])
    qa.check("stale alert is rendered", alert.count() == 1 and "Stale Policy" in alert.inner_text(), covers=["ac:6", "okf:docs/features/policy/gui/screens/edit-policy.md:contract"])
    qa.check("browser remains on the edit route", qa.page.url.endswith("/policies/pn-1001/edit"), covers=["ac:6", "okf:docs/features/policy/flows/edit-policy.md:start:1"])
    qa.goto("/policies/pn-1001")
    summary = qa.by_css("dl")
    qa.eventually("the detail screen draws the summary after the refused write", summary.is_visible)
    qa.eventually("the redrawn detail screen still offers its edit entry", edit_link.is_visible)
    qa.vet("docs/features/policy/gui/screens/policy-detail.md", name="detail-after-stale-write", components=["policy-summary"])
    qa.verify("conflict_on_stale", stale_submission.value.status, subject="policy pn-1001", token="version", covers=["okf:docs/features/policy/flows/edit-policy.md:start:1", "okf:docs/features/policy/flows/edit-policy.md:end:1", "okf:docs/features/policy/flows/edit-policy.md:end-state"])
    qa.verify("visible", summary, locator="text=Draft", covers=["okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:states:1"])
    qa.verify("visible", summary, locator="text=1HGCM82633A004352", covers=["okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:states:1"])
    qa.check("policy summary is rendered after the refused write", summary.count() == 1, covers=["okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:contract", "okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:keyboard:1", "okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:name:1", "okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:role:1", "okf:docs/features/policy/flows/edit-policy.md:end:1", "okf:docs/features/policy/flows/edit-policy.md:end-state"])
    unexpected = [entry for entry in qa.diagnostics.console_errors() if "409" not in entry.get("text", "")]
    qa.check("no console errors beyond the provoked 409 refusal", unexpected == [] and qa.diagnostics.page_errors() == [], covers=["okf:docs/features/policy/gui/screens/edit-policy.md:contract"])
    qa.screenshot("stale-edit-final")

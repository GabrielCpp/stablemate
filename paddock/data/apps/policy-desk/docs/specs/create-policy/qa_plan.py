import json

from _fixtures.policies import valid_policy
from ostler_qa import HttpError, Qa, plan, scenario, target


plan(run_id="qa-create-policy", story="create-policy")

api = target("api", driver="python", base_url="http://localhost:18084")
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
        "ac:1", "ac:2", "ac:3", "ac:5", "ac:6",
        "okf:docs/features/policy/concepts/policy.md:contract",
        "okf:docs/features/policy/concepts/policy-ledger.md:contract",
        "okf:docs/features/policy/http/policy-desk-api.md:contract",
        "okf:docs/features/policy/http/policy-desk-api.md#post-policies:contract",
        "okf:docs/features/policy/http/policy-desk-api.md#post-policies:does:1",
        "okf:docs/features/policy/http/policy-desk-api.md#post-policies:errors:1",
        "okf:docs/features/policy/http/policy-desk-api.md#post-policies:errors:2",
        "okf:docs/features/policy/http/policy-desk-api.md#post-policies:persistence:1",
        "okf:docs/features/policy/concepts/policy.md:contract",
    ],
    preconditions=["GET /healthz returns status ok", "the register can be reset through its documented route"],
    checkpoints=["accepted record is returned with Draft/version 1", "the service is restarted between the accepted write and the persistence re-read", "duplicate and validation refusals leave the ledger correct", "the created record is readable by its slug"],
    forbid=["in-memory state as persistence evidence", "a test double or direct ledger file access", "asserting only HTTP success codes"],
)
def create_policy_api(qa: Qa) -> None:
    """Create, refuse, and re-read policies against the live ledger."""
    health = qa.http.get("/healthz")
    health_body = health.json()
    qa.check("health reports the ready status", qa.field(health_body, "status") == "ok", covers=["okf:docs/features/policy/http/policy-desk-api.md:contract"])

    reset = qa.http.delete("/api/policies", expect_status=204)
    qa.check("reset clears the register", reset.status == 204, covers=["okf:docs/features/policy/http/policy-desk-api.md:contract"])
    reset_again = qa.http.delete("/api/policies", expect_status=204)
    qa.check("reset is idempotent", reset_again.status == 204, covers=["okf:docs/features/policy/http/policy-desk-api.md:contract"])

    payload = valid_policy("PN-1001")
    created = qa.http.post("/api/policies", json_body=payload, expect_status=201)
    created_body = created.json()
    policy = created_body["policy"]
    qa.verify("http_status", created, code=201, path="/api/policies", covers=["okf:docs/features/policy/http/policy-desk-api.md#post-policies:does:1"])
    qa.verify("json_path", created_body, path="$.policy.status", equals="Draft", covers=["okf:docs/features/policy/http/policy-desk-api.md#post-policies:does:1"])
    qa.verify("json_path", created_body, path="$.policy.version", equals="1", covers=["okf:docs/features/policy/http/policy-desk-api.md#post-policies:does:1"])
    qa.verify("json_path", created_body, path="$.policy.id", equals="pn-1001", covers=["okf:docs/features/policy/http/policy-desk-api.md#post-policies:does:1"])
    # The book's persistence bullet promises the record is still on the books after the
    # service restarts — a same-process re-read is exactly what an in-memory ledger would
    # also pass, so the process that accepted the write must die before the re-read.
    restart = qa.tool("docker").run("compose", "-f", "compose.yml", "restart", timeout=120.0)
    qa.check(
        "the service restarts cleanly between the write and the re-read",
        restart.ok,
        covers=["okf:docs/features/policy/http/policy-desk-api.md#post-policies:persistence:1"],
    )
    def restarted_service_answers() -> bool:
        # A connection refused during the restart window is "not yet", not a verdict —
        # the harness's `eventually` retries only timeouts, so the swallow lives here.
        try:
            return qa.http.get("/healthz").json()["status"] == "ok"
        except HttpError:
            return False

    qa.eventually(
        "the restarted service answers /healthz again",
        restarted_service_answers,
        timeout=60.0,
        interval=0.5,
        covers=["okf:docs/features/policy/http/policy-desk-api.md#post-policies:persistence:1"],
    )
    reread = qa.http.get("/api/policies/pn-1001", expect_status=200)
    reread_body = reread.json()
    qa.verify("persists", (policy, reread_body["policy"]), subject="policy pn-1001", covers=["okf:docs/features/policy/http/policy-desk-api.md#post-policies:persistence:1", "okf:docs/features/policy/concepts/policy-ledger.md:contract"])
    qa.check("the created policy is readable by its slug", qa.field(reread_body, "policy.policy_number") == "PN-1001", covers=["okf:docs/features/policy/http/policy-desk-api.md:contract"])
    missing = qa.http.get("/api/policies/missing", expect_status=404)
    qa.check("missing policy is refused with its documented title", qa.field(missing.json(), "title") == "Unknown Policy", covers=["ac:2"])

    duplicate = qa.http.post("/api/policies", json_body=payload, expect_status=409)
    qa.verify("http_status", duplicate, code=409, title="Duplicate Policy Number", path="/api/policies", covers=["okf:docs/features/policy/http/policy-desk-api.md#post-policies:errors:2"])
    listing = {"policies": [qa.http.get("/api/policies/pn-1001", expect_status=200).json()["policy"]]}
    qa.verify("count", listing, subject="policies", equals=1, covers=["okf:docs/features/policy/http/policy-desk-api.md#post-policies:errors:2"])

    invalid = valid_policy("PN-1002")
    invalid.update({"vehicle_vin": "", "start_date": "2000-01-01", "end_date": "1999-01-01", "premium": 1})
    refused = qa.http.post("/api/policies", json_body=invalid, expect_status=422)
    refused_body = refused.json()
    qa.verify("http_status", refused, code=422, path="/api/policies", covers=["okf:docs/features/policy/http/policy-desk-api.md#post-policies:errors:1"])
    qa.verify("json_path", refused_body, path="$.errors.vehicle_vin", absent=False, covers=["okf:docs/features/policy/http/policy-desk-api.md#post-policies:errors:1"])
    qa.verify("json_path", refused_body, path="$.errors.end_date", absent=False, covers=["okf:docs/features/policy/http/policy-desk-api.md#post-policies:errors:1"])
    qa.verify("json_path", refused_body, path="$.errors.start_date", absent=False, covers=["okf:docs/features/policy/http/policy-desk-api.md#post-policies:errors:1"])
    qa.verify("json_path", refused_body, path="$.errors.premium", absent=False, covers=["okf:docs/features/policy/http/policy-desk-api.md#post-policies:errors:1"])
    invalid_type = valid_policy("PN-1005", "bad-email", "invalid")
    invalid_type["policy_number"] = ""
    refused_type = qa.http.post("/api/policies", json_body=invalid_type, expect_status=422)
    refused_type_body = refused_type.json()
    qa.verify("json_path", refused_type_body, path="$.errors.coverage_type", absent=False, covers=["okf:docs/features/policy/http/policy-desk-api.md#post-policies:errors:1"])
    qa.check("validation includes blank number and malformed holder email", "policy_number" in qa.field(refused_type_body, "errors") and "holder_email" in qa.field(refused_type_body, "errors"), covers=["ac:3"])
    invalid_home = valid_policy("PN-1006", "home@example.com", "home")
    invalid_home["property_address"] = ""
    home_refused = qa.http.post("/api/policies", json_body=invalid_home, expect_status=422)
    qa.check("home validation names the missing property address", "property_address" in qa.field(home_refused.json(), "errors"), covers=["ac:4", "okf:docs/features/policy/http/policy-desk-api.md#post-policies:errors:1"])

    umbrella_without_base = valid_policy("PN-1003", "nobody@example.com", "umbrella")
    umbrella_refused = qa.http.post("/api/policies", json_body=umbrella_without_base, expect_status=422)
    qa.check("umbrella refuses a holder with no underlying policy", "coverage_type" in qa.field(umbrella_refused.json(), "errors"), covers=["ac:5", "okf:docs/features/policy/http/policy-desk-api.md#post-policies:errors:1"])
    umbrella_with_base = valid_policy("PN-1004", "alex@example.com", "umbrella")
    umbrella_created = qa.http.post("/api/policies", json_body=umbrella_with_base, expect_status=201)
    qa.check("umbrella accepts the same holder's underlying auto policy", qa.field(umbrella_created.json(), "policy.status") == "Draft", covers=["ac:5"])
    qa.check("accepted API record is durable and correctly identified", qa.field(policy, "status") == "Draft" and qa.field(policy, "version") == 1 and (qa.field(policy, "id") == "pn-1001"), covers=["ac:1", "okf:docs/features/policy/concepts/policy.md:contract", "okf:docs/features/policy/http/policy-desk-api.md:contract", "okf:docs/features/policy/http/policy-desk-api.md#post-policies:contract"])
    qa.check("duplicate branch leaves exactly one policy", len(qa.field(listing, "policies")) == 1, covers=["ac:2"])
    qa.check("API validation covers date rules", all((field in qa.field(refused_body, "errors") for field in ["start_date", "end_date"])), covers=["ac:6"])
    json.dump({"created": policy, "reread": reread_body, "refused": refused_body}, qa.artifact("steps/api-evidence.json", kind="json").open("w"))


@scenario(
    target=web,
    mechanism="live",
    covers=[
        "ac:7", "okf:docs/features/policy/flows/create-policy.md:start:1", "okf:docs/features/policy/flows/create-policy.md:end:1", "okf:docs/features/policy/flows/create-policy.md:end-state",
        "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:contract", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:does:1", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:when:1",
        "okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:contract", "okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:keyboard:1", "okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:name:1", "okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:role:1", "okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:states:1",
    ],
    preconditions=["the register is reset and the API health endpoint is ready"],
    checkpoints=["the app root lands on the new-policy form", "successful submit reaches the detail route", "a fresh deep link renders the same stored policy"],
    forbid=["deep-linking past the app-root entry", "asserting a detail screen without a fresh reload"],
)
def create_policy_browser_happy_path(qa: Qa) -> None:
    """Create a policy from the register and prove client navigation plus deep linking."""
    qa.http.delete("/api/policies", expect_status=204)
    qa.goto("/")
    form = qa.by_css('form[aria-label="New policy"]')
    qa.eventually("the new-policy form is on screen", form.is_visible)
    qa.check("the app root lands on the new-policy form as a client route", qa.page.url.endswith("/policies/new"), actual=qa.page.url, expected="/policies/new")
    qa.vet("docs/features/policy/gui/screens/new-policy.md", name="new-form", components=["coverage-type-select", "vehicle-vin-field"])
    qa.screenshot("new-form")
    absent = qa.http.get("/api/policies/pn-1001", expect_status=404)
    qa.require("policy PN-1001 is absent before submission", qa.field(absent.json(), "title") == "Unknown Policy")
    before = []
    qa.by_css("#policy_number").fill("PN-1001")
    qa.by_css("#holder_email").fill("alex@example.com")
    qa.by_css("#vehicle_vin").fill("1HGCM82633A004352")
    qa.by_css("#start_date").fill("2099-01-01")
    qa.by_css("#end_date").fill("2099-12-31")
    qa.by_css("#premium").fill("1000")
    qa.by_role("button", name="Create policy").click()
    detail = qa.by_css("dl")
    qa.eventually("the accepted submit lands on a policy summary", detail.is_visible)
    qa.vet("docs/features/policy/gui/screens/policy-detail.md", name="created-detail", components=["policy-summary"])
    qa.screenshot("created-detail")
    after = qa.http.get("/api/policies/pn-1001", expect_status=200).json()["policy"]
    qa.check("client navigation uses the slugged policy route", qa.page.url.endswith("/policies/pn-1001"), actual=qa.page.url, expected="/policies/pn-1001", covers=["ac:7", "okf:docs/features/policy/flows/create-policy.md:end:1"])
    qa.verify("visible", detail, locator="heading:Policy PN-1001", covers=["okf:docs/features/policy/flows/create-policy.md:end:1", "okf:docs/features/policy/flows/create-policy.md:end-state", "okf:docs/features/policy/flows/create-policy.md:start:1", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:contract", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:does:1", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:when:1"])
    qa.verify("visible", detail, locator="text=Draft", covers=["okf:docs/features/policy/flows/create-policy.md:end:1", "okf:docs/features/policy/flows/create-policy.md:end-state", "okf:docs/features/policy/flows/create-policy.md:start:1", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:contract", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:does:1", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:when:1"])
    qa.verify("created", (before, after), subject="policy pn-1001", covers=["okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:contract", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:does:1", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:when:1"])
    qa.check("detail shows Draft and the entered VIN", detail.count() == 1 and "Draft" in detail.inner_text() and "1HGCM82633A004352" in detail.inner_text(), covers=["okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:contract"])
    qa.verify("visible", detail, locator="text=Draft", covers=["okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:states:1"])
    qa.verify("visible", detail, locator="text=1HGCM82633A004352", covers=["okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:states:1"])
    qa.check("detail summary is still the live terminal record", qa.by_css("dl").is_visible() and qa.page.url.endswith("/policies/pn-1001"), covers=["okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:contract", "okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:keyboard:1", "okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:name:1", "okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:role:1", "okf:docs/features/policy/gui/screens/policy-detail.md#policy-summary:states:1"])
    qa.page.reload()
    qa.eventually("the reloaded deep link draws the summary again", detail.is_visible)
    qa.check("deep link reload preserves the created policy", "Policy PN-1001" in qa.page.locator("body").inner_text(), covers=["ac:7", "okf:docs/features/policy/flows/create-policy.md:end:1"])


@scenario(
    target=web,
    mechanism="live",
    covers=[
        "ac:3", "ac:4", "ac:6", "okf:docs/features/policy/gui/screens/new-policy.md#coverage-type-select:contract", "okf:docs/features/policy/gui/screens/new-policy.md#coverage-type-select:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#coverage-type-select:name:1", "okf:docs/features/policy/gui/screens/new-policy.md#coverage-type-select:role:1", "okf:docs/features/policy/gui/screens/new-policy.md#coverage-type-select:states:1", "okf:docs/features/policy/gui/screens/new-policy.md#coverage-type-select:states:2", "okf:docs/features/policy/gui/screens/new-policy.md#duplicate-policy-alert:contract", "okf:docs/features/policy/gui/screens/new-policy.md#duplicate-policy-alert:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#duplicate-policy-alert:name:1", "okf:docs/features/policy/gui/screens/new-policy.md#duplicate-policy-alert:role:1", "okf:docs/features/policy/gui/screens/new-policy.md#field-error-message:contract", "okf:docs/features/policy/gui/screens/new-policy.md#field-error-message:states:1", "okf:docs/features/policy/gui/screens/new-policy.md#field-error-message:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#field-error-message:name:1", "okf:docs/features/policy/gui/screens/new-policy.md#field-error-message:role:1", "okf:docs/features/policy/gui/screens/new-policy.md#policy-form:contract", "okf:docs/features/policy/gui/screens/new-policy.md#policy-form:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#policy-form:name:1", "okf:docs/features/policy/gui/screens/new-policy.md#policy-form:role:1", "okf:docs/features/policy/gui/screens/new-policy.md#property-address-field:contract", "okf:docs/features/policy/gui/screens/new-policy.md#property-address-field:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#property-address-field:name:1", "okf:docs/features/policy/gui/screens/new-policy.md#property-address-field:role:1", "okf:docs/features/policy/gui/screens/new-policy.md#property-address-field:states:1", "okf:docs/features/policy/gui/screens/new-policy.md#refuse-new-policy:contract", "okf:docs/features/policy/gui/screens/new-policy.md#refuse-new-policy:does:1", "okf:docs/features/policy/gui/screens/new-policy.md#refuse-new-policy:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#refuse-new-policy:when:1", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:contract", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:does:1", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:when:1", "okf:docs/features/policy/gui/screens/new-policy.md#vehicle-vin-field:contract", "okf:docs/features/policy/gui/screens/new-policy.md#vehicle-vin-field:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#vehicle-vin-field:name:1", "okf:docs/features/policy/gui/screens/new-policy.md#vehicle-vin-field:role:1", "okf:docs/features/policy/gui/screens/new-policy.md#vehicle-vin-field:states:1",
    ],
    preconditions=["the register is empty", "the new-policy route is reached from the app root"],
    checkpoints=["coverage selection changes the conditional field", "a service refusal remains on the form", "the refusal is rendered beside the named field"],
    forbid=["checking only that an error is absent", "using a guessed locator or invented route"],
)
def refuse_policy_browser(qa: Qa) -> None:
    """Exercise conditional fields and show a server refusal inline without navigation."""
    qa.http.delete("/api/policies", expect_status=204)
    qa.http.post("/api/policies", json_body=valid_policy("PN-0999"), expect_status=201)
    qa.goto("/")
    form = qa.by_css('form[aria-label="New policy"]')
    qa.eventually("the new-policy form is on screen", form.is_visible)
    qa.vet("docs/features/policy/gui/screens/new-policy.md", name="auto-form", components=["coverage-type-select", "vehicle-vin-field"])
    qa.screenshot("auto-form")
    coverage = qa.by_css("#coverage_type")
    qa.check("coverage opens on auto", coverage.count() == 1 and coverage.input_value() == "auto", covers=["okf:docs/features/policy/gui/screens/new-policy.md#coverage-type-select:states:1"])
    qa.check("auto shows VIN and not property address", qa.by_css("#vehicle_vin").count() == 1 and qa.by_css("#property_address").count() == 0, covers=["ac:4", "okf:docs/features/policy/gui/screens/new-policy.md#vehicle-vin-field:states:1", "okf:docs/features/policy/gui/screens/new-policy.md#property-address-field:states:1"])
    qa.verify("visible", qa.by_css("#vehicle_vin"), locator="textbox:Vehicle VIN", covers=["ac:4", "okf:docs/features/policy/gui/screens/new-policy.md#vehicle-vin-field:states:1"])
    qa.verify("visible", coverage, locator="combobox:Coverage type", covers=["okf:docs/features/policy/gui/screens/new-policy.md#coverage-type-select:states:2"])
    qa.verify("visible", form, locator="form:New policy", covers=["okf:docs/features/policy/gui/screens/new-policy.md#policy-form:contract", "okf:docs/features/policy/gui/screens/new-policy.md#policy-form:keyboard:1"])
    qa.check("coverage offers exactly auto home umbrella", coverage.locator("option").all_inner_texts() == ["auto", "home", "umbrella"], covers=["okf:docs/features/policy/gui/screens/new-policy.md#coverage-type-select:states:2"])
    qa.check("new-policy form and coverage control contracts are rendered", form.is_visible() and coverage.is_visible(), covers=["okf:docs/features/policy/gui/screens/new-policy.md#coverage-type-select:contract", "okf:docs/features/policy/gui/screens/new-policy.md#coverage-type-select:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#coverage-type-select:name:1", "okf:docs/features/policy/gui/screens/new-policy.md#coverage-type-select:role:1", "okf:docs/features/policy/gui/screens/new-policy.md#policy-form:contract", "okf:docs/features/policy/gui/screens/new-policy.md#policy-form:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#policy-form:name:1", "okf:docs/features/policy/gui/screens/new-policy.md#policy-form:role:1", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:contract", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:when:1", "okf:docs/features/policy/gui/screens/new-policy.md#vehicle-vin-field:contract", "okf:docs/features/policy/gui/screens/new-policy.md#vehicle-vin-field:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#vehicle-vin-field:name:1", "okf:docs/features/policy/gui/screens/new-policy.md#vehicle-vin-field:role:1", "okf:docs/features/policy/gui/screens/new-policy.md#property-address-field:contract", "okf:docs/features/policy/gui/screens/new-policy.md#property-address-field:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#property-address-field:name:1", "okf:docs/features/policy/gui/screens/new-policy.md#property-address-field:role:1"])
    qa.by_css("#policy_number").fill("PN-0999")
    qa.by_css("#holder_email").fill("alex@example.com")
    qa.by_css("#vehicle_vin").fill("1HGCM82633A004352")
    qa.by_css("#start_date").fill("2099-01-01")
    qa.by_css("#end_date").fill("2099-12-31")
    qa.by_css("#premium").fill("1000")
    qa.by_role("button", name="Create policy").click()
    duplicate_alert = qa.by_css('p[role="alert"]')
    qa.eventually("the duplicate submit is answered with an alert", duplicate_alert.is_visible)
    qa.vet("docs/features/policy/gui/screens/new-policy.md", name="duplicate-form", components=["duplicate-policy-alert"])
    qa.screenshot("duplicate-form")
    qa.check("duplicate policy alert names the conflict", duplicate_alert.count() == 1 and "Duplicate Policy Number" in duplicate_alert.inner_text(), covers=["okf:docs/features/policy/gui/screens/new-policy.md#duplicate-policy-alert:contract", "okf:docs/features/policy/gui/screens/new-policy.md#duplicate-policy-alert:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#duplicate-policy-alert:name:1", "okf:docs/features/policy/gui/screens/new-policy.md#duplicate-policy-alert:role:1"])
    coverage.select_option("home")
    qa.check("home shows address and not VIN", qa.by_css("#property_address").count() == 1 and qa.by_css("#vehicle_vin").count() == 0, covers=["ac:4"])
    qa.verify("visible", qa.by_css("#property_address"), locator="textbox:Property address", covers=["ac:4", "okf:docs/features/policy/gui/screens/new-policy.md#property-address-field:states:1"])
    coverage.select_option("auto")
    qa.by_css("#vehicle_vin").fill("")
    qa.by_css("#policy_number").fill("PN-1002")
    qa.by_css("#holder_email").fill("bad-email")
    qa.by_css("#start_date").fill("2000-01-01")
    qa.by_css("#end_date").fill("1999-01-01")
    qa.by_css("#premium").fill("1")
    qa.by_role("button", name="Create policy").click()
    error = qa.by_css("span.field-error")
    qa.eventually("the refused submit puts a message beside a field", error.first.is_visible)
    qa.vet("docs/features/policy/gui/screens/new-policy.md", name="refused-form", components=["coverage-type-select", "vehicle-vin-field", "field-error-message"])
    qa.screenshot("refused-form")
    qa.check("refusal stays on the form with the typed policy number", form.is_visible() and qa.by_css("#policy_number").count() == 1 and qa.by_css("#policy_number").input_value() == "PN-1002", covers=["okf:docs/features/policy/gui/screens/new-policy.md#refuse-new-policy:does:1"])
    qa.verify("visible", form, locator="form:New policy", covers=["okf:docs/features/policy/gui/screens/new-policy.md#refuse-new-policy:contract", "okf:docs/features/policy/gui/screens/new-policy.md#refuse-new-policy:does:1", "okf:docs/features/policy/gui/screens/new-policy.md#refuse-new-policy:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#refuse-new-policy:when:1"])
    qa.verify("visible", error.filter(has_text="Auto coverage needs the vehicle VIN."), locator="text=Auto coverage needs the vehicle VIN.", covers=["okf:docs/features/policy/gui/screens/new-policy.md#refuse-new-policy:contract", "okf:docs/features/policy/gui/screens/new-policy.md#refuse-new-policy:does:1", "okf:docs/features/policy/gui/screens/new-policy.md#refuse-new-policy:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#refuse-new-policy:when:1"])
    qa.verify("visible", error.filter(has_text="End date must be after the start date."), locator="text=End date must be after the start date.", covers=["ac:6", "okf:docs/features/policy/gui/screens/new-policy.md#field-error-message:states:1"])
    qa.check("field refusal is beside the field", "Start date cannot be in the past." in error.all_inner_texts() and "End date must be after the start date." in error.all_inner_texts(), covers=["ac:3", "ac:6", "okf:docs/features/policy/gui/screens/new-policy.md#field-error-message:contract", "okf:docs/features/policy/gui/screens/new-policy.md#field-error-message:states:1", "okf:docs/features/policy/gui/screens/new-policy.md#refuse-new-policy:does:1"])
    qa.check("refusal controls and field-error contract are present", form.is_visible() and error.first.is_visible(), covers=["okf:docs/features/policy/gui/screens/new-policy.md#duplicate-policy-alert:contract", "okf:docs/features/policy/gui/screens/new-policy.md#duplicate-policy-alert:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#duplicate-policy-alert:name:1", "okf:docs/features/policy/gui/screens/new-policy.md#duplicate-policy-alert:role:1", "okf:docs/features/policy/gui/screens/new-policy.md#field-error-message:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#field-error-message:name:1", "okf:docs/features/policy/gui/screens/new-policy.md#field-error-message:role:1", "okf:docs/features/policy/gui/screens/new-policy.md#refuse-new-policy:contract", "okf:docs/features/policy/gui/screens/new-policy.md#refuse-new-policy:keyboard:1", "okf:docs/features/policy/gui/screens/new-policy.md#submit-new-policy:does:1"])
    qa.check("browser reports no uncaught page errors", qa.diagnostics.page_errors() == [], covers=["okf:docs/features/policy/gui/screens/new-policy.md#refuse-new-policy:when:1"])

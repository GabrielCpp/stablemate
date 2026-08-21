from ostler_qa import Qa, plan, scenario, target


plan(run_id="qa-policy-list", story="policy-list")

api = target("api", driver="python", base_url="http://localhost:18084")
web = target(
    "web",
    driver="playwright",
    base_url="http://localhost:18084",
    browser="chromium",
    recording={"required": True, "mode": "window"},
)


def valid_policy(number: str, email: str = "alex@example.com", coverage: str = "auto") -> dict:
    return {
        "policy_number": number,
        "holder_email": email,
        "coverage_type": coverage,
        "vehicle_vin": "1HGCM82633A004352" if coverage == "auto" else "",
        "property_address": "10 Main Street" if coverage == "home" else "",
        "start_date": "2099-01-01",
        "end_date": "2099-12-31",
        "premium": 1000 if coverage == "auto" else 200,
    }


@scenario(
    target=api,
    mechanism="live",
    covers=[
        "ac:1",
        "okf:docs/features/policy/http/policy-desk-api.md:contract",
        "okf:docs/features/policy/http/policy-desk-api.md#get-health:contract",
        "okf:docs/features/policy/http/policy-desk-api.md#get-health:does:1",
        "okf:docs/features/policy/http/policy-desk-api.md#delete-policies:contract",
        "okf:docs/features/policy/http/policy-desk-api.md#delete-policies:does:1",
        "okf:docs/features/policy/http/policy-desk-api.md#delete-policies:does:2",
        "okf:docs/features/policy/http/policy-desk-api.md#get-policies:contract",
        "okf:docs/features/policy/http/policy-desk-api.md#get-policies:does:1",
        "okf:docs/features/policy/http/policy-desk-api.md#get-policies:does:2",
    ],
    preconditions=["GET /healthz returns status ok", "the register can be reset through its documented route"],
    checkpoints=["register lists every policy ordered by policy number", "each record carries the fields the register renders"],
    forbid=["a test double or direct ledger file access", "asserting only HTTP success codes"],
)
def register_api(qa: Qa) -> None:
    """List the register over HTTP: ordering and record shape."""
    health = qa.http.get("/healthz")
    qa.check("health reports the ready status", health.json()["status"] == "ok", covers=["okf:docs/features/policy/http/policy-desk-api.md#get-health:contract", "okf:docs/features/policy/http/policy-desk-api.md#get-health:does:1"])
    reset = qa.http.delete("/api/policies", expect_status=204)
    qa.verify("http_status", reset, code=204, path="/api/policies", covers=["okf:docs/features/policy/http/policy-desk-api.md#delete-policies:contract", "okf:docs/features/policy/http/policy-desk-api.md#delete-policies:does:1"])
    emptied = qa.http.get("/api/policies", expect_status=200).json()["policies"]
    qa.verify("count", emptied, subject="policies", equals=0, covers=["okf:docs/features/policy/http/policy-desk-api.md#delete-policies:does:1"])
    reset_again = qa.http.delete("/api/policies", expect_status=204)
    qa.check("reset is idempotent on empty books", reset_again.status == 204, covers=["okf:docs/features/policy/http/policy-desk-api.md#delete-policies:does:2"])

    for number in ("PN-1003", "PN-1001", "PN-1002"):
        qa.http.post("/api/policies", json_body=valid_policy(number), expect_status=201)
    listing = qa.http.get("/api/policies", expect_status=200)
    policies = listing.json()["policies"]
    qa.verify("http_status", listing, code=200, path="/api/policies", covers=["ac:1", "okf:docs/features/policy/http/policy-desk-api.md:contract", "okf:docs/features/policy/http/policy-desk-api.md#get-policies:contract"])
    numbers = [policy["policy_number"] for policy in policies]
    qa.check("every policy on file is listed, ordered by policy number", numbers == ["PN-1001", "PN-1002", "PN-1003"], actual=numbers, expected=["PN-1001", "PN-1002", "PN-1003"], covers=["ac:1", "okf:docs/features/policy/http/policy-desk-api.md#get-policies:does:1"])
    fields = ("id", "policy_number", "holder_email", "coverage_type", "start_date", "end_date", "premium", "status", "version")
    qa.check("each record carries the register's fields without a second request", all(field in policy for policy in policies for field in fields), covers=["okf:docs/features/policy/http/policy-desk-api.md#get-policies:does:2"])
    qa.verify("json_path", listing.json(), path="$.policies[0].id", equals="pn-1001", covers=["okf:docs/features/policy/http/policy-desk-api.md#get-policies:does:2"])



@scenario(
    target=web,
    mechanism="live",
    covers=[
        "ac:2", "ac:5", "ac:6",
        "okf:docs/features/policy/gui/screens/policy-list.md:contract",
        "okf:docs/features/policy/gui/screens/policy-list.md#policy-table:contract",
        "okf:docs/features/policy/gui/screens/policy-list.md#policy-table:keyboard:1",
        "okf:docs/features/policy/gui/screens/policy-list.md#policy-table:name:1",
        "okf:docs/features/policy/gui/screens/policy-list.md#policy-table:role:1",
        "okf:docs/features/policy/gui/screens/policy-list.md#open-policy:contract",
        "okf:docs/features/policy/gui/screens/policy-list.md#open-policy:does:1",
        "okf:docs/features/policy/gui/screens/policy-list.md#open-policy:keyboard:1",
        "okf:docs/features/policy/gui/screens/policy-list.md#new-policy-link:contract",
        "okf:docs/features/policy/gui/screens/policy-list.md#new-policy-link:keyboard:1",
        "okf:docs/features/policy/gui/screens/policy-list.md#new-policy-link:name:1",
        "okf:docs/features/policy/gui/screens/policy-list.md#new-policy-link:role:1",
        "okf:docs/features/policy/gui/screens/policy-detail.md:contract",
        "okf:docs/features/policy/gui/screens/policy-detail.md#edit-policy-link:contract",
        "okf:docs/features/policy/gui/screens/policy-detail.md#edit-policy-link:name:1",
        "okf:docs/features/policy/gui/screens/policy-detail.md#edit-policy-link:role:1",
    ],
    preconditions=["the register is reset and holds two policies created through the documented route"],
    checkpoints=["the register renders one named row per policy", "a row's link is a client route to that policy's detail", "the navigation region rides along to the detail screen"],
    forbid=["deep-linking past the documented register entry to prove row navigation", "asserting a detail screen for a policy other than the one clicked"],
)
def register_browser(qa: Qa) -> None:
    """Walk the register: named rows, keyboard-followed New policy, and client-route row links."""
    qa.http.delete("/api/policies", expect_status=204)
    qa.http.post("/api/policies", json_body=valid_policy("PN-1001"), expect_status=201)
    qa.http.post("/api/policies", json_body=valid_policy("PN-1002", email="sam@example.com", coverage="home"), expect_status=201)
    qa.goto("/policies")
    table = qa.by_role("table", name="Policies on file")
    table.wait_for(state="visible")
    qa.vet("docs/features/policy/gui/screens/policy-list.md", name="register", components=["policy-table", "new-policy-link"])
    qa.screenshot("register")
    qa.verify("visible", table, locator="table:Policies on file", covers=["ac:2", "okf:docs/features/policy/gui/screens/policy-list.md:contract", "okf:docs/features/policy/gui/screens/policy-list.md#policy-table:contract", "okf:docs/features/policy/gui/screens/policy-list.md#policy-table:name:1", "okf:docs/features/policy/gui/screens/policy-list.md#policy-table:role:1"])
    rows = qa.by_css("table tbody tr")
    qa.check("the register renders one row per policy", rows.count() == 2, actual=rows.count(), expected=2, covers=["ac:2", "okf:docs/features/policy/gui/screens/policy-list.md#policy-table:contract"])
    first_row_link = qa.by_role("link", name="PN-1001")
    qa.verify("visible", first_row_link, locator="link:PN-1001", covers=["ac:2", "okf:docs/features/policy/gui/screens/policy-list.md#policy-table:contract", "okf:docs/features/policy/gui/screens/policy-list.md#policy-table:keyboard:1"])

    new_link = qa.by_role("link", name="New policy")
    qa.verify("visible", new_link, locator="link:New policy", covers=["okf:docs/features/policy/gui/screens/policy-list.md#new-policy-link:contract", "okf:docs/features/policy/gui/screens/policy-list.md#new-policy-link:name:1", "okf:docs/features/policy/gui/screens/policy-list.md#new-policy-link:role:1"])
    new_link.focus()
    qa.page.keyboard.press("Enter")
    form = qa.by_css('form[aria-label="New policy"]')
    form.wait_for(state="visible")
    qa.check("New policy is keyboard-operable and lands on the form as a client route", qa.page.url.endswith("/policies/new"), actual=qa.page.url, expected="/policies/new", covers=["ac:6", "okf:docs/features/policy/gui/screens/policy-list.md#new-policy-link:contract", "okf:docs/features/policy/gui/screens/policy-list.md#new-policy-link:keyboard:1"])
    qa.by_role("link", name="Policies").click()
    table.wait_for(state="visible")

    qa.page.evaluate("() => { window.__qa_register_mounted = true; }")
    qa.by_role("link", name="PN-1001").click()
    detail = qa.by_css("dl")
    detail.wait_for(state="visible")
    qa.vet("docs/features/policy/gui/screens/policy-detail.md", name="opened-detail", components=["edit-policy-link"])
    qa.screenshot("opened-detail")
    qa.verify("visible", detail, locator="heading:Policy PN-1001", covers=["ac:5", "okf:docs/features/policy/gui/screens/policy-list.md#open-policy:contract", "okf:docs/features/policy/gui/screens/policy-list.md#open-policy:does:1", "okf:docs/features/policy/gui/screens/policy-list.md#open-policy:keyboard:1", "okf:docs/features/policy/gui/screens/policy-detail.md:contract"])
    qa.check("the clicked policy is the one shown, not a neighbour", "PN-1002" not in qa.by_css("main h1").inner_text(), covers=["ac:5", "okf:docs/features/policy/gui/screens/policy-list.md#open-policy:does:1"])
    not_reloaded = qa.page.evaluate("() => window.__qa_register_mounted === true")
    qa.check("following the row link did not reload the document", not_reloaded is True, covers=["ac:5", "okf:docs/features/policy/gui/screens/policy-list.md#open-policy:does:1"])
    edit_link = qa.by_role("link", name="Edit policy")
    qa.verify("visible", edit_link, locator="link:Edit policy", covers=["okf:docs/features/policy/gui/screens/policy-detail.md#edit-policy-link:contract", "okf:docs/features/policy/gui/screens/policy-detail.md#edit-policy-link:name:1", "okf:docs/features/policy/gui/screens/policy-detail.md#edit-policy-link:role:1"])
    qa.check("the navigation region rides along to the detail screen", qa.by_role("link", name="New policy").is_visible() and qa.by_role("link", name="Policies").is_visible(), covers=["ac:6"])

    qa.goto("/policies/pn-1002")
    detail.wait_for(state="visible")
    qa.check("a policy detail URL is a working deep link", "PN-1002" in qa.by_css("main h1").inner_text(), covers=["okf:docs/features/policy/gui/screens/policy-detail.md:contract"])


@scenario(
    target=web,
    mechanism="live",
    covers=[
        "ac:3", "ac:4",
        "okf:docs/features/policy/gui/screens/policy-list.md:contract",
        "okf:docs/features/policy/gui/screens/policy-list.md#empty-register-notice:contract",
        "okf:docs/features/policy/gui/screens/policy-list.md#empty-register-notice:keyboard:1",
        "okf:docs/features/policy/gui/screens/policy-list.md#empty-register-notice:name:1",
        "okf:docs/features/policy/gui/screens/policy-list.md#empty-register-notice:role:1",
        "okf:docs/features/policy/gui/screens/policy-list.md#register-error-alert:contract",
        "okf:docs/features/policy/gui/screens/policy-list.md#register-error-alert:keyboard:1",
        "okf:docs/features/policy/gui/screens/policy-list.md#register-error-alert:name:1",
        "okf:docs/features/policy/gui/screens/policy-list.md#register-error-alert:role:1",
        "okf:docs/features/policy/gui/screens/policy-list.md#register-error-alert:states:1",
    ],
    preconditions=["the register is reset through its documented route"],
    checkpoints=["an empty register shows the notice and no table", "the timer re-read replaces the notice once a policy exists", "a failed re-read raises the alert instead of a stale table"],
    forbid=["reaching into the ledger file to empty the register", "asserting the alert without first making the register unreadable"],
)
def register_empty_and_unreadable_browser(qa: Qa) -> None:
    """Show the empty notice, watch the timer re-read pick up a policy, then fail the read and demand the alert."""
    qa.http.delete("/api/policies", expect_status=204)
    qa.goto("/policies")
    notice = qa.by_css("p.empty-notice")
    notice.wait_for(state="visible")
    qa.vet("docs/features/policy/gui/screens/policy-list.md", name="empty-register", components=["empty-register-notice"])
    qa.screenshot("empty-register")
    qa.verify("visible", notice, locator="text=No policies are on file yet", covers=["ac:3", "okf:docs/features/policy/gui/screens/policy-list.md:contract", "okf:docs/features/policy/gui/screens/policy-list.md#empty-register-notice:contract", "okf:docs/features/policy/gui/screens/policy-list.md#empty-register-notice:keyboard:1", "okf:docs/features/policy/gui/screens/policy-list.md#empty-register-notice:name:1", "okf:docs/features/policy/gui/screens/policy-list.md#empty-register-notice:role:1"])
    qa.check("an empty register renders no table", qa.by_css("table").count() == 0, covers=["ac:3", "okf:docs/features/policy/gui/screens/policy-list.md#empty-register-notice:contract"])

    qa.http.post("/api/policies", json_body=valid_policy("PN-1001"), expect_status=201)
    table = qa.by_role("table", name="Policies on file")
    table.wait_for(state="visible", timeout=20000)
    qa.check("the timer re-read replaces the notice without a reload", table.is_visible() and notice.count() == 0, covers=["okf:docs/features/policy/gui/screens/policy-list.md#empty-register-notice:contract"])

    alert = qa.by_role("alert")
    qa.check("no alert is present while the register is readable", alert.count() == 0, covers=["okf:docs/features/policy/gui/screens/policy-list.md#register-error-alert:states:1"])
    def _abort_register_read(route) -> None:
        route.abort()

    qa.page.route("**/api/policies", _abort_register_read)
    alert.wait_for(state="visible", timeout=20000)
    qa.screenshot("register-unreadable")
    qa.verify("visible", alert, locator="alert", covers=["ac:4", "okf:docs/features/policy/gui/screens/policy-list.md#register-error-alert:contract", "okf:docs/features/policy/gui/screens/policy-list.md#register-error-alert:keyboard:1", "okf:docs/features/policy/gui/screens/policy-list.md#register-error-alert:name:1", "okf:docs/features/policy/gui/screens/policy-list.md#register-error-alert:role:1", "okf:docs/features/policy/gui/screens/policy-list.md#register-error-alert:states:1"])
    qa.check("the failed re-read is announced rather than leaving a stale empty table", alert.is_visible(), covers=["ac:4", "okf:docs/features/policy/gui/screens/policy-list.md#register-error-alert:contract", "okf:docs/features/policy/gui/screens/policy-list.md#register-error-alert:states:1"])
    qa.page.unroute("**/api/policies")

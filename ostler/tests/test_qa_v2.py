from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import types
from pathlib import Path

import yaml

from ostler.artifact.kinds import _qa_evidence_vet
from ostler.qa.plan import load_plan, validate_v2
from ostler.qa.run import cmd_run, cmd_validate
from ostler.qa.drivers import PlaywrightDriver, SharedPlaywright, _compile_maestro
from ostler.qa.session import QaSession, _kill_pid


def _context(spec: Path) -> str:
    obligation = "okf:docs/features/demo/item.md:contract"
    (spec / "qa-okf-context.json").write_text(
        json.dumps(
            {
                "version": 1,
                "available": True,
                "base": "base",
                "head": "head",
                "changedCode": [],
                "directNodes": [],
                "contracts": [],
                "journeys": [],
                "journeyNodes": [],
                "verificationRefs": [],
                "healthFindings": [],
                "acceptanceCriteria": [],
                "obligations": [
                    {
                        "id": obligation,
                        "kind": "contract",
                        "node": "item",
                        "source": "docs/features/demo/item.md",
                        "requirement": "item is emitted",
                        "evidenceRequired": "live",
                        "reasons": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return obligation


def _plan(spec: Path, obligation: str) -> Path:
    plan = {
        "version": 2,
        "run_id": "qa-run-1",
        "story": "story-1",
        "targets": {"api": {"driver": "command"}},
        "scenarios": [
            {
                "id": "api-contract",
                "target": "api",
                "mechanism": "live",
                "covers": [obligation],
                "actions": [
                    {
                        "do": "command",
                        "id": "emit",
                        "cmd": "printf '{\"value\":\"ok\"}'",
                        "assert_contains": "ok",
                        "out": "qa/steps/emit.json",
                    }
                ],
            }
        ],
    }
    path = spec / "qa-plan.yml"
    path.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
    return path


def test_v2_command_run_owns_log_manifest_and_evidence(tmp_path: Path):
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    stale = spec / "qa/stale.txt"
    stale.parent.mkdir()
    stale.write_text("old", encoding="utf-8")

    outcome = cmd_run(plan, root=tmp_path)

    assert outcome.status == "passed"
    assert not stale.exists()
    records = [
        json.loads(line)
        for line in (spec / "qa/qa-run.ndjson").read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["kind"] == "session_start"
    assert records[-1]["kind"] == "session_stop"
    assert records[-1]["status"] == "passed"
    assert any(
        row.get("kind") == "assert"
        and obligation in row.get("covers", [])
        and row.get("result") == "PASS"
        for row in records
    )
    manifest = json.loads((spec / "qa/run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["runId"] == "qa-run-1"
    for artifact in manifest["artifacts"]:
        artifact_path = spec / artifact["path"]
        assert artifact_path.is_file()
        assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == artifact["sha256"]
    evidence = json.loads((spec / "qa-evidence.json").read_text(encoding="utf-8"))
    assert evidence["obligations"][0]["verdict"] == "Pass"
    assert _qa_evidence_vet(evidence, spec, tmp_path) == []


def test_a_failing_upstream_pipeline_stage_fails_the_step(tmp_path: Path):
    """An assertion that cannot tell a broken command from a true negative is not an oracle.

    A pipeline's exit status is its last stage, so `jq <missing-file> | wc -l` exits 0 and
    prints `0` whether jq read an empty result or never ran at all — and `assert_contains: "0"`
    on that step passes having observed nothing. `set -o pipefail` is what lets the driver's
    non-zero-exit path see the upstream failure.
    """
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    action = data["scenarios"][0]["actions"][0]
    action["cmd"] = "cat ./absent-upstream.json | wc -l"
    action["assert_contains"] = "0"
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    outcome = cmd_run(plan, root=tmp_path)

    assert outcome.status == "failed"
    evidence = json.loads((spec / "qa-evidence.json").read_text(encoding="utf-8"))
    assert evidence["obligations"][0]["verdict"] == "Fail"


def test_one_failing_assertion_sinks_the_item_it_covers(tmp_path: Path):
    """Evidence is a summary of the run log, so it may not disagree with the run log.

    The aggregation used to read the passing assertions alone, which made an item Pass as soon
    as any one assertion covering it succeeded. A live journey that walked eight steps and
    failed the ninth therefore published every criterion Pass under an `overall: Fail` — an
    artifact strictly worse than none, because the QA assessor downstream either routes on the
    per-item verdicts the same file's `overall` contradicts, or spends a turn every pass
    rediscovering that it has to read `qa/qa-run.ndjson` instead.
    """
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    data["scenarios"][0]["actions"].append(
        {
            "do": "command",
            "id": "emit-again",
            "cmd": "printf '{\"value\":\"ok\"}'",
            "assert_contains": "absent",
            "out": "qa/steps/emit-again.json",
        }
    )
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    outcome = cmd_run(plan, root=tmp_path)

    assert outcome.status == "failed"
    evidence = json.loads((spec / "qa-evidence.json").read_text(encoding="utf-8"))
    assert evidence["overall"] == "Fail"
    row = evidence["obligations"][0]
    assert row["verdict"] == "Fail"
    # The disproof is named, not merely implied by the absence of a Pass: a consumer routing on
    # this file should not have to re-derive from the log which assertion sank the item.
    assert row["failing_log_refs"] == ["api-contract:assert:2"]
    assert row["log_refs"] == ["api-contract:assert:1", "api-contract:assert:2"]
    assert _qa_evidence_vet(evidence, spec, tmp_path) == []

    # And the gate rejects the same claim made by hand, which is the shape an agent authoring
    # the file itself produces — every check but this one asks whether a Pass is supported.
    tampered = json.loads(json.dumps(evidence))
    tampered["obligations"][0] = {
        "id": obligation,
        "verdict": "Pass",
        "log_refs": ["api-contract:assert:1"],
        "evidence": evidence["obligations"][0]["evidence"] or ["qa/qa-run.ndjson"],
    }
    problems = _qa_evidence_vet(tampered, spec, tmp_path)
    assert any(
        "marked Pass but the run log records failing assertions" in problem
        and "api-contract:assert:2" in problem
        for problem in problems
    ), problems


def test_v2_validation_rejects_disposable_input_and_unasserted_coverage(tmp_path: Path):
    spec = tmp_path / "docs/specs/story-1"
    (spec / "qa").mkdir(parents=True)
    obligation = _context(spec)
    payload = spec / "qa/payload.json"
    payload.write_text("{}", encoding="utf-8")
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    data["inputs"] = {"payload": "qa/payload.json"}
    data["scenarios"][0]["actions"][0].pop("assert_contains")
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    outcome = cmd_validate(plan, root=tmp_path)

    assert outcome.status == "invalid"
    assert any("disposable qa" in problem for problem in outcome.data["problems"])
    assert any("no machine assertion" in problem for problem in outcome.data["problems"])


def test_v2_validation_rejects_a_bare_evidence_path_inside_a_command(tmp_path: Path):
    """`qa/steps/x` means the evidence dir under `out:` and a missing dir inside a `cmd`.

    `out:` is resolved against the spec directory; a `cmd` runs with its cwd at the repo root,
    where `qa/steps/` does not exist. A plan that chains actions through hand-written temp files
    therefore has every redirect fail, every command exit with empty stdout, and every downstream
    assertion fail — against an implementation that is correct. A real run lost 38 of 66
    assertions that way and routed the story to rework. The absolute spelling still passes, so
    the rule rejects the ambiguity rather than the directory.
    """
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    action = data["scenarios"][0]["actions"][0]
    action["cmd"] = "printf '{\"value\":\"ok\"}' > qa/steps/body.json && cat qa/steps/body.json"
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    outcome = cmd_validate(plan, root=tmp_path)

    assert outcome.status == "invalid"
    assert any("bare 'qa/steps/'" in problem for problem in outcome.data["problems"])

    # The same command written absolutely addresses the same file and is the documented fix, so
    # it must survive — otherwise the rule bans the evidence directory instead of the ambiguity.
    body = f"{spec}/qa/steps/body.json"
    action["cmd"] = f"printf '{{\"value\":\"ok\"}}' > {body} && cat {body}"
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    absolute = cmd_validate(plan, root=tmp_path)
    assert absolute.status == "passed", absolute.data


def test_v2_secret_is_runtime_only_and_redacted(tmp_path: Path, monkeypatch):
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    data["secrets"] = {"token": {"from_env": "QA_TOKEN"}}
    action = data["scenarios"][0]["actions"][0]
    action["cmd"] = "printf '{{secret.token}}'"
    action["assert_contains"] = "{{secret.token}}"
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("QA_TOKEN", "top-secret-value")

    outcome = cmd_run(plan, root=tmp_path)

    assert outcome.status == "passed"
    persisted = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in [
            spec / "qa/qa-run.ndjson",
            spec / "qa/qa-session.json",
            spec / "qa/steps/emit.json",
        ]
        if path.exists()
    )
    assert "top-secret-value" not in persisted
    assert "{{secret.token}}" in (spec / "qa/qa-run.ndjson").read_text(encoding="utf-8")


def test_v2_separates_a_documented_node_from_a_genuinely_unknown_id(tmp_path: Path):
    """A node the diff does not touch is not "unknown" — and saying so costs a rework lap.

    The live failure: a plan covered `okf:…/api.md#tooling:contract`. `#tooling` is a real
    documented section, so "covers unknown ID" sent the author back to the book to confirm
    a node that was never in question, instead of to the obligation list — which is the
    only place that says what this change actually owes. The plan came back asserting the
    same id and the story spent one of its three plan reworks on the round trip.
    """
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    context = json.loads((spec / "qa-okf-context.json").read_text(encoding="utf-8"))
    context["contracts"] = ["docs/features/demo/api.md#tooling"]
    (spec / "qa-okf-context.json").write_text(json.dumps(context), encoding="utf-8")

    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    data["scenarios"][0]["covers"] = [
        obligation,
        "okf:docs/features/demo/api.md#tooling:contract",   # documented, but not owed here
        "okf:docs/features/demo/invented.md:contract",      # not in the book at all
    ]
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    document, load_problems = load_plan(plan, spec, tmp_path)
    assert not load_problems and document is not None
    problems = validate_v2(document)
    documented = next(p for p in problems if "#tooling" in p)
    unknown = next(p for p in problems if "invented.md" in p)

    # The documented-but-untouched one says so, and does not call the node unknown.
    assert "not an obligation of this change" in documented
    assert "unknown ID" not in documented
    # Both name what the plan *could* cover — the list neither message used to carry.
    assert obligation in documented
    assert obligation in unknown
    assert "unknown ID" in unknown


def test_load_plan_requires_okf_context(tmp_path: Path):
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    plan = _plan(spec, "okf:missing")
    document, problems = load_plan(plan, spec, tmp_path)
    assert not problems and document is not None
    assert any("qa-okf-context.json is required" in item for item in validate_v2(document))


def test_maestro_compiler_emits_native_two_document_flow():
    flow = _compile_maestro(
        {"app_id": "com.example.app"},
        {
            "id": "profile",
            "actions": [
                {"do": "launch", "clear_state": False},
                {"do": "tap", "locator": {"text": "Profile"}},
                {"do": "fill", "locator": {"id": "display-name"}, "value": "Updated"},
                {"expect": "value", "locator": {"id": "display-name"}, "value": "Updated"},
                {"capture": "screenshot", "name": "profile-restored"},
            ],
        },
    )
    documents = list(yaml.safe_load_all(flow))
    assert documents[0] == {"appId": "com.example.app"}
    assert documents[1][0] == {"launchApp": {"clearState": False}}
    assert {"takeScreenshot": "profile-restored"} in documents[1]


def test_recording_cannot_be_disabled_by_the_plan_itself(tmp_path: Path):
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    data["policy"] = {"recording_exempt_targets": ["web"]}
    data["targets"] = {
        "web": {
            "driver": "playwright",
            "base_url": "http://localhost:3000",
            "recording": {"required": False},
        }
    }
    data["scenarios"][0]["target"] = "web"
    data["scenarios"][0]["actions"] = [
        {"expect": "visible", "locator": {"role": "button", "name": "Add"}}
    ]
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    result = cmd_validate(plan, root=tmp_path)
    assert any("repository policy" in problem for problem in result.data["problems"])

    (tmp_path / "ostler.yml").write_text(
        "qa:\n  recordingExemptTargets: [web]\n",
        encoding="utf-8",
    )
    assert cmd_validate(plan, root=tmp_path).status == "passed"


def _playwright_url_plan(spec: Path, obligation: str, expectation: dict) -> Path:
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    data["targets"] = {"web": {"driver": "playwright", "base_url": "http://localhost:3000"}}
    data["scenarios"][0]["target"] = "web"
    data["scenarios"][0]["actions"] = [{"expect": "url", **expectation}]
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return plan


def test_expect_url_accepts_contains_as_an_alternative_to_an_exact_value(tmp_path: Path):
    """A URL with a non-deterministic piece (query param, encoded return-path) can only be

    asserted by substring — `value:` demands the whole string match. `contains:` was silently
    accepted by the plan schema without being wired to any real check, so a typo'd assertion
    passed validation and then no-op'd true at run time. It must now either work or be rejected.
    """
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)

    contains_plan = _playwright_url_plan(spec, obligation, {"contains": "#configuration"})
    assert cmd_validate(contains_plan, root=tmp_path).status == "passed"

    value_plan = _playwright_url_plan(spec, obligation, {"value": "http://localhost:3000/x"})
    assert cmd_validate(value_plan, root=tmp_path).status == "passed"


def test_expect_url_rejects_neither_or_both_of_value_and_contains(tmp_path: Path):
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)

    neither = _playwright_url_plan(spec, obligation, {})
    result = cmd_validate(neither, root=tmp_path)
    assert result.status == "invalid"
    assert any("exactly one of value" in problem for problem in result.data["problems"])

    both = _playwright_url_plan(
        spec, obligation, {"value": "http://localhost:3000/x", "contains": "/x"}
    )
    result = cmd_validate(both, root=tmp_path)
    assert result.status == "invalid"
    assert any("exactly one of value" in problem for problem in result.data["problems"])


def test_expect_url_contains_matches_a_url_with_a_non_deterministic_suffix(tmp_path: Path, monkeypatch):
    """The Playwright driver's assertion, not just the schema — the substring must actually
    match against a URL it does not equal.
    """
    class _Page:
        url = "http://localhost:3000/fr/guide-complet?token=abc123#configuration"

    class _Expect:
        def __init__(self, page):
            self.page = page

        def to_have_url(self, pattern, timeout):
            assert pattern.search(self.page.url), f"{pattern.pattern!r} did not match {self.page.url!r}"

    fake = types.ModuleType("playwright.sync_api")
    fake.__dict__["expect"] = _Expect
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake)

    driver = PlaywrightDriver.__new__(PlaywrightDriver)
    driver.session = QaSession(tmp_path)
    driver.session._data = {"run_id": "qa-run-1", "story": "story-1"}
    driver.variables = {}
    driver._expect(_Page(), {"expect": "url", "contains": "#configuration"})


def test_an_accessibility_snapshot_uses_an_api_playwright_still_has(tmp_path: Path):
    """``page.accessibility`` was removed from Playwright, and its absence surfaced as an
    ordinary scenario failure — so a plan that captured evidence looked like a product defect.
    The fake stands in for a current Page: it has ``aria_snapshot`` and no ``accessibility``.
    """
    class _Body:
        def aria_snapshot(self) -> str:
            return '- status: "Copied."'

    class _Page:
        def locator(self, selector: str) -> _Body:
            assert selector == "body"
            return _Body()

        def __getattr__(self, item: str):
            raise AttributeError(f"'Page' object has no attribute {item!r}")

    driver = PlaywrightDriver.__new__(PlaywrightDriver)
    driver.session = QaSession(tmp_path)
    driver.session._data = {"run_id": "qa-run-1", "story": "story-1"}

    path = driver._capture(_Page(), {"capture": "accessibility_snapshot", "name": "copied"}, "s", 1)
    assert path.read_text(encoding="utf-8") == '- status: "Copied."\n'


def test_an_unmatchable_role_name_pair_says_the_name_is_what_missed():
    """"element(s) not found" reads identically for a missing element and an impossible name.

    A role that does not take its accessible name from its text content — ``status``, a live
    region — can never match a ``name:`` drawn from that text, so the assertion burns its whole
    timeout proving something about the plan, and every reader blames the product. Counting the
    role on its own is what separates the two.
    """
    class _Locator:
        def __init__(self, count: int) -> None:
            self._count = count

        def count(self) -> int:
            return self._count

    class _Page:
        def __init__(self, present: int) -> None:
            self.present = present

        def get_by_role(self, role: str, name: str | None = None) -> _Locator:
            return _Locator(self.present)

    driver = PlaywrightDriver.__new__(PlaywrightDriver)
    action = {"expect": "visible", "locator": {"role": "status", "name": "Copied."}}
    original = AssertionError("Locator expected to be visible\nError: element(s) not found")

    enriched = str(driver._enrich(_Page(1), action, original))
    assert "element(s) not found" in enriched, "the original failure must survive verbatim"
    assert "does not take its accessible name from its text content" in enriched
    assert "1 element(s) carry that role" in enriched

    gone = str(driver._enrich(_Page(0), action, original))
    assert "does not take its accessible name" in gone, (
        "the element a plan waits for is usually transient, so it is already gone when the "
        "timeout expires — a live count of zero must not silence the static role fact"
    )

    named = {"expect": "visible", "locator": {"role": "button", "name": "Copy link"}}
    assert driver._enrich(_Page(0), named, original) is original, (
        "'button' is named from its content, so this locator is well-formed and the plain "
        "failure is the honest one"
    )
    bare = {"expect": "visible", "locator": {"role": "status"}}
    assert driver._enrich(_Page(1), bare, original) is original
    css = {"expect": "visible", "locator": {"css": ".copy-feedback"}}
    assert driver._enrich(_Page(1), css, original) is original


def test_a_chromium_context_is_granted_the_clipboard_by_default():
    """A copy journey is only provable if the context can reach the clipboard.

    Chromium denies an ungranted permission instead of prompting, so
    ``navigator.clipboard.writeText()`` rejects; an app that catches that renders its
    failure branch with no console error, and the run blames the product for a harness
    default. Firefox and WebKit reject the clipboard permission names outright, so the
    default is Chromium's alone.
    """
    driver = PlaywrightDriver.__new__(PlaywrightDriver)

    driver.target = {"driver": "playwright", "base_url": "http://127.0.0.1:8099"}
    assert driver._permissions() == ["clipboard-read", "clipboard-write"]

    driver.target = {"driver": "playwright", "browser": "firefox"}
    assert driver._permissions() == []

    driver.target = {"driver": "playwright", "permissions": ["geolocation"]}
    assert driver._permissions() == ["geolocation"]

    driver.target = {"driver": "playwright", "permissions": []}
    assert driver._permissions() == [], "an explicit empty list denies, it does not fall back"


def test_a_response_record_carries_the_status_a_5xx_assertion_needs():
    """``requestfailed`` never fires for a completed 500, so before the ``response``
    listener existed the diagnostics file had no status in it anywhere. A plan that wrote
    ``[.responses[]? | select(.status >= 500)] | length == 0`` was reading a key nothing
    produced, and jq answers a missing field with an empty stream rather than an error —
    so the assertion passed on every run, including the ones serving 500s.
    """

    class _Request:
        method = "POST"

    class _Response:
        url = "http://127.0.0.1:8099/api/docs"
        status = 503
        request = _Request()

    assert PlaywrightDriver._response_record(_Response()) == {
        "url": "http://127.0.0.1:8099/api/docs",
        "status": 503,
        "method": "POST",
    }


def test_a_failed_request_record_says_why_it_failed():
    """``requestfailed`` fires for an app cancelling its own fetch just as it does for a
    refused connection. With only the URL recorded the two are the same entry, so a plan
    that gates on ``.failedRequests | length == 0`` goes red on a benign StrictMode abort
    and the only way back to green is to stop asserting on the field.
    """

    class _Request:
        url = "http://127.0.0.1:8099/v1/pages/p_copy_links/fr"
        method = "GET"
        failure = "net::ERR_ABORTED"

    assert PlaywrightDriver._failed_request_record(_Request()) == {
        "url": "http://127.0.0.1:8099/v1/pages/p_copy_links/fr",
        "method": "GET",
        "errorText": "net::ERR_ABORTED",
    }

    class _Unexplained(_Request):
        failure = None

    assert PlaywrightDriver._failed_request_record(_Unexplained())["errorText"] == "", (
        "a missing failure reason is the empty string, never a null a jq select would skip"
    )


def test_two_browser_targets_share_one_playwright(monkeypatch):
    """A plan with two Playwright targets must not start Playwright twice on one thread.

    The runner starts every target's driver before the first scenario, and the sync API
    drives an event loop of its own: the second ``sync_playwright().start()`` lands inside
    the first one's loop and raises, which ended a whole run `invalid` with zero scenarios
    executed. One shared handle, released by whichever driver stops last.
    """
    starts: list[str] = []
    stops: list[str] = []

    class _Playwright:
        def stop(self) -> None:
            stops.append("stop")

    class _Context:
        def start(self) -> _Playwright:
            starts.append("start")
            return _Playwright()

    fake = types.ModuleType("playwright.sync_api")
    # Populated through the namespace rather than by attribute: `ModuleType` declares no
    # `sync_playwright`, so `fake.sync_playwright = ...` is an unresolved attribute to
    # anything that checks types, and the point of a fake module is that its contents are
    # exactly what the test puts in it.
    fake.__dict__["sync_playwright"] = _Context
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake)
    monkeypatch.setattr(SharedPlaywright, "_playwright", None)
    monkeypatch.setattr(SharedPlaywright, "_users", 0)

    first = SharedPlaywright.acquire()
    second = SharedPlaywright.acquire()

    assert first is second
    assert starts == ["start"]

    SharedPlaywright.release()
    assert stops == [], "still held by the target whose browser is open"
    SharedPlaywright.release()
    assert stops == ["stop"]
    assert SharedPlaywright._playwright is None


def test_v1_plan_survives_cleanup_and_uses_static_inputs(tmp_path: Path):
    spec = tmp_path / "docs/specs/story-1"
    inputs = spec / "qa-inputs"
    inputs.mkdir(parents=True)
    (inputs / "value.txt").write_text("stable-input", encoding="utf-8")
    plan = spec / "qa-plan.yml"
    plan.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "run_id": "legacy-run",
                "story": "story-1",
                "inputs": {"value": "qa-inputs/value.txt"},
                "steps": [
                    {
                        "id": "read-input",
                        "mechanism": "fixture",
                        "cmd": "cat {{input.value}}",
                        "assert_contains": "stable-input",
                        "out": "qa/steps/value.txt",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (spec / "qa").mkdir()
    (spec / "qa/stale").write_text("stale", encoding="utf-8")

    result = cmd_run(plan, root=tmp_path)

    assert result.status == "passed"
    assert (inputs / "value.txt").is_file()
    assert not (spec / "qa/stale").exists()
    assert (spec / "qa/steps/value.txt").read_text(encoding="utf-8") == "stable-input"


def test_v1_plan_and_inputs_are_rejected_under_disposable_qa(tmp_path: Path):
    spec = tmp_path / "docs/specs/story-1"
    qa = spec / "qa"
    qa.mkdir(parents=True)
    (qa / "input.json").write_text("{}", encoding="utf-8")
    plan = qa / "qa-plan.yml"
    plan.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "run_id": "bad",
                "story": "story-1",
                "inputs": {"payload": "qa/input.json"},
                "steps": [],
            }
        ),
        encoding="utf-8",
    )
    result = cmd_validate(plan, spec, root=tmp_path)
    assert any("qa-plan.yml cannot live" in item for item in result.data["problems"])
    assert any("input 'payload'" in item for item in result.data["problems"])


def test_a_command_ready_check_polls_until_the_daemon_says_it_is_up(tmp_path: Path):
    """`ready_check` accepts a `{cmd, assert_contains}` mapping, not just a URL.

    A URL cannot express every service's notion of "up": the plan that surfaced this ran an
    API whose only route was a `POST`, so no `GET` answered 200 and the string form could
    not probe it at all. The mapping used to be handed straight to `urlopen`, which set
    `.timeout` on it — an `AttributeError`, which the poll's `URLError`/`OSError` guard did
    not catch, so it aborted the run before its first scenario.

    The daemon here is slow on purpose: the check must fail once and be retried, which is
    the whole point of a readiness probe, and it must run in the daemon's own directory.
    """
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    data["background"] = [
        {
            "name": "api-server",
            "cmd": "sleep 0.4; printf listening > ready.txt; sleep 30",
            "ready_check": {"cmd": "cat ready.txt", "assert_contains": "listening"},
            "timeout": 10,
        }
    ]
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    outcome = cmd_run(plan, root=tmp_path)

    assert outcome.status == "passed", outcome.message
    records = [
        json.loads(line)
        for line in (spec / "qa/qa-run.ndjson").read_text(encoding="utf-8").splitlines()
    ]
    assert not [row for row in records if row.get("kind") == "runner_error"], records
    (started,) = [row for row in records if row.get("kind") == "daemon_start"]
    assert started["ready_check"]["assert_contains"] == "listening"
    # `cat ready.txt` resolved against the daemon's cwd, which is the repo root here.
    assert (tmp_path / "ready.txt").read_text(encoding="utf-8") == "listening"


def test_a_run_that_dies_before_its_scenarios_reports_why(tmp_path: Path):
    """The caller must be told the cause, not just that nothing ran.

    The ledger has always carried a `runner_error` record, but the returned message carried
    only counts — so a crash in the runner surfaced to the coder workflow's QA gate as
    "0 scenarios" with no cause. Having nothing to route around, the gate sent a valid,
    reviewer-approved plan back to be re-planned until its rework guard ran out. A gate can
    only act on a failure it can read.
    """
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    data["background"] = [
        {
            "name": "api-server",
            "cmd": "sleep 30",
            "ready_check": {"cmd": "false"},  # never ready
            "timeout": 1,
        }
    ]
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    outcome = cmd_run(plan, root=tmp_path)

    assert outcome.status == "invalid", outcome.message
    assert "0 scenarios" in outcome.message
    assert "TimeoutError" in outcome.message, outcome.message
    assert "ready_check" in outcome.message, outcome.message
    assert outcome.data["runner_errors"], outcome.data


def test_a_daemon_that_dies_on_startup_is_reported_as_dead_with_what_it_printed(tmp_path: Path):
    """"Timed out" describes a slow service. A daemon that never started is a different fault.

    A service that cannot bind, compile or migrate exits in under a second, and the poll used
    to keep probing the corpse for the rest of the timeout and then report `ready_check timed
    out after 30s` — true of a slow daemon, misleading about a dead one, and silent on the
    cause. The run that prompted this had `listen tcp :8080: bind: address already in use`
    sitting in `qa/daemon-api-server.log` while the QA verdict said only "timed out"; the
    agent had to go find it and a gate deciding whether to retry could not see it at all.

    So both halves are asserted: the exit code (this is death, not slowness) and the daemon's
    own last words. The wall clock is asserted too — the whole point is not waiting out a
    timeout that cannot end any other way.
    """
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    data["background"] = [
        {
            "name": "api-server",
            "cmd": "echo 'listen tcp :8080: bind: address already in use' >&2; exit 1",
            "ready_check": {"cmd": "false"},  # never ready, because nothing is listening
            "timeout": 30,
        }
    ]
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    started = time.monotonic()
    outcome = cmd_run(plan, root=tmp_path)
    elapsed = time.monotonic() - started

    assert outcome.status == "invalid", outcome.message
    assert "exited with code 1" in outcome.message, outcome.message
    assert "address already in use" in outcome.message, outcome.message
    # Failed on the exit, not by waiting out the 30s the plan asked for.
    assert elapsed < 15, f"polled a dead daemon for {elapsed:.1f}s"


def test_a_dead_daemon_whose_check_still_passes_fails_the_run(tmp_path: Path):
    """A readiness probe asks "is anything answering", never "is it mine".

    This is the observed false pass, reproduced. A previous run's server was still bound to
    the port, so the daemon this run started died instantly on `address already in use` —
    and the probe got its `201` from the orphan. The session recorded `passed` with zero
    runner errors, and the suite validated a binary built five minutes earlier instead of
    the code under test. Silent, and worse than any false failure.

    The stand-in for the orphan is a file the check reads: the daemon fails to create it
    (something already did), the check finds it anyway, and the run must still fail. A
    non-zero exit outranks a passing check; `test_a_launcher_that_forks...` pins the other
    half, that exit 0 does not.
    """
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    (tmp_path / "ready.txt").write_text("listening", encoding="utf-8")  # the orphan
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    data["background"] = [
        {
            "name": "api-server",
            "cmd": "echo 'bind: address already in use' >&2; exit 1",
            "ready_check": {"cmd": "cat ready.txt", "assert_contains": "listening"},
            "timeout": 10,
        }
    ]
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    outcome = cmd_run(plan, root=tmp_path)

    assert outcome.status == "invalid", outcome.message
    assert "exited with code 1" in outcome.message, outcome.message
    # The message must name the actual fault, or the reader concludes the check is flaky.
    assert "something other than this run's daemon is answering" in outcome.message
    assert "address already in use" in outcome.message, outcome.message


def test_a_daemon_that_dies_just_after_a_passing_check_still_fails_the_run(tmp_path: Path):
    """The rule above was a race, and this is the half of it that was losing.

    Both facts are sampled in the same instant: the orphan answers immediately, and our own
    daemon — which is going to die on `address already in use` — has not been scheduled long
    enough to have exited, so `poll()` reads `None`. Ready wins, and the suite runs green
    against the previous run's server. Exactly the false pass the test above claims to catch,
    reached by losing the race instead of by the check arriving late.

    The daemon here dies half a second in, which is what a real bind failure behind a
    shell wrapper looks like. Nothing about the verdict may depend on which of the two won.
    """
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    (tmp_path / "ready.txt").write_text("listening", encoding="utf-8")  # the orphan
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    data["background"] = [
        {
            "name": "api-server",
            "cmd": "sleep 0.5; echo 'bind: address already in use' >&2; exit 1",
            "ready_check": {"cmd": "cat ready.txt", "assert_contains": "listening"},
            "timeout": 10,
        }
    ]
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    outcome = cmd_run(plan, root=tmp_path)

    assert outcome.status == "invalid", outcome.message
    assert "exited with code 1" in outcome.message, outcome.message
    assert "something other than this run's daemon is answering" in outcome.message
    assert "address already in use" in outcome.message, outcome.message


def test_a_launcher_that_forks_and_exits_zero_still_counts_as_ready(tmp_path: Path):
    """Exit 0 is a hand-off, not a death — the other half of the rule above.

    `docker compose up -d`, a wrapper that backgrounds the real server, an `npm start` that
    execs and detaches: all exit 0 while the service they started comes up behind them. If a
    clean exit stopped the poll, none of them could ever be a daemon here.
    """
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    data["background"] = [
        {
            "name": "api-server",
            # Hands off to a child that becomes ready after the launcher is already gone.
            "cmd": "(sleep 1; printf listening > ready.txt) & exit 0",
            "ready_check": {"cmd": "cat ready.txt", "assert_contains": "listening"},
            "timeout": 10,
        }
    ]
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    outcome = cmd_run(plan, root=tmp_path)

    assert outcome.status == "passed", outcome.message


def test_an_unrunnable_ready_check_is_caught_at_validation(tmp_path: Path):
    """Where a bad daemon shape should fail: at validate, with a diagnostic naming it.

    `background` was the one top-level block nobody validated, and its entries are the ones
    that reach a subprocess. A failure at run time gets a status and a sentence; a failure
    here is handed to the plan agent as a field-level diagnostic it can act on.
    """
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    data["background"] = [
        {"name": "api", "cmd": "go run ./cmd/server", "ready_check": "localhost:8080/health"},
        {"name": "web", "cmd": "npm start", "ready_check": {"assert_contains": "201"}},
        {"name": "web", "cmd": "", "ready_check": {"cmd": "curl -s /", "url": "/"}},
    ]
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    problems = cmd_validate(plan, root=tmp_path).data["problems"]

    assert any("must be an http(s) URL" in item for item in problems), problems
    assert any("requires a non-empty 'cmd'" in item for item in problems), problems
    assert any("duplicate background daemon 'web'" in item for item in problems), problems
    assert any("cmd is required and must be non-empty" in item for item in problems), problems
    assert any("unknown keys ['url']" in item for item in problems), problems


def test_a_step_that_writes_into_qa_steps_itself_finds_the_directory_there(tmp_path: Path):
    """`qa/steps/` is a layout ostler publishes, so ostler has to be the one that creates it.

    Nothing here needed it early for ostler's own sake: the `out:` sidecar mkdirs its parent
    after the subprocess returns, and `qa/asserts/` is made just before the first assertion is
    written. But the plan prompt tells agents to put evidence under `qa/steps/`, and a plan took
    it literally with a `curl -o .../qa/steps/create-fixture.json` fixture step — which runs
    before ostler has written any sidecar, and so before anything has made the directory. curl
    cannot create it, exits 23, and the capture that step was to feed comes back empty. The
    request that reads the capture then goes somewhere unrelated and gets a plausible wrong
    answer: a 404 that reads as a product defect rather than as a missing directory.

    So the step here is deliberately a plain shell redirect rather than an `out:` — `out:` was
    never broken, and asserting on it would test the wrong half. It bites only the first run
    against a fresh spec dir, which is exactly the run least likely to be doubted.
    """
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    fixture = spec / "qa/steps/create-fixture.json"
    data["scenarios"][0]["actions"].insert(
        0,
        {
            "do": "command",
            "id": "create-fixture",
            "cmd": f"printf '{{\"code\":\"abc\"}}' > {fixture}",
        },
    )
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    assert not fixture.parent.exists()  # fresh spec dir: the first run is the one that breaks

    outcome = cmd_run(plan, root=tmp_path)

    assert outcome.status == "passed", outcome.message
    assert json.loads(fixture.read_text(encoding="utf-8")) == {"code": "abc"}


def test_an_out_sidecar_never_blanks_a_file_the_command_wrote_itself(tmp_path: Path):
    """`out:` is a capture of stdout, and an empty capture is not a reason to delete evidence.

    A plan step that redirects its own stdout — `curl -w '%{http_code}' … > qa/steps/x.txt` —
    and also declares `out: qa/steps/x.txt` leaves nothing on the pipe for ostler to capture.
    The sidecar write then landed 0 bytes on top of the bytes curl had just written, and the
    assertion reading that file compared a status code against an empty string. It failed, and
    it failed *as a product defect*: a run reported three acceptance criteria broken while its
    own per-step ledger recorded the correct 404/201/302 for every request. The one criterion
    that passed was the one whose oracle read a `-D` header dump instead.

    Naming both is redundant, and a validator could say so — but the harm here is that ostler
    destroys output it did not produce, so the guard belongs at the write. `qa/` is wiped at
    session start, so a non-empty file at that path is always this run's own evidence.
    """
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    status = spec / "qa/steps/status.txt"
    data["scenarios"][0]["actions"] = [
        {
            "do": "command",
            "id": "probe",
            "cmd": f"printf '404' > {status}",
            "out": "qa/steps/status.txt",
        },
        {
            "do": "command",
            "id": "assert-404",
            "cmd": f"printf 'status=%s' \"$(cat {status})\"",
            "assert_contains": "status=404",
        },
    ]
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    outcome = cmd_run(plan, root=tmp_path)

    assert outcome.status == "passed", outcome.message
    assert status.read_text(encoding="utf-8") == "404"
    records = [
        json.loads(line)
        for line in (spec / "qa/qa-run.ndjson").read_text(encoding="utf-8").splitlines()
    ]
    probe = next(row for row in records if row.get("id") == "probe")
    # The ledger says why the sidecar holds bytes ostler did not capture.
    assert probe["stdout_file_written_by_cmd"] is True
    assert probe["stdout_file"] == str(status)


def test_expect_http_reads_a_status_the_command_redirected_to_its_own_out_file(tmp_path: Path):
    """The redirect that hid the file's contents hid the status code with it.

    `expect_http` reads the trailing `%{http_code}` that curl appends to stdout. A step that
    sends that stdout to a file has an empty pipe, so the status parsed as None and the check
    compared it against the code the plan expected — failing on every request the plan made,
    while the header dumps beside it showed the server had answered correctly all along.

    Keeping the file (the sibling guard) is not enough on its own: the four `assert_contains`
    oracles that re-read those files went green while four `expect_http` checks on the same
    steps stayed red, which is a worse state to leave a run in than uniformly failing. If the
    file is the step's stdout, everything derived from stdout has to come from it.
    """
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    body = spec / "qa/steps/response.txt"
    data["scenarios"][0]["actions"] = [
        {
            "do": "command",
            "id": "request",
            # What `curl -s -w '\n%{http_code}' … > file` leaves behind: body, then the code.
            "cmd": f"printf 'served\\n302' > {body}",
            "out": "qa/steps/response.txt",
            "expect_http": 302,
            "assert_contains": "served",
        },
    ]
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    outcome = cmd_run(plan, root=tmp_path)

    assert outcome.status == "passed", outcome.message
    # The file is untouched — the status was parsed out of it, not written back over it.
    assert body.read_text(encoding="utf-8") == "served\n302"
    records = [
        json.loads(line)
        for line in (spec / "qa/qa-run.ndjson").read_text(encoding="utf-8").splitlines()
    ]
    request = next(row for row in records if row.get("id") == "request")
    assert request["http_status"] == 302
    assert request["stdout_file_written_by_cmd"] is True


def test_expect_http_reads_the_status_line_of_a_curl_header_dump(tmp_path: Path):
    """`-D` is the other way a plan hands ostler a status, and it was the unreadable one.

    `curl -o body -D headers` sends the body one way and the response head another, leaving
    stdout empty — so there is no trailing `%{http_code}` for ostler to find, and `expect_http`
    compared None to 201 while the step's own sibling assertion read the same number off the
    same file with `head -1 | awk '{print $2}'`. Reporting an acceptance criterion broken over
    a status code sitting in a file ostler already captured is the worst answer available: it
    reads as a product defect and sends the loop off repairing working code.

    The redirect chain here is the reason the *last* status line wins rather than the first —
    with `-L` curl dumps every hop, and the expectation is about the response that came back,
    not the 302 that pointed at it.
    """
    spec = tmp_path / "docs/specs/demo"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    headers = spec / "qa/steps/create-headers.txt"
    dump = "HTTP/1.1 302 Found\r\nLocation: /final\r\n\r\nHTTP/1.1 201 Created\r\nContent-Type: application/json\r\n\r\n"
    data["scenarios"][0]["actions"] = [
        {
            "do": "command",
            "id": "create",
            # What `curl -s -o body.json -D headers.txt -L …` leaves in the dump.
            "cmd": f"printf '{dump}' > {headers}",
            "out": "qa/steps/create-headers.txt",
            "expect_http": 201,
        },
    ]
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    outcome = cmd_run(plan, root=tmp_path)

    assert outcome.status == "passed", outcome.message
    # The head is evidence in its own right — nothing is stripped out of it.
    assert "Location: /final" in headers.read_text(encoding="utf-8")
    records = [
        json.loads(line)
        for line in (spec / "qa/qa-run.ndjson").read_text(encoding="utf-8").splitlines()
    ]
    create = next(row for row in records if row.get("id") == "create")
    assert create["http_status"] == 201


def test_a_trailing_write_out_code_still_beats_a_body_that_looks_like_headers(tmp_path: Path):
    """The header-dump read is a fallback, and it has to stay one.

    A body can legitimately begin with `HTTP/` — a proxy log, a captured transcript, a fixture
    describing a response. If the dump scan ran first it would quietly win over the code curl
    was actually asked to write out, and the step would assert against a number from the payload
    instead of from the request. Ordering is the whole guarantee here, so it gets its own test.
    """
    spec = tmp_path / "docs/specs/demo"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    data["scenarios"][0]["actions"] = [
        {
            "do": "command",
            "id": "transcript",
            "cmd": "printf 'HTTP/1.1 500 Internal Server Error\\nrecorded upstream\\n200'",
            "expect_http": 200,
        },
    ]
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    outcome = cmd_run(plan, root=tmp_path)

    assert outcome.status == "passed", outcome.message


def test_an_uncapturable_status_says_so_instead_of_reporting_None(tmp_path: Path):
    """A step can assert `expect_http` and give ostler no way to answer it.

    `curl -o /dev/null -D headers.txt` with `out:` pointing at neither one leaves the pipe
    empty, so there is no status to compare and the assertion fails with `a: "None"`. That is
    true and useless: it is indistinguishable from the service having returned a status that
    didn't match, which is how two assessment turns in a row came to hunt a product regression
    that did not exist — one of them re-issuing every request by hand before concluding the
    plan, not the code, was at fault.

    The verdict is still a failure — the plan really can't prove what it claims. What changes
    is that the record says which kind of failure it is, in the field the reader actually reads.
    """
    spec = tmp_path / "docs/specs/demo"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    headers = spec / "qa/steps/headers.txt"
    data["scenarios"][0]["actions"] = [
        {
            "do": "command",
            "id": "probe",
            # Body to /dev/null, head to a file this step does not declare as its `out:`.
            "cmd": f"printf 'HTTP/1.1 404 Not Found\\n' > {headers}",
            "expect_http": 200,
        },
    ]
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    outcome = cmd_run(plan, root=tmp_path)

    assert outcome.status == "failed"
    records = [
        json.loads(line)
        for line in (spec / "qa/qa-run.ndjson").read_text(encoding="utf-8").splitlines()
    ]
    verdict = next(row for row in records if row.get("kind") == "assert")
    detail = json.dumps(verdict)
    assert "no HTTP status captured" in detail
    # Never the bare word that reads as an observed status.
    assert '"a": "None"' not in detail


def test_an_operation_written_as_a_mapping_is_reported_not_crashed(tmp_path: Path):
    """`do: {cmd: ...}` — arguments nested under the verb instead of beside it.

    A plan author who writes it that way gets a problem naming the mistake; the
    validator must not raise on an unhashable operation before it can say so.
    """
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    action = data["scenarios"][0]["actions"][0]
    action["do"] = {"cmd": action.pop("cmd")}
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    outcome = cmd_validate(plan, root=tmp_path)

    assert outcome.status == "invalid"
    assert any(
        "must name a single operation" in problem for problem in outcome.data["problems"]
    )


def test_stopping_a_daemon_that_already_exited_is_not_an_error():
    """Teardown must survive a daemon that stopped on its own.

    `killpg` does not answer the same way everywhere for a group with nothing left
    in it: on macOS/BSD an unreaped zombie leader gives EPERM (a zombie has no
    credentials to check the signal against), where Linux gives ESRCH. The kill path
    guarded only `ProcessLookupError`, so every `ostler qa run` on macOS ended by
    raising `PermissionError` out of `stop_all_daemons` — the run failed on cleanup
    after its scenarios had already passed.

    The **outcome** of that difference is not portable either, and asserting one
    platform's number is how this test then failed on the other Unix. A zombie is
    still a process on Linux, so `killpg` *succeeds*: the escalation runs its full
    SIGINT → SIGTERM window and reports SIGKILL, where macOS stops at the first EPERM
    and reports that nothing landed. Both are the contract being kept. What this test
    owns is that teardown **survives** — it returns rather than raising — so it
    accepts either answer and pins the invariant instead of the platform.
    """
    proc = subprocess.Popen("exit 0", shell=True, start_new_session=True)
    pid = proc.pid
    # Deliberately NOT reaped: the zombie window is exactly the case that broke.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            break
        except PermissionError:
            break  # macOS: the group is now all-zombie, which is what we want
        time.sleep(0.02)

    # 0 on macOS (EPERM read as "gone"); -SIGKILL on Linux, where the zombie group is
    # real enough to signal. Neither is a failure; raising would be.
    assert _kill_pid(pid) in (0, -signal.SIGKILL)
    proc.wait()


def test_a_live_daemon_is_still_stopped_and_reports_its_signal():
    """The EPERM tolerance above must not turn into "never kills anything"."""
    proc = subprocess.Popen("sleep 30", shell=True, start_new_session=True)
    try:
        assert _kill_pid(proc.pid) in (-signal.SIGINT, -signal.SIGTERM, -signal.SIGKILL)
    finally:
        proc.wait()

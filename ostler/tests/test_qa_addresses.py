"""The address book: a run's copy of a stack names its addresses, and every reader takes them from the book."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from ostler import doctor, model
from ostler.qa import addresses, attribution, stack as stack_mod
from ostler.qa.harness_host import load_harness_module

from conftest import write

harness = load_harness_module("ostler_qa")

OPS = Path("docs") / "services" / "app" / "ops"


@pytest.fixture(autouse=True)
def _own_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STABLEMATE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv(addresses.LEASE_ENV, raising=False)
    monkeypatch.delenv(addresses.BOOK_ENV, raising=False)


def _environment(root: Path, *, sharing: str, entries: dict[str, str], ops: Path = OPS) -> None:
    lines = "".join(f"  - `{name}`: {value}\n" for name, value in entries.items())
    write(root / ops / "test.md",
          f"---\ntype: environment\ntitle: Test\n---\n\n# Test\n\n- sharing: {sharing}\n"
          f"- addresses:\n{lines}")


def _runbook(root: Path, *, entry_url: str = "{gateway}", run: str = "make copy",
             health: str = "curl -fsS {gateway}/health", ops: Path = OPS) -> None:
    write(root / ops / "web.md",
          "---\ntype: runbook\ntitle: Web\n---\n\n# Web\n\n- driver: web\n"
          f"- environment: [Test](test.md)\n- entry-url: {entry_url}\n- stop: make copy-down\n\n"
          f"## Steps\n\n### serve\n\n- kind: service\n- run: {run}\n- health: {health}\n")


def _per_run_book(root: Path) -> None:
    (root / ".git").mkdir()
    _environment(root, sharing="per-run", entries={"gateway": "the browser's front door"})
    _runbook(root)


def test_a_reference_is_a_braced_name_and_never_a_shell_expansion() -> None:
    assert addresses.names_in("curl {gateway}/x ${HOME} {Bad} {api-2}") == ["gateway", "api-2"]


def test_substitution_leaves_a_name_the_book_does_not_give() -> None:
    assert addresses.substitute("{gateway}/x {other}", {"gateway": "http://h:1"}) == "http://h:1/x {other}"


def test_a_book_drops_the_trailing_slash_and_refuses_what_is_not_name_to_url(tmp_path: Path) -> None:
    book = tmp_path / "book.json"
    book.write_text(json.dumps({"gateway": "http://localhost:1234/"}))
    assert addresses.read_book(book) == {"gateway": "http://localhost:1234"}
    book.write_text(json.dumps(["http://localhost:1234"]))
    with pytest.raises(addresses.AddressError, match="not a JSON object"):
        addresses.read_book(book)
    with pytest.raises(addresses.AddressError, match="has not written it"):
        addresses.read_book(tmp_path / "missing.json")


def test_a_book_serves_an_environment_only_with_a_url_for_every_name() -> None:
    assert addresses.book_problems({"gateway": "http://h:1"}, ["gateway"]) == []
    assert addresses.book_problems({"gateway": "h:1"}, ["gateway", "api"]) == [
        "it gives no address for `api`",
        "its `gateway` is `h:1`, not an absolute http(s) URL",
    ]


def test_a_lease_names_containers_so_it_is_lowercase_and_plain() -> None:
    assert addresses.lease_problem("story-01m18_x") == ""
    assert addresses.lease_problem("Story 1")


def test_resolution_is_off_until_a_book_is_named_and_fails_when_the_named_book_is_absent(
        tmp_path: Path) -> None:
    assert addresses.resolve_now("{gateway}/x", {}) == "{gateway}/x"
    where = tmp_path / "book.json"
    with pytest.raises(addresses.AddressError):
        addresses.resolve_now("{gateway}/x", {addresses.BOOK_ENV: str(where)})
    addresses.write_book(where, {"gateway": "http://localhost:4321"})
    assert addresses.resolve_now("{gateway}/x", {addresses.BOOK_ENV: str(where)}) == "http://localhost:4321/x"


def test_a_lease_is_held_only_for_the_bring_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(addresses.LEASE_ENV, "before")
    with addresses.leased({addresses.LEASE_ENV: "story", addresses.BOOK_ENV: "/b.json"}):
        assert addresses.resolve_now("x") == "x"
        assert os.environ[addresses.LEASE_ENV] == "story"
    assert os.environ[addresses.LEASE_ENV] == "before"
    assert addresses.BOOK_ENV not in os.environ


def test_a_recipe_reads_its_address_from_the_book_as_it_starts(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    where = tmp_path / "book.json"
    monkeypatch.setenv(addresses.BOOK_ENV, str(where))
    assert stack_mod._url_now("{gateway}") == ""
    addresses.write_book(where, {"gateway": "http://localhost:4321"})
    assert stack_mod._url_now("{gateway}/") == "http://localhost:4321/"
    assert stack_mod._recipe_argv("curl {gateway}/health")[-1] == "curl http://localhost:4321/health"


def test_a_bring_up_reports_the_address_its_copy_wrote_while_the_gates_waited(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    where = tmp_path / "book.json"
    monkeypatch.setenv(addresses.BOOK_ENV, str(where))
    monkeypatch.setattr(stack_mod, "boot_app", lambda *_a, **_kw: {
        "boot_ok": "yes", "entry_url": "", "app_pid": "", "app_pgid": ""})

    def gates(*_a: Any, **_kw: Any) -> tuple[str, str]:
        addresses.write_book(where, {"gateway": "http://localhost:4321"})
        return "", ""

    monkeypatch.setattr(stack_mod, "_seed_then_gate", gates)
    out = stack_mod.ensure_stack(
        {"entry_url": "{gateway}/", "launch": "make copy-up", "app_cwd": str(tmp_path)},
        logger=logging.getLogger(__name__))
    assert out["ready"] == "yes"
    assert out["entry_url"] == "http://localhost:4321/"


def _fake_bring_up(book: dict[str, str] | None, seen: list[dict[str, str]]):
    def ensure_stack(manifest: dict[str, Any], *, repo_root: str, logger: Any) -> dict[str, Any]:
        seen.append({key: os.environ.get(key, "") for key in (addresses.LEASE_ENV, addresses.BOOK_ENV)})
        if book is not None:
            addresses.write_book(Path(os.environ[addresses.BOOK_ENV]), book)
        return {"ready": "yes", "adopted": "no",
                "entry_url": stack_mod._url_now(manifest["entry_url"])}
    return ensure_stack


def _fake_teardown(seen: list[dict[str, str]]):
    def teardown_stack(handles: dict[str, str], manifest: dict[str, Any], *, logger: Any) -> dict[str, str]:
        seen.append({"source": manifest.get("source", ""),
                     **{key: os.environ.get(key, "") for key in (addresses.LEASE_ENV, addresses.BOOK_ENV)}})
        return {"torn_down": "yes"}
    return teardown_stack


def codes(root: Path) -> list[str]:
    return [fd.code for fd in doctor.run(model.load(root)).findings]


def test_a_plan_target_opens_the_runs_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert harness.resolve_addresses("{gateway}") == "{gateway}"
    where = tmp_path / "book.json"
    where.write_text(json.dumps({"gateway": "http://localhost:4321/"}))
    monkeypatch.setenv(harness.ADDRESS_BOOK_ENV, str(where))
    assert harness.resolve_addresses("{gateway}") == "http://localhost:4321"
    with pytest.raises(ValueError, match="does not give"):
        harness.resolve_addresses("{api}")


def test_a_base_url_with_no_address_book_to_give_it_is_named_as_an_environment_fault(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(harness.ADDRESS_BOOK_ENV, raising=False)
    detail = harness.unresolved_address_detail(harness.Target("web_web", base_url="{gateway}/app"))
    assert detail is not None
    assert "'web_web'" in detail and "{gateway}" in detail and f"${harness.ADDRESS_BOOK_ENV} is unset" in detail
    assert harness.unresolved_address_detail(harness.Target("web_web", base_url="http://localhost:1")) is None
    assert harness.unresolved_address_detail(harness.Target("web_web")) is None


UNRESOLVED_PLAN = '''\
from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-addresses", story="addresses")

web = target("web_web", base_url="{gateway}/app")


@scenario(target=web, mechanism="live", covers=["ac:1"])
def opens_the_app(qa: Qa) -> None:
    """Never reached."""
    qa.check("reached", True)
'''


def test_a_scenario_whose_address_has_no_book_errors_as_an_environment_fault(tmp_path: Path) -> None:
    module = tmp_path / "qa_plan.py"
    module.write_text(UNRESOLVED_PLAN, encoding="utf-8")
    records_to = tmp_path / "records.jsonl"
    context = json.dumps({"root": str(tmp_path), "spec_dir": str(tmp_path), "qa_dir": str(tmp_path / "qa")})
    harness_dir = Path(__file__).resolve().parents[1] / "ostler" / "qa" / "harness"
    with records_to.open("w") as sink:
        done = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "ostler_qa", "run", str(module), "opens-the-app", context],
            capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL, pass_fds=(sink.fileno(),),
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(harness_dir),
                 "OSTLER_QA_RECORD_FD": str(sink.fileno())},
        )
    records = [json.loads(line) for line in records_to.read_text(encoding="utf-8").splitlines() if line]
    scenario = next(r for r in records if r.get("type") == "scenario")
    assert done.returncode == 1
    assert scenario["status"] == "errored"
    assert scenario["stop"]["fault"]["fault_class"] == "environment"
    assert "{gateway}" in scenario["error"]
    assert attribution.attribute(attribution.CheckEvidence.model_validate(scenario["stop"])).cause is (
        attribution.Cause.ENVIRONMENT)

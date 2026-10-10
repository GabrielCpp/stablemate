"""The address book: a run's copy of a stack names its addresses, and every reader takes them from the book."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from ostler import doctor, model, reach
from ostler.qa import addresses, runbook as rb, stack as stack_mod
from ostler.qa.harness_host import load_harness_module

from conftest import write

harness = load_harness_module("ostler_qa")

OPS = Path("docs") / "features" / "app" / "ops"


@pytest.fixture(autouse=True)
def _own_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STABLEMATE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv(addresses.LEASE_ENV, raising=False)
    monkeypatch.delenv(addresses.BOOK_ENV, raising=False)


def _environment(root: Path, *, sharing: str, entries: dict[str, str]) -> None:
    lines = "".join(f"  - `{name}`: {value}\n" for name, value in entries.items())
    write(root / OPS / "test.md",
          f"---\ntype: environment\ntitle: Test\n---\n\n# Test\n\n- sharing: {sharing}\n"
          f"- addresses:\n{lines}")


def _runbook(root: Path, *, entry_url: str = "{gateway}", run: str = "make copy",
             health: str = "curl -fsS {gateway}/health") -> None:
    write(root / OPS / "web.md",
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


def test_a_per_run_environment_refuses_a_bring_up_with_no_lease(tmp_path: Path) -> None:
    _per_run_book(tmp_path)
    outcome = rb.cmd_stack_up(tmp_path)
    assert not outcome.ok and outcome.status == "lease-required"
    assert rb.cmd_stack_down(tmp_path).status == "lease-required"
    assert rb.cmd_stack_up(tmp_path, lease="Not A Lease").status == "bad-lease"


def _fake_bring_up(book: dict[str, str] | None, seen: list[dict[str, str]]):
    def ensure_stack(manifest: dict[str, Any], *, repo_root: str, logger: Any) -> dict[str, Any]:
        seen.append({key: os.environ.get(key, "") for key in (addresses.LEASE_ENV, addresses.BOOK_ENV)})
        if book is not None:
            addresses.write_book(Path(os.environ[addresses.BOOK_ENV]), book)
        return {"ready": "yes", "adopted": "no",
                "entry_url": stack_mod._url_now(manifest["entry_url"])}
    return ensure_stack


def test_a_per_run_bring_up_runs_under_its_lease_and_reports_the_addresses_it_left(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _per_run_book(tmp_path)
    seen: list[dict[str, str]] = []
    monkeypatch.setattr(rb.stack_mod, "ensure_stack",
                        _fake_bring_up({"gateway": "http://localhost:4321"}, seen))
    outcome = rb.cmd_stack_up(tmp_path, lease="story-1")
    assert outcome.ok, outcome.message
    assert seen[0][addresses.LEASE_ENV] == "story-1"
    assert seen[0][addresses.BOOK_ENV].endswith("lease-story-1.json")
    assert outcome.data["addresses"] == {"gateway": "http://localhost:4321"}
    assert outcome.data["entry_url"] == "http://localhost:4321"


def test_a_copy_that_leaves_no_book_is_not_ready(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _per_run_book(tmp_path)
    monkeypatch.setattr(rb.stack_mod, "ensure_stack", _fake_bring_up(None, []))
    outcome = rb.cmd_stack_up(tmp_path, lease="story-1")
    assert not outcome.ok and outcome.status == "address-book"
    assert "has not written it" in outcome.message


def test_a_book_missing_a_page_name_is_not_ready(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _per_run_book(tmp_path)
    monkeypatch.setattr(rb.stack_mod, "ensure_stack",
                        _fake_bring_up({"other": "http://localhost:1"}, []))
    outcome = rb.cmd_stack_up(tmp_path, lease="story-1")
    assert outcome.status == "address-book"
    assert "no address for `gateway`" in outcome.message


def test_a_shared_environment_writes_its_book_from_the_page(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".git").mkdir()
    _environment(tmp_path, sharing="shared", entries={"gateway": "http://localhost:3000/"})
    _runbook(tmp_path)
    seen: list[dict[str, str]] = []
    monkeypatch.setattr(rb.stack_mod, "ensure_stack", _fake_bring_up(None, seen))
    outcome = rb.cmd_stack_up(tmp_path)
    assert outcome.ok, outcome.message
    assert seen[0][addresses.BOOK_ENV].endswith("shared.json")
    assert outcome.data["entry_url"] == "http://localhost:3000"


def codes(root: Path) -> list[str]:
    return [fd.code for fd in doctor.run(model.load(root)).findings]


def test_the_doctor_takes_a_named_entry_url_and_its_named_gates(tmp_path: Path) -> None:
    _per_run_book(tmp_path)
    errors = [fd.code for fd in doctor.run(model.load(tmp_path)).findings if fd.severity == "error"]
    assert errors == []


def test_the_doctor_refuses_a_url_on_a_per_run_address(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _environment(tmp_path, sharing="per-run", entries={"gateway": "http://localhost:3000"})
    _runbook(tmp_path)
    assert "environment-address-value" in codes(tmp_path)


def test_the_doctor_asks_a_shared_address_for_its_url(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _environment(tmp_path, sharing="shared", entries={"gateway": "the front door"})
    _runbook(tmp_path)
    assert "environment-address-value" in codes(tmp_path)


def test_the_doctor_refuses_a_name_no_reference_can_spell(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _environment(tmp_path, sharing="per-run", entries={"Gateway": "the front door"})
    _runbook(tmp_path, entry_url="http://localhost:1", health="curl -fsS http://localhost:1")
    assert "environment-address-name" in codes(tmp_path)


def test_the_doctor_refuses_a_reference_the_environment_does_not_name(tmp_path: Path) -> None:
    _per_run_book(tmp_path)
    _runbook(tmp_path, health="curl -fsS {api}/health")
    assert codes(tmp_path).count("runbook-unknown-address") == 1


def test_a_named_entry_url_keeps_its_name_as_the_origin() -> None:
    assert reach.url_origin("{gateway}/app") == "{gateway}"
    assert reach.url_origin("http://localhost:3000/app") == "http://localhost:3000"


def test_a_plan_target_opens_the_runs_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert harness.resolve_addresses("{gateway}") == "{gateway}"
    where = tmp_path / "book.json"
    where.write_text(json.dumps({"gateway": "http://localhost:4321/"}))
    monkeypatch.setenv(harness.ADDRESS_BOOK_ENV, str(where))
    assert harness.resolve_addresses("{gateway}") == "http://localhost:4321"
    with pytest.raises(ValueError, match="does not give"):
        harness.resolve_addresses("{api}")

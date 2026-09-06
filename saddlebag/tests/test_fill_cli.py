"""``saddlebag fill`` and ``saddlebag totp`` at the CLI boundary.

The load-bearing assertion in this file is the negative one: whatever the command
prints, and whatever it logs, must not contain the value it typed. Everything else
here is the plumbing that gets a value to the browser.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path
from typing import Any

import pytest

from saddlebag import browser, cli, totp

RFC_SEED = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch: pytest.MonkeyPatch, store):
    monkeypatch.setattr(cli, "open_store", lambda backend=None: store)
    return store


@pytest.fixture(autouse=True)
def no_inferred_project(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cli, "infer_project", lambda: None)


class RecordingSession:
    """Stands in for the page's WebSocket. Reports a field that accepts everything."""

    last: "RecordingSession | None" = None

    def __init__(self, websocket_url: str) -> None:
        self.websocket_url = websocket_url
        self.typed: str | None = None
        self.closed = False
        RecordingSession.last = self

    def send(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "Input.insertText":
            self.typed = params["text"]
            return {}
        if "el.focus()" in params["expression"]:
            return {"result": {"value": {"found": True, "editable": True, "tag": "INPUT", "type": "password"}}}
        return {"result": {"value": len(self.typed or "")}}

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_browser(monkeypatch: pytest.MonkeyPatch):
    """One open page at the login URL, and a session that records what is typed."""
    pages = (
        browser.Target(id="a", url="https://github.com/login", title="", websocket_url="ws://127.0.0.1:9222/a"),
    )
    monkeypatch.setattr(browser, "list_targets", lambda endpoint: pages)
    monkeypatch.setattr(browser, "WebSocketSession", RecordingSession)
    RecordingSession.last = None
    return pages


@pytest.fixture
def run(db_path: Path, capsys, monkeypatch: pytest.MonkeyPatch):
    def _run(*argv: str, stdin: str | None = None) -> int:
        if stdin is not None:
            monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        capsys.readouterr()
        with pytest.raises(SystemExit) as exc:
            cli.main(["--db", str(db_path), *argv])
        code = exc.value.code
        assert isinstance(code, int)
        return code

    return _run


@pytest.fixture
def credential(run):
    assert run("add", "--username", "qa-bot", "--env", "prod", "--password-stdin", stdin="hunter2") == 0
    return "cred-001"


def out(capsys) -> str:
    return capsys.readouterr().out


# -- fill -------------------------------------------------------------------


def test_fills_the_password_into_the_named_selector(run, credential, fake_browser, capsys):
    assert run("fill", credential, "--selector", "#pw") == 0
    assert RecordingSession.last is not None
    assert RecordingSession.last.typed == "hunter2"


def test_the_password_is_absent_from_everything_the_command_prints(run, credential, fake_browser, capsys, caplog):
    """The opacity guarantee, asserted where it would actually be broken."""
    assert run("fill", credential, "--selector", "#pw", "--json") == 0
    captured = capsys.readouterr()
    assert "hunter2" not in captured.out
    assert "hunter2" not in captured.err
    assert "hunter2" not in caplog.text
    assert json.loads(captured.out)["characters"] == 7


def test_fills_the_username_without_touching_the_store(run, credential, fake_browser, store):
    """The username is metadata, not a secret — it comes from the pool row."""
    assert run("fill", credential, "--field", "username", "--selector", "#login") == 0
    assert RecordingSession.last is not None
    assert RecordingSession.last.typed == "qa-bot"


def test_the_session_is_closed_even_when_the_fill_fails(run, credential, monkeypatch, fake_browser):
    def explode(session, selector, value):
        raise browser.BrowserError("nothing matches")

    monkeypatch.setattr(browser, "fill", explode)
    assert run("fill", credential, "--selector", "#pw") == 1
    assert RecordingSession.last is not None
    assert RecordingSession.last.closed, "a leaked debugger socket keeps the page attached"


def test_an_unknown_credential_is_an_error(run, fake_browser):
    assert run("fill", "cred-404", "--selector", "#pw") == 1


def test_a_credential_whose_password_is_missing_from_the_store(run, credential, fake_browser, store):
    store.delete("cred-001")
    assert run("fill", credential, "--selector", "#pw") == 1


def test_a_browser_that_is_not_running_is_reported_not_raised(run, credential, monkeypatch):
    def refuse(endpoint: str):
        raise browser.BrowserError("no browser answering")

    monkeypatch.setattr(browser, "list_targets", refuse)
    assert run("fill", credential, "--selector", "#pw") == 1


# -- totp -------------------------------------------------------------------


def test_stores_a_seed_and_types_a_code_rather_than_the_seed(run, credential, fake_browser, capsys, caplog):
    assert run("totp", "set", credential, stdin=RFC_SEED) == 0
    assert run("fill", credential, "--field", "totp", "--selector", "#otp", "--min-seconds", "0") == 0

    assert RecordingSession.last is not None
    code = RecordingSession.last.typed
    assert code is not None
    assert code.isdigit() and len(code) == 6
    # Either side of a window boundary: the command computes its code microseconds
    # before the assertion does, and pinning to exactly one window makes this test
    # fail once every few thousand runs for no reason.
    now = time.time()
    assert code in {totp.code(RFC_SEED, now=now), totp.code(RFC_SEED, now=now - totp.PERIOD_SECONDS)}
    captured = capsys.readouterr()
    assert RFC_SEED not in captured.out + captured.err + caplog.text


def test_a_seed_that_is_not_base32_is_refused_at_the_point_it_is_stored(run, credential, store):
    """Rejecting it here is the difference between a typo and a login that stopped working."""
    assert run("totp", "set", credential, stdin="not base32 !!") == 2
    assert store.get("cred-001/totp") is None


def test_an_empty_seed_on_stdin_is_a_usage_error(run, credential, store):
    assert run("totp", "set", credential, stdin="   ") == 2
    assert store.get("cred-001/totp") is None


def test_filling_a_totp_without_a_seed_names_the_command_that_stores_one(run, credential, fake_browser, caplog):
    assert run("fill", credential, "--field", "totp", "--selector", "#otp") == 1
    assert "totp set" in caplog.text


def test_unset_forgets_the_seed(run, credential, store):
    assert run("totp", "set", credential, stdin=RFC_SEED) == 0
    assert run("totp", "unset", credential) == 0
    assert store.get("cred-001/totp") is None


def test_removing_a_credential_takes_its_seed_with_it(run, credential, store):
    """A seed outliving its credential would be adopted by the next one to mint the id."""
    assert run("totp", "set", credential, stdin=RFC_SEED) == 0
    assert run("remove", credential) == 0
    assert store.get("cred-001/totp") is None

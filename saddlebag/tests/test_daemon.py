"""Every verb over a real socket, against the dict-backed vault."""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from saddlebag import browser, daemon, protocol, totp, verbs
from saddlebag.models import Secret
from saddlebag.protocol import Reply, Request
from saddlebag.verbs import Verbs

from conftest import FakeVault, RecordingSession, Running

RFC_SEED = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
PASSWORD = "hunter2-pw"
LOCAL = ("environment=local",)


def seed(running: Running) -> None:
    running.vault.create(Secret("login", "gab", "Log in as a normal user", "LOGIN_PASSWORD", frozenset({("environment", "local")})))
    running.vault.set_value("login", "password", PASSWORD)
    running.vault.set_value("login", "totp", RFC_SEED)
    running.vault.create(Secret("other", None, "Another environment", "OTHER_PASSWORD", frozenset({("environment", "staging")})))
    running.vault.set_value("other", "password", "other-pw")


def ok(reply: Reply) -> dict[str, Any]:
    assert reply.ok, reply.error
    return reply.result


def test_ping_reports_the_version(running: Running) -> None:
    assert set(ok(running.ask("ping"))) == {"version"}


def test_list_returns_the_matching_secrets_without_values(running: Running) -> None:
    seed(running)
    result = ok(running.ask("list", tags=["environment=local"]))
    assert result == {
        "secrets": [
            {
                "name": "login",
                "username": "gab",
                "description": "Log in as a normal user",
                "var": "LOGIN_PASSWORD",
                "tags": [["environment", "local"]],
                "fields": ["password", "totp"],
            }
        ]
    }
    assert [s["name"] for s in ok(running.ask("list"))["secrets"]] == ["login", "other"]


def test_tags_returns_the_distinct_pairs_of_the_matches(running: Running) -> None:
    seed(running)
    assert ok(running.ask("tags")) == {"tags": [["environment", "local"], ["environment", "staging"]]}
    assert ok(running.ask("tags", tags=["environment=local"])) == {"tags": [["environment", "local"]]}


def test_create_stores_metadata_only_and_refuses_a_duplicate(running: Running) -> None:
    created = ok(running.ask("create", name="login", username="gab", description="d", var="LOGIN_PASSWORD", tags=["environment=local"]))
    assert created["secret"]["fields"] == []
    assert running.vault.metadata["login"].var == "LOGIN_PASSWORD"
    assert running.vault.data["login"] == {}
    again = running.ask("create", name="login")
    assert not again.ok and "already exists" in str(again.error)


@pytest.mark.parametrize(
    "args, message",
    [
        ({"name": "../escape"}, "invalid secret name"),
        ({"name": "x", "var": "1BAD"}, "invalid environment variable"),
        ({"name": "x", "tags": ["nonsense"]}, "key=value"),
    ],
)
def test_create_rejects_bad_input(running: Running, args: dict[str, object], message: str) -> None:
    reply = running.ask("create", **args)
    assert not reply.ok and message in str(reply.error)
    assert running.vault.names() == []


def test_set_stores_the_value_and_reports_its_length_only(running: Running) -> None:
    seed(running)
    reply = running.ask("set", name="login", field="password", value="a-new-password")
    assert reply.result == {"name": "login", "field": "password", "characters": 14}
    assert running.vault.data["login"]["password"] == "a-new-password"
    assert running.vault.data["login"]["totp"] == RFC_SEED


def test_set_refuses_a_totp_seed_that_is_not_base32(running: Running) -> None:
    seed(running)
    reply = running.ask("set", name="login", field="totp", value="not base32 !!")
    assert not reply.ok
    assert running.vault.data["login"]["totp"] == RFC_SEED


def test_set_refuses_the_username_field_and_an_unknown_secret(running: Running) -> None:
    seed(running)
    assert not running.ask("set", name="login", field="username", value="x").ok
    missing = running.ask("set", name="ghost", field="password", value="x")
    assert not missing.ok and "no such secret" in str(missing.error)


def test_unset_remove_tag_and_untag_change_the_vault(running: Running) -> None:
    seed(running)
    ok(running.ask("unset", name="login", field="totp"))
    assert "totp" not in running.vault.data["login"]
    ok(running.ask("tag", name="login", tags=["roles=admin"]))
    assert running.vault.metadata["login"].tags == {("environment", "local"), ("roles", "admin")}
    ok(running.ask("untag", name="login", tags=["roles=admin"]))
    assert running.vault.metadata["login"].tags == {("environment", "local")}
    ok(running.ask("remove", name="login"))
    assert running.vault.names() == ["other"]


def test_env_fills_each_tag_match_with_its_password(running: Running) -> None:
    seed(running)
    assert ok(running.ask("env", tags=["environment=local"])) == {"values": {"LOGIN_PASSWORD": PASSWORD}}


def test_env_binding_can_name_any_field(running: Running) -> None:
    seed(running)
    bindings = [
        {"var": "USER_NAME", "name": "login", "field": "username"},
        {"var": "SEED", "name": "login", "field": "totp"},
        {"var": "OTHER", "name": "other", "field": "password"},
    ]
    assert ok(running.ask("env", bindings=bindings)) == {
        "values": {"USER_NAME": "gab", "SEED": RFC_SEED, "OTHER": "other-pw"}
    }


def test_env_names_a_tag_match_that_has_no_var(running: Running) -> None:
    seed(running)
    running.vault.create(Secret("nameless", tags=frozenset({("environment", "local")})))
    reply = running.ask("env", tags=["environment=local"])
    assert not reply.ok
    assert "nameless" in str(reply.error)
    assert PASSWORD not in reply.to_json()


def test_env_refuses_a_tag_that_matches_nothing(running: Running) -> None:
    seed(running)
    reply = running.ask("env", tags=["environment=nowhere"])
    assert not reply.ok and "no secret carries" in str(reply.error)


def test_env_names_a_match_whose_password_is_missing(running: Running) -> None:
    seed(running)
    running.vault.unset_value("login", "password")
    reply = running.ask("env", tags=["environment=local"])
    assert not reply.ok and "login has no password" in str(reply.error)


def test_fill_types_the_value_and_reports_a_count(running: Running, fake_browser: tuple[browser.Target, ...]) -> None:
    seed(running)
    result = ok(running.ask("fill", name="login", field="password", selector="#pw", url_contains="github"))
    assert RecordingSession.last is not None
    assert RecordingSession.last.typed == PASSWORD
    assert RecordingSession.last.closed
    assert result == {
        "name": "login",
        "field": "password",
        "selector": "#pw",
        "characters": len(PASSWORD),
        "url": "https://github.com/login",
    }


def test_fill_types_the_username_from_metadata(running: Running, fake_browser: tuple[browser.Target, ...]) -> None:
    seed(running)
    ok(running.ask("fill", name="login", field="username", selector="#user"))
    assert RecordingSession.last is not None
    assert RecordingSession.last.typed == "gab"


def test_fill_types_a_code_and_never_the_seed(running: Running, fake_browser: tuple[browser.Target, ...]) -> None:
    seed(running)
    result = ok(running.ask("fill", name="login", field="totp", selector="#otp", min_seconds=0))
    assert RecordingSession.last is not None
    typed = RecordingSession.last.typed
    assert typed is not None and typed.isdigit() and len(typed) == 6
    now = time.time()
    assert typed in {totp.code(RFC_SEED, now=now), totp.code(RFC_SEED, now=now - totp.PERIOD_SECONDS)}
    assert "valid_for_seconds" in result


def test_fill_waits_out_a_code_that_is_about_to_expire(
    running: Running, fake_browser: tuple[browser.Target, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(running)
    slept: list[float] = []
    monkeypatch.setattr(verbs.time, "sleep", slept.append)
    monkeypatch.setattr(totp, "seconds_remaining", lambda **_: 2)
    ok(running.ask("fill", name="login", field="totp", selector="#otp", min_seconds=5))
    assert slept == [2]


def test_fill_closes_the_session_when_the_page_refuses(
    running: Running, fake_browser: tuple[browser.Target, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(running)

    def explode(session: object, selector: str, value: str) -> int:
        raise browser.BrowserError("nothing matches")

    monkeypatch.setattr(browser, "fill", explode)
    reply = running.ask("fill", name="login", field="password", selector="#pw")
    assert not reply.ok and "nothing matches" in str(reply.error)
    assert RecordingSession.last is not None and RecordingSession.last.closed


def test_fill_without_a_stored_totp_names_the_command_to_store_one(running: Running, fake_browser: tuple[browser.Target, ...]) -> None:
    seed(running)
    running.vault.unset_value("login", "totp")
    reply = running.ask("fill", name="login", field="totp", selector="#otp")
    assert not reply.ok and "saddlebag secret set login --field totp" in str(reply.error)


def test_doctor_reports_health_and_valueless_secrets(running: Running, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seed(running)
    running.vault.create(Secret("empty"))
    monkeypatch.setattr(verbs, "VAULT_TOKEN_FILE", tmp_path / "token")
    first = ok(running.ask("doctor"))
    assert first["route"].startswith("socket ")
    assert first["backend"] == "vault"
    assert first["orphan_items"] is None
    assert first["interpreter"] is None
    assert first["missing_items"] == []
    assert first["store_reachable"] is True
    assert first["vault_authenticated"] is True
    assert first["secrets_without_value"] == ["empty"]
    assert first["vault_token_file"] is False
    assert first["token_source"] is None
    (tmp_path / "token").write_text("x")
    running.vault.authenticated = False
    second = ok(running.ask("doctor"))
    assert second["store_reachable"] is False
    assert second["vault_authenticated"] is False
    assert second["secrets_without_value"] == []
    assert second["vault_token_file"] is True


def test_no_reply_except_env_carries_a_stored_value(running: Running, fake_browser: tuple[browser.Target, ...], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(verbs, "VAULT_TOKEN_FILE", Path("/nonexistent/token"))
    secret_value = "zz-distinctive-secret-zz"
    replies = [
        running.ask("create", name="login", username="gab", var="LOGIN_PASSWORD", tags=["environment=local"]),
        running.ask("set", name="login", field="password", value=secret_value),
        running.ask("set", name="login", field="totp", value=RFC_SEED),
        running.ask("list"),
        running.ask("tags"),
        running.ask("tag", name="login", tags=["roles=admin"]),
        running.ask("untag", name="login", tags=["roles=admin"]),
        running.ask("fill", name="login", field="password", selector="#pw"),
        running.ask("fill", name="login", field="totp", selector="#otp", min_seconds=0),
        running.ask("doctor"),
        running.ask("ping"),
        running.ask("set", name="ghost", field="password", value=secret_value),
        running.ask("set", name="login", field="totp", value=secret_value),
        running.ask("unset", name="login", field="totp"),
        running.ask("remove", name="login"),
    ]
    assert all(reply.ok for reply in replies[:11])
    for reply in replies:
        assert secret_value not in reply.to_json()
        assert RFC_SEED not in reply.to_json()
    running.ask("create", name="again", var="AGAIN")
    running.ask("set", name="again", field="password", value=secret_value)
    assert secret_value in running.ask("env", bindings=[{"var": "AGAIN", "name": "again", "field": "password"}]).to_json()


def test_the_daemon_logs_no_value(running: Running, fake_browser: tuple[browser.Target, ...], caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("DEBUG")
    running.ask("create", name="login", var="LOGIN_PASSWORD")
    running.ask("set", name="login", field="password", value=PASSWORD)
    running.ask("fill", name="login", field="password", selector="#pw")
    running.ask("env", bindings=[{"var": "X", "name": "login", "field": "password"}])
    assert PASSWORD not in caplog.text


def test_a_failing_handler_answers_with_its_type_and_the_loop_survives(running: Running, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> list[str]:
        raise RuntimeError(PASSWORD)

    monkeypatch.setattr(running.vault, "names", boom)
    reply = running.ask("list")
    assert not reply.ok
    assert PASSWORD not in reply.to_json()
    assert "RuntimeError" in str(reply.error)
    assert running.ask("ping").ok


def _raw(path: Path, payload: bytes) -> str:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(5)
        client.connect(str(path))
        client.sendall(payload)
        return protocol.read_message(client, limit=protocol.REPLY_LIMIT)


def test_a_malformed_request_is_answered_and_does_not_kill_the_loop(running: Running) -> None:
    for payload in (b"not json\n", b'["a list"]\n', b'{"verb": 3}\n', b'{"verb": "nope"}\n'):
        reply = Reply.from_json(_raw(running.path, payload))
        assert not reply.ok and reply.error
    assert running.ask("ping").ok


def test_an_oversized_request_is_refused_and_the_loop_survives(running: Running) -> None:
    reply = Reply.from_json(_raw(running.path, b"x" * (protocol.REQUEST_LIMIT + 10) + b"\n"))
    assert not reply.ok and "exceeded" in str(reply.error)
    assert running.ask("ping").ok


def test_the_socket_is_private_to_the_user(running: Running) -> None:
    assert running.path.stat().st_mode & 0o777 == 0o600


def test_a_live_daemon_is_not_replaced(running: Running, vault) -> None:
    with pytest.raises(OSError, match="already listening"):
        daemon.serve(vault, socket_path=running.path)
    assert running.ask("ping").ok


def test_a_stale_socket_file_is_rebound(vault, daemon_path: Path) -> None:
    dead = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    dead.bind(str(daemon_path))
    dead.close()
    assert daemon_path.exists()
    ready, stop = threading.Event(), threading.Event()
    thread = threading.Thread(target=daemon.serve, args=(vault,), kwargs={"socket_path": daemon_path, "ready": ready, "stop": stop})
    thread.start()
    try:
        assert ready.wait(5)
        assert protocol.send(Request("ping"), timeout=5).ok
    finally:
        stop.set()
        thread.join(timeout=5)
    assert not daemon_path.exists()


def test_a_socket_path_too_long_for_sun_path_falls_back_to_a_short_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    long = tmp_path / ("d" * 120) / "saddlebag.sock"
    monkeypatch.setenv("SADDLEBAG_SOCKET", str(long))
    chosen = protocol.socket_path()
    assert chosen != long
    assert len(str(chosen)) <= 100
    assert protocol.socket_path() == chosen


def test_the_socket_path_follows_xdg_runtime_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SADDLEBAG_SOCKET", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert protocol.socket_path() == tmp_path / "saddlebag.sock"


def test_send_reports_a_missing_daemon(daemon_path: Path) -> None:
    with pytest.raises(protocol.DaemonNotRunning, match="saddlebag serve"):
        protocol.send(Request("ping"), timeout=1)


def test_doctor_carries_the_token_source_the_daemon_was_given(vault: FakeVault) -> None:
    assert Verbs(vault, "http://127.0.0.1:9222", "socket x", "stdin").verb_doctor({})["token_source"] == "stdin"

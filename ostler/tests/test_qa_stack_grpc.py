from __future__ import annotations

import logging
import os
import stat
import sys
from pathlib import Path

import pytest

from ostler.qa import stack

LOG = logging.getLogger("test-stack-grpc")
SERVICE = "ticket.v1.TicketService"

FAKE = '''\
import os, sys

args = sys.argv[1:]
with open(os.environ["FAKE_GRPCURL_LOG"], "a") as sink:
    sink.write(" ".join(args) + "\\n")
mode = os.environ.get("FAKE_GRPCURL_MODE", "ok")
if mode == "down":
    print("Failed to dial target host", file=sys.stderr)
    sys.exit(1)
if args[-1] == "grpc.health.v1.Health/Check":
    print('{"status": "' + ("NOT_SERVING" if mode == "not-serving" else "SERVING") + '"}')
elif args[-1] == "list":
    print("grpc.health.v1.Health" if mode == "other" else "grpc.health.v1.Health\\n" + os.environ["FAKE_SERVICE"])
'''


@pytest.fixture
def fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path]:
    script = tmp_path / "grpcurl"
    script.write_text(f"#!{sys.executable}\n{FAKE}")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "calls.log"
    monkeypatch.setenv("FAKE_GRPCURL_LOG", str(log))
    monkeypatch.setenv("FAKE_SERVICE", SERVICE)
    return str(script), log


def test_an_http_url_is_probed_over_http_and_never_asks_grpcurl(
    fake: tuple[str, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    command, log = fake

    def refuse(*_a: object, **_kw: object) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr(stack.urllib.request, "urlopen", refuse)
    assert "is not answering" in stack.health_probe("http://127.0.0.1:1/", grpcurl=command)
    assert not log.exists()


def test_a_grpc_url_is_ready_when_serving_and_listing_every_service(fake: tuple[str, Path]) -> None:
    command, log = fake
    assert stack.health_probe("grpc://localhost:50051/", serves=(SERVICE,), grpcurl=command) == ""
    calls = log.read_text().splitlines()
    assert calls[0].endswith("localhost:50051 grpc.health.v1.Health/Check")
    assert calls[1].endswith("localhost:50051 list")
    assert all(call.startswith("-plaintext") for call in calls)


def test_a_grpc_url_not_serving_is_not_ready(fake: tuple[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    command, _ = fake
    monkeypatch.setenv("FAKE_GRPCURL_MODE", "not-serving")
    assert "not SERVING" in stack.health_probe("grpc://localhost:50051/", serves=(SERVICE,), grpcurl=command)


def test_a_grpc_url_that_does_not_answer_is_not_ready(fake: tuple[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    command, _ = fake
    monkeypatch.setenv("FAKE_GRPCURL_MODE", "down")
    assert "not answering" in stack.health_probe("grpc://localhost:50051/", grpcurl=command)


def test_a_different_server_on_the_port_is_named_by_the_service_it_lacks(
    fake: tuple[str, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    command, _ = fake
    monkeypatch.setenv("FAKE_GRPCURL_MODE", "other")
    why = stack.health_probe("grpc://localhost:50051/", serves=(SERVICE,), grpcurl=command)
    assert SERVICE in why
    assert "does not list" in why


def test_a_grpc_url_without_grpcurl_says_how_to_opt_in() -> None:
    assert "qa: {tools: [grpcurl]}" in stack.health_probe("grpc://localhost:50051/")


SECRET_VALUE = "tok-3f9a-do-not-leak"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TICKET_TOKEN", raising=False)


def _echo(value: str) -> str:
    return f"{sys.executable} -c \"print({value!r})\""


def test_a_recipe_is_run_once_and_its_stripped_output_is_the_value(monkeypatch: pytest.MonkeyPatch) -> None:
    assert stack.mint_secrets({"secrets": {"TICKET_TOKEN": _echo(SECRET_VALUE)}}, LOG) == ""
    assert os.environ["TICKET_TOKEN"] == SECRET_VALUE
    monkeypatch.delenv("TICKET_TOKEN")


def test_a_recipe_is_not_run_through_a_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    recipe = f"{sys.executable} -c \"import sys; print(*sys.argv[1:])\" a ; echo injected"
    assert stack.mint_secrets({"secrets": {"TICKET_TOKEN": recipe}}, LOG) == ""
    assert os.environ["TICKET_TOKEN"] == "a ; echo injected"
    monkeypatch.delenv("TICKET_TOKEN")


def test_a_failing_recipe_names_the_secret_and_the_status_and_never_the_output() -> None:
    recipe = f"{sys.executable} -c \"import sys; print('{SECRET_VALUE}'); sys.exit(7)\""
    why = stack.mint_secrets({"secrets": {"TICKET_TOKEN": recipe}}, LOG)
    assert "TICKET_TOKEN" in why
    assert "7" in why
    assert SECRET_VALUE not in why
    assert "TICKET_TOKEN" not in os.environ


def test_the_value_is_in_no_log_line(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger=LOG.name):
        stack.mint_secrets({"secrets": {"TICKET_TOKEN": _echo(SECRET_VALUE)}}, LOG)
    assert SECRET_VALUE not in caplog.text
    assert "TICKET_TOKEN" in caplog.text


def test_ensure_stack_fails_the_bring_up_when_a_recipe_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "")
    out = stack.ensure_stack(
        {"entry_url": "http://localhost:8080", "identity": "acme", "reuse": "always",
         "secrets": {"TICKET_TOKEN": f"{sys.executable} -c \"import sys; sys.exit(3)\""}},
        logger=LOG,
    )
    assert out["ready"] == "no"
    assert out["failed_step"] == "secrets"
    assert "TICKET_TOKEN" in out["error"]
    assert "3" in out["error"]


def test_ensure_stack_mints_after_the_stack_is_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stack, "health_probe", lambda *_a, **_kw: "")
    out = stack.ensure_stack(
        {"entry_url": "http://localhost:8080", "identity": "acme", "reuse": "always",
         "secrets": {"TICKET_TOKEN": _echo(SECRET_VALUE)}},
        logger=LOG,
    )
    assert out["ready"] == "yes"
    assert os.environ["TICKET_TOKEN"] == SECRET_VALUE
    assert SECRET_VALUE not in repr(out)
    monkeypatch.delenv("TICKET_TOKEN")

"""The PreToolUse guard: what it refuses, what it lets through and that every redirect passes itself."""

from __future__ import annotations

import io
import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from saddlebag import guard

Run = Callable[..., int]


def bash(command: str) -> dict[str, object]:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def tool(name: str, **tool_input: str) -> dict[str, object]:
    return {"tool_name": name, "tool_input": tool_input}


DENIED_PATHS = [".env", ".env.local", "secrets.env", "~/.aws/credentials", "id_rsa", "server.pem", "/home/u/.netrc", "/proc/self/environ", "/proc/12/environ", "x/.docker/config.json"]
ALLOWED_PATHS = [".env.example", ".env.sample", "app.env.template", "id_rsa.pub", "README.md", "credentials", "config.json"]

DENIED_COMMANDS = [
    "cat .env",
    "sed -n 1p .env",
    "source .env",
    ". ./.env",
    "set -a; . .env; set +a",
    "grep PASSWORD .env",
    "cat ~/.aws/credentials",
    "cat < .env",
    "sudo cat id_rsa",
    "echo hi && cat .env",
    "echo $(cat .env)",
    "printenv",
    "env",
    "env | grep X",
    "export -p",
    "export",
    "declare -p",
    "set",
    "aws secretsmanager get-secret-value --secret-id x",
    "aws ssm get-parameter --name x --with-decryption",
    "vault kv get secret/x",
    "gh auth token",
    "docker compose config",
    "kubectl get secret db -o yaml",
    "pass show site",
    "docker inspect web",
]

ALLOWED_COMMANDS = [
    "printenv HOME",
    "env FOO=1 ls",
    "ls -la .env",
    "rm .env",
    "git add .env",
    "cp .env.example .env",
    "openssl rand -hex 24 | saddlebag secret set x",
    "aws secretsmanager get-secret-value --secret-id x | saddlebag secret set x",
    "saddlebag exec --tag environment=local -- docker compose config",
    "saddlebag env show .env",
    "saddlebag env keys .env",
    "set -e",
    "set -euo pipefail",
    "export FOO=bar",
    "git commit -m 'fix; printenv'",
    "pass ls",
    "aws ssm get-parameter --name x",
]


@pytest.mark.parametrize("path", DENIED_PATHS)
def test_read_of_a_protected_path_is_denied(path: str) -> None:
    verdict = guard.decide(tool("Read", file_path=path))
    assert not verdict.allowed and verdict.reason


@pytest.mark.parametrize("path", ALLOWED_PATHS)
def test_read_of_an_ordinary_path_is_allowed(path: str) -> None:
    assert guard.decide(tool("Read", file_path=path)).allowed


def test_grep_and_write_tools_are_checked_by_their_path() -> None:
    assert not guard.decide(tool("Grep", path=".env")).allowed
    assert not guard.decide(tool("Write", file_path=".env")).allowed
    assert not guard.decide(tool("Edit", file_path=".env")).allowed
    assert not guard.decide(tool("MultiEdit", file_path=".env")).allowed


@pytest.mark.parametrize("payload", [None, [], "x", {}, {"tool_name": "Read"}, {"tool_name": "Read", "tool_input": []}, {"tool_name": "Read", "tool_input": {"file_path": 3}}, tool("WebFetch", url=".env"), bash("")])
def test_an_unknown_tool_or_garbage_payload_is_allowed(payload: object) -> None:
    assert guard.decide(payload).allowed


@pytest.mark.parametrize("command", DENIED_COMMANDS)
def test_a_revealing_command_is_denied(command: str) -> None:
    verdict = guard.decide(bash(command))
    assert not verdict.allowed and verdict.reason


@pytest.mark.parametrize("command", ALLOWED_COMMANDS)
def test_an_ordinary_command_is_allowed(command: str) -> None:
    assert guard.decide(bash(command)).allowed


def test_known_hole_a_path_inside_a_quoted_program_is_allowed() -> None:
    assert guard.decide(bash("python -c \"print(open('.env').read())\"")).allowed


def alternatives(reason: str) -> list[str]:
    found = re.findall(r"`([^`]+)`", reason)
    return [text for text in found if "saddlebag" in text or text == "printenv HOME"]


def concrete(alternative: str) -> str:
    return re.sub(r"<command>", "true", re.sub(r"\bVAR\b", "X", re.sub(r"\bNAME\b", "x", alternative)))


REDIRECTS = [
    (payload, alt)
    for payload in [
        *(tool("Read", file_path=path) for path in DENIED_PATHS),
        *(bash(command) for command in DENIED_COMMANDS),
    ]
    for alt in alternatives(guard.decide(payload).reason)
]


@pytest.mark.parametrize(
    ("payload", "alternative"),
    REDIRECTS,
    ids=[f"{json.dumps(payload['tool_input'])}->{alt}" for payload, alt in REDIRECTS],
)
def test_every_redirect_passes_the_guard(payload: dict[str, object], alternative: str) -> None:
    assert guard.decide(bash(concrete(alternative))).allowed


def test_every_denial_names_at_least_one_alternative() -> None:
    payloads = [tool("Read", file_path=path) for path in DENIED_PATHS] + [bash(command) for command in DENIED_COMMANDS]
    for payload in payloads:
        assert alternatives(guard.decide(payload).reason), payload


def test_hook_prints_the_deny_decision_and_returns_zero() -> None:
    out = io.StringIO()
    assert guard.hook(io.StringIO(json.dumps(bash("cat .env"))), out) == 0
    lines = out.getvalue().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": guard.decide(bash("cat .env")).reason,
        }
    }


def test_hook_prints_nothing_when_allowing() -> None:
    out = io.StringIO()
    assert guard.hook(io.StringIO(json.dumps(bash("ls"))), out) == 0
    assert out.getvalue() == ""


def test_hook_ignores_malformed_input() -> None:
    out = io.StringIO()
    assert guard.hook(io.StringIO("not json"), out) == 0
    assert out.getvalue() == ""


def test_the_hook_flag_runs_through_the_cli(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from saddlebag import cli

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(bash("printenv"))))
    with pytest.raises(SystemExit) as exc:
        cli.main(["guard", "--hook"])
    assert exc.value.code == 0
    assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"] == "deny"


COMMAND = "/usr/bin/saddlebag guard --hook"


def test_install_writes_the_entry_into_an_empty_file(tmp_path: Path) -> None:
    path = guard.install("user", tmp_path / ".claude" / "settings.json", COMMAND)
    assert json.loads(path.read_text()) == {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Read|Grep|Bash",
                    "hooks": [{"type": "command", "command": COMMAND, "timeout": 5, "statusMessage": "saddlebag guard"}],
                }
            ]
        }
    }
    assert path.read_text().endswith("}\n")


def test_install_keeps_other_keys_and_entries(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    other = {"matcher": "Write", "hooks": [{"type": "command", "command": "x"}]}
    path.write_text(json.dumps({"model": "opus", "hooks": {"PreToolUse": [other], "Stop": [{"hooks": []}]}}))
    guard.install("user", path, COMMAND)
    settings = json.loads(path.read_text())
    assert settings["model"] == "opus"
    assert settings["hooks"]["Stop"] == [{"hooks": []}]
    assert settings["hooks"]["PreToolUse"][0] == other
    assert len(settings["hooks"]["PreToolUse"]) == 2


def test_install_twice_does_not_duplicate_and_replaces_in_place(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    guard.install("user", path, "/old/saddlebag guard --hook")
    other = {"matcher": "Write", "hooks": []}
    settings = json.loads(path.read_text())
    settings["hooks"]["PreToolUse"].append(other)
    path.write_text(json.dumps(settings))
    guard.install("user", path, COMMAND)
    guard.install("user", path, COMMAND)
    entries = json.loads(path.read_text())["hooks"]["PreToolUse"]
    assert len(entries) == 2
    assert entries[0]["hooks"][0]["command"] == COMMAND
    assert entries[1] == other


def test_install_project_scope_writes_under_the_working_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    path = guard.install("project", command=COMMAND)
    assert path == tmp_path / ".claude" / "settings.json"
    assert path.exists()


def test_the_install_command_writes_the_user_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert run("guard", "install", "--user") == 0
    target = tmp_path / ".claude" / "settings.json"
    assert f"installed PreToolUse guard in {target}" in capsys.readouterr().out
    command = json.loads(target.read_text())["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert command.endswith("guard --hook")


def test_the_install_command_needs_a_scope(run: Run) -> None:
    assert run("guard", "install") == 2


@pytest.fixture(autouse=True)
def no_daemon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "absent.sock"
    monkeypatch.setenv("SADDLEBAG_SOCKET", str(path))
    return path


def answer_with(monkeypatch: pytest.MonkeyPatch, no_daemon: Path, *, held: bool, names: list[str]) -> list[str]:
    from saddlebag import protocol

    asked: list[str] = []

    def send(request: protocol.Request, *, timeout: float = 0) -> protocol.Reply:
        asked.append(request.args["text"])
        return protocol.Reply(True, {"held": held, "names": names})

    no_daemon.touch()
    monkeypatch.setattr(protocol, "send", send)
    return asked


def test_a_command_without_a_candidate_token_never_asks_custody(monkeypatch: pytest.MonkeyPatch) -> None:
    from saddlebag import protocol

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("custody was asked")

    monkeypatch.setattr(protocol, "send", refuse)
    assert guard.decide(bash("echo hello world; ls -la src 12345 abcdefgh")).allowed


def test_a_held_value_in_the_command_is_denied(monkeypatch: pytest.MonkeyPatch, no_daemon: Path) -> None:
    asked = answer_with(monkeypatch, no_daemon, held=True, names=["qa_admin", "other"])
    verdict = guard.decide(bash("echo correct-horse-9f3k2m"))
    assert not verdict.allowed
    assert verdict.reason == guard.PASTED_MESSAGE.format(names="qa_admin, other", name="qa_admin")
    assert asked == ["echo correct-horse-9f3k2m"]


def test_a_candidate_that_custody_does_not_hold_is_allowed(monkeypatch: pytest.MonkeyPatch, no_daemon: Path) -> None:
    answer_with(monkeypatch, no_daemon, held=False, names=[])
    assert guard.decide(bash("echo correct-horse-9f3k2m")).allowed


def test_a_held_value_in_a_heredoc_body_is_denied(monkeypatch: pytest.MonkeyPatch, no_daemon: Path) -> None:
    answer_with(monkeypatch, no_daemon, held=True, names=["qa_admin"])
    assert not guard.decide(bash("cat <<EOF\ncorrect-horse-9f3k2m\nEOF")).allowed


def test_no_daemon_allows_and_says_the_command_was_not_checked(capsys: pytest.CaptureFixture[str]) -> None:
    assert guard.decide(bash("echo correct-horse-9f3k2m")).allowed
    assert guard.UNREACHABLE_NOTE in capsys.readouterr().err


def test_a_refusing_daemon_allows(monkeypatch: pytest.MonkeyPatch, no_daemon: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from saddlebag import protocol

    def down(request: protocol.Request, *, timeout: float = 0) -> protocol.Reply:
        raise protocol.DaemonNotRunning("down")

    no_daemon.touch()
    monkeypatch.setattr(protocol, "send", down)
    assert guard.decide(bash("echo correct-horse-9f3k2m")).allowed
    assert guard.UNREACHABLE_NOTE in capsys.readouterr().err


def test_intake_through_secret_set_is_not_checked(monkeypatch: pytest.MonkeyPatch, no_daemon: Path) -> None:
    asked = answer_with(monkeypatch, no_daemon, held=True, names=["x"])
    assert guard.decide(bash("printf 'hunter2hunter2' | saddlebag secret set x")).allowed
    assert asked == []


def test_exec_is_not_checked(monkeypatch: pytest.MonkeyPatch, no_daemon: Path) -> None:
    asked = answer_with(monkeypatch, no_daemon, held=True, names=["x"])
    assert guard.decide(bash("saddlebag exec --env A=x -- echo 9f3k2m9f3k2m")).allowed
    assert asked == []


@pytest.mark.parametrize(
    "text",
    ["abcdefg1", "sk-abcdefgh", "ghp_abcdefgh", "xoxb-abcdefg", "glpat-abcdefg", "echo 'abc' 'defghijk1'"],
)
def test_candidate_tokens(text: str) -> None:
    assert guard._candidates(text)


@pytest.mark.parametrize("text", ["abcdefgh", "12345678", "abc123", "ls -la src/long-name", "echo (hello) $(world)"])
def test_non_candidate_tokens(text: str) -> None:
    assert not guard._candidates(text)


HEREDOC_FIXTURE = """python3 - <<'EOF'
t = t.replace("| `set` reads its value |", "...")
EOF"""


@pytest.mark.parametrize(
    "command",
    [
        HEREDOC_FIXTURE,
        "cat <<EOF\nset\nEOF",
        "cat <<-EOF\n\tset\n\tEOF",
        "cat <<A <<B\nset\nA\nprintenv\nB",
        "echo '`set`'",
        "cat <<< `echo hi`",
    ],
)
def test_heredoc_bodies_and_single_quoted_backticks_are_not_commands(command: str) -> None:
    assert guard.decide(bash(command)).allowed


@pytest.mark.parametrize(
    "command",
    [
        "cat <<EOF\nbody\nEOF\nprintenv",
        'echo "`set`"',
        "echo 'a' `set`",
        "cat <<EOF >out\nx\nEOF\nset",
    ],
)
def test_a_real_stage_after_a_heredoc_or_in_double_quotes_is_still_denied(command: str) -> None:
    assert not guard.decide(bash(command)).allowed


def test_the_pasted_value_redirect_passes_the_guard() -> None:
    found = alternatives(guard.PASTED_MESSAGE.format(names="qa_admin", name="qa_admin"))
    assert found
    assert all(guard.decide(bash(concrete(alt))).allowed for alt in found)
    assert guard.decide(bash("saddlebag exec --env VAR=qa_admin -- true")).allowed

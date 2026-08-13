"""The sandbox's host-side halves: config, path identity, the env allowlist, the gateway.

Nothing here starts a container. What these cover is the part that decides *what* a
container would be told — which is where a mistake is silent rather than loud: a leaked
`GITHUB_TOKEN` and a translated path both produce a run that appears to work.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ostler.qa.drivers import DriverBlocked, PythonDriver
from ostler.qa.gateway import Gateway, Verb
from ostler.qa.sandbox import (
    CONTAINER_HOME,
    Sandbox,
    SandboxConfig,
    _read_records,
)
from ostler.qa.session import QaSession

STACK = """\
sandbox:
  network: acme_default
  forward:
    8090: api-service:8090
    5173: host-gateway:5173
  images:
    base: acme-qa:base
  gateway:
    allow:
      - verb: device-screenshot
        argv: ["adb", "exec-out", "screencap"]
"""


def _repo(tmp_path: Path, stack: str | None = STACK) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs/specs/story-1").mkdir(parents=True)
    if stack is not None:
        (repo / "qa-stack.yml").write_text(stack, encoding="utf-8")
    return repo


def _sandbox(repo: Path, *, config: SandboxConfig | None = None) -> Sandbox:
    spec = repo / "docs/specs/story-1"
    session = QaSession.create(
        spec,
        "qa-sandbox-1",
        "story-1",
        {"BASE_URL": "http://localhost:8090"},
        secret_values={"API_TOKEN": "s3cret"},
        qa_dirname="qa-sandbox",
    )
    return Sandbox(config or SandboxConfig.load(repo), session=session, root=repo)


# -- configuration ------------------------------------------------------------------------


def test_config_reads_the_repositorys_stack_file(tmp_path: Path) -> None:
    config = SandboxConfig.load(_repo(tmp_path))
    assert config.network == "acme_default"
    assert config.forward == {8090: "api-service:8090", 5173: "host-gateway:5173"}
    assert config.base_image == "acme-qa:base"
    assert config.gateway_allow == (
        Verb(name="device-screenshot", argv=("adb", "exec-out", "screencap")),
    )


def test_config_without_a_stack_file_forwards_nothing_and_allows_nothing(tmp_path: Path) -> None:
    config = SandboxConfig.load(_repo(tmp_path, stack=None))
    assert config.network == ""
    assert config.forward == {}
    assert config.gateway_allow == ()


def test_a_forward_entry_without_a_port_is_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path, stack="sandbox:\n  forward:\n    8090: api-service\n")
    with pytest.raises(DriverBlocked, match="must be `host:port`"):
        SandboxConfig.load(repo)


def test_a_gateway_verb_without_an_argv_is_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path, stack="sandbox:\n  gateway:\n    allow:\n      - verb: nope\n")
    with pytest.raises(DriverBlocked, match="needs `verb` and `argv`"):
        SandboxConfig.load(repo)


# -- path identity ------------------------------------------------------------------------


def test_the_spec_directory_mounts_at_its_own_absolute_path(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    sandbox = _sandbox(repo)
    argv = sandbox.mount_argv()
    spec = str((repo / "docs/specs/story-1").resolve())
    assert ["-v", f"{spec}:{spec}"] == argv[argv.index("-v") : argv.index("-v") + 2]
    # The repository root itself is empty in there: that absence is the whole enforcement.
    assert argv[:2] == ["--tmpfs", str(repo.resolve())]
    assert "--tmpfs" in argv and CONTAINER_HOME in argv
    assert argv[-2:] == ["-w", str(repo.resolve())]


def test_containers_run_as_the_invoking_user(tmp_path: Path) -> None:
    argv = _sandbox(_repo(tmp_path)).base_argv("c")
    assert "--user" in argv
    assert argv[argv.index("--user") + 1].count(":") == 1


def test_a_spec_directory_at_the_repository_root_is_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    session = QaSession.create(repo, "qa-sandbox-2", "story-1", {}, qa_dirname="qa-sandbox")
    sandbox = Sandbox(SandboxConfig(), session=session, root=repo)
    with pytest.raises(DriverBlocked, match="below the repository root"):
        sandbox.start()


# -- the environment allowlist ------------------------------------------------------------


def test_the_container_environment_is_built_from_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "leak-me")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example.com:3128")
    repo = _repo(tmp_path)
    sandbox = _sandbox(repo)
    launcher = sandbox.launcher_for("api", {"driver": "python"})
    driver = PythonDriver(
        sandbox.session, "api", {"driver": "python"}, root=repo, variables={}, launcher=launcher
    )

    env = launcher._env(driver, sandbox.session.qa_dir / "records/s.ndjson")

    assert "GITHUB_TOKEN" not in env
    assert "HTTPS_PROXY" not in env
    # Declared `env:` and declared secrets do cross, the latter keyed by the secret's own
    # name — which is what the harness reads, not the host variable it came from.
    assert env["BASE_URL"] == "http://localhost:8090"
    assert env["API_TOKEN"] == "s3cret"
    assert env["OSTLER_QA_RECORD_PATH"].endswith("records/s.ndjson")
    assert env["OSTLER_QA_GATEWAY_TOKEN"] == sandbox.gateway.token
    assert json.loads(env["OSTLER_SANDBOX_FORWARD"]) == {
        "8090": "api-service:8090",
        "5173": "host-gateway:5173",
    }


def test_secrets_travel_by_file_not_by_argv(tmp_path: Path) -> None:
    sandbox = _sandbox(_repo(tmp_path))
    path = sandbox.write_env_file("scenario-1", {"API_TOKEN": "s3cret"})
    assert path.read_text(encoding="utf-8").strip() == "API_TOKEN=s3cret"
    assert path.stat().st_mode & 0o777 == 0o600


def test_a_newline_in_a_value_is_refused_rather_than_truncated(tmp_path: Path) -> None:
    sandbox = _sandbox(_repo(tmp_path))
    with pytest.raises(DriverBlocked, match="newline"):
        sandbox.write_env_file("scenario-1", {"KEY": "line\nmore"})


# -- records ------------------------------------------------------------------------------


def test_a_truncated_last_record_costs_only_itself(tmp_path: Path) -> None:
    path = tmp_path / "records.ndjson"
    path.write_text('{"type": "step"}\n{"type": "asse', encoding="utf-8")
    assert _read_records(path) == [{"type": "step"}]


def test_a_scenario_that_wrote_nothing_reads_as_no_records(tmp_path: Path) -> None:
    assert _read_records(tmp_path / "absent.ndjson") == []


# -- the gateway --------------------------------------------------------------------------


def _gateway(tmp_path: Path, allow: list[Verb]) -> Gateway:
    repo = _repo(tmp_path)
    spec = repo / "docs/specs/story-1"
    session = QaSession.create(spec, "qa-gw-1", "story-1", {}, qa_dirname="qa-sandbox")
    return Gateway(session, repo, allow)


def _ledger(gateway: Gateway) -> list[dict]:
    log = gateway.session.qa_dir / "qa-run.ndjson"
    return [
        record
        for record in (json.loads(line) for line in log.read_text(encoding="utf-8").splitlines())
        if record.get("kind") == "gateway"
    ]


def test_an_undeclared_verb_is_refused_with_a_reason(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path, [])
    status, body = gateway.execute({"verb": "go-test", "args": ["./..."]})
    assert status == 403
    assert "allows nothing on the host" in body["error"]


def test_every_request_lands_in_the_ledger_including_the_refused_one(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path, [Verb(name="echo", argv=("echo",))])
    gateway.execute({"verb": "npx"})
    gateway.execute({"verb": "echo", "args": ["hello"]})
    decisions = [(record["verb"], record["decision"]) for record in _ledger(gateway)]
    assert ("npx", "denied") in decisions
    assert ("echo", "allowed") in decisions


def test_an_allowed_verb_cannot_be_turned_into_a_different_command(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path, [Verb(name="echo", argv=("echo", "fixed"))])
    status, body = gateway.execute({"verb": "echo", "args": ["extra"]})
    assert status == 200
    # The declared argv is a prefix, never a suggestion: arguments append, they do not
    # replace, so a verb cannot be steered into being a shell.
    assert body["stdout"].strip() == "fixed extra"


def test_args_must_be_strings(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path, [Verb(name="echo", argv=("echo",))])
    status, _ = gateway.execute({"verb": "echo", "args": [{"cmd": "rm"}]})
    assert status == 400

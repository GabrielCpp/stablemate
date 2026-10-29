"""`ostler env import-dotenv`: literals onto the page, secrets into saddlebag, no value in any output."""

from __future__ import annotations

import io
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from ostler.environments import commands, migrate

from conftest import write
from test_environment_variables import FIXTURE, PAGE

GITHUB = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"
STRIPE = "sk-live-abcdefghijklmnop"
DATABASE = "postgres://qa:pw@localhost/db"
SECRET_VALUES = (GITHUB, STRIPE, DATABASE, "pw@")

DOTENV = f"""# local settings
APP_HOST=localhost

export APP_PORT=8080
GITHUB_TOKEN={GITHUB}
LOG_LEVEL='debug'
STRIPE_KEY={STRIPE}
DATABASE_URL={DATABASE}
FEATURE_FLAGS=a,b # trailing note
API_URL=http://localhost:9000
"""

VERDICTS: list[tuple[str, str | None]] = [
    ("APP_HOST", None),
    ("APP_PORT", None),
    ("GITHUB_TOKEN", "key-name"),
    ("LOG_LEVEL", None),
    ("STRIPE_KEY", "token-shape"),
    ("DATABASE_URL", "url-userinfo"),
    ("FEATURE_FLAGS", None),
    ("API_URL", None),
]

EXPECTED_LINES = [
    "APP_HOST=localhost",
    "APP_PORT=8080",
    "GITHUB_TOKEN=",
    "LOG_LEVEL=debug",
    "STRIPE_KEY=",
    "DATABASE_URL=",
    "FEATURE_FLAGS=a,b",
    "API_URL=http://localhost:9000",
]

BARE = """---
type: environment
slug: local
title: Local
---
# Local

- selector: the developer's machine
- local-only: true
"""


class FakeSaddlebag:
    def __init__(self, verdicts: list[tuple[str, str | None]] = VERDICTS,
                 records: list[dict[str, str]] | None = None, import_status: int = 0) -> None:
        self.verdicts = verdicts
        self.records = records or []
        self.import_status = import_status
        self.calls: list[list[str]] = []

    def __call__(self, argv: Sequence[str], *, capture: bool,
                 stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(argv))
        args = list(argv)
        if args[1:3] == ["env", "classify"]:
            body = {"file": args[3], "verdicts": [
                {"key": key, "secret": rule is not None, "rule": rule} for key, rule in self.verdicts]}
            return subprocess.CompletedProcess(args, 0, json.dumps(body), "")
        if args[1] == "list":
            return subprocess.CompletedProcess(args, 0, json.dumps({"secrets": self.records}), "")
        keys = args[args.index("--keys") + 1].split(",")
        prefix = args[args.index("--prefix") + 1]
        if self.import_status:
            return subprocess.CompletedProcess(args, self.import_status, "", "saddlebag: daemon down")
        lines = "".join(f"stored {k} as {prefix}{k.lower().replace('_', '-')}\n" for k in keys)
        return subprocess.CompletedProcess(args, 0, lines, "")

    @property
    def imports(self) -> list[list[str]]:
        return [call for call in self.calls if call[1:3] == ["env", "import"]]


def _book(root: Path, text: str = BARE) -> Path:
    (root / ".git").mkdir(parents=True, exist_ok=True)
    write(root / PAGE, text)
    write(root / ".env.source", DOTENV)
    return root


def _run(root: Path, saddlebag: FakeSaddlebag) -> tuple[commands.EnvOutcome, str]:
    out = io.StringIO()
    outcome = migrate.cmd_import_dotenv(root, root / ".env.source", "local", runner=saddlebag, out=out)
    return outcome, out.getvalue()


def test_the_page_gains_the_literals_and_the_secret_marks_in_file_order(tmp_path: Path) -> None:
    root = _book(tmp_path)
    outcome, diff = _run(root, FakeSaddlebag())
    assert outcome.ok, outcome.message
    page_text = (root / PAGE).read_text()
    assert page_text.split("- variables:\n")[1].splitlines()[:8] == [
        "  - APP_HOST: localhost",
        "  - APP_PORT: 8080",
        "  - GITHUB_TOKEN: secret",
        "  - LOG_LEVEL: debug",
        "  - STRIPE_KEY: secret",
        "  - DATABASE_URL: secret",
        "  - FEATURE_FLAGS: a,b",
        "  - API_URL: http://localhost:9000",
    ]
    assert page_text.endswith("- local-only: true\n- variables:\n" + "".join(
        line + "\n" for line in page_text.split("- variables:\n")[1].splitlines()))
    assert diff.count("\n+  - ") == 8
    assert diff.count(": secret") == 3
    assert diff.startswith("--- a/")


def test_the_import_names_exactly_the_secret_keys_with_the_tag_and_prefix(tmp_path: Path) -> None:
    saddlebag = FakeSaddlebag()
    _run(_book(tmp_path), saddlebag)
    assert saddlebag.imports == [[
        "saddlebag", "env", "import", str(tmp_path / ".env.source"),
        "--keys", "GITHUB_TOKEN,STRIPE_KEY,DATABASE_URL",
        "--tag", "environment=local", "--prefix", "local-"]]


def test_the_report_counts_the_lines_and_relays_the_stored_names(tmp_path: Path) -> None:
    outcome, _ = _run(_book(tmp_path), FakeSaddlebag())
    assert outcome.message.splitlines() == [
        "8 lines: 3 held, 5 literal",
        "stored GITHUB_TOKEN as local-github-token",
        "stored STRIPE_KEY as local-stripe-key",
        "stored DATABASE_URL as local-database-url",
        f"next: review the diff above and commit {PAGE.as_posix()}; `ostler env dotenv local` "
        "writes the file back when a tool still wants one",
    ]
    assert outcome.data == {
        "ok": True, "page": str(tmp_path / PAGE), "lines": 8, "held": 3, "literal": 5,
        "imported": ["GITHUB_TOKEN", "STRIPE_KEY", "DATABASE_URL"], "already_held": []}


def test_no_secret_value_reaches_the_output_or_the_message(tmp_path: Path) -> None:
    root = _book(tmp_path)
    outcome, diff = _run(root, FakeSaddlebag())
    shown = diff + outcome.message + json.dumps(outcome.data) + (root / PAGE).read_text()
    for value in SECRET_VALUES:
        assert value not in shown


def test_a_page_with_variables_keeps_unrelated_entries_and_replaces_the_same_names(tmp_path: Path) -> None:
    root = _book(tmp_path, FIXTURE)
    outcome, _ = _run(root, FakeSaddlebag())
    assert outcome.ok, outcome.message
    text = (root / PAGE).read_text()
    assert text.count("- variables:") == 1
    assert text.endswith("- local-only: true\n")
    block = text.split("- variables:\n")[1].split("- local-only")[0].splitlines()
    assert block == [
        "  - API_URL: http://localhost:9000",
        "  - LOG_LEVEL: debug",
        "  - FEATURE_FLAGS: a,b",
        "  - DATABASE_URL: secret",
        "  - STRIPE_KEY: secret",
        "  - APP_HOST: localhost",
        "  - APP_PORT: 8080",
        "  - GITHUB_TOKEN: secret",
    ]


def test_a_var_a_record_already_holds_is_skipped_and_reported(tmp_path: Path) -> None:
    saddlebag = FakeSaddlebag(records=[{"name": "local-stripe-key", "var": "STRIPE_KEY"}])
    outcome, _ = _run(_book(tmp_path), saddlebag)
    assert outcome.ok, outcome.message
    assert saddlebag.imports[0][saddlebag.imports[0].index("--keys") + 1] == "GITHUB_TOKEN,DATABASE_URL"
    assert outcome.message.splitlines()[:2] == ["8 lines: 3 held, 5 literal", "1 already held"]
    assert outcome.data["already_held"] == ["STRIPE_KEY"]
    assert "STRIPE_KEY: secret" in (tmp_path / PAGE).read_text()


def test_nothing_to_import_runs_no_import(tmp_path: Path) -> None:
    saddlebag = FakeSaddlebag(verdicts=[("APP_HOST", None)])
    outcome, _ = _run(_book(tmp_path), saddlebag)
    assert outcome.ok and saddlebag.imports == []
    assert outcome.message.splitlines()[0] == "1 lines: 0 held, 1 literal"


def test_a_failed_import_says_the_page_was_written(tmp_path: Path) -> None:
    root = _book(tmp_path)
    outcome, _ = _run(root, FakeSaddlebag(import_status=1))
    assert not outcome.ok
    assert "after the page was written" in outcome.message
    assert "saddlebag: daemon down" in outcome.message
    assert "DATABASE_URL: secret" in (root / PAGE).read_text()


def test_a_literal_key_ostler_cannot_read_stops_before_any_write(tmp_path: Path) -> None:
    root = _book(tmp_path)
    outcome, _ = _run(root, FakeSaddlebag(verdicts=[("GHOST", None)]))
    assert not outcome.ok and "GHOST" in outcome.message
    assert (root / PAGE).read_text() == BARE


def test_a_literal_whose_value_is_the_held_mark_stops_before_any_write(tmp_path: Path) -> None:
    root = _book(tmp_path)
    write(root / ".env.source", "MODE=secret\n")
    outcome, _ = _run(root, FakeSaddlebag(verdicts=[("MODE", None)]))
    assert not outcome.ok and "MODE" in outcome.message
    assert (root / PAGE).read_text() == BARE


def test_an_unknown_environment_fails_with_one_line(tmp_path: Path) -> None:
    root = _book(tmp_path)
    outcome = migrate.cmd_import_dotenv(root, root / ".env.source", "nowhere", runner=FakeSaddlebag())
    assert not outcome.ok and "nowhere" in outcome.message


def test_the_dotenv_command_writes_the_eight_assignments_back_with_secrets_blank(tmp_path: Path) -> None:
    root = _book(tmp_path)
    assert _run(root, FakeSaddlebag())[0].ok
    assert commands.cmd_dotenv(root, "local").ok
    assert (root / ".env").read_text().splitlines()[1:] == EXPECTED_LINES


def test_the_root_parser_routes_import_dotenv(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    from ostler.cli import _build_parser
    from ostler.environments import cli as env_cli

    seen: list[tuple[Path, Path, str]] = []

    def fake(root: Path, file: Path, token: str) -> commands.EnvOutcome:
        seen.append((root, file, token))
        return commands.EnvOutcome(True, "8 lines: 3 held, 5 literal", {})

    monkeypatch.setattr(migrate, "cmd_import_dotenv", fake)
    args = _build_parser().parse_args(["env", "import-dotenv", ".env", "--environment", "local"])
    assert args.env_op == "import-dotenv" and args.environment == "local"
    assert env_cli.run(args, tmp_path) == 0
    assert seen == [(tmp_path, Path(".env"), "local")]
    assert capsys.readouterr().out == "8 lines: 3 held, 5 literal\n"


def test_the_root_parser_requires_the_environment() -> None:
    from ostler.cli import _build_parser

    with pytest.raises(SystemExit):
        _build_parser().parse_args(["env", "import-dotenv", ".env"])

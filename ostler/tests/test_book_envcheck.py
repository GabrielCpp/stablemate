"""Environment-independence check for books: hardcoded cloud resources, UUIDs, ULIDs and non-reserved URLs fail check."""

from __future__ import annotations

from collections.abc import Iterator
import importlib
import sys
from pathlib import Path

import pytest

from ostler.book.check import check
from ostler.book.envcheck import environment_faults

CLEAN_SERVICE = """\
from datetime import date

from ostler.book import Action, Answer, Axes, Documentation, Endpoint, Environment, Object, Scene, Service, State, Transaction

DOCS = "https://docs.acme.io/orders"
DEV_API = "https://api.acme.io"
LOCAL = Environment("local", {"api": "http://127.0.0.1:8080"})
DEV = Environment("dev", {"api": DEV_API})


class CheckUp(Action[object, State]):
    source = ("https://docs.acme.io/orders#ping",)

    @staticmethod
    def reduce(a: object, s: State, by: object) -> Transaction:
        return Transaction(says=({},))


class Ping(Endpoint):
    \"\"\"Docstrings may mention 55768f04-9986-4c21-b3cb-a1531412266c or arn:aws:s3:::docs-example.\"\"\"

    does = "Check that the service is up."
    method = "GET"
    path = "/ping"
    answers = (Answer(200, Object("Pong"), "up"),)
    carries = CheckUp
    source = ("https://docs.acme.io/orders#ping",)


AXES = Axes(
    "Pong",
    today=date(2026, 1, 1),
    state_of=lambda *_: "up",
    told_apart=lambda _: "up",
    scenes=(Scene("up", "ready", lambda _: ()),),
    actions={"ping": lambda _: Ping()},
)

service = Service(
    "orders",
    new_model=State,
    journeys=(),
    stack=lambda _: None,
    surface=lambda env: None,
    environments={"local": LOCAL, "dev": DEV},
    default_environment="local",
    documentation=Documentation(sites=(DOCS,)),
    endpoints=(Ping,),
    matrices=(AXES,),
)
"""


def _write_book(root: Path, name: str, service_code: str, extra: dict[str, str] | None = None) -> str:
    pkg = root / "services" / name
    pkg.mkdir(parents=True, exist_ok=True)
    (root / "services" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "service.py").write_text(service_code, encoding="utf-8")
    for rel, text in (extra or {}).items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return f"services.{name}"


@pytest.fixture()
def book_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    saved = {
        name: sys.modules.pop(name)
        for name in list(sys.modules)
        if name == "services" or name.startswith("services.")
    }
    try:
        yield tmp_path
    finally:
        for name in list(sys.modules):
            if name == "services" or name.startswith("services."):
                sys.modules.pop(name, None)
        sys.modules.update(saved)


def test_clean_book_with_environment_and_documentation_urls_passes(book_workspace: Path) -> None:
    module = _write_book(book_workspace, "orders", CLEAN_SERVICE)
    service = importlib.import_module(f"{module}.service").service
    assert environment_faults(module) == []
    assert [f for f in check(service, module) if not f.told] == []


@pytest.mark.parametrize(
    ("snippet", "expected"),
    [
        ('ARN = "arn:aws:events:us-east-2:123456789012:event-bus/orders-dev"\n', "hardcodes AWS ARN"),
        ('SECRET = f"arn:aws:secretsmanager:{region}:123456789012:secret:orders"\n', "hardcodes AWS ARN"),
        ('BUCKET = "s3://acme-orders-dev/uploads/clip.mp4"\n', "hardcodes cloud storage URI"),
        ('QUEUE = "https://sqs.us-east-2.amazonaws.com/123456789012/orders"\n', "hardcodes AWS resource endpoint"),
        ('VPC = "vpc-0a1b2c3d4e5f60718"\n', "hardcodes AWS resource id"),
        ('INSTANCE = "i-0123456789abcdef0"\n', "hardcodes AWS resource id"),
        ('KEY_ID = "AKIAIOSFODNN7EXAMPLE"\n', "hardcodes AWS access key id"),
        ('FACILITY_ID = "55768f04-9986-4c21-b3cb-a1531412266c"\n', "hardcodes UUID"),
        ('UNIT_ID = "01G8BR5S2Z15GZCQBN0B7YRD31"\n', "hardcodes ULID"),
        ('GATEWAY = "https://gateway.dev.acme.io/v1"\n', "hardcodes URL"),
        ('DYNAMIC = f"https://{tenant}.portal.acme.io/api"\n', "hardcodes URL"),
        ('CDN = "d111111abcdef8.cloudfront.net"\n', "hardcodes cloud endpoint"),
    ],
)
def test_hardcoded_identifiers_and_cloud_resources_fail_check(
    book_workspace: Path,
    snippet: str,
    expected: str,
) -> None:
    extra = {"services/orders/fixtures.py": "region = 'us-east-2'\ntenant = 'acme'\n" + snippet}
    code = "from . import fixtures\n" + CLEAN_SERVICE
    module = _write_book(book_workspace, "orders", code, extra=extra)
    service = importlib.import_module(f"{module}.service").service
    faults = check(service, module)
    matching = [f for f in faults if expected in f.problem]
    assert matching, f"expected {expected!r} in {[str(f) for f in faults]}"
    assert all(f.blocks and not f.told for f in matching)
    assert any(f.name.startswith("services/orders/fixtures.py:") for f in matching)


def test_shared_outside_helper_imported_by_book_is_checked(book_workspace: Path) -> None:
    extra = {
        "services/shared/__init__.py": "",
        "services/shared/places.py": 'MAIN_SITE = "e121039c-9206-4f70-8419-45e104ba2798"\n',
    }
    code = "from services.shared import places\n" + CLEAN_SERVICE
    module = _write_book(book_workspace, "orders", code, extra=extra)
    faults = environment_faults(module)
    assert len(faults) == 1
    assert faults[0].name == "services/shared/places.py:1"
    assert "hardcodes UUID" in faults[0].problem


def test_reserved_loopback_and_example_urls_in_fixtures_are_allowed(book_workspace: Path) -> None:
    extra = {
        "services/orders/fixtures.py": (
            'LOOPBACK = "http://127.0.0.1:9000/callback"\n'
            'LOCALHOST = "http://localhost:3000/callback"\n'
            'SYNTHETIC = "https://orders.example.com/webhook"\n'
            'TEST_HOST = "http://gateway.local/health"\n'
        ),
    }
    code = "from . import fixtures\n" + CLEAN_SERVICE
    module = _write_book(book_workspace, "orders", code, extra=extra)
    assert environment_faults(module) == []


def test_aws_arn_or_uuid_inside_environment_still_fails(book_workspace: Path) -> None:
    bad = CLEAN_SERVICE.replace(
        'LOCAL = Environment("local", {"api": "http://127.0.0.1:8080"})',
        'LOCAL = Environment("local", {"api": "http://127.0.0.1:8080", "bus": "arn:aws:events:us-east-2:123456789012:event-bus/dev"})',
    )
    module = _write_book(book_workspace, "orders", bad)
    faults = environment_faults(module)
    assert len(faults) == 1
    assert "hardcodes AWS ARN" in faults[0].problem

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest
import yaml

from ostler import doctor
from ostler.environments import commands, leases, runtime, spec
from ostler.environments import render as render_mod
from ostler.model import load
from ostler.qa import addresses, runbook

FEATURES = Path("docs/features")


@pytest.fixture(autouse=True)
def _env_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "env-home"
    monkeypatch.setenv(runtime.HOME_ENV, str(home))
    monkeypatch.delenv(addresses.LEASE_ENV, raising=False)
    return home


def _file(root: Path, relative: str, text: str) -> Path:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "acme"
    (root / ".git").mkdir(parents=True)
    api = f"{FEATURES}/api"
    _file(root, f"{api}/ops/services/db.yml.j2", "\n".join([
        "image: mysql:8.0",
        "volumes:",
        "  - data:/var/lib/mysql",
        "{% for f in fixtures %}",
        "  - {{ f.path }}:/docker-entrypoint-initdb.d/{{ loop.index }}-{{ f.name }}:ro",
        "{% endfor %}",
        "healthcheck:",
        "  test: [CMD, mysqladmin, ping]",
        "",
    ]))
    _file(root, f"{api}/ops/services/provision.yml.j2", "image: pulumi/pulumi\n")
    _file(root, f"{api}/ops/services/api.yml.j2",
          "build: {{ repo }}/api-service\nenvironment:\n  DB_HOST: {{ service('db') }}\n")
    _file(root, f"{api}/ops/fixtures/schema.sql", "create table t (id int);\n")
    _file(root, f"{api}/ops/fixtures/users.sql", "insert into t values (1);\n")
    _file(root, f"{api}/stack.yml", yaml.safe_dump({
        "default-fixtures": ["schema"],
        "services": {
            "db": {"about": "the database", "define": "ops/services/db.yml.j2",
                   "fixtures": {"schema": ["ops/fixtures/schema.sql"],
                                "users": ["ops/fixtures/users.sql"]}},
            "provision": {"define": "ops/services/provision.yml.j2", "once": True},
            "api": {"define": "ops/services/api.yml.j2", "needs": ["db", "provision"],
                    "address": "api", "port": 8080},
        },
    }))
    web = f"{FEATURES}/web"
    _file(root, f"{web}/ops/services/web.yml.j2", "build: {{ repo }}/web-app\n")
    _file(root, f"{web}/ops/services/gateway.yml.j2",
          "image: caddy:2\nvolumes:\n  - {{ dir }}/Caddyfile:/etc/caddy/Caddyfile:ro\n")
    _file(root, f"{web}/ops/services/Caddyfile.j2",
          ":80 {\n  reverse_proxy /api/* {{ service('api:api') }}:8080\n}\n")
    _file(root, f"{web}/stack.yml", yaml.safe_dump({
        "services": {
            "web": {"define": "ops/services/web.yml.j2", "needs": ["api:api", "api:provision"]},
            "gateway": {"define": "ops/services/gateway.yml.j2",
                        "render": ["ops/services/Caddyfile.j2"], "needs": ["web"],
                        "address": "gateway", "port": 80, "host-port": 8443},
        },
    }))
    return root


def _rewrite_stack(root: Path, book: str, change: dict) -> None:
    target = root / FEATURES / book / spec.STACK_FILE
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    data["services"].update(change)
    target.write_text(yaml.safe_dump(data), encoding="utf-8")


def test_a_service_two_books_need_comes_up_once_and_before_both(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    catalog = spec.load(root)
    assert catalog.errors == []
    order = [service.ref for service in spec.closure(catalog, ["web"])]
    assert order == ["api:db", "api:provision", "api:api", "web:web", "web:gateway"]


def test_one_service_names_only_what_it_needs(tmp_path: Path) -> None:
    catalog = spec.load(_repo(tmp_path))
    assert [service.ref for service in spec.closure(catalog, ["api:api"])] == [
        "api:db", "api:provision", "api:api"]


def test_two_books_defining_the_same_template_is_refused(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _rewrite_stack(root, "web", {"provision": {"define": "../api/ops/services/provision.yml.j2"}})
    errors = spec.load(root).errors
    assert any("web:provision and api:provision are both defined" in error for error in errors) \
        or any("api:provision and web:provision are both defined" in error for error in errors)


def test_a_need_no_book_defines_is_refused(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _rewrite_stack(root, "web", {"web": {"define": "ops/services/web.yml.j2",
                                         "needs": ["api:queue"]}})
    assert "web:web needs `api:queue`, which no book defines" in spec.load(root).errors


def test_needs_that_loop_are_refused(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _rewrite_stack(root, "api", {"db": {"define": "ops/services/db.yml.j2", "needs": ["api"]}})
    assert any("cycle" in error for error in spec.load(root).errors)


def test_a_service_named_twice_in_one_file_is_refused(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    target = root / FEATURES / "web" / spec.STACK_FILE
    target.write_text(target.read_text(encoding="utf-8")
                      + "  web:\n    define: ops/services/web.yml.j2\n", encoding="utf-8")
    assert any("`web` is defined twice" in error for error in spec.load(root).errors)


def test_a_misspelt_key_and_a_port_less_address_are_refused(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _rewrite_stack(root, "web", {"web": {"define": "ops/services/web.yml.j2", "need": ["x"],
                                         "address": "site"}})
    errors = spec.load(root).errors
    assert any("`need` is not a service key" in error for error in errors)
    assert any("publishes `site` but names no `port:`" in error for error in errors)


def test_doctor_reports_each_stack_problem_on_the_file_it_was_found_in(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert not [f for f in doctor.run(load(root)).findings if f.code == "stack-invalid"]
    _rewrite_stack(root, "web", {"web": {"define": "ops/services/web.yml.j2", "need": ["x"],
                                         "needs": ["api:queue"]}})
    found = [(f.path, f.message) for f in doctor.run(load(root)).findings
             if f.code == "stack-invalid"]
    assert any(path == "docs/features/web/stack.yml"
               and message.startswith("service `web`: `need` is not a service key")
               for path, message in found)
    assert ("", "web:web needs `api:queue`, which no book defines") in found


def test_the_render_names_orders_and_publishes_each_service(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    outcome = commands.cmd_render(root, ["web"], copy_name="story-1")
    assert outcome.ok, outcome.message
    directory = Path(outcome.data["directory"])
    compose = yaml.safe_load((directory / render_mod.COMPOSE_FILE).read_text(encoding="utf-8"))
    services = compose["services"]
    assert compose["name"] == "acme-story-1"
    assert list(services) == ["api-db", "api-provision", "api-api", "web-web", "web-gateway"]
    assert services["api-api"]["depends_on"] == {
        "api-db": {"condition": "service_healthy"},
        "api-provision": {"condition": "service_completed_successfully"},
    }
    assert services["web-gateway"]["depends_on"] == {"web-web": {"condition": "service_started"}}
    assert services["web-gateway"]["ports"] == ["127.0.0.1::80"]
    assert services["api-api"]["environment"] == {"DB_HOST": "api-db"}
    assert services["api-db"]["volumes"][0] == "api-db-data:/var/lib/mysql"
    assert services["api-db"]["volumes"][1].endswith("schema.sql:/docker-entrypoint-initdb.d/"
                                                     "1-schema.sql:ro")
    assert "api-db-data" in compose["volumes"]
    caddyfile = (directory / "web-gateway" / "Caddyfile").read_text(encoding="utf-8")
    assert "reverse_proxy /api/* api-api:8080" in caddyfile


def test_the_shared_copy_keeps_its_fixed_port_and_a_run_copy_takes_any(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    shared = commands.cmd_render(root, ["web"])
    compose = yaml.safe_load(
        (Path(shared.data["directory"]) / render_mod.COMPOSE_FILE).read_text(encoding="utf-8"))
    assert compose["services"]["web-gateway"]["ports"] == ["127.0.0.1:8443:80"]
    assert compose["services"]["api-api"]["ports"] == ["127.0.0.1::8080"]


def test_a_chosen_fixture_set_replaces_the_defaults(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    outcome = commands.cmd_render(root, ["api"], copy_name="c1", fixtures=["schema", "users"])
    compose = yaml.safe_load(
        (Path(outcome.data["directory"]) / render_mod.COMPOSE_FILE).read_text(encoding="utf-8"))
    mounts = compose["services"]["api-db"]["volumes"]
    assert [mount.rsplit("/", 1)[-1] for mount in mounts[1:]] == ["1-schema.sql:ro",
                                                                 "2-users.sql:ro"]
    unknown = commands.cmd_render(root, ["api"], copy_name="c1", fixtures=["seed"])
    assert not unknown.ok
    assert "`seed`" in unknown.message


def test_a_template_that_sets_its_own_ports_is_refused(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _file(root, f"{FEATURES}/web/ops/services/web.yml.j2", "image: web\nports: ['3000:3000']\n")
    outcome = commands.cmd_render(root, ["web"])
    assert not outcome.ok
    assert "`ports`" in outcome.message


def test_the_book_you_stand_in_is_the_default_target(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    outcome = commands.cmd_render(root, copy_name="c2", cwd=root / FEATURES / "api" / "ops")
    assert outcome.data["services"] == ["api:db", "api:provision", "api:api"]


class FakeDocker:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv: Sequence[str], *, capture: bool) -> subprocess.CompletedProcess[str]:
        args = list(argv)
        self.calls.append(args)
        stdout = ""
        if "port" in args:
            stdout = {"80": "127.0.0.1:49200\n", "8080": "127.0.0.1:49201\n"}[args[-1]]
        if args[:3] == ["docker", "compose", "ls"]:
            stdout = '[{"Name": "acme-story-1", "Status": "running(5)"}]'
        return subprocess.CompletedProcess(args, 0, stdout, "")


def test_up_writes_the_address_book_from_the_published_ports(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    docker = FakeDocker()
    outcome = commands.cmd_up(root, ["web"], copy_name="story-1", runner=docker)
    assert outcome.ok, outcome.message
    assert outcome.data["addresses"] == {"api": "http://localhost:49201",
                                         "gateway": "http://localhost:49200"}
    assert addresses.read_book(Path(outcome.data["address_book"]))["gateway"] == \
        "http://localhost:49200"
    up = next(call for call in docker.calls if "up" in call)
    assert up[up.index("--project-name") + 1] == "acme-story-1"
    assert commands.cmd_address(root, "gateway", copy_name="story-1").message == \
        "http://localhost:49200"
    listing = commands.cmd_ls(root, runner=docker)
    assert [(row["copy"], row["status"]) for row in listing.data["copies"]] == [
        ("story-1", "running(5)")]


def test_down_removes_the_copy_and_drops_its_data_unless_kept(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    docker = FakeDocker()
    up = commands.cmd_up(root, ["web"], copy_name="story-1", runner=docker)
    outcome = commands.cmd_down(root, copy_name="story-1", runner=docker)
    assert outcome.ok
    assert "--volumes" in docker.calls[-1]
    assert not Path(up.data["directory"]).exists()
    kept = commands.cmd_up(root, ["web"], copy_name="story-1", runner=docker)
    (Path(kept.data["directory"]) / runtime.SECRETS_DIR).mkdir()
    commands.cmd_down(root, copy_name="story-1", keep_data=True, runner=docker)
    assert "--volumes" not in docker.calls[-1]
    assert not (Path(kept.data["directory"]) / runtime.SECRETS_DIR).exists()
    assert [copy.name for copy in runtime.copies(root)] == ["story-1"]
    commands.cmd_down(root, copy_name="story-1", runner=docker)
    assert "--volumes" in docker.calls[-1]
    assert runtime.copies(root) == []


def test_a_copy_name_that_cannot_name_containers_is_refused(tmp_path: Path) -> None:
    outcome = commands.cmd_render(_repo(tmp_path), ["web"], copy_name="Story 1")
    assert not outcome.ok
    assert "cannot name a copy" in outcome.message


def test_a_run_copy_comes_up_under_its_lease_and_names_the_front_service(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    outcome = leases.up(root, lease="story-1", near=root / FEATURES / "web", runner=FakeDocker())
    assert outcome is not None and outcome.ok, outcome
    assert outcome.data["entry_url"] == "http://localhost:49200"
    assert outcome.data["lease"] == "story-1"
    assert leases.run_env(root, "story-1") == {
        addresses.LEASE_ENV: "story-1",
        addresses.BOOK_ENV: outcome.data["address_book"],
    }
    down = leases.down(root, lease="story-1", runner=FakeDocker())
    assert down is not None and down.ok
    assert runtime.copies(root) == []


def test_the_book_near_the_run_is_the_only_one_brought_up(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert leases.books_near(root, root / FEATURES / "api" / "ops") == ["api"]
    assert leases.books_near(root) == ["api", "web"]
    assert leases.books_near(root, tmp_path) == []


def test_a_repo_with_no_stack_file_keeps_the_runbook_path(tmp_path: Path) -> None:
    root = tmp_path / "globex"
    (root / FEATURES).mkdir(parents=True)
    assert leases.up(root, lease="story-1") is None
    assert leases.down(root, lease="story-1") is None
    assert leases.run_env(root, "story-1") is None


def test_qa_stack_brings_a_stack_file_up_and_a_named_runbook_keeps_its_path(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _rewrite_stack(root, "web", {"web": {"define": "ops/services/missing.yml.j2"}})
    refused = runbook.cmd_stack_up(root, lease="story-1")
    assert not refused.ok
    assert "do not fit together" in refused.message
    named = runbook.cmd_stack_up(root, name="links-local", lease="story-1")
    assert "do not fit together" not in named.message
    assert runbook.cmd_stack_down(root, lease="story-1").message == "stack torn down"

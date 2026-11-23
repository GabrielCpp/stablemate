from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NoReturn

import pytest
import yaml

from ostler._vendor.stablemate_core import config as core_config
from ostler.environments import checkout, cli, commands, leases, runtime, secrets, spec
from ostler.environments import render as render_mod
from ostler.qa import addresses

SERVICES = Path("services")


@pytest.fixture(autouse=True)
def _env_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "env-home"
    monkeypatch.setenv(runtime.HOME_ENV, str(home))
    monkeypatch.delenv(addresses.LEASE_ENV, raising=False)
    monkeypatch.delenv(runtime.HOLDER_ENV, raising=False)
    monkeypatch.setattr(runtime, "port_free", lambda port: True)
    return home


def _file(root: Path, relative: str, text: str) -> Path:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "acme"
    (root / ".git").mkdir(parents=True)
    api = f"{SERVICES}/api"
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
    _file(root, f"{api}/ops/stack.yml", yaml.safe_dump({
        "default-fixtures": ["schema"],
        "services": {
            "db": {"about": "the database", "define": "services/db.yml.j2",
                   "fixtures": {"schema": ["fixtures/schema.sql"],
                                "users": ["fixtures/users.sql"]}},
            "provision": {"about": "creates the schema", "define": "services/provision.yml.j2",
                          "once": True},
            "api": {"about": "the HTTP API", "define": "services/api.yml.j2",
                    "needs": ["db", "provision"], "address": "api", "port": 8080},
        },
    }))
    web = f"{SERVICES}/web"
    _file(root, f"{web}/ops/services/web.yml.j2", "build: {{ repo }}/web-app\n")
    _file(root, f"{web}/ops/services/gateway.yml.j2",
          "image: caddy:2\nvolumes:\n  - {{ dir }}/Caddyfile:/etc/caddy/Caddyfile:ro\n")
    _file(root, f"{web}/ops/services/Caddyfile.j2",
          ":80 {\n  reverse_proxy /api/* {{ service('api:api') }}:8080\n}\n")
    _file(root, f"{web}/ops/stack.yml", yaml.safe_dump({
        "services": {
            "web": {"about": "the browser app", "define": "services/web.yml.j2",
                    "needs": ["api:api", "api:provision"]},
            "gateway": {"about": "the proxy a browser opens",
                        "define": "services/gateway.yml.j2",
                        "files": {"Caddyfile": "services/Caddyfile.j2"}, "needs": ["web"],
                        "address": "gateway", "port": 80, "host-port": 8443},
        },
    }))
    return root


def _rewrite_stack(root: Path, book: str, change: dict) -> None:
    target = root / SERVICES / book / spec.OPS_DIR / spec.STACK_FILE
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
    _rewrite_stack(root, "web", {"provision": {"about": "x", "define": "../../api/ops/services/provision.yml.j2"}})
    errors = spec.load(root).errors
    assert any("web:provision and api:provision are both defined" in error for error in errors) \
        or any("api:provision and web:provision are both defined" in error for error in errors)


def test_a_need_no_book_defines_is_refused(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _rewrite_stack(root, "web", {"web": {"about": "x", "define": "services/web.yml.j2",
                                         "needs": ["api:queue"]}})
    assert "web:web needs `api:queue`, which no book defines" in spec.load(root).errors


def test_needs_that_loop_are_refused(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _rewrite_stack(root, "api", {"db": {"about": "x", "define": "services/db.yml.j2", "needs": ["api"]}})
    assert any("cycle" in error for error in spec.load(root).errors)


def test_a_service_named_twice_in_one_file_is_refused(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    target = root / SERVICES / "web" / spec.OPS_DIR / spec.STACK_FILE
    target.write_text(target.read_text(encoding="utf-8")
                      + "  web:\n    about: x\n    define: services/web.yml.j2\n", encoding="utf-8")
    assert any("`web` is defined twice" in error for error in spec.load(root).errors)


def test_a_misspelt_key_and_a_port_less_address_are_refused(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _rewrite_stack(root, "web", {"web": {"about": "x", "define": "services/web.yml.j2", "need": ["x"],
                                         "address": "site"}})
    errors = spec.load(root).errors
    assert any("`need` is not a service key" in error for error in errors)
    assert any("publishes `site` but names no `port:`" in error for error in errors)


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


def test_a_stack_template_in_the_artifacts_folder_reaches_a_member_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = tmp_path / "code" / "todo-api"
    member.mkdir(parents=True)
    config = tmp_path / "home.toml"
    config.write_text(f'[workspaces]\ntodo = ["{member}"]\n')
    monkeypatch.setenv(core_config.CONFIG_PATH_ENV, str(config))
    root = tmp_path / "artifacts"
    (root / ".git").mkdir(parents=True)
    _file(root, "services/api/ops/services/api.yml.j2", 'build: {{ repos["todo-api"] }}\n')
    _file(root, "services/api/ops/stack.yml", yaml.safe_dump({
        "services": {"api": {"about": "the HTTP API", "define": "services/api.yml.j2", "address": "api", "port": 8080}},
    }))
    outcome = commands.cmd_render(root, ["api"], copy_name="story-1")
    assert outcome.ok, outcome.message
    compose = yaml.safe_load((Path(outcome.data["directory"]) / render_mod.COMPOSE_FILE).read_text(encoding="utf-8"))
    assert compose["services"]["api-api"]["build"] == str(member)


def _lone_trees(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    code = _real_repo(tmp_path / "code" / "todo-api")
    artifacts = _real_repo(tmp_path / "artifacts")
    config = tmp_path / "home.toml"
    config.write_text("")
    monkeypatch.setenv(core_config.CONFIG_PATH_ENV, str(config))
    monkeypatch.setenv(core_config.ARTIFACTS_DIR_ENV, str(artifacts))
    _file(artifacts, "services/todo-api/api/ops/services/api.yml.j2", 'build: {{ repos["todo-api"] }}\n')
    _file(artifacts, "services/todo-api/api/ops/stack.yml", yaml.safe_dump({
        "services": {"api": {"about": "the HTTP API", "define": "services/api.yml.j2", "address": "api", "port": 8080}},
    }))
    return artifacts, code


def test_render_names_the_lone_repository_in_repos_when_given_its_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts, code = _lone_trees(tmp_path, monkeypatch)
    outcome = commands.cmd_render(artifacts, ["api"], copy_name="story-1", code=code)
    assert outcome.ok, outcome.message
    compose = yaml.safe_load((Path(outcome.data["directory"]) / render_mod.COMPOSE_FILE).read_text(encoding="utf-8"))
    assert compose["services"]["api-api"]["build"] == str(code)


def test_render_without_code_keeps_the_workspace_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts, _ = _lone_trees(tmp_path, monkeypatch)
    outcome = commands.cmd_render(artifacts, ["api"], copy_name="story-1")
    assert not outcome.ok
    assert "todo-api" in outcome.message


def _real_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    for args in (["init", "--quiet", "-b", "main"], ["commit", "--quiet", "--allow-empty", "-m", "x"]):
        subprocess.run(["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                       check=True, capture_output=True)
    return path.resolve()


def _run_trees(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    member = _real_repo(tmp_path / "code" / "todo-api")
    artifacts = _real_repo(tmp_path / "artifacts")
    config = tmp_path / "home.toml"
    config.write_text(f'[workspaces]\ntodo = ["{member}"]\n')
    monkeypatch.setenv(core_config.CONFIG_PATH_ENV, str(config))
    monkeypatch.setenv(core_config.ARTIFACTS_DIR_ENV, str(artifacts))
    trees = []
    for name, repo in (("artifacts", artifacts), ("todo-api", member)):
        target = tmp_path / "trees" / f"{name}-run-t"
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "--quiet", "-b", "run/t", str(target)],
                       check=True, capture_output=True)
        trees.append(target.resolve())
    return artifacts, trees[0], trees[1]


def _api_stack(root: Path) -> None:
    _file(root, "services/todo-api/api/ops/services/api.yml.j2", 'build: {{ repos["todo-api"] }}\n')
    _file(root, "services/todo-api/api/ops/stack.yml", yaml.safe_dump({
        "services": {"api": {"about": "the HTTP API", "define": "services/api.yml.j2", "address": "api", "port": 8080}},
    }))


def test_a_stack_template_rendered_from_an_artifacts_worktree_reaches_the_member_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, book, member = _run_trees(tmp_path, monkeypatch)
    _api_stack(book)
    outcome = commands.cmd_render(book, ["api"], copy_name="story-1")
    assert outcome.ok, outcome.message
    compose = yaml.safe_load((Path(outcome.data["directory"]) / render_mod.COMPOSE_FILE).read_text(encoding="utf-8"))
    assert compose["services"]["api-api"]["build"] == str(member)


def test_env_from_a_member_worktree_reads_the_stacks_of_the_artifacts_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _, book, member = _run_trees(tmp_path, monkeypatch)
    _api_stack(book)
    from ostler import cli as ostler_cli
    assert ostler_cli.main(["-C", str(member), "env", "check", "--json"]) == 0
    assert "api:api" in json.loads(capsys.readouterr().out)["services"]


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


def test_a_service_that_loads_no_fixture_sees_the_sets_the_bring_up_loads(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _file(root, f"{SERVICES}/web/ops/services/web.yml.j2",
          "build: {{ repo }}/web-app\nenvironment:\n  SETS: \"{{ fixture_sets | join(',') }}\"\n")

    def sets(fixtures: tuple[str, ...]) -> str:
        outcome = commands.cmd_render(root, ["web"], copy_name="c1", fixtures=fixtures)
        compose = yaml.safe_load(
            (Path(outcome.data["directory"]) / render_mod.COMPOSE_FILE).read_text(encoding="utf-8"))
        return compose["services"]["web-web"]["environment"]["SETS"]

    assert sets(()) == "schema"
    assert sets(("users", "schema")) == "users,schema"


def _docs_book(root: Path) -> None:
    _file(root, f"{SERVICES}/docs/ops/services/docs.yml.j2", "build: {{ repo }}/docs-app\n")
    _file(root, f"{SERVICES}/docs/ops/stack.yml", yaml.safe_dump({
        "services": {"docs": {"about": "the docs app", "define": "services/docs.yml.j2",
                              "needs": ["api:api"], "address": "docs", "port": 5173}},
    }))


def test_an_up_that_names_one_book_keeps_the_services_of_the_others(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _docs_book(root)
    commands.cmd_render(root, ["web"], copy_name="c1", fixtures=["users", "schema"])
    outcome = commands.cmd_render(root, ["docs"], copy_name="c1")
    assert outcome.data["services"] == [
        "api:db", "api:provision", "api:api", "web:web", "web:gateway", "docs:docs"]
    assert outcome.data["fixtures"] == ["users", "schema"]


def test_an_up_that_names_one_service_keeps_the_other_services_of_its_book(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _docs_book(root)
    commands.cmd_render(root, ["web"], copy_name="c1")
    commands.cmd_render(root, ["docs"], copy_name="c1")
    rebuilt = commands.cmd_render(root, ["web:web"], copy_name="c1")
    assert "web:gateway" in rebuilt.data["services"]
    assert "docs:docs" in rebuilt.data["services"]


def test_an_up_that_names_one_service_of_a_book_the_copy_lacks_adds_that_service_alone(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _docs_book(root)
    commands.cmd_render(root, ["docs"], copy_name="c1")
    added = commands.cmd_render(root, ["web:web"], copy_name="c1")
    assert "web:web" in added.data["services"]
    assert "web:gateway" not in added.data["services"]


def test_an_up_replaces_the_services_of_the_books_it_names(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _docs_book(root)
    commands.cmd_render(root, ["web"], copy_name="c1")
    commands.cmd_render(root, ["docs"], copy_name="c1", fixtures=["users"])
    every = commands.cmd_render(root, copy_name="c1", cwd=root)
    assert every.data["services"] == [
        "api:db", "api:provision", "api:api", "docs:docs", "web:web", "web:gateway"]
    assert every.data["fixtures"] == ["schema"]


def _db_with_dump(root: Path) -> None:
    _rewrite_stack(root, "api", {"db": {
        "about": "the database", "define": "services/db.yml.j2",
        "fixtures": {"schema": ["fixtures/schema.sql"], "users": ["fixtures/users.sql"],
                     "dump": ["fixtures/dump.sql"]}}})


def test_a_set_no_bring_up_names_may_point_at_an_absent_file(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _db_with_dump(root)
    assert spec.load(root).errors == []
    assert commands.cmd_render(root, ["api"], copy_name="c1").ok


def test_choosing_a_set_with_an_absent_file_fails_before_any_docker_call(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _db_with_dump(root)
    rendered = commands.cmd_render(root, ["api"], copy_name="c1", fixtures=["dump"])
    assert not rendered.ok
    assert "`dump`" in rendered.message
    assert "fixtures/dump.sql" in rendered.message
    docker = FakeDocker()
    upped = commands.cmd_up(root, ["api"], copy_name="c1", fixtures=["dump"], runner=docker)
    assert not upped.ok
    assert "`dump`" in upped.message
    assert "fixtures/dump.sql" in upped.message
    assert docker.calls == []


def test_a_default_set_with_an_absent_file_is_a_load_error(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / SERVICES / "api" / "ops" / "fixtures" / "schema.sql").unlink()
    errors = spec.load(root).errors
    assert len(errors) == 1
    assert "service `db`" in errors[0]
    assert "fixture set `schema`" in errors[0]
    assert "`fixtures/schema.sql` does not exist" in errors[0]


def test_a_worktree_mounts_a_fixture_file_of_the_main_checkout(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _db_with_dump(root)
    tree = _worktree(root)
    dump = _file(root, f"{SERVICES}/api/ops/fixtures/dump.sql", "insert into t values (9);\n")
    (tree / SERVICES / "api" / "ops" / "fixtures" / "schema.sql").unlink()
    assert spec.load(tree).errors == []
    outcome = commands.cmd_render(tree, ["api"], copy_name="c1", fixtures=["schema", "dump"])
    assert outcome.ok, outcome.message
    compose = yaml.safe_load(
        (Path(outcome.data["directory"]) / render_mod.COMPOSE_FILE).read_text(encoding="utf-8"))
    mounts = compose["services"]["api-db"]["volumes"]
    assert f"{dump}:/docker-entrypoint-initdb.d/2-dump.sql:ro" in mounts
    assert f"{root}/{SERVICES}/api/ops/fixtures/schema.sql:/docker-entrypoint-initdb.d/1-schema.sql:ro" in mounts


def test_a_book_only_the_worktree_has_mounts_a_dump_of_the_main_checkout(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    tree = _worktree(root)
    shutil.rmtree(root / SERVICES / "api")
    _rewrite_stack(tree, "api", {"db": {
        "about": "the database", "define": "services/db.yml.j2",
        "fixtures": {"schema": ["fixtures/schema.sql"], "dump": ["../../../dumps/dump.sql"]}}})
    _file(root, "dumps/dump.sql", "insert into t values (9);\n")
    outcome = commands.cmd_render(tree, ["api"], copy_name="c1", fixtures=["dump"])
    assert outcome.ok, outcome.message
    compose = yaml.safe_load(
        (Path(outcome.data["directory"]) / render_mod.COMPOSE_FILE).read_text(encoding="utf-8"))
    assert (f"{root}/dumps/dump.sql:/docker-entrypoint-initdb.d/1-dump.sql:ro"
            in compose["services"]["api-db"]["volumes"])


def test_a_template_that_sets_its_own_ports_is_refused(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _file(root, f"{SERVICES}/web/ops/services/web.yml.j2", "image: web\nports: ['3000:3000']\n")
    outcome = commands.cmd_render(root, ["web"])
    assert not outcome.ok
    assert "`ports`" in outcome.message


def test_the_book_you_stand_in_is_the_default_target(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    outcome = commands.cmd_render(root, copy_name="c2", cwd=root / SERVICES / "api" / "ops")
    assert outcome.data["services"] == ["api:db", "api:provision", "api:api"]


class FakeDocker:
    def __init__(self, ps: str = "") -> None:
        self.calls: list[list[str]] = []
        self.ps = ps

    def __call__(self, argv: Sequence[str], *, capture: bool, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        args = list(argv)
        self.calls.append(args)
        stdout = ""
        if "port" in args:
            stdout = {"80": "127.0.0.1:49200\n", "8080": "127.0.0.1:49201\n"}[args[-1]]
        if args[:3] == ["docker", "compose", "ls"]:
            stdout = '[{"Name": "acme-story-1", "Status": "exited(3), running(5)"}]'
        if args[:2] == ["docker", "ps"]:
            stdout = self.ps
        return subprocess.CompletedProcess(args, 0, stdout, "")


def _compose_calls(docker: FakeDocker) -> list[list[str]]:
    return [call for call in docker.calls if call[:2] == ["docker", "compose"]]


def test_a_shared_up_names_the_container_holding_its_fixed_port(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    docker = FakeDocker(ps="api-mysql-test-1\tapi\t\t0.0.0.0:8443->3306/tcp, [::]:8443->3306/tcp\n")
    outcome = commands.cmd_up(root, ["web"], runner=docker)
    assert not outcome.ok
    assert "web:gateway needs host port 8443, which container api-mysql-test-1 of compose " \
           "project api holds" in outcome.message
    assert "`ostler env up web --copy NAME`" in outcome.message
    assert _compose_calls(docker) == []


def test_a_shared_up_says_another_checkout_already_runs_the_service(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    other = runtime.Copy(name="shared", project="beta-shared",
                         directory=runtime.home() / "beta-shared")
    runtime.write_manifest(other, {"repo": "/work/beta", "copy": "shared"})
    docker = FakeDocker(ps="beta-shared-web-gateway-1\tbeta-shared\tweb:gateway\t"
                           "127.0.0.1:8443->80/tcp\n")
    outcome = commands.cmd_up(root, ["web"], runner=docker)
    assert not outcome.ok
    assert "web:gateway is already running on host port 8443 in the shared copy of /work/beta" \
        in outcome.message


def test_a_shared_up_names_a_port_held_outside_docker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)
    monkeypatch.setattr(runtime, "port_free", lambda port: port != 8443)
    outcome = commands.cmd_up(root, ["web"], runner=FakeDocker())
    assert not outcome.ok
    assert "which a process outside docker holds" in outcome.message


def test_a_shared_up_over_its_own_running_containers_goes_ahead(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    docker = FakeDocker(ps="acme-shared-web-gateway-1\tacme-shared\tweb:gateway\t"
                           "127.0.0.1:8443->80/tcp\n")
    outcome = commands.cmd_up(root, ["web"], runner=docker)
    assert outcome.ok, outcome.message


def test_a_named_copy_never_checks_the_fixed_ports(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    docker = FakeDocker(ps="other\t\t\t0.0.0.0:8443->80/tcp\n")
    assert commands.cmd_up(root, ["web"], copy_name="story-1", runner=docker).ok
    assert not any(call[:2] == ["docker", "ps"] for call in docker.calls)


def test_up_waits_for_a_port_that_refuses_twice_then_accepts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)
    tries: list[tuple[str, int]] = []

    def probe(host: str, port: int) -> bool:
        tries.append((host, port))
        return tries.count((host, port)) > 2 or port != 49201

    monkeypatch.setattr(runtime, "port_probe", probe)
    outcome = commands.cmd_up(root, ["web"], copy_name="story-1", runner=FakeDocker())
    assert outcome.ok, outcome.message
    assert tries.count(("localhost", 49201)) == 3
    assert (runtime.copy_for(root, "story-1").directory / runtime.ADDRESSES).is_file()


def test_up_fails_naming_a_port_that_never_accepts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)
    monkeypatch.setattr(runtime, "port_probe", lambda host, port: port != 49201)
    outcome = commands.cmd_up(root, ["web"], copy_name="story-1", runner=FakeDocker(), wait_seconds=1)
    assert not outcome.ok
    assert outcome.message == "api:api did not accept a connection on localhost:49201 within 1s"
    assert not (runtime.copy_for(root, "story-1").directory / runtime.ADDRESSES).exists()


def test_a_target_with_no_published_port_is_not_probed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)
    tries: list[int] = []
    monkeypatch.setattr(runtime, "port_probe", lambda host, port: tries.append(port) or True)
    assert commands.cmd_up(root, ["api"], copy_name="story-1", runner=FakeDocker()).ok
    assert tries == [49201]


def test_the_probe_accepts_a_listening_port_and_refuses_a_closed_one() -> None:
    import socket
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        assert runtime.accepts_connection("127.0.0.1", port)
    assert not runtime.accepts_connection("127.0.0.1", port)


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
        ("story-1", "running")]


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
    outcome = leases.up(root, lease="story-1", near=root / SERVICES / "web", runner=FakeDocker())
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


def _gone_pid() -> int:
    finished = subprocess.Popen(["true"])
    finished.wait()
    return finished.pid


def test_a_copy_whose_run_is_gone_is_reclaimed_at_the_next_lease(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    docker = FakeDocker()
    commands.cmd_up(root, ["web"], copy_name="by-hand", runner=docker)
    commands.cmd_up(root, ["web"], copy_name="story-1", holder=_gone_pid(), runner=docker)
    live = leases.up(root, lease="story-2", near=root / SERVICES / "web", holder=os.getpid(),
                     runner=docker)
    assert live is not None and live.ok, live
    assert live.data["reclaimed"] == ["acme-story-1"]
    later = commands.cmd_up(root, ["web"], copy_name="story-3", runner=docker)
    assert later.data["reclaimed"] == []
    assert [copy.name for copy in runtime.copies(root)] == ["by-hand", "story-2", "story-3"]


def test_a_resumed_run_restamps_its_copy_and_survives_reclaim(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    docker = FakeDocker()
    up = commands.cmd_up(root, ["web"], copy_name="story-1", holder=_gone_pid(), runner=docker)
    directory = Path(up.data["directory"])
    assert not runtime.holder_alive(runtime.read_manifest(directory)["holder"])
    assert runtime.hold(root, "story-1", os.getpid())
    assert runtime.read_manifest(directory)["holder"] == runtime.holder_stamp(os.getpid())
    assert commands.reclaim(runner=docker) == []
    assert [copy.name for copy in runtime.copies(root)] == ["story-1"]


def test_holding_a_copy_that_does_not_exist_does_nothing(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert not runtime.hold(root, "story-9", os.getpid())
    assert runtime.copies(root) == []


def test_a_reused_pid_does_not_pass_for_the_run_that_held_the_copy() -> None:
    stamp = runtime.holder_stamp(os.getpid())
    assert runtime.holder_alive(stamp)
    assert runtime.holder_alive({})
    if stamp["started"]:
        assert not runtime.holder_alive({**stamp, "started": "1"})


def test_a_command_run_under_a_lease_names_its_holder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)
    env = leases.run_env(root, "story-1", holder=os.getpid())
    assert env is not None and env[runtime.HOLDER_ENV] == str(os.getpid())
    monkeypatch.setenv(addresses.LEASE_ENV, env[addresses.LEASE_ENV])
    monkeypatch.setenv(runtime.HOLDER_ENV, env[runtime.HOLDER_ENV])
    up = commands.cmd_up(root, ["web"], copy_name="story-1", runner=FakeDocker())
    assert runtime.read_manifest(Path(up.data["directory"]))["holder"] == \
        runtime.holder_stamp(os.getpid())


def test_a_named_copy_brought_up_under_a_lease_is_not_held_by_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)
    docker = FakeDocker()
    monkeypatch.setenv(addresses.LEASE_ENV, "story-1")
    monkeypatch.setenv(runtime.HOLDER_ENV, str(_gone_pid()))
    prod = commands.cmd_up(root, ["web"], copy_name="prod", runner=docker)
    assert runtime.read_manifest(Path(prod.data["directory"]))["holder"] == {}
    lease = commands.cmd_up(root, ["web"], copy_name="story-1", runner=docker)
    assert lease.data["reclaimed"] == []
    assert [copy.name for copy in runtime.copies(root)] == ["prod", "story-1"]


def test_a_command_run_without_a_lease_names_the_shared_copy(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    env = leases.run_env(root)
    assert env == {
        addresses.LEASE_ENV: render_mod.SHARED,
        addresses.BOOK_ENV: str(runtime.copy_for(root, render_mod.SHARED).directory / runtime.ADDRESSES),
    }


def test_the_book_near_the_run_is_the_only_one_brought_up(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert leases.books_near(root, root / SERVICES / "api" / "ops") == ["api"]
    assert leases.books_near(root) == ["api", "web"]
    assert leases.books_near(root, tmp_path) == []


def _worktree(root: Path) -> Path:
    gitdir = root / ".git" / "worktrees" / "story-1"
    gitdir.mkdir(parents=True)
    _file(gitdir, "commondir", "../..\n")
    tree = root.parent / "worktrees" / "acme-story-1"
    shutil.copytree(root / "services", tree / "services")
    _file(tree, ".git", f"gitdir: {gitdir}\n")
    return tree


def test_a_book_reads_its_paths_from_its_ops_folder(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    catalog = spec.load(root)
    book = catalog.books["web"]
    assert book.directory == root / SERVICES / "web"
    assert book.ops_dir == root / SERVICES / "web" / "ops"
    assert catalog.services["web:gateway"].ops_dir == book.ops_dir
    assert catalog.services["web:gateway"].define == book.ops_dir / "services" / "gateway.yml.j2"


def test_the_stack_root_is_a_book_named_after_the_repo(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _file(root, f"{SERVICES}/ops/services/cache.yml.j2", "image: redis:7\n")
    _file(root, f"{SERVICES}/ops/stack.yml", yaml.safe_dump({"services": {
        "cache": {"about": "the cache", "define": "services/cache.yml.j2"}}}))
    catalog = spec.load(root)
    assert catalog.errors == []
    assert catalog.books["acme"].directory == root / SERVICES
    assert catalog.books["acme"].ops_dir == root / SERVICES / "ops"
    assert "acme:cache" in catalog.services


def test_a_template_sees_ops_dir_and_no_longer_book_dir(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _file(root, f"{SERVICES}/web/ops/services/web.yml.j2",
          "image: web\nlabels:\n  from: {{ ops_dir }}\n")
    outcome = commands.cmd_render(root, ["web"], copy_name="c1")
    assert outcome.ok, outcome.message
    compose = yaml.safe_load(
        (Path(outcome.data["directory"]) / render_mod.COMPOSE_FILE).read_text(encoding="utf-8"))
    assert compose["services"]["web-web"]["labels"]["from"] == str(root / SERVICES / "web" / "ops")
    _file(root, f"{SERVICES}/web/ops/services/web.yml.j2", "image: {{ book_dir }}\n")
    stale = commands.cmd_render(root, ["web"], copy_name="c1")
    assert not stale.ok
    assert "book_dir" in stale.message


def test_a_service_with_no_about_is_refused_by_name(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _rewrite_stack(root, "web", {"web": {"define": "services/web.yml.j2"}})
    assert ("services/web/ops/stack.yml: service `web`: names no `about:`, "
            "the line `ostler env ls` shows for it") in spec.load(root).errors


def _reference_levels() -> set[tuple[str, str]]:
    reference = (Path(__file__).resolve().parents[2] / "base-library" / "library" / "skills"
                 / "ostler" / "ostler-cli" / "references" / "stack.md")
    found: set[tuple[str, str]] = set()
    keyed = False
    for line in reference.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[:2] == ["key", "where"]:
            keyed = True
        elif keyed and line.startswith("|"):
            match = re.fullmatch(r"`([a-z-]+)`", cells[0])
            if match:
                found.add((match.group(1), cells[1]))
        else:
            keyed = False
    return found


def test_the_reference_lists_exactly_the_keys_the_loader_accepts() -> None:
    assert _reference_levels() == {(key.name, key.level) for key in spec.KEYS}


def test_the_schema_comes_from_the_key_table_and_refuses_an_unknown_key() -> None:
    schema = spec.schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == spec.keys_at("book") | spec.keys_at("root")
    service = schema["properties"]["services"]["additionalProperties"]
    assert service["additionalProperties"] is False
    assert set(service["properties"]) == spec.keys_at("service")
    assert service["required"] == ["about", "define"]
    assert all(body["description"] for body in service["properties"].values())


def test_env_schema_prints_the_schema_as_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    parser = argparse.ArgumentParser()
    cli.add_parser(parser.add_subparsers(dest="command"))
    assert cli.run(parser.parse_args(["env", "schema"]), tmp_path) == 0
    assert json.loads(capsys.readouterr().out) == spec.schema()


def _up_two_copies(root: Path) -> FakeDocker:
    docker = FakeDocker()
    assert commands.cmd_up(root, ["web"], copy_name="story-1", runner=docker).ok
    assert commands.cmd_render(root, ["api"]).ok
    return docker


def test_ls_lists_each_service_with_its_about_address_and_copies(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    docker = _up_two_copies(root)
    listing = commands.cmd_ls(root, runner=docker)
    assert listing.ok
    assert listing.message.splitlines() == [
        "api",
        "  api:api        the HTTP API               api            shared (stopped), story-1",
        "  api:db         the database                              shared (stopped), story-1",
        "  api:provision  creates the schema                        shared (stopped), story-1",
        "web",
        "  web:gateway    the proxy a browser opens  gateway :8443  story-1",
        "  web:web        the browser app                           story-1",
    ]


def test_ls_json_keeps_the_copies_and_adds_the_services(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    docker = _up_two_copies(root)
    data = commands.cmd_ls(root, runner=docker).data
    assert sorted(row["copy"] for row in data["copies"]) == ["shared", "story-1"]
    gateway = next(row for row in data["services"] if row["ref"] == "web:gateway")
    assert gateway == {
        "ref": "web:gateway", "book": "web", "name": "gateway",
        "about": "the proxy a browser opens", "address": "gateway", "host_port": 8443,
        "copies": ["story-1"],
    }


def test_ls_cuts_a_long_about_to_one_line(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _rewrite_stack(root, "web", {"web": {"about": "x" * 80, "define": "services/web.yml.j2"}})
    line = next(row for row in commands.cmd_ls(root, runner=FakeDocker()).message.splitlines()
                if "web:web" in row)
    assert line.strip().endswith("…")
    assert len(line) < 80


def test_ls_still_lists_what_loaded_when_the_catalog_has_errors(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _rewrite_stack(root, "web", {"web": {"define": "services/web.yml.j2"}})
    listing = commands.cmd_ls(root, runner=FakeDocker())
    assert not listing.ok
    assert "api:db" in listing.message
    assert "the stack files do not fit together:\n- " in listing.message
    assert "names no `about:`" in listing.message
    assert listing.data["errors"]


def test_ls_with_no_stack_file_says_so_and_lists_the_copies(tmp_path: Path) -> None:
    root = tmp_path / "globex"
    (root / SERVICES).mkdir(parents=True)
    empty = commands.cmd_ls(root, runner=FakeDocker())
    assert empty.ok
    assert empty.message == "no book has an ops/stack.yml"
    runtime.write_manifest(runtime.copy_for(root, "story-9"), {
        "repo": str(root), "copy": "story-9", "targets": ["x:y"]})
    kept = commands.cmd_ls(root, runner=FakeDocker())
    assert kept.message.splitlines() == ["no book has an ops/stack.yml", "story-9  stopped  x:y"]


def _book_stack(root: Path, book: str, change: dict) -> None:
    target = root / SERVICES / book / "ops" / spec.STACK_FILE
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    target.write_text(yaml.safe_dump({**data, **change}), encoding="utf-8")


def _root_stack(root: Path, secrets: object) -> None:
    _file(root, f"{SERVICES}/ops/stack.yml", yaml.safe_dump({"secrets": secrets}))


def _needs_token(root: Path) -> None:
    _file(root, f"{SERVICES}/web/ops/services/web.yml.j2",
          "image: web\nenvironment:\n  TOKEN: ${TOKEN}\n  LITERAL: $${NOT_A_NAME}\n"
          "  OPTIONAL: ${OPT:-none}\n")


def _up_calls(docker: FakeDocker) -> list[list[str]]:
    return [call for call in docker.calls if "up" in call]


def test_secrets_in_a_book_file_is_refused_and_a_saddlebag_name_names_the_new_shape(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _book_stack(root, "web", {"secrets": "web-local"})
    errors = spec.load(root).errors
    assert any(
        error.startswith("services/web/ops/stack.yml: `secrets:` belongs in the stack root, "
                         "services/ops/stack.yml: one repo has one secret source")
        and "`saddlebag: \"<key>=<value>\"`" in error for error in errors)


def test_the_stack_root_refuses_a_saddlebag_name_and_two_sources(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _root_stack(root, "web-local")
    assert any("`secrets: web-local` names a saddlebag environment" in error
               and "`secrets: {saddlebag: \"<key>=<value>\"}`" in error
               for error in spec.load(root).errors)
    _root_stack(root, {"file": ".env", "decrypt": "true"})
    assert any("takes exactly one of `file:`, `decrypt:` or `saddlebag:`" in error
               for error in spec.load(root).errors)
    _root_stack(root, {"file": ".env"})
    assert spec.load(root).secrets == spec.SecretSpec(file=".env")


def _beside_repo(tmp_path: Path) -> Path:
    root = tmp_path / "acme"
    (root / ".git").mkdir(parents=True)
    _file(root, "services/billing/ops/services/ledger.yml.j2", "image: ledger\n")
    _file(root, "services/billing/ops/stack.yml", yaml.safe_dump({"services": {
        "ledger": {"about": "the ledger", "define": "services/ledger.yml.j2"}}}))
    return root


def test_a_stack_file_beside_the_service_book_is_loaded(tmp_path: Path) -> None:
    root = _beside_repo(tmp_path)
    catalog = spec.load(root)
    assert catalog.errors == []
    book = catalog.books["billing"]
    assert book.directory == root / "services" / "billing"
    assert book.ops_dir == root / "services" / "billing" / "ops"
    assert catalog.services["billing:ledger"].define == book.ops_dir / "services" / "ledger.yml.j2"


def test_the_stack_root_beside_the_service_books_holds_secrets(tmp_path: Path) -> None:
    root = _beside_repo(tmp_path)
    _file(root, "services/ops/services/cache.yml.j2", "image: redis:7\n")
    _file(root, "services/ops/stack.yml", yaml.safe_dump({
        "secrets": {"file": ".env"},
        "services": {"cache": {"about": "the cache", "define": "services/cache.yml.j2"}}}))
    catalog = spec.load(root)
    assert catalog.errors == []
    assert catalog.secrets == spec.SecretSpec(file=".env")
    assert catalog.books["acme"].directory == root / "services"
    assert "acme:cache" in catalog.services


def test_the_book_near_a_file_beside_the_service_book_is_the_one_brought_up(
    tmp_path: Path,
) -> None:
    root = _beside_repo(tmp_path)
    near = root / "services" / "billing" / "some" / "file"
    assert leases.books_near(root, near=near) == ["billing"]


def test_the_reference_tables_the_root_level_for_secrets() -> None:
    assert ("secrets", "root") in {(key.name, key.level) for key in spec.KEYS}
    assert "stack root" in spec.schema()["properties"]["secrets"]["description"]


def test_a_dotenv_file_feeds_compose_in_place_and_names_are_read_without_values(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _needs_token(root)
    _root_stack(root, {"file": ".env"})
    _file(root, ".env", "# note\nexport TOKEN=abc\n\nOTHER = 2\n")
    docker = FakeDocker()
    outcome = commands.cmd_up(root, ["web"], copy_name="story-1", runner=docker)
    assert outcome.ok, outcome.message
    up = _up_calls(docker)[0]
    assert up[up.index("--env-file") + 1] == str(root / ".env")
    assert runtime.read_manifest(Path(outcome.data["directory"]))["env_files"] == [
        str(root / ".env")]
    compose = commands.compose_argv(root, ["logs"], copy_name="story-1")
    assert isinstance(compose, list) and str(root / ".env") in compose


def test_a_missing_dotenv_file_fails_up_naming_its_path(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _root_stack(root, {"file": ".env"})
    docker = FakeDocker()
    outcome = commands.cmd_up(root, ["web"], copy_name="story-1", runner=docker)
    assert not outcome.ok
    assert str(root / ".env") in outcome.message
    assert _up_calls(docker) == []


def test_a_worktree_reads_the_dotenv_file_of_the_main_checkout(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _root_stack(root, {"file": ".env"})
    _file(root, ".env", "TOKEN=abc\n")
    tree = _worktree(root)
    assert checkout.main_checkout(tree) == root
    docker = FakeDocker()
    assert commands.cmd_up(tree, ["api"], copy_name="story-1", runner=docker).ok
    up = _up_calls(docker)[0]
    assert up[up.index("--env-file") + 1] == str(root / ".env")


class FakeDecrypt(FakeDocker):
    def __init__(self, status: int = 0) -> None:
        super().__init__()
        self.status = status

    def __call__(self, argv: Sequence[str], *, capture: bool, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        if argv[0] == "sh":
            self.calls.append(list(argv))
            return subprocess.CompletedProcess(
                list(argv), self.status, "TOKEN=s3cret-value\n" if not self.status else "",
                "\n".join(f"line {n}" for n in range(8)) if self.status else "")
        return super().__call__(argv, capture=capture, stdin=stdin)


def test_a_decrypt_command_writes_a_private_file_and_no_output_holds_its_value(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    root = _repo(tmp_path)
    _needs_token(root)
    _root_stack(root, {"decrypt": "vault read"})
    docker = FakeDecrypt()
    outcome = commands.cmd_up(root, ["web"], copy_name="story-1", runner=docker)
    assert outcome.ok, outcome.message
    env = Path(outcome.data["directory"]) / runtime.SECRETS_DIR / "stack.env"
    assert env.read_text(encoding="utf-8") == "TOKEN=s3cret-value\n"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    assert [call for call in docker.calls if call[0] == "sh"] == [
        ["sh", "-c", f"cd {root} && vault read"]]
    checked = commands.cmd_check(root, runner=docker)
    assert checked.ok, checked.message
    parser = argparse.ArgumentParser()
    cli.add_parser(parser.add_subparsers(dest="command"))
    assert cli.run(parser.parse_args(["env", "check", "--json"]), root) in (0, 1)
    seen = capsys.readouterr()
    for text in (outcome.message, json.dumps(outcome.data), checked.message,
                 json.dumps(checked.data), seen.out, seen.err):
        assert "s3cret-value" not in text
    commands.cmd_down(root, copy_name="story-1", runner=docker)
    assert not env.exists()


def test_a_failing_decrypt_command_reports_its_exit_code_and_last_five_stderr_lines(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _root_stack(root, {"decrypt": "vault read"})
    docker = FakeDecrypt(status=3)
    outcome = commands.cmd_up(root, ["web"], copy_name="story-1", runner=docker)
    assert not outcome.ok
    assert "exited 3" in outcome.message
    assert outcome.message.endswith("line 3\nline 4\nline 5\nline 6\nline 7")
    assert "line 2" not in outcome.message
    assert _up_calls(docker) == []


def test_a_name_no_source_defines_fails_up_before_docker_and_check_by_name(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _needs_token(root)
    _root_stack(root, {"file": ".env"})
    _file(root, ".env", "OTHER=1\n")
    docker = FakeDocker()
    outcome = commands.cmd_up(root, ["web"], copy_name="story-1", runner=docker)
    assert not outcome.ok
    assert "`TOKEN` is required by web:web" in outcome.message
    assert "NOT_A_NAME" not in outcome.message and "OPT" not in outcome.message
    assert docker.calls == []
    checked = commands.cmd_check(root)
    assert not checked.ok
    assert "`TOKEN` is required by web:web" in checked.message
    _file(root, ".env", "TOKEN=1\n")
    assert commands.cmd_check(root).ok


def test_a_template_name_with_no_secret_source_at_all_is_missing(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _needs_token(root)
    assert "`TOKEN` is required by web:web" in commands.cmd_check(root).message


def test_an_unbraced_name_is_required_an_escaped_one_is_not() -> None:
    assert secrets.required_names("echo $TOKEN") == {"TOKEN"}
    assert secrets.required_names("echo $$TOKEN") == frozenset()
    assert secrets.required_names("echo ${TOKEN:+x} ${TOKEN+x}") == frozenset()


def test_required_names_skip_defaults_and_escapes() -> None:
    text = "${A} ${B:?need} ${C?need} ${D:-x} ${E-x} ${F:+y} $${G} $$H $I x$J_K"
    assert secrets.required_names(text) == {"A", "B", "C", "I", "J_K"}
    assert secrets.parse_names("# X=1\nexport A=1\n B=2\nnot a line\n") == {"A", "B"}


def test_a_render_key_is_refused_and_names_files(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _rewrite_stack(root, "web", {"web": {"about": "x", "define": "services/web.yml.j2",
                                         "render": ["services/Caddyfile.j2"]}})
    assert any("`render:` is gone" in error and "`files:" in error
               for error in spec.load(root).errors)


def test_a_files_target_outside_the_service_folder_or_a_missing_source_is_refused(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _rewrite_stack(root, "web", {"web": {"about": "x", "define": "services/web.yml.j2", "files": {
        "../escape": "services/Caddyfile.j2", "/abs": "services/Caddyfile.j2",
        "ok": "services/none.txt"}}})
    errors = spec.load(root).errors
    assert any("target `../escape` is not a path inside" in error for error in errors)
    assert any("target `/abs` is not a path inside" in error for error in errors)
    assert any("`services/none.txt` does not exist" in error for error in errors)


def test_files_render_j2_sources_and_copy_every_other_file_byte_for_byte(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    ops = root / SERVICES / "web" / "ops"
    _file(ops, "static/run.sh", "#!/bin/sh\necho {{ not_a_template }}\n")
    (ops / "static" / "run.sh").chmod(0o755)
    _file(ops, "static/conf/app.ini.j2", "host={{ service('api:api') }}\n")
    _file(ops, "static/conf/plain.txt", "{{ literal }}\n")
    _file(ops, "static/Caddy.j2", "{{ env_dir }}\n")
    _rewrite_stack(root, "web", {"web": {"about": "x", "define": "services/web.yml.j2", "files": {
        "bin/run.sh": "static/run.sh", "etc": "static/conf", "Caddy": "static/Caddy.j2"}}})
    outcome = commands.cmd_render(root, ["web"], copy_name="c1")
    assert outcome.ok, outcome.message
    directory = Path(outcome.data["directory"])
    folder = directory / "web-web"
    script = folder / "bin" / "run.sh"
    assert script.read_text(encoding="utf-8") == "#!/bin/sh\necho {{ not_a_template }}\n"
    assert stat.S_IMODE(script.stat().st_mode) == 0o755
    assert (folder / "etc" / "app.ini").read_text(encoding="utf-8") == "host=api-api\n"
    assert not (folder / "etc" / "app.ini.j2").exists()
    assert (folder / "etc" / "plain.txt").read_text(encoding="utf-8") == "{{ literal }}\n"
    assert (folder / "Caddy").read_text(encoding="utf-8") == f"{directory}\n"


def test_a_dockerfile_placed_in_the_copy_builds_against_the_checkout(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    ops = root / SERVICES / "web" / "ops"
    _file(ops, "services/web.yml.j2",
          'build:\n  context: "{{ repo }}"\n  dockerfile: "{{ dir }}/Dockerfile"\n')
    _file(ops, "images/web.Dockerfile.j2", "FROM node:22\nCOPY . /app\n# {{ copy }}\n")
    _rewrite_stack(root, "web", {"web": {"about": "x", "define": "services/web.yml.j2",
                                         "files": {"Dockerfile": "images/web.Dockerfile.j2"}}})
    outcome = commands.cmd_render(root, ["web"], copy_name="c1")
    assert outcome.ok, outcome.message
    directory = Path(outcome.data["directory"])
    compose = yaml.safe_load((directory / render_mod.COMPOSE_FILE).read_text(encoding="utf-8"))
    build = compose["services"]["web-web"]["build"]
    assert build == {"context": str(root), "dockerfile": str(directory / "web-web" / "Dockerfile")}
    assert (directory / "web-web" / "Dockerfile").read_text(encoding="utf-8").endswith("# c1\n")


def _web_needs_api(root: Path) -> None:
    target = root / SERVICES / "web" / "ops" / spec.STACK_FILE
    target.write_text(yaml.safe_dump({"needs": ["api"], "services": {
        "web": {"about": "the browser app", "define": "services/web.yml.j2"},
        "gateway": {"about": "the proxy", "define": "services/gateway.yml.j2",
                    "needs": ["web"], "address": "gateway", "port": 80, "host-port": 8443,
                    "files": {"Caddyfile": "services/Caddyfile.j2"}}}}), encoding="utf-8")


def test_a_book_that_needs_a_book_brings_every_service_of_it_up_first(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _web_needs_api(root)
    catalog = spec.load(root)
    assert catalog.errors == []
    order = [service.ref for service in spec.closure(catalog, ["web"])]
    assert order == ["api:db", "api:provision", "api:api", "web:web", "web:gateway"]
    outcome = commands.cmd_render(root, ["web"], copy_name="c1")
    compose = yaml.safe_load(
        (Path(outcome.data["directory"]) / render_mod.COMPOSE_FILE).read_text(encoding="utf-8"))
    assert set(compose["services"]["web-web"]["depends_on"]) == {
        "api-db", "api-provision", "api-api"}


def test_a_book_needing_an_unknown_book_or_itself_is_refused(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _book_stack(root, "web", {"needs": ["queue", "web"]})
    errors = spec.load(root).errors
    assert ("services/web/ops/stack.yml: `needs:` names the book `queue`, which no "
            "stack.yml defines") in errors
    assert "services/web/ops/stack.yml: book `web` lists itself in `needs:`" in errors


def test_books_that_need_each_other_form_a_cycle_naming_the_services(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _book_stack(root, "web", {"needs": ["api"]})
    _book_stack(root, "api", {"needs": ["web"]})
    errors = [error for error in spec.load(root).errors if "cycle" in error]
    assert errors
    assert "web:web" in errors[0] and "api:api" in errors[0]


def _report_reaches_api(root: Path, key: str) -> None:
    _rewrite_stack(root, "api", {
        "api": {"about": "x", "define": "services/api.yml.j2",
                "needs": ["db", "provision", "report:report"]}})
    _file(root, f"{SERVICES}/report/ops/services/report.yml.j2", "image: report\n")
    _file(root, f"{SERVICES}/report/ops/stack.yml", yaml.safe_dump({key: ["api"], "services": {
        "report": {"about": "x", "define": "services/report.yml.j2"}}}))


def test_a_book_reaches_a_service_its_own_do_not_need_without_a_cycle(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _report_reaches_api(root, "reaches")
    catalog = spec.load(root)
    assert catalog.errors == []
    order = [service.ref for service in spec.closure(catalog, ["report"])]
    assert order == ["report:report", "api:db", "api:provision", "api:api"]
    assert catalog.services["report:report"].needs == ()


def test_a_book_that_needs_what_needs_it_is_still_a_cycle(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _report_reaches_api(root, "needs")
    assert any("cycle" in error for error in spec.load(root).errors)


def test_a_book_reaching_an_unknown_book_is_refused(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _book_stack(root, "web", {"reaches": ["queue"]})
    assert ("services/web/ops/stack.yml: `reaches:` names the book `queue`, which no "
            "stack.yml defines") in spec.load(root).errors


def test_a_target_of_one_service_does_not_pull_what_its_book_reaches(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _report_reaches_api(root, "reaches")
    catalog = spec.load(root)
    assert [service.ref for service in spec.closure(catalog, ["report:report"])] == ["report:report"]


def test_outputs_need_once_and_an_environment_name(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _rewrite_stack(root, "api", {
        "db": {"about": "x", "define": "services/db.yml.j2", "outputs": ["URL"]},
        "provision": {"about": "x", "define": "services/provision.yml.j2", "once": True,
                      "outputs": ["bad-name"]}})
    errors = spec.load(root).errors
    assert any("service `db`: `outputs:` needs `once: true`" in error for error in errors)
    assert any("output `bad-name` is not an environment name" in error for error in errors)


def _with_outputs(root: Path, template: str = "image: pulumi/pulumi\n") -> None:
    _file(root, f"{SERVICES}/api/ops/services/provision.yml.j2", template)
    _rewrite_stack(root, "api", {"provision": {
        "about": "creates the bucket", "define": "services/provision.yml.j2", "once": True,
        "outputs": ["UPLOAD_BUCKET"]}})
    _file(root, f"{SERVICES}/api/ops/services/api.yml.j2",
          "build: {{ repo }}/api-service\nenvironment:\n  BUCKET: ${UPLOAD_BUCKET}\n")


def _render_compose(root: Path) -> dict:
    outcome = commands.cmd_render(root, ["api"], copy_name="c1")
    assert outcome.ok, outcome.message
    return yaml.safe_load(
        (Path(outcome.data["directory"]) / render_mod.COMPOSE_FILE).read_text(encoding="utf-8"))


def test_a_job_with_outputs_gets_a_world_writable_mount_and_the_outputs_variable(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _with_outputs(root)
    job = _render_compose(root)["services"]["api-provision"]
    host = runtime.copy_for(root, "c1").directory / "outputs" / "api-provision"
    assert f"{host}:/stablemate/outputs" in job["volumes"]
    assert job["environment"] == {"STABLEMATE_OUTPUTS": "/stablemate/outputs/outputs.env"}
    assert stat.S_IMODE(host.stat().st_mode) == 0o777


def test_the_outputs_variable_is_added_to_a_list_environment(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _with_outputs(root, "image: x\nenvironment:\n  - A=1\nvolumes:\n  - data:/d\n")
    job = _render_compose(root)["services"]["api-provision"]
    assert job["environment"] == ["A=1", "STABLEMATE_OUTPUTS=/stablemate/outputs/outputs.env"]
    assert job["volumes"][0] == "api-provision-data:/d"


@pytest.mark.parametrize("environment", ["  STABLEMATE_OUTPUTS: /x\n", "  - STABLEMATE_OUTPUTS=/x\n"])
def test_a_template_that_sets_the_outputs_variable_is_refused(
    tmp_path: Path, environment: str,
) -> None:
    root = _repo(tmp_path)
    _with_outputs(root, "image: x\nenvironment:\n" + environment)
    outcome = commands.cmd_render(root, ["api"], copy_name="c1")
    assert not outcome.ok
    assert "STABLEMATE_OUTPUTS" in outcome.message


class FakeJobs(FakeDocker):
    def __init__(self, writes: str = "UPLOAD_BUCKET=bkt-123\nOTHER=ignored\n") -> None:
        super().__init__()
        self.writes = writes
        self.seen: list[str] = []

    def __call__(self, argv: Sequence[str], *, capture: bool, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        args = list(argv)
        if "up" in args and "api-provision" in args:
            directory = Path(args[args.index("--project-directory") + 1])
            self.seen.append(args[args.index("--env-file") + 1]
                             if "--env-file" in args else "")
            target = directory / "outputs" / "api-provision" / "outputs.env"
            target.write_text(self.writes, encoding="utf-8")
        return super().__call__(args, capture=capture, stdin=stdin)


def test_a_stack_with_no_job_outputs_runs_exactly_one_compose_up(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    docker = FakeDocker()
    assert commands.cmd_up(root, ["web"], copy_name="story-1", runner=docker).ok
    assert len(_up_calls(docker)) == 1


def test_a_job_with_outputs_runs_first_and_its_values_reach_the_full_up(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _with_outputs(root)
    docker = FakeJobs()
    outcome = commands.cmd_up(root, ["api"], copy_name="story-1", runner=docker)
    assert outcome.ok, outcome.message
    first, second = _up_calls(docker)
    assert first[-1] == "api-provision"
    assert "api-api" not in first and "api-db" not in first
    assert second[-1] != "api-provision"
    merged = Path(outcome.data["directory"]) / "secrets" / "outputs.env"
    assert merged.read_text(encoding="utf-8") == "UPLOAD_BUCKET=bkt-123\n"
    assert stat.S_IMODE(merged.stat().st_mode) == 0o600
    assert str(merged) in second
    assert docker.seen == [str(merged)]
    raw = Path(outcome.data["directory"]) / "outputs" / "api-provision" / "outputs.env"
    assert not raw.exists()
    assert "bkt-123" not in outcome.message + json.dumps(outcome.data)


def test_a_job_that_omits_a_declared_name_fails_up_naming_the_job_and_the_name(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _with_outputs(root)
    docker = FakeJobs(writes="OTHER=1\n")
    outcome = commands.cmd_up(root, ["api"], copy_name="story-1", runner=docker)
    assert not outcome.ok
    assert "api:provision exited 0 without writing `UPLOAD_BUCKET`" in outcome.message
    assert len(_up_calls(docker)) == 1


def test_a_job_output_satisfies_the_name_check_for_the_services_that_need_it(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _with_outputs(root)
    assert commands.cmd_check(root).ok
    _rewrite_stack(root, "api", {"provision": {
        "about": "x", "define": "services/provision.yml.j2", "once": True}})
    assert "`UPLOAD_BUCKET` is required by api:api" in commands.cmd_check(root).message


class FakeSaddlebag(FakeDocker):
    def __init__(self, secrets: list[dict] | None = None, status: int = 0) -> None:
        super().__init__()
        self.secrets = [{"name": "api-token", "username": None, "description": None,
                         "var": "TOKEN", "tags": [["environment", "local"]],
                         "fields": ["value"]}] if secrets is None else secrets
        self.status = status

    def __call__(self, argv: Sequence[str], *, capture: bool, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        if argv[0] == "saddlebag":
            self.calls.append(list(argv))
            return subprocess.CompletedProcess(
                list(argv), self.status, json.dumps({"secrets": self.secrets}) if not self.status else "",
                "the daemon is not running" if self.status else "")
        return super().__call__(argv, capture=capture, stdin=stdin)


def test_the_saddlebag_key_takes_one_or_more_tags_and_refuses_a_bad_one(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _root_stack(root, {"saddlebag": "environment=local"})
    assert spec.load(root).secrets == spec.SecretSpec(saddlebag="environment=local")
    _root_stack(root, {"saddlebag": "environment=local  team=acme"})
    loaded = spec.load(root)
    assert loaded.secrets.saddlebag == "environment=local  team=acme"
    assert not loaded.errors
    for bad in ("environment", "=local", "environment="):
        _root_stack(root, {"saddlebag": bad})
        assert any("`key=value` tags" in error for error in spec.load(root).errors)


def test_a_saddlebag_source_wraps_compose_and_writes_no_env_file(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _needs_token(root)
    _root_stack(root, {"saddlebag": "environment=local"})
    docker = FakeSaddlebag()
    outcome = commands.cmd_up(root, ["web"], copy_name="story-1", runner=docker)
    assert outcome.ok, outcome.message
    prefix = ["saddlebag", "exec", "--tag", "environment=local", "--"]
    assert ["saddlebag", "list", "--tag", "environment=local", "--json"] in docker.calls
    assert _up_calls(docker)[0][:5] == prefix
    directory = Path(outcome.data["directory"])
    assert not (directory / runtime.SECRETS_DIR / "stack.env").exists()
    assert runtime.read_manifest(directory)["exec_prefix"] == prefix
    assert runtime.exec_prefix(runtime.copy_for(root, "story-1")) == prefix
    compose = commands.compose_argv(root, ["logs"], copy_name="story-1")
    assert isinstance(compose, list) and compose[:7] == [*prefix, "docker", "compose"]


def test_a_saddlebag_secret_with_no_var_fails_before_docker(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _needs_token(root)
    _root_stack(root, {"saddlebag": "environment=local"})
    docker = FakeSaddlebag([{"name": "api-token", "username": None, "description": None,
                             "var": None, "tags": [], "fields": []}])
    outcome = commands.cmd_up(root, ["web"], copy_name="story-1", runner=docker)
    assert not outcome.ok
    assert "api-token" in outcome.message
    assert _up_calls(docker) == []
    assert "api-token" in commands.cmd_check(root, runner=docker).message


def test_saddlebag_vars_are_checked_against_the_names_the_templates_require(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _needs_token(root)
    _root_stack(root, {"saddlebag": "environment=local"})
    assert commands.cmd_check(root, runner=FakeSaddlebag()).ok
    other = FakeSaddlebag([{"name": "x", "username": None, "description": None, "var": "OTHER",
                            "tags": [], "fields": []}])
    checked = commands.cmd_check(root, runner=other)
    assert not checked.ok
    assert "`TOKEN` is required by" in checked.message
    down = commands.cmd_up(root, ["web"], copy_name="story-1", runner=FakeSaddlebag(status=1))
    assert not down.ok
    assert "the daemon is not running" in down.message


def test_a_manifest_without_exec_prefix_reads_as_empty(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _root_stack(root, {"file": ".env"})
    _file(root, ".env", "TOKEN=abc\n")
    outcome = commands.cmd_up(root, ["web"], copy_name="story-1", runner=FakeDocker())
    assert outcome.ok, outcome.message
    copy = runtime.copy_for(root, "story-1")
    assert runtime.exec_prefix(copy) == []
    manifest = runtime.read_manifest(copy.directory)
    manifest.pop("exec_prefix")
    runtime.write_manifest(copy, manifest)
    assert runtime.exec_prefix(copy) == []


def _set_device(root: Path, book: str, device: object) -> None:
    target = root / SERVICES / book / spec.OPS_DIR / spec.STACK_FILE
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    data["device"] = device
    target.write_text(yaml.safe_dump(data), encoding="utf-8")


def test_a_book_reads_its_device_steps_in_order(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    steps = [{"name": "boot", "run": "emulator -avd x", "timeout": 60},
             {"name": "install", "run": "./gradlew installDebug", "working-directory": "app"}]
    _set_device(root, "web", steps)
    catalog = spec.load(root)
    assert catalog.errors == []
    assert catalog.books["web"].device == tuple(steps)


def test_a_device_step_with_an_unknown_key_is_refused(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _set_device(root, "web", [{"name": "boot", "run": "emulator", "cwd": "app"}])
    assert any("device step `boot`: `cwd` is not a device key" in error for error in spec.load(root).errors)


def test_a_device_step_with_no_command_is_refused(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _set_device(root, "web", [{"name": "boot", "timeout": 0}])
    errors = spec.load(root).errors
    assert any("device step `boot`: `run` is not a string" in error for error in errors)
    assert any("device step `boot`: `timeout` is not a positive number of seconds" in error for error in errors)


class Executed(Exception):
    def __init__(self, argv: list[str], env: Mapping[str, str]) -> None:
        super().__init__(argv)
        self.argv = argv
        self.env = env


def _execute(argv: list[str], env: Mapping[str, str]) -> NoReturn:
    raise Executed(argv, env)


def test_exec_under_a_saddlebag_source_runs_the_command_behind_its_prefix(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _root_stack(root, {"saddlebag": "environment=local"})
    with pytest.raises(Executed) as run:
        commands.cmd_exec(root, ["env"], runner=FakeSaddlebag(), execute=_execute, base={"HOME": "/h"})
    assert run.value.argv == ["saddlebag", "exec", "--tag", "environment=local", "--", "env"]
    assert run.value.env == {"HOME": "/h"}


def test_exec_under_a_dotenv_file_sources_it_before_the_command(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _root_stack(root, {"file": ".env"})
    _file(root, ".env", "TOKEN=abc\n")
    with pytest.raises(Executed) as run:
        commands.cmd_exec(root, ["env", "-0"], execute=_execute, base={})
    assert run.value.argv == [
        "sh", "-c", 'set -a; . "$1"; set +a; shift; exec "$@"', "sh", str(root / ".env"), "env", "-0"]


def test_exec_with_no_secret_source_runs_the_bare_command(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    with pytest.raises(Executed) as run:
        commands.cmd_exec(root, ["env"], execute=_execute, base={})
    assert run.value.argv == ["env"]


def test_exec_of_a_missing_dotenv_file_fails_naming_it(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _root_stack(root, {"file": ".env"})
    outcome = commands.cmd_exec(root, ["env"], execute=_execute, base={})
    assert not outcome.ok
    assert str(root / ".env") in outcome.message


def _git(cwd: Path, *argv: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *argv],
        cwd=cwd, check=True, capture_output=True)


def _repo_with_worktree(tmp_path: Path) -> tuple[Path, Path]:
    root = _repo(tmp_path)
    (root / ".git").rmdir()
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "one")
    worktree = tmp_path / "elsewhere" / "wt-1"
    _git(root, "worktree", "add", "-q", str(worktree))
    return root, worktree


def test_a_worktree_and_its_main_checkout_name_the_same_copy(tmp_path: Path) -> None:
    main, worktree = _repo_with_worktree(tmp_path)
    from_worktree = runtime.copy_for(worktree, "evening")
    from_main = runtime.copy_for(main, "evening")
    assert from_worktree.project == from_main.project == "acme-evening"
    assert from_worktree.directory == from_main.directory


def test_a_worktree_lists_the_copies_its_main_checkout_wrote(tmp_path: Path) -> None:
    main, worktree = _repo_with_worktree(tmp_path)
    commands.cmd_up(main, ["web"], copy_name="story-1", runner=FakeDocker())
    assert [copy.name for copy in runtime.copies(worktree)] == ["story-1"]


def test_a_directory_with_no_git_keeps_its_own_name(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert runtime.checkout_home(plain) == plain
    assert runtime.copy_for(plain, "evening").project == "plain-evening"


def test_up_from_a_worktree_names_the_main_checkouts_project(tmp_path: Path) -> None:
    main, worktree = _repo_with_worktree(tmp_path)
    docker = FakeDocker()
    up = commands.cmd_up(worktree, ["web"], copy_name="story-1", runner=docker)
    assert up.ok
    call = next(call for call in docker.calls if "up" in call)
    assert call[call.index("--project-name") + 1] == "acme-story-1"
    manifest = runtime.read_manifest(runtime.copy_for(main, "story-1").directory)
    assert manifest["repo"] == str(main)


def _git_repo(tmp_path: Path) -> Path:
    root = tmp_path / "acme"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "commit", "-q", "--allow-empty", "-m", "init")
    return root


def _manifest(name: str, **fields: object) -> runtime.Copy:
    copy = runtime.Copy(name=name, project=f"acme-{name}", directory=runtime.home() / f"acme-{name}")
    runtime.write_manifest(copy, {"repo": "/nowhere", "copy": name, **fields})
    (copy.directory / render_mod.COMPOSE_FILE).write_text("services: {}\n", encoding="utf-8")
    return copy


class RunningDocker(FakeDocker):
    def __init__(self, running: Sequence[str] = ()) -> None:
        super().__init__()
        self.running = list(running)

    def __call__(self, argv: Sequence[str], *, capture: bool, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        args = list(argv)
        if args[:3] == ["docker", "compose", "ls"]:
            self.calls.append(args)
            rows = [{"Name": name, "Status": "exited(3), running(1)"} for name in self.running]
            return subprocess.CompletedProcess(args, 0, json.dumps(rows), "")
        return super().__call__(argv, capture=capture, stdin=stdin)


def _ago(hours: float) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat(timespec="seconds")


def test_up_records_the_worktree_and_the_time_of_use(tmp_path: Path) -> None:
    root = _git_repo(tmp_path)
    tree = tmp_path / "trees" / "story"
    tree.parent.mkdir()
    _git(root, "worktree", "add", "-q", str(tree), "-b", "story")
    _file(tree, "marker", "x")
    stub = _repo(tmp_path / "stub")
    docker = RunningDocker()
    up = commands.cmd_up(stub, ["web"], copy_name="story-1", cwd=tree, runner=docker)
    manifest = runtime.read_manifest(Path(up.data["directory"]))
    assert manifest["worktree"] == str(tree.resolve())
    assert datetime.fromisoformat(str(manifest["used_at"])).tzinfo is not None
    again = commands.cmd_up(stub, ["web"], copy_name="story-1", cwd=tmp_path, runner=docker)
    assert runtime.read_manifest(Path(again.data["directory"]))["worktree"] == str(tree.resolve())


def test_a_manifest_with_neither_field_is_never_orphaned_and_never_idle() -> None:
    old = {"repo": "/nowhere", "copy": "x", "holder": {}}
    assert not runtime.orphaned(old)
    assert not runtime.idle(old)
    assert commands.cmd_ls_all(runner=RunningDocker()).message == "no copy exists on this machine"
    _manifest("old", repo="/nowhere")
    row = commands.cmd_ls_all(runner=RunningDocker()).data["copies"][0]
    assert row["mark"] == "" and row["worktree"] == ""


def test_a_worktree_missing_from_disk_and_from_git_is_orphaned(tmp_path: Path) -> None:
    root = _git_repo(tmp_path)
    tree = tmp_path / "trees" / "story"
    tree.parent.mkdir()
    _git(root, "worktree", "add", "-q", str(tree), "-b", "story")
    manifest = {"repo": str(root), "worktree": str(tree)}
    assert not runtime.orphaned(manifest)
    shutil.rmtree(tree)
    assert not runtime.orphaned(manifest)
    _git(root, "worktree", "prune")
    assert runtime.orphaned(manifest)


def test_an_unmounted_disk_or_a_missing_repo_is_not_an_orphan(tmp_path: Path) -> None:
    root = _git_repo(tmp_path)
    assert not runtime.orphaned({"repo": str(root), "worktree": str(tmp_path / "unmounted" / "story")})
    (tmp_path / "trees").mkdir()
    gone = {"repo": str(tmp_path / "missing"), "worktree": str(tmp_path / "trees" / "story")}
    assert not runtime.orphaned(gone)
    assert runtime.orphaned({"repo": str(root), "worktree": str(tmp_path / "trees" / "story")})


def test_a_copy_unused_for_a_day_with_no_live_holder_is_idle() -> None:
    assert runtime.idle({"used_at": _ago(25)})
    assert runtime.idle({"used_at": _ago(25), "holder": {}})
    assert runtime.idle({"used_at": _ago(25), "holder": {"pid": _gone_pid(), "started": ""}})
    assert not runtime.idle({"used_at": _ago(23)})
    assert not runtime.idle({"used_at": _ago(25), "holder": runtime.holder_stamp(os.getpid())})


def test_ls_all_lists_every_copy_with_its_mark(tmp_path: Path) -> None:
    root = _git_repo(tmp_path)
    (tmp_path / "trees").mkdir()
    _manifest("lost", repo=str(root), worktree=str(tmp_path / "trees" / "lost"),
              rendered_at=_ago(50), used_at=_ago(2))
    _manifest("slow", repo="/nowhere", worktree="/nowhere/tree", rendered_at=_ago(5),
              used_at=_ago(30))
    _manifest("busy", repo="/nowhere", rendered_at=_ago(1), used_at=_ago(0.5))
    docker = RunningDocker(["acme-slow"])
    listing = commands.cmd_ls_all(runner=docker)
    by_copy = {row["copy"]: row for row in listing.data["copies"]}
    assert by_copy["lost"]["mark"] == "orphaned" and by_copy["lost"]["state"] == "stopped"
    assert by_copy["lost"]["age"] == "2d" and by_copy["lost"]["unused"] == "2h"
    assert by_copy["slow"]["mark"] == "idle" and by_copy["slow"]["state"] == "running"
    assert by_copy["busy"]["mark"] == ""
    lines = {line.split()[1]: line for line in listing.message.splitlines()}
    assert lines["lost"].endswith("orphaned") and lines["slow"].endswith("idle")
    assert lines["busy"].split()[2] == "unknown"


def test_prune_tears_down_orphans_and_stops_idle_running_copies(tmp_path: Path) -> None:
    root = _git_repo(tmp_path)
    (tmp_path / "trees").mkdir()
    lost = _manifest("lost", repo=str(root), worktree=str(tmp_path / "trees" / "lost"),
                     used_at=_ago(1))
    slow = _manifest("slow", used_at=_ago(30))
    asleep = _manifest("asleep", used_at=_ago(30))
    busy = _manifest("busy", used_at=_ago(1))
    docker = RunningDocker(["acme-slow", "acme-busy"])
    dry = commands.cmd_prune(dry_run=True, runner=docker)
    assert sorted(dry.message.splitlines()) == [
        f"acme-lost: orphaned, its worktree {tmp_path / 'trees' / 'lost'} is gone; "
        "tear down and drop its data",
        "acme-slow: idle for 30h; stop and keep its data"]
    assert not [call for call in docker.calls if "down" in call]
    done = commands.cmd_prune(runner=docker)
    assert sorted(done.message.splitlines()) == sorted(dry.message.splitlines())
    downs = {call[call.index("--project-name") + 1]: call for call in docker.calls if "down" in call}
    assert set(downs) == {"acme-lost", "acme-slow"}
    assert "--volumes" in downs["acme-lost"] and "--volumes" not in downs["acme-slow"]
    assert not lost.directory.exists()
    assert slow.directory.is_dir() and asleep.directory.is_dir() and busy.directory.is_dir()


def test_prune_with_nothing_to_do_says_so() -> None:
    _manifest("busy", used_at=_ago(1))
    outcome = commands.cmd_prune(runner=RunningDocker(["acme-busy"]))
    assert outcome.message == "nothing to prune"
    assert outcome.data["pruned"] == []


def test_the_cli_runs_ls_all_and_prune_with_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    _manifest("busy", used_at=_ago(1))
    parser = argparse.ArgumentParser()
    cli.add_parser(parser.add_subparsers(dest="command"))
    listing = parser.parse_args(["env", "ls", "--all", "--json"])
    assert cli.run(listing, tmp_path) == 0
    assert json.loads(capsys.readouterr().out)["copies"][0]["copy"] == "busy"
    pruning = parser.parse_args(["env", "prune", "--dry-run", "--json"])
    assert pruning.dry_run


def test_an_up_reclaims_the_orphaned_and_the_idle_beside_the_dead_holder(tmp_path: Path) -> None:
    root = _git_repo(tmp_path)
    (tmp_path / "trees").mkdir()
    _manifest("lost", repo=str(root), worktree=str(tmp_path / "trees" / "lost"))
    _manifest("slow", used_at=_ago(30))
    docker = RunningDocker(["acme-slow"])
    stub = _repo(tmp_path / "stub")
    up = commands.cmd_up(stub, ["web"], copy_name="story-2", runner=docker)
    assert up.ok, up.message
    assert sorted(row["project"] for row in up.data["pruned"]) == ["acme-lost", "acme-slow"]
    assert "acme-slow: idle for 30h; stop and keep its data" in up.message
    assert not (runtime.home() / "acme-lost").exists()
    assert (runtime.home() / "acme-slow").is_dir()
    assert (runtime.home() / "acme-story-2").is_dir()


def test_an_up_never_prunes_the_copy_it_brings_up(tmp_path: Path) -> None:
    stub = _repo(tmp_path)
    docker = RunningDocker(["acme-story-2"])
    commands.cmd_up(stub, ["web"], copy_name="story-2", runner=docker)
    runtime.write_manifest(runtime.copy_for(stub, "story-2"), {
        **runtime.read_manifest(runtime.copy_for(stub, "story-2").directory),
        "used_at": _ago(40), "worktree": str(tmp_path / "gone")})
    up = commands.cmd_up(stub, ["web"], copy_name="story-2", runner=docker)
    assert up.data["pruned"] == []


def test_a_copy_records_who_started_it_only_when_it_was_not_running(tmp_path: Path) -> None:
    stub = _repo(tmp_path)
    copy = runtime.copy_for(stub, "story-2")
    stamp = runtime.holder_stamp(os.getpid())
    commands.cmd_up(stub, ["web"], copy_name="story-2", holder=os.getpid(), runner=RunningDocker())
    assert runtime.read_manifest(copy.directory)["started_by"] == stamp
    commands.cmd_up(stub, ["web"], copy_name="story-2", holder=_gone_pid(),
                    runner=RunningDocker(["acme-story-2"]))
    assert runtime.read_manifest(copy.directory)["started_by"] == stamp
    commands.cmd_up(stub, ["web"], copy_name="by-hand", runner=RunningDocker())
    assert runtime.read_manifest(runtime.copy_for(stub, "by-hand").directory)["started_by"] == {}


def test_a_running_copy_whose_starter_is_dead_is_adopted_by_the_next_up(tmp_path: Path) -> None:
    stub = _repo(tmp_path)
    copy = runtime.copy_for(stub, "story-2")
    commands.cmd_up(stub, ["web"], copy_name="story-2", holder=_gone_pid(), runner=RunningDocker())
    commands.cmd_up(stub, ["web"], copy_name="story-2", holder=os.getpid(),
                    runner=RunningDocker(["acme-story-2"]))
    assert runtime.read_manifest(copy.directory)["started_by"] == runtime.holder_stamp(os.getpid())


def test_a_running_copy_whose_starter_is_alive_keeps_its_starter(tmp_path: Path) -> None:
    stub = _repo(tmp_path)
    copy = runtime.copy_for(stub, "story-2")
    first = subprocess.Popen(["sleep", "60"])
    try:
        stamp = runtime.holder_stamp(first.pid)
        commands.cmd_up(stub, ["web"], copy_name="story-2", holder=first.pid,
                        runner=RunningDocker())
        commands.cmd_up(stub, ["web"], copy_name="story-2", holder=os.getpid(),
                        runner=RunningDocker(["acme-story-2"]))
        assert runtime.read_manifest(copy.directory)["started_by"] == stamp
    finally:
        first.kill()
        first.wait()


def test_a_running_copy_started_by_hand_stays_empty_when_another_up_holds_it(
    tmp_path: Path,
) -> None:
    stub = _repo(tmp_path)
    copy = runtime.copy_for(stub, "story-2")
    commands.cmd_up(stub, ["web"], copy_name="story-2", runner=RunningDocker())
    commands.cmd_up(stub, ["web"], copy_name="story-2", holder=os.getpid(),
                    runner=RunningDocker(["acme-story-2"]))
    assert runtime.read_manifest(copy.directory)["started_by"] == {}


def test_a_holder_is_cleared_only_by_the_process_that_holds_it(tmp_path: Path) -> None:
    stub = _repo(tmp_path)
    copy = runtime.copy_for(stub, "story-2")
    commands.cmd_up(stub, ["web"], copy_name="story-2", holder=os.getpid(), runner=RunningDocker())
    assert not runtime.release_holder(stub, "story-2", _gone_pid())
    assert runtime.release_holder(stub, "story-2", os.getpid())
    assert runtime.read_manifest(copy.directory)["holder"] == {}


def test_touching_a_copy_that_cannot_be_written_never_raises() -> None:
    runtime.touch_used(runtime.home() / "acme-nothing")
    copy = _manifest("locked")
    (copy.directory / runtime.MANIFEST).chmod(0o400)
    runtime.touch_used(copy.directory)


class BrokenDocker(FakeDocker):
    def __init__(self, returncode: int = 1, error: Exception | None = None) -> None:
        super().__init__()
        self.returncode = returncode
        self.error = error

    def __call__(self, argv: Sequence[str], *, capture: bool, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        args = list(argv)
        if args[:3] == ["docker", "compose", "ls"]:
            if self.error:
                raise self.error
            return subprocess.CompletedProcess(args, self.returncode, "", "Cannot connect to the Docker daemon")
        return super().__call__(argv, capture=capture, stdin=stdin)


def test_a_project_with_exited_and_running_containers_is_running() -> None:
    states = runtime.project_states(RunningDocker(["acme-busy"]))
    assert states.of("acme-busy") == "running"
    assert states.of("acme-gone") == "stopped"
    assert runtime.project_states(FakeDocker()).projects["acme-story-1"] == "exited(3), running(5)"


def test_ls_all_and_ls_list_a_running_copy_as_running(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    docker = FakeDocker()
    assert commands.cmd_up(root, ["web"], copy_name="story-1", runner=docker).ok
    assert commands.cmd_ls(root, runner=docker).data["copies"][0]["status"] == "running"
    assert commands.cmd_ls_all(runner=docker).data["copies"][0]["state"] == "running"


def test_a_copy_whose_containers_are_gone_lists_as_stopped(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert commands.cmd_up(root, ["web"], copy_name="story-1", runner=FakeDocker()).ok
    docker = RunningDocker()
    assert commands.cmd_ls(root, runner=docker).data["copies"][0]["status"] == "stopped"
    assert commands.cmd_ls_all(runner=docker).data["copies"][0]["state"] == "stopped"


def test_a_failing_status_query_lists_unknown_with_the_reason(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert commands.cmd_up(root, ["web"], copy_name="story-1", runner=FakeDocker()).ok
    for docker in (BrokenDocker(), BrokenDocker(error=FileNotFoundError("docker"))):
        everywhere = commands.cmd_ls_all(runner=docker)
        assert everywhere.data["copies"][0]["state"] == "unknown"
        assert everywhere.data["status_error"] in everywhere.message
        listing = commands.cmd_ls(root, runner=docker)
        assert listing.data["copies"][0]["status"] == "unknown"
        assert listing.data["copies"][0]["status_error"]
    assert "Cannot connect" in commands.cmd_ls_all(runner=BrokenDocker()).data["status_error"]


def _artifacts_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "artifacts"
    root.mkdir()
    monkeypatch.setenv(core_config.ARTIFACTS_DIR_ENV, str(root))
    return root


def _stack(root: Path, folder: str, extra: dict | None = None) -> None:
    _file(root, f"{folder}/ops/services/svc.yml.j2", "image: redis:7\n")
    _file(root, f"{folder}/ops/stack.yml", yaml.safe_dump({
        **(extra or {}),
        "services": {"svc": {"about": "a service", "define": "services/svc.yml.j2"}}}))


def test_each_repository_folder_of_the_artifacts_folder_is_a_stack_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _artifacts_root(tmp_path, monkeypatch)
    _stack(root, "services/acme")
    _stack(root, "services/acme/api")
    _file(root, "services/old/service.py", "")
    _stack(root, "services/old")
    catalog = spec.load(root)
    assert catalog.errors == []
    assert sorted(catalog.books) == ["acme", "api"]
    assert catalog.books["acme"].directory == root / "services" / "acme"
    assert catalog.books["api"].directory == root / "services" / "acme" / "api"


def test_a_second_secret_source_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _artifacts_root(tmp_path, monkeypatch)
    _stack(root, "services/acme", {"secrets": {"file": ".env"}})
    _stack(root, "services/globex", {"secrets": {"file": ".env"}})
    catalog = spec.load(root)
    assert catalog.secrets == spec.SecretSpec(file=".env")
    assert catalog.errors == [
        "services/globex/ops/stack.yml: `secrets:` is declared in "
        "services/acme/ops/stack.yml too: one book root has one secret source"]


def test_a_book_below_a_repository_folder_names_the_stack_root_of_that_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _artifacts_root(tmp_path, monkeypatch)
    _stack(root, "services/acme")
    _stack(root, "services/acme/api", {"secrets": {"file": ".env"}})
    errors = spec.load(root).errors
    assert len(errors) == 1
    assert "belongs in the stack root, services/acme/ops/stack.yml" in errors[0]


def _repo_fixture_stack(root: Path, fixture: str) -> None:
    _file(root, "services/acme/ops/services/db.yml.j2",
          "image: mysql:8.0\nvolumes:\n{% for f in fixtures %}\n  - {{ f.path }}:/seed/{{ f.name }}:ro\n{% endfor %}\n")
    _file(root, "services/acme/ops/stack.yml", yaml.safe_dump({
        "default-fixtures": ["seed"],
        "services": {"db": {"about": "the database", "define": "services/db.yml.j2",
                            "fixtures": {"seed": [fixture]}}}}))


def _fixture_world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    root = _real_repo(tmp_path / "artifacts")
    code = _real_repo(tmp_path / "code" / "acme")
    config = tmp_path / "home.toml"
    config.write_text("")
    monkeypatch.setenv(core_config.CONFIG_PATH_ENV, str(config))
    monkeypatch.setenv(core_config.ARTIFACTS_DIR_ENV, str(root))
    return root, code


def _mounted(outcome: commands.EnvOutcome) -> list[str]:
    compose = yaml.safe_load(
        (Path(outcome.data["directory"]) / render_mod.COMPOSE_FILE).read_text(encoding="utf-8"))
    return compose["services"]["acme-db"]["volumes"]


def test_a_repo_fixture_resolves_to_the_file_of_the_code_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, code = _fixture_world(tmp_path, monkeypatch)
    _file(code, "db/seed.sql", "insert into t values (1);\n")
    _repo_fixture_stack(root, "repo://acme/db/seed.sql")
    outcome = commands.cmd_render(root, ["acme"], copy_name="c1", code=code)
    assert outcome.ok, outcome.message
    assert _mounted(outcome) == [f"{code}/db/seed.sql:/seed/seed.sql:ro"]


def test_a_relative_fixture_resolves_beside_the_stack_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, code = _fixture_world(tmp_path, monkeypatch)
    _file(root, "services/acme/ops/fixtures/seed.sql", "insert into t values (1);\n")
    _repo_fixture_stack(root, "fixtures/seed.sql")
    outcome = commands.cmd_render(root, ["acme"], copy_name="c1", code=code)
    assert outcome.ok, outcome.message
    assert _mounted(outcome) == [f"{root}/services/acme/ops/fixtures/seed.sql:/seed/seed.sql:ro"]


def test_a_repo_fixture_naming_an_unknown_repository_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, code = _fixture_world(tmp_path, monkeypatch)
    _repo_fixture_stack(root, "repo://globex/db/seed.sql")
    errors = spec.load(root, code=code).errors
    assert len(errors) == 1
    assert "services/acme/ops/stack.yml" in errors[0]
    assert "globex" in errors[0]
    assert "acme" in errors[0].split("globex", 1)[1]


def test_a_repo_fixture_absent_from_the_code_checkout_is_a_load_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, code = _fixture_world(tmp_path, monkeypatch)
    _repo_fixture_stack(root, "repo://acme/db/seed.sql")
    errors = spec.load(root, code=code).errors
    assert len(errors) == 1
    assert "fixture set `seed`" in errors[0]
    assert "db/seed.sql" in errors[0]
    assert "does not exist" in errors[0]


def _secrets_stack(root: Path, source: dict[str, str]) -> None:
    _file(root, "services/acme/ops/stack.yml", yaml.safe_dump({"secrets": source, "services": {}}))


def test_a_repo_secrets_file_is_read_from_the_code_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, code = _fixture_world(tmp_path, monkeypatch)
    _file(code, "services/ops/.env", "TOKEN=abc\n")
    _secrets_stack(root, {"file": "repo://acme/services/ops/.env"})
    catalog = spec.load(root, code=code)
    assert not catalog.errors
    source = secrets.source_for(catalog, root, commands.run_command)
    assert source.names() == {"TOKEN"}
    assert source.files(runtime.copy_for(root, "c1")) == [(code / "services/ops/.env").resolve()]


def _linked_worktree(code: Path) -> Path:
    linked = code.parent / "acme-linked"
    subprocess.run(["git", "-C", str(code), "worktree", "add", "--quiet", "-b", "linked", str(linked)],
                   check=True, capture_output=True)
    return linked.resolve()


def test_a_repo_secrets_file_missing_from_a_worktree_is_read_from_the_main_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, code = _fixture_world(tmp_path, monkeypatch)
    _file(code, "ops/.env", "TOKEN=main\n")
    linked = _linked_worktree(code)
    _secrets_stack(root, {"file": "repo://acme/ops/.env"})
    catalog = spec.load(root, code=linked)
    assert not catalog.errors
    source = secrets.source_for(catalog, root, commands.run_command)
    assert source.names() == {"TOKEN"}
    assert source.files(runtime.copy_for(root, "c1")) == [(code / "ops/.env").resolve()]


def test_a_repo_secrets_file_of_a_worktree_wins_over_the_main_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, code = _fixture_world(tmp_path, monkeypatch)
    _file(code, "ops/.env", "TOKEN=main\n")
    linked = _linked_worktree(code)
    _file(linked, "ops/.env", "OWN=linked\n")
    _secrets_stack(root, {"file": "repo://acme/ops/.env"})
    catalog = spec.load(root, code=linked)
    assert not catalog.errors
    source = secrets.source_for(catalog, root, commands.run_command)
    assert source.names() == {"OWN"}
    assert source.files(runtime.copy_for(root, "c1")) == [(linked / "ops/.env").resolve()]


def test_a_repo_secrets_file_missing_everywhere_names_both_places(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, code = _fixture_world(tmp_path, monkeypatch)
    linked = _linked_worktree(code)
    _secrets_stack(root, {"file": "repo://acme/ops/.env"})
    catalog = spec.load(root, code=linked)
    assert not catalog.errors
    source = secrets.source_for(catalog, root, commands.run_command)
    with pytest.raises(secrets.SecretError) as raised:
        source.names()
    assert str(linked / "ops/.env") in str(raised.value)
    assert str(code / "ops/.env") in str(raised.value)


def test_a_relative_secrets_file_is_read_under_the_book_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, code = _fixture_world(tmp_path, monkeypatch)
    _file(root, "services/ops/.env", "TOKEN=abc\n")
    _secrets_stack(root, {"file": "services/ops/.env"})
    catalog = spec.load(root, code=code)
    assert not catalog.errors
    source = secrets.source_for(catalog, root, commands.run_command)
    assert source.files(runtime.copy_for(root, "c1")) == [root / "services/ops/.env"]


def test_a_repo_secrets_file_naming_an_unknown_repository_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, code = _fixture_world(tmp_path, monkeypatch)
    _secrets_stack(root, {"file": "repo://globex/services/ops/.env"})
    errors = spec.load(root, code=code).errors
    assert len(errors) == 1
    assert "services/acme/ops/stack.yml" in errors[0]
    assert "globex" in errors[0]
    assert "acme" in errors[0].split("globex", 1)[1]


def _product(root: Path, repository: str, fixture: str = "") -> None:
    fixtures = {"seed": [fixture]} if fixture else {}
    _file(root, f"services/{repository}/ops/services/core.yml.j2", "image: redis:7\n")
    _file(root, f"services/{repository}/ops/stack.yml", yaml.safe_dump({
        "services": {"core": {"about": "the core", "define": "services/core.yml.j2"}}}))
    _file(root, f"services/{repository}/api/ops/services/api.yml.j2", "image: redis:7\n")
    _file(root, f"services/{repository}/api/ops/stack.yml", yaml.safe_dump({
        "services": {"api": {"about": "the API", "define": "services/api.yml.j2",
                             "address": "api", "port": 8080,
                             **({"fixtures": fixtures} if fixtures else {})}}}))


def _two_products(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workspaces: str = "") -> tuple[Path, Path]:
    root = _real_repo(tmp_path / "artifacts")
    code = _real_repo(tmp_path / "code" / "acme")
    config = tmp_path / "home.toml"
    config.write_text(workspaces)
    monkeypatch.setenv(core_config.CONFIG_PATH_ENV, str(config))
    monkeypatch.setenv(core_config.ARTIFACTS_DIR_ENV, str(root))
    _product(root, "acme")
    _product(root, "globex", "repo://globex/db/seed.sql")
    return root, code


def test_a_command_started_for_a_repository_loads_only_its_own_stacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, code = _two_products(tmp_path, monkeypatch)
    catalog = spec.load(root, code=code)
    assert catalog.errors == []
    assert sorted(book.directory.relative_to(root).as_posix() for book in catalog.books.values()) == [
        "services/acme", "services/acme/api"]
    assert spec.load(root).errors != []


def test_a_command_without_a_code_checkout_reports_the_clash_between_products(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _code = _two_products(tmp_path, monkeypatch)
    errors = spec.load(root).errors
    assert any("the book `api` already has" in error for error in errors)


def test_a_command_started_for_a_workspace_loads_the_stacks_of_every_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = _real_repo(tmp_path / "code" / "globex")
    root, code = _two_products(tmp_path, monkeypatch, f'[workspaces]\nshop = ["{member}", "{tmp_path / "code" / "acme"}"]\n')
    shutil.rmtree(root / "services" / "globex" / "api")
    _file(root, "services/globex/ops/stack.yml", yaml.safe_dump({"services": {}}))
    _file(root, "services/globex/web/ops/stack.yml", yaml.safe_dump({"services": {}}))
    catalog = spec.load(root, code=code)
    assert sorted(book.directory.relative_to(root).as_posix() for book in catalog.books.values()) == [
        "services/acme", "services/acme/api", "services/globex", "services/globex/web"]


def test_a_command_started_in_the_artifacts_folder_loads_every_repository_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _code = _two_products(tmp_path, monkeypatch)
    assert [path.name for path in spec.stack_roots(root, code=root)] == ["acme", "globex"]
    assert any("the book `api` already has" in error for error in spec.load(root, code=root).errors)


def test_env_check_from_a_repository_ignores_the_other_products_in_the_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from ostler.cli import main

    _root, code = _two_products(tmp_path, monkeypatch)
    monkeypatch.chdir(code)
    assert main(["env", "check"]) == 0
    assert "globex" not in capsys.readouterr().err


def test_a_book_play_resets_its_copy_with_the_code_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ostler.book.environment import Environment

    _root, code = _two_products(tmp_path, monkeypatch)
    seen: dict[str, object] = {}

    def reset(root: Path, name: str, **kw: object) -> tuple[int, float, str]:
        seen["code"] = kw.get("code")
        return 0, 0.0, ""

    monkeypatch.setattr(commands, "reset", reset)
    Environment("local", {"api": "ostler:story-1"}, root=str(code)).reset()
    assert seen == {"code": code}


def _globex_code(tmp_path: Path) -> Path:
    return _real_repo(tmp_path / "code" / "globex")


def test_two_products_in_one_artifacts_folder_name_different_copies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, acme = _two_products(tmp_path, monkeypatch)
    globex = _globex_code(tmp_path)
    assert runtime.copy_for(root, "story-1", acme).project == "acme-story-1"
    assert runtime.copy_for(root, "story-1", globex).project == "globex-story-1"
    assert runtime.copy_for(root, code=acme).project == "acme-shared"
    assert runtime.copy_for(root, code=globex).project == "globex-shared"
    assert runtime.copy_for(root, code=acme).directory != runtime.copy_for(root, code=globex).directory


def test_a_copy_started_in_the_artifacts_folder_keeps_the_folders_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, acme = _two_products(tmp_path, monkeypatch)
    assert runtime.copy_for(root, "story-1", root).project == runtime.copy_for(root, "story-1").project
    assert runtime.copy_for(root, "story-1").project == "artifacts-story-1"


def test_a_copy_of_a_workspace_run_is_named_after_the_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = _real_repo(tmp_path / "code" / "globex")
    root, acme = _two_products(
        tmp_path, monkeypatch, f'[workspaces]\nshop = ["{member}", "{tmp_path / "code" / "acme"}"]\n')
    assert runtime.copy_for(root, "story-1", acme).project == "shop-story-1"
    assert runtime.copy_for(root, "story-1", member).project == "shop-story-1"


def test_a_root_that_is_not_namespaced_names_its_copy_as_before(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    assert runtime.copy_for(root, "story-1", other).project == "acme-story-1"
    assert runtime.copy_for(root, "story-1").project == "acme-story-1"


def test_up_and_down_with_the_same_code_checkout_name_the_same_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, code = _two_products(tmp_path, monkeypatch)
    docker = FakeDocker()
    up = commands.cmd_up(root, ["api"], copy_name="story-1", runner=docker, code=code)
    assert up.ok, up.message
    copy = runtime.copy_for(root, "story-1", code)
    assert copy.project == "acme-story-1"
    assert (copy.directory / runtime.MANIFEST).is_file()
    assert [held.project for held in runtime.copies(root, code)] == ["acme-story-1"]
    down = commands.cmd_down(root, copy_name="story-1", runner=docker, code=code)
    assert down.ok
    assert not copy.directory.exists()
    projects = {call[call.index("--project-name") + 1] for call in _compose_calls(docker)
                if "--project-name" in call}
    assert projects == {"acme-story-1"}


def test_a_listing_for_one_product_leaves_out_the_copies_of_another(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, acme = _two_products(tmp_path, monkeypatch)
    globex = _globex_code(tmp_path)
    for code in (acme, globex):
        runtime.write_manifest(runtime.copy_for(root, "story-1", code),
                               {"repo": str(root), "copy": "story-1"})
    assert [copy.project for copy in runtime.copies(root, acme)] == ["acme-story-1"]
    assert [copy.project for copy in runtime.copies(root, globex)] == ["globex-story-1"]
    assert len(runtime.copies(root, root)) == 2

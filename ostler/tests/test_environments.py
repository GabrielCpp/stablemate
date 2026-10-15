from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest
import yaml

from ostler import doctor
from ostler.environments import cli, commands, leases, runtime, secrets, spec
from ostler.environments import render as render_mod
from ostler.model import load
from ostler.qa import addresses, runbook

FEATURES = Path("docs/features")


@pytest.fixture(autouse=True)
def _env_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "env-home"
    monkeypatch.setenv(runtime.HOME_ENV, str(home))
    monkeypatch.delenv(addresses.LEASE_ENV, raising=False)
    monkeypatch.delenv(runtime.HOLDER_ENV, raising=False)
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
    web = f"{FEATURES}/web"
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
    target = root / FEATURES / book / spec.OPS_DIR / spec.STACK_FILE
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
    target = root / FEATURES / "web" / spec.OPS_DIR / spec.STACK_FILE
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


def test_doctor_reports_each_stack_problem_on_the_file_it_was_found_in(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert not [f for f in doctor.run(load(root)).findings if f.code == "stack-invalid"]
    _rewrite_stack(root, "web", {"web": {"about": "x", "define": "services/web.yml.j2", "need": ["x"],
                                         "needs": ["api:queue"]}})
    found = [(f.path, f.message) for f in doctor.run(load(root)).findings
             if f.code == "stack-invalid"]
    assert any(path == "docs/features/web/ops/stack.yml"
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


def _gone_pid() -> int:
    finished = subprocess.Popen(["true"])
    finished.wait()
    return finished.pid


def test_a_copy_whose_run_is_gone_is_reclaimed_at_the_next_lease(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    docker = FakeDocker()
    commands.cmd_up(root, ["web"], copy_name="by-hand", runner=docker)
    commands.cmd_up(root, ["web"], copy_name="story-1", holder=_gone_pid(), runner=docker)
    live = leases.up(root, lease="story-2", near=root / FEATURES / "web", holder=os.getpid(),
                     runner=docker)
    assert live is not None and live.ok, live
    assert live.data["reclaimed"] == ["acme-story-1"]
    later = commands.cmd_up(root, ["web"], copy_name="story-3", runner=docker)
    assert later.data["reclaimed"] == []
    assert [copy.name for copy in runtime.copies(root)] == ["by-hand", "story-2", "story-3"]


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
    monkeypatch.setenv(runtime.HOLDER_ENV, env[runtime.HOLDER_ENV])
    up = commands.cmd_up(root, ["web"], copy_name="story-1", runner=FakeDocker())
    assert runtime.read_manifest(Path(up.data["directory"]))["holder"] == \
        runtime.holder_stamp(os.getpid())


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
    _rewrite_stack(root, "web", {"web": {"about": "x", "define": "services/missing.yml.j2"}})
    refused = runbook.cmd_stack_up(root, lease="story-1")
    assert not refused.ok
    assert "do not fit together" in refused.message
    named = runbook.cmd_stack_up(root, name="links-local", lease="story-1")
    assert "do not fit together" not in named.message
    assert runbook.cmd_stack_down(root, lease="story-1").message == "stack torn down"


def _worktree(root: Path) -> Path:
    gitdir = root / ".git" / "worktrees" / "story-1"
    gitdir.mkdir(parents=True)
    _file(gitdir, "commondir", "../..\n")
    tree = root.parent / "worktrees" / "acme-story-1"
    shutil.copytree(root / "docs", tree / "docs")
    _file(tree, ".git", f"gitdir: {gitdir}\n")
    return tree


def test_a_lease_less_bring_up_keeps_the_stack_a_runbook_declares(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)
    _file(root, f"{FEATURES}/api/ops/qa-stack.md", (
        "---\ntype: runbook\ntitle: QA stack\n---\n\n# QA stack\n\n"
        "- driver: web\n- entry-url: http://localhost:18084\n\n"
        "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n"))
    copied: list[str] = []
    monkeypatch.setattr(runbook.leases, "up", lambda _root, *, lease, near: copied.append(lease))
    monkeypatch.setattr(runbook, "bring_up_stacks",
                        lambda manifests, **_kw: [{"ready": "no", "manifest": manifests[-1]}])
    runbook.cmd_stack_up(root)
    assert copied == []
    runbook.cmd_stack_up(root, lease="story-1")
    assert copied == ["story-1"]


def test_a_book_reads_its_paths_from_its_ops_folder(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    catalog = spec.load(root)
    book = catalog.books["web"]
    assert book.directory == root / FEATURES / "web"
    assert book.ops_dir == root / FEATURES / "web" / "ops"
    assert catalog.services["web:gateway"].ops_dir == book.ops_dir
    assert catalog.services["web:gateway"].define == book.ops_dir / "services" / "gateway.yml.j2"


def test_the_stack_root_is_a_book_named_after_the_repo(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _file(root, f"{FEATURES}/ops/services/cache.yml.j2", "image: redis:7\n")
    _file(root, f"{FEATURES}/ops/stack.yml", yaml.safe_dump({"services": {
        "cache": {"about": "the cache", "define": "services/cache.yml.j2"}}}))
    catalog = spec.load(root)
    assert catalog.errors == []
    assert catalog.books["acme"].directory == root / FEATURES
    assert catalog.books["acme"].ops_dir == root / FEATURES / "ops"
    assert "acme:cache" in catalog.services


@pytest.mark.parametrize("book", ["", "web"])
def test_a_stack_file_at_the_old_place_names_where_it_moves_to(tmp_path: Path, book: str) -> None:
    root = _repo(tmp_path)
    folder = root / FEATURES / book if book else root / FEATURES
    old = folder / spec.STACK_FILE
    old.write_text("services: {}\n", encoding="utf-8")
    shown = old.relative_to(root).as_posix()
    moved = (folder / "ops" / spec.STACK_FILE).relative_to(root).as_posix()
    assert (f"{shown}: is the old place: move it to {moved}, whose paths are read from ops/"
            in spec.load(root).errors)
    assert old not in spec.stack_files(root)


def test_doctor_attaches_an_old_place_error_to_the_old_file(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _file(root, f"{FEATURES}/web/stack.yml", "services: {}\n")
    found = [f for f in doctor.run(load(root)).findings if f.code == "stack-invalid"]
    assert [(f.path, f.message) for f in found] == [(
        "docs/features/web/stack.yml",
        "is the old place: move it to docs/features/web/ops/stack.yml, whose paths are read "
        "from ops/")]


def test_a_template_sees_ops_dir_and_no_longer_book_dir(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _file(root, f"{FEATURES}/web/ops/services/web.yml.j2",
          "image: web\nlabels:\n  from: {{ ops_dir }}\n")
    outcome = commands.cmd_render(root, ["web"], copy_name="c1")
    assert outcome.ok, outcome.message
    compose = yaml.safe_load(
        (Path(outcome.data["directory"]) / render_mod.COMPOSE_FILE).read_text(encoding="utf-8"))
    assert compose["services"]["web-web"]["labels"]["from"] == str(root / FEATURES / "web" / "ops")
    _file(root, f"{FEATURES}/web/ops/services/web.yml.j2", "image: {{ book_dir }}\n")
    stale = commands.cmd_render(root, ["web"], copy_name="c1")
    assert not stale.ok
    assert "book_dir" in stale.message


def test_a_service_with_no_about_is_refused_by_name(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _rewrite_stack(root, "web", {"web": {"define": "services/web.yml.j2"}})
    assert ("docs/features/web/ops/stack.yml: service `web`: names no `about:`, "
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
        "  api:api        the HTTP API               api            shared (not running), story-1",
        "  api:db         the database                              shared (not running), story-1",
        "  api:provision  creates the schema                        shared (not running), story-1",
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
    (root / FEATURES).mkdir(parents=True)
    empty = commands.cmd_ls(root, runner=FakeDocker())
    assert empty.ok
    assert empty.message == "no book has an ops/stack.yml"
    runtime.write_manifest(runtime.copy_for(root, "story-9"), {
        "repo": str(root), "copy": "story-9", "targets": ["x:y"]})
    kept = commands.cmd_ls(root, runner=FakeDocker())
    assert kept.message.splitlines() == ["no book has an ops/stack.yml", "story-9  not running  x:y"]


def _book_stack(root: Path, book: str, change: dict) -> None:
    target = root / FEATURES / book / "ops" / spec.STACK_FILE
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    target.write_text(yaml.safe_dump({**data, **change}), encoding="utf-8")


def _root_stack(root: Path, secrets: object) -> None:
    _file(root, f"{FEATURES}/ops/stack.yml", yaml.safe_dump({"secrets": secrets}))


def _needs_token(root: Path) -> None:
    _file(root, f"{FEATURES}/web/ops/services/web.yml.j2",
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
        error.startswith("docs/features/web/ops/stack.yml: `secrets:` belongs in the stack root, "
                         "docs/features/ops/stack.yml: one repo has one secret source")
        and "`file: <path>` or `decrypt: <command>`" in error for error in errors)


def test_the_stack_root_refuses_a_saddlebag_name_and_two_sources(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _root_stack(root, "web-local")
    assert any("`secrets: web-local` names a saddlebag environment" in error
               for error in spec.load(root).errors)
    _root_stack(root, {"file": ".env", "decrypt": "true"})
    assert any("takes exactly one of `file:` or `decrypt:`" in error
               for error in spec.load(root).errors)
    _root_stack(root, {"file": ".env"})
    assert spec.load(root).secrets == spec.SecretSpec(file=".env")


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
    assert runtime.main_checkout(tree) == root
    docker = FakeDocker()
    assert commands.cmd_up(tree, ["api"], copy_name="story-1", runner=docker).ok
    up = _up_calls(docker)[0]
    assert up[up.index("--env-file") + 1] == str(root / ".env")


class FakeDecrypt(FakeDocker):
    def __init__(self, status: int = 0) -> None:
        super().__init__()
        self.status = status

    def __call__(self, argv: Sequence[str], *, capture: bool) -> subprocess.CompletedProcess[str]:
        if argv[0] == "sh":
            self.calls.append(list(argv))
            return subprocess.CompletedProcess(
                list(argv), self.status, "TOKEN=s3cret-value\n" if not self.status else "",
                "\n".join(f"line {n}" for n in range(8)) if self.status else "")
        return super().__call__(argv, capture=capture)


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
    ops = root / FEATURES / "web" / "ops"
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
    ops = root / FEATURES / "web" / "ops"
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
    target = root / FEATURES / "web" / "ops" / spec.STACK_FILE
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
    assert ("docs/features/web/ops/stack.yml: `needs:` names the book `queue`, which no "
            "stack.yml defines") in errors
    assert "docs/features/web/ops/stack.yml: book `web` lists itself in `needs:`" in errors


def test_books_that_need_each_other_form_a_cycle_naming_the_services(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _book_stack(root, "web", {"needs": ["api"]})
    _book_stack(root, "api", {"needs": ["web"]})
    errors = [error for error in spec.load(root).errors if "cycle" in error]
    assert errors
    assert "web:web" in errors[0] and "api:api" in errors[0]


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
    _file(root, f"{FEATURES}/api/ops/services/provision.yml.j2", template)
    _rewrite_stack(root, "api", {"provision": {
        "about": "creates the bucket", "define": "services/provision.yml.j2", "once": True,
        "outputs": ["UPLOAD_BUCKET"]}})
    _file(root, f"{FEATURES}/api/ops/services/api.yml.j2",
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

    def __call__(self, argv: Sequence[str], *, capture: bool) -> subprocess.CompletedProcess[str]:
        args = list(argv)
        if "up" in args and "api-provision" in args:
            directory = Path(args[args.index("--project-directory") + 1])
            self.seen.append(args[args.index("--env-file") + 1]
                             if "--env-file" in args else "")
            target = directory / "outputs" / "api-provision" / "outputs.env"
            target.write_text(self.writes, encoding="utf-8")
        return super().__call__(args, capture=capture)


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

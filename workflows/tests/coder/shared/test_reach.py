"""The lap's check set: which declared services a story's change reaches, and what belongs to none."""
from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from workhorse.pyflow import WorkflowFailed

from workhorse_workflows.coder.shared.reach import owner, resolve_check_set, unit_identities
from workhorse_workflows.coder.shared.schemas.dev import DispatchEntry

Git = Callable[..., subprocess.CompletedProcess]

GO_API = {"api/go.mod": "module example.com/api\n\ngo 1.22\n", "api/auth/token.go": "package auth\n"}
GO_REPORT = {
    "report/go.mod": "module example.com/report\n",
    "report/main.go": 'package main\n\nimport "example.com/api/auth"\n',
}
GO_WEB = {"web/app.ts": 'fetch("/api/auth/login")\nfetch("/api/handlers")\n'}
GO_SERVICES = {
    "api": {"path": "api", "type": "go"},
    "report": {"path": "report", "type": "go"},
    "web": {"path": "web", "type": "ts"},
}


def write_all(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def build(
    tmp_path: Path, git: Git, files: dict[str, str], services: dict[str, dict[str, str]]
) -> Path:
    root = tmp_path / "acme"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    agents = {"repo": {"name": "acme"}, "services": services}
    write_all(root, {**files, "agents.yml": yaml.safe_dump(agents)})
    git(root, "add", "-A")
    git(root, "commit", "-qm", "seed")
    return root


def edit(root: Path, git: Git, files: dict[str, str], committed: bool = True) -> None:
    write_all(root, files)
    if committed:
        git(root, "add", "-A")
        git(root, "commit", "-qm", "feat(api): the change\n\nStory: acme-1")


def entry(root: Path, path: str, type: str = "go") -> DispatchEntry:
    return DispatchEntry(
        service=f"acme::{path}",
        repo="acme",
        cwd=str(root),
        service_path=path,
        type=type,
        plan_file=f"plan-{path}.md",
        label=type,
    )


def check(root: Path, logger: logging.Logger, *plan: DispatchEntry):
    return resolve_check_set(
        logger, tuple(plan), story_slug="the-story", story_id="acme-1", repo_dir=str(root)
    )


def paths_of(result) -> list[str]:
    return [e.service_path for e in result.checks]


def test_a_changed_package_gates_the_service_that_imports_it_by_module_path(
    tmp_path: Path, git: Git, logger: logging.Logger
) -> None:
    root = build(tmp_path, git, {**GO_API, **GO_REPORT, **GO_WEB}, GO_SERVICES)
    edit(root, git, {"api/auth/token.go": "package auth\n// v2\n"})
    plan = entry(root, "api")

    result = check(root, logger, plan)

    assert result.checks[0] == plan
    assert paths_of(result) == ["api", "report"]
    assert result.shared == []


def test_a_private_edit_gates_the_plan_only(
    tmp_path: Path, git: Git, logger: logging.Logger
) -> None:
    files = {**GO_API, **GO_REPORT, **GO_WEB, "api/handlers/h.go": "package handlers\n"}
    root = build(tmp_path, git, files, GO_SERVICES)
    edit(root, git, {"api/handlers/h.go": "package handlers\n// v2\n"})
    plan = entry(root, "api")

    result = check(root, logger, plan)

    assert result.checks == [plan]
    assert result.shared == []


def test_a_relative_import_into_a_shared_directory_gates_the_importer_and_marks_it_shared(
    tmp_path: Path, git: Git, logger: logging.Logger
) -> None:
    files = {
        "packages/web/src/a.ts": 'import { x } from "../../shared/auth";\n',
        "packages/api/src/b.ts": "export const b = 1;\n",
        "packages/shared/auth/x.ts": "export const x = 1;\n",
    }
    services = {
        "web": {"path": "packages/web", "type": "ts"},
        "api": {"path": "packages/api", "type": "ts"},
    }
    root = build(tmp_path, git, files, services)
    edit(root, git, {"packages/shared/auth/x.ts": "export const x = 2;\n"})
    plan = entry(root, "packages/api", "ts")

    result = check(root, logger, plan)

    assert paths_of(result) == ["packages/api", "packages/web"]
    assert result.shared == ["acme::packages/shared/auth"]


def test_a_package_json_name_is_how_a_service_imports_a_sibling_package(
    tmp_path: Path, git: Git, logger: logging.Logger
) -> None:
    files = {
        "packages/ui/package.json": '{"name": "@acme/ui"}\n',
        "packages/ui/src/button.ts": "export const button = 1;\n",
        "packages/web/src/page.ts": 'import { button } from "@acme/ui/button";\n',
    }
    services = {
        "ui": {"path": "packages/ui", "type": "ts"},
        "web": {"path": "packages/web", "type": "ts"},
    }
    root = build(tmp_path, git, files, services)
    edit(root, git, {"packages/ui/src/button.ts": "export const button = 2;\n"})
    plan = entry(root, "packages/ui", "ts")

    result = check(root, logger, plan)

    assert paths_of(result) == ["packages/ui", "packages/web"]


def test_a_pyproject_name_is_how_a_service_imports_a_sibling_library(
    tmp_path: Path, git: Git, logger: logging.Logger
) -> None:
    files = {
        "lib/pyproject.toml": '[project]\nname = "acme-common"\n',
        "lib/acme_common/auth/y.py": "y = 1\n",
        "svc/app.py": "from acme_common.auth import y\n",
    }
    services = {"svc": {"path": "svc", "type": "py"}, "lib": {"path": "lib", "type": "py"}}
    root = build(tmp_path, git, files, services)
    edit(root, git, {"lib/acme_common/auth/y.py": "y = 2\n"})
    plan = entry(root, "lib", "py")

    result = check(root, logger, plan)

    assert paths_of(result) == ["lib", "svc"]


def test_a_string_literal_that_spells_a_package_name_is_not_an_import(
    tmp_path: Path, git: Git, logger: logging.Logger
) -> None:
    files = {
        "packages/web/package.json": '{"name": "acme-web"}\n',
        "packages/web/src/page.ts": "export const page = 1;\n",
        "infra/index.ts": 'export const account = { accountId: "acme-web" };\n'
        'if (app.name === "packages/web/src") {}\n',
    }
    services = {
        "web": {"path": "packages/web", "type": "ts"},
        "infra": {"path": "infra", "type": "ts"},
    }
    root = build(tmp_path, git, files, services)
    edit(root, git, {"packages/web/src/page.ts": "export const page = 2;\n"})
    plan = entry(root, "packages/web", "ts")

    result = check(root, logger, plan)

    assert result.checks == [plan]


def test_an_uncommitted_edit_counts(tmp_path: Path, git: Git, logger: logging.Logger) -> None:
    root = build(tmp_path, git, {**GO_API, **GO_REPORT, **GO_WEB}, GO_SERVICES)
    edit(root, git, {"api/auth/token.go": "package auth\n// v2\n"}, committed=False)

    result = check(root, logger, entry(root, "api"))

    assert paths_of(result) == ["api", "report"]


def test_a_plan_entry_spelled_with_a_trailing_slash_is_not_added_twice(
    tmp_path: Path, git: Git, logger: logging.Logger
) -> None:
    root = build(tmp_path, git, {**GO_API, **GO_REPORT, **GO_WEB}, GO_SERVICES)
    edit(root, git, {"api/auth/token.go": "package auth\n// v2\n"})
    plan = [entry(root, "api/"), entry(root, "report/")]

    result = check(root, logger, *plan)

    assert result.checks == plan


def test_a_repo_whose_services_declare_no_path_gates_the_plan_only(
    tmp_path: Path, git: Git, logger: logging.Logger
) -> None:
    root = build(tmp_path, git, {**GO_API, **GO_REPORT}, {"api": {"type": "go"}})
    edit(root, git, {"api/auth/token.go": "package auth\n// v2\n"})
    plan = entry(root, ".")

    result = check(root, logger, plan)

    assert result.checks == [plan]
    assert result.shared == []


def test_a_docs_entry_s_repo_is_not_scanned(tmp_path: Path, logger: logging.Logger) -> None:
    root = tmp_path / "book"
    root.mkdir()
    plan = DispatchEntry(service="book", repo="book", cwd=str(root), service_path=".", type="docs")

    result = resolve_check_set(logger, (plan,), story_id="acme-1", repo_dir=str(root))

    assert result.checks == [plan]


def test_a_repository_with_no_story_base_stops_the_run(
    tmp_path: Path, git: Git, logger: logging.Logger
) -> None:
    root = tmp_path / "acme"
    root.mkdir()
    git(root, "init", "-q", "-b", "work")
    write_all(
        root,
        {"agents.yml": yaml.safe_dump({"repo": {"name": "acme"}, "services": GO_SERVICES}), "a.txt": "a\n"},
    )
    git(root, "add", "-A")
    git(root, "commit", "-qm", "seed")

    with pytest.raises(WorkflowFailed, match="no story base in"):
        check(root, logger, entry(root, "api"))


def test_the_longest_declared_path_owns_a_file() -> None:
    declared = ["packages", "packages/web"]

    assert owner("packages/web/src/a.ts", declared) == "packages/web"
    assert owner("packages/shared/x.ts", declared) == "packages"
    assert owner("packages/webby/x.ts", ["packages/web"]) is None
    assert owner("anything/x.ts", ["."]) == "."


def test_a_deleted_directory_still_yields_its_manifest_identity(tmp_path: Path) -> None:
    write_all(tmp_path, {"api/go.mod": "module example.com/api\n"})

    found = unit_identities(tmp_path, "api/gone")

    assert '"example.com/api/gone"' in found
    assert 'from "api/gone"' in found
    assert "from api.gone " in found

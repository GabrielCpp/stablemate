"""Render the services one bring-up needs into a single compose file and its helper files."""

from __future__ import annotations

import re
import shutil
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jinja2
import yaml

from ostler.environments.spec import Catalog, Service

COMPOSE_FILE = "compose.yml"
OUTPUTS_DIR = "outputs"
OUTPUTS_FILE = "outputs.env"
OUTPUTS_VAR = "STABLEMATE_OUTPUTS"
OUTPUTS_MOUNT = "/stablemate/outputs"
OWNED_KEYS = ("depends_on", "ports", "container_name")
_NAMED_VOLUME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


class RenderError(ValueError):
    """A template that does not render to a compose service ostler can place."""


@dataclass(frozen=True)
class Copy:
    """One running instance of the stack: its name, its compose project and its directory."""

    name: str
    project: str
    directory: Path

    @property
    def shared(self) -> bool:
        return self.name == SHARED


SHARED = "shared"


@dataclass
class Rendered:
    """What one bring-up writes into its copy's directory."""

    compose: dict[str, Any]
    files: dict[Path, str] = field(default_factory=dict)
    copies: dict[Path, Path] = field(default_factory=dict)
    defines: dict[str, str] = field(default_factory=dict)
    shared_dirs: list[Path] = field(default_factory=list)


def fixture_sets(catalog: Catalog, services: Sequence[Service], chosen: Sequence[str]) -> list[str]:
    """The fixture sets to load: *chosen*, or the defaults of every book *services* come from."""
    if chosen:
        declared = {name for service in services for name in service.fixtures}
        unknown = [name for name in chosen if name not in declared]
        if unknown:
            raise RenderError(f"no service in this stack declares the fixture set "
                              f"{', '.join(f'`{name}`' for name in unknown)}")
        return list(chosen)
    books = dict.fromkeys(service.book for service in services)
    return list(dict.fromkeys(
        name for book in books for name in catalog.books[book].default_fixtures))


def render(
    catalog: Catalog, services: Sequence[Service], copy: Copy, *, repo: Path,
    fixtures: Sequence[str],
) -> Rendered:
    """The compose file and helper files that bring *services* up as *copy*."""
    environment = jinja2.Environment(
        undefined=jinja2.StrictUndefined, keep_trailing_newline=True, autoescape=False)
    rendered = Rendered(compose={"name": copy.project, "services": {}, "volumes": {}})
    blocks: dict[str, dict[str, Any]] = {}
    for service in services:
        context = _context(catalog, service, copy, repo=repo, fixtures=fixtures)
        _place_files(rendered, environment, service, copy, context)
        block = _block(rendered, environment, service, context)
        rendered.compose["volumes"].update(_scope_volumes(service, block))
        if service.outputs:
            _mount_outputs(rendered, service, copy, block)
        blocks[service.ref] = block
    for service in services:
        block = blocks[service.ref]
        depends = {
            catalog.services[need].compose_name: {"condition": _condition(
                catalog.services[need], blocks[need])}
            for need in service.needs
        }
        if depends:
            block["depends_on"] = depends
        if service.address:
            host = str(service.host_port) if copy.shared and service.host_port else ""
            block["ports"] = [f"127.0.0.1:{host}:{service.port}"]
        block.setdefault("labels", {})
        if isinstance(block["labels"], dict):
            block["labels"]["stablemate.ostler.service"] = service.ref
        rendered.compose["services"][service.compose_name] = block
    if not rendered.compose["volumes"]:
        del rendered.compose["volumes"]
    rendered.files[copy.directory / COMPOSE_FILE] = yaml.safe_dump(
        rendered.compose, sort_keys=False, default_flow_style=False)
    return rendered


def write(rendered: Rendered) -> list[Path]:
    """Write every rendered file and byte copy, replacing what the last render of this copy left."""
    for directory in rendered.shared_dirs:
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o777)
    for target, text in rendered.files.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    for target, source in rendered.copies.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return [*rendered.files, *rendered.copies]


def outputs_dir(copy: Copy, service: Service) -> Path:
    """The host folder a job's `$STABLEMATE_OUTPUTS` file is written in."""
    return copy.directory / OUTPUTS_DIR / service.compose_name


def _mount_outputs(rendered: Rendered, service: Service, copy: Copy, block: dict[str, Any]) -> None:
    host = outputs_dir(copy, service)
    rendered.shared_dirs.append(host)
    mounts = block.setdefault("volumes", [])
    if not isinstance(mounts, list):
        raise RenderError(f"{service.define} sets `volumes` that is not a list, so ostler cannot "
                          "add the outputs mount")
    mounts.append(f"{host}:{OUTPUTS_MOUNT}")
    value = f"{OUTPUTS_MOUNT}/{OUTPUTS_FILE}"
    environment = block.setdefault("environment", {})
    if isinstance(environment, dict):
        if OUTPUTS_VAR in environment:
            raise RenderError(f"{service.define} sets `{OUTPUTS_VAR}`, which ostler writes "
                              "for a job that declares `outputs:`")
        environment[OUTPUTS_VAR] = value
    elif isinstance(environment, list):
        if any(str(item).partition("=")[0] == OUTPUTS_VAR for item in environment):
            raise RenderError(f"{service.define} sets `{OUTPUTS_VAR}`, which ostler writes "
                              "for a job that declares `outputs:`")
        environment.append(f"{OUTPUTS_VAR}={value}")
    else:
        raise RenderError(f"{service.define} sets an `environment` that is neither a mapping "
                          "nor a list")


def _place_files(
    rendered: Rendered, environment: jinja2.Environment, service: Service, copy: Copy,
    context: dict[str, Any],
) -> None:
    base = copy.directory / service.compose_name
    for target, source in service.files.items():
        if source.is_dir():
            for path in sorted(item for item in source.rglob("*") if item.is_file()):
                relative = path.relative_to(source).as_posix()
                if path.suffix == ".j2":
                    rendered.files[base / target / relative.removesuffix(".j2")] = _render_file(
                        environment, path, context)
                else:
                    rendered.copies[base / target / relative] = path
        elif source.suffix == ".j2":
            rendered.files[base / target] = _render_file(environment, source, context)
        else:
            rendered.copies[base / target] = source


def _context(
    catalog: Catalog, service: Service, copy: Copy, *, repo: Path, fixtures: Sequence[str]
) -> dict[str, Any]:
    def service_name(ref: str) -> str:
        qualified = ref if ":" in ref else f"{service.book}:{ref}"
        if qualified not in catalog.services:
            raise RenderError(f"{service.ref} names `{ref}`, which no book defines")
        return catalog.services[qualified].compose_name

    files = [path for name in fixtures for path in service.fixtures.get(name, ())]
    return {
        "copy": copy.name,
        "project": copy.project,
        "shared": copy.shared,
        "repo": str(repo),
        "ops_dir": str(service.ops_dir),
        "env_dir": str(copy.directory),
        "dir": str(copy.directory / service.compose_name),
        "fixtures": [{"path": str(path), "name": path.name} for path in files],
        "service": service_name,
    }


def _render_file(environment: jinja2.Environment, template: Path, context: dict[str, Any]) -> str:
    try:
        return environment.from_string(template.read_text(encoding="utf-8")).render(**context)
    except jinja2.TemplateError as exc:
        raise RenderError(f"{template}: {exc}") from exc


def _block(
    rendered: Rendered, environment: jinja2.Environment, service: Service, context: dict[str, Any]
) -> dict[str, Any]:
    text = _render_file(environment, service.define, context)
    rendered.defines[service.ref] = text
    try:
        block = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RenderError(f"{service.define} does not render to YAML: {exc}") from exc
    if not isinstance(block, dict):
        raise RenderError(f"{service.define} does not render to one compose service mapping")
    owned = [key for key in OWNED_KEYS if key in block]
    if owned:
        raise RenderError(
            f"{service.define} sets {', '.join(f'`{key}`' for key in owned)}, which ostler "
            f"writes from stack.yml: `needs:` for the order, `address:` and `port:` for a port")
    return block


def _scope_volumes(service: Service, block: dict[str, Any]) -> dict[str, dict[str, Any]]:
    declared: dict[str, dict[str, Any]] = {}
    mounts = block.get("volumes")
    if not isinstance(mounts, list):
        return declared
    scoped: list[Any] = []
    for mount in mounts:
        if isinstance(mount, str):
            source, sep, rest = mount.partition(":")
            if sep and _NAMED_VOLUME.fullmatch(source):
                name = f"{service.compose_name}-{source}"
                declared[name] = {}
                mount = f"{name}:{rest}"
        elif isinstance(mount, dict) and mount.get("type", "volume") == "volume":
            source = str(mount.get("source") or "")
            if _NAMED_VOLUME.fullmatch(source):
                name = f"{service.compose_name}-{source}"
                declared[name] = {}
                mount = {**mount, "source": name}
        scoped.append(mount)
    block["volumes"] = scoped
    return declared


def _condition(service: Service, block: dict[str, Any]) -> str:
    if service.once:
        return "service_completed_successfully"
    if "healthcheck" in block:
        return "service_healthy"
    return "service_started"

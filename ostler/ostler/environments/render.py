"""Render the services one bring-up needs into a single compose file and its helper files."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jinja2
import yaml

from ostler.environments.spec import Catalog, Service

COMPOSE_FILE = "compose.yml"
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
        for template in service.render:
            target = copy.directory / service.compose_name / _rendered_name(template)
            rendered.files[target] = _render_file(environment, template, context)
        block = _block(environment, service, context)
        rendered.compose["volumes"].update(_scope_volumes(service, block))
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
    """Write every rendered file, replacing what the last render of this copy left."""
    for target, text in rendered.files.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return list(rendered.files)


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
        "book_dir": str(service.book_dir),
        "dir": str(copy.directory / service.compose_name),
        "fixtures": [{"path": str(path), "name": path.name} for path in files],
        "service": service_name,
    }


def _render_file(environment: jinja2.Environment, template: Path, context: dict[str, Any]) -> str:
    try:
        return environment.from_string(template.read_text(encoding="utf-8")).render(**context)
    except jinja2.TemplateError as exc:
        raise RenderError(f"{template}: {exc}") from exc


def _rendered_name(template: Path) -> str:
    return template.name.removesuffix(".j2")


def _block(environment: jinja2.Environment, service: Service, context: dict[str, Any]) -> dict[str, Any]:
    text = _render_file(environment, service.define, context)
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

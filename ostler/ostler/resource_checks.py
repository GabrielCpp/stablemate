"""`ostler doctor`'s checks on `resource` pages, request steps, borrow and release fixtures, and a claim's `observe:` rows."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ostler import refs as refs_mod, registry
from ostler.finding import Finding
from ostler.model import Graph, UINode
from ostler.qa import book_fixtures, runbook as runbook_mod

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_REQUEST = re.compile(r"^(GET|POST|PUT|PATCH|DELETE) /\S*$")
_OBSERVATION_REF = re.compile(r"@([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)")
_WITHIN = re.compile(r"\bwithin\s*=")
_THIS_MACHINE = re.compile(r"\b(?:localhost|127\.0\.0\.1|0\.0\.0\.0)\b|\[::1\]")
_HTTP_ONLY = ("binary", "secrets", "install")
_CLI_ONLY = ("base", "credential")


def _value(node: UINode, key: str) -> str:
    return runbook_mod.bullet_value(node.meta, key)


def _said(node: UINode, message: str) -> str:
    return f"{node.id}: {message}"


def _where(node: UINode, rel: str, key: str = "") -> dict[str, Any]:
    return {"path": rel, "line": node.line, "ref": refs_mod.bullet_ref(node.id, key) if key else node.id}


def _step_form(step: UINode, reach: str) -> bool:
    return bool(_value(step, "request" if reach == "http" else "run"))


def _check_reach(node: UINode, rel: str, f: list[Finding]) -> str:
    reach = _value(node, "reach")
    if reach not in ("http", "cli"):
        f.append(Finding("error", "resource-reach-shape", _said(node, f"`reach: {reach}` is neither `http` nor `cli`, so no harness knows how to talk to it"),
                **_where(node, rel, "reach")))
        return ""
    if reach == "http" and not _value(node, "base"):
        f.append(Finding("error", "resource-reach-shape", _said(node, "an `http` resource states its `base:` URL, which `$NAME` may take from the harness's "
                          "environment"),
                **_where(node, rel, "base")))
    if reach == "cli" and not _value(node, "binary"):
        f.append(Finding("error", "resource-reach-shape", _said(node, "a `cli` resource states the `binary:` it runs, which the harness looks for on its PATH"),
                **_where(node, rel, "binary")))
    excluded = _HTTP_ONLY if reach == "http" else _CLI_ONLY
    for key in excluded:
        if node.meta.get(key):
            f.append(Finding("error", "resource-reach-shape", _said(node, f"`{key}:` belongs to a {'cli' if reach == 'http' else 'http'} resource, "
                              f"and this one is `reach: {reach}`"),
                **_where(node, rel, key)))
    credential = book_fixtures._properties(node, "credential")
    if credential and not (credential.get("header") and credential.get("secret")):
        f.append(Finding("error", "resource-reach-shape", _said(node, "`credential:` states both a `header:` and the `secret:` that holds its value"),
                **_where(node, rel, "credential")))
    secrets = [credential.get("secret", ""), *book_fixtures._declared_secrets(node)]
    for name in secrets:
        if name and not _ENV_NAME.match(name):
            f.append(Finding("error", "resource-reach-shape", _said(node, f"secret {name!r} is not an environment variable name, and only the NAME belongs here"),
                **_where(node, rel, "credential")))
    base = _value(node, "base")
    if reach == "http" and _THIS_MACHINE.search(base):
        f.append(Finding("error", "fixture-probe-local", _said(node, f"`base: {base}` is a service on this machine. A resource is an outside service only a "
                          f"person can supply, and whatever answers on this machine may be someone else's. Start a "
                          f"service of your own in the runbook instead"),
                **_where(node, rel, "base")))
    return reach


def _check_steps(graph: Graph, node: UINode, rel: str, reach: str, f: list[Finding]) -> None:
    steps = runbook_mod.steps_of(graph, node)
    probes = [s for s in steps if s.data.get("container") == "Probe"]
    if len(probes) != 1:
        f.append(Finding("error", "resource-probe-shape", _said(node, f"`## Probe` holds {len(probes)} steps and must hold exactly one"),
                **_where(node, rel)))
    for step in steps:
        container = step.data.get("container")
        kind = _value(step, "kind")
        wanted = "probe" if container == "Probe" else "observe"
        problem = None
        key = ""
        if kind != wanted:
            problem = f"a step under `## {container}` is `kind: {wanted}`, and this one is `kind: {kind}`"
            key = "kind"
        elif reach and not _step_form(step, reach):
            problem = f"a {reach} resource's step states `{'request' if reach == 'http' else 'run'}:`"
            key = "request" if reach == "http" else "run"
        if problem and container == "Probe":
            f.append(Finding("error", "resource-probe-shape", _said(step, problem), **_where(step, rel, key)))
        elif problem:
            f.append(Finding("error", "resource-observation-shape", _said(step, problem), **_where(step, rel, key)))
        if container == "Observations" and _value(step, "request").split(" ")[0].upper() not in ("", "GET"):
            f.append(Finding("error", "resource-observation-shape", _said(step, "an observation reads, so its `request:` is a GET"),
                **_where(step, rel, "request")))


def check_resources(graph: Graph, rel_of, f: list[Finding]) -> None:
    """Every resource page: its reach, its probe and its observations."""
    for node in graph.ui_nodes_of_type("resource"):
        rel = rel_of(graph, node)
        reach = _check_reach(node, rel, f)
        _check_steps(graph, node, rel, reach, f)


def check_request_step(graph: Graph, step: UINode, rel: str, f: list[Finding]) -> None:
    """A step's `request:`, `body:` and `on:` agree with each other and with the resource's reach."""
    request, on, run = _value(step, "request"), _value(step, "on"), _value(step, "run")
    if request and not _REQUEST.match(request):
        f.append(Finding("error", "step-request-shape", _said(step, f"`request: {request}` is not `<METHOD> /path` with GET, POST, PUT, PATCH or DELETE"),
                **_where(step, rel, "request")))
    if request and run:
        f.append(Finding("error", "step-request-shape", _said(step, "a step sends a `request:` or runs a `run:`, not both"),
                **_where(step, rel)))
    if request and not on:
        f.append(Finding("error", "step-request-shape", _said(step, "a `request:` goes to the resource named by `on:`"),
                **_where(step, rel, "request")))
    if on and not (request or run):
        f.append(Finding("error", "step-request-shape", _said(step, "`on:` names a resource, and the step sends a "
                          "`request:` or runs a `run:` against it"),
                **_where(step, rel, "on")))
    body = _value(step, "body")
    if body:
        try:
            ok = isinstance(json.loads(re.sub(r"\$\{?\w+\}?|@[\w-]+\.\w+", "0", body)), dict)
        except ValueError:
            ok = False
        if not ok:
            f.append(Finding("error", "step-request-shape", _said(step, "`body:` is a JSON object"),
                **_where(step, rel, "body")))
    if on:
        stem = book_fixtures.on_stem(on)
        target = next((n for n in graph.ui_nodes_of_type("resource") if Path(n.id).stem == stem), None)
        reach = _value(target, "reach") if target is not None else ""
        if (request and reach == "cli") or (run and reach == "http"):
            f.append(Finding("error", "step-reach-mismatch", _said(step, f"`{'request' if request else 'run'}:` cannot go to `{stem}`, a {reach} resource"),
                **_where(step, rel, "on")))
    kind = _value(step, "kind")
    if kind in ("borrow", "release") and not on:
        f.append(Finding("error", "step-request-shape", _said(step, f"a `{kind}` step names its resource with `on:`"),
                **_where(step, rel, "kind")))


def check_lifetimes(node: UINode, steps: list[UINode], rel: str, f: list[Finding]) -> None:
    """A fixture that borrows is built per scenario, and one that releases borrows first."""
    kinds = {_value(step, "kind") for step in steps}
    if "borrow" in kinds and _value(node, "lifetime") != "scenario":
        f.append(Finding("error", "fixture-borrow-lifetime", _said(node, "a `borrow` step leases from a resource that gets the lease back when the scenario ends, "
                          "so each scenario takes its own. Declare `lifetime: scenario`"),
                **_where(node, rel, "lifetime")))
    if "release" in kinds and "borrow" not in kinds:
        f.append(Finding("error", "fixture-release-without-borrow", _said(node, "a `release` step gives back what a `borrow` step took, and this fixture has no `borrow` "
                          "step"),
                **_where(node, rel)))


def check_observations(resources: Mapping[str, Mapping[str, Any]], node: UINode, rel: str, f: list[Finding]) -> None:
    """A claim's `observe:` names a resource observation, and only rows held on one wait with `within=`."""
    held = registry.attributed_observations(node.type, node.bullet_order, node.combiners)
    for entries in held.values():
        for value, _ in entries:
            named = _OBSERVATION_REF.fullmatch(value.strip())
            if named is None:
                f.append(Finding("error", "unparsed-observation", _said(node, f"`observe: {value}` is not `@<resource>.<observation>`"),
                **_where(node, rel, "observe")))
                continue
            page = resources.get(named.group(1))
            if page is None:
                f.append(Finding("error", "unknown-observation", _said(node, f"`observe: {value}` names no resource page called `{named.group(1)}`"),
                **_where(node, rel, "observe")))
            elif named.group(2) not in page["observations"]:
                f.append(Finding("error", "unknown-observation", _said(node, f"`observe: {value}` names an observation `{page['page']}` does not hold under "
                                  f"`## Observations`"),
                **_where(node, rel, "observe")))
    contract, per_claim = registry.attributed_check_bullets(node.type, node.bullet_order, node.combiners)
    for rows in (contract, *per_claim.values()):
        for index, value in rows:
            if _WITHIN.search(value):
                f.append(Finding("error", "within-off-observation", _said(node, f"`verify:{index}` ({value}) waits with `within=`, and only a row held on an "
                                  f"`observe:` has anything to wait for. A response is read once"),
                **_where(node, rel, "verify")))

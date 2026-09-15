"""Compile a QA plan skeleton out of the book, without reading the implementation.

A plan written by looking at the code tests what the code already does. The book is the
only artefact that says what the code is *supposed* to do, and — unlike the code — it says
it in a grammar: `verify:` values are parsed calls (`checks.parse_check`), `route:` and
`entry:` are addresses, and `attributed_checks` already binds each call to the one claim it
observes. That is enough to emit the assertion half of a plan mechanically, with every
`covers=` list correct by construction rather than by an author's recollection.

What the book does *not* carry is the arrangement: how to reach the state the assertion
observes, in what order, with which fixture. Those come out as `TODO` markers naming the
obligation they block, and they are the only thing left for a human or a model to fill.

The count of markers is the point as much as the plan is. An obligation that is owed live
evidence and declares no check is a claim the book asserts and does not say how to observe;
a compiled plan that comes back thin is a measurement of book construction, taken without
an agent turn and without ever opening the implementation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ostler.qa import references
from ostler.qa.outcome import QaOutcome


@dataclass(frozen=True)
class Gap:
    """One obligation left uncompiled, and why — `compile_plan`'s structured gap report.

    `checkpoints=[]` and `forbid=[]` are not gaps: they are always emitted, for every
    scenario, whether or not the book gave a reason — there is nothing conditional to
    report. Everything here is instead a fact compile.py discovered about one obligation
    while trying to compile it, in the vocabulary `doctor` reads rather than redefines:
    `unresolved-precondition` for a state the plan cannot yet reach (a missing fixture, an
    unresolved reference, a template variable, a request body the book never wrote), and
    `uncompilable-claim` for a node with no action to observe at all — no fixture or
    capture could supply one, so it is not a precondition gap.
    """
    obligation_id: str
    kind: str
    detail: str

#: What each check is handed. `http_status` and `conflict_on_stale` read a response — status
#: line, headers, problem body — so the compiled call takes the response object. `json_path`
#: walks a decoded document, `visible` addresses the page. Everything else observes a subject
#: the scenario must already be holding: a record read before *and* after, a key inventory, an
#: event log. The book names that subject and not where it came from, which is exactly the
#: arrangement it does not carry, so those compile to a marker rather than to a call whose
#: operand would have to be invented.
_RESPONSE_CHECKS = frozenset({"http_status", "conflict_on_stale"})
_BODY_CHECKS = frozenset({"json_path"})
_PAGE_CHECKS = frozenset({"visible"})

_ROUTE = re.compile(r"^\s*`?\s*(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(\S+?)\s*`?\s*$", re.I)
_IDENT = re.compile(r"[^0-9a-zA-Z]+")


def _route(obligation: dict[str, Any]) -> tuple[str, str] | None:
    """The HTTP method and path template this obligation's node is addressed by."""
    for value in obligation.get("locators", {}).get("route", []):
        matched = _ROUTE.match(value)
        if matched:
            return matched.group(1).upper(), matched.group(2)
    return None


def _concrete_path(rows: list[dict[str, Any]]) -> str | None:
    """A real path from a declared check, preferred over the route's `{id}` template.

    `http_status(409, title="Stale Policy", path="/api/policies/pn-1001")` names the exact
    request the book expects that refusal from. Substituting a path variable is guesswork;
    reading the one the book already wrote is not.
    """
    for row in rows:
        path = row.get("args", {}).get("path")
        if isinstance(path, str) and path.startswith("/"):
            return path
    return None


def _expect_status(rows: list[dict[str, Any]]) -> int | None:
    for row in rows:
        if row.get("name") == "http_status":
            code = row.get("args", {}).get("code")
            if isinstance(code, int):
                return code
    return None


def _lit(value: Any) -> str:
    """A Python literal spelled the way the repo's formatter would spell it.

    `repr` picks single quotes, which every other plan in the tree does not use; the
    compiled file has to read like one an author wrote or the diff against a filled-in
    version is all quotation marks. `json.dumps` picks the right quotes and the wrong
    booleans — `absent=false` is the book's spelling and a `NameError` in Python — so the
    two literals JSON and Python disagree about are spelled here.
    """
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, list):
        return "[" + ", ".join(_lit(item) for item in value) + "]"
    return json.dumps(value)


def _kwargs(args: dict[str, Any]) -> str:
    """Render check arguments, wrapping only the literals a reference was found in.

    `qa.resolve(...)` is the harness's one explicit substitution entry point (Fix 2) — a
    literal with no `@node.key`/`$name` embedded in it stays a plain literal, since wrapping
    it would cost nothing today but would ask the harness to scan it every run for a
    reference it will never contain.
    """
    parts = []
    for name, value in args.items():
        if isinstance(value, str) and references.find_references(value):
            parts.append(f", {name}=qa.resolve({_lit(value)})")
        else:
            parts.append(f", {name}={_lit(value)}")
    return "".join(parts)


def _slug(path: str) -> str:
    stem = path.rsplit("/", 1)[-1].removesuffix(".md")
    ident = _IDENT.sub("_", stem).strip("_").lower()
    return ident or "book"


def _owed(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [o for o in context.get("obligations", []) if o.get("required", True)]


def compile_plan(
    context: dict[str, Any],
    *,
    story: str,
    run_id: str | None = None,
    base_url: str = "http://localhost:8000",
) -> str:
    """Render a `qa_plan.py` skeleton covering every obligation the change owes live proof.

    The plan is not expected to pass as emitted — a POST whose body the book never wrote
    cannot be. It is expected to *validate*: `ostler qa validate` reports zero uncovered
    obligations against it exactly when the book declared a check for everything it owes.
    """
    source, _gaps = compile_plan_gaps(context, story=story, run_id=run_id, base_url=base_url)
    return source


def compile_plan_gaps(
    context: dict[str, Any],
    *,
    story: str,
    run_id: str | None = None,
    base_url: str = "http://localhost:8000",
) -> tuple[str, list[Gap]]:
    """`compile_plan`'s source, plus the structured gap report it compiled alongside it.

    Same rendering, same TODO markers in the source — this is the one place that also
    hands back *why* each conditional TODO fired, as `(obligation id, gap kind, detail)`,
    for a caller (`doctor`) that wants to map book debt to obligations without re-parsing
    the compiled Python.
    """
    gaps: list[Gap] = []
    owed = _owed(context)
    lines: list[str] = [
        "# Compiled from the book by `ostler qa compile-plan`. Every `covers=` below is the",
        "# obligation the book itself attributed the check to. Fill the TODO markers from the",
        "# story, the fixtures and the flows — not from the implementation, which is the thing",
        "# under test and cannot also be the specification it is tested against.",
        "",
        "from ostler_qa import Qa, plan, scenario, target",
        "",
        "",
        f"plan(run_id={_lit(run_id or f'qa-{story}')}, story={_lit(story)})",
        "",
        f'api = target("api", driver="python", base_url={_lit(base_url)})',
        "",
    ]

    by_source: dict[str, list[dict[str, Any]]] = {}
    for obligation in owed:
        by_source.setdefault(str(obligation.get("source", "book")), []).append(obligation)

    debt: list[dict[str, Any]] = []
    for source, obligations in by_source.items():
        declared = [o for o in obligations if o.get("checksDeclared")]
        debt.extend(o for o in obligations if not o.get("checksDeclared"))
        # A scenario claiming an id its body never asserts is refused by `qa validate`, and
        # rightly: the claim would read as covered in every report while nothing observed it.
        # An obligation with no declared check is book debt, listed below rather than claimed.
        if not declared:
            continue
        lines.append("")
        lines.append("")
        lines.append("@scenario(")
        lines.append("    target=api,")
        lines.append('    mechanism="live",')
        lines.append("    covers=[")
        lines.extend(f"        {_lit(o['id'])}," for o in declared)
        lines.append("    ],")
        arranged = _arrangements(declared)
        if arranged:
            # The preconditions are the book's own words for the state each fixture leaves
            # behind. A scenario states what must hold before it runs, and the node that owns
            # the claim already said it — copying it here beats an author paraphrasing it.
            lines.append("    preconditions=[")
            lines.extend(f"        {_lit(row['provides'] or row['name'])},"
                         for row in arranged)
            lines.append("    ],")
        else:
            lines.append("    preconditions=[],  # TODO(arrange): what must hold before this scenario runs")
            gaps.extend(
                Gap(o["id"], "unresolved-precondition", "no fixture arranged for this obligation")
                for o in declared
            )
        lines.append("    checkpoints=[],  # TODO(arrange): what an observer should see it prove")
        lines.append("    forbid=[],  # TODO: the weaker observations this scenario must not settle for")
        lines.append(")")
        lines.append(f"def {_slug(source)}_from_the_book(qa: Qa) -> None:")
        lines.append(f'    """Obligations {source} owes live evidence for."""')
        if arranged:
            lines.append("")
            lines.extend(
                f"    qa.fixture({_lit(row['name'])}"
                + "".join(f", {_lit(arg)}" for arg in row.get("args", []))
                + ")"
                for row in arranged
            )
        lines.extend(_scenario_body(declared, gaps))

    if debt:
        lines.append("")
        lines.append("")
        lines.append("# Book debt. Each of these is owed live evidence by this change and declares no")
        lines.append("# `verify:`, so there is nothing to compile and nothing an author could copy. The")
        lines.append("# fix is a check on the bullet in the book, not an assertion invented down here.")
        for obligation in debt:
            requirement = " ".join(str(obligation.get("requirement", "")).split())
            lines.append(f"#   {obligation['id']}")
            lines.append(f"#     {requirement[:100]}")

    return "\n".join(lines).rstrip() + "\n", gaps


def _arrangements(obligations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every fixture the obligations in one scenario declare, in order, arranged once each.

    Deduped on name *and* arguments: two claims documented in the same seeded ledger name one
    arrangement, and running it twice would be a second ledger rather than the one they share.
    Two that differ in an argument are two states, and both are arranged.
    """
    rows: list[dict[str, Any]] = []
    for obligation in obligations:
        rows.extend(obligation.get("fixturesDeclared", []))
    return list({(row["name"], tuple(row.get("args", []))): row for row in rows}.values())


def _resolved(
    ref: references.Reference,
    produced_facts: set[tuple[str, str]],
    produced_captures: set[str],
) -> bool:
    """Whether *ref* names a fact some earlier producer in the scenario already left behind.

    `@node.key` resolves against `produced_facts`, which by the time this obligation's own
    references are checked already carries this obligation's own arranged fixtures — arranging
    happens before verifying on the same node, so a fixture that node itself arranges resolves
    its own references. `$name` resolves against `produced_captures`, which does *not* yet carry
    this obligation's own captures: a capture is the thing an action just produced, not a fact in
    hand before that action ran, so a reference on the same obligation that captures it is still
    a gap — only a *strictly earlier* obligation's capture resolves it.
    """
    if isinstance(ref, references.NodeRef):
        return (ref.node, ref.key) in produced_facts
    return ref.name in produced_captures


def _scenario_body(obligations: list[dict[str, Any]], gaps: list[Gap]) -> list[str]:
    """Compile every obligation's assertion half. Called only with `checksDeclared` obligations.

    `compile_plan` filters to `declared = [o for o in obligations if o.get("checksDeclared")]`
    before ever reaching here, so every obligation this sees already has at least one row —
    there is no "declares no `verify:`" case left to report from inside the loop.

    References are resolved statically against a running producer set built by walking these
    obligations in the book's own document order: a `@node.key`/`$name` the book has not yet
    produced by this point is a gap, one it has is not — see `_resolved`.

    `obligations` arrives sorted by `_sort_key` (alphabetical on id, for stable ids and display),
    which is not the book's document order — a node written `returns:` (capturing a value) then
    `raises:` (reading it) sorts as `raises` before `returns`. The walk here re-sorts by each
    obligation's stamped `docPosition`, a `[node line, bullet ordinal]` pair, so the producer set
    fills in the order the author actually wrote the bullets — across the several nodes one
    scenario can owe evidence for, not just within one — rather than the order their key names
    happen to alphabetize to.
    """
    lines: list[str] = []
    index = 0
    produced_facts: set[tuple[str, str]] = set()
    produced_captures: set[str] = set()
    for obligation in sorted(obligations, key=lambda o: tuple(o.get("docPosition") or (0, 0))):
        oid = obligation["id"]
        rows = obligation.get("checksDeclared", [])
        requirement = " ".join(str(obligation.get("requirement", "")).split())
        lines.append("")
        lines.append(f"    # {oid}")
        lines.append(f"    # {requirement}")

        for fixture_row in obligation.get("fixturesDeclared", []):
            for qualified in fixture_row.get("providesKeys", []):
                owner, sep, key = qualified.rpartition(".")
                if sep:
                    produced_facts.add((owner, key))

        route = _route(obligation)
        index += 1
        name = f"observed_{index}"
        if route is not None:
            method, template = route
            path = _concrete_path(rows) or template
            status = _expect_status(rows)
            path_refs = references.find_references(path)
            for ref in path_refs:
                if not _resolved(ref, produced_facts, produced_captures):
                    gaps.append(Gap(oid, "unresolved-precondition",
                                     f"the path references {ref!r}, not resolvable without running the plan"))
            # A route path is almost never a whole reference — `/orgs/@seeded-acme.id/projects`
            # embeds one mid-string. `Http` takes plain literals now (Fix 2), so a path that
            # found a reference is wrapped in the harness's one explicit substitution call;
            # every other path is left a bare literal `Http` never touches for resolution.
            path_expr = f"qa.resolve({_lit(path)})" if path_refs else _lit(path)
            body = "" if method in {"GET", "DELETE", "HEAD", "OPTIONS"} else ", json_body={}"
            todo = ""
            if body != "":
                todo = "  # TODO(arrange): the book carries no request body"
                gaps.append(Gap(oid, "unresolved-precondition", "the book carries no request body"))
            expect = f", expect_status={status}" if status is not None else ""
            lines.append(f"    {name} = qa.http.{method.lower()}({path_expr}{body}{expect}){todo}")
            if "{" in path:
                lines.append("    # TODO(arrange): the path above still carries a template variable")
                gaps.append(Gap(oid, "unresolved-precondition", "the path still carries a template variable"))
        else:
            lines.append("    # TODO(arrange): the book gives this node no `route:` to act on")
            lines.append(f"    {name} = None  # TODO(arrange): what this scenario observes")
            gaps.append(Gap(oid, "uncompilable-claim", "the book gives this node no `route:` to act on"))
        for row in rows:
            for ref in references.find_references(json.dumps(row.get("args", {}))):
                if not _resolved(ref, produced_facts, produced_captures):
                    gaps.append(Gap(oid, "unresolved-precondition",
                                     f"a verify argument references {ref!r}, not resolvable without running the plan"))
            operand, note = _operand(row["name"], name)
            if note:
                lines.append(f"    # TODO(arrange): {note}")
                gaps.append(Gap(oid, "uncompilable-claim", note))
            lines.append(
                f"    qa.verify({_lit(row['name'])}, {operand}{_kwargs(row.get('args', {}))}, covers=[{_lit(oid)}])"
            )

        for capture in obligation.get("capturesDeclared", []):
            cname = capture.get("name")
            if cname:
                produced_captures.add(cname)
    return lines


def _operand(check: str, observed: str) -> tuple[str, str]:
    """What the compiled call is handed, and the arrangement note it still needs."""
    if check in _RESPONSE_CHECKS:
        return observed, ""
    if check in _BODY_CHECKS:
        return f"{observed}.json()", ""
    if check in _PAGE_CHECKS:
        return "qa.page", ""
    # A subject check compares observations the book never says how to take — `persists`
    # wants the record from before the process died and the one read after it came back.
    return observed, f"`{check}` observes a subject, not a response — hand it the pair"


def cmd_compile_plan(
    spec_dir: Path,
    *,
    out: Path | None = None,
    story: str = "",
    run_id: str | None = None,
    base_url: str = "http://localhost:8000",
) -> QaOutcome:
    """Compile `spec_dir/qa-okf-context.json` into a plan skeleton.

    Writing over an existing plan is refused. What is on disk may be an authored plan with
    hours of arrangement in it, and this command has no way to tell that from its own last
    output — so it declines and names the path, rather than deciding on the author's behalf.
    """
    context_file = spec_dir / "qa-okf-context.json"
    try:
        packet = json.loads(context_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return QaOutcome(ok=False, message=f"error: {exc}", status="invalid",
                         data={"status": "invalid", "problems": [str(exc)]})

    story_name = story or str(packet.get("story", "") or "story")
    source, gaps = compile_plan_gaps(packet, story=story_name, run_id=run_id, base_url=base_url)

    owed = _owed(packet)
    declared = [o for o in owed if o.get("checksDeclared")]
    data = {
        "owed": len(owed),
        "declared": len(declared),
        "debt": [o["id"] for o in owed if not o.get("checksDeclared")],
        # Doctor-shaped, not doctor-imported: `severity`/`code`/`message`/`ref` are the field
        # names `doctor.Finding` uses, and `code` is the gap's own `kind` — the vocabulary the
        # `Gap` docstring already promises doctor reads rather than redefines. A caller that
        # wants real `Finding` objects reuses `doctor.gap_findings` on the same `Gap` list;
        # this is the shape for one that only has this command's JSON output to read.
        "gaps": [
            {"severity": "error", "code": gap.kind, "message": gap.detail, "ref": gap.obligation_id}
            for gap in gaps
        ],
    }

    if out is None:
        return QaOutcome(ok=True, message=source, status="passed", data={**data, "plan": source})
    if out.exists():
        return QaOutcome(
            ok=False,
            message=f"error: {out} already exists; move it aside or compile to stdout",
            status="invalid",
            data={**data, "problems": [f"{out} already exists"]},
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(source, encoding="utf-8")
    return QaOutcome(
        ok=True,
        message=(f"Compiled {len(declared)} of {len(owed)} owed obligations into {out}.\n"
                 f"{len(data['debt'])} owed obligation(s) declare no `verify:` and are listed "
                 f"as book debt in the file."),
        status="passed",
        data=data,
    )

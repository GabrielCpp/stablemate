"""The policy-desk trial machinery: materialize a story, seed a defect, score the round.

Moved out of `benchmarks/replay.py` rather than rewritten. Everything here was already
paid for in blood — the pre-image commit that makes a story's diff uncommitted, the
`stories`-at-the-root ignore rule, `$PWD` alignment, the three routes that count as a
catch, the `–` that is not a zero — and a re-implementation would have re-earned each of
those the same way. What changed is only the frame around it: the tree comes from a
paddock seed, the fan-out lives in one task's steps, and the evidence a trial leaves
behind is copied into the result so the score can be recomputed from the sealed zip.

The leading underscore keeps `paddock.loader` from treating this as a task module: it is
the library `policy_desk_qa.py` imports, not a second declaration.
"""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

# ── the app tree ──────────────────────────────────────────────────────────────────────

#: The answer key and the story images sit inside the app tree and are not the app. They
#: are matched at the app *root* only: `shutil.ignore_patterns` matches a basename at any
#: depth, and `stories` is also what an epic calls its story folders — which silently
#: removed every story.md from the trial and left the run with nothing to plan against.
NOT_THE_APP = ("stories", "defects", "defects.yml")

#: What the QA flow *writes*, and therefore what a trial must remove before running it.
#: The flow's own `clear_qa_evidence` already drops `qa/` and `qa-evidence.json`, so those
#: are belt-and-braces; the plan files are the load-bearing ones, because a plan left on
#: disk is a plan the flow would repair instead of author — a different loop from the one
#: being measured.
QA_OUTPUTS = (
    "qa-plan.yml", "qa-plan.md", "qa.md", "qa-evidence.json",
    "qa-okf-verification-index.json", "qa",
)

#: The nodes the round exists to move. Others still print — a change that fixes one loop
#: by pushing the work into another has not fixed anything — but these are the headline.
WATCHED = ("plan-qa", "audit-qa", "document-story", "review-story-documentation")

#: The deterministic node that drives the product: the QA plan actually executing against
#: a running app. Its share of the trial's wall clock is the time-leverage numerator —
#: everything else is the loop talking to itself about what it is going to do.
DRIVING_NODE = "run_qa_plan"

#: The label a trial with nothing seeded in it carries.
CLEAN = "clean"


class TrialError(RuntimeError):
    """A fixture or trial precondition that fails before anything has been measured."""


def git(*args: str, cwd: Path) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise TrialError(f"git {' '.join(args)} in {cwd}: {proc.stderr.strip()}")
    return proc.stdout


def story_diff(app: Path, story: str) -> dict[str, list[str]]:
    """The `changed:`/`added:` manifest for one story, validated against the tree."""
    manifest = app / "stories" / story / "diff.yml"
    if not manifest.is_file():
        known = ", ".join(sorted(p.name for p in (app / "stories").glob("*"))) or "none"
        raise TrialError(f"no diff manifest at {manifest} (stories: {known})")
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    return {"changed": list(data.get("changed") or []), "added": list(data.get("added") or [])}


def story_image(app: Path, story: str, rel: str, *, phase: str) -> Path:
    """Where the `pre`/`post` content of one path for one story lives.

    `post/` is optional and the fallback is the app tree, because the app tree IS the last
    story's post-image — that is what keeps it the single thing a reader checks the book
    against. `pre/` has no fallback: a `changed:` path with no pre-image would be committed
    at its final content, and the story's diff would silently come out empty.
    """
    image = app / "stories" / story / phase / rel
    if image.is_file():
        return image
    if phase == "pre":
        raise TrialError(f"story {story!r} lists {rel} as changed but has no pre/ image at {image}")
    return app / rel


def materialize(app: Path, story: str, dest: Path) -> Path:
    """Build, at `dest`, the git state a QA run for `story` is supposed to face.

    The coder's QA lane mints its obligations from *uncommitted* changes
    (`build_okf_context(..., base="HEAD", head="WORKTREE", ...)`), so a plain copy of a
    finished app obligates nothing at all and the run has nothing to prove. Hence:

      1. copy the app tree, minus the answer key;
      2. commit a *before* tree — each `changed:` path replaced by its `pre/` image, each
         `added:` path deleted;
      3. restore this story's files into the worktree, uncommitted, from `post/` where that
         exists and from the app tree otherwise.

    `HEAD..WORKTREE` is then exactly this story's implementation diff, while the book, the
    specs and every other story's code sit at their authored state.
    """
    diff = story_diff(app, story)
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    def ignore(directory: str, names: list[str]) -> set[str]:
        top = NOT_THE_APP if Path(directory) == app else ()
        return {name for name in names if name in top or name in ("__pycache__", ".git")}

    shutil.copytree(app, dest, ignore=ignore)

    # The finished content this story is responsible for, held aside while the before tree
    # is committed.
    after = {
        rel: story_image(app, story, rel, phase="post").read_bytes()
        for rel in [*diff["changed"], *diff["added"]]
    }
    for rel in diff["added"]:
        (dest / rel).unlink(missing_ok=True)
    for rel in diff["changed"]:
        (dest / rel).write_bytes(story_image(app, story, rel, phase="pre").read_bytes())

    git("init", "--quiet", "--initial-branch", "main", cwd=dest)
    # Identity on the repo rather than the machine: a trial must not depend on whether the
    # host has a global git config, and must not write to it either.
    git("config", "user.email", "benchmark@example.com", cwd=dest)
    git("config", "user.name", "policy-desk benchmark", cwd=dest)
    git("add", "--all", cwd=dest)
    git("commit", "--quiet", "-m", f"before {story}", cwd=dest)

    for rel, body in after.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)

    # A rewind belongs here rather than in the seed: the seed is the app as tracked, and
    # the state `run qa` is entered in is the app minus this story's plan and evidence.
    spec = dest / "docs" / "specs" / story
    if not spec.is_dir():
        raise TrialError(f"no spec dir {spec} — is the seed the app tree it should be?")
    for name in QA_OUTPUTS:
        target = spec / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    return dest


def reset_stack_state(dest: Path) -> None:
    """Drop the trial's compose volumes, once, before the run starts.

    The app's `qa-stack.yml` deliberately does not do this in its `launch` line: a bring-up
    happens at the head of every plan lane, so a `down -v` there can land in the middle of a
    story proving a record survives a restart, and empty the ledger under it. Here there is
    no run in flight yet, which makes this the one safe moment to reset.

    Every trial shares one compose project name (farrier ties the trial directory's basename
    to its generated skills, so the directory cannot be named after the defect), which is
    exactly why the previous trial's volume is still there to drop.
    """
    if not (dest / "compose.yml").is_file():
        return
    subprocess.run(
        ["docker", "compose", "-f", "compose.yml", "down", "-v", "--remove-orphans"],
        cwd=str(dest), capture_output=True, text=True, check=False,
    )


# ── the answer key ────────────────────────────────────────────────────────────────────


def load_defects(app: Path) -> list[dict[str, str]]:
    path = app / "defects.yml"
    if not path.is_file():
        raise TrialError(f"no answer key at {path} — the round can be run but not scored")
    rows = list((yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("defects") or [])
    if not rows:
        raise TrialError(f"{path} lists no defects")
    return rows


def select_defects(app: Path, wanted: tuple[str, ...]) -> list[dict[str, str]]:
    rows = load_defects(app)
    if not wanted:
        return rows
    by_id = {str(row["id"]): row for row in rows}
    unknown = [name for name in wanted if name not in by_id]
    if unknown:
        raise TrialError(
            f"no such defect(s): {', '.join(unknown)} (have: {', '.join(sorted(by_id))})"
        )
    return [by_id[name] for name in wanted]


def variant_path(app: Path, row: dict[str, str]) -> Path:
    return app / "defects" / str(row["id"]) / str(row["path"])


def seed_defect(app: Path, row: dict[str, str], repo: Path) -> None:
    """Plant one defect in a materialized tree.

    A whole-file overwrite: the variant either lands on a path that exists or raises here,
    where the trial has not yet cost anything. A patch would apply cleanly against a stale
    app and leave the trial measuring an app with no defect in it at all.
    """
    variant = variant_path(app, row)
    if not variant.is_file():
        raise TrialError(f"defect {row['id']}: no variant at {variant}")
    target = repo / str(row["path"])
    if not target.is_file():
        raise TrialError(f"defect {row['id']}: {row['path']} is not in the materialized tree")
    shutil.copyfile(variant, target)


def defect_survived(app: Path, row: dict[str, str], witness: Path) -> bool:
    """Is the seeded file still byte-for-byte the defect variant at the end of the trial?

    This is the half of the score the terminal evidence map cannot see. The QA lane does not
    only observe — it triages a failing observation as `code` and repairs the product. When
    it does, the *last* evidence map is computed over a fixed app and reads `covered`, which
    is indistinguishable from a run that never noticed anything. Reading only that end state
    scores the loudest possible detection as a miss.

    So the seeded file itself is the witness. It was planted by an overwrite and nothing but
    the flow can have touched it since; if it no longer matches the variant, the flow acted
    on the defect. Byte equality, not a semantic check, because the question is only whether
    the code under test is still the code that was seeded — a repair that differs from the
    canonical app is still a repair.
    """
    target = witness / str(row["path"])
    if not target.is_file():
        return False
    return target.read_bytes() == variant_path(app, row).read_bytes()


# ── what a trial leaves behind ────────────────────────────────────────────────────────


def capture_witness(repo: Path, dest: Path, extra: tuple[str, ...] = ()) -> Path:
    """Copy the part of a finished trial tree the score reads, into the staged result.

    The trial tree itself lives in `scratch/` and is never sealed — fourteen copies of an
    application is a result zip nobody keeps. What the score needs is small and specific:
    `docs/` (the book, the spec, the plan, the evidence and the run ledger), the config
    files ostler roots on, and the one file the defect was seeded into.

    `docs/` is also what makes the copy work at all: `ostler.model.find_root` stops at a
    directory holding `docs/`, so the witness *is* a repo as far as the book loader is
    concerned, and a sealed result stays re-scorable on a machine that never ran it.
    """
    dest.mkdir(parents=True, exist_ok=True)
    if (repo / "docs").is_dir():
        shutil.copytree(repo / "docs", dest / "docs", dirs_exist_ok=True)
    for name in ("agents.yml", ".agents.yml", "ostler.yml", "ostler.yaml"):
        if (repo / name).is_file():
            shutil.copyfile(repo / name, dest / name)
    for rel in extra:
        source = repo / rel
        if source.is_file():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest / rel)
    return dest


def timing_of(run_id: str, wall_s: float) -> dict[str, Any]:
    """Per-trial wall clock, the run's own time partition, and per-node seconds.

    Two clocks on purpose. `wall_s` is measured around the subprocess and includes
    everything the harness paid for — materialization, compose bring-up, the run, the
    teardown. groom's partition is what happened *inside* the run, and it is the only one
    that can separate the agent thinking from the product being driven.

    Per-node seconds come from the spans directly rather than from `node_costs`, which
    counts `agent_turn` spans only: the node this instrument is about, `run_qa_plan`, is
    deterministic and has no turn under it. A node span is named after its node, so
    selecting `name == node` sums each node once instead of once per nested turn.
    """
    from groom import store

    profile = store.run_profile(run_id) or {}
    nodes: dict[str, float] = {}
    for span in store.query_spans(run=run_id, limit=100000):
        if span.get("name") != span.get("node") or not span.get("node"):
            continue
        seconds = float(span.get("end_ts") or 0.0) - float(span.get("start_ts") or 0.0)
        if seconds > 0:
            nodes[str(span["node"])] = nodes.get(str(span["node"]), 0.0) + seconds
    return {
        "wall_s": round(wall_s, 1),
        "time_s": {
            key: round(value, 1)
            for key, value in (profile.get("time_s") or {}).items()
            if isinstance(value, (int, float))
        },
        "nodes_s": {node: round(seconds, 1) for node, seconds in sorted(nodes.items())},
        "driving_s": round(nodes.get(DRIVING_NODE, 0.0), 1),
    }


def laps_of(run_id: str) -> list[dict[str, Any]]:
    """This trial's per-node lap rows, persisted so the round can be re-scored later.

    `min_work_items=1` because a trial is ONE story, so every node has exactly one work
    item; `groom loops`' default of 3 exists to keep one-off nodes out of a whole-machine
    report and would silence this one entirely.
    """
    from groom import store

    keep = ("node", "work_items", "turns", "max_laps", "cost_usd", "est_cost_usd")
    return [
        {key: row.get(key) for key in keep}
        for row in store.loop_convergence(run=run_id, min_work_items=1)
    ]


# ── classification ────────────────────────────────────────────────────────────────────


def evidence_statuses(witness: Path, story: str) -> dict[str, str] | None:
    """`{obligation id: status}` for the run's owed obligations, or None if unbuildable.

    None is not an empty map. `build_evidence_map` refuses when an input is missing, and a
    map computed over a missing run log reports every obligation `uncovered` — which is
    indistinguishable from a run that genuinely asserted nothing and would score a trial
    that never started as a wall of detections.
    """
    from ostler import qa as qa_mod

    try:
        data = qa_mod.build_evidence_map(witness / "docs" / "specs" / story)
    except qa_mod.EvidenceMapError:
        return None
    return {str(row["id"]): str(row["status"]) for row in data["obligations"]}


def audit_result(artifacts: Path, run_id: str) -> dict[str, Any]:
    """The auditor's last verdict for a trial, or an empty dict if it never ran."""
    path = artifacts / f"coder-{run_id}" / "audit-qa" / "output.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def classify(
    row: dict[str, str] | None,
    statuses: dict[str, str] | None,
    audit: dict[str, Any],
    *,
    survived: bool = True,
) -> tuple[str, str]:
    """Score one trial against its row. Returns `(verdict, the status that decided it)`.

    Three routes count as a catch, because the flow has three places a defect can surface
    and which one fires is a property of the QA plan — the thing under measurement:

    * the **evidence map** puts the named obligation at the row's `expect`, which is a set
      operation over the run's own artifacts, or
    * the **auditor** refuted the pass and its findings name that obligation, or
    * the seeded code **did not survive** the run: QA observed the defect, triaged it as a
      code failure and repaired it. That path ends with the obligation `covered` — the map
      is right, the app really is fixed — so only the seeded file distinguishes it from a
      run that never noticed. It is checked last, since the first two say *where* the
      detection was recorded and this one only says that it happened.

    A miss is the specific, worse outcome: the run published a pass, claimed the obligation
    covered, *and* left the defect in place. Anything else — no map, an obligation out of
    scope, a run that blocked before it asserted anything — is `inconclusive` rather than a
    catch or a miss, since scoring an infrastructure failure either way is a number about
    this machine.
    """
    refuted = str(audit.get("verdict", "")) == "refuted"
    if row is None:  # the clean control: any contradiction at all is a false alarm
        if statuses is None:
            return "inconclusive", "no evidence map"
        contradicted = sorted(k for k, v in statuses.items() if v == "contradicted")
        if contradicted:
            return "false", contradicted[0]
        return ("false", "audit refuted") if refuted else ("clean", "no contradiction")

    obligation = str(row["obligation"])
    status = (statuses or {}).get(obligation, "")
    if status == str(row["expect"]):
        return "caught", status
    cited = obligation in json.dumps(audit)
    if refuted and cited:
        return "caught", "audit refutation"
    if not survived:
        return "caught", "defect repaired"
    if statuses is None:
        return "inconclusive", "no evidence map"
    if not status:
        return "inconclusive", "obligation not owed by this trial"
    if status == "covered":
        return "missed", status
    return "inconclusive", status


# ── leverage ──────────────────────────────────────────────────────────────────────────


#: Printed in place of a metric whose inputs are not there, and never `0`. A trial that
#: blocked before writing a plan navigated through no links and addressed no roles; a
#: `roles 0/0` there is a claim about the QA it produced rather than a report that there
#: was none — the same lie `classify` refuses when it scores a missing evidence map
#: `inconclusive` instead of a miss.
BLANK = "–"

#: The scorecard, in print order. Detection says whether the QA flow noticed a defect;
#: these say whether the plan it wrote used the book it was handed — entered each flow
#: where the book says the flow starts, moved between screens by clicking rather than by
#: re-navigating, addressed the UI by the roles the book documents, and closed the
#: obligations and the journeys it owed. A plan can catch a seeded defect while doing none
#: of that, and it is the difference between QA and a regression suite of URL fetches.
LEVERAGE_KEYS = ("entry", "deep_links", "roles", "obligations", "journeys")

LEVERAGE_LABELS = {
    "entry": "entry",
    "deep_links": "deep-links",
    "roles": "roles",
    "obligations": "obligations",
    "journeys": "journeys",
}

#: The one evidence-map status that is a discharged obligation. The other three
#: (`uncovered`, `claimed-but-unasserted`, `contradicted`) are each a different way of not
#: having proved it, and none of them counts here.
PASSING_STATUS = "covered"


def route_matches(route: str, url: str) -> bool:
    """Whether a planned `goto` lands on a route the book documents.

    Ostler's own `_route_matches` when it imports: it is the rule `qa validate` already
    applied to this plan, and a second implementation here would score plans against a
    gate that never ran. The fallback below is a transcription of that function, for an
    environment without ostler on the path.
    """
    try:
        from ostler.qa.plan import _route_matches
    except ImportError:
        planned = [part for part in urlsplit(url).path.strip("/").split("/") if part]
        documented = [part for part in urlsplit(route).path.strip("/").split("/") if part]
        if len(planned) != len(documented):
            return False
        return all(
            part.startswith((":", "{")) or other.startswith((":", "{")) or part == other
            for part, other in zip(planned, documented, strict=True)
        )
    return _route_matches(route, url)


def _values(value: Any) -> list[str]:
    if value is None:
        return []
    return [str(item) for item in (value if isinstance(value, list) else [value])]


def _route_of(node: dict[str, Any]) -> str:
    """The route a screen node documents, or `""`.

    First whitespace token of the `route:` bullet with its backticks stripped, because the
    bullet is prose-shaped — ``- route: `/policies/:id` (the detail screen)`` — and only the
    path is a route.
    """
    for value in _values(node.get("bullets", {}).get("route")):
        token = value.strip().split()[0].strip("`") if value.strip() else ""
        if token.startswith("/"):
            return token
    return ""


def _literal(node: ast.expr | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def _called(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else ""


def plan_scenarios(source: str) -> dict[str, dict[str, Any]]:
    """`{scenario id: {"covers": [...], "actions": [...]}}`, read statically from a `qa_plan.py`.

    From the plan rather than the run log because a `goto` URL never reaches
    `qa-run.ndjson`: the ledger records steps and assertions, not the browser calls inside
    them. The plan is also the artifact `ostler qa validate` judges, so scoring it scores
    the thing the flow was gated on.

    The action list comes from ostler's own `extract_locators` — the parser
    `_validate_book_locators` reads — so a locator counted here is the locator that gate
    saw, computed roles (`"*"`) and all. Only the `@scenario(...)` header is parsed
    locally, and only for the two fields the harness's static half does not return: the
    id, which is what the run log calls a scenario, and `covers`, which is what ties a
    scenario to the book.
    """
    from ostler.qa.harness_host import load_harness_module

    actions = load_harness_module("ostler_qa").extract_locators(source)
    found: dict[str, dict[str, Any]] = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or _called(decorator) != "scenario":
                continue
            keywords = {kw.arg: kw.value for kw in decorator.keywords if kw.arg}
            given = _literal(keywords.get("id"))
            covers = _literal(keywords.get("covers"))
            found[given if isinstance(given, str) else node.name.replace("_", "-")] = {
                "covers": [str(item) for item in covers] if isinstance(covers, list) else [],
                "actions": actions.get(node.name, []),
            }
    return found


def _gotos(scenario: dict[str, Any]) -> list[str]:
    return [
        str(action["url"])
        for action in scenario["actions"]
        if isinstance(action, dict) and action.get("do") == "goto" and action.get("url")
    ]


def _locators(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        action["locator"]
        for action in scenario["actions"]
        if isinstance(action, dict) and isinstance(action.get("locator"), dict)
    ]


def required_flows(packet: dict[str, Any]) -> list[str]:
    """The flow nodes this story owes live evidence for.

    Off the obligations rather than the packet's `journeys:` list, because that list is
    every flow the graph closure reached and most of them are context: a story touching one
    endpoint pulls in every journey that endpoint appears in, and scoring a plan for not
    walking all of them would report a correct plan as a third of one.
    """
    return sorted({
        str(obligation["node"])
        for obligation in packet.get("obligations", []) or []
        if isinstance(obligation, dict)
        and obligation.get("kind") == "journey"
        and obligation.get("required", True)
        and obligation.get("node")
    })


def flow_starts(book: dict[str, Any]) -> dict[str, str]:
    """`{flow node id: the route its `start:` screen documents}`.

    Two hops, because neither end carries both halves: the flow names its start screen as a
    link, and the route lives on the screen. `via` is the bullet key the link was written
    under, which is what keeps a `start:` edge apart from a `steps:` one pointing at the
    same screen.
    """
    routes = {str(node["id"]): _route_of(node) for node in book.get("nodes", []) or []}
    starts: dict[str, str] = {}
    for edge in book.get("edges", []) or []:
        if edge.get("via") == "start" and routes.get(str(edge.get("to"))):
            starts.setdefault(str(edge["from"]), routes[str(edge["to"])])
    return starts


def entry_routes(book: dict[str, Any]) -> set[str]:
    """Every route a user may legitimately arrive at from outside in-app navigation.

    A flow's start plus any screen carrying an `entry:` bullet — the book's own word for
    "reached by an app root, an emailed link or an OAuth callback". Navigating straight to
    one of these mid-scenario is arriving, not deep-linking.
    """
    routes = {
        _route_of(node)
        for node in book.get("nodes", []) or []
        if node.get("bullets", {}).get("entry") and _route_of(node)
    }
    return routes | set(flow_starts(book).values())


def documented_routes(book: dict[str, Any]) -> set[str]:
    return {route for node in book.get("nodes", []) or [] if (route := _route_of(node))}


def leverage_from(
    book: dict[str, Any] | None,
    packet: dict[str, Any] | None,
    plan_source: str | None,
    run_log: list[dict[str, Any]] | None,
    statuses: dict[str, str] | None,
) -> dict[str, Any]:
    """The five leverage metrics, each a `[n, of]` pair, an int, or None when incomputable.

    None rather than a zero everywhere an input is missing. Every one of these is a
    fraction whose denominator is a property of the *book* — flows documented, obligations
    owed, locators written — so an absent artifact makes the question unaskable rather than
    the answer bad, and `leverage_line` prints `–` for it.
    """
    scenarios = plan_scenarios(plan_source) if plan_source else {}
    if run_log is not None:
        # Only what the run actually started. A scenario the plan declares and the driver
        # never reached entered nothing and clicked nothing, and crediting it for the entry
        # its source says it would have made scores an intention.
        started = {
            str(record.get("scenario", ""))
            for record in run_log
            if record.get("kind") == "scenario_start"
        }
        scenarios = {name: data for name, data in scenarios.items() if name in started}

    flows = required_flows(packet) if packet else []
    starts = flow_starts(book) if book else {}
    covering: dict[str, list[dict[str, Any]]] = {flow: [] for flow in flows}
    for data in scenarios.values():
        for flow in flows:
            if any(cover.startswith(f"okf:{flow}:") for cover in data["covers"]):
                covering[flow].append(data)

    entry: list[int] | None = None
    if flows and any(starts.get(flow) for flow in flows):
        entry = [
            sum(
                1
                for flow in flows
                if (route := starts.get(flow))
                and any(
                    (gotos := _gotos(data)) and route_matches(route, gotos[0])
                    for data in covering[flow]
                )
            ),
            len(flows),
        ]

    deep_links: int | None = None
    if book and scenarios:
        elsewhere = documented_routes(book)
        arrivals = entry_routes(book)
        deep_links = sum(
            1
            for data in scenarios.values()
            for url in _gotos(data)[1:]
            if any(route_matches(route, url) for route in elsewhere)
            and not any(route_matches(route, url) for route in arrivals)
        )

    roles: list[int] | None = None
    uses = [locator for data in scenarios.values() for locator in _locators(data)]
    if uses:
        # `role` and `css` are the two strategies the book can vouch for — a `role:` bullet
        # and a `selector:` one. `text` and `label` address a rendered string, which is what
        # the next copy edit changes; `test_id` addresses a hook the book never mentions.
        roles = [sum(1 for locator in uses if "role" in locator or "css" in locator), len(uses)]

    obligations = (
        [sum(1 for status in statuses.values() if status == PASSING_STATUS), len(statuses)]
        if statuses
        else None
    )

    journeys = (
        [
            sum(1 for flow in flows if statuses.get(f"okf:{flow}:end-state") == PASSING_STATUS),
            len(flows),
        ]
        if statuses and flows
        else None
    )

    return {
        "entry": entry,
        "deep_links": deep_links,
        "roles": roles,
        "obligations": obligations,
        "journeys": journeys,
    }


def read_ndjson(path: Path) -> list[dict[str, Any]] | None:
    if not path.is_file():
        return None
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def load_book(repo: Path) -> dict[str, Any] | None:
    """The feature graph as `{"nodes": [...], "edges": [...]}`, or None if it will not load.

    The same `graph.build` behind `ostler graph`, in this process. A trial's book is the
    frozen app's book plus whatever the flow wrote, and it is the only artifact carrying a
    flow's start screen — the packet lifts `route:` onto an obligation but never `start:`.
    """
    try:
        from ostler import graph as graph_mod
        from ostler import model
    except ImportError:
        return None
    try:
        return graph_mod.build(model.load(repo))
    except Exception:  # noqa: BLE001 - a book that will not load scores `–`, not a crash
        return None


def leverage(witness: Path, story: str, statuses: dict[str, str] | None) -> dict[str, Any]:
    """Score one trial's artifacts. Every input is optional; a missing one prints `–`."""
    spec = witness / "docs" / "specs" / story
    plan_file = spec / "qa_plan.py"
    return leverage_from(
        load_book(witness),
        read_json(spec / "qa-okf-context.json"),
        plan_file.read_text(encoding="utf-8") if plan_file.is_file() else None,
        read_ndjson(spec / "qa" / "qa-run.ndjson"),
        statuses,
    )


def pool_leverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum the metrics across trials, keeping a metric None when no trial could compute it.

    Summed rather than averaged, for the reason laps are pooled: these are counts over a
    denominator that varies per story, and averaging per-trial fractions would weight a
    one-flow story the same as a five-flow one.
    """
    pooled: dict[str, Any] = dict.fromkeys(LEVERAGE_KEYS)
    for row in rows:
        metrics = row.get("leverage") or {}
        for key in LEVERAGE_KEYS:
            value = metrics.get(key)
            if value is None:
                continue
            current = pooled[key]
            if isinstance(value, list):
                pair = [int(value[0]), int(value[1])]
                pooled[key] = pair if current is None else [current[0] + pair[0], current[1] + pair[1]]
            else:
                pooled[key] = int(value) + (current or 0)
    return pooled


def leverage_line(metrics: dict[str, Any]) -> str:
    parts = []
    for key in LEVERAGE_KEYS:
        value = metrics.get(key)
        if value is None:
            shown = BLANK
        elif isinstance(value, list):
            shown = f"{value[0]}/{value[1]}"
        else:
            shown = str(value)
        parts.append(f"{LEVERAGE_LABELS[key]} {shown}")
    return "leverage: " + "  ".join(parts)


# ── the round ─────────────────────────────────────────────────────────────────────────


def money(rows: list[dict[str, Any]]) -> str:
    """`$0.94`, or `~$0.71` when the estimate is standing in, or `$?` when neither exists.

    `?` rather than `$0.00`: a backend that reports nothing and a model the rate card does
    not name leave the round genuinely unpriced, and a zero there is a claim. A backend
    under subscription auth reports a literal `$0` over millions of tokens, which is not a
    cheap round, it is an unpriced one.
    """
    billed = sum(row.get("cost_usd") or 0.0 for row in rows)
    if billed:
        return f"${billed:.2f}"
    estimated = sum(row.get("est_cost_usd") or 0.0 for row in rows)
    return f"~${estimated:.2f}" if estimated else "$?"


def convergence(trials: list[dict[str, Any]]) -> str:
    """The cost half of the headline: `| plan-qa 2.1 laps ~$0.94`, pooled over the round.

    Detection and convergence belong on one line because either alone is gameable in the
    direction of the other — a flow that refutes everything catches every defect and never
    terminates, and one that approves everything converges in a single lap.
    """
    rows = [
        row
        for trial in trials
        for row in (trial.get("laps") or [])
        if row.get("node") == "plan-qa"
    ]
    if not rows:
        return ""
    items = sum(row.get("work_items") or 0 for row in rows)
    turns = sum(row.get("turns") or 0 for row in rows)
    return f" | plan-qa {turns / items:.1f} laps {money(rows)}" if items else ""


def time_leverage(trials: list[dict[str, Any]]) -> str:
    """`time-leverage: 8% (12m driving / 148m)` — the product-facing share of the round.

    The question the number answers is what a QA lane spends its hour on. `run_qa_plan` is
    the only node that touches the running application; everything else is the loop
    authoring, reviewing and repairing its intention to do so. A round that catches every
    defect at 3% time-leverage and one that catches them at 30% are the same scorecard and
    very different products, which is the same reason the leverage line sits under the
    detection line rather than replacing it.

    Wall clock is summed across trials rather than measured end to end: the round is
    sequential today, and a sum stays honest if it ever stops being.
    """
    wall = sum(float((trial.get("timing") or {}).get("wall_s") or 0.0) for trial in trials)
    driving = sum(float((trial.get("timing") or {}).get("driving_s") or 0.0) for trial in trials)
    if not wall:
        return ""
    return (
        f"time-leverage: {driving / wall:.0%} "
        f"({driving / 60:.0f}m driving / {wall / 60:.0f}m)"
    )


def node_table(trials: list[dict[str, Any]]) -> list[str]:
    """The per-node convergence table, pooled over every trial in the round.

    Laps are summed rather than averaged, which is the right aggregation for this
    statistic: the exit rate is a per-lap acceptance probability, and pooling the laps is
    its maximum-likelihood estimate over the whole sample. Averaging per-trial rates would
    weight a one-lap story the same as a thirteen-lap one.
    """
    pooled: dict[str, list[dict[str, Any]]] = {}
    seconds: dict[str, float] = {}
    for trial in trials:
        for row in trial.get("laps") or []:
            pooled.setdefault(str(row.get("node")), []).append(row)
        for node, value in ((trial.get("timing") or {}).get("nodes_s") or {}).items():
            seconds[node] = seconds.get(node, 0.0) + float(value)
    if not pooled:
        return ["no laps recorded — did the runs reach an agent turn?"]

    lines = [f"  {'node':<30} {'items':>5} {'turns':>5} {'exit':>6} {'mean':>5} "
             f"{'max':>4} {'cost$':>8} {'min':>6}"]
    order = sorted(
        pooled.items(),
        key=lambda kv: (kv[0] not in WATCHED, -sum(row.get("turns") or 0 for row in kv[1])),
    )
    for node, rows in order:
        items = sum(row.get("work_items") or 0 for row in rows)
        turns = sum(row.get("turns") or 0 for row in rows)
        if not items or not turns:
            continue
        mark = "*" if node in WATCHED else " "
        lines.append(
            f"{mark} {node:<30} {items:>5} {turns:>5} {items / turns:>5.0%} "
            f"{turns / items:>5.2f} {max(row.get('max_laps') or 0 for row in rows):>4} "
            f"{money(rows):>8} {seconds.get(node, 0.0) / 60:>6.1f}"
        )
    excess = sum(
        (row.get("turns") or 0) - (row.get("work_items") or 0)
        for rows in pooled.values()
        for row in rows
    )
    every = [row for rows in pooled.values() for row in rows]
    lines.append(f"  {'-' * 75}")
    lines.append(
        f"  {'TOTAL':<30} {'':>5} {'':>5} {'':>6} {'':>5} {'':>4} {money(every):>8} "
        f"{'':>6}   ({excess} excess turns)"
    )
    return lines


def headline(trials: list[dict[str, Any]]) -> str:
    seeded = [trial for trial in trials if trial["defect"] != CLEAN]
    caught = sum(1 for trial in seeded if trial["verdict"] == "caught")
    missed = sum(1 for trial in seeded if trial["verdict"] == "missed")
    false = sum(1 for trial in trials if trial["verdict"] == "false")
    unknown = sum(1 for trial in trials if trial["verdict"] == "inconclusive")
    line = f"caught {caught}/{len(seeded)}  missed {missed}  false {false}{convergence(trials)}"
    if unknown:
        # Loudly, and never folded into a miss: an inconclusive trial is the harness
        # failing, and averaging it into the detection rate hides the outage as a result.
        line += f"  inconclusive {unknown}"
    return line


def detail(trials: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for trial in trials:
        timing = trial.get("timing") or {}
        lines.append(
            f"  {trial['defect']:<6} {trial['verdict']:<13} {trial['because']}"
            f"  [{timing.get('wall_s', 0) / 60:.0f}m]"
        )
        lines.append(f"    {trial['obligation'] or '(control)'}")
    lines.append("")
    lines.append("  " + leverage_line(pool_leverage(trials)))
    if (leveraged := time_leverage(trials)):
        lines.append("  " + leveraged)
    lines.append("")
    lines.extend(node_table(trials))
    return lines

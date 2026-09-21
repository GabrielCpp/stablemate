"""The frozen-app trial machinery: materialize a story, seed a defect, score the round."""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml
import _forensics as fx
from _stablemate import TrialError, effective, git, no_leaks, pin_held, stablemate_checkout, uv_run
from paddock import Run, Score


NOT_THE_APP = ("stories", "defects", "defects.yml", "mutants", "mutants.yml")

QA_OUTPUTS = (
    "qa-plan.yml", "qa-plan.md", "qa.md", "qa-evidence.json",
    "qa-okf-verification-index.json", "qa",
    "qa-smoke-proof.txt",
)

CLEAN = "clean"


DIFF_KINDS = ("changed", "added", "pinned")


def story_diff(app: Path, story: str) -> dict[str, list[str]]:
    """The `changed:`/`added:`/`pinned:` manifest for one story, validated against the tree."""
    manifest = app / "stories" / story / "diff.yml"
    if not manifest.is_file():
        known = ", ".join(sorted(p.name for p in (app / "stories").glob("*"))) or "none"
        raise TrialError(f"no diff manifest at {manifest} (stories: {known})")
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    diff = {kind: [str(rel) for rel in data.get(kind) or []] for kind in DIFF_KINDS}
    seen: dict[str, str] = {}
    for kind in DIFF_KINDS:
        for rel in diff[kind]:
            if rel in seen:
                raise TrialError(
                    f"{manifest}: {rel} is listed under both {seen[rel]}: and {kind}: — "
                    "a path is exactly one of changed, added or pinned"
                )
            seen[rel] = kind
    return diff


def story_image(app: Path, story: str, rel: str, *, phase: str) -> Path:
    """Where the `pre`/`post` content of one path for one story lives."""
    image = app / "stories" / story / phase / rel
    if image.is_file():
        return image
    if phase == "pre":
        raise TrialError(f"story {story!r} lists {rel} as changed but has no pre/ image at {image}")
    if phase == "pinned":
        raise TrialError(f"story {story!r} pins {rel} but has no pinned/ image at {image}")
    return app / rel


def tracked_paths(app: Path) -> list[str]:
    """Every path git tracks under `app`, relative to `app` itself."""
    return [rel for rel in git("ls-files", "-z", cwd=app).split("\0") if rel]


def copy_tracked(app: Path, dest: Path) -> None:
    """Copy exactly the files git tracks under `app` into `dest`, minus `NOT_THE_APP`."""
    for rel in tracked_paths(app):
        if Path(rel).parts[0] in NOT_THE_APP:
            continue
        source = app / rel
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            os.symlink(os.readlink(source), target)
        else:
            shutil.copy2(source, target)


def materialize(
    app: Path, story: str, dest: Path, install: Callable[[Path], None] | None = None
) -> Path:
    """Build, at `dest`, the git state a QA run for `story` is supposed to face."""
    diff = story_diff(app, story)
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    copy_tracked(app, dest)

    after = {
        rel: story_image(app, story, rel, phase="post").read_bytes()
        for rel in [*diff["changed"], *diff["added"]]
    }
    for rel in diff["added"]:
        (dest / rel).unlink(missing_ok=True)
    for rel in diff["changed"]:
        (dest / rel).write_bytes(story_image(app, story, rel, phase="pre").read_bytes())
    for rel in diff["pinned"]:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(story_image(app, story, rel, phase="pinned").read_bytes())

    git("init", "--quiet", "--initial-branch", "main", cwd=dest)
    git("config", "user.email", "benchmark@example.com", cwd=dest)
    git("config", "user.name", "stablemate benchmark", cwd=dest)
    if install is not None:
        install(dest)
    git("add", "--all", cwd=dest)
    git("commit", "--quiet", "-m", f"before {story}", cwd=dest)

    for rel, body in after.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)

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
    """Drop the trial's compose volumes, once, before the run starts."""
    if not (dest / "compose.yml").is_file():
        return
    subprocess.run(
        ["docker", "compose", "-f", "compose.yml", "down", "-v", "--remove-orphans"],
        cwd=str(dest), capture_output=True, text=True, check=False,
    )




CATCH_ROUTES = frozenset({"run", "audit"})

FIRST_VERDICT = True


def load_defects(app: Path) -> list[dict[str, str]]:
    path = app / "defects.yml"
    if not path.is_file():
        raise TrialError(f"no answer key at {path} — the round can be run but not scored")
    rows = list((yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("defects") or [])
    if not rows:
        raise TrialError(f"{path} lists no defects")
    for row in rows:
        route = str(row.setdefault("caught_by", "run"))
        if route not in CATCH_ROUTES:
            raise TrialError(
                f"{path}: defect {row.get('id')!r} has caught_by: {route!r}; "
                f"the routes are {', '.join(sorted(CATCH_ROUTES))}"
            )
    return rows


def validate_defects(app: Path) -> list[str]:
    """Every way an answer-key row can be wrong *without* failing a trial, named at once."""
    problems: list[str] = []
    stories = {p.name for p in (app / "stories").glob("*") if p.is_dir()}
    diffs: dict[str, set[str]] = {}
    for row in load_defects(app):
        rid, story, path = str(row.get("id")), str(row.get("story")), str(row.get("path"))
        if story not in stories:
            problems.append(f"{rid}: story {story!r} is not one of {', '.join(sorted(stories))}")
            continue
        if story not in diffs:
            diff = story_diff(app, story)
            diffs[story] = {*diff["changed"], *diff["added"]}
        if path not in diffs[story]:
            where = "pinned by" if path in story_diff(app, story)["pinned"] else "not in"
            problems.append(
                f"{rid}: {path} is {where} {story}'s diff — the defect would be committed in "
                "the before tree and no obligation would be minted for it"
            )
        if not variant_path(app, row).is_file():
            problems.append(f"{rid}: no variant at {variant_path(app, row)}")
        if str(row.get("expect")) != "contradicted":
            problems.append(f"{rid}: expect must be 'contradicted', not {row.get('expect')!r}")
    return problems


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
    """Plant one defect in a materialized tree."""
    variant = variant_path(app, row)
    if not variant.is_file():
        raise TrialError(f"defect {row['id']}: no variant at {variant}")
    diff = story_diff(app, str(row["story"]))
    if str(row["path"]) not in {*diff["changed"], *diff["added"]}:
        raise TrialError(
            f"defect {row['id']}: {row['path']} is not in {row['story']}'s diff — seeding it "
            "would plant a defect in the before tree, outside what the trial is measured on"
        )
    target = repo / str(row["path"])
    if not target.is_file():
        raise TrialError(f"defect {row['id']}: {row['path']} is not in the materialized tree")
    shutil.copyfile(variant, target)


def defect_survived(app: Path, row: dict[str, str], witness: Path) -> bool:
    """Is the seeded file still byte-for-byte the defect variant at the end of the trial?"""
    target = witness / str(row["path"])
    if not target.is_file():
        return False
    return target.read_bytes() == variant_path(app, row).read_bytes()




def capture_witness(repo: Path, dest: Path, extra: tuple[str, ...] = ()) -> Path:
    """Copy the part of a finished trial tree the score reads, into the staged result."""
    dest.mkdir(parents=True, exist_ok=True)
    if (repo / "docs").is_dir():
        shutil.copytree(repo / "docs", dest / "docs", dirs_exist_ok=True)
    for name in ("agents.yml", ".agents.yml", "ostler.yml", "ostler.yaml"):
        if (repo / name).is_file():
            shutil.copyfile(repo / name, dest / name)
    for rel in extra:
        source = repo / rel
        if source.is_dir():
            shutil.copytree(
                source,
                dest / rel,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "node_modules"),
            )
        elif source.is_file():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest / rel)
    return dest




def evidence_statuses(witness: Path, story: str) -> dict[str, str] | None:
    """`{obligation id: status}` for the run's owed obligations, or None if unbuildable."""
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
    audit_ran: bool = True,
) -> tuple[str, str]:
    """Score one trial against its row."""
    refuted = str(audit.get("verdict", "")) == "refuted"
    if row is None:
        if statuses is None:
            return "inconclusive", "no evidence map"
        contradicted = sorted(k for k, v in statuses.items() if v == "contradicted")
        if contradicted:
            return "false", contradicted[0]
        return ("false", "audit refuted") if refuted else ("clean", "no contradiction")

    obligation = str(row["obligation"])
    route = str(row.get("caught_by") or "run")
    by_run = "" if route == "run" else " (expected audit)"
    by_audit = "" if route == "audit" else " (expected run)"
    status = (statuses or {}).get(obligation, "")
    if status == str(row["expect"]):
        return "caught", status + by_run
    cited = obligation in json.dumps(audit)
    if refuted and cited:
        return "caught", "audit refutation" + by_audit
    if not survived:
        return "caught", "defect repaired" + by_run
    if route == "audit" and not audit_ran:
        return "inconclusive", "no audit turn in this configuration"
    if statuses is None:
        return "inconclusive", "no evidence map"
    if not status:
        return "inconclusive", "obligation not owed by this trial"
    if status == "covered":
        return "missed", status
    return "inconclusive", status




BLANK = "–"

LEVERAGE_KEYS = ("entry", "deep_links", "roles", "obligations", "journeys", "sensitivity")

LEVERAGE_LABELS = {
    "entry": "entry",
    "deep_links": "deep-links",
    "roles": "roles",
    "obligations": "obligations",
    "journeys": "journeys",
    "sensitivity": "sensitivity",
}

PASSING_STATUS = "covered"


def route_matches(route: str, url: str) -> bool:
    """Whether a planned `goto` lands on a route the book documents."""
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
    """The route a screen node documents, or `""`."""
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
    """`{scenario id: {"covers": [...], "actions": [...]}}`, read statically from a `qa_plan.py`."""
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
    """The flow nodes this story owes live evidence for."""
    return sorted({
        str(obligation["node"])
        for obligation in packet.get("obligations", []) or []
        if isinstance(obligation, dict)
        and obligation.get("kind") == "journey"
        and obligation.get("required", True)
        and obligation.get("node")
    })


def flow_starts(book: dict[str, Any]) -> dict[str, str]:
    """`{flow node id: the route its `start:` screen documents}`."""
    routes = {str(node["id"]): _route_of(node) for node in book.get("nodes", []) or []}
    starts: dict[str, str] = {}
    for edge in book.get("edges", []) or []:
        if edge.get("via") == "start" and routes.get(str(edge.get("to"))):
            starts.setdefault(str(edge["from"]), routes[str(edge["to"])])
    return starts


def entry_routes(book: dict[str, Any]) -> set[str]:
    """Every route a user may legitimately arrive at from outside in-app navigation."""
    routes = {
        _route_of(node)
        for node in book.get("nodes", []) or []
        if node.get("bullets", {}).get("entry") and _route_of(node)
    }
    return routes | set(flow_starts(book).values())


def documented_routes(book: dict[str, Any]) -> set[str]:
    return {route for node in book.get("nodes", []) or [] if (route := _route_of(node))}


def book_sensitivity(repo: Path) -> list[int] | None:
    """`[claims observed by a check that could fail, claims the book mints]`, or None."""
    try:
        from ostler import model
        from ostler.qa import sensitivity as sensitivity_mod
    except ImportError:
        return None
    try:
        rows = sensitivity_mod.report(model.load(repo))
    except Exception:  # noqa: BLE001 - a book that will not load scores `–`, not a crash
        return None
    return [sum(1 for row in rows if row.status == "sensitive"), len(rows)] if rows else None


def leverage_from(
    book: dict[str, Any] | None,
    packet: dict[str, Any] | None,
    plan_source: str | None,
    run_log: list[dict[str, Any]] | None,
    statuses: dict[str, str] | None,
    sensitivity: list[int] | None = None,
) -> dict[str, Any]:
    """The six leverage metrics, each a `[n, of]` pair, an int, or None when incomputable."""
    scenarios = plan_scenarios(plan_source) if plan_source else {}
    if run_log is not None:
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
        "sensitivity": sensitivity,
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
    """The feature graph as `{"nodes": [...], "edges": [...]}`, or None if it will not load."""
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
    """Score one trial's artifacts."""
    spec = witness / "docs" / "specs" / story
    plan_file = spec / "qa_plan.py"
    return leverage_from(
        load_book(witness),
        read_json(spec / "qa-okf-context.json"),
        plan_file.read_text(encoding="utf-8") if plan_file.is_file() else None,
        read_ndjson(spec / "qa" / "qa-run.ndjson"),
        statuses,
        book_sensitivity(witness),
    )


BOOK_LEVEL_KEYS = frozenset({"sensitivity"})


def pool_leverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum the metrics across trials, keeping a metric None when no trial could compute it."""
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
                if current is None:
                    pooled[key] = pair
                elif key in BOOK_LEVEL_KEYS:
                    pooled[key] = max(current, pair, key=lambda seen: seen[1])
                else:
                    pooled[key] = [current[0] + pair[0], current[1] + pair[1]]
            else:
                pooled[key] = int(value) + (current or 0)
    return pooled


def leverage_line(metrics: dict[str, Any], keys: tuple[str, ...] = LEVERAGE_KEYS) -> str:
    """Print the metrics the fixture declared it can own, and say how many it left out."""
    parts = []
    for key in keys:
        value = metrics.get(key)
        if value is None:
            shown = BLANK
        elif isinstance(value, list):
            shown = f"{value[0]}/{value[1]}"
        else:
            shown = str(value)
        parts.append(f"{LEVERAGE_LABELS[key]} {shown}")
    line = "leverage: " + "  ".join(parts)
    if len(keys) < len(LEVERAGE_KEYS):
        line += f"  ({len(keys)} of {len(LEVERAGE_KEYS)} metrics)"
    return line




def headline(trials: list[dict[str, Any]]) -> str:
    seeded = [trial for trial in trials if trial["defect"] != CLEAN]
    caught = sum(1 for trial in seeded if trial["verdict"] == "caught")
    missed = sum(1 for trial in seeded if trial["verdict"] == "missed")
    false = sum(1 for trial in trials if trial["verdict"] == "false")
    unknown = sum(1 for trial in trials if trial["verdict"] == "inconclusive")
    line = f"caught {caught}/{len(seeded)}  missed {missed}  false {false}{fx.convergence(trials)}"
    if unknown:
        line += f"  inconclusive {unknown}"
    return line


def detail(trials: list[dict[str, Any]], leverage: tuple[str, ...] = LEVERAGE_KEYS) -> list[str]:
    lines: list[str] = []
    for trial in trials:
        timing = trial.get("timing") or {}
        lines.append(
            f"  {trial['defect']:<6} {trial['verdict']:<13} {trial['because']}"
            f"  [{timing.get('wall_s', 0) / 60:.0f}m]"
        )
        lines.append(f"    {trial['obligation'] or '(control)'}")
    lines.append("")
    lines.append("  " + leverage_line(pool_leverage(trials), leverage))
    if (leveraged := fx.time_leverage(trials)):
        lines.append("  " + leveraged)
    lines.append("")
    lines.extend(fx.node_table(trials))
    return lines




@dataclass(frozen=True, slots=True)
class Fixture:
    """Everything that distinguishes one frozen-app task from another."""

    app: str
    repo_dir: str
    budget_s: float = 2400.0
    leverage: tuple[str, ...] = LEVERAGE_KEYS
    first_verdict: bool = FIRST_VERDICT
    defects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        unknown = [key for key in self.leverage if key not in LEVERAGE_KEYS]
        if unknown or not self.leverage:
            raise ValueError(
                f"{self.app}: leverage must name one or more of {', '.join(LEVERAGE_KEYS)}; "
                f"got {self.leverage!r}"
            )


TRIALS = ("artifacts", "trials")


def key_dir(run: Run, fixture: Fixture) -> Path:
    """The tracked app tree, which is where `defects.yml` and the variants are read from."""
    directory = run.data_dir / fixture.app
    if not (directory / "defects.yml").is_file():
        raise TrialError(f"no answer key under {directory} — is --data-dir the repo's paddock/data/?")
    return directory


def trials_dir(run: Run) -> Path:
    directory = run.stage.joinpath(*TRIALS)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def plan_round(
    run: Run, app: Path, fixture: Fixture | None = None,
) -> list[tuple[str, dict[str, str] | None]]:
    """The trials to run: one control per story, then one per selected defect."""
    problems = validate_defects(app)
    if problems:
        raise TrialError(f"{app / 'defects.yml'} cannot be scored:\n  " + "\n  ".join(problems))
    wanted = run.param_list("defects") or (fixture.defects if fixture else ())
    rows = select_defects(app, wanted)
    stories = sorted({str(row["story"]) for row in rows})
    control: list[tuple[str, dict[str, str] | None]] = (
        [] if run.param_bool("no_control") else [(story, None) for story in stories]
    )
    return [*control, *[(str(row["story"]), row) for row in rows]]


def run_round(run: Run, fixture: Fixture) -> None:
    """Run the round: materialize, seed, drive `workhorse-coder run qa`, keep the witness."""
    app = key_dir(run, fixture)
    checkout = stablemate_checkout(run)
    budget = run.param_float("budget", fixture.budget_s)
    config = effective(run)
    runs_dir = trials_dir(run) / "runs"

    with no_leaks(checkout, pinned=pin_held(run.pinned)):
        ledger: list[dict[str, Any]] = []
        for index, (story, row) in enumerate(plan_round(run, app, fixture), start=1):
            variant = str(row["id"]) if row else CLEAN
            run_id = f"{fixture.repo_dir}-{run.label}-qa-{story}-{variant}-{index}"
            def install(repo: Path, run_id: str = run_id) -> None:
                run.cli(
                    *uv_run(checkout, "farrier"),
                    "farrier", "install", "--repo", str(repo),
                    cwd=checkout, log_name=f"{run_id}-farrier", check=True,
                )

            repo = materialize(run.repo, story, run.workdir(run_id) / fixture.repo_dir, install)
            if row:
                seed_defect(app, row, repo)
            reset_stack_state(repo)

            started, since = time.monotonic(), time.time()
            result = run.cli(
                *uv_run(checkout, "workhorse-workflows"),
                "workhorse-coder", "run", "qa",
                "--runs-dir", str(runs_dir), "--run-id", run_id,
                "--config", str(config),
                "--params", json.dumps(
                    {
                        "story": story, "docs_path": str(repo),
                        "stop_at_first_verdict": fixture.first_verdict,
                    }
                ),
                cwd=repo,
                env={**os.environ, "WORKHORSE_MAX_RUNTIME_S": str(budget), "AGENT_REPO_DIR": str(repo)},
                log_name=f"{run_id}-qa",
            )
            wall = time.monotonic() - started

            witness = capture_witness(
                repo,
                trials_dir(run) / run_id / "witness",
                extra=(str(row["path"]),) if row else (),
            )
            ledger.append({
                "run_id": run_id, "story": story, "defect": variant,
                "obligation": str(row["obligation"]) if row else "",
                "path": str(row["path"]) if row else "",
                "rc": result.returncode,
                "audit_turn": not fixture.first_verdict,
                "witness": str(witness.relative_to(run.stage)),
                "timing": fx.timing_of(run_id, wall, since),
                "laps": fx.laps_of(run_id, since),
            })
            run.write_json(trials_dir(run) / "trials.json", ledger)


def score_round(run: Run, fixture: Fixture) -> Score:
    """Detection beside cost beside leverage — exactly the round the replay harness printed."""
    ledger = run.stage.joinpath(*TRIALS) / "trials.json"
    if not ledger.is_file():
        return Score(headline="no trials recorded — the round did not reach a run", detail=())

    app = key_dir(run, fixture)
    by_id = {str(row["id"]): row for row in load_defects(app)}
    trials: list[dict[str, Any]] = []
    for entry in json.loads(ledger.read_text(encoding="utf-8")):
        row = by_id.get(str(entry["defect"]))
        witness = run.stage / str(entry["witness"])
        statuses = evidence_statuses(witness, str(entry["story"]))
        audit = audit_result(run.stage.joinpath(*TRIALS) / "runs", str(entry["run_id"]))
        verdict, because = classify(
            row,
            statuses,
            audit,
            survived=defect_survived(app, row, witness) if row else True,
            audit_ran=bool(audit) or bool(entry.get("audit_turn", not FIRST_VERDICT)),
        )
        trials.append({
            **entry,
            "verdict": verdict,
            "because": because,
            "leverage": leverage(witness, str(entry["story"]), statuses),
        })

    return Score(
        headline=headline(trials),
        detail=tuple(detail(trials, fixture.leverage)),
        data={"trials": trials, "leverage": pool_leverage(trials)},
    )

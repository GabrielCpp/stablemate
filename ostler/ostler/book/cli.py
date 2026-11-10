"""`python -m ostler.book <command> <service module> ...`

A request on the command line is a Python expression over the service's words:
its endpoints and fixtures, plus `today`, `date` and `timedelta`. For example
`--given "AddTodo(todo('Buy milk', due_on=today + timedelta(days=2)))"`."""

from __future__ import annotations

import argparse
import dataclasses
import ast
import builtins
import importlib
import io
import os
import random
import sys
import time
from datetime import date, timedelta
from typing import Any

from ostler.book.backstage import CannotArrange
from ostler.book.cells import Played, play
from ostler.book.check import broken, cmd_check
from ostler.book.decisions import cmd_decisions, load as load_decisions
from ostler.book.defects import declared, never_met, met, section, tally
from ostler.book.denied import denied
from ostler.book.environment import Environment, credentials
from ostler.book.errors import Unhealthy
from ostler.book.explore import attempts, moves
from ostler.book.exploration import BASELINE, REFUSED, Cell, Played as Explored, Walk, never_refused, play as play_cells, seed, unreached
from ostler.book.graph import dot, render
from ostler.book.index import cmd_index, cmd_search_book
from ostler.book.http import Endpoint, identity_lines, named_shapes
from ostler.book.inputs import Tried, play as play_inputs
from ostler.book.journey import JourneyResult
from ostler.book.matrix import matrix
from ostler.book.model import Model
from ostler.book.planner import plan
from ostler.book.runner import attempt, blocked, walk
from ostler.book.state import Impossible
from ostler.book.search import KINDS, cmd_explain, cmd_search
from ostler.book.witness import WitnessReport, witnessed
from ostler.book.service import Service
from ostler.book.stack import Stack
from ostler.book.sources import head_of, stale
from ostler.book.surface import Surface


def load(name: str) -> Service[Any]:
    return importlib.import_module(f"{name}.service").service


def build_parser(embedded: bool = False) -> argparse.ArgumentParser:
    """The command line of the book runtime. `embedded` is the form `ostler` mounts under its own `book` command, which
    has no help of its own and names its verb apart from the host's."""
    parser = argparse.ArgumentParser(prog="ostler book", add_help=not embedded)
    sub = parser.add_subparsers(dest="book_command" if embedded else "command", required=not embedded)
    run = sub.add_parser("run", help="walk every journey on the service's surface, against its model")
    run.add_argument("service")
    run.add_argument("--journey", action="append")
    run.add_argument("--out", default="results")
    run.add_argument("--no-stack", action="store_true")
    run.add_argument("--order", choices=("declared", "reversed", "shuffled"), default="declared",
                     help="the order the journeys are taken in on the one long-lived account")
    run.add_argument("--seed", type=int, default=0, help="the seed of a shuffled order")
    run.add_argument("--partial", action="store_true",
                     help="a run of some journeys only: unseen answers and unmet defects do not fail it")
    run.add_argument("--only", action="append", default=[], metavar="ENDPOINT",
                     help="play only the journeys that call these endpoints, their declared cells and their input classes; "
                          "repeatable or comma-separated")
    explorer = sub.add_parser("explore", help="walk the model's state graph, then play every state, action and input class once")
    explorer.add_argument("service")
    explorer.add_argument("--depth", type=int, default=4)
    explorer.add_argument("--out", default="results")
    explorer.add_argument("--no-stack", action="store_true")
    explorer.add_argument("--seed-only", action="store_true", help="walk and list the cells without touching the app")
    explorer.add_argument("--only", action="append", default=[], metavar="ENDPOINT",
                          help="play the cells of these endpoints only, repeatable or comma-separated; the walk stays whole")
    live = sub.add_parser("walk", help="arrange one matrix scene on the live service, then take one action there")
    live.add_argument("service")
    live.add_argument("--record", help="the record whose matrix is meant; omitted, the service's first")
    live.add_argument("--scene", required=True, help="a scene named in that matrix")
    live.add_argument("--action", help="an action named in that matrix; omitted, only the scene is arranged")
    live.add_argument("--out", default="results")
    live.add_argument("--no-stack", action="store_true")
    for p in (run, explorer, live):
        p.add_argument("--print-exec", action="store_true", help="print the saddlebag command that would supply the secrets, and stop")
    find = sub.add_parser("search", help="find a term among the endpoints, rules, actions, journeys, screens and scenes")
    find.add_argument("term", help="the text to find; the old form `search <service> <term>` still works")
    find.add_argument("extra", nargs="?", help=argparse.SUPPRESS)
    find.add_argument("--service", help="search this service only; omitted, every service under services/")
    find.add_argument("--kind", choices=KINDS)
    explain = sub.add_parser("explain", help="everything the book says of one endpoint, action, screen or journey")
    explain.add_argument("service")
    explain.add_argument("name", help="a class name")
    indexer = sub.add_parser("index", help="write the service's index.tsv, which search reads without importing the service")
    indexer.add_argument("service")
    checker = sub.add_parser("check", help="build everything the book declares, with no stack, and name what is broken")
    checker.add_argument("service")
    checker.add_argument("--app", help="the app's root; every source pointer must exist under it")
    for p in (run, explorer, live, checker):
        p.add_argument("--env", help="the environment to reach, by name; omitted, the service's default")
    for name, text in (("stale", "list the elements whose source changed since the verified commit"),
                       ("verified", "record the app's HEAD as the commit the book is verified against")):
        p = sub.add_parser(name, help=text)
        p.add_argument("service")
        p.add_argument("--app", required=True, help="the app's root")
    listing = sub.add_parser("decisions", help="list the decisions the service settled")
    listing.add_argument("service")
    listing.add_argument("--story")
    listing.add_argument("--element")
    graph = sub.add_parser("graph", help="draw each record's state graph and table from the matrix, as dot and svg")
    graph.add_argument("service")
    graph.add_argument("--record", help="one record; omitted, every matrix")
    graph.add_argument("--out", default="results")
    for name in ("endpoints", "screens", "matrix", "denied", "plan"):
        p = sub.add_parser(name)
        p.add_argument("service")
        if name == "screens":
            p.add_argument("--lang", default="en")
        if name in ("denied", "plan"):
            p.add_argument("--given", action="append", default=[], help="a request to perform first, as an expression")
        if name == "plan":
            p.add_argument("--goal", required=True, help="an expression over `state` that holds where the user wants to be")
            p.add_argument("--text", action="append", default=[], help="a text the planner may put in a string field")
            p.add_argument("--depth", type=int, default=8)
            p.add_argument("--only", help="comma separated step kinds the plan may use, by class name prefix, e.g. add,remove")
    return parser


def main(argv: list[str] | None = None) -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(line_buffering=True)
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "search":
        if args.extra is not None:
            if not args.term.startswith("services."):
                parser.error(f"search takes a term and --service, or the old `<service> <term>`; {args.term!r} is not a service")
            args.service, args.term = args.term, args.extra
        else:
            return cmd_search_book(args)
    service = load(args.service)
    if args.command in ("run", "explore", "walk", "check"):
        args.environment = service.environment(args.env)
    if args.command in ("run", "explore", "walk") and not getattr(args, "seed_only", False):
        stop = credentials(args.environment, sys.argv[1:] if argv is None else argv, args.print_exec)
        if stop is not None:
            return stop
    return COMMANDS[args.command](service, args)


def cmd_endpoints(service: Service[Any], args: argparse.Namespace) -> int:
    for name, shape in named_shapes(service.endpoints).items():
        print(name)
        print(shape.describe_fields())
        print()
    for endpoint in service.endpoints:
        print(endpoint.describe())
        print()
    lines = identity_lines(service.endpoints)
    if lines:
        print("\n".join(lines))
    return 0


def cmd_screens(service: Service[Any], args: argparse.Namespace) -> int:
    for screen in service.screens:
        print(screen.describe(args.lang))
        print()
    if service.interactions:
        print("interactions:")
        for interaction in service.interactions:
            print("  " + interaction.describe())
    return 0


def cmd_matrix(service: Service[Any], args: argparse.Namespace) -> int:
    print("\n\n".join(matrix(service.new_model, axes) for axes in service.matrices))
    return 0


def cmd_graph(service: Service[Any], args: argparse.Namespace) -> int:
    chosen = [a for a in service.matrices if args.record is None or a.record == args.record]
    if not chosen:
        axes_of(service, args.record)
    os.makedirs(args.out, exist_ok=True)
    for axes in chosen:
        path = os.path.join(args.out, f"{service.name}-{axes.record}.dot")
        source = dot(service.new_model, axes)
        with open(path, "w") as f:
            f.write(source + "\n")
        svg = render(source, path)
        print(path + (f" and {svg}" if svg else " (no `dot` on this machine, so no svg)"))
    return 0


def axes_of(service: Service[Any], record: str | None):
    for axes in service.matrices:
        if record is None or axes.record == record:
            return axes
    raise SystemExit(f"no matrix for {record!r}; the records are " + ", ".join(a.record for a in service.matrices))


def made_ready(service: Service[Any], args: argparse.Namespace) -> tuple[Surface, Stack] | int:
    """The surface and the stack, begun and healthy, or the exit code where the place cannot be judged or
    lets the run arrange nothing."""
    surface = _surface(service, args.environment)
    stack = service.stack(os.path.join(args.out, "logs"))
    try:
        why = begin(surface, stack, args)
    except Unhealthy as sick:
        print(f"could not judge: {sick}")
        return 3
    if why:
        show_skips(args.environment, [why])
        return 0
    return surface, stack


def cmd_walk(service: Service[Any], args: argparse.Namespace) -> int:
    axes = axes_of(service, args.record)
    scene = axes.scene(args.scene)
    if args.action and args.action not in axes.actions:
        print(f"no action named {args.action!r}; the actions are " + ", ".join(axes.actions))
        return 2
    begun = made_ready(service, args)
    if isinstance(begun, int):
        return begun
    surface, stack = begun
    try:
        _set_lang(surface, "en")
        try:
            surface.reset()
        except CannotArrange as cannot:
            show_skips(args.environment, [cannot.reason])
            return 0
        today = _today(surface)
        model = service.new_model(today)
        print(f"{scene.name}: {scene.when}")
        taken = []
        for step in scene.reached_by(today):
            taken.append(attempt(step, model, surface))
            if not taken[-1].ok or taken[-1].skipped:
                break
        if args.action and all(t.ok and not t.skipped for t in taken):
            action = axes.actions[args.action](model)
            if action is None or isinstance(action, Impossible):
                print(f"{args.action}: impossible in this scene, {getattr(action, 'why', 'the model builds no such step')}")
            else:
                taken.append(attempt(action, model, surface))
        for step in taken:
            outcome = f"  → {step.app}" if step.app is not None else ""
            print(f"  {'SKIP' if step.skipped else 'ok  ' if step.ok else 'FAIL'}  {step.text}{outcome}" + (f"\n        {step.trace}" if step.trace else "")
                  + (f"\n        {step.note}" if step.note else ""))
        print(f"now: {axes.told_apart(model)}")
        print(model.describe())
    finally:
        surface.stop()
        if not args.no_stack:
            stack.stop()
    show_skips(args.environment, [t.skipped for t in taken if t.skipped])
    return 0 if all(t.ok for t in taken) else 1


BUILTINS = {name: getattr(builtins, name) for name in ("len", "any", "all", "sum", "sorted", "min", "max")}


def words(service: Service[Any], model: Model) -> dict[str, object]:
    return {**service.words, "today": model.today, "date": date, "timedelta": timedelta}


def scope(service: Service[Any], model: Model, names: dict[str, object]) -> dict[str, object]:
    return {"__builtins__": BUILTINS, **words(service, model), **names}


def _given(service: Service[Any], givens: list[str]) -> tuple[Model, dict[str, object]]:
    """The model after the requests, and the names the givens bound: `p = project('X')`
    binds `p`, any other expression is a request to perform."""
    model = service.new_model(date.today())
    names: dict[str, object] = {}
    for expression in givens:
        tree = ast.parse(expression.strip(), mode="exec")
        env = scope(service, model, names)
        if len(tree.body) == 1 and isinstance(tree.body[0], ast.Assign) and len(tree.body[0].targets) == 1 \
                and isinstance(tree.body[0].targets[0], ast.Name):
            names[tree.body[0].targets[0].id] = eval(compile(ast.Expression(tree.body[0].value), "<given>", "eval"), env)
        else:
            model.apply(eval(expression, env))
    return model, names


def cmd_denied(service: Service[Any], args: argparse.Namespace) -> int:
    model, _ = _given(service, args.given)
    print("From this state:")
    print(model.describe())
    print()
    if not service.endpoints:
        print("the service declares no endpoint to derive attempts from")
        return 2
    for denial in denied(model, attempts(service.endpoints, model, cast=service.cast)):
        print(denial)
    return 0


def cmd_plan(service: Service[Any], args: argparse.Namespace) -> int:
    model, names = _given(service, args.given)
    print("From:")
    print(model.describe())
    print(f"Wanted: {args.goal}")
    allowed = moves(service.endpoints, tuple(args.text), service.cast)
    if args.only:
        kinds = tuple(k.strip().lower() for k in args.only.split(","))
        narrowed = allowed

        def only_those(state: Model) -> list[Endpoint]:
            return [m for m in narrowed(state) if type(m).__name__.lower().startswith(kinds)]

        allowed = only_those

    def goal(state: Model) -> bool:
        return bool(eval(args.goal, {**scope(service, state, names), "state": state}))

    path = plan(model, goal, allowed, args.depth)
    if path is None:
        print(f"No way there within {args.depth} moves.")
        return 1
    print(f"{len(path)} moves:")
    for n, move in enumerate(path, 1):
        model.apply(move)
        print(f"  {n}. {move}  → " + ", ".join(str(r) for r in model.rows()))
    return 0


def cmd_run(service: Service[Any], args: argparse.Namespace) -> int:
    if args.journey and not args.partial:
        print("a run of some journeys leaves the rest unseen: add --partial")
        return 2
    if broken(service, args.service):
        return 1
    begun = made_ready(service, args)
    if isinstance(begun, int):
        return begun
    surface, stack = begun
    results: list[JourneyResult] = []
    names = named(service, args.only)
    journeys = [j for j in service.journeys
                if (not args.journey or j.title() in args.journey) and (not names or touches(service, j, names))]
    if names:
        print(f"only what calls {', '.join(sorted(names))}: {len(journeys)} of {len(service.journeys)} journeys")
    if args.order == "reversed":
        journeys.reverse()
    elif args.order == "shuffled":
        random.Random(args.seed).shuffle(journeys)
    order = args.order + (f" (seed {args.seed})" if args.order == "shuffled" else "")
    print(f"order: {order}")
    began = time.time()
    try:
        sick = unhealthy(service, surface)
        if sick:
            print(f"could not judge: {sick}")
            return 3
        model, why = renewed(service, surface)
        for journey in journeys:
            started = time.time()
            _set_lang(surface, journey.lang)
            if journey.alone or model is None:
                model, why = renewed(service, surface)
            result = walk(journey, model, surface) if model is not None else blocked(journey, surface, why)
            results.append(result)
            print(f"{result.verdict}  {journey.title()}  ({len(result.steps)} steps, {time.time() - started:.1f}s)"
                  + ("  [alone]" if journey.alone else ""))
            for step in result.steps:
                if not step.ok:
                    print(f"      at: {step.text}\n      {step.note}")
                elif step.skipped:
                    print(f"      {step.note}")
            if not result.ok:
                for defect in result.defects:
                    if defect.does is not None:
                        print(f"      a known defect made a wrong change earlier in this journey: {defect.status} {defect.message}; "
                              "if the app no longer makes it, delete its declaration")
            if journey.alone or not result.ok or result.skipped:
                model, why = renewed(service, surface)
        journeys_took = time.time() - began
        played = Played()
        if not args.journey and service.matrices:
            _set_lang(surface, "en")
            print(f"journeys took {journeys_took:.0f}s; playing the cells")
            began = time.time()
            played = play(service.matrices, surface, lambda: fresh(service, surface),
                          keep=lambda axes, scene, name: not names or aims(service, axes, scene, name, names))
            cells_took = time.time() - began
        else:
            cells_took = 0.0
        tried = Tried()
        inputs_took = 0.0
        if not args.journey and service.endpoints:
            print("playing the input classes")
            began = time.time()
            tried = play_inputs(service, surface, lambda: fresh(service, surface), only=names)
            inputs_took = time.time() - began
        seen = witnessed(service, surface)
        if names:
            seen = dataclasses.replace(seen, gaps=[g for g in seen.gaps if g.endpoint.__name__ in names],
                                       unseen=tuple(u for u in seen.unseen if u.endpoint.__name__ in names))
    except Unhealthy as sick:
        print(f"could not judge: {sick}")
        print(f"what ran before it is no verdict: {len(results)} journeys")
        return 3
    finally:
        surface.stop()
        if not args.no_stack:
            stack.stop()
    skips = [r.skipped for r in results if r.skipped] + [c.skipped for c in played.cells if c.skipped] \
        + [s.skipped for s in tried.sent if s.skipped]
    partial = args.partial or bool(skips) or bool(names)
    found = declared(service, args.service)
    report(service, results, args.out, order, found, not partial, played, tried)
    print(tally(results))
    for c in played.cells:
        if not c.ok:
            print(f"FAIL  cell {c.text}\n      {c.note}")
    print(f"cells: {played.count} played on {played.arrangements} arrangements, {sum(1 for c in played.cells if c.why)} impossible, "
          f"{sum(1 for c in played.cells if not c.ok)} fail")
    for s in tried.sent:
        if not s.ok:
            print(f"FAIL  input {s.text}\n      {s.note}")
    unmet = [d for d in service.diverges if tried.sent and d not in tried.diverged
             and (not names or d.endpoint.__name__ in names)]
    if unmet and (not partial or names):
        print("Declared divergences never met (fails the run)")
        for d in unmet:
            print(f"- {d}: {d.why}")
    print(f"inputs: {sum(1 for s in tried.sent if not s.skipped)} played, {len(tried.diverged)} diverge as declared, "
          f"{sum(1 for s in tried.sent if not s.ok)} fail")
    print(f"time: journeys {journeys_took:.1f}s, cells {cells_took:.1f}s, inputs {inputs_took:.1f}s")
    everything = [*results, played, tried]
    stale = never_met(found, met(everything))
    for line in section(everything, found, not partial):
        print(line)
    show_witness(service, seen, args.out, not partial)
    show_skips(args.environment, skips)
    return 0 if (all(r.ok for r in results) and played.ok and tried.ok and not (names and unmet)
                 and (partial or (not stale and not unmet and seen.complete))) else 1


def cmd_explore(service: Service[Any], args: argparse.Namespace) -> int:
    if broken(service, args.service):
        return 1
    if args.seed_only:
        began = time.time()
        walked, cells = seed(service, service.new_model(date.today()), args.depth)
        walk_took = time.time() - began
        picked = chosen(service, cells, args.only)
        for cell in picked:
            print(cell.text)
        report_exploration(service, args, walked, cells, walk_took, None, 0.0, unreached(service, date.today(), walked), picked)
        return 0
    begun = made_ready(service, args)
    if isinstance(begun, int):
        return begun
    surface, stack = begun
    try:
        _set_lang(surface, "en")
        try:
            start = fresh(service, surface)
        except CannotArrange as cannot:
            show_skips(args.environment, [cannot.reason])
            return 0
        began = time.time()
        walked, cells = seed(service, start, args.depth)
        walk_took = time.time() - began
        picked = chosen(service, cells, args.only)
        began = time.time()
        played = play_cells(service, picked, surface, lambda: fresh(service, surface))
        play_took = time.time() - began
    finally:
        surface.stop()
        if not args.no_stack:
            stack.stop()
    report_exploration(service, args, walked, cells, walk_took, played, play_took, unreached(service, start.today, walked), picked)
    show_skips(args.environment, played.skips)
    return 0 if played.ok else 1


def named(service: Service[Any], only: list[str]) -> frozenset[str]:
    """The endpoint names `--only` gives, each one checked against the service."""
    names = frozenset(n.strip() for item in only for n in item.split(",") if n.strip())
    known = {e.__name__ for e in service.endpoints}
    unknown = sorted(names - known)
    if unknown:
        raise SystemExit(f"--only names no endpoint of {service.name}: {', '.join(unknown)}; known: {', '.join(sorted(known))}")
    return names


def chosen(service: Service[Any], cells: list[Cell], only: list[str]) -> list[Cell]:
    """The cells of the named endpoints, or every cell when none is named."""
    names = named(service, only)
    if not names:
        return cells
    return [c for c in cells if c.endpoint in names]


def touches(service: Service[Any], journey: Any, names: frozenset[str]) -> bool:
    """Whether the journey calls one of the named endpoints, found on the model alone.
    A journey the model cannot walk is kept, so a broken one is never left out."""
    model = service.new_model(date.today())
    try:
        for given in journey.given:
            if type(given.request).__name__ in names:
                return True
            model.perform(given.request)
        for step in journey().steps(model.today):
            if getattr(type(step), "carries", None) is None:
                continue
            if type(step).__name__ in names:
                return True
            model.perform(step)
    except Exception:
        return True
    return False


def aims(service: Service[Any], axes: Any, scene: Any, name: str, names: frozenset[str]) -> bool:
    """Whether a declared cell calls one of the named endpoints, found on the model alone.
    A cell the model cannot build is kept."""
    try:
        action = axes.actions[name](scene.arrange(service.new_model(axes.today)))
    except Exception:
        return True
    return type(action).__name__ in names


def begin(surface: Surface, stack: Any, args: argparse.Namespace) -> str:
    """Starts the stack and the surface. The reason the surface cannot start here, or an empty string."""
    if not args.no_stack:
        stack.start()
    try:
        surface.start()
    except (CannotArrange, Unhealthy) as cannot:
        surface.stop()
        if not args.no_stack:
            stack.stop()
        if isinstance(cannot, Unhealthy):
            raise
        return cannot.reason
    return ""


def unhealthy(service: Service[Any], surface: Surface) -> str:
    """Why the environment cannot be judged, or an empty string: each health
    journey the service declares, played on a fresh model, must pass."""
    for journey in service.health:
        result = walk(journey, fresh(service, surface), surface)
        bad = next((step for step in result.steps if not step.ok or step.skipped), None)
        if bad is not None:
            return f"the health journey {journey.title()} fails at: {bad.text}: {bad.note}"
    return ""


def renewed(service: Service[Any], surface: Surface) -> tuple[Model | None, str]:
    try:
        return fresh(service, surface), ""
    except CannotArrange as cannot:
        return None, cannot.reason


def show_skips(environment: Environment, reasons: list[str]) -> None:
    if reasons:
        print(f"skipped {len(reasons)} (cannot arrange in {environment.name})")
        for reason in dict.fromkeys(reasons):
            print(f"  - {reason}")


def baselines(cells: list[Cell]) -> int:
    return sum(1 for c in cells if c.label == BASELINE)


def refusals(cells: list[Cell]) -> int:
    return sum(1 for c in cells if c.label.startswith(REFUSED))


def report_exploration(service: Service[Any], args: argparse.Namespace, walked: Walk, cells: list[Cell], walk_took: float,
                       played: Explored | None, play_took: float, missing: list[str], picked: list[Cell] | None = None) -> None:
    picked = cells if picked is None else picked
    unrefused = never_refused(service, service.new_model(date.today()), cells)
    lines = [f"# {service.name}: exploration", "",
             f"Depth bound {args.depth}. The walk stopped at depth {walked.reached}: {walked.stopped}.", "",
             "| depth | new signatures |", "|---|---|"]
    lines += [f"| {d} | {n} |" for d, n in enumerate(walked.per_depth)]
    lines += ["", f"{len(walked.nodes)} signatures, {len(cells)} cells: {baselines(cells)} baselines, "
                    f"{refusals(cells)} refusals, {len(cells) - baselines(cells) - refusals(cells)} input classes, {sum(1 for c in cells if c.writes)} writes."]
    if len(picked) != len(cells):
        lines += [f"Only the cells of {', '.join(args.only)}: {len(picked)} of {len(cells)}."]
    if played is not None:
        lines += [f"{played.played} cells played on {played.arrangements} arrangements, "
                  f"{played.shared} shared by {played.shared_cells} cells that change nothing.",
                  f"Time: walk {walk_took:.1f}s, play {play_took:.1f}s.", ""]
        if played.failures:
            lines += ["## Failures", ""]
            for f in played.failures:
                lines += [f"- {f.text}", f"  - path: {'; '.join(f.path) or '(start)'}", f"  - {f.note}"]
            lines.append("")
    else:
        lines += [f"Time: walk {walk_took:.1f}s. Nothing was played (--seed-only).", ""]
    lines += ["## Declared scenes the walk never reached", ""]
    lines += [f"- {m}" for m in missing] or ["- none"]
    lines += ["", "## Rules never refused", ""]
    lines += [f"- {r}" for r in unrefused] or ["- none"]
    lines += ["", "## Cells", ""] + [f"- {c.text}{' (writes)' if c.writes else ''}" for c in picked]
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, f"{service.name}-explore.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"explore {service.name}: depth bound {args.depth}, stopped at depth {walked.reached}: {walked.stopped}")
    print("signatures per depth: " + ", ".join(f"{d}: {n}" for d, n in enumerate(walked.per_depth)) + f" ({len(walked.nodes)} in all)")
    if len(picked) != len(cells):
        print(f"only the cells of {', '.join(args.only)}: {len(picked)} of {len(cells)}")
    if played is not None:
        for f in played.failures:
            print(f"FAIL  {f.text}\n      path: {'; '.join(f.path) or '(start)'}\n      {f.note}")
        print(f"cells: {len(cells)} total ({baselines(cells)} baselines, {refusals(cells)} refusals, {len(cells) - baselines(cells) - refusals(cells)} classes), {played.played} played, {played.arrangements} arrangements, "
              f"{played.shared} shared by {played.shared_cells} cells, {len(played.failures)} fail")
        print(f"time: walk {walk_took:.1f}s, play {play_took:.1f}s")
    else:
        print(f"cells: {len(cells)} total ({baselines(cells)} baselines, {refusals(cells)} refusals, {len(cells) - baselines(cells) - refusals(cells)} classes, "
              f"{sum(1 for c in cells if c.writes)} writes), none played; time: walk {walk_took:.1f}s")
    print(f"rules never refused: {len(unrefused)}")
    for r in unrefused:
        print(f"  {r}")
    print(f"declared scenes never reached: {len(missing)}")
    for m in missing:
        print(f"  {m}")


def show_witness(service: Service[Any], seen: WitnessReport, out: str, fails: bool = True) -> None:
    text = seen.text(service.name, fails)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, f"{service.name}-witness.md"), "w") as f:
        f.write(text + "\n")
    print(text)


def fresh(service: Service[Any], surface: Surface) -> Model:
    """A reset surface and a new model of it, in step."""
    surface.reset()
    return service.new_model(_today(surface))


def report(service: Service[Any], results: list[JourneyResult], out: str, order: str = "declared",
           found: list[tuple[type, Any]] | None = None, complete: bool = True, played: Played | None = None,
           tried: Tried | None = None) -> None:
    os.makedirs(out, exist_ok=True)
    lines = [f"# {service.name}", "", f"{tally(results)}.",
             "", f"Journeys taken in {order} order on one long-lived account.", ""]
    lines += section(results, found or [], complete)
    for result in results:
        lines.append(f"## {result.verdict} {result.journey.title()}")
        lines.append("")
        lines.append(result.journey.story())
        lines.append("")
        lines.append("| # | step | model | reduced to | app | listed afterwards |")
        lines.append("|---|---|---|---|---|---|")
        for n, step in enumerate(result.steps, 1):
            listed = "<br>".join(str(r) for r in step.app_rows) or "(empty)"
            mark = " (known defect)" if step.known is not None else " (skipped)" if step.skipped else "" if step.ok else " ❌"
            model = step.model if step.model is not None else ""
            app = step.app if step.app is not None else ""
            lines.append(f"| {n} | {step.text} | {model} | {step.trace} | {app}{mark} | {listed} |")
            if step.note:
                lines.append(f"| | | | | {step.note} | |")
        lines.append("")
        lines.append("The model at the end:")
        lines.append("")
        lines.append("```")
        lines.append(result.state)
        lines.append("```")
        lines.append("")
    if played is not None and played.cells:
        lines += ["## The state table played", "", "| cell | verdict | model / app |", "|---|---|---|"]
        for c in played.cells:
            lines.append(f"| {c.text} | {c.verdict}{' ' + c.why if c.why else ''}{' ' + c.note if c.note else ''} | {c.outcome} |")
        lines.append("")
    if tried is not None and tried.sent:
        lines += ["## The input classes sent", "", "| input | verdict | model / app |", "|---|---|---|"]
        for s in tried.sent:
            lines.append(f"| {s.text} | {s.verdict}{' ' + s.note if s.note else ''} | {s.outcome} |")
        lines.append("")
    with open(os.path.join(out, f"{service.name}.md"), "w") as f:
        f.write("\n".join(lines))


def _package_dir(args: argparse.Namespace) -> str:
    return os.path.dirname(importlib.import_module(args.service).__file__ or "")


def traced(service: Service[Any], args: argparse.Namespace) -> Any | None:
    """What changed in the app since the book was last verified, or None where the service declares no app."""
    if service.app is None:
        print(f"{service.name} declares no app")
        return None
    return stale(service, args.app, _package_dir(args))


def cmd_stale(service: Service[Any], args: argparse.Namespace) -> int:
    found = traced(service, args)
    if found is None:
        return 2
    if found.verified is None:
        print("not verified: write the commit with 'verified'")
        return 2
    print(f"verified at {found.verified}, app at {found.head}")
    print("\n## Stale elements")
    for element, paths in found.stale.items():
        for path, commits in paths.items():
            coarse = " (file level)" if (element, path) in found.coarse else ""
            print(f"- {element}: {path} ({len(commits)} commits: {', '.join(commits)}){coarse}")
    print("\n## Changed files no element names")
    for path, commits in found.unnamed.items():
        print(f"- {path} ({len(commits)} commits: {', '.join(commits)})")
    print("\n## Changed functions no element names")
    for path, functions in found.functions.items():
        for function, commits in functions.items():
            print(f"- {path}::{function} ({len(commits)} commits: {', '.join(commits)})")
    print("\n## Changed beside the named symbols, functions not told apart")
    for path, (commits, names) in found.beside.items():
        print(f"- {path} ({len(commits)} commits: {', '.join(commits)}) named by {', '.join(names)}")
    print("\n## Pointers to files that no longer exist")
    for element, path in found.missing:
        print(f"- {element}: {path}")
    touched = [*found.stale, *(n for _, names in found.beside.values() for n in names)]
    print("\n## Decisions touching stale elements")
    for d in load_decisions(args.service):
        for element in d.elements:
            if element in touched:
                print(f"- {d.slug} (story {d.story}) via {element}")
                break
    if found.stale or found.open or found.beside:
        return 1
    print("\nnothing stale")
    return 0


def cmd_verified(service: Service[Any], args: argparse.Namespace) -> int:
    found = traced(service, args)
    if found is None or service.app is None:
        return 2
    if found.open:
        print("not verified: name or ignore every changed file and function, and fix every missing pointer; `stale` lists them")
        return 1
    head = head_of(args.app)
    with open(os.path.join(_package_dir(args), service.app.verified), "w") as f:
        f.write(head + "\n")
    print(head)
    return 0


COMMANDS = {"stale": cmd_stale, "decisions": cmd_decisions, "verified": cmd_verified, "check": cmd_check, "explore": cmd_explore, "search": cmd_search, "index": cmd_index, "explain": cmd_explain, "run": cmd_run, "walk": cmd_walk, "endpoints": cmd_endpoints, "screens": cmd_screens, "matrix": cmd_matrix,
            "denied": cmd_denied, "plan": cmd_plan, "graph": cmd_graph}


def _surface(service: Service[Any], environment: Environment) -> Surface:
    surface = service.surface(environment)
    follow = getattr(surface, "follow", None)
    if callable(follow):
        follow(service.watch)
    return surface


def _set_lang(surface: Surface, lang: str) -> None:
    speak = getattr(surface, "set_lang", None)
    if callable(speak):
        speak(lang)


def _today(surface: Surface) -> date:
    tell = getattr(surface, "today", None)
    told = tell() if callable(tell) else None
    return told if isinstance(told, date) else date.today()


if __name__ == "__main__":
    sys.exit(main())

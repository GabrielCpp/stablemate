"""ostler command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import version as _pkg_version
from pathlib import Path

import yaml

from . import (
    backlog as backlog_mod,
    crud,
    crud_generic,
    doctor,
    edit,
    freeze as freeze_mod,
    path as path_mod,
    query as query_mod,
    registry,
    select,
    templates as templates_mod,
    todo as todo_mod,
    trace,
)
from . import vet as vet_mod
from . import artifact as artifact_mod
from .model import load

_TYPES = tuple(t.name for t in registry.REGISTRY) + ("seed", "gap")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ostler", description="Tend your documentation graph.")
    p.add_argument("--version", action="version", version=f"ostler {_pkg_version('ostler')}")
    p.add_argument("-C", "--chdir", metavar="DIR", help="operate as if run from DIR")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("doctor", help="referential-integrity check")
    d.add_argument("--epic", help="restrict checks to one epic (name or folder)")
    d.add_argument("--json", action="store_true", help="emit the structured report as JSON")
    d.add_argument("--no-schema", action="store_true", help="skip JSON Schema validation")

    t = sub.add_parser("trace", help="walk the graph from a node")
    t.add_argument("token", help="seed id, story slug, gap id, surface or doc path")

    # ---- retrieval --------------------------------------------------------
    ls = sub.add_parser("list", help="list Concepts of a type")
    ls.add_argument("--type", required=True, dest="etype",
                    help=f"one of {', '.join(_TYPES)}, or a template-declared kind")
    ls.add_argument("--epic")
    ls.add_argument("--status")
    ls.add_argument("--json", action="store_true")

    se = sub.add_parser("search", help="full-text search over Concepts")
    se.add_argument("q")
    se.add_argument("--type", dest="etype",
                    help=f"one of {', '.join(_TYPES)}, or a template-declared kind")
    se.add_argument("--owner")
    se.add_argument("--tag")
    se.add_argument("--json", action="store_true")

    qy = sub.add_parser("query", help="reverse-index queries")
    qy.add_argument("name", choices=query_mod.QUERIES)
    qy.add_argument("arg")
    qy.add_argument("--json", action="store_true")

    ne = sub.add_parser("next-epic", help="the next epic with unfinished work")
    ne.add_argument("--json", action="store_true")
    ns = sub.add_parser("next-story", help="the next runnable story in an epic")
    ns.add_argument("epic")
    ns.add_argument("--json", action="store_true")

    # ---- CRUD -------------------------------------------------------------
    cr = sub.add_parser("create", help="create an epic/story/feature (allocates an id)")
    crs = cr.add_subparsers(dest="what", required=True)
    cre = crs.add_parser("epic")
    cre.add_argument("name")
    cre.add_argument("--title", required=True)
    cre.add_argument("--prefix")
    cre.add_argument("--json", action="store_true")
    crt = crs.add_parser("story")
    crt.add_argument("epic")
    crt.add_argument("slug")
    crt.add_argument("--title", required=True)
    crt.add_argument("--covers", default="")
    crt.add_argument("--depends", default="")
    crt.add_argument("--prefix")
    crt.add_argument("--json", action="store_true")
    crf = crs.add_parser("feature")
    crf.add_argument("slug")
    crf.add_argument("--title", required=True)
    crf.add_argument("--area", default="")
    crf.add_argument("--route", default="")
    crf.add_argument("--prefix")
    crf.add_argument("--json", action="store_true")

    dl = sub.add_parser("delete", help="delete an epic/story/feature")
    dls = dl.add_subparsers(dest="what", required=True)
    dls.add_parser("epic").add_argument("name")
    dls.add_parser("story").add_argument("slug")
    dls.add_parser("feature").add_argument("slug")

    # ---- template-declared kinds: generic instance CRUD + hierarchy CRUD --
    gn = sub.add_parser("new", help="create an instance of a template-declared kind")
    gn.add_argument("kind")
    gn.add_argument("name")
    gn.add_argument("fields", nargs="*", metavar="key=value")
    gn.add_argument("--json", action="store_true")

    gf = sub.add_parser("find", help="find/list instances of a template-declared kind")
    gf.add_argument("kind")
    gf.add_argument("name", nargs="?")
    gf.add_argument("--json", action="store_true")

    gs = sub.add_parser("set", help="edit fields on an instance of a template-declared kind")
    gs.add_argument("kind")
    gs.add_argument("name")
    gs.add_argument("fields", nargs="+", metavar="key=value")
    gs.add_argument("--json", action="store_true")

    gr = sub.add_parser("remove", help="delete an instance of a template-declared kind")
    gr.add_argument("kind")
    gr.add_argument("name")
    gr.add_argument("--json", action="store_true")

    tp = sub.add_parser("template", help="define/apply OKF hierarchies (.agents/templates.yml)")
    tps = tp.add_subparsers(dest="op", required=True)
    tpn = tps.add_parser("new", help="declare a new template, optionally stubbing kinds")
    tpn.add_argument("name")
    tpn.add_argument("kinds", nargs="*")
    tpn.add_argument("--json", action="store_true")
    tpe = tps.add_parser("edit", help="patch a template's kinds via --set kind.field=value")
    tpe.add_argument("name")
    tpe.add_argument("--set", action="append", default=[], dest="assignments")
    tpf = tps.add_parser("find", help="list templates, or one template's definition")
    tpf.add_argument("name", nargs="?")
    tpf.add_argument("--json", action="store_true")
    tps.add_parser("delete").add_argument("name")
    tps.add_parser("apply", help="scaffold doc_root dirs + inject CLAUDE.md guidance") \
        .add_argument("name")

    sd = sub.add_parser("seed", help="add/remove a seed in an epic")
    sds = sd.add_subparsers(dest="op", required=True)
    sda = sds.add_parser("add")
    sda.add_argument("epic")
    sda.add_argument("id")
    sda.add_argument("--status", default=registry.DEFAULT_SEED_STATUS)
    sda.add_argument("--summary", default="")
    sda.add_argument("--surface", default="")
    sda.add_argument("--legacy-surface", default="", dest="legacy_surface")
    sda.add_argument("--backing", default="")
    sda.add_argument("--prerequisites", default="")
    sda.add_argument("--source-bullet", default="", dest="source_bullet")
    sdr = sds.add_parser("remove")
    sdr.add_argument("epic")
    sdr.add_argument("id")

    ss = sub.add_parser("set-status", help="set a story's status")
    ss.add_argument("slug")
    ss.add_argument("status")

    bl = sub.add_parser("backlog", help="manage docs/backlog.md")
    bls = bl.add_subparsers(dest="op", required=True)
    bla = bls.add_parser("add")
    bla.add_argument("id")
    bla.add_argument("text")
    bla.add_argument("--section", default="")
    bls.add_parser("prune").add_argument("id")
    bls.add_parser("list").add_argument("--json", action="store_true")

    td = sub.add_parser("todo", help="manage the epics queue (docs/epics/index.md)")
    tds = td.add_subparsers(dest="op", required=True)
    tda = tds.add_parser("add")
    tda.add_argument("name")
    tda.add_argument("--front", action="store_true")
    tds.add_parser("prune").add_argument("name")
    tds.add_parser("reorder").add_argument("names", nargs="+")
    tds.add_parser("list").add_argument("--json", action="store_true")

    # ---- edit / freeze ----------------------------------------------------
    write_parent = argparse.ArgumentParser(add_help=False)
    write_parent.add_argument("--write", action="store_true", default=argparse.SUPPRESS,
                              help="apply changes (default: dry-run)")
    e = sub.add_parser("edit", parents=[write_parent],
                       help="structured edits (dry-run unless --write)")
    esub = e.add_subparsers(dest="op", required=True)
    so = esub.add_parser("set-owner", parents=[write_parent])
    so.add_argument("gap")
    so.add_argument("story")
    rl = esub.add_parser("relink", parents=[write_parent])
    rl.add_argument("old_path")
    rl.add_argument("new_path")
    rn = esub.add_parser("rename", parents=[write_parent])
    rn.add_argument("old_slug")
    rn.add_argument("new_slug")
    sr = esub.add_parser("settle-review", parents=[write_parent],
                         help="flip a story's status from its review-resolution.json, "
                              "gated on the artifacts/assertions the verdict cites")
    sr.add_argument("slug")

    # ---- path resolution -----------------------------------------------------
    pa = sub.add_parser("path", help="resolve a slug to its canonical path")
    pas = pa.add_subparsers(dest="what", required=True)
    pa_spec = pas.add_parser("spec", help="spec dir for a story slug")
    pa_spec.add_argument("slug")
    pa_story = pas.add_parser("story", help="story.md path for an epic + slug")
    pa_story.add_argument("epic")
    pa_story.add_argument("slug")
    pa_branch = pas.add_parser("branch", help="git branch name for a slug")
    pa_branch.add_argument("slug")
    pa_branch.add_argument("--epic", action="store_true", dest="is_epic",
                           help="emit feat/<slug> instead of story/<slug>")

    fz = sub.add_parser("freeze", help="pin an approved story/seed as immutable ground truth")
    fz.add_argument("ident")
    fz.add_argument("--by", default="")
    fz.add_argument("--note", default="")
    uf = sub.add_parser("unfreeze", help="lift the freeze on a story/seed")
    uf.add_argument("ident")

    # ---- vet ---------------------------------------------------------------
    vt = sub.add_parser("vet", parents=[write_parent],
                        help="deterministic visual-fidelity check")
    vt.add_argument("screenshot", type=Path)
    vt.add_argument("--manifest", required=True, type=Path)
    vt_group = vt.add_mutually_exclusive_group(required=True)
    vt_group.add_argument("--cdp-url", dest="cdp_url")
    vt_group.add_argument("--regions", dest="regions_file", type=Path)
    vt.add_argument("--slug", required=True)
    vt.add_argument("--state", default="default")
    vt.add_argument("--iou-threshold", type=float, default=0.5, dest="iou_threshold")
    vt.add_argument("--json", action="store_true")

    ar = sub.add_parser("artifact", help="schema-checked workflow artifacts (scaffold/vet/list)")
    ars = ar.add_subparsers(dest="what", required=True)
    arsc = ars.add_parser("scaffold", help="write the kind's skeleton into the spec dir")
    arsc.add_argument("kind")
    arsc.add_argument("--spec", required=True, type=Path,
                      help="spec directory (absolute, or relative to the repo root)")
    arsc.add_argument("--force", action="store_true")
    arvt = ars.add_parser("vet", help="validate the artifact against its contract")
    arvt.add_argument("kind")
    arvt.add_argument("--spec", required=True, type=Path)
    arvt.add_argument("--json", action="store_true")
    arls = ars.add_parser("list", help="show registered artifact kinds")
    arls.add_argument("--json", action="store_true")
    return p


# ---------------------------------------------------------------------------
def _emit(rows, as_json: bool) -> int:
    if as_json:
        print(json.dumps(rows, indent=2))
    elif isinstance(rows, list):
        for r in rows:
            print(json.dumps(r) if isinstance(r, dict) else r)
        if not rows:
            print("(none)")
    else:
        print(json.dumps(rows, indent=2) if rows else "(none)")
    return 0


def _result(res, as_json: bool = False) -> int:
    if as_json:
        print(json.dumps({"ok": res.ok, "id": res.entity_id, "message": res.message}))
    else:
        print(res.message)
    return 0 if res.ok else 1


def _cmd_doctor(graph, args) -> int:
    report = doctor.run(graph, epic_filter=args.epic, check_schema=not args.no_schema)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
        return 1 if report.errors else 0
    print(f"org: {report.org}   profile: {report.profile}")
    for facts in report.epics:
        orphans = facts["orphanActiveSeeds"]
        print(f"  epic {facts['dir']}: {facts['storyCount']} stories, "
              f"{facts['activeSeedCount']} active seeds ({facts['coveredActiveSeeds']} covered)"
              + (f"  orphans: {', '.join(orphans)}" if orphans else ""))
    if report.findings:
        print()
        for fnd in sorted(report.findings, key=lambda x: (x.severity != "error", x.code)):
            mark = "✗" if fnd.severity == "error" else "⚠"
            scope = f"[{fnd.epic}] " if fnd.epic else ""
            print(f"  {mark} {fnd.code}: {scope}{fnd.message}")
    print(f"\n{report.errors} error(s), {report.warnings} warning(s)")
    return 1 if report.errors else 0


def _cmd_edit(graph, args) -> int:
    if args.op == "set-owner":
        plan = edit.set_owner(graph, args.gap, args.story)
    elif args.op == "relink":
        plan = edit.relink(graph, args.old_path, args.new_path)
    elif args.op == "settle-review":
        plan = edit.settle_review(graph, args.slug)
    else:
        plan = edit.rename(graph, args.old_slug, args.new_slug)
    print(plan.render())
    if plan.error:
        return 1
    if getattr(args, "write", False):
        plan.apply()
        print(f"\napplied: {len(plan.changes)} file(s) changed, {len(plan.moves)} move(s)")
    elif plan.changes or plan.moves:
        print("\n(dry-run — pass --write to apply)")
    return 0


def _cmd_vet(graph, args) -> int:
    outcome, plan = vet_mod.run_vet(
        graph, args.screenshot, args.manifest, args.slug,
        cdp_url=args.cdp_url, regions_file=args.regions_file,
        state=args.state, iou_threshold=args.iou_threshold,
    )
    if outcome.error:
        if args.json:
            print(json.dumps({"error": outcome.error}))
        else:
            print(f"error: {outcome.error}")
        return 1
    if args.json:
        print(outcome.report.model_dump_json(by_alias=True, indent=2))
    else:
        print(plan.render())
    if getattr(args, "write", False):
        plan.apply()
        if not args.json:
            print(f"\napplied: {len(plan.writes)} file(s) written")
    elif not args.json:
        print("\n(dry-run — pass --write to apply)")
    return 0 if outcome.report.summary.status == "clean" else 1


def _cmd_artifact(graph, args) -> int:
    if args.what == "list":
        return _emit(artifact_mod.list_kinds(), args.json)
    if args.what == "scaffold":
        outcome = artifact_mod.scaffold(args.kind, args.spec, graph.root, force=args.force)
        if outcome.error:
            print(f"error: {outcome.error}")
            return 1
        print(f"scaffolded {outcome.kind} -> {outcome.path}")
        return 0
    # vet
    outcome = artifact_mod.vet(args.kind, args.spec, graph.root)
    if args.json:
        print(json.dumps(outcome.to_dict(), indent=2))
    else:
        if outcome.error:
            print(f"error: {outcome.error}")
        else:
            print(f"{outcome.kind}: {outcome.status}")
            for problem in outcome.problems:
                print(f"  - {problem}")
    return 0 if outcome.status == "clean" else 1


def _split(csv: str) -> list[str]:
    return [p.strip() for p in csv.split(",") if p.strip()]


def _parse_fields(pairs: list[str]) -> dict | None:
    fields: dict = {}
    for pair in pairs:
        if "=" not in pair:
            return None
        key, _, raw_value = pair.partition("=")
        try:
            value = yaml.safe_load(raw_value)
        except yaml.YAMLError:
            value = raw_value
        fields[key.strip()] = value
    return fields


def _cmd_template(graph, args) -> int:
    root = graph.root
    if args.op == "new":
        return _result(templates_mod.new(root, args.name, args.kinds), getattr(args, "json", False))
    if args.op == "edit":
        return _result(templates_mod.edit(root, args.name, args.assignments))
    if args.op == "find":
        return _emit(templates_mod.find(root, args.name), args.json)
    if args.op == "delete":
        return _result(templates_mod.delete(root, args.name))
    return _result(templates_mod.apply(root, args.name))


def main(argv: list[str] | None = None) -> int:  # noqa: C901 — flat command dispatch
    args = _build_parser().parse_args(argv)
    cwd = Path(args.chdir) if args.chdir else None
    graph = load(cwd)
    c = args.command

    if c == "doctor":
        return _cmd_doctor(graph, args)
    if c == "trace":
        lines, found = trace.run(graph, args.token)
        print("\n".join(lines))
        return 0 if found else 1
    if c in ("list", "search"):
        valid_types = _TYPES + tuple(k.name for k in graph.template_kinds)
        if args.etype is not None and args.etype not in valid_types:
            print(f"error: argument --type: invalid choice: '{args.etype}' "
                  f"(choose from {', '.join(valid_types)})")
            return 2
    if c == "list":
        return _emit(query_mod.list_entities(graph, args.etype, args.epic, args.status), args.json)
    if c == "search":
        return _emit(query_mod.search(graph, args.q, args.etype, args.owner, args.tag), args.json)
    if c == "query":
        return _emit(query_mod.query(graph, args.name, args.arg), args.json)
    if c == "next-epic":
        return _emit(select.next_epic(graph), args.json)
    if c == "next-story":
        return _emit(select.next_story(graph, args.epic), args.json)
    if c == "create":
        if args.what == "epic":
            res = crud.create_epic(graph, args.name, args.title, args.prefix)
        elif args.what == "story":
            res = crud.create_story(graph, args.epic, args.slug, args.title,
                                    _split(args.covers), _split(args.depends), args.prefix)
        else:
            res = crud.create_feature(graph, args.slug, args.title, args.area, args.route, args.prefix)
        return _result(res, getattr(args, "json", False))
    if c == "delete":
        if args.what == "epic":
            return _result(crud.delete_epic(graph, args.name))
        if args.what == "story":
            return _result(crud.delete_story(graph, args.slug))
        return _result(crud.delete_feature(graph, args.slug))
    if c == "seed":
        if args.op == "add":
            meta = {"surface": args.surface, "legacySurface": args.legacy_surface,
                    "backing": args.backing, "prerequisites": args.prerequisites,
                    "sourceBullet": args.source_bullet}
            return _result(crud.add_seed(graph, args.epic, args.id, args.status, args.summary, meta))
        return _result(crud.remove_seed(graph, args.epic, args.id))
    if c == "set-status":
        return _result(crud.set_status(graph, args.slug, args.status))
    if c == "backlog":
        if args.op == "add":
            return _result(backlog_mod.add(graph, args.id, args.text, args.section))
        if args.op == "prune":
            return _result(backlog_mod.prune(graph, args.id))
        return _emit([{"id": i, "text": t} for i, t in backlog_mod.items(graph)], args.json)
    if c == "todo":
        if args.op == "add":
            return _result(todo_mod.add(graph, args.name, front=args.front))
        if args.op == "prune":
            return _result(todo_mod.prune(graph, args.name))
        if args.op == "reorder":
            return _result(todo_mod.reorder(graph, args.names))
        return _emit(todo_mod.list_epics(graph), args.json)
    if c == "path":
        if args.what == "spec":
            print(path_mod.resolve_spec(graph, args.slug))
        elif args.what == "story":
            print(path_mod.resolve_story(graph, args.epic, args.slug))
        else:
            print(path_mod.resolve_branch(args.slug, epic=args.is_epic))
        return 0
    if c == "edit":
        return _cmd_edit(graph, args)
    if c == "freeze":
        plan = freeze_mod.freeze(graph, args.ident, by=args.by, note=args.note)
        print(plan.render())
        if plan.error:
            return 1
        plan.apply()
        print(f"frozen — recorded in {(graph.root / '.agents' / 'ids.json').as_posix()}")
        return 0
    if c == "unfreeze":
        plan = freeze_mod.unfreeze(graph, args.ident)
        print(plan.render())
        if plan.error:
            return 1
        plan.apply()
        return 0
    if c == "vet":
        return _cmd_vet(graph, args)
    if c == "artifact":
        return _cmd_artifact(graph, args)
    if c == "new":
        fields = _parse_fields(args.fields)
        if fields is None:
            print("invalid field (expected key=value)")
            return 2
        return _result(crud_generic.create_instance(graph, args.kind, args.name, fields),
                       getattr(args, "json", False))
    if c == "find":
        return _emit(crud_generic.find_instance(graph, args.kind, args.name), args.json)
    if c == "set":
        fields = _parse_fields(args.fields)
        if fields is None:
            print("invalid field (expected key=value)")
            return 2
        return _result(crud_generic.edit_instance(graph, args.kind, args.name, fields),
                       getattr(args, "json", False))
    if c == "remove":
        return _result(crud_generic.delete_instance(graph, args.kind, args.name),
                       getattr(args, "json", False))
    if c == "template":
        return _cmd_template(graph, args)
    return 2


if __name__ == "__main__":
    sys.exit(main())

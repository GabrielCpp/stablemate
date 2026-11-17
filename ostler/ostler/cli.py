"""ostler command-line entry point."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import traceback
from importlib.metadata import version as _pkg_version
from pathlib import Path

import yaml

from ostler import crud, crud_generic, decisions as decisions_mod, doctor, edit, ids as ids_mod, layout as layout_mod, path as path_mod, query as query_mod, register as register_mod, register_import, registry, select, templates as templates_mod, todo as todo_mod
from ostler import checks as checks_mod
from ostler import vet as vet_mod
from ostler import artifact as artifact_mod
from ostler import qa as qa_mod
from ostler import index as index_mod
from ostler import textindex as textindex_mod
from ostler._vendor.stablemate_core import config as core_config
from ostler.environments import cli as env_cli
from ostler.book import cli as book_cli
from ostler._vendor.stablemate_core.config import ConfigError
from ostler.model import find_root, load

_TYPES = tuple(t.name for t in registry.REGISTRY if t.name != "feature") + ("seed",)


_INDEXLESS_COMMANDS = frozenset({"checks", "cache", "book"})

_DEFAULT_MAX_AGE_DAYS = index_mod.DEFAULT_MAX_AGE_S / (24 * 60 * 60)


def _add_index_controls(parser: argparse.ArgumentParser) -> None:
    """Give *parser* the two index controls, defaulting to *silence*."""
    parser.add_argument(
        "--no-index", action="store_true", dest="no_index", default=argparse.SUPPRESS,
        help="force the uncached path: read nothing from the parse index and write nothing to it",
    )
    parser.add_argument(
        "--index-dir", metavar="DIR", dest="index_dir", default=argparse.SUPPRESS,
        help=f"the parse index directory, overriding ${index_mod.INDEX_DIR_ENV}, "
             "ostler's config and the shared stablemate cache",
    )


def _install_index_controls(parser: argparse.ArgumentParser) -> None:
    """Add the index controls to every subcommand of *parser* that loads a graph."""
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for name, sub in action.choices.items():
            if name in _INDEXLESS_COMMANDS or not isinstance(sub, argparse.ArgumentParser):
                continue
            _add_index_controls(sub)
            _install_index_controls(sub)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ostler", description="Tend your documentation graph."
    )
    p.add_argument(
        "--version", action="version", version=f"ostler {_pkg_version('ostler')}"
    )
    p.add_argument("-C", "--chdir", metavar="DIR", help="operate as if run from DIR")
    handles = p.add_mutually_exclusive_group()
    handles.add_argument(
        "--handles", action="store_true", dest="handles",
        help="print ids as short handles (default for human-readable output)")
    handles.add_argument(
        "--full-ids", action="store_true", dest="full_ids",
        help="print ids in full (default for --json)")
    sub = p.add_subparsers(dest="command", required=True)
    env_cli.add_parser(sub)
    lay = sub.add_parser("layout", help="bring the epics shelf to the current layout")
    lay.add_argument("op", choices=["apply"],
                     help="apply: rename every epic and story folder to its id, record each "
                          "epic's slug and repoint the queue")

    sub.add_parser(
        "book", parents=[book_cli.build_parser(embedded=True)], add_help=False,
        help="run a service's book: check, run, explore, walk, search, explain, plan",
    )

    d = sub.add_parser("doctor", help="referential-integrity check")
    d.add_argument("--epic", help="restrict checks to one epic (name or folder)")
    d.add_argument(
        "--milestone",
        help="check one milestone, the epics it lists and their stories, against the authoring "
             "contract (folder name or id); exits 1 on any error",
    )
    d.add_argument(
        "--path", action="append", default=[], metavar="PATH",
        help="report only the findings about this file or folder (repeatable); the whole "
             "book is still checked, and the exit code counts only what is reported",
    )
    d.add_argument(
        "--json", action="store_true", help="emit the structured report as JSON"
    )
    d.add_argument(
        "--no-schema", action="store_true", help="skip JSON Schema validation"
    )
    d.add_argument(
        "--verify-index", action="store_true", dest="verify_index",
        help="run doctor with the index and without it and diff the two reports; "
             "exit non-zero on any disagreement (one command, for CI)",
    )
    ck = sub.add_parser("checks", help="the named checks `qa.verify` takes, and their signatures")
    ck.add_argument("name", nargs="?", help="one check, instead of all of them")
    ck.add_argument("--json", action="store_true")

    ls = sub.add_parser("list", help="list Concepts of a type")
    ls.add_argument(
        "--type",
        required=True,
        dest="etype",
        help=f"one of {', '.join(_TYPES)}, or a template-declared kind",
    )
    ls.add_argument("--epic")
    ls.add_argument("--status")
    ls.add_argument("--json", action="store_true")

    se = sub.add_parser("search", help="ranked full-text search over the current book and decisions")
    se.add_argument("q")
    se.add_argument("--type", dest="etype", help="a frontmatter type, such as concept or flow")
    se.add_argument("--root", help="a document root: decisions, adrs, epics, milestones, specs, register, or all")
    se.add_argument("--limit", type=int, default=10, help="most hits to return")
    se.add_argument(
        "--match", action="store_true",
        help="pass the query through as raw FTS5 syntax",
    )
    se.add_argument("--json", action="store_true")

    ix = sub.add_parser("index", help="the full-text index over every document root")
    ixs = ix.add_subparsers(dest="op", required=True)
    ixb = ixs.add_parser("build", help="build or refresh the index and report its counts")
    ixb.add_argument("--json", action="store_true")

    qy = sub.add_parser("query", help="reverse-index queries")
    qy.add_argument("name", choices=query_mod.QUERIES)
    qy.add_argument("arg")
    qy.add_argument("--json", action="store_true")

    ne = sub.add_parser("next-epic", help="the next epic with unfinished work")
    ne.add_argument("--json", action="store_true")
    ns = sub.add_parser("next-story", help="the next runnable story in an epic")
    ns.add_argument("epic")
    ns.add_argument("--json", action="store_true")

    cr = sub.add_parser("create", help="create a planning entity (allocates an id)")
    crs = cr.add_subparsers(dest="what", required=True)
    cre = crs.add_parser("epic")
    cre.add_argument("name")
    cre.add_argument("--title", required=True)
    cre.add_argument("--json", action="store_true")
    crm = crs.add_parser("milestone")
    crm.add_argument("name")
    crm.add_argument("--title", required=True)
    crm.add_argument("--source-items", default="", dest="source_items")
    crm.add_argument("--json", action="store_true")
    crb = crs.add_parser("backlog-item", help="file a record on the Register, as `backlog add`")
    _record_flags(crb)
    crt = crs.add_parser("story")
    crt.add_argument("epic")
    crt.add_argument("slug")
    crt.add_argument("--title", required=True)
    crt.add_argument("--covers", default="")
    crt.add_argument("--depends", default="",
                     help="sibling slugs that block this story; written as `- Blocked by:` "
                          "bullets in the story's own `## Dependencies` section")
    crt.add_argument("--json", action="store_true")
    crp = crs.add_parser("spec", help="create/stamp a spec doc (idempotent; safe after the write)")
    crp.add_argument("story", help="the story id (its spec folder is `ostler path spec <id>`)")
    crp.add_argument("doc", help="file name, e.g. plan.md, qa.md, review.md, executive.md")
    crp.add_argument("--title", default="", help="H1 for a newly created doc")
    crp.add_argument("--json", action="store_true")

    dl = sub.add_parser("delete", help="delete an epic or a story")
    dls = dl.add_subparsers(dest="what", required=True)
    dls.add_parser("epic").add_argument("name")
    dls.add_parser("story").add_argument("story", help="the story id")

    up = sub.add_parser("update", help="update built-in planning entity metadata")
    ups = up.add_subparsers(dest="what", required=True)
    upst = ups.add_parser("story", help="replace story title, coverage, and dependencies")
    upst.add_argument("story", help="the story id")
    upst.add_argument("--title", required=True)
    upst.add_argument("--covers", required=True)
    upst.add_argument("--depends", required=True,
                      help="the story's complete blocker list, rewritten into its "
                           "`## Dependencies` section; pass '(none)' to clear it")
    upst.add_argument("--fixtures",
                      help="the story's complete declared-QA-fixture list, rewritten into its "
                           "`## Fixtures` section; pass '(none)' to clear it. Omitted entirely, "
                           "the section is left as it stands — which is how a story created "
                           "before its QA plan exists keeps its `(none)` until the plan says "
                           "otherwise")

    gn = sub.add_parser("new", help="create an instance of a template-declared kind")
    gn.add_argument("kind")
    gn.add_argument("name")
    gn.add_argument("fields", nargs="*", metavar="key=value")
    gn.add_argument("--json", action="store_true")

    gf = sub.add_parser("find", help="find/list instances of a template-declared kind")
    gf.add_argument("kind")
    gf.add_argument("name", nargs="?")
    gf.add_argument("--json", action="store_true")

    gs = sub.add_parser(
        "set", help="edit fields on an instance of a template-declared kind"
    )
    gs.add_argument("kind")
    gs.add_argument("name")
    gs.add_argument("fields", nargs="+", metavar="key=value")
    gs.add_argument("--json", action="store_true")

    gr = sub.add_parser("remove", help="delete an instance of a template-declared kind")
    gr.add_argument("kind")
    gr.add_argument("name")
    gr.add_argument("--json", action="store_true")

    tp = sub.add_parser(
        "template", help="define/apply document hierarchies (.agents/templates.yml)"
    )
    tps = tp.add_subparsers(dest="op", required=True)
    tpn = tps.add_parser(
        "new", help="declare a new template, optionally stubbing kinds"
    )
    tpn.add_argument("name")
    tpn.add_argument("kinds", nargs="*")
    tpn.add_argument("--json", action="store_true")
    tpe = tps.add_parser(
        "edit", help="patch a template's kinds via --set kind.field=value"
    )
    tpe.add_argument("name")
    tpe.add_argument("--set", action="append", default=[], dest="assignments")
    tpf = tps.add_parser("find", help="list templates, or one template's definition")
    tpf.add_argument("name", nargs="?")
    tpf.add_argument("--json", action="store_true")
    tps.add_parser("delete").add_argument("name")
    tps.add_parser(
        "apply", help="scaffold doc_root dirs + inject CLAUDE.md guidance"
    ).add_argument("name")

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
    sda.add_argument("--layer", action="append", default=[], dest="layers",
                     help=f"repeatable; one of {', '.join(registry.SEED_LAYERS)}")
    sda.add_argument("--service", action="append", default=[], dest="services",
                     help="repeatable; the service/package this seed lands in")
    sdr = sds.add_parser("remove")
    sdr.add_argument("epic")
    sdr.add_argument("id")

    ss = sub.add_parser("set-status", help="set a story's status")
    ss.add_argument("story", help="the story id")
    ss.add_argument("status")

    cf = sub.add_parser("conflict",
                        help="record a story's acceptance-criteria conflict, or clear it")
    cf.add_argument("story", help="the story id")
    cf.add_argument("text", nargs="?", default="",
                    help="the conflict and the chain that found it; omit with --clear")
    cf.add_argument("--clear", action="store_true", help="remove the recorded conflict")
    cf.add_argument("--json", action="store_true")

    ub = sub.add_parser("unblock", help="clear give-up stamps off stories")
    ub.add_argument("story", nargs="?", default="",
                    help="one story id; omit it and pass --epic or --all for the wider scope")
    ub.add_argument("--epic", default="", help="every blocked story in this epic")
    ub.add_argument("--all", action="store_true", dest="all_stories",
                    help="every blocked story in the graph")
    ub.add_argument("--status", default=registry.DEFAULT_STORY_STATUS,
                    help=f"the status to restore (default: {registry.DEFAULT_STORY_STATUS!r})")
    ub.add_argument("--json", action="store_true")

    bl = sub.add_parser("backlog", help="the Register of proposed improvements")
    bls = bl.add_subparsers(dest="op", required=True)
    bla = bls.add_parser("add", help="file a record on the Register")
    _record_flags(bla)
    blad = bls.add_parser("adopt", help="import an old bullet list as records, once, then delete the list")
    blad.add_argument("source", help="the markdown list to import")
    blad.add_argument("--repo", required=True, help="the workspace repository the list belongs to")
    blad.add_argument("--json", action="store_true")
    blp = bls.add_parser("prune", help="close a record as done, dropped or promoted")
    blp.add_argument("id")
    blp.add_argument("--as", dest="status", choices=["done", "dropped", "promoted"], default="done")
    blp.add_argument("--reason", default="")
    blp.add_argument("--json", action="store_true")
    bll = bls.add_parser("list")
    bll.add_argument("--repo", default="")
    bll.add_argument("--status", default="")
    bll.add_argument("--json", action="store_true")

    dc = sub.add_parser("decisions", help="the operator's standing decisions")
    dcs = dc.add_subparsers(dest="op", required=True)
    dca = dcs.add_parser("add", help="file an empty decision at docs/decisions/<slug>/decision.md")
    dca.add_argument("slug", help="short kebab-case name of the decision")
    dca.add_argument("--repo", default="",
                     help="the repository the decision is about (default: the one holding the cwd)")
    dca.add_argument("--summary", required=True, help="the decision in one line")

    ml = sub.add_parser("milestone", help="manage milestone backlog ownership")
    mls = ml.add_subparsers(dest="op", required=True)
    mlss = mls.add_parser("set-source-items")
    mlss.add_argument("name")
    mlss.add_argument("ids", nargs="+")
    mle = mls.add_parser(
        "epics",
        help="set a milestone's epics in coding order, stored by id, and rewrite its `## Epics` section",
    )
    mle.add_argument("name", help="the milestone, by folder name or id")
    mle.add_argument("epics", nargs="*",
                     help="each epic by id, folder or slug; none re-resolves the list the milestone holds")

    td = sub.add_parser("todo", help="manage the epics queue (docs/epics/index.md)")
    tds = td.add_subparsers(dest="op", required=True)
    tda = tds.add_parser("add")
    tda.add_argument("name")
    tda.add_argument("--front", action="store_true")
    tds.add_parser("prune").add_argument("name")
    tds.add_parser("reorder").add_argument("names", nargs="+")
    tds.add_parser("list").add_argument("--json", action="store_true")

    write_parent = argparse.ArgumentParser(add_help=False)
    write_parent.add_argument(
        "--write",
        action="store_true",
        default=argparse.SUPPRESS,
        help="apply changes (default: dry-run)",
    )
    e = sub.add_parser(
        "edit", parents=[write_parent], help="structured edits (dry-run unless --write)"
    )
    esub = e.add_subparsers(dest="op", required=True)
    rl = esub.add_parser("relink", parents=[write_parent])
    rl.add_argument("old_path")
    rl.add_argument("new_path")
    rn = esub.add_parser("rename", parents=[write_parent])
    rn.add_argument("old_slug")
    rn.add_argument("new_slug")
    sr = esub.add_parser(
        "settle-review",
        parents=[write_parent],
        help="flip a story's status from its review-resolution.json, "
        "gated on the artifacts/assertions the verdict cites",
    )
    sr.add_argument("story", help="the story id")
    pa = sub.add_parser("path", help="resolve a story id or epic name to its canonical path")
    pas = pa.add_subparsers(dest="what", required=True)
    pa_spec = pas.add_parser("spec", help="spec dir for a story id")
    pa_spec.add_argument("story", help="the story id")
    pa_epic = pas.add_parser("epic", help="directory for an epic (number or bare slug)")
    pa_epic.add_argument("epic")
    pa_story = pas.add_parser("story", help="story.md path for a story id")
    pa_story.add_argument("story", help="the story id")
    pa_branch = pas.add_parser("branch", help="git branch name for a story id (or an epic)")
    pa_branch.add_argument("ref", help="the story id, or the epic name with --epic")
    pa_branch.add_argument(
        "--epic",
        action="store_true",
        dest="is_epic",
        help="emit feat/<slug> instead of the bare <slug>",
    )

    vt = sub.add_parser(
        "vet", parents=[write_parent], help="deterministic visual-fidelity check"
    )
    vt.add_argument("screenshot", type=Path)
    vt.add_argument("--manifest", required=True, type=Path)
    vt_group = vt.add_mutually_exclusive_group(required=True)
    vt_group.add_argument("--cdp-url", dest="cdp_url")
    vt_group.add_argument("--regions", dest="regions_file", type=Path)
    vt.add_argument("--story", required=True, help="the story id")
    vt.add_argument("--state", default="default")
    vt.add_argument("--iou-threshold", type=float, default=0.5, dest="iou_threshold")
    vt.add_argument("--json", action="store_true")

    ar = sub.add_parser(
        "artifact", help="schema-checked workflow artifacts (scaffold/vet/list)"
    )
    ars = ar.add_subparsers(dest="what", required=True)
    arsc = ars.add_parser(
        "scaffold", help="write the kind's skeleton into the spec dir"
    )
    arsc.add_argument("kind")
    arsc.add_argument(
        "--spec",
        required=True,
        type=Path,
        help="spec directory (absolute, or relative to the specs root or the repo root)",
    )
    arsc.add_argument("--force", action="store_true")
    arvt = ars.add_parser("vet", help="validate the artifact against its contract")
    arvt.add_argument("kind")
    arvt.add_argument("--spec", required=True, type=Path)
    arvt.add_argument("--json", action="store_true")
    arls = ars.add_parser("list", help="show registered artifact kinds")
    arls.add_argument("--json", action="store_true")

    qa = sub.add_parser(
        "qa", help="deterministic QA run bookkeeping (start/step/assert/stop/run/…)"
    )
    qas = qa.add_subparsers(dest="op", required=True)

    qa_start = qas.add_parser("start", help="open a QA session and start daemons")
    qa_start.add_argument("run_id")
    qa_start.add_argument("--story", required=True)
    qa_start.add_argument(
        "--spec",
        required=True,
        type=Path,
        help="spec directory (absolute, or relative to the specs root or the repo root)",
    )
    qa_start.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="environment variable for the session (repeatable)",
    )
    qa_start.add_argument(
        "--daemon",
        action="append",
        default=[],
        metavar="NAME:ARGV",
        dest="daemons",
        help="background daemon to start (repeatable); ARGV is tokenised, not run through "
        "a shell — append :READY_URL to poll before advancing",
    )

    qa_step = qas.add_parser(
        "step", help="execute a command and record it in the run log"
    )
    qa_step.add_argument("--id", required=True)
    qa_step.add_argument("--label", required=True)
    qa_step.add_argument(
        "--mechanism", required=True, choices=["live", "fixture"]
    )
    qa_step.add_argument("--cmd", required=True)
    qa_step.add_argument("--timeout", type=float, default=60)
    qa_step.add_argument("--spec", required=True, type=Path)
    qa_step.add_argument(
        "--capture",
        action="append",
        default=[],
        metavar="KEY=$.path",
        help="extract value from step stdout JSON (repeatable)",
    )
    qa_step.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help="write step stdout to this path as a sidecar file",
    )
    qa_step.add_argument(
        "--allow-fail",
        action="store_true",
        dest="allow_fail",
        help="do not exit non-zero if the step command fails",
    )

    qa_assert = qas.add_parser(
        "assert", help="execute a named check and record PASS/FAIL"
    )
    qa_assert.add_argument("--id", required=True)
    qa_assert.add_argument("--label", required=True)
    qa_assert.add_argument(
        "--check",
        required=True,
        choices=[
            "cloudwatch_filter",
            "event_present",
            "field_equal",
            "http_status",
            "no_duplicate",
        ],
    )
    qa_assert.add_argument("--spec", required=True, type=Path)
    qa_assert.add_argument(
        "param",
        nargs="*",
        metavar="KEY=VALUE",
        help="check-specific parameters (KEY=VALUE pairs)",
    )

    qa_stop = qas.add_parser("stop", help="kill daemons and write session_stop summary")
    qa_stop.add_argument("--spec", required=True, type=Path)

    qa_report = qas.add_parser(
        "report",
        help="render the run per acceptance criterion and obligation — what was done, "
             "what was asserted, what was observed, what backs it — and rewrite "
             "<spec>/qa-report.md",
    )
    qa_report.add_argument("--spec", default=None, type=Path)
    qa_report.add_argument(
        "--out-dir",
        default=None,
        dest="out_dir",
        metavar="LABEL",
        help="render the dry run at <spec>/qa/LABEL/ (to <spec>/qa/LABEL/report.md) "
             "instead of the scored one; must be the label that run was given",
    )
    qa_report.add_argument(
        "--ledger",
        action="store_true",
        help="print the flat, time-ordered STEP/ASSERT listing of the raw ledger instead "
             "and write nothing",
    )

    qa_frames = qas.add_parser(
        "frames",
        help="write the frames of the run's recording around a step (or a position) to "
             "<spec>/qa/frames/<step>/, one PNG per 1/fps seconds, with an index.md",
    )
    qa_frames.add_argument("--spec", default=None, type=Path)
    which = qa_frames.add_mutually_exclusive_group(required=True)
    which.add_argument(
        "--step", default=None,
        help="a step id from qa-report.md, or a unique fragment of its label",
    )
    which.add_argument(
        "--at", default=None, type=float, metavar="SECONDS",
        help="a position in the recording instead of a step",
    )
    qa_frames.add_argument(
        "--target", default=None,
        help="which recording --at refers to, when several targets were recorded",
    )
    qa_frames.add_argument(
        "--around", default=1.0, type=float, metavar="SECONDS",
        help="how far before the step starts and after it ends to reach (default 1.0)",
    )
    qa_frames.add_argument(
        "--fps", default=10.0, type=float,
        help="frames per second of recording to write (default 10)",
    )
    qa_frames.add_argument(
        "--out-dir", default=None, dest="out_dir", metavar="LABEL",
        help="read the dry run at <spec>/qa/LABEL/ instead of the scored one",
    )

    qa_replay = qas.add_parser(
        "replay", help="emit a replay shell script from the run log"
    )
    qa_replay.add_argument("--spec", required=True, type=Path)

    qa_lint = qas.add_parser(
        "lint", help="statically lint a qa_plan.py's AST without importing or executing it"
    )
    qa_lint.add_argument("plan_file", type=Path)
    qa_lint.add_argument("--json", action="store_true")

    qa_validate = qas.add_parser(
        "validate", help="validate a qa_plan.py without executing"
    )
    qa_validate.add_argument("plan_file", type=Path)
    qa_validate.add_argument("--spec", default=None, type=Path)
    qa_validate.add_argument("--json", action="store_true")

    qa_run = qas.add_parser("run", help="execute a qa_plan.py in batch mode")
    qa_run.add_argument("plan_file", type=Path)
    qa_run.add_argument("--spec", default=None, type=Path)
    qa_run.add_argument("--stop-on-fail", action="store_true", dest="stop_on_fail")
    qa_run.add_argument(
        "--scenario",
        action="append",
        default=None,
        dest="scenarios",
        metavar="ID",
        help="run only this scenario (repeatable); background daemons still start",
    )
    qa_run.add_argument(
        "--out-dir",
        default=None,
        dest="out_dir",
        metavar="LABEL",
        help="make this a dry run into <spec>/qa/LABEL/, writing no qa-evidence.json; "
             "LABEL is one name, not a path. Omit for the scored ledger",
    )
    qa_run.add_argument("--json", action="store_true")

    qa_tools = qas.add_parser("tools", help="inspect this repo's opted-in QA tools")
    qa_tools_ops = qa_tools.add_subparsers(dest="tools_op", required=True)
    qa_tools_list = qa_tools_ops.add_parser("list", help="list opted-in tools and whether they resolve")
    qa_tools_list.add_argument("--json", action="store_true")

    qa_clean = qas.add_parser(
        "clean",
        help="list (and with --yes, delete) the legacy qa-* scratch directories the old "
             "sibling layout left beside the spec",
    )
    qa_clean.add_argument(
        "--spec", required=True, type=Path,
        help="a spec directory, or any directory above one — it is searched recursively",
    )
    qa_clean.add_argument(
        "--yes", action="store_true", dest="apply",
        help="actually delete them; without it nothing is removed",
    )
    qa_clean.add_argument("--json", action="store_true")

    ca = sub.add_parser("cache", help="the persistent parse index: evict what it holds")
    cas = ca.add_subparsers(dest="op", required=True)
    cac = cas.add_parser(
        "clean",
        help="delete aged-out index entries (--all: every entry)",
    )
    cac.add_argument(
        "--index-dir", metavar="DIR", dest="index_dir", default=argparse.SUPPRESS,
        help=f"the index directory to clean, overriding ${index_mod.INDEX_DIR_ENV}, "
             "ostler's config and the shared stablemate cache",
    )
    cac.add_argument(
        "--all", action="store_true", dest="everything",
        help="remove every entry, not only the aged-out ones",
    )
    cac.add_argument(
        "--max-age-days", type=float, default=_DEFAULT_MAX_AGE_DAYS, dest="max_age_days",
        metavar="N", help="how long an entry may go unwritten before it ages out "
                          f"(default: {_DEFAULT_MAX_AGE_DAYS:g})",
    )
    cac.add_argument("--json", action="store_true")

    p.set_defaults(no_index=False, index_dir=None)
    _add_index_controls(p)
    _install_index_controls(p)
    return p


_HANDLES: dict[str, str] = {}
_HANDLES_ON = False


def _use_handles(graph, args) -> None:
    """Decide, once per run, whether ids print short."""
    global _HANDLES, _HANDLES_ON
    _HANDLES_ON = args.handles or (not args.full_ids and not getattr(args, "json", False))
    _HANDLES = ids_mod.table(ids_mod.known(graph)) if _HANDLES_ON else {}


def _out(value="") -> None:
    """Print, abbreviating any full id in what is printed when this run renders handles."""
    print(ids_mod.shorten(value, _HANDLES) if _HANDLES_ON else value)


def _emit(rows, as_json: bool) -> int:
    if as_json:
        _out(json.dumps(rows, indent=2))
    elif isinstance(rows, list):
        for r in rows:
            _out(json.dumps(r) if isinstance(r, dict) else r)
        if not rows:
            _out("(none)")
    else:
        _out(json.dumps(rows, indent=2) if rows else "(none)")
    return 0


def _record_flags(parser: argparse.ArgumentParser) -> None:
    """The flags a person files a record with, shared by ``backlog add`` and ``create backlog-item``."""
    parser.add_argument("summary")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--area", required=True)
    parser.add_argument("--pattern", default="untriaged")
    parser.add_argument("--symbol", action="append", default=[], dest="symbols")
    parser.add_argument("--id", default="", dest="record_id")
    parser.add_argument("--body", default="")
    parser.add_argument("--json", action="store_true")


def _file_person(graph, args) -> register_mod.Filing:
    """File the record the parsed ``_record_flags`` describe."""
    return register_mod.file_person(
        graph, summary=args.summary, repo=args.repo, area=args.area, pattern=args.pattern,
        symbols=args.symbols, body=args.body, record_id=args.record_id,
    )


def _prune_record(graph, args) -> int:
    """Close the record ``backlog prune`` names; ``dropped`` and ``promoted`` must say why."""
    if args.status != "done" and not args.reason.strip():
        return _result(crud.Result(False, f"--as {args.status} requires --reason"), args.json)
    return _result(register_mod.close(graph, args.id, args.status, args.reason), args.json)


def _adopt_list(graph, args) -> int:
    """Import an old bullet list: one listing line per record and a summary line, or the refusal."""
    outcome = register_import.import_list(graph, Path(args.source).expanduser().resolve(), args.repo)
    if not outcome.ok:
        _out(outcome.message)
        return 1
    if args.json:
        return _emit([r.model_dump() for r in outcome.records], True)
    _out("\n".join([*register_mod.listing(outcome.records), outcome.message]))
    return 0


def _result(res, as_json: bool = False) -> int:
    if _HANDLES_ON and res.entity_id and res.entity_id not in _HANDLES:
        _HANDLES.update(ids_mod.table([*_HANDLES, res.entity_id]))
    if as_json:
        _out(json.dumps({"ok": res.ok, "id": res.entity_id,
                          "name": res.entity_name, "message": res.message}))
    else:
        _out(res.message)
    return 0 if res.ok else 1


def _book_file(graph, typed: str) -> Path | None:
    """The file or folder *typed* names, an absolute path as given and a relative one under the repo root as doctor prints it, or None when no doc root holds it."""
    candidate = Path(typed) if Path(typed).is_absolute() else graph.root / typed
    candidate = candidate.resolve()
    if not candidate.exists():
        return None
    if not any(candidate.is_relative_to(r.resolve()) for r in graph.doc_roots.values()):
        return None
    return candidate


def _cmd_doctor(graph, args, store: index_mod.IndexStore) -> int:
    scope = [_book_file(graph, p) for p in args.path]
    outside = [p for p, file in zip(args.path, scope, strict=True) if file is None]
    if outside:
        roots = ", ".join(sorted(path_mod.display_path(graph.root, r)
                                 for r in graph.doc_roots.values()))
        print(f"ostler doctor: --path {', '.join(outside)} is not a file of this book "
              f"(its doc roots: {roots})", file=sys.stderr)
        return 2
    wanted = [file for file in scope if file is not None]
    report = doctor.run(graph, epic_filter=args.epic, check_schema=not args.no_schema,
                        milestone_filter=args.milestone)
    if wanted:
        report = doctor.scope_to_paths(
            report, graph.root, wanted,
            {epic.name: epic.epic_md for epic in graph.epics if epic.epic_md is not None})
    if args.json:
        payload = report.as_dict()
        payload["index"] = store.stats()
        _out(json.dumps(payload, indent=2))
        return 1 if report.errors else 0
    if args.path:
        _out(f"{report.errors} error(s), {report.warnings} warning(s) in "
             f"{', '.join(path_mod.display_path(graph.root, file) for file in wanted)}")
    else:
        _out(f"org: {report.org}   profile: {report.profile}")
    for facts in [] if args.path else report.epics:
        orphans = facts["orphanActiveSeeds"]
        _out(
            f"  epic {facts['dir']}: {facts['storyCount']} stories, "
            f"{facts['activeSeedCount']} active seeds ({facts['coveredActiveSeeds']} covered)"
            + (f"  orphans: {', '.join(orphans)}" if orphans else "")
        )
    if report.findings:
        _out()
        for fnd in sorted(
            report.findings, key=lambda x: (x.severity != "error", x.code)
        ):
            mark = "✗" if fnd.severity == "error" else "⚠"
            scope = f"[{fnd.epic}] " if fnd.epic else ""
            _out(f"  {mark} {fnd.code}: {scope}{fnd.message}")
    _out(f"\n{report.errors} error(s), {report.warnings} warning(s)")
    return 1 if report.errors else 0


def _cmd_verify_index(cwd: Path | None, args) -> int:
    """Run doctor both ways and diff the two reports — the correctness half of the gate."""
    root = find_root(cwd if cwd is not None else Path.cwd())
    reports: list[doctor.Report] = []
    for enabled in (True, False):
        with index_mod.session(root, directory=args.index_dir, enabled=enabled):
            reports.append(
                doctor.run(
                    load(cwd), epic_filter=args.epic, check_schema=not args.no_schema
                )
            )
    diff = doctor.diff_reports(reports[0], reports[1])
    if not diff:
        _out(
            f"verify-index: the indexed and uncached reports agree "
            f"({reports[0].errors} error(s), {reports[0].warnings} warning(s))"
        )
        return 0
    _out("verify-index: the indexed and uncached reports disagree")
    for line in diff:
        _out(line)
    return 1


def _cmd_cache(args) -> int:
    """``ostler cache clean`` — the eviction `IndexStore.prune` runs automatically."""
    directory = index_mod.index_dir(args.index_dir)
    removed = index_mod.clean(
        directory,
        everything=args.everything,
        max_age_s=args.max_age_days * 24 * 60 * 60,
    )
    if args.json:
        _out(json.dumps({"dir": str(directory), "removed": removed}, indent=2))
    else:
        scope = "entries" if args.everything else "aged-out entries"
        _out(f"removed {removed} {scope} from {directory}")
    return 0


def _cmd_search(graph, args) -> int:
    try:
        hits = query_mod.search(
            graph, args.q, args.etype, root=args.root, limit=args.limit, raw=args.match
        )
    except ValueError as exc:
        _out(f"error: {exc}")
        return 2
    if args.json:
        _out(json.dumps(hits, indent=2))
        return 0
    for hit in hits:
        where = f"{hit['node']}#{hit['anchor']}" if hit["anchor"] else hit["node"]
        heading = f" — {hit['heading']}" if hit["heading"] else ""
        _out(f"{hit['score']:.3f}  {hit['root']}/{hit['type']}  {where}{heading}")
        _out(f"        {hit['snippet']}")
    if not hits:
        _out("(none)")
    return 0


def _cmd_index(graph, args) -> int:
    report = textindex_mod.build(graph)
    if args.json:
        _out(json.dumps(report.as_dict(), indent=2))
    else:
        _out(
            f"indexed {report.sections} sections from {report.files} files "
            f"({report.indexed} refreshed, {report.removed} removed) in {report.dir}"
        )
    return 0


def _cmd_edit(graph, args) -> int:
    if args.op == "relink":
        plan = edit.relink(graph, args.old_path, args.new_path)
    elif args.op == "settle-review":
        plan = edit.settle_review(graph, args.story)
    else:
        plan = edit.rename(graph, args.old_slug, args.new_slug)
    _out(plan.render())
    if plan.error:
        return 1
    if getattr(args, "write", False):
        plan.apply()
        _out(
            f"\napplied: {len(plan.changes)} file(s) changed, {len(plan.moves)} move(s)"
        )
    elif plan.changes or plan.moves:
        _out("\n(dry-run — pass --write to apply)")
    return 0


def _cmd_vet(graph, args) -> int:
    try:
        outcome, plan = vet_mod.run_vet(
            graph,
            args.screenshot,
            args.manifest,
            args.story,
            cdp_url=args.cdp_url,
            regions_file=args.regions_file,
            state=args.state,
            iou_threshold=args.iou_threshold,
        )
    except ValueError as exc:
        _out(f"error: {exc}")
        return 1
    report = outcome.report
    if outcome.error or report is None:
        message = outcome.error or "vet produced no report"
        if args.json:
            _out(json.dumps({"error": message}))
        else:
            _out(f"error: {message}")
        return 1
    if args.json:
        _out(report.model_dump_json(by_alias=True, indent=2))
    else:
        _out(plan.render())
    if getattr(args, "write", False):
        plan.apply()
        if not args.json:
            _out(f"\napplied: {len(plan.writes)} file(s) written")
    elif not args.json:
        _out("\n(dry-run — pass --write to apply)")
    return 0 if report.summary.status == "clean" else 1


def _cmd_artifact(graph, args) -> int:
    if args.what == "list":
        return _emit(artifact_mod.list_kinds(), args.json)
    if args.what == "scaffold":
        outcome = artifact_mod.scaffold(
            args.kind, args.spec, graph.root, force=args.force
        )
        if outcome.error:
            _out(f"error: {outcome.error}")
            return 1
        _out(f"scaffolded {outcome.kind} -> {outcome.path}")
        return 0
    outcome = artifact_mod.vet(args.kind, args.spec, graph.root)
    if args.json:
        _out(json.dumps(outcome.to_dict(), indent=2))
    else:
        if outcome.error:
            _out(f"error: {outcome.error}")
        else:
            _out(f"{outcome.kind}: {outcome.status}")
            for problem in outcome.problems:
                _out(f"  - {problem}")
    return 0 if outcome.status == "clean" else 1


def _cmd_qa(graph, args) -> int:  # noqa: C901 — flat QA subcommand dispatch
    root = graph.root
    op = args.op

    def _resolve_spec(spec_arg: Path | None) -> Path:
        if spec_arg is None:
            _out("error: --spec is required")
            sys.exit(2)
        return path_mod.resolve_spec_arg(root, spec_arg)

    def _resolve_out(out_arg: Path | None) -> Path | None:
        """A path-valued option against the same root `--spec` is read against."""
        if out_arg is None:
            return None
        return out_arg if out_arg.is_absolute() else root / out_arg

    if op == "start":
        spec_dir = _resolve_spec(args.spec)
        env = dict(kv.split("=", 1) for kv in args.env if "=" in kv)
        daemons: list[qa_mod.DaemonSpec] = []
        for raw in args.daemons:
            parts = raw.split(":", 2)
            name = parts[0]
            if len(parts) == 2:
                daemons.append((name, shlex.split(parts[1]), None))
            elif len(parts) == 3:
                daemons.append((name, shlex.split(parts[1]), parts[2]))
            else:
                _out(
                    f"error: invalid --daemon format: {raw!r} (expected NAME:ARGV[:READY_URL])"
                )
                return 2
        result = qa_mod.cmd_start(
            args.run_id, args.story, spec_dir, env=env, daemons=daemons
        )
        _out(result.message)
        return 0 if result.ok else 1

    if op == "step":
        spec_dir = _resolve_spec(args.spec)
        captures: list[tuple[str, str]] = []
        for raw in args.capture:
            if "=" not in raw:
                _out(f"error: --capture must be KEY=$.path, got {raw!r}")
                return 2
            k, _, v = raw.partition("=")
            captures.append((k.strip(), v.strip()))
        result = qa_mod.cmd_step(
            spec_dir,
            args.id,
            args.label,
            args.mechanism,
            args.cmd,
            captures=captures,
            out_path=args.out,
            allow_fail=args.allow_fail,
            timeout=args.timeout,
        )
        _out(result.message)
        return 0 if result.ok else 1

    if op == "assert":
        spec_dir = _resolve_spec(args.spec)
        params: dict = {}
        for raw in args.param:
            if "=" not in raw:
                _out(f"error: assert params must be KEY=VALUE, got {raw!r}")
                return 2
            k, _, v = raw.partition("=")
            params[k.strip()] = v.strip()
        result = qa_mod.cmd_assert(
            spec_dir, args.id, args.label, args.check, params, root=root
        )
        _out(result.message)
        return 0 if result.ok else 1

    if op == "stop":
        spec_dir = _resolve_spec(args.spec)
        result = qa_mod.cmd_stop(spec_dir)
        _out(result.message)
        return 0 if result.ok else 1

    if op == "report":
        spec_dir = _resolve_spec(args.spec)
        result = qa_mod.cmd_report(spec_dir, label=args.out_dir, ledger=args.ledger)
        if not result.ok:
            _out(f"error: {result.message}")
        return 0 if result.ok else 1

    if op == "frames":
        spec_dir = _resolve_spec(args.spec)
        result = qa_mod.cmd_frames(
            spec_dir,
            step=args.step,
            at=args.at,
            target=args.target,
            around=args.around,
            fps=args.fps,
            label=args.out_dir,
        )
        if not result.ok:
            _out(f"error: {result.message}")
        return 0 if result.ok else 1

    if op == "replay":
        spec_dir = _resolve_spec(args.spec)
        result = qa_mod.cmd_replay(spec_dir)
        return 0 if result.ok else 1

    if op == "lint":
        result = qa_mod.cmd_lint(args.plan_file, root=root)
        if args.json:
            _out(json.dumps(result.data, indent=2))
        else:
            _out(result.message)
        return 0 if result.ok else 1

    if op == "validate":
        spec_dir = args.spec
        if spec_dir is not None and not spec_dir.is_absolute():
            spec_dir = root / spec_dir
        result = qa_mod.cmd_validate(args.plan_file, spec_dir, root=root)
        if args.json:
            _out(json.dumps(result.data, indent=2))
        else:
            _out(result.message)
        return 0 if result.ok else 1

    if op == "run":
        spec_dir = args.spec
        if spec_dir is not None and not spec_dir.is_absolute():
            spec_dir = root / spec_dir
        result = qa_mod.cmd_run(
            args.plan_file,
            spec_dir,
            stop_on_fail=args.stop_on_fail,
            only=args.scenarios,
            label=args.out_dir,
            root=root,
        )
        if getattr(args, "json", False):
            _out(json.dumps(result.data, indent=2))
        else:
            _out(result.message)
        return 0 if result.ok else 1

    if op == "tools":
        result = qa_mod.tools.cmd_catalog(root)
        if args.json:
            _out(json.dumps(result.data, indent=2))
        else:
            for row in result.data["tools"]:
                mark = "ok" if row["available"] else "MISSING"
                _out(f"{row['name']} ({row['command']}) [{mark}] - {row['description']}")
            for error in result.data["errors"]:
                _out(f"error: {error}")
        return 0 if result.ok else 1

    if op == "clean":
        result = qa_mod.cmd_clean(_resolve_spec(args.spec), apply=args.apply)
        if args.json:
            _out(json.dumps(result.data, indent=2))
        else:
            _out(result.message)
        return 0 if result.ok else 1

    return 2


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
        return _result(
            templates_mod.new(root, args.name, args.kinds), getattr(args, "json", False)
        )
    if args.op == "edit":
        return _result(templates_mod.edit(root, args.name, args.assignments))
    if args.op == "find":
        return _emit(templates_mod.find(root, args.name), args.json)
    if args.op == "delete":
        return _result(templates_mod.delete(root, args.name))
    return _result(templates_mod.apply(root, args.name))


def _cmd_checks(args: argparse.Namespace) -> int:
    """Print the named checks `qa.verify` takes, so a signature can be read rather than guessed."""
    specs = list(checks_mod.CHECKS)
    if args.name:
        spec = checks_mod.CHECK_BY_NAME.get(args.name)
        if spec is None:
            known = ", ".join(sorted(checks_mod.CHECK_BY_NAME))
            print(f"ostler checks: `{args.name}` is not a check — the vocabulary is: {known}",
                  file=sys.stderr)
            return 1
        specs = [spec]
    if args.json:
        _out(json.dumps([
            {
                "name": s.name,
                "signature": s.signature(),
                "params": [{"name": p.name, "type": p.type, "required": p.required,
                            "path": p.path, "locator": p.locator}
                           for p in s.params if not p.hidden],
                "excludes": s.excludes,
                "plan_reads": s.plan_reads,
                "cli_reads": s.cli_reads,
            }
            for s in specs
        ], indent=2))
        return 0
    _out(checks_mod.describe(tuple(specs)))
    return 0


def _env_root(start: Path) -> Path:
    """The root `ostler env` reads its stacks under: the book root in a workspace, else the docs root."""
    return env_cli.commands.env_root(start)


INTERNAL_ERROR = 70


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        if os.environ.get("OSTLER_DEBUG"):
            raise
        print(_internal_error(argv, exc), file=sys.stderr)
        return INTERNAL_ERROR


def _internal_error(argv: list[str] | None, exc: Exception) -> str:
    """One line naming the command, where ostler failed and why: an ostler defect, never the caller's input."""
    given = sys.argv[1:] if argv is None else argv
    at = 0
    while at < len(given) and given[at].startswith("-"):
        at += 2 if given[at] in ("-C", "--chdir", "--index-dir") else 1
    command = given[at] if at < len(given) else ""
    frame = traceback.extract_tb(exc.__traceback__)[-1]
    where = f"{Path(frame.filename).name}:{frame.lineno}"
    return (f"ostler {command}: internal error at {where}: "
            f"{type(exc).__name__}: {exc} (an ostler defect; OSTLER_DEBUG=1 prints the stack)")


def _book_position(argv: list[str]) -> int | None:
    """Where the `book` command sits among the global options, so everything after it is the runtime's."""
    at = 0
    while at < len(argv):
        word = argv[at]
        if word in ("-C", "--chdir", "--index-dir"):
            at += 2
        elif word.startswith("-"):
            at += 1
        else:
            return at if word == "book" else None
    return None


def _cmd_book(cwd: Path | None, book_args: list[str]) -> int:
    """Hand the arguments to the book runtime from the directory that holds `services/`."""
    if cwd is not None:
        os.chdir(cwd)
    return book_cli.main(book_args)


def _cmd_layout() -> int:
    """Rename the shelf's epic and story folders to their ids; exit 1 when any could not move."""
    done, refused = layout_mod.apply(core_config.resolve_artifacts_dir())
    for line in done:
        _out(line)
    for line in refused:
        print(f"ostler layout: {line}", file=sys.stderr)
    if not done and not refused:
        _out("every epic and story folder is already named by its id")
    return 1 if refused else 0


def _main(argv: list[str] | None) -> int:
    given = sys.argv[1:] if argv is None else argv
    at = _book_position(given)
    book_args = given[at + 1:] if at is not None else []
    args = _build_parser().parse_args(given[:at + 1] if at is not None else given)
    cwd = Path(args.chdir) if args.chdir else None
    if args.command == "checks":
        return _cmd_checks(args)
    if args.command == "cache":
        return _cmd_cache(args)
    if args.command == "book":
        return _cmd_book(cwd, book_args)
    if args.command == "env":
        return env_cli.run(args, _env_root(cwd if cwd is not None else Path.cwd()))
    if args.command == "layout":
        return _cmd_layout()
    if args.command == "doctor" and args.verify_index:
        return _cmd_verify_index(cwd, args)
    with index_mod.session(
        find_root(cwd if cwd is not None else Path.cwd()),
        directory=args.index_dir,
        enabled=not args.no_index,
    ) as store:
        try:
            graph = load(cwd)
        except layout_mod.LayoutMoveRequired as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        _use_handles(graph, args)
        return _dispatch(graph, args, store)


def _dispatch(graph, args, store: index_mod.IndexStore) -> int:  # noqa: C901 — flat command dispatch
    c = args.command

    if c == "doctor":
        return _cmd_doctor(graph, args, store)
    if c == "list":
        valid_types = _TYPES + tuple(k.name for k in graph.template_kinds)
        if args.etype is not None and args.etype not in valid_types:
            _out(
                f"error: argument --type: invalid choice: '{args.etype}' "
                f"(choose from {', '.join(valid_types)})"
            )
            return 2
    if c == "list":
        return _emit(
            query_mod.list_entities(graph, str(args.etype), args.epic, args.status),
            args.json,
        )
    if c == "search":
        return _cmd_search(graph, args)
    if c == "index":
        return _cmd_index(graph, args)
    if c == "query":
        return _emit(
            query_mod.query(graph, args.name, ids_mod.resolve(graph, args.arg)),
            args.json,
        )
    if c == "next-epic":
        return _emit(select.next_epic(graph), args.json)
    if c == "next-story":
        found = select.next_story_report(graph, args.epic)
        if found["state"] == "no-epic":
            print(f"ostler next-story: {found['detail']}", file=sys.stderr)
            return 1
        return _emit(found["story"], args.json)
    if c == "create":
        if args.what == "epic":
            res = crud.create_epic(graph, args.name, args.title)
        elif args.what == "milestone":
            res = crud.create_milestone(
                graph,
                args.name,
                args.title,
                [ids_mod.resolve(graph, item) for item in _split(args.source_items)],
            )
        elif args.what == "backlog-item":
            res = register_mod.filing_result(_file_person(graph, args))
        elif args.what == "story":
            res = crud.create_story(
                graph,
                args.epic,
                args.slug,
                args.title,
                [ids_mod.resolve(graph, s) for s in _split(args.covers)],
                _split(args.depends),
            )
        else:
            try:
                key = Path(path_mod.resolve_spec(graph, args.story)).name
            except ValueError as exc:
                return _result(crud.Result(False, str(exc)), getattr(args, "json", False))
            res = crud.create_spec(graph.doc_roots["specs"], key, args.doc, args.title)
        return _result(res, getattr(args, "json", False))
    if c == "delete":
        if args.what == "epic":
            return _result(crud.delete_epic(graph, args.name))
        return _result(crud.delete_story(graph, args.story))
    if c == "update":
        return _result(
            crud.update_story(
                graph,
                args.story,
                title=args.title,
                covers=[ids_mod.resolve(graph, seed) for seed in _split(args.covers)],
                depends=_split(args.depends),
                fixtures=_split(args.fixtures) if args.fixtures is not None else None,
            )
        )
    if c == "seed":
        if args.op == "add":
            meta = {
                "surface": args.surface,
                "legacySurface": args.legacy_surface,
                "backing": args.backing,
                "prerequisites": args.prerequisites,
                "layers": args.layers,
                "services": args.services,
            }
            return _result(
                crud.add_seed(
                    graph, args.epic, ids_mod.resolve(graph, args.id),
                    args.status, args.summary, meta
                )
            )
        return _result(crud.remove_seed(graph, args.epic, ids_mod.resolve(graph, args.id)))
    if c == "set-status":
        return _result(crud.set_status(graph, args.story, args.status))
    if c == "conflict":
        if bool(args.text) == bool(args.clear):
            return _result(crud.Result(
                False, "pass the conflict text, or --clear — one of the two"), args.json)
        return _result(crud.set_conflict(graph, args.story, "" if args.clear else args.text),
                       args.json)
    if c == "unblock":
        if not (args.story or args.epic or args.all_stories):
            return _result(crud.Result(False, "name a story, pass --epic, or pass --all"), args.json)
        if args.all_stories and (args.story or args.epic):
            return _result(crud.Result(False, "--all takes no story or --epic"), args.json)
        return _result(
            crud.unblock(graph, story=args.story, epic=args.epic, status=args.status),
            args.json,
        )
    if c == "backlog":
        if args.op == "add":
            return _result(register_mod.filing_result(_file_person(graph, args)), args.json)
        if args.op == "adopt":
            return _adopt_list(graph, args)
        if args.op == "prune":
            return _prune_record(graph, args)
        shown = [
            r for r in register_mod.records(graph).records
            if (not args.repo or r.repo == args.repo) and (not args.status or r.status == args.status)
        ]
        if args.json:
            return _emit([r.model_dump() for r in shown], True)
        return _emit(register_mod.listing(shown), False)
    if c == "decisions":
        start = Path(args.chdir) if args.chdir else Path.cwd()
        return _result(decisions_mod.add(
            graph, args.slug, repo=args.repo or decisions_mod.default_repo(start),
            summary=args.summary,
        ))
    if c == "milestone" and args.op == "epics":
        return _result(crud.set_milestone_epics(graph, args.name, args.epics or None))
    if c == "milestone":
        return _result(crud.set_milestone_source_items(
            graph,
            args.name,
            [ids_mod.resolve(graph, item) for item in args.ids],
        ))
    if c == "todo":
        if args.op == "add":
            return _result(todo_mod.add(graph, args.name, front=args.front))
        if args.op == "prune":
            return _result(todo_mod.prune(graph, args.name))
        if args.op == "reorder":
            return _result(todo_mod.reorder(graph, args.names))
        return _emit(todo_mod.list_epics(graph), args.json)
    if c == "path":
        try:
            if args.what == "spec":
                _out(path_mod.resolve_spec(graph, args.story))
            elif args.what == "epic":
                _out(path_mod.resolve_epic(graph, args.epic))
            elif args.what == "story":
                _out(path_mod.resolve_story(graph, args.story))
            else:
                _out(path_mod.resolve_branch(graph, args.ref, epic=args.is_epic))
        except ValueError as exc:
            _out(f"error: {exc}")
            return 1
        return 0
    if c == "edit":
        return _cmd_edit(graph, args)
    if c == "vet":
        return _cmd_vet(graph, args)
    if c == "artifact":
        return _cmd_artifact(graph, args)
    if c == "qa":
        return _cmd_qa(graph, args)
    if c == "new":
        fields = _parse_fields(args.fields)
        if fields is None:
            _out("invalid field (expected key=value)")
            return 2
        return _result(
            crud_generic.create_instance(graph, args.kind, args.name, fields),
            getattr(args, "json", False),
        )
    if c == "find":
        return _emit(crud_generic.find_instance(graph, args.kind, args.name), args.json)
    if c == "set":
        fields = _parse_fields(args.fields)
        if fields is None:
            _out("invalid field (expected key=value)")
            return 2
        return _result(
            crud_generic.edit_instance(graph, args.kind, args.name, fields),
            getattr(args, "json", False),
        )
    if c == "remove":
        return _result(
            crud_generic.delete_instance(graph, args.kind, args.name),
            getattr(args, "json", False),
        )
    if c == "template":
        return _cmd_template(graph, args)
    return 2


if __name__ == "__main__":
    sys.exit(main())

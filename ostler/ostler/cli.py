"""ostler command-line entry point."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from importlib.metadata import version as _pkg_version
from pathlib import Path

import yaml

from ostler import autofix as autofix_mod, backlog as backlog_mod, coverage, crud, crud_generic, doctor, edit, fmt as fmt_mod, freeze as freeze_mod, graph as graph_mod, ids as ids_mod, locators, path as path_mod, query as query_mod, reach, registry, scaffold as scaffold_mod, select, templates as templates_mod, todo as todo_mod, trace
from ostler import checks as checks_mod
from ostler import vet as vet_mod
from ostler import artifact as artifact_mod
from ostler import qa as qa_mod
from ostler import index as index_mod
from ostler.model import find_root, load

_TYPES = (
    tuple(t.name for t in registry.REGISTRY)
    + ("seed",)
    + tuple(t.name for t in registry.UI_TYPES)
)


#: The subcommands that answer without loading a graph, and so have no index to control.
#: `checks` prints a vocabulary that is a property of ostler rather than of a book;
#: `cache` operates *on* the index and carries its own `--index-dir` instead.
_INDEXLESS_COMMANDS = frozenset({"checks", "cache"})

#: Days, the unit `cache clean` takes its age bound in. The seconds live in `index`.
_DEFAULT_MAX_AGE_DAYS = index_mod.DEFAULT_MAX_AGE_S / (24 * 60 * 60)


def _add_index_controls(parser: argparse.ArgumentParser) -> None:
    """Give *parser* the two index controls, defaulting to *silence*.

    ``argparse.SUPPRESS`` rather than a real default, exactly as ``write_parent`` does it:
    a subparser applies its own defaults into the shared namespace, so a concrete default
    here would let ``ostler create --no-index epic …`` be overwritten by the ``epic``
    parser's ``False`` on the way past. Suppressed, a parser that did not see the flag
    contributes nothing and the one value :func:`_build_parser` sets stands.
    """
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
    """Add the index controls to every subcommand of *parser* that loads a graph.

    Walked rather than spelled out at each ``add_parser`` call, because "every command
    that loads a graph" is nearly every command ostler has, and a list of sixty would be
    wrong the first time somebody adds the sixty-first. The recursion reaches nested
    subcommands (``create epic``, ``qa run``) so the flag is accepted after the leaf verb
    as well as before it.

    argparse offers no public accessor for the subparsers it has registered, so this reads
    ``_actions``. The alternative is threading a parent parser through every one of those
    call sites and still missing the next one.
    """
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for name, sub in action.choices.items():
            # `choices` is declared as a mapping to `object`, and an alias registers the
            # same parser twice; the isinstance both narrows the type and would skip
            # anything that is not a parser rather than crashing on it.
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

    d = sub.add_parser("doctor", help="referential-integrity check")
    d.add_argument("--epic", help="restrict checks to one epic (name or folder)")
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

    ck = sub.add_parser("checks", help="the `verify:` check vocabulary and its signatures")
    ck.add_argument("name", nargs="?", help="one check, instead of all of them")
    ck.add_argument("--json", action="store_true")

    t = sub.add_parser("trace", help="walk the graph from a node")
    t.add_argument("token", help="seed id, story slug, surface or doc path")

    # ---- retrieval --------------------------------------------------------
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

    se = sub.add_parser("search", help="full-text search over Concepts")
    se.add_argument("q")
    se.add_argument(
        "--type",
        dest="etype",
        help=f"one of {', '.join(_TYPES)}, or a template-declared kind",
    )
    se.add_argument("--json", action="store_true")

    qy = sub.add_parser("query", help="reverse-index queries")
    qy.add_argument("name", choices=query_mod.QUERIES)
    qy.add_argument("arg")
    qy.add_argument("--json", action="store_true")

    rc = sub.add_parser(
        "reach",
        help="derive the documented click-path to a screen (or audit what has none)",
    )
    rc.add_argument(
        "target",
        nargs="?",
        help="screen node id to route to; omit to audit every screen on the surface",
    )
    rc.add_argument(
        "--from",
        dest="start",
        required=True,
        metavar="ID",
        help="screen the walk starts on, e.g. the post-login landing screen",
    )
    rc.add_argument("--surface", help="scope to one service (docs/features/<surface>)")
    rc.add_argument("--json", action="store_true")

    lc = sub.add_parser(
        "locators",
        help="the Playwright locator for every documented control (and where it is ambiguous)",
    )
    lc.add_argument("screen", nargs="?", help="screen slug or node id; omit for every screen")
    lc.add_argument("--surface", help="scope to one service (docs/features/<surface>)")
    lc.add_argument("--json", action="store_true")

    gp = sub.add_parser(
        "graph", help="query the node/edge/bullet graph (nested + typed)"
    )
    gp.add_argument("--surface", help="scope to one service (docs/features/<surface>)")
    gp.add_argument(
        "--type", dest="etype", help="nodes of this type (concept, field, method, …)"
    )
    gp.add_argument("--title", help="title contains this text")
    gp.add_argument(
        "--path",
        help="hierarchy path, e.g. 'concept:agent / field:timeout' (/ = "
        "descendant, > = direct child; each segment is type:title)",
    )
    gp.add_argument(
        "--under", metavar="ID", help="only nodes contained under this node id"
    )
    gp.add_argument("--depth", type=int, help="with --under: cap descent to N levels")
    gp.add_argument(
        "--has-bullet",
        dest="has_bullet",
        metavar="KEY",
        help="nodes that declare this bullet",
    )
    gp.add_argument(
        "--bullet", metavar="KEY=VAL", help="nodes whose KEY bullet contains VAL"
    )
    gp.add_argument(
        "--links-to",
        dest="links_to",
        metavar="ID",
        help="nodes with an out-edge to this node",
    )
    gp.add_argument("--orphans", action="store_true", help="nodes no edge points to")
    out = gp.add_mutually_exclusive_group()
    out.add_argument("--tree", action="store_true", help="indented outline (default)")
    out.add_argument("--ids", action="store_true", help="bare node ids, one per line")
    out.add_argument("--json", action="store_true", help="filtered {nodes, edges}")

    cv = sub.add_parser(
        "coverage", help="join a book's `code:` citations against a source inventory"
    )
    cv.add_argument("--surface", help="scope to one book (docs/features/<surface>)")
    cv.add_argument(
        "--inventory", required=True, metavar="PATH",
        help="the source inventory to diff against (the okf-builder `inventory_source` node's "
             "artifact; `scripts/okf_verify.py` writes one per book)",
    )
    cv.add_argument(
        "--waivers", metavar="PATH",
        help="adjudicated non-units, keyed by `code:` target; a waived unit counts as covered",
    )
    cv.add_argument("--json", action="store_true", help="{covered, total, waived, missing}")

    ne = sub.add_parser("next-epic", help="the next epic with unfinished work")
    ne.add_argument("--json", action="store_true")
    ns = sub.add_parser("next-story", help="the next runnable story in an epic")
    ns.add_argument("epic")
    ns.add_argument("--json", action="store_true")

    # ---- CRUD -------------------------------------------------------------
    cr = sub.add_parser("create", help="create a planning entity (allocates an id)")
    crs = cr.add_subparsers(dest="what", required=True)
    cre = crs.add_parser("epic")
    cre.add_argument("name")
    cre.add_argument("--title", required=True)
    cre.add_argument("--prefix")
    cre.add_argument("--json", action="store_true")
    crm = crs.add_parser("milestone")
    crm.add_argument("name")
    crm.add_argument("--title", required=True)
    crm.add_argument("--source-items", default="", dest="source_items")
    crm.add_argument("--prefix")
    crm.add_argument("--json", action="store_true")
    crb = crs.add_parser("backlog-item")
    crb.add_argument("text")
    crb.add_argument("--section", default="")
    crb.add_argument("--prefix")
    crb.add_argument("--json", action="store_true")
    crt = crs.add_parser("story")
    crt.add_argument("epic")
    crt.add_argument("slug")
    crt.add_argument("--title", required=True)
    crt.add_argument("--covers", default="")
    crt.add_argument("--depends", default="",
                     help="sibling slugs that block this story; written as `- Blocked by:` "
                          "bullets in the story's own `## Dependencies` section")
    crt.add_argument("--prefix")
    crt.add_argument("--json", action="store_true")
    crf = crs.add_parser("feature")
    crf.add_argument("slug")
    crf.add_argument("--title", required=True)
    crf.add_argument("--area", default="")
    crf.add_argument("--route", default="")
    crf.add_argument("--prefix")
    crf.add_argument("--json", action="store_true")
    crp = crs.add_parser("spec", help="create/stamp a spec doc (idempotent; safe after the write)")
    crp.add_argument("slug", help="story slug — the docs/specs/<slug>/ directory")
    crp.add_argument("doc", help="file name, e.g. plan.md, qa.md, review.md, executive.md")
    crp.add_argument("--title", default="", help="H1 for a newly created doc")
    crp.add_argument("--json", action="store_true")

    dl = sub.add_parser("delete", help="delete an epic/story/feature")
    dls = dl.add_subparsers(dest="what", required=True)
    dls.add_parser("epic").add_argument("name")
    dls.add_parser("story").add_argument("slug")
    dls.add_parser("feature").add_argument("slug")

    up = sub.add_parser("update", help="update built-in planning entity metadata")
    ups = up.add_subparsers(dest="what", required=True)
    upst = ups.add_parser("story", help="replace story title, coverage, and dependencies")
    upst.add_argument("slug")
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
        "template", help="define/apply OKF hierarchies (.agents/templates.yml)"
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
    sda.add_argument("--source-bullet", default="", dest="source_bullet")
    sda.add_argument("--layer", action="append", default=[], dest="layers",
                     help=f"repeatable; one of {', '.join(registry.SEED_LAYERS)}")
    sda.add_argument("--service", action="append", default=[], dest="services",
                     help="repeatable; the service/package this seed lands in")
    sdr = sds.add_parser("remove")
    sdr.add_argument("epic")
    sdr.add_argument("id")

    ss = sub.add_parser("set-status", help="set a story's status")
    ss.add_argument("slug")
    ss.add_argument("status")

    ub = sub.add_parser("unblock", help="clear give-up stamps off stories")
    ub.add_argument("slug", nargs="?", default="",
                    help="one story; omit it and pass --epic or --all for the wider scope")
    ub.add_argument("--epic", default="", help="every blocked story in this epic")
    ub.add_argument("--all", action="store_true", dest="all_stories",
                    help="every blocked story in the graph")
    ub.add_argument("--status", default=registry.DEFAULT_STORY_STATUS,
                    help=f"the status to restore (default: {registry.DEFAULT_STORY_STATUS!r})")
    ub.add_argument("--json", action="store_true")

    bl = sub.add_parser("backlog", help="manage docs/backlog.md")
    bls = bl.add_subparsers(dest="op", required=True)
    bla = bls.add_parser("add")
    bla.add_argument("id")
    bla.add_argument("text")
    bla.add_argument("--section", default="")
    blad = bls.add_parser("adopt")
    blad.add_argument("--path", default="")
    blad.add_argument("--prefix")
    bls.add_parser("prune").add_argument("id")
    bls.add_parser("list").add_argument("--json", action="store_true")

    ml = sub.add_parser("milestone", help="manage milestone backlog ownership")
    mls = ml.add_subparsers(dest="op", required=True)
    mlss = mls.add_parser("set-source-items")
    mlss.add_argument("name")
    mlss.add_argument("ids", nargs="+")

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
    sr.add_argument("slug")

    sc = sub.add_parser(
        "scaffold", help="create a UI-profile node in the right place (§9)"
    )
    sc.add_argument("type", help=f"one of {', '.join(registry.UI_TYPES_BY_NAME)}")
    sc.add_argument("name")
    sc.add_argument(
        "--service", help="file-level types: the service subtree (docs/features/<svc>/)"
    )
    sc.add_argument(
        "--in",
        dest="in_file",
        help="section-level types: the surface doc to insert the `### id` into",
    )
    sc.add_argument("--title")
    sc.add_argument("--json", action="store_true")

    fm = sub.add_parser(
        "fmt", help="canonicalize UI-profile docs (frontmatter/bullets/headings)"
    )
    fm.add_argument(
        "paths", nargs="*", help="files to format (default: all docs/features/**/*.md)"
    )
    fm.add_argument(
        "--check",
        action="store_true",
        help="don't write; exit 1 if any file is not already canonical",
    )

    af = sub.add_parser(
        "autofix", help="fix shape-detectable format drift (e.g. verify: holding test ids)"
    )
    af.add_argument(
        "paths", nargs="*", help="files to fix (default: all docs/features/**/*.md)"
    )
    af.add_argument(
        "--check",
        action="store_true",
        help="don't write; exit 1 if any file carries a fixable drift",
    )

    # ---- path resolution -----------------------------------------------------
    pa = sub.add_parser("path", help="resolve a slug to its canonical path")
    pas = pa.add_subparsers(dest="what", required=True)
    pa_spec = pas.add_parser("spec", help="spec dir for a story (slug or minted id)")
    pa_spec.add_argument("slug")
    pa_epic = pas.add_parser("epic", help="directory for an epic (number or bare slug)")
    pa_epic.add_argument("epic")
    pa_story = pas.add_parser("story", help="story.md path for an epic + slug")
    pa_story.add_argument("epic")
    pa_story.add_argument("slug")
    pa_branch = pas.add_parser("branch", help="git branch name for a slug")
    pa_branch.add_argument("slug")
    pa_branch.add_argument(
        "--epic",
        action="store_true",
        dest="is_epic",
        help="emit feat/<slug> instead of the bare <slug>",
    )

    fz = sub.add_parser(
        "freeze", help="pin an approved story/seed as immutable ground truth"
    )
    fz.add_argument("ident")
    fz.add_argument("--by", default="")
    fz.add_argument("--note", default="")
    uf = sub.add_parser("unfreeze", help="lift the freeze on a story/seed")
    uf.add_argument("ident")

    # ---- vet ---------------------------------------------------------------
    vt = sub.add_parser(
        "vet", parents=[write_parent], help="deterministic visual-fidelity check"
    )
    vt.add_argument("screenshot", type=Path)
    vt.add_argument("--manifest", required=True, type=Path)
    vt_group = vt.add_mutually_exclusive_group(required=True)
    vt_group.add_argument("--cdp-url", dest="cdp_url")
    vt_group.add_argument("--regions", dest="regions_file", type=Path)
    vt.add_argument("--slug", required=True)
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
        help="spec directory (absolute, or relative to the repo root)",
    )
    arsc.add_argument("--force", action="store_true")
    arvt = ars.add_parser("vet", help="validate the artifact against its contract")
    arvt.add_argument("kind")
    arvt.add_argument("--spec", required=True, type=Path)
    arvt.add_argument("--json", action="store_true")
    arls = ars.add_parser("list", help="show registered artifact kinds")
    arls.add_argument("--json", action="store_true")

    # ---- qa ----------------------------------------------------------------
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
        help="spec directory (absolute or repo-relative)",
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
    qa_lint.add_argument("--spec", default=None, type=Path)
    qa_lint.add_argument("--json", action="store_true")

    qa_validate = qas.add_parser(
        "validate", help="validate a qa_plan.py without executing"
    )
    qa_validate.add_argument("plan_file", type=Path)
    qa_validate.add_argument("--spec", default=None, type=Path)
    qa_validate.add_argument("--json", action="store_true")

    qa_sensitivity = qas.add_parser(
        "sensitivity",
        help="report which declared checks could actually have gone red",
    )
    qa_sensitivity.add_argument(
        "--node", default="",
        help="only claims whose id or book path contains this substring",
    )
    qa_sensitivity.add_argument("--json", action="store_true")

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

    qa_stack = qas.add_parser(
        "stack", help="bring the stack the book declares up (or tear it down)"
    )
    qa_stack_ops = qa_stack.add_subparsers(dest="stack_op", required=True)
    qa_stack_up = qa_stack_ops.add_parser("up", help="bring the declared stack to ready")
    qa_stack_up.add_argument("--runbook", default="",
                             help="which runbook, when the book carries more than one")
    qa_stack_up.add_argument("--json", action="store_true")
    qa_stack_down = qa_stack_ops.add_parser("down", help="run the declared teardown recipe")
    qa_stack_down.add_argument("--runbook", default="")
    qa_stack_down.add_argument("--json", action="store_true")

    qa_tools = qas.add_parser("tools", help="inspect this repo's opted-in QA tools")
    qa_tools_ops = qa_tools.add_subparsers(dest="tools_op", required=True)
    qa_tools_list = qa_tools_ops.add_parser("list", help="list opted-in tools and whether they resolve")
    qa_tools_list.add_argument("--json", action="store_true")

    qa_context = qas.add_parser(
        "context", help="build the base/head changed-code to OKF obligation packet"
    )
    qa_context.add_argument("--base", required=True)
    qa_context.add_argument("--head", default="WORKTREE")
    qa_context.add_argument("--spec", required=True, type=Path)
    qa_context.add_argument("--features-root", default="",
                            help="repo-relative feature book; default: as configured")
    qa_context.add_argument(
        "--source-root",
        action="append",
        default=[],
        metavar="SURFACE=PATH",
        help="associate a production source root with an OKF surface (repeatable)",
    )
    qa_context.add_argument("--story-file", type=Path)
    qa_context.add_argument("--json", action="store_true")

    qa_context_show = qas.add_parser(
        "context-show", help="read a filtered, paged slice of an already-built context packet"
    )
    qa_context_show.add_argument("--spec", required=True, type=Path)
    owed = qa_context_show.add_mutually_exclusive_group()
    owed.add_argument("--required", action="store_true",
                      help="only obligations owed live evidence")
    owed.add_argument("--context-only", action="store_true", dest="context_only",
                      help="only obligations reached by closure")
    qa_context_show.add_argument("--node", default="",
                                 help="substring of the obligation's node path")
    qa_context_show.add_argument("--kind", default="",
                                 help="exact obligation kind, e.g. contract, journey, does")
    qa_context_show.add_argument("--offset", type=int, default=0)
    qa_context_show.add_argument("--limit", type=int,
                                 help="how many to print; omit for all that matched")
    qa_context_show.add_argument("--ids-only", action="store_true", dest="ids_only",
                                 help="print bare obligation ids, no requirement text")
    qa_context_show.add_argument("--no-locators", action="store_false", dest="locators",
                                 help="omit each obligation's locator bullets")
    qa_context_show.add_argument("--json", action="store_true")

    qa_compile_plan = qas.add_parser(
        "compile-plan",
        help="compile a qa_plan.py skeleton from the context packet, reading no source",
    )
    qa_compile_plan.add_argument("--spec", required=True, type=Path)
    qa_compile_plan.add_argument(
        "--out", default=None, type=Path, metavar="PATH",
        help="write the plan here; omit to print it. An existing file is never overwritten",
    )
    qa_compile_plan.add_argument(
        "--story", default="",
        help="story name for `plan(story=...)`; default: the one the packet was built for",
    )
    qa_compile_plan.add_argument("--run-id", default=None, dest="run_id")
    qa_compile_plan.add_argument(
        "--base-url", default="http://localhost:8000", dest="base_url",
        help="base URL for the compiled `target(...)`",
    )
    qa_compile_plan.add_argument("--json", action="store_true")

    qa_context_validate = qas.add_parser(
        "context-validate", help="validate qa-okf-context.json"
    )
    qa_context_validate.add_argument("--spec", required=True, type=Path)
    qa_context_validate.add_argument("--json", action="store_true")

    qa_evidence_map = qas.add_parser(
        "evidence-map",
        help="join the context packet, the run log, the manifest and qa-evidence.json "
             "into one status per obligation",
    )
    qa_evidence_map.add_argument("--spec", default=None, type=Path)
    qa_evidence_map.add_argument(
        "--out-dir",
        default=None,
        dest="out_dir",
        metavar="LABEL",
        help="read the dry-run ledger at <spec>/qa/LABEL/ instead of the scored one; "
             "must be the label that run was given",
    )
    qa_evidence_map.add_argument(
        "--status",
        default="",
        choices=["", *qa_mod.STATUSES],
        help="print only the obligations with this status",
    )
    qa_evidence_map.add_argument(
        "--out",
        default=None,
        type=Path,
        metavar="PATH",
        help="also write the map as JSON here",
    )
    qa_evidence_map.add_argument("--json", action="store_true")

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

    # ---- cache -------------------------------------------------------------
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

    # One value for the whole run, set here so a suppressed flag on any subparser leaves
    # it standing. On by default from the first commit: `--no-index` is the escape hatch.
    p.set_defaults(no_index=False, index_dir=None)
    _add_index_controls(p)
    _install_index_controls(p)
    return p


# ---------------------------------------------------------------------------
#: ``{id: handle}`` while the run is abbreviating, empty otherwise. Module state because every
#: command prints through :func:`_out`, and threading a table through 30 dispatch arms to reach
#: `print` would be a worse trade than one value set once per run. The mode is tracked separately
#: because "abbreviating" and "has ids to abbreviate" differ in a fresh repo — the first `create`
#: there is exactly the case that needs the table extended.
_HANDLES: dict[str, str] = {}
_HANDLES_ON = False


def _use_handles(graph, args) -> None:
    """Decide, once per run, whether ids print short.

    Human output abbreviates by default and ``--json`` does not: a person reading a listing wants
    a token short enough to retype, while a program reading one wants the identity that never
    changes — a handle lengthens the moment a colliding id is minted, so it is a display form, not
    a key to store. ``--handles`` / ``--full-ids`` override either default; input is unaffected,
    since a handle is accepted wherever an id is regardless of how this run prints.
    """
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


def _result(res, as_json: bool = False) -> int:
    # An id minted by *this* command postdates the table, and it is the one id the caller is most
    # likely to copy — so fold it in rather than printing the one full id in an abbreviated run.
    if _HANDLES_ON and res.entity_id and res.entity_id not in _HANDLES:
        _HANDLES.update(ids_mod.table([*_HANDLES, res.entity_id]))
    if as_json:
        # `name` is the name the writer used — an epic lands in a numbered directory, so a
        # caller that pipes `--json` into a path needs the created name, not the one it asked
        # for. It falls back to the id-only shape's silence: "" when the writer named nothing.
        _out(json.dumps({"ok": res.ok, "id": res.entity_id,
                          "name": res.entity_name, "message": res.message}))
    else:
        _out(res.message)
    return 0 if res.ok else 1


def _cmd_reach(graph, args) -> int:
    """Route to one screen, or audit the whole surface when no target is given.

    Exits non-zero when a route is missing — an unreachable screen is a defect in the book, and a
    caller that shells out to this should stop rather than navigate by URL and paper over it.
    """
    if args.target:
        data = graph_mod.build(graph, surface=args.surface)
        by_id = {n["id"]: n for n in data["nodes"]}
        path = reach.route(reach.navigation_edges(data), args.start, args.target, by_id)
        if args.json:
            _out(json.dumps({"start": args.start, "target": args.target, "route": path}))
        elif path is None:
            _out(f"no documented route from {args.start} to {args.target}")
        else:
            _out(reach.render_route(path, args.start, args.target))
        return 1 if path is None else 0

    report = reach.reachability(graph, surface=args.surface, start=args.start)
    _out(json.dumps(report) if args.json else reach.render_reachability(report))
    return 1 if report["unreachable"] else 0


def _cmd_locators(graph, args) -> int:
    """Emit the derived locators, exiting non-zero when the one-to-one mapping is broken.

    A collision or an unlocatable control means a caller cannot mechanically address what the book
    documents. Failing here keeps that a documentation defect rather than letting it resurface as a
    strict-mode violation in somebody's test run.
    """
    data = locators.build(graph, surface=args.surface, screen=args.screen)
    _out(locators.render_json(data) if args.json else locators.render(data))
    broken = (data["collisions"] or data["unnamed"] or data["invalid_roles"]
              or data["counts"]["unlocatable"])
    return 1 if broken else 0


def _cmd_doctor(graph, args, store: index_mod.IndexStore) -> int:
    report = doctor.run(graph, epic_filter=args.epic, check_schema=not args.no_schema)
    if args.json:
        # The hit/miss line is *added* to the report, never substituted for it: a caller
        # that gates on `errors` must not have to learn a new shape to keep doing so.
        payload = report.as_dict()
        payload["index"] = store.stats()
        _out(json.dumps(payload, indent=2))
        return 1 if report.errors else 0
    _out(f"org: {report.org}   profile: {report.profile}")
    for facts in report.epics:
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
    """Run doctor both ways and diff the two reports — the correctness half of the gate.

    One command rather than a flag pair, because CI has to be able to run it without
    knowing how to compare two invocations' output itself. Both loads happen in this
    process and each gets its own index session, so the indexed run is the one that reads
    and writes entries and the other is the cold path it must agree with.

    ``--no-index`` is deliberately ignored here: a mode whose whole job is to run both
    ways has nothing to do with an escape hatch from one of them.

    Until a parse product is actually served from the store the two runs are the same
    computation and this passes trivially — which is the correct result, and the point of
    landing the gate green before anything starts depending on it.
    """
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
    """``ostler cache clean`` — the eviction `IndexStore.prune` runs automatically.

    Exits zero against a directory that is not there: a fresh machine has no index, and a
    clean that fails because there was nothing to clean is a clean that cannot be put in a
    setup script.
    """
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


def _cmd_fmt(graph, args) -> int:
    result = fmt_mod.run_fmt(graph, args.paths, check=args.check)
    for path in result.changed:
        rel = (
            path.relative_to(graph.root).as_posix()
            if path.is_relative_to(graph.root)
            else path.as_posix()
        )
        _out(f"{'would reformat' if args.check else 'reformatted'}: {rel}")
    if not result.changed:
        _out("all files already canonical")
        return 0
    if args.check:
        _out(
            f"\n{len(result.changed)} file(s) not canonical (run `ostler fmt` to fix)"
        )
        return 1
    _out(f"\nreformatted {len(result.changed)} file(s)")
    return 0


def _cmd_autofix(graph, args) -> int:
    result = autofix_mod.run_autofix(graph, args.paths, check=args.check)
    for path in result.changed:
        rel = (
            path.relative_to(graph.root).as_posix()
            if path.is_relative_to(graph.root)
            else path.as_posix()
        )
        _out(f"{'would fix' if args.check else 'fixed'}: {rel}")
    if not result.changed:
        _out("no fixable drift found")
        return 0
    if args.check:
        _out(
            f"\n{len(result.changed)} file(s) carry fixable drift (run `ostler autofix` to fix)"
        )
        return 1
    _out(f"\nfixed {len(result.changed)} file(s)")
    return 0


def _cmd_edit(graph, args) -> int:
    if args.op == "relink":
        plan = edit.relink(graph, args.old_path, args.new_path)
    elif args.op == "settle-review":
        plan = edit.settle_review(graph, args.slug)
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
    outcome, plan = vet_mod.run_vet(
        graph,
        args.screenshot,
        args.manifest,
        args.slug,
        cdp_url=args.cdp_url,
        regions_file=args.regions_file,
        state=args.state,
        iou_threshold=args.iou_threshold,
    )
    # A run without an error carries a report; treating a missing one as an error keeps the
    # two exits together instead of reporting "clean" off an object that is not there.
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
    # vet
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
        return spec_arg if spec_arg.is_absolute() else root / spec_arg

    if op == "start":
        spec_dir = _resolve_spec(args.spec)
        env = dict(kv.split("=", 1) for kv in args.env if "=" in kv)
        daemons: list[qa_mod.DaemonSpec] = []
        for raw in args.daemons:
            parts = raw.split(":", 2)
            name = parts[0]
            # `shlex.split`, not a shell: it recovers the argv an author wrote with quotes,
            # and leaves `&&` or `|` as literal arguments that fail at `exec` with the
            # program named. A daemon has not been able to be a command line since the shell
            # came out of `start_daemon`, and the CLI is not the place to put one back.
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
        spec_dir = args.spec
        if spec_dir is not None and not spec_dir.is_absolute():
            spec_dir = root / spec_dir
        result = qa_mod.cmd_lint(args.plan_file, spec_dir, root=root)
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

    if op == "sensitivity":
        result = qa_mod.cmd_sensitivity(root, node=args.node)
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

    if op == "stack":
        if args.stack_op == "up":
            result = qa_mod.runbook.cmd_stack_up(root, name=args.runbook)
        else:
            result = qa_mod.runbook.cmd_stack_down(root, name=args.runbook)
        if args.json:
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

    if op == "context":
        spec_dir = _resolve_spec(args.spec)
        source_roots: dict[str, list[str]] = {}
        for raw in args.source_root:
            if "=" not in raw:
                _out(f"error: --source-root must be SURFACE=PATH, got {raw!r}")
                return 2
            surface, path = raw.split("=", 1)
            source_roots.setdefault(surface.strip(), []).append(path.strip())
        story_file = args.story_file
        if story_file is not None and not story_file.is_absolute():
            story_file = root / story_file
        result = qa_mod.cmd_context(
            root,
            spec_dir,
            base=args.base,
            head=args.head,
            source_roots=source_roots,
            features_root=args.features_root,
            story_file=story_file,
        )
        if result.status == "invalid":
            # The packet was never built — `data` carries the failure, not a graph.
            _out(json.dumps(result.data, indent=2) if args.json else f"error: {result.message}")
            return 1
        _out(json.dumps(result.data, indent=2) if args.json else result.message)
        return 0 if result.ok else 1

    if op == "context-show":
        spec_dir = _resolve_spec(args.spec)
        context_file = spec_dir / "qa-okf-context.json"
        try:
            packet = json.loads(context_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _out(json.dumps({"status": "invalid", "message": str(exc)}, indent=2)
                 if args.json else f"error: {exc}")
            return 1
        required = True if args.required else (False if args.context_only else None)
        page, matched = qa_mod.select_obligations(
            packet,
            required=required,
            node=args.node,
            kind=args.kind,
            offset=args.offset,
            limit=args.limit,
        )
        if args.json:
            _out(json.dumps({"obligations": page, "matched": matched,
                             "total": len(packet.get("obligations", []))}, indent=2))
            return 0
        if args.ids_only:
            _out("\n".join(item["id"] for item in page) or "- (none)")
        else:
            _out("\n".join(qa_mod.render_obligations(page, locators=args.locators)))
        shown = args.offset + len(page)
        _out(f"\n# showing {args.offset + 1 if page else 0}-{shown} of {matched} matched "
             f"({len(packet.get('obligations', []))} in packet)")
        return 0

    if op == "compile-plan":
        spec_dir = _resolve_spec(args.spec)
        result = qa_mod.cmd_compile_plan(
            spec_dir,
            out=args.out,
            story=args.story,
            run_id=args.run_id,
            base_url=args.base_url,
        )
        _out(json.dumps(result.data, indent=2) if args.json else result.message)
        return 0 if result.ok else 1

    if op == "context-validate":
        spec_dir = _resolve_spec(args.spec)
        result = qa_mod.cmd_context_validate(spec_dir)
        if args.json:
            _out(json.dumps(result.data, indent=2))
        else:
            _out(result.message)
        return 0 if result.ok else 1

    if op == "evidence-map":
        spec_dir = _resolve_spec(args.spec)
        try:
            data = qa_mod.build_evidence_map(spec_dir, label=args.out_dir)
        except (qa_mod.EvidenceMapError, qa_mod.ScratchLabelError) as exc:
            _out(json.dumps({"status": "invalid", "message": str(exc)}, indent=2)
                 if args.json else f"error: {exc}")
            return 1
        if args.out:
            args.out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        if args.json:
            _out(json.dumps(data, indent=2))
        else:
            _out("\n".join(qa_mod.render_evidence_map(data, only=args.status)))
        # Non-zero when anything is not `covered`, so a caller can gate on the join without
        # parsing it. `contradicted`, `unproven` and `uncovered` are all blocking and all
        # mean the published evidence does not describe the run — they differ only in who
        # has to fix it, which the caller reads off the status rather than the exit code.
        return 0 if data["counts"]["covered"] == len(data["obligations"]) else 1

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
    """Print the `verify:` vocabulary, so a signature can be read rather than guessed."""
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
                "params": [{"name": p.name, "type": p.type, "required": p.required}
                           for p in s.params],
                "excludes": s.excludes,
            }
            for s in specs
        ], indent=2))
        return 0
    # `excludes` alongside the signature on purpose: it is what makes the choice between two
    # checks decidable, and an author picking by name alone picks the weaker one.
    _out("\n\n".join(f"{s.signature()}\n    excludes {s.excludes}" for s in specs))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    cwd = Path(args.chdir) if args.chdir else None
    # Before the graph: the vocabulary is a property of ostler, not of a book, and an author
    # who needs to look a signature up is often standing somewhere there is no book to load.
    if args.command == "checks":
        return _cmd_checks(args)
    # Also before the graph, for the opposite reason: `cache clean` acts on the index, and
    # a machine whose book will not load is exactly one somebody wants to clean the cache on.
    if args.command == "cache":
        return _cmd_cache(args)
    if args.command == "doctor" and args.verify_index:
        return _cmd_verify_index(cwd, args)
    # The session wraps the load as well as the dispatch: the parse products the next
    # increment serves are read during `load`, so a session opened after it would cover
    # the cheap half of the run and miss the expensive one.
    with index_mod.session(
        find_root(cwd if cwd is not None else Path.cwd()),
        directory=args.index_dir,
        enabled=not args.no_index,
    ) as store:
        graph = load(cwd)
        _use_handles(graph, args)
        return _dispatch(graph, args, store)


def _dispatch(graph, args, store: index_mod.IndexStore) -> int:  # noqa: C901 — flat command dispatch
    c = args.command

    if c == "doctor":
        return _cmd_doctor(graph, args, store)
    if c == "trace":
        lines, found = trace.run(graph, ids_mod.resolve(graph, args.token))
        _out("\n".join(lines))
        return 0 if found else 1
    if c == "reach":
        return _cmd_reach(graph, args)
    if c == "locators":
        return _cmd_locators(graph, args)
    if c == "graph":
        data = graph_mod.build(graph, surface=args.surface)
        sel = graph_mod.select(
            data,
            node_type=args.etype,
            title=args.title,
            path=args.path,
            under=args.under,
            depth=args.depth,
            has_bullet=args.has_bullet,
            bullet=args.bullet,
            links_to=args.links_to,
            orphans=args.orphans,
        )
        if args.json:
            ids = {n["id"] for n in sel}
            _out(
                json.dumps(
                    {
                        "counts": {"nodes": len(sel)},
                        "nodes": sel,
                        "edges": [e for e in data["edges"] if e["from"] in ids],
                    }
                )
            )
        elif args.ids:
            _out(graph_mod.render_ids(sel))
        else:
            _out(graph_mod.render_tree(sel))
        return 0
    if c == "coverage":
        result = coverage.cmd_coverage(graph, surface=args.surface, inventory=args.inventory,
                                       waivers=args.waivers)
        if result.status == "invalid":
            # An unreadable inventory is a failure, never an empty one: zero units reads
            # downstream as "everything is covered". Its own exit code, because a caller
            # that retries on an incomplete book must not retry on a broken inventory.
            print(f"ostler coverage: {result.message}", file=sys.stderr)
            return 2
        _out(json.dumps(result.data, indent=2) if args.json else result.message)
        # Exit non-zero on an incomplete book so a `make` target / CI check can gate on it.
        return 0 if result.ok else 1
    if c in ("list", "search"):
        valid_types = _TYPES + tuple(k.name for k in graph.template_kinds)
        if args.etype is not None and args.etype not in valid_types:
            _out(
                f"error: argument --type: invalid choice: '{args.etype}' "
                f"(choose from {', '.join(valid_types)})"
            )
            return 2
    if c == "list":
        return _emit(
            # `list`'s own `--type` is `required=True` — unlike `search`'s, which is a filter.
            query_mod.list_entities(graph, str(args.etype), args.epic, args.status),
            args.json,
        )
    if c == "search":
        return _emit(
            query_mod.search(graph, args.q, args.etype), args.json
        )
    if c == "query":
        return _emit(query_mod.query(graph, args.name, ids_mod.resolve(graph, args.arg)), args.json)
    if c == "next-epic":
        return _emit(select.next_epic(graph), args.json)
    if c == "next-story":
        return _emit(select.next_story(graph, args.epic), args.json)
    if c == "create":
        if args.what == "epic":
            res = crud.create_epic(graph, args.name, args.title, args.prefix)
        elif args.what == "milestone":
            res = crud.create_milestone(
                graph,
                args.name,
                args.title,
                [ids_mod.resolve(graph, item) for item in _split(args.source_items)],
                args.prefix,
            )
        elif args.what == "backlog-item":
            res = backlog_mod.create(graph, args.text, args.section, args.prefix)
        elif args.what == "story":
            res = crud.create_story(
                graph,
                args.epic,
                args.slug,
                args.title,
                [ids_mod.resolve(graph, s) for s in _split(args.covers)],
                _split(args.depends),
                args.prefix,
            )
        elif args.what == "spec":
            res = crud.create_spec(graph.doc_roots["specs"], args.slug, args.doc, args.title)
        else:
            res = crud.create_feature(
                graph, args.slug, args.title, args.area, args.route, args.prefix
            )
        return _result(res, getattr(args, "json", False))
    if c == "delete":
        if args.what == "epic":
            return _result(crud.delete_epic(graph, args.name))
        if args.what == "story":
            return _result(crud.delete_story(graph, args.slug))
        return _result(crud.delete_feature(graph, args.slug))
    if c == "update":
        return _result(
            crud.update_story(
                graph,
                args.slug,
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
                "sourceBullet": args.source_bullet,
                "layers": args.layers,
                "services": args.services,
            }
            # A handle resolves here too: `seed add` is update-or-create, so naming an existing
            # seed by its handle updates that seed instead of filing a second one under a name
            # that only looked new. An id nothing matches is passed through and creates.
            return _result(
                crud.add_seed(
                    graph, args.epic, ids_mod.resolve(graph, args.id),
                    args.status, args.summary, meta
                )
            )
        return _result(crud.remove_seed(graph, args.epic, ids_mod.resolve(graph, args.id)))
    if c == "set-status":
        return _result(crud.set_status(graph, args.slug, args.status))
    if c == "unblock":
        # A bare `ostler unblock` rewrites every stamped story in the repo, which is a
        # reasonable thing to want and a terrible thing to do by accident — so the widest
        # scope is the one that has to be spelled out.
        if not (args.slug or args.epic or args.all_stories):
            return _result(crud.Result(False, "name a story, pass --epic, or pass --all"), args.json)
        if args.all_stories and (args.slug or args.epic):
            return _result(crud.Result(False, "--all takes no story or --epic"), args.json)
        return _result(
            crud.unblock(graph, story=args.slug, epic=args.epic, status=args.status),
            args.json,
        )
    if c == "backlog":
        if args.op == "add":
            return _result(backlog_mod.add(graph, args.id, args.text, args.section))
        if args.op == "adopt":
            return _result(backlog_mod.adopt(graph, args.path, args.prefix))
        if args.op == "prune":
            return _result(backlog_mod.prune(graph, ids_mod.resolve(graph, args.id)))
        return _emit(
            [{"id": i, "text": t} for i, t in backlog_mod.items(graph)], args.json
        )
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
        if args.what == "spec":
            _out(path_mod.resolve_spec(graph, args.slug))
        elif args.what == "epic":
            _out(path_mod.resolve_epic(graph, args.epic))
        elif args.what == "story":
            _out(path_mod.resolve_story(graph, args.epic, args.slug))
        else:
            _out(path_mod.resolve_branch(args.slug, epic=args.is_epic))
        return 0
    if c == "scaffold":
        return _result(
            scaffold_mod.scaffold(
                graph,
                args.type,
                args.name,
                service=args.service,
                in_file=args.in_file,
                title=args.title,
            ),
            getattr(args, "json", False),
        )
    if c == "fmt":
        return _cmd_fmt(graph, args)
    if c == "autofix":
        return _cmd_autofix(graph, args)
    if c == "edit":
        return _cmd_edit(graph, args)
    if c == "freeze":
        plan = freeze_mod.freeze(graph, ids_mod.resolve(graph, args.ident), by=args.by, note=args.note)
        _out(plan.render())
        if plan.error:
            return 1
        plan.apply()
        _out(
            f"frozen — recorded in {(graph.root / '.agents' / 'ids.json').as_posix()}"
        )
        return 0
    if c == "unfreeze":
        plan = freeze_mod.unfreeze(graph, ids_mod.resolve(graph, args.ident))
        _out(plan.render())
        if plan.error:
            return 1
        plan.apply()
        return 0
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

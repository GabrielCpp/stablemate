# workhorse-workflows

The stablemate agent workflows as an installable Python distribution: `research`,
`author`, `okf-builder` and `coder`, each a checkpointed state machine. Workhorse is the
engine; this is its content.

**Not on PyPI yet** — install it from a checkout of the
[stablemate](https://github.com/GabrielCpp/stablemate) workspace, into the *same*
interpreter as workhorse, because a workflow runs in workhorse's own process:

```bash
make sync                              # at the workspace root: engine + workflows, one venv
uv run workhorse run research          # resolved through the entry-point group
uv run workhorse-research run          # the same parser, name already bound
```

The shape came from the
[workflow-as-python-state-machine](../docs/plans/workflow-as-python-state-machine.md)
design brief, which shipped and is now kept only for its reasoning. What is still
outstanding *here* is noted under [Status](#status).

## How workhorse finds a workflow in here

A distribution advertises what it ships:

```toml
[project.entry-points."workhorse.workflows"]
research = "workhorse_workflows.research.workflow:workflow"

[project.scripts]
workhorse-research = "workhorse_workflows.research.workflow:main"
```

The **entry point** points at the `Workflow` object, because discovery needs the
registry rather than the entry function. The **console script** points at `main` — the
callable `console_script(workflow.entry_point(Entry))` *returns*, since a script target
is called after import, not during it. `entry_point` declares which flow a bare run
starts and returns the registry; `console_script` — which lives in `workhorse.cli`,
the ring a console script actually starts — turns it into that callable.

`workhorse run <name>` resolves the entry point and hands the name to the same parser
`workhorse-<name>` uses. There is one parser on purpose: two commands with two parsers
is the failure this shape invites.

Nothing here is a plugin API for workhorse. A third party can register the same group
— that is what makes the mechanism plural — but the engine still knows no workflow's
vocabulary, and this package still imports the engine and never the other way.

## Installed unpacked, always

Workhorse renders a workflow's prompts with a filesystem template loader rooted at the
workflow's own package directory, and keys per-node overrides on that directory's
name. A wheel installed by pip or uv satisfies this; a zipapp or zip-safe egg does
not, and workhorse refuses one at resolution rather than failing later as a missing
template.

## A workflow reads no environment (load-bearing)

**Prohibited:** `os.environ`, `os.getenv` and their kin anywhere under
`src/workhorse_workflows/`. Everything a node or a state needs is an **argument** or a
**workflow parameter** — a field on the `Workflow` subclass, settable with `--param`.

The reason is the checkpoint. A run's inputs are recorded there, so a resume days later
on another machine replays the values the run actually started with; a value read from
the environment is in no checkpoint, so a resume silently takes a *different* one and
nothing in the artifacts says so. It is also absent from the run's telemetry, and
unreachable from the CLI — `--params` cannot set it — which splits the operator contract
across two spellings that no test compares.

The **process boundary** is where the environment legitimately lives, and it is outside
this package: `workhorse/cli/run.py` and `workhorse/entrypoint.sh` translate `$FOO` into
`--params` once, on the way in. That is why `repo_dir` reaches every workflow without any
of them reading `AGENT_REPO_DIR`.

Ambient *paths* — `repo_dir`, `docs_path`, `workspace_file` — are wanted by roughly every
second node and chosen by no state, which is exactly the shape that used to be an
environment read. They are fields, and `Workflow.injects` (see `coder/shared/paths.AMBIENT`)
fills them into any node or sub-flow that declares a parameter of the same name and was
not passed one. A callsite value always wins, and an empty field injects nothing, so the
target's own default stands.

One exception, and it is a security property rather than an exemption:
`kit/credentials.py` resolves tokens from the environment **because** a secret must never
become a `--param` — params are checkpointed to disk and echoed in logs and telemetry,
which is precisely what a token must not be. A credential crosses into a subprocess by
*name* (`_git_network_command` names the variable; git expands it), never by value.
Keeping that in one auditable module is the point.

The rule is enforced, not just written down:

```bash
make check-no-env    # also runs as part of `make test`
```

## A workflow does not spell a doc path (load-bearing)

**Where a document lives is ostler's answer.** The epics root, the epic folder, the story
folder, the epics index, the backlog file, the feature book and its waivers and screenshots
all come from `ostler.path`; no module under `src/workhorse_workflows/` writes
`docs/epics`, `docs/backlog.md` or `docs/features` as a literal.

The reason is that these locations are **configurable** — a repo moves them with
`docRoots:` in `ostler.yml` / `agents.yml` — and that epic directories are **numbered**
(`0001-checkout-flow`) while every queue entry, prompt and operator names them by bare
slug. A hand-built join gets both wrong, and gets them wrong *silently*: the run writes
into a directory nothing reads, and `ostler doctor` reports a book that is not there. Two
derivations of the same location is the failure the rule exists for; the second one never
learns about the config.

What a workflow still owns is the **filename it invented** — `context.md`, `feedback.md`,
`_author-context.md`, `<gate>-context.md`, `attempts.md`, `dependencies.json` — joined onto
a directory ostler resolved. Run artifacts that are not documents at all (`.agents/operator`,
`.agents/okf-build`, the dream inbox and ledger, the surveyor's `docs/survey/` scratch) stay
with the workflow, because ostler has no opinion about them.

Each workflow's `shared/paths.py` is the one place that calls `ostler.path`, and it is also
where an operator override is honoured: a `backlog` or `epics_dir` **parameter** wins when
it is set, and empty — the normal case — means "as this repo configures it". An override
still gets ostler's resolution rules applied inside it, via the `*_under` family.

Two probes look like exceptions and are not: the repo-root resolvers test for a `docs/epics/`
directory, and that is how a *root* is recognized before there is a root to ask ostler about.

**And what is *in* the document is ostler's answer too.** A node that reads a backlog entry,
an epic's stories, a gate's frontmatter or a table in the book goes through
`ostler.markdown` — `find_section` / `Section.bullets` / `Bullet.bracketed` /
`walk_tables` — not a `^\s*-\s*\[(\w+)\]` of its own. Same failure mode as a hand-built
path, one layer down: a bullet regex matches inside a fenced example, misses the
`- **Status**:` spelling of the field it wants, and reports a confident wrong answer rather
than raising. Agent *output* is different — a CLI's log line has no grammar, and regex is
what reads it. The boundary, the parser for each format, and how to declare an exemption
are in the `stablemate-structured-parsing` skill; `make check-parsers` enforces it.

## A prompt does not name a skill (load-bearing)

**Which skill teaches a subject is the repo's answer, asked for by tag.** A prompt in here
has never met the repo it will run against, so it may not write
`instruction_refs("go-testing", "flutter-testing", "react-router-testing", …)` — the menu
of every stack the author happened to think of. It asks for the capability instead:

```jinja
{% raw %}{{ find_by_tags("web", "tests") }}{% endraw %}
```

The query is an AND over the `tags:` in each installed skill's front matter, it renders the
matching skills' paths (backticked, comma-joined) and it renders **nothing** when the repo
installs no match — so the sentence around it carries a `| default("(none installed — …)",
true)`, or the whole paragraph sits behind `{% raw %}{% if %}{% endraw %}`.

The hand-listed menu was wrong in both directions. A repo with a stack the list forgot got
no guidance at all, and — the defect that cost a run — a repo with only a web app and no
mobile code rendered `plan-story` with ten mentions of Flutter and Dart, because the helper
correctly dropped the unresolvable names while the prose around it still enumerated them.
`tests/coder/test_prompt_stack_neutrality.py` renders every coder prompt against a
one-stack manifest and holds that line.

The vocabulary the coder prompts query is `runbook`, `standards`, `tests`, `qa` and
`codegen`, each combined with a layer — `backend`, `cli`, `web`, `mobile`, `infra`. It is
documented for skill authors in the `stablemate-agent-library` skill, which is where
someone adding `tags:` to a skill is reading. Adding a *new* tag to a prompt means teaching
that vocabulary there in the same change; a tag no skill declares silently matches nothing.

## Layout

**One directory per machine.** A workflow is a graph plus the sub-graphs it hands off to,
and each of those is a state machine with nodes of its own. The layout says so: a machine's
`flow.py` and the nodes only that machine calls are one directory, and nothing else is.

```
src/workhorse_workflows/
  kit/            shared workflow-side helpers (git.py, github.py, workspace.py)
  <workflow>/
    workflow.py   the main machine — one Workflow subclass, `main`, nothing else
    nodes/        the callables only workflow.py calls, one module per subject
    <flow>/       one directory per sub-graph, named for the flow:
      flow.py       its Workflow subclass, reached by handoff() or run directly
      nodes.py      the callables only this flow calls  (→ nodes/ when it grows)
    shared/       what a second machine also reaches:
      blueprint.py  the one Blueprint every node in the workflow registers on
      paths.py      the only caller of `ostler.path`: doc dirs + this workflow's filenames
      schemas.py    agent-reply schemas and node return types  (→ schemas/ when it grows)
      stubs.py      the --dry-run stand-ins
      <subject>.py  a node module more than one machine calls
    prompts/      the agent-facing markdown, rendered by a filesystem template loader

tests/<workflow>/  outside src/ and outside the wheel; mirrors the tree above —
                   tests/<workflow>/<flow>/test_flow.py, plus one test_workflow.py
```

**What goes in `shared/` is a count, not a judgement.** Every module belongs to the machine
that calls it; a module a *second* machine also calls moves to `shared/`, and the move is
mechanical enough to check by grep. That is what keeps `coder/qa/nodes/evidence.py` beside
the QA flow (one caller) while `coder/shared/story.py` is shared (seven), and why a shared
node module keeps the name of its **subject** rather than of the flow that reads it most —
naming one of two callers is the mirroring this layout undoes.

A workflow with no sub-flows has no `shared/` and no `<flow>/`: with one machine there is
nothing to share, which is why `research/` is `workflow.py` + `nodes/` + a `scaffold/`
package and nothing more.

Prompts stay at the workflow root even though flows have directories of their own, because
`handoff` subscopes only the run *writer*, not the environment: a sub-flow's prompt path
resolves against the **parent** package directory.

Imports point one way: `workflow.py` imports `nodes/`, each `<flow>/` and `shared/`; a
`<flow>/` imports its own nodes and `shared/`; nothing under either imports `workflow.py`,
and nothing in `shared/` imports a flow.

How small each of those files has to be is **normative, not per-workflow taste** — one
subject per module, `nodes/` is a package even when it holds three functions, and
`~400 lines` is the trigger to apply the rule. This README is where that rule is stated;
the argument behind it is "One workflow, several files" in the
[retired design brief](../docs/plans/workflow-as-python-state-machine.md).
`coder`'s nodes alone run to ~6,600 lines across 18
modules, and a single `nodes.py` at that size is `scriptutil.py` again.

## Status

All four workflows are ported and resolve through the entry-point group; the YAML engine
they came from is retired, so this package is the only place a stablemate workflow lives.

What is still outstanding: this distribution is unpublished, so there is no `pip install`
route to it and a `pipx` layout needs `pipx inject workhorse-agent <this distribution>`
to land it in the engine's venv. Farrier also still validates a `workflows:` selection
against a `workflows/<name>/` directory in a library layer rather than against the entry
points — see the end of
[farrier/docs/LAYOUT.md](../farrier/docs/LAYOUT.md).

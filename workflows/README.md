# workhorse-workflows

The stablemate agent workflows as an installable Python distribution: `hello-world`,
`research`, `author`, `okf-builder` and `coder`, each a checkpointed state machine.
Workhorse is the engine; this is its content.

Install it from [PyPI](https://pypi.org/project/workhorse-workflows/) — the engine and
the tools its workflows import arrive as ordinary dependencies, in the *same*
interpreter, because a workflow runs in workhorse's own process:

```bash
uv tool install workhorse-workflows    # or: pipx install workhorse-workflows
workhorse-hello-world run --dry-run    # the install check; needs no agent CLI
```

Working on the workflows themselves wants a checkout of the
[stablemate](https://github.com/GabrielCpp/stablemate) workspace instead —
`make sync` at the workspace root lands engine and workflows in one venv, and
`uv run workhorse-research run` reaches the same commands from source.

The shape came from an internal workflow-as-python-state-machine design brief, which
shipped and is now kept only for its reasoning.

## The workflows

- **`hello-world`** — two states, one agent turn; the install check and the smallest
  example to copy when [shipping your own](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/AUTHORING.md#shipping-your-own-outside-this-repo).
- **`author`** — turns product intent into the repo's OKF book: epics, stories with
  acceptance criteria, seeds and coverage, as a normalized docs graph ostler validates.
  What it writes is what `coder`'s QA later holds the running app to.
- **`coder`** — implements stories from that book, then examines each one from three
  independent evidence bases — tests against the story's intent, review against the
  skills' engineering standards, QA of the live app against the book with the code not
  in the room. The reasoning is in the workspace README's
  [methodology section](https://github.com/GabrielCpp/stablemate#the-methodology-three-evidence-bases-none-of-them-the-implementers).
- **`okf-builder`** — backfills an OKF book for an existing codebase, grounding every
  claim in the file it read it from, so a brownfield repo can reach the same contract.
- **`research`** — runs experiment gates: a protocol is designed, made runnable,
  submitted as a detached measurement job, waited on across resumes, and its artifacts
  classified deterministically — for measurements an agent turn is the wrong container
  for.

Use `since` to narrow reconciliation to source changed since a revision. `story` no longer
selects a build mode; when supplied, it is retained as provenance on the completed book's
commit:

```bash
workhorse-okf-builder run --params '{
  "docs_path": "/workspace/product-docs",
  "service": "billing",
  "story": "TEAM-123",
  "source_path": "billing",
  "since": "main"
}'
```

Omit `story` for a bulk book commit with no `Story:` trailer.

## Authoring authority

Author is allowed to define previously unspecified behavior when the epic and story put that
behavior in scope. Explicit, observable Acceptance Criteria become the authority for those new
choices; the independent audit checks consistency, verifiability, existing documented behavior,
and scope rather than demanding that a greenfield detail already exist in the OKF book. A conflict
with an existing source or a required scope expansion still goes to the operator.

Epic authoring consumes one explicitly named approved roadmap and produces exactly one milestone:

```bash
workhorse-author run --params '{
  "roadmap": "docs/roadmaps/account-access.md"
}'
```

The roadmap path is the milestone's durable source identity. Author preserves the roadmap, writes
ordered epics and vertical stories, and changes `status: approved` to `status: authored` only after
the complete planning graph validates. Survey modes stop after discovery; they do not bypass roadmap
approval by decomposing their generated backlog.

## Editing authored scope

The author command exposes two standalone edit flows. `epic-edit` is the reconciliation
machine; `story-edit` validates a story-level request and hands a typed binding intent to it.
Adding or removing a story therefore cannot leave the parent epic's user journeys, seeds or
coverage describing the product before the requested change.

```bash
workhorse-author run epic-edit --params '{
  "epic": "docs-app-editor",
  "change": "Replace the interactive editor with raw XML editing",
  "force": true
}'

workhorse-author run story-edit --params '{
  "action": "add",
  "epic": "docs-app-editor",
  "bullet": "RAW-XML-EDITOR",
  "reason": "Add raw XML editing alongside the interactive editor"
}'

workhorse-author run story-edit --params '{
  "action": "remove",
  "story": "interactive-only-editor",
  "reason": "The revised journey replaces this story"
}'
```

Story removal refuses work beyond `Not started` unless `"force": true` is explicit. A plan
also needs force to remove any story or seed beyond the scope implied by that story request;
frozen scope must be explicitly unfrozen first. Direct `epic-edit` accepts the same force
parameter for destructive reconciliation. The edit planner is read-only and returns a typed
replacement plan. Deterministic checks project that plan before any write, then feed coded
findings back to the plan refiner: every active seed remains covered, dependencies remain local
and acyclic, the requested add/remove is satisfied, and every changed story needing new prose is
in the affected worklist. Only then does Ostler apply structural mutations, the model revise epic
prose and affected story bodies, and coverage/integrity gates permit backlog pruning and commit.
Design turns may write `mockup.html` only inside the current story directory. The feature book is
read-only: author never creates an inventory or registers a mockup outside its story.

Removing the last story does not silently strand scope. Its plan must also remove the last
seeds; once both resulting sets are empty, the epic and its milestone/queue references
are deleted. The complete behavior is recorded in the [epic edit](https://github.com/GabrielCpp/stablemate/blob/main/docs/features/workflows/flows/author-epic-edit.md)
and [story edit](https://github.com/GabrielCpp/stablemate/blob/main/docs/features/workflows/flows/author-story-edit.md)
flows.

## Coder documentation convergence

Coder documents a story after implementation and review, before QA. A clean QA pass then
commits without repeating that agent flow. Any QA state that may edit code, setup, or OKF
grounding sets a checkpointed `docs_recheck_required` taint; the nested backlog-fix drain
sets the same taint. Tainted stories must pass Docs again before commit.

The taint is monotonic and defaults to required when checkpoint or QA state lacks it, so
missing state never authorizes publishing stale documentation. If the required recheck is
blocked, epic mode records a docs-blocked marker and moves on without the normal story
commit; story mode fails because there is no queue in which to contain the block.

## How a workflow gets a command

Each workflow binds one, and that is the only way it is reached:

```toml
[project.scripts]
workhorse-research = "workhorse_workflows.research.workflow:main"
```

The script points at `main` — the callable `console_script(workflow.entry_point(Entry))`
*returns*, since a script target is called after import, not during it. `entry_point`
declares which flow a bare run starts and returns the registry; `console_script` — which
lives in `workhorse.cli`, the ring a console script actually starts — turns it into that
callable.

Nothing resolves a workflow by **name**: the command carries the `Registry` it runs, so
there is no lookup to disagree with, no group to register in, and a workflow with no row
in this table has no command at all — a gap you meet at install time rather than
mid-resolution. Workhorse itself ships no executable.

Nothing here is a plugin API for workhorse either. A third party ships their own
distribution with their own scripts, and the engine still knows no workflow's
vocabulary — this package imports the engine and never the other way.

## Installed unpacked, always

Workhorse renders a workflow's prompts with a filesystem template loader rooted at the
workflow's own package directory, and keys per-node overrides on that directory's
name. A wheel installed by pip or uv satisfies this; a zipapp or zip-safe egg does
not, and workhorse refuses one at startup rather than failing later as a missing
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
this package: `workhorse/cli/run.py` and `workhorse/supervisor.py` translate `$FOO` into
`--params` once, on the way in. That is why `repo_dir` reaches every workflow without any
of them reading `AGENT_REPO_DIR`.

Ambient *paths* — `repo_dir`, `docs_path`, `workspace_file` — are wanted by roughly every
second node and chosen by no state. They are fields, and `Workflow.injects` (see `coder/shared/paths.AMBIENT`)
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
`_author-context.md`, `<gate>-context.md`, `attempts.md` — joined onto
a directory ostler resolved. Run artifacts that are not documents at all (`.agents/operator`,
`.agents/okf-build`, the surveyor's `docs/survey/` scratch) stay
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
documented for skill authors in the `agent-library` skill (base-library), which is where
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
    workflow.py   the composition root — the Registry, the flow table, the console script
    main/         the machine a bare `run` starts, laid out like any other flow below
    <flow>/       one directory per sub-graph, named for the flow:
      flow.py       its Workflow subclass, reached by handoff() or run directly
      nodes.py      the callables only this flow calls  (→ nodes/ when it grows)
      prompts/      the agent-facing markdown only this flow renders
    shared/       what a second machine also reaches:
      blueprint.py  the one Blueprint every node in the workflow registers on
      paths.py      the only caller of `ostler.path`: doc dirs + this workflow's filenames
      schemas.py    agent-reply schemas and node return types  (→ schemas/ when it grows)
      stubs.py      the --dry-run stand-ins
      <subject>.py  a node module more than one machine calls

tests/<workflow>/  outside src/ and outside the wheel; mirrors the tree above —
                   tests/<workflow>/<flow>/test_flow.py, plus one test_workflow.py
```

**What goes in `shared/` is a count, not a judgement.** Every module belongs to the machine
that calls it; a module a *second* machine also calls moves to `shared/`, and the move is
mechanical enough to check by grep. That is what keeps `coder/qa/nodes/evidence.py` beside
the QA flow (one caller) while `coder/shared/story.py` is shared (seven), and why a shared
node module keeps the name of its **subject** rather than of the flow that reads it most —
naming one of two callers is the mirroring this layout undoes.

**A prompt belongs to the flow that renders it**, and a prompt two flows both render is
**two files**, one per flow, each free to diverge — nothing checks that copies stay
identical. That is why `workflow.py` declares `Registry(name, package=__package__)`: the
package directory is the template root, so a path is written from there down
(`dev/prompts/implement-plan.md`) and every flow's prompts stay inside the one loader. Were
the root inferred from the entry class instead, moving that class into `main/` would put
every sibling flow's prompts outside it.

A workflow with no sub-flows has no `shared/` and no `<flow>/`, and keeps its `prompts/` at
the package root: with one machine there is nothing to share and nothing to disambiguate,
which is why `research/` is `workflow.py` + `nodes/` + `prompts/` + a `scaffold/` package
and nothing more.

Prompts stay at the workflow root even though flows have directories of their own, because
`handoff` subscopes only the run *writer*, not the environment: a sub-flow's prompt path
resolves against the **parent** package directory.

Imports point one way: `workflow.py` imports `nodes/`, each `<flow>/` and `shared/`; a
`<flow>/` imports its own nodes and `shared/`; nothing under either imports `workflow.py`,
and nothing in `shared/` imports a flow.

How small each of those files has to be is **normative, not per-workflow taste** — one
subject per module, `nodes/` is a package even when it holds three functions, and
`~400 lines` is the trigger to apply the rule. `coder`'s nodes alone run to ~6,600 lines across 18
modules, and a single `nodes.py` at that size is unreviewable.

## Status

Every workflow is reached through its own console script — there is no
entry-point group and no resolution by name (see
[How a workflow gets a command](#how-a-workflow-gets-a-command)). This package is the
only place a stablemate workflow lives, and the distribution is on PyPI (install line at
the top). Farrier installs skills and prompts only; it neither selects nor validates
workflows.

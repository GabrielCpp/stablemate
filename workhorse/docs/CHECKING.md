# Reading a workflow without running it — `--dry-run` and `dot`

Three things are read off a workflow's own source, so none of them can drift from it: the
skill references its prompts make, `--dry-run`'s verdict on whether the machine
is sound, and the Graphviz graph `dot` renders. This document is all three — how a
reference is declared as required or optional, what the static pass checks,
what the substituted node index covers, what a fail terminal means with and without declared
stand-ins, and how the graph is read off the states. See [README.md](../README.md) for
running a workflow for real.

## Skill references

A prompt names a skill by its library name, the folder name it has in the skill library.
The name is the same in every repo, whatever prefix farrier installed the skill under.
Three helpers render a named skill:

| Helper | Renders |
|---|---|
| `skill_link("ostler-okf")` | a Markdown link to the installed `SKILL.md` |
| `skill_path("ostler-okf", "references/x.md")` | the path of the skill's file, or of `SKILL.md` with no second argument |
| `skill_command("ostler-okf")` | the line that loads the skill in the running harness: `/acme-ostler-okf` on Claude Code, `$acme-ostler-okf` on Codex, and `Read \`<path>\` and follow its instructions` elsewhere |

A turn looks a name up in the skills its harness loads. The search starts at the turn's
`cwd` and walks up to the repo root, then reads the turn's `add_dirs`, then the home
folder. `AGENT_CLI` names the harness, and the harness decides which folders count:
`.claude/skills` for Claude Code and `.agents/skills` for Codex. Added dirs count on
Claude Code only. A skill installed in the repo shadows the home copy of the same name.

A name the search does not find stops the render. The turn fails with an error naming the
skill, so a prompt never reaches an agent with a hole where the skill should be. Before the
first state, workhorse parses the workflow's `prompts/**/*.md`, checks every constant name
against the catalog the run's workspace loads, and prints the ones that will not resolve.
The fix is to install the skill in the repo or at home with `farrier install`. It is a
warning on a real run, because a turn with its own `cwd` may load skills the workspace does
not. `--dry-run` turns it into an exit code. A name built from a computed argument cannot
be seen statically, so only its render catches it.

A prompt that enumerates the skills for every stack a workflow has ever met is naming a
menu, not a dependency. A Go repo must not be told to read a Flutter skill, and must not
fail for not having one. Two helpers ask for a skill without demanding it:

```jinja
{# by capability: whichever skills carry ALL of these tags, whatever they are called #}
{%- set web_tests = find_by_tags("web", "tests") %}
{%- if web_tests %}
- How this repo writes web tests: {{ web_tests }}
{%- endif %}

{# or guard a branch on one skill #}
{% if has_skill("flutter") %}{{ skill_link("flutter-testing") }}{% endif %}
```

`find_by_tags(...)` takes tags, not names. A skill matches when its `metadata.tags` carry
every tag asked for, so a second tag narrows. It renders the matches as links, sorted, and
returns the empty string when nothing matches. Its arguments are never findings, because
they name a capability and "absent" is an answer. A named reference inside a `has_skill`
branch is not a finding either. The branch's `{% else %}` and `{% elif %}` are judged on
their own, since they render when the guard did not hold.

The helpers of the old manifest model (`instruction_ref`, `prompt_ref`, `skill_load_ref`,
`skill_dir`, `isUsingInstruction` and their siblings) are retired. The sweep reports every
call to one, and a render that reaches one fails with the name of its replacement.

## `--dry-run`: checking a workflow before you run it

`--dry-run` checks a workflow and exits without running a node — `0` when it is
clean, `1` on the first problem, so CI can read it. The failure it exists to catch
is a typo found at hour 30 of an unattended run.

```bash
workhorse-research run --dry-run
```

It turns the reference warning above into an exit code, and then does two complementary
things.
First a **static pass** over the states' own source (the same reading `dot` uses):
every prompt path a state renders must exist, every state must be reachable from the
start state, at least one state must be able to return `Done`, and no transition may
name something that is not a state. A prompt argument the source cannot name is itself a
problem: a bare string is one path and a ternary of strings is each of its arms. A
module constant is its value. A subscript of a module mapping of strings is the value a
constant key names, or every value when the key is computed. That last form lets a state
dispatch the same table entry it sized the turn from. Anything else (a local variable, an
f-string) is reported, because a path this pass cannot read is a path nothing checks. A turn written inline is checked further than a file one is:
its labels must be unique within the flow, since two turns sharing one would share a run
directory, and its text must parse as Jinja, which no dry run of a file prompt ever
proves. Then it **drives the machine for real** over a
*substituted node index*, which covers what only running can — imports, `setup()`, and
the transitions actually bound along one path. The static half is the one that carries
the weight: it sees the branches this run would never take.

Nothing branches on "is this a dry run" inside the driver. The run is handed a copy of
the registry's node index with every node's body replaced by its stand-in, so `self.call`
runs the same code path it always does — see
[The node index is the substitution seam](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/AUTHORING.md#the-node-index-is-the-substitution-seam).
A node's stand-in is whatever `@blueprint.node(stub=…)` declared, or a blank instance of
its declared return type. An agent turn's stand-in comes from the first of three places
that has one: the entry `Registry.stub_agents({...})` declared for that prompt stem or
inline label, then the reply its return model declared with `@dry_run(...)`, then a blank
reply model. A `@dry_run` declaration belongs to the model it decorates, so a subclass
does not inherit it. The decorator validates the reply against the model when the module
imports, so a declaration fails loudly even for a turn no dry run reaches.

**What a fail terminal means depends on whether the workflow declared any stand-ins.**
Undeclared, every reply is blank, so the machine takes whichever branch a blank selects
— and for any workflow with a reachable `raise WorkflowFailed` that can be the failing
one, which would mean no such workflow could ever dry-run green. So a dry run prints
which state halted and why, marks the run dir `fail`, and still exits `0`. A workflow
that calls `stub_agents({...})`, or whose package holds a `@dry_run` model, or whose run
answered a turn from one, has *said* what the happy path answers, so reaching a fail terminal anyway is a real
finding and exits `1`. Every other deliberate failure (a
dead state, a bad checkpoint parameter, an exhausted transition budget) exits `1` either
way.

A dry run writes its artifacts to a run dir named `dry-run` and clears it first, so
it can never resume — or overwrite — the checkpoint of a real week-long run. Each seam
it entered is marked in `events.jsonl` with which stand-in answered it —
`"stub": "declared"` for one the workflow supplied, `"blank"` for the default empty
model — which is how you tell a path the workflow *meant* from one a blank reply picked.

## `dot`: diagramming a workflow (`workhorse-<name> dot`)

`dot` renders a workflow to [Graphviz](https://graphviz.org) DOT straight
from the workflow, so the diagram never drifts from it.

```bash
workhorse-coder dot                         # DOT to stdout
workhorse-coder dot -o wf.dot               # ...to a file
dot -Tsvg wf.dot -o wf.svg                  # render (needs graphviz)
```

A workflow is rendered from its states, one dashed cluster per flow, each with its own
`START` (green circle) and `END` (gold double circle). A state is a rounded blue box
holding one bubble per step its body runs, top to bottom in source order:

| Bubble | What it is | Caption |
|---|---|---|
| white box | a node call (`self.call(node, …)`) | the node's file, then the first line of its docstring |
| yellow note | an agent turn (`self.agent("prompts/x.md", …)`) | the prompt file, then its `#` title (a leading `<workflow> — ` is trimmed) |
| yellow note | an inline turn (`self.agent(text, label="fix-findings", …)`) | the label, then the body's own `#` title |
| plum box | a handoff (`self.handoff(Child, …)`) | `handoff → <child flow>` |

A handoff is a bubble, never an arrow across the page: the child flow stands as its own
cluster with its own `START` and `END`, and the colour is the link. A state that runs
nothing is the plain box it always was.

Edges are the transitions. `Done` is one transition among the others — an edge into the
flow's `END`, coloured gold — never a colour on the state, because a state that can end on
one branch still continues on another. An `Await` is dashed orange. The edge label is the
transition's `.because("…")` reason when the author wrote one; otherwise it lists the
parameters the transition binds. A state nothing reaches, an opaque state, or a dangling
target is coral, since the same walk already found it as a defect. The graph is read off
the states' source, so both arms of an `if` appear (it over-approximates) and it cannot
drift from the code. A state that factors a repeated turn into a private helper keeps
its annotations: `self._helper(...)` is followed into the class's own underscore
methods, and what it finds is attributed to the state that called it — the helper is
not a node. Aliases are never drawn as a second state.

What the diagram reads is what the author already wrote, so a legible diagram is a
matter of three habits, spelled out in
[AUTHORING.md](AUTHORING.md#what-the-diagram-reads-off-a-state): a one-line docstring on
every node, a `#` title on every prompt, a `.because()` on every transition.

| Flag | Purpose |
|---|---|
| `--name <id>` | Override the `digraph` identifier (default: sanitized workflow name) |
| `-o, --output <path>` | Write to a file instead of stdout |

There is no flag for carving one mode out of a multi-mode workflow: a state machine's
branches are ordinary Python, so there is no declared branch variable to pin. Give the
mode its own flow if its diagram should stand alone.

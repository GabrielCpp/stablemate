# Reading a workflow without running it — `--dry-run` and `dot`

Three things are read off a workflow's own source, so none of them can drift from it: the
skill and prompt references its prompts make, `--dry-run`'s verdict on whether the machine
is sound, and the Graphviz graph `dot` renders. This document is all three — how a
reference is declared as required or optional, what the static pass checks,
what the substituted node index covers, what a fail terminal means with and without declared
stand-ins, and how the graph is read off the states. See [README.md](../README.md) for
running a workflow for real.

## Skill and prompt references

A prompt naming a skill the consuming repo never installed is the quiet failure here. A
`{{ instruction_ref("story-docs") }}` that resolves against nothing does not fail — it
renders the sentence `generated story-docs instruction file when installed` into a live
agent prompt, and the agent is left to find the skill itself. Before the first state,
workhorse parses the workflow's `prompts/**/*.md`, resolves every constant reference
against the loaded context manifest, and prints the ones that will not resolve, with the
fix (add them to the repo's `agents.yml` selection and re-run `make agent-install`). It is
a warning, not an error: the run is degraded, not impossible. A run carrying **no**
manifest at all (`hello-world`, most tests) is skipped — there, unresolved is the normal
state. References built from a computed argument can't be seen statically; those log a
`[template] ⚠` line when they render instead.

Only *required* references are reported. A prompt that enumerates the skills for every
stack a workflow has ever met is naming a menu, not a dependency — a Go repo must not be
told to read a Flutter skill, and must not fail preflight for not having one. Three ways
to say so:

```jinja
{# by capability: whichever skills carry ALL of these tags, whatever they are called #}
{%- set web_tests = find_by_tags("web", "tests") %}
{%- if web_tests %}
- How this repo writes web tests: {{ web_tests }}
{%- endif %}

{# plural: render whichever of these the repo installed, drop the rest #}
{%- set web = instruction_refs("react-router", "react-router-qa", "flutter", "pulumi") %}
{%- if web %}
- Instruction files for this layer: {{ web }}
{%- endif %}

{# or guard a whole branch on one skill #}
{% if isUsingInstruction("flutter") %}{{ instruction_ref("flutter-testing") }}{% endif %}
```

`find_by_tags(...)` takes **tags**, not names: each installed skill's `tags:` front matter
rides the manifest, and a skill matches only if it carries every tag asked for (AND — a
second tag narrows). It renders the matches the same way `instruction_refs` renders its
survivors, sorted so a regenerated manifest doesn't reshuffle the prompt, and returns the
**empty string** when nothing matches or nothing is asked. Asking is what a workflow that
ships to unknown repos can honestly do: the name of the skill teaching a subject is the
repo's business, the subject is not. Its arguments are never preflight findings either —
they name a capability, not a file, so "absent" is an answer rather than a defect.

`instruction_refs(...)` (aliases `instruction_files`/`skill_files`, and `prompt_refs`/
`prompt_files` for prompts) takes any number of names — or one list — resolves each,
renders the survivors as a backtick-quoted comma-separated list deduplicated by path, and
returns the **empty string** when none resolve, so `{% if %}` can drop the sentence rather
than leave a dangling "e.g.". Its arguments are never preflight findings, and neither are
references inside an `isUsingInstruction` branch (its `{% else %}` and `{% elif %}` are
judged on their own, since they render precisely when the guard did not hold).

`skill_load_ref("name", fallback_path)` is the imperative one: where `instruction_ref`
yields a path for a prompt to cite, this yields the instruction that *loads* the skill in
whatever harness is running — a `/slash-command` on Claude Code, `Read \`<path>\` and
follow its instructions` elsewhere. Both spellings are derived from the one resolved
path, because farrier installs a skill under the consuming repo's prefix
(`ostler-documentation` → `<repo>-ostler-documentation`) and the registered command is
that installed name, not the one the prompt asked for. Its first argument **is** a
required reference and is preflighted like any other; the second is only where an
uninstalled skill would have lived, and is never checked.

## `--dry-run`: checking a workflow before you run it

`--dry-run` checks a workflow and exits without running a node — `0` when it is
clean, `1` on the first problem, so CI can read it. The failure it exists to catch
is a typo found at hour 30 of an unattended run.

```bash
workhorse-coder run --dry-run
```

It turns the reference warning above into an exit code, and then does two complementary
things.
First a **static pass** over the states' own source (the same reading `dot` uses):
every prompt path a state renders must exist, every state must be reachable from the
start state, at least one state must be able to return `Done`, and no transition may
name something that is not a state. Then it **drives the machine for real** over a
*substituted node index*, which covers what only running can — imports, `setup()`, and
the transitions actually bound along one path. The static half is the one that carries
the weight: it sees the branches this run would never take.

Nothing branches on "is this a dry run" inside the driver. The run is handed a copy of
the registry's node index with every node's body replaced by its stand-in, so `self.call`
runs the same code path it always does — see
[The node index is the substitution seam](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/AUTHORING.md#the-node-index-is-the-substitution-seam).
A node's stand-in is whatever `@blueprint.node(stub=…)` declared, or a blank instance of
its declared return type; an agent turn's is whatever `Registry.stub_agents({...})`
declared for that prompt stem, or a blank reply model.

**What a fail terminal means depends on whether the workflow declared any stand-ins.**
Undeclared, every reply is blank, so the machine takes whichever branch a blank selects
— and for any workflow with a reachable `raise WorkflowFailed` that can be the failing
one, which would mean no such workflow could ever dry-run green. So a dry run prints
which state halted and why, marks the run dir `fail`, and still exits `0`. A workflow
that calls `stub_agents({...})` has *said* what the happy path answers, so reaching a
fail terminal anyway is a real finding and exits `1`. Every other deliberate failure (a
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

A workflow is rendered from its states: one cluster per flow, a `box3d` green node for every state that can return
`Done`, dashed orange edges for an `Await`, coral for a state nothing reaches, and
edge labels naming the parameters each transition binds. The graph is read off the
states' source, so both arms of an `if` appear (it over-approximates) and it cannot
drift from the code. A state that factors a repeated turn into a private helper keeps
its annotations: `self._helper(...)` is followed into the class's own underscore
methods, and what it finds is attributed to the state that called it — the helper is
not a node. Aliases are never drawn as a second state.

| Flag | Purpose |
|---|---|
| `--name <id>` | Override the `digraph` identifier (default: sanitized workflow name) |
| `-o, --output <path>` | Write to a file instead of stdout |

There is no flag for carving one mode out of a multi-mode workflow: a state machine's
branches are ordinary Python, so there is no declared branch variable to pin. Give the
mode its own flow if its diagram should stand alone.

# Workflows Library

Each subdirectory is a self-contained **workflow** that can be executed by the local agent worker.

## Template Rendering: Two-Pass System

The workflow system uses **two-pass rendering** to separate install-time concerns (project configuration) from runtime concerns (workflow execution variables):

### Pass 1: Install Time (in `farrier`)

When `farrier --repo <target>` runs:

1. **Read** the source workflow from `vigilant-octo/` and project config from the target's `agents.yml`
2. **Render** template functions and conditionals using **project context only**:
   - `{{ instruction_ref("go") }}` → resolves to the target's actual Go instruction path (e.g., `./.claude/skills/acme-go/SKILL.md`)
   - `{{ template.backend_layer_name }}` → resolves to the target's backend name (e.g., "Go API")
   - `{{ isUsingInstruction('flutter') }}` → `true`/`false` based on whether Flutter is in the target's `agents.yml` skills list
   - `{{ workhorse_var('plan_path') }}` → outputs literal `{{ plan_path }}` (escaped for runtime rendering)
3. **Write** the rendered prompt to the target's `.agents/workflows/` directory

**Assumption**: At install time, only project-level facts are known. You can safely reference instruction files, layer names, and skill selections because they are declared in `agents.yml`.

### Pass 2: Runtime (in `workhorse`)

When `workhorse` executes the workflow:

1. **Load** the installed prompt from the target's `.agents/workflows/`
2. **Render** runtime variables from the workflow node's `args`:
   - `{{ plan_path }}` → filled from the node's `args.plan_path` (e.g., `"docs/specs/{{ story_slug }}/plan.md"`)
   - `{{ story_slug }}` → filled from the node's `args.story_slug`
   - Custom variables from the workflow context
3. **Pass** the rendered prompt to the agent

**Assumption**: At runtime, workflow variables are available from the executing node's `args` dict. These are typically derived from previous node outputs or invocation parameters.

### Key Distinction

| Function | Where Rendered | Know What | Example |
|---|---|---|---|
| `{{ instruction_ref() }}` | Install time | Project skills | `{{ instruction_ref("go") }}` → `./.claude/skills/acme-go/SKILL.md` |
| `{{ template.* }}` | Install time | Project config values | `{{ template.backend_layer_name }}` → `"Go API"` |
| `{{ isUsingInstruction() }}` | Install time | Skill selection | `{% if isUsingInstruction('flutter') %}...{% endif %}` → rendered to include/exclude block |
| `{{ workhorse_var() }}` | Install time | Marker for runtime | `{{ workhorse_var('plan_path') }}` → outputs `{{ plan_path }}` |
| `{{ plan_path }}` | Runtime | Workflow context | `{{ plan_path }}` → filled from node `args.plan_path` |

## Anatomy of a workflow

```
<workflow-name>/
  workflow.yaml         # REQUIRED — DAG definition (see below)
  prompts/              # REQUIRED — one .md file per agent node
  scripts/              # Optional — Python scripts for script nodes
  rules/                # Optional — JSON rule files consumed by scripts
  programs/             # Optional — standalone programs called by scripts
  Dockerfile            # Optional — custom execution environment
  entrypoint.sh         # Optional — custom container entrypoint
```

### `workflow.yaml`

The `workflow.yaml` defines the DAG. Top-level keys:

| Key | Required | Description |
|---|---|---|
| `name` | yes | Unique workflow identifier (matches directory name) |
| `vars` | yes | Default input variables (overridden at invocation) |
| `start` | yes | ID of the first node to execute |
| `nodes` | yes | Ordered list of node definitions |

#### Node types

| `type` | Purpose | Required keys |
|---|---|---|
| `agent` | Call an LLM with a prompt template | `prompt`, `outputs`, `next` |
| `script` | Run a Python script | `script`, `args`, `outputs`, `next` |
| `branch` | Route to a different node based on a value | `path`, `cases`, `default` |
| `terminal` | Normal end state | — |
| `fail` | Abnormal end state (non-zero exit) | — |

#### Variable interpolation

Use `{{ var_name }}` anywhere in `args` or `path`. Nested keys from `outputs` are accessed with dot notation: `{{ discovery.next_file }}`.

### `prompts/`

One Markdown file per `agent` node. Use `{placeholder}` syntax for values injected at runtime from the node's `args`.

### `scripts/`

Script nodes are **Python only** (run with `sys.executable`). Scripts must write
**JSON to stdout** matching the shape declared in the node's `outputs`. The workflow
runtime captures stdout and merges the returned keys into the variable scope.

Example output from a script node with `outputs: [{key: validation}]`:

```json
{"validation": {"status": "ok", "word_count": 42}}
```

**External tools are libraries, not subprocesses.** A script talks to git/GitHub
through the `workhorse.scriptutil` seams (`open_repo`, `github_client`, …) and to the
OKF doc graph through the in-process `ostler` API (`from ostler import Ostler`) —
never by shelling out to `git`/`gh`/`ostler` and scraping stdout. `Ostler` returns
plain Python objects (`okf.todo()`, `okf.list("story", epic=…)`, `okf.create_story(…)`,
`okf.qa_run(…)`, …); a read raises on an unloadable graph rather than returning
`None`, which is the seam an in-process test fakes. See the
`stablemate-workhorse-scripting` skill (git/GitHub/ostler seams + testing) and
`stablemate-ostler` (the full verb→method table).

### `rules/`

Static configuration consumed by scripts. Typically JSON files describing patterns to detect, globs to scan, or thresholds to enforce. Scripts receive the path as an `args` entry.

## Reference: `hello-world`

The `hello-world` workflow is the canonical minimal example. Read it before writing a new workflow.

```
hello-world/
  workflow.yaml     # 4-node DAG: agent → script → branch → terminal
  prompts/greet.md  # Agent prompt returning { greeting: { message, word_count } }
  scripts/validate.py  # Python script returning { validation: { status, word_count } }
```

Flow:

```
greet (agent)
  └─► validate (script)
        └─► decide (branch)
              └─► done (terminal)
```

## Writing Prompts: Assumptions and Layer Awareness

### What You Can Assume at Install Time

✅ **Safe to reference directly in your prompt source:**

- Project configuration: `{{ template.backend_layer_name }}`, `{{ template.go_cli_name }}`
- Instruction file paths: `{{ instruction_ref("go") }}`, `{{ instruction_ref("flutter") }}`
- Skill membership: `{% if isUsingInstruction('flutter') %}...{% endif %}`
- Hardcoded guidance specific to the layer being invoked (no conditionals needed if the prompt itself only runs when that layer is touched)

### What You Cannot Assume: Use `workhorse_var()`

❌ **Never hardcode or guess:**

- File paths that depend on runtime variables (story slugs, epic names, branch-specific paths)
- Values that will be determined during workflow execution
- Paths to user-generated spec or QA artifacts

✅ **Instead, use `workhorse_var()` and pass via node `args`:**

Example: the `implement` node must reference the plan file, but the path depends on the story's slug (not known at install time).

**In `workflow.yaml` node definition:**
```yaml
- id: implement
  type: agent
  prompt: prompts/implement-plan.md
  args:
    story_slug: "{{ story_slug }}"
    plan_path: "docs/specs/{{ story_slug }}/plan.md"
```

**In `prompts/implement-plan.md`:**
```markdown
Implement the plan at `{{ workhorse_var('plan_path') }}`.
```

**What happens:**
- Install time: `{{ workhorse_var('plan_path') }}` → renders to `{{ plan_path }}`
- Runtime: `{{ plan_path }}` → filled from `args.plan_path` → `"docs/specs/my-story/plan.md"`

### Layer-Aware Prompts: Conditional Inclusion

When a prompt applies to multiple layers (e.g., implement, QA, review), make layer-specific sections conditional:

**Use `isUsingInstruction()` to check actual skill selection:**

```markdown
{%- if isUsingInstruction('go') %}
### Go API Implementation

1. Update OpenAPI spec
2. Implement service methods
{%- endif %}

{%- if isUsingInstruction('flutter') %}
### Flutter App Implementation

1. Regenerate Dart client
2. Implement screens
{%- endif %}

{%- if isUsingInstruction('react-router') %}
### React Web Implementation

1. Regenerate TypeScript client
2. Implement components
{%- endif %}
```

**Result:**
- Acme (Go + React): sees only Go and React sections
- Globex (Go + Flutter): sees only Go and Flutter sections
- No irrelevant guidance pollutes the agent's context

**Why this matters**: Agents should only see guidance for the layers they're actually working with. Irrelevant guidance (Flutter instructions in a Go-only project, React instructions in a Flutter-only project) creates noise and confusion.

## Repo-specific behavior goes in FLAVORS — keep the base generic

The workflows in this library are **generic and repo-agnostic**. A workflow base prompt/script must read the same whether it runs against a greenfield app, a rewrite of a legacy system, a Go service, or a Flutter app. **Do not bake one repo's specifics into the shared base.** That includes:

- repo or product names, URLs, hostnames, ports (`acme.com`, `localhost:8081`);
- one repo's situation treated as universal — e.g. assuming every run is a **rewrite / fidelity** job, has a running **legacy** site, or must capture **old-side screenshot evidence**. *Not everything is a rewrite.*
- repo-specific skill names (use `{{ instruction_ref("...") }}`, which resolves per-repo at install time — never hardcode `acme-legacy-visual-capture`);
- repo-specific required artifacts enforced in a **shared script** (a generic validator must not demand `evidence/old-*.png`).

Passing a `template.*` value through `cfg` into a prompt is fine (it's just plumbing); **branching the base's behavior on it is not** — put the branch in the flavor.

The gap-prevention defenses are **generic principles** in the base, parameterized so a greenfield repo benefits without a legacy mirror:

- **Deferral ownership** (author) — a `deferred` knowledge-record gap must name a resolvable `owner`; `validate-epic-coverage.py` fails an orphaned deferral. Generic; no oracle needed.
- **Verification setup** (author) — every story carries a `## Verification setup` section (the data/fixture/stack to render the surface) via the `repo_verification_setup` block; the coder builds those preconditions rather than QA'ing an empty surface.
- **Independent oracle at QA** (coder) — a contract-consuming surface is verified against a *real* producer, not its own fixtures. The *principle* is generic prose in `qa-story`; the concrete oracle (rewrite → legacy mirror; greenfield → a deployed/staging env; or none) is supplied per-repo, never baked in.
- **Coder→backlog edge** (coder) — separate-scope discoveries are filed to the repo backlog (`append-backlog-item.py`) so the author authors them next run; in-scope preconditions are built, not filed.

Acme-specific instantiations (the `localhost:8081` legacy mirror, `old-*.png` capture, `acme-visual-fidelity-qa`) stay in Acme flavors — they fill these generic seams, they don't live in the base.

### How flavors work (Jinja block inheritance)

A base prompt exposes named extension points:

```markdown
{% block repo_authoring_rules %}{% endblock %}
```

A consuming repo overrides them in `<repo>/.agents/flavors/<workflow>/<node>.md`:

```markdown
{% extends "prompts/write-story.md" %}
{% block repo_authoring_rules %}
## Acme: ground stories in the legacy mirror at {{ template.fidelity_source }}
...repo-specific instructions...
{% endblock %}
```

- **Presence-activated**: the flavor applies simply because the file exists in that repo — no graph change, no config flag.
- **Repo-owned, hand-authored**: `.agents/flavors/` is tracked in the consuming repo (it is NOT a generated farrier output). The shared library has no copy.
- **No graph changes**: flavors only fill prompt blocks. They cannot add/remove workflow nodes or scripts. Keep the DAG generic; if a node is genuinely useful only to one repo, make the node generic and push its repo-specific *content* into the flavor.
- **Scripts can't be flavored.** There is no block inheritance for `scripts/`. Keep validators generic; enforce repo-specific requirements in the repo's flavor *prompt* (which instructs the agent), not by special-casing the shared script.

When you find yourself writing `{% if workhorse_var('some_repo_concept') %}` with repo-specific guidance inside a base prompt, that content belongs in a flavor block instead.

## Writing Workflows: Passing Data Through the DAG

### Node Outputs and Variable Scope

Each `agent` or `script` node declares `outputs`:

```yaml
- id: plan
  type: agent
  prompt: prompts/plan-story.md
  outputs:
    - key: plan_artifacts
      description: Paths to generated plan files
  next: implement
```

The agent's response is parsed as JSON with this shape:
```json
{
  "plan_artifacts": {
    "root": "docs/specs/my-story/plan.md",
    "subplans": ["docs/specs/my-story/plan-go.md"]
  }
}
```

Subsequent nodes access this via `{{ plan_artifacts.root }}` or `{{ plan_artifacts.subplans }}` in their `args`.

### Declaring Node Arguments

To pass data to an agent's prompt, declare `args` in the workflow node:

```yaml
- id: implement
  type: agent
  prompt: prompts/implement-plan.md
  args:
    story_slug: "{{ story_slug }}"
    spec_dir: "{{ spec_dir }}"
    plan_path: "docs/specs/{{ story_slug }}/plan.md"
  next: qa
```

These become variables available in the prompt via `{{ workhorse_var('plan_path') }}` (for runtime vars) or direct reference (for known values).

## Creating a new workflow

1. Copy `coder/` as a starting point (canonical multi-layer workflow).
2. Rename the directory to match the workflow name.
3. Update `workflow.yaml`:
   - Set `name`, `vars` (invocation parameters)
   - Define nodes with explicit `args` for any runtime-dependent paths
   - Use `{{ workhorse_var('varname') }}` calls in prompts, not hardcoded paths
4. For each `agent` node, create a prompt file that:
   - Uses `{{ instruction_ref("go") }}` etc. for install-time skill references
   - Wraps layer-specific sections in `{% if isUsingInstruction('...') %}...{% endif %}`
   - Uses `{{ workhorse_var('varname') }}` for runtime-dependent values (never hardcode them)
5. For each `script` node, ensure it outputs valid JSON matching the `outputs` shape.
6. Test locally by running `farrier --check` on a target project.

## Reference Workflows

- `coder/` — multi-layer story implementation, QA, and review workflow (canonical example of layer-aware prompts and multi-pass rendering)
- `hello-world/` — minimal workflow with agent, script, and branch nodes

See `CLAUDE.md` for agent-facing authoring rules.

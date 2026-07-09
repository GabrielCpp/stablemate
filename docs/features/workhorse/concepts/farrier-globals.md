---
type: concept
slug: farrier-globals
title: _farrier_globals — Jinja helpers for library prompts
---
# _farrier_globals — Jinja helpers for library prompts

Builds the set of Jinja2 global functions that every rendered prompt/arg has access to, so a
library-resident prompt can resolve repo-specific values (which skill/prompt file backs a name,
whether a skill was selected, the active skills directory, a prior node's recorded output) without
farrier copying or rewriting the workflow's own files. Called once per render by both
[`render`](render-prompt.md) (file-based prompt rendering, with flavor-override support) and
[`render_string`](render-prompt.md#render_string-sibling) (inline args/cwd/command rendering) — the
module's other two public entry points, `workhorse/workhorse/templates.py::render` and
`::render_string` — and installed via `env.globals.update(...)` before the template is
rendered/instantiated, so every helper is visible to `{{ ... }}` expressions in the prompt body,
node `args:`, `cwd:`, and `command:` strings alike.

- code: `workhorse/workhorse/templates.py::_farrier_globals`
- verify: `workhorse/tests/test_context_manifest.py::test_instruction_ref_resolves_from_manifest`, `test_instruction_ref_unknown_returns_placeholder_not_crash`, `test_is_using_instruction_is_real_bool`

## Contract

- **Input:** `context: dict[str, Any]` — the node's render context, expected to carry the reserved
  keys a [context manifest](../context-manifest.md) sets (`_instructions`, `_prompts`,
  `_used_skills`, `_skill_dir`, `_run_dir`) — all optional, each missing/falsy key degrades to its
  empty default (`{}` / `set()` / `""`) rather than erroring; `workflow_dir: Path` — the running
  workflow's own directory, used as `skill_dir()`'s fallback.
- **Output:** a `dict[str, Callable]` of Jinja global names → functions, merged into the
  `Environment.globals` of the caller (later `env.globals.update(...)` calls, i.e. a second render
  in the same process, simply overwrite with a freshly-built dict — the helpers close over that
  particular call's `context`/`workflow_dir`, so two renders never share state).

## Globals

Each entry below is a Jinja-callable name → the closure `_farrier_globals` returns for it.

### `workhorse_var(name)`
Returns `context.get(name, "")` — a permissive read of any top-level context key, used when a
prompt wants a raw value without the `ResilientUndefined` placeholder/log side effect that a bare
`{{ name }}` reference would trigger for a missing key (see `render`'s own `Environment` setup in
`workhorse/workhorse/templates.py`).

### `get_node_output(node_id, key, default="")`
Reads a key from a **previously-run node's** `output.json` on disk, letting a prompt pull a value
the graph-walk loop hasn't (yet) merged into the live context. Algorithm:
1. If `context["_run_dir"]` is falsy, return `default` (no run directory to read from — e.g. a
   `render_string` call made outside a checkpointed run).
2. Build `<run_dir>/<node_id>/output.json` (the [`output.json` run artifact](../run-artifacts.md)
   a prior node's step wrote) and return `default` if it doesn't exist.
3. Parse the file as JSON and return `data.get(key, default)`.
4. On `JSONDecodeError` or `OSError` (partially-written or unreadable file), return `default`
   rather than raising — consistent with the runner's fail-soft posture for unattended runs.

### `skill_dir()`
Returns `context["_skill_dir"]` if set (the repo-root-relative skills directory recorded in the
[context manifest](../context-manifest.md#skill_dir)), else `str(workflow_dir)` — the running
workflow's own directory, used as a sane default for a manifest-free run (e.g. `hello-world`).

### `instruction_ref(name="")` (aliased as `instruction_file`, `skill_file`)
Returns `instructions.get(name, f"generated {name} instruction file when installed")` —
`instructions` being `context["_instructions"]`, the selected-skill-id → installed-path map from
the [context manifest](../context-manifest.md#instructions). A name absent from the map (skill not
selected, or manifest empty) degrades to the placeholder string rather than erroring, so a prompt
authored against a skill that a given repo didn't install still renders (just names the skill
generically instead of linking its real path). All three names are the *same function object* —
kept as aliases for prompts written against any of the historical names.

### `prompt_ref(name="")` (aliased as `prompt_file`)
Same shape as [`instruction_ref`](#instruction_ref-name-aliased-as-instruction_file-skill_file) but
reads `context["_prompts"]` (the [context manifest](../context-manifest.md#prompts) prompt-id →
path map) and its placeholder reads `f"generated {name} prompt when installed"`.

### `is_using_instruction(name="", *_args, **_kwargs)` (Jinja name `isUsingInstruction`)
Returns `name in used_skills`, `used_skills` being `set(context["_used_skills"] or [])` — the
[context manifest](../context-manifest.md#used_skills) selected-skill-id set. Lets a prompt
conditionally include a section only when that skill was actually installed for the repo. Accepts
and ignores extra positional/keyword arguments so a call site that also passes gating context (e.g.
a per-story layer list) doesn't raise a `TypeError`.

### `agent_cli()`
Returns `os.environ.get("AGENT_CLI", "claude").strip().lower()` — the active backend name for this
run (see [workhorse run](../workhorse.md#run)'s `--cli` flag, which sets `AGENT_CLI` before any
node renders). Read directly from the environment rather than `context`, since the backend is a
run-level (not per-node) choice.

### `skill_load_ref(skill_name, skill_path="")`
Returns the harness-native syntax for loading a skill, so one prompt works unmodified across
backends:
1. If [`agent_cli()`](#agent_cli) is `"claude"`, return `f"/{skill_name}"` — a slash-command
   invocation, since Claude Code loads skills that way.
2. Otherwise resolve a path in priority order — `instructions.get(skill_name)` (the manifest's
   real installed path, already backend-rewritten — see [context manifest's runtime
   mapping](../context-manifest.md#runtime-mapping)), else the caller-supplied `skill_path`, else
   the computed fallback `f"{skill_dir()}/{skill_name}/SKILL.md"` — and return `f"Read \`{path}\`
   and follow its instructions"`, a plain-text instruction every non-Claude backend can follow
   verbatim.

## Consuming context keys

All manifest-sourced values are read once at the top of `_farrier_globals` (not per-call), from the
reserved keys a [context manifest](../context-manifest.md) sets: `_instructions`, `_prompts`,
`_used_skills`, `_skill_dir`; `_run_dir` is read separately by
[`get_node_output`](#get_node_output-node_id-key-default) since it names a run artifact, not a
manifest field.

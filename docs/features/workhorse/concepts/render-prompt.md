---
type: concept
slug: render-prompt
title: render — file-based prompt rendering
---
# render — file-based prompt rendering

Renders an [agent node](../workflow-format.md#agent)'s `prompt:` file (a Jinja2 template on disk)
against the node's render context, first splicing in a repo-authored **flavor override**
([`_flavor_override`](#_flavor_override)) if one exists for that node. [`run_agent`](run-agent.md)
calls it once per node (`render(node.prompt, prompt_ctx, workflow_dir)`) to produce the text
persisted to the run's [`prompt.md`](../run-artifacts.md#node-idpromptmd) and sent to the agent
CLI. Every Jinja global a rendered prompt can call — [`instruction_ref`, `prompt_ref`, `skill_dir`,
`isUsingInstruction`, `agent_cli`, `skill_load_ref`, `workhorse_var`,
`get_node_output`](farrier-globals.md) — is installed into the `Environment` here via
[`_farrier_globals`](farrier-globals.md), so it shares that global set with
[`render_string`](#render_string-sibling).

- code: `workhorse/workhorse/templates.py::render`
- verify: `workhorse/tests/test_flavor_render.py::test_plain_renders_base_unchanged`,
  `test_override_fills_block_keeps_base`, `test_override_dir_without_file_for_node_is_base`,
  `test_no_repo_root_renders_base`

## Contract

- **Input:**
  - `template_path: str | Path` — the prompt file to render; either **absolute** or **relative to
    `workflow_dir`** (the two forms take different loader-search-path branches, see
    [Algorithm](#algorithm)).
  - `context: dict[str, Any]` — the node's render context (an already-`.as_dict()`'d
    [`WorkflowContext`](workflow-context.md), plus the per-node keys [`run_agent`](run-agent.md)
    merges in); passed both to Jinja's `tmpl.render(**context)` and to
    [`_farrier_globals`](farrier-globals.md#contract) for the reserved `_instructions`/`_prompts`/
    `_used_skills`/`_skill_dir`/`_run_dir` keys and to [`_flavor_override`](#_flavor_override) for
    `_node_cwd`/`_repo_root`.
  - `workflow_dir: str | Path` — the workflow's own directory; the search root for a relative
    `template_path`, and the `workflow_dir` argument forwarded to `_farrier_globals`
    (`skill_dir()`'s fallback).
- **Output:** `str` — the fully-rendered prompt text, trailing newline preserved
  (`keep_trailing_newline=True`, so a template's final `\n` survives, matching how the file reads
  on disk).
- **Raises:** propagates Jinja2's `TemplateNotFound` if `template_name` resolves to no file on any
  search path (the caller has no fallback for a missing prompt file — this is an authoring error,
  not a runtime condition to fail soft over, unlike [`ResilientUndefined`](#resilientundefined) for
  missing *variables*).

## Algorithm

1. Coerce `workflow_dir`/`template_path` to `Path`.
2. **Absolute `template_path`** — search path is `[template_path.parent]`, template name is
   `template_path.name`; no flavor lookup (an absolute path names one file directly, not a
   node-relative prompt id).
3. **Relative `template_path`** — template name is the path as given, search path starts as
   `[workflow_dir]`, then:
   1. Call [`_flavor_override(template_path, context, workflow_dir)`](#_flavor_override).
   2. If it returns a hit `(flavor_dir, node_name)`: search path becomes `[flavor_dir,
      workflow_dir]` (flavor first, so the override file itself resolves there) and template name
      becomes `node_name` — the override's `{% extends "prompts/<node>.md" %}` then finds the base
      prompt on the second search path entry.
   3. No hit: search path/template name stay as set in step 3 — the base prompt renders unchanged.
4. Build a Jinja2 `Environment(loader=FileSystemLoader(search_paths), undefined=ResilientUndefined,
   keep_trailing_newline=True)` — a **fresh environment per call**, so no globals or loader state
   leaks between renders.
5. `env.globals.update(_farrier_globals(context, workflow_dir))` — installs the farrier helpers
   (see [intro](#render--file-based-prompt-rendering)).
6. `tmpl = env.get_template(template_name)`; return `tmpl.render(**context)`.

## `_flavor_override`

Locates a repo-authored **flavor** — a same-named file a consuming repo drops at
`<repo_root>/.agents/flavors/<workflow_dir.name>/<node_name>.md` to extend a base prompt without
farrier copying or rewriting it. Presence alone activates it: no config, no selection step.

- code: `workhorse/workhorse/templates.py::_flavor_override`

**Contract:**
- **Input:** `template_path: Path` (the node's prompt path — only `.name` is used, i.e. the node
  id derives from the file name, not the full relative path); `context: dict[str, Any]`;
  `workflow_dir: Path`.
- **Algorithm:**
  1. `repo_root = context.get("_node_cwd") or context.get("_repo_root")` — an agent node with a
     declared [`cwd:`](../workflow-format.md#agent) looks its flavor up **relative to that per-node
     working directory** instead of the run's [`_repo_root`](../context-manifest.md#runtime-mapping),
     so each repo in a multi-repo workflow can carry its own flavor independent of the orchestrating
     repo. Neither key set → return `None` (no repo to look an override up against, e.g. a
     manifest-free run).
  2. `flavor_dir = Path(repo_root) / ".agents" / "flavors" / workflow_dir.name`.
  3. If `(flavor_dir / template_path.name)` is a file, return `(str(flavor_dir),
     template_path.name)`; else return `None`.
- **Output:** `tuple[str, str] | None` — `(flavor_dir, node_name)` on a hit, else `None`.

A flavor file is expected to open with `{% extends "prompts/<node>.md" %}` and fill the base's
named `{% block %}`s; with no override the base's blocks extend to nothing, so a plain base prompt
is unaffected either way.

## `render_string` (sibling)

Renders an **inline** Jinja2 template string — a node's `args:`/`cwd:`/`command:`/`env:` values, not
a prompt file — so it needs no loader or flavor lookup. Called once per rendered value by every
non-prompt render site: [`run_agent`](run-agent.md) (`cwd`, `args`, `add_dirs`),
`runner/script.py::run_script` (`args`, `cwd`, `env`), `runner/call.py` (`args`), and
`main.py::_run_flow` (a flow node's `args` crossing into the child graph's context). It shares
`ResilientUndefined` and the [farrier globals](farrier-globals.md) with `render`, but not the
flavor-override machinery — an inline string has no node-file identity (`template_path.name`) for a
flavor to key off of.

- code: `workhorse/workhorse/templates.py::render_string`
- verify: `workhorse/tests/test_templates_resilient.py::test_attribute_on_wrong_typed_value_renders_empty`,
  `test_missing_top_level_var_renders_empty`, `test_deep_chain_through_missing_renders_empty`,
  `test_valid_reference_still_renders`, `test_undefined_use_is_logged`

**Contract:**
- **Input:** `template_str: str` — the raw Jinja2 source (not a path); `context: dict[str, Any]` —
  same render context `render` takes, passed both to Jinja's `tmpl.render(**context)` and to
  [`_farrier_globals`](farrier-globals.md#contract).
- **Output:** `str` — the rendered text. No `keep_trailing_newline` (irrelevant for a one-line
  arg/cwd/command value, unlike a multi-line prompt file).
- **Raises:** none of its own — `env.from_string` never fails on a missing file (there is none);
  a malformed Jinja expression still raises `jinja2.TemplateSyntaxError`, uncaught here.

**Algorithm:**
1. Build `workflow_dir = Path(context.get("_skill_dir") or ".")` — there is no real workflow
   directory for an inline string, so `_farrier_globals`'s `skill_dir()` fallback is approximated
   from the manifest's `_skill_dir` (or `"."` if even that is absent).
2. `env = Environment(undefined=ResilientUndefined)` — a **fresh environment per call**, no
   `FileSystemLoader`.
3. `env.globals.update(_farrier_globals(context, workflow_dir))` — installs the same farrier
   helpers `render` installs (see [intro](#render--file-based-prompt-rendering)).
4. `tmpl = env.from_string(template_str)`; return `tmpl.render(**context)`.

## `ResilientUndefined`

Both `render` and `render_string` build their `Environment` with
`undefined=ResilientUndefined` — a `make_logging_undefined(logger=..., base=ChainableUndefined)`
class module-level singleton. A missing top-level variable or an attribute/index read through a
chain where an earlier link is missing/wrong-typed (`{{ qa_result.notes }}` when `qa_result` came
back as a bare string — a routine shape an upstream LLM output can take) renders as **empty**
instead of raising and aborting the run, while still logging a `[template] ⚠ …` warning to stdout
so the bad reference stays visible. This replaces Jinja's default `StrictUndefined`, which would
raise and abort a node over a single malformed template reference — inconsistent with
[workhorse's fail-soft posture](workflow.md#resilience-fail-soft) for unattended runs.


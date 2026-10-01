---
type: concept
slug: render-prompt
title: render — file-based prompt rendering
---
# render — file-based prompt rendering

Renders the prompt file an [agent turn](../formats/workflow-format.md#the-agent-turn) names (a Jinja2
template on disk) against the turn's render context, first splicing in a repo-authored **flavor
override** ([`_flavor_override`](#_flavor_override)) if one exists for that prompt.
[`AgentRunner.run`](run-agent.md) calls it once per turn
(`render(node.prompt, prompt_ctx, workflow_dir)`, `runner/ladder.py`) to produce the text persisted
to the run's [`prompt.md`](../formats/run-artifacts.md#node-idpromptmd) and sent to the agent CLI.
`_environment` installs every Jinja global a rendered prompt can call. The set comes from
[`template_globals`](template-globals.md): `workhorse_var`, `get_node_output`, `agent_cli`,
`skill_link`, `skill_path`, `skill_command`, `find_by_tags`, `has_skill`, and a raising stub for
each retired helper. [`render_string`](#render_string) installs the same set. `render_text`
renders a prompt body written inline in a state's source, through the same `_environment`.

The base and flavor rendering paths are covered by
`workhorse/tests/test_flavor_render.py::test_plain_renders_base_unchanged`,
`test_override_fills_block_keeps_base`, `test_override_dir_without_file_for_node_is_base`, and
`test_no_repo_root_renders_base`.

- code: `workhorse/workhorse/templates.py::render` @5308504a0103

## Contract

- **Input:**
  - `template_path: str | Path` — the prompt file to render; either **absolute** or **relative to
    `workflow_dir`** (the two forms take different loader-search-path branches, see
    [Algorithm](#algorithm)).
  - `context: dict[str, Any]` is the turn's render context. It holds the workflow's own
    [context](workflow-context.md) as a dict, plus the per-turn keys
    [`AgentRunner.run`](run-agent.md) merges in. The renderer passes it to Jinja's
    `tmpl.render(**context)` and to [`template_globals`](template-globals.md#contract). Three
    reserved keys decide where the skill helpers look: `_node_cwd`, `_repo_root` and
    `_node_add_dirs`. `ManifestContext.from_context` is the only reader that spells `_repo_root`.
    [`_flavor_override`](#_flavor_override) reads `_node_cwd` as a literal.
  - `workflow_dir: str | Path` is the workflow's own directory. It is the search root for a
    relative `template_path`.
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
For a **relative `template_path`**, the template name begins as the path as given and the search
path begins as `[workflow_dir]`. The renderer calls
[`_flavor_override(template_path, context, workflow_dir)`](#_flavor_override). A hit
`(flavor_dir, node_name)` changes the search path to `[flavor_dir, workflow_dir]` and the template
name to the matched candidate. Putting the flavor first resolves the override file there, while
the second entry lets its `{% extends "<flow>/prompts/<node>.md" %}` find the base prompt. Without a
hit, the initial search path and template name remain in use, rendering the base prompt unchanged.

4. Build a Jinja2 `Environment(loader=FileSystemLoader(search_paths), undefined=ResilientUndefined,
   keep_trailing_newline=True)` — a **fresh environment per call**, so no globals or loader state
   leaks between renders.
5. `_environment` calls `env.globals.update(template_globals(context))`, which installs the
   globals listed at the top of this page.
6. `tmpl = env.get_template(template_name)`; return `tmpl.render(**context)`.

## `_flavor_override`

Locates a repo-authored **flavor** — a same-named file a consuming repo drops at
`<repo_root>/.agents/flavors/<workflow_dir.name>/<prompt_file>.md` to extend a base prompt without
farrier copying or rewriting it. Presence alone activates it: no config, no selection step.

- code: `workhorse/workhorse/templates.py::_flavor_override` @5308504a0103

**Contract:**
- **Input:** `template_path: Path` (the prompt path — only `.name` is used, so a flavor is keyed by
  the prompt's **file name**, not its full relative path); `context: dict[str, Any]`;
  `workflow_dir: Path`.

The lookup proceeds as follows:

1. It derives `repo_root` from `context.get("_node_cwd")` or
   `ManifestContext.from_context(context).repo_root`. An agent turn with a declared
   [`cwd`](../formats/workflow-format.md#cwd-and-add_dirs) therefore looks its flavor up **relative to that
   per-turn working directory** instead of the run's
   [`_repo_root`](../formats/context-manifest.md#runtime-mapping), so each repo in a multi-repo workflow can
   carry its own flavor independent of the orchestrating repo. With neither value available, the
   lookup yields `None`, because there is no repo to look an override up in.
2. It derives `flavor_dir` as
   `Path(repo_root) / ".agents" / "flavors" / workflow_dir.name`.
3. It considers two candidates, the **path-keyed** one first — `<flow>/<name>.md`, mirroring the
   prompt's own directory (`dev/implement-plan.md` for `dev/prompts/implement-plan.md`) — and then
   `<name>.md` by basename alone. The result is `(str(flavor_dir), <candidate>)` for the first
   candidate that is a file, or `None` when neither candidate is a file.
- **Output:** `tuple[str, str] | None` — `(flavor_dir, template_name)` on a hit, else `None`.

The path-keyed location exists because a workflow whose flows each own their prompts has several
files called `implement-plan.md`, one per flow, and the basename cannot tell them apart: one
flavor would activate on all of them while its `{% extends %}` names a single base. The basename
location stays and stays working — it is what every repo that already ships a flavor wrote — it is
simply the broader match.

A flavor file is expected to open with `{% extends "<flow>/prompts/<name>.md" %}` — the base's own
path from the workflow root down — and fill the base's named `{% block %}`s; with no override the
base's blocks extend to nothing, so a plain base prompt is unaffected either way.

## `render_string`

Renders an **inline** Jinja2 template string — a turn's `cwd`/`args`/`add_dirs` values, not a prompt
file — so it needs no loader or flavor lookup. [`AgentRunner.run`](run-agent.md) is now its only
caller (`runner/ladder.py`), once per value: `node.cwd`, each entry of `node.args`, and `add_dirs`
(a bare string or each element of a list). It shares `ResilientUndefined` and the
[template globals](template-globals.md) with `render`. It does not share the flavor override,
because an inline string has no file name for a flavor to key off.

The script/call/flow render sites this page used to list are gone with the YAML front-end: a state
that needs a value computed calls a Python function and passes it, so there is no string to render.

- code: `workhorse/workhorse/templates.py::render_string` @5308504a0103
- verify: `workhorse/tests/test_templates_resilient.py::test_attribute_on_wrong_typed_value_renders_empty`,
  `test_missing_top_level_var_renders_empty`, `test_deep_chain_through_missing_renders_empty`,
  `test_valid_reference_still_renders`, `test_undefined_use_is_logged`

**Contract:**
- **Input:** `template_str: str` is the raw Jinja2 source, not a path. `context: dict[str, Any]`
  is the same render context `render` takes. The function passes it to Jinja's
  `tmpl.render(**context)` and to [`template_globals`](template-globals.md#contract).
  `quiet: bool = False` is keyword-only and is described below.
- **Output:** `str` — the rendered text. No `keep_trailing_newline` (irrelevant for a one-line
  arg/cwd value, unlike a multi-line prompt file).

Template parsing is delegated to `env.from_string`, with no file lookup involved and no exception
handling around it. A malformed Jinja expression consequently surfaces Jinja's
`TemplateSyntaxError` directly.

**Algorithm:**
1. `env = Environment(undefined=ChainableUndefined if quiet else ResilientUndefined)` — a **fresh
   environment per call**, no `FileSystemLoader`.
2. `env.globals.update(template_globals(context, quiet=quiet))` installs the same globals
   `render` installs.
3. `tmpl = env.from_string(template_str)`; return `tmpl.render(**context)`.

`quiet=True` swaps `ResilientUndefined` for a plain `ChainableUndefined`, so a missing variable
still renders empty but logs no `[template] ⚠ …` warning. It also makes a skill helper render
`generated <name> skill when installed` for a name the catalog does not hold, instead of raising
`MissingSkill`. It exists for a caller where an
unresolved reference is an *expected* state rather than a symptom, re-rendered often enough that
warning would mean thousands of lines about designed behavior. **Nothing passes it today** — the
one such caller was the YAML front-end's `labels:` block, whose Jinja strings were re-rendered
before every transition; a Python workflow declares its telemetry dimensions by overriding
`labels()` and returning a dict, which involves no template at all. The parameter is a live,
tested-by-nobody remnant of that path.

## `ResilientUndefined`

Both `render` and `render_string` build their `Environment` with
`undefined=ResilientUndefined` — a `make_logging_undefined(logger=..., base=ChainableUndefined)`
class module-level singleton. A missing top-level variable or an attribute/index read through a
chain where an earlier link is missing/wrong-typed (`{{ qa_result.notes }}` when `qa_result` came
back as a bare string — a routine shape an upstream LLM output can take) renders as **empty**
instead of raising and aborting the run, while still logging a `[template] ⚠ …` warning to stdout
so the bad reference stays visible. This replaces Jinja's default `StrictUndefined`, which would
raise and abort a node over a single malformed template reference — inconsistent with
[workhorse's fail-soft posture](run-agent.md) for unattended runs.

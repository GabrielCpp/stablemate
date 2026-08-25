---
type: concept
slug: render-prompt
title: render — file-based prompt rendering
---
# render — file-based prompt rendering

Renders the prompt file an [agent turn](../workflow-format.md#the-agent-turn) names (a Jinja2
template on disk) against the turn's render context, first splicing in a repo-authored **flavor
override** ([`_flavor_override`](#_flavor_override)) if one exists for that prompt.
[`AgentRunner.run`](run-agent.md) calls it once per turn
(`render(node.prompt, prompt_ctx, workflow_dir)`, `runner/ladder.py`) to produce the text persisted
to the run's [`prompt.md`](../run-artifacts.md#node-idpromptmd) and sent to the agent CLI. Every
Jinja global a rendered prompt can call — [`instruction_ref`, `prompt_ref`, `skill_dir`,
`isUsingInstruction`, `agent_cli`, `skill_load_ref`, `workhorse_var`,
`get_node_output`](farrier-globals.md) — is installed into the `Environment` here via
[`_farrier_globals`](farrier-globals.md), so it shares that global set with
[`render_string`](#render_string).

- code: `workhorse/workhorse/templates.py::render`
- verify: `workhorse/tests/test_flavor_render.py::test_plain_renders_base_unchanged`,
  `test_override_fills_block_keeps_base`, `test_override_dir_without_file_for_node_is_base`,
  `test_no_repo_root_renders_base`

## Contract

- **Input:**
  - `template_path: str | Path` — the prompt file to render; either **absolute** or **relative to
    `workflow_dir`** (the two forms take different loader-search-path branches, see
    [Algorithm](#algorithm)).
  - `context: dict[str, Any]` — the turn's render context (the workflow's own
    [context](workflow-context.md) flattened to a dict, plus the per-turn keys
    [`AgentRunner.run`](run-agent.md) merges in); passed both to Jinja's `tmpl.render(**context)`
    and to [`_farrier_globals`](farrier-globals.md#contract). The reserved `_`-prefixed half of that
    bag — `_instructions`/`_prompts`/`_used_skills`/`_skill_dir`/`_repo_root` — is read back through
    `ManifestContext.from_context`, which is the only place those key names are spelled; the one
    key read as a literal here is [`_flavor_override`](#_flavor_override)'s `_node_cwd`.
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
      becomes the matched candidate — the override's `{% extends "<flow>/prompts/<node>.md" %}`
      then finds the base prompt on the second search path entry.
   3. No hit: search path/template name stay as set in step 3 — the base prompt renders unchanged.
4. Build a Jinja2 `Environment(loader=FileSystemLoader(search_paths), undefined=ResilientUndefined,
   keep_trailing_newline=True)` — a **fresh environment per call**, so no globals or loader state
   leaks between renders.
5. `env.globals.update(_farrier_globals(context, workflow_dir))` — installs the farrier helpers
   listed at the top of this page.
6. `tmpl = env.get_template(template_name)`; return `tmpl.render(**context)`.

## `_flavor_override`

Locates a repo-authored **flavor** — a same-named file a consuming repo drops at
`<repo_root>/.agents/flavors/<workflow_dir.name>/<prompt_file>.md` to extend a base prompt without
farrier copying or rewriting it. Presence alone activates it: no config, no selection step.

- code: `workhorse/workhorse/templates.py::_flavor_override`

**Contract:**
- **Input:** `template_path: Path` (the prompt path — only `.name` is used, so a flavor is keyed by
  the prompt's **file name**, not its full relative path); `context: dict[str, Any]`;
  `workflow_dir: Path`.
- **Algorithm:**
  1. `repo_root = context.get("_node_cwd") or ManifestContext.from_context(context).repo_root` — an
     agent turn with a declared [`cwd`](../workflow-format.md#cwd-and-add_dirs) looks its flavor up
     **relative to that per-turn working directory** instead of the run's
     [`_repo_root`](../context-manifest.md#runtime-mapping), so each repo in a multi-repo workflow
     can carry its own flavor independent of the orchestrating repo. Neither available → return
     `None` (no repo to look an override up against, e.g. a manifest-free run).
  2. `flavor_dir = Path(repo_root) / ".agents" / "flavors" / workflow_dir.name`.
  3. Two candidates, the **path-keyed** one first — `<flow>/<name>.md`, mirroring the prompt's own
     directory (`dev/implement-plan.md` for `dev/prompts/implement-plan.md`), then `<name>.md` by
     basename alone. Return `(str(flavor_dir), <candidate>)` for the first that is a file; else
     `None`.
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
[farrier globals](farrier-globals.md) with `render`, but not the flavor-override machinery — an
inline string has no file identity (`template_path.name`) for a flavor to key off of.

The script/call/flow render sites this page used to list are gone with the YAML front-end: a state
that needs a value computed calls a Python function and passes it, so there is no string to render.

- code: `workhorse/workhorse/templates.py::render_string`
- verify: `workhorse/tests/test_templates_resilient.py::test_attribute_on_wrong_typed_value_renders_empty`,
  `test_missing_top_level_var_renders_empty`, `test_deep_chain_through_missing_renders_empty`,
  `test_valid_reference_still_renders`, `test_undefined_use_is_logged`

**Contract:**
- **Input:** `template_str: str` — the raw Jinja2 source (not a path); `context: dict[str, Any]` —
  same render context `render` takes, passed both to Jinja's `tmpl.render(**context)` and to
  [`_farrier_globals`](farrier-globals.md#contract); `quiet: bool = False` (keyword-only) — see
  below.
- **Output:** `str` — the rendered text. No `keep_trailing_newline` (irrelevant for a one-line
  arg/cwd value, unlike a multi-line prompt file).
- **Raises:** none of its own — `env.from_string` never fails on a missing file (there is none);
  a malformed Jinja expression still raises `jinja2.TemplateSyntaxError`, uncaught here.

**Algorithm:**
1. `env = Environment(undefined=ChainableUndefined if quiet else ResilientUndefined)` — a **fresh
   environment per call**, no `FileSystemLoader`.
2. Build `workflow_dir = Path(ManifestContext.from_context(context).skill_dir or ".")` — there is no
   real workflow directory for an inline string, so `_farrier_globals`'s `skill_dir()` fallback is
   approximated from the manifest's skill dir (or `"."` if even that is absent).
3. `env.globals.update(_farrier_globals(context, workflow_dir, quiet=quiet))` — installs the same
   farrier helpers `render` installs.
4. `tmpl = env.from_string(template_str)`; return `tmpl.render(**context)`.

`quiet=True` swaps `ResilientUndefined` for a plain `ChainableUndefined`, so a missing variable
still renders empty but logs no `[template] ⚠ …` warning. It exists for a caller where an
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


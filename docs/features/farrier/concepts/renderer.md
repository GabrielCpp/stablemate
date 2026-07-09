---
type: concept
slug: renderer
title: Renderer
---
# Renderer

Turns a resolved [`agents.yml`](../agents-yml-config.md) selection (skills, prompts, scaffolds,
workflows) into the concrete `{output path: file content}` map that
[`render_expected`](../farrier.md#install) writes (or, under `--check`, diffs against disk). One
`Renderer` is constructed per `install` run; its methods each cover one class of generated output —
`render()` (skills/prompts/launcher), `render_scaffold()` (scaffold files), and
`render_local_instruction()` (`localInstructions` aggregates) are the three `render_expected` calls
directly.

- code: `farrier/farrier/install.py::Renderer`

## Construction

`Renderer(repo, prefix, repo_config, template_values, skills, prompts)`:

- `repo` — the target repo root (`Path`), the resolved `--repo`.
- `prefix` — the kebab-cased install prefix (`repo.prefix` → `repo.name` → the repo dirname; see
  [`agents.yml`'s `repo` field](../agents-yml-config.md#repo)) — prepended to every generated
  skill/prompt's public name (`public_name`).
- `repo_config` — the `agents.yml` `repo:` mapping, copied into `self.repo_context` with `name`
  defaulted to `repo.name`, `prefix` set to the resolved prefix, and `root` set to `repo`'s absolute
  posix path. This becomes the Jinja `repo.*` context every rendered skill/prompt template sees
  (`context_manifest` later re-pins `root` to `"."` for the committed manifest).
- `template_values` — the merged `template`/`vars` mapping (`collect_template_values`), exposed to
  templates as both `template.*` and `vars.*`.
- `skills` / `prompts` — the selected `Source` lists (`selected_sources` over
  `load_sources(SKILLS, "skill")` / `load_sources(PROMPTS, "prompt")`), each indexed into
  `self.skill_lookup` / `self.prompt_lookup` via `build_lookup` — keyed by dotted id, deprefixed
  public id, prefixed public name, and library-relative path (with/without `.md`/`.prompt.md`),
  dash-normalized — so the `instruction_ref`/`prompt_ref`/`skill_file`/`isUsingInstruction` template
  helpers below can resolve a reference by any of those spellings. Two sources normalizing to the
  same lookup key raise `SystemExit("Ambiguous selected source id ...")`.

## `render_templates` — the Jinja helper surface

`render_templates(content, target, from_file)` renders a skill/prompt/scaffold body with Jinja2
(`StrictUndefined` — an unresolved `template.*`/`vars.*` reference raises unless the source guards
it with `| default(...)`) if `content` contains any of a fixed token list (`instruction_file(`,
`instruction_ref(`, `skill_file(`, `prompt_file(`, `prompt_ref(`, `skill_dir(`,
`isUsingInstruction(`, `repo.`, `template.`, `vars.`); otherwise it returns `content` unchanged
(cheap skip for templates using none of these). Helpers exposed to the template:

- `instruction_ref(name)` / `instruction_file(name)` — a relative path (`relative_reference`,
  computed from `from_file`) to `name`'s rendered skill output for this render pass's `target`
  (Copilot resolves through `copilot-instruction`, i.e. `.github/instructions/*.instructions.md`,
  not the `.github/skills/` copy); falls back to `"generated <name> instruction file when
  installed"` if `name` isn't a selected skill.
- `skill_file(name)` — same resolution as `instruction_ref`, but always against the plain
  `skill_output_path(name, target)` (Copilot resolves to `.github/skills/`, not the instructions
  copy).
- `prompt_ref(name)` / `prompt_file(name)` — a relative path to `name`'s rendered prompt output for
  `target`; same "generated ... when installed" fallback if unselected.
- `skill_dir()` — a relative path to this `target`'s skill directory (`skill_dir_path`).
- `isUsingInstruction(name)` — `True` iff `name` is a selected skill (for `{% if %}` gating).
- `workhorse_var(name)` — emits `{{ name }}` literally, i.e. a *workhorse* template placeholder
  passed through unrendered by farrier's own Jinja pass, so workhorse can substitute it at workflow
  run time (e.g. `{{ workhorse_var('plan_path') }}` → `{{ plan_path }}` in the installed file).
- `repo` / `template` / `vars` — the construction-time contexts above (`vars` and `template` are the
  same merged mapping under two names).
- `target` — the render target string (`"claude"` / `"codex"` / `"copilot"` / `"scaffold"`).

- code: `farrier/farrier/install.py::Renderer.render_templates`

## Skill and prompt output paths

`skill_output_path(name, target)` / `prompt_output_path(name, target)` resolve a selected skill's or
prompt's `Source` (`SystemExit("Unknown selected skill/prompt reference: <name>")` if unmatched) and
map it to its per-target generated path:

| target | skill path | prompt path |
|---|---|---|
| `claude` | `.claude/skills/<name>/SKILL.md` | `.claude/commands/<name>.md` |
| `codex` | `.agents/skills/<name>/SKILL.md` | `.agents/prompts/<name>.prompt.md` |
| `copilot` | `.github/skills/<name>/SKILL.md` | `.github/prompts/<name>.prompt.md` |
| `copilot-instruction` | `.github/instructions/<name>.instructions.md` | n/a |

`<name>` is `public_name(prefix, source)` — the resolved install `prefix` plus the source's
deprefixed public id. An unrecognized `target` string is a `SystemExit` (defensive; every call site
passes a literal from the fixed target set above).

- code: `farrier/farrier/install.py::Renderer.skill_output_path`

## `render` — the per-agent output set

`render(agents, roots, workflows, workflow_meta) -> {Path: str}` is the method `render_expected`
calls to produce almost the whole output map, gated per enabled [`agents:`
name](../agents-yml-config.md#agents):

- **`copilot`** — every selected skill via `generated_skill(source, "copilot", path)`; every
  selected prompt via a plain `render_templates` copy (no front matter rewrite, unlike Claude); and,
  per selected `roots` name whose `ROOTS/<root>.md` exists, that file's Jinja-rendered body written
  to **both** `.github/copilot-instructions.md` and `.github/agents/copilot-instructions.md`
  (missing root names are silently skipped).
- **`codex`** — every selected skill via `generated_skill(source, "codex", path)`; every selected
  prompt via a plain `render_templates` copy.
- **`claude`** — every selected skill via `generated_skill(source, "claude", path)`; every selected
  prompt via `generated_command(source, "claude", path)` (front matter + provenance, unlike
  Codex/Copilot's plain copy).
- **workflows** — validates every name in `workflows` exists under `WORKFLOWS/<name>` (`SystemExit
  ("Unknown workflow: <name>")` otherwise); workflow *content* is never copied into the repo — only
  the launcher scaffolding that points at it, at the library path, is generated:
  - `.agents/agents.mk` (`render_agents_mk`) — **always** emitted, for every install, filling
    `workflow_meta` defaults (`repo_url` → `REPLACE_ME-git-remote-url`, `branch` → `"main"`,
    `agents_dir` → `DEFAULT_AGENTS_DIR`, `repo_name` → `repo.name`) for any key `workflow_meta`
    omits.
  - when `workflows` is non-empty: one `.agents/agents-context.<assistant>.json` per **enabled**
    assistant (`context_manifest(assistant)`, JSON, sorted/indented) plus the generic
    `.agents/agents-context.json` aliased to the first enabled assistant (`"claude"` if none is
    enabled); and `.agents/local.compose.yaml` (`render_local_compose`).
  - a thin root `Makefile` (`include .agents/agents.mk`) is emitted **only if the repo has none** —
    an existing root Makefile is never overwritten; `ensure_makefile_include` wires it at install
    time instead.

- code: `farrier/farrier/install.py::Renderer.render`

### `context_manifest` — the per-repo run-time manifest

`context_manifest(target)` builds the JSON object written to the per-assistant
`agents-context.*.json` files — everything a workflow prompt running **directly from the library**
(never copied into the repo) needs to resolve `instruction_ref`/`isUsingInstruction`/`template.*`/
`skill_dir` at run time instead of at install time: `template`/`repo` (with `root` pinned to `"."`
so the committed file is machine-independent) /`vars`, `instructions` and `prompts` (every selected
skill/prompt id → its rendered output path, repo-root-relative), `used_skills` (sorted lookup keys),
and `skill_dir` (this `target`'s skill directory, repo-root-relative).

- code: `farrier/farrier/install.py::Renderer.context_manifest`

### `generated_skill` / `generated_command` — front matter + provenance

Both read `source`'s front matter and body (`split_front_matter`), Jinja-render every header value
and the body through `render_templates`, then re-emit front matter carrying the
[generated-file metadata block](../generated-file-metadata.md) (`skill_metadata_block`) that lets
[`farrier source`](../farrier.md#source) resolve the file back to its library origin:

- `generated_skill` — front matter is exactly `name` (`public_name`), `description`
  (`skill_description`: explicit header `description:`, else `"Use for <prefix> repository work
  involving <title>[. Applies to <applyTo>]"`), and the metadata block.
- `generated_command` — front matter is `description` (`command_description`: explicit header
  `description:`, else the body's first `# ` heading), any of `argument-hint`/`model`/
  `allowed-tools` the source header sets (accepting camelCase aliases), and the metadata block.
  Farrier-internal header keys (`agent`, `name`) are dropped — the command name comes from the
  filename.

- code: `farrier/farrier/install.py::Renderer.generated_skill`
- code: `farrier/farrier/install.py::Renderer.generated_command`

## `render_scaffold` / `render_local_instruction`

- `render_scaffold(source, output_path)` — a scaffold source's content, Jinja-rendered with
  `target="scaffold"` (so scaffold content can reference `repo.*`/`template.*`/`vars.*` like any
  other library source). Called once per selected scaffold, from `render_expected` directly (not
  from `render()`).
- `render_local_instruction(skill_names, target, output_path, readme_mode)` — concatenates each
  named skill's rendered body (`\n\n---\n\n`-joined) for a
  [`localInstructions`](../agents-yml-config.md#localinstructions) entry, then folds in a sibling
  `README.md` per `readme_mode`: `"none"` (or no README present) omits it; `"import"` on the
  `claude` target emits a `@README.md` directive instead of copying the body (falls back to
  inlining for non-Claude targets); otherwise the rendered README body is appended under a `##
  Local README` heading.

- code: `farrier/farrier/install.py::Renderer.render_scaffold`
- code: `farrier/farrier/install.py::Renderer.render_local_instruction`

## `validate_workflow_dependencies`

`validate_workflow_dependencies(workflow_name) -> list[str]` — not called by `render_expected`
itself; checks that every skill/prompt a workflow's prompts reference via `instruction_ref(...)`/
`prompt_ref(...)` (`extract_workflow_dependencies`, a regex scan of the workflow's `prompts/*.md`)
is among this `Renderer`'s selected skills/prompts, returning one message per missing dependency
(empty list if all satisfied). No current call site in `install.py` invokes this — it is exposed for
external tooling/tests to pre-flight a workflow selection.

- code: `farrier/farrier/install.py::Renderer.validate_workflow_dependencies`

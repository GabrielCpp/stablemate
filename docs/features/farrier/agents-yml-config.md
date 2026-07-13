---
type: format
slug: agents-yml-config
title: agents.yml (installer config)
---
# agents.yml (installer config)

The YAML mapping [`install`](farrier.md#install) reads to decide which skills, prompts, roots,
and workflows from the resolved [library directory](concepts/library-directory.md) get rendered
into a target repo's Codex/Claude/Copilot adapters, which scaffold ids
[`farrier scaffold`](farrier.md#scaffold) may apply, and how the generated launcher
(`.agents/agents.mk`, `.agents/local.compose.yaml`) is parameterized. Every top-level key is
optional except `agents:`. `read_yaml` checks the path exists first (`SystemExit("Missing config:
<path>")` if not), parses it with `yaml.safe_load` (an empty file yields `{}` rather than `None`,
so an empty `agents.yml` fails the required-`agents:` check below rather than crashing on a `None`
lookup), then raises `SystemExit("Config must be a YAML mapping: <path>")` if the parsed value
isn't a `dict` (e.g. a bare YAML list or scalar); `render_expected` then walks every key below to
compute the `{output path: content}` map `install`/`install --check` act on.

- file: `agents.yml` at the repo root (or `--config PATH`)
- code: `farrier/farrier/install.py::render_expected`

## Fields

### repo
- type: `mapping` — required: no — default: `{}`

Repository identity, merged into the Jinja `repo.*` template context every rendered skill/prompt
sees (`Renderer.repo_context`). Any key placed here (not just the two below) is copied through
and reachable as `repo.<key>` in library templates.

- `name` — type: `string` — required: no — default: the repo directory's basename
  (`repo.name` in Path terms). Also the fallback source for `prefix` when `prefix` is unset.
- `prefix` — type: `string` — required: no — default: `name`, else the repo directory's basename.
  Passed through `kebab()` and prepended to every installed skill/prompt's public name
  (`<prefix>-<skill-id>`); see `public_name`.
- `root` — always overwritten by farrier; not user-settable. Set to the repo's absolute path in
  the per-run `repo.*` template context, but pinned to `"."` in the generated context manifest
  (`Renderer.context_manifest`) so the committed adapter is machine-independent.

### agents
- type: `mapping` of `codex`/`claude`/`copilot` → `bool`, **or** a `list` of the enabled names —
  required: yes — default: none (installing errors: `"No agents selected in config"`)

Which assistant adapters to render. At least one of the three must resolve truthy
(`normalize_agents`) or `render_expected` raises `SystemExit`. Two equivalent shapes:

- mapping form — `{claude: true, codex: false, copilot: false}`; any name omitted defaults to
  `false`.
- list form — `[claude]`; equivalent to setting only the listed names `true`.

Each enabled name turns on a distinct output set in `Renderer.render`:

- `claude` — `.claude/skills/<name>/SKILL.md` (every selected skill) +
  `.claude/commands/<name>.md` (every selected prompt).
- `codex` — `.agents/skills/<name>/SKILL.md` + `.agents/prompts/<name>.prompt.md`.
- `copilot` — `.github/instructions/<name>.instructions.md`, `.github/skills/<name>/SKILL.md`,
  `.github/prompts/<name>.prompt.md`, plus rendering every selected `roots` file into
  `.github/copilot-instructions.md` and `.github/agents/copilot-instructions.md`.

[`localInstructions`](#localinstructions) only renders for `claude` (`CLAUDE.md`) and `codex`
(`AGENTS.md`/`CODEX.md`) — enabling `copilot` alone produces no local-instruction files.

### packs
- type: `list` of `string` (pack ids, `.yml` omitted) — required: no — default: `[]`

Each id names a `<id>.yml` file under the library's `packs/` directory (`PACKS / f"{pack_id}.yml"`,
`load_pack`); a missing pack raises `SystemExit("Unknown pack: <id>")` before the file is even
opened. Once found, the pack file is read through the same `read_yaml` used for `agents.yml`
itself, so a pack whose content isn't a YAML mapping fails with
`SystemExit("Config must be a YAML mapping: <path>")` too. A pack file selects
`skills`/`prompts`/`roots`/`scaffolds`/`workflows` and may itself list `includes:` (other pack ids),
merged recursively — an include cycle raises `SystemExit("Pack include cycle detected at <id>")`.
All selected packs' selections are unioned together (`collect_selection`), then unioned again with
this file's own `skills`/`prompts`/`roots`/`scaffolds`/`workflows` keys below.

### skills / prompts / roots / workflows
- type: `list` of `string` — required: no — default: `[]`

Extra individual selections **added on top of** whatever the `packs:` list pulled in (union, never
a replacement of pack-selected items). `skills`/`prompts` entries may be glob patterns; `roots`/
`workflows` entries are compared as literal names:

- `skills` — matched (`matches()`, case-insensitively, dash/dot-normalized) against a selectable
  skill's dotted id, its deprefixed public id, and its library-relative path with/without a
  trailing `.md` stripped. Selected skills are rendered per enabled agent as above.
- `prompts` — same matching, against library `prompts/` sources; suffix stripping also covers
  `.prompt.md` / `.instructions.md`.
- `roots` — literal names (no globbing); `Renderer.render` looks up `ROOTS / f"{root}.md"` and
  silently skips any name with no matching file — only consumed when `copilot` is enabled.
- `workflows` — literal workflow directory names under the library's `workflows/`; an unknown name
  raises `SystemExit("Unknown workflow: <name>")`. Workflows are never copied into the repo — they
  run directly from the library (`WORKFLOW_DIR` in the generated launcher) — but selecting >= 1
  workflow makes `install` additionally emit `.agents/agents-context*.json` and
  `.agents/local.compose.yaml`, and turns on the workflow-run targets in `.agents/agents.mk`.

### scaffolds
- type: `list` of `string` (scaffold definition ids) — required: no — default: `[]`

The catalog of scaffold ids this repo may apply with the
[`farrier scaffold <id>` command](farrier.md#scaffold), unioned with the ids contributed by
every selected pack's own `scaffolds:` list. Ids name definitions in the library's
`scaffolds/*.yml` files (parameterized file trees; see the command doc for the definition
format). **`install` renders no scaffold files** — this key only gates which ids `scaffold`
accepts. Each entry must be a plain string; the legacy `{source-prefix: dest-dir}` mapping form
from the retired install-time file-tree scaffolds raises a `SystemExit` with a migration hint
(`parse_scaffold_ids`) — placement folders are now `--param` values at invocation time.

### exclude
- type: `mapping` with optional `skills`/`prompts` keys, each a `list` of `string` glob —
  required: no — default: `{}`

Removes items the merged `packs`/top-level selections would otherwise include, applied last
(same `matches()` glob semantics) before rendering. Only these two sub-keys are read — there is
no `exclude.roots`, `exclude.workflows`, or `exclude.scaffolds`; an unwanted root or workflow
must simply not be listed, and an unwanted scaffold id is simply never invoked.

### template / vars
- type: `mapping` (arbitrary keys) — required: no — default: `{}`

Jinja2 values available to every rendered skill/prompt as `{{ template.<key> }}` / `{{ vars.<key> }}`
(both names resolve to the same merged mapping — `vars:` is the legacy spelling).
`collect_template_values` reads `vars` first, then `template`, updating the same dict in that
order — so when both tables set the same key, **`template`'s value wins**. Either table must be a
YAML mapping when present, or `render_expected` raises `SystemExit("<key> must be a YAML mapping when present")`.
Rendering uses Jinja2's `StrictUndefined`, so a library template referencing a `template.*`/`vars.*`
key that resolves to neither table raises at render time unless the library source guards it with
a Jinja `| default(...)` filter.

### localInstructions
- type: `list` of `mapping` — required: no — default: `[]`

Each entry aggregates one or more already-selected skills' bodies into a local `CLAUDE.md`/
`AGENTS.md`/`CODEX.md` file written under one or more repo directories, so the assistant
auto-loads those rules from any ancestor directory without an explicit skill invocation.

- `skill` — type: `string` — required: one of `skill`/`skills` — default: none. Names a single
  already-selected skill.
- `skills` — type: `list` of `string` — required: one of `skill`/`skills` — default: none. Names
  several already-selected skills, concatenated in list order, separated by a `\n\n---\n\n` rule.
  Takes precedence over `skill` when both are present.
- `paths` — type: `list` of `string` (repo-relative directories) — required: no (no-op if
  omitted/empty) — default: `[]`. Each path must already exist (scaffold it first — e.g.
  `farrier scaffold shared-docs`); otherwise `SystemExit("Local instruction path does not
  exist: <rel> ...")`.
- `includeReadme` — type: `enum{inline,import,none}` or `bool` — required: no — default: `inline`.
  Controls how a sibling `README.md` (in the same directory) is folded in when present:
  `inline` copies its rendered body under a `## Local README` heading; `import` emits Claude's
  `@README.md` directive instead (falls back to `inline`'s copy-in behavior for non-Claude
  targets); `none` omits it entirely. `true`/`false` are accepted as aliases for `inline`/`none`.
  Any other string raises `SystemExit`.

For each `paths` entry, output is written per **enabled** agent only for `codex` (both
`AGENTS.md` and `CODEX.md`, identical content) and `claude` (`CLAUDE.md`) — `copilot` has no
local-instruction output.

### workflow
- type: `mapping` — required: no (only meaningful when >= 1 workflow is selected) — default: `{}`

Configuration for the generated launcher (`.agents/agents.mk`, `.agents/local.compose.yaml`) and
for the selected workflow(s) at run time (`resolve_workflow_meta`). Every sub-key accepts either
camelCase or snake_case spelling.

- `repoUrl` / `repo_url` — type: `string` — required: no — default: `git remote get-url origin`
  (`get_git_remote`) if unset, else the literal placeholder `REPLACE_ME-git-remote-url`. Only used
  by GitHub-default workflow runs, not the default local bind-mount clone, so the placeholder is
  harmless until a run needs it.
- `branch` — type: `string` — required: no — default: the repo's detected trunk
  (`get_default_branch`: `origin/HEAD`'s target, else a local/origin `main`, else `master`), or the
  literal `"main"` if none of those resolve. Must be the long-lived integration branch the worker
  clones and opens/merges PRs against — **not** whatever branch `install` happened to run from.
- `agentsDir` / `agents_dir` — type: `string` — required: no — default:
  `$(abspath $(CURDIR)/../vigilant-octo/agents)` (`DEFAULT_AGENTS_DIR`). Becomes `AGENTS_DIR` in
  the generated `.agents/agents.mk`.
- `envPassthrough` / `env_passthrough` — type: `list` of `string` (env var names) — required: no —
  default: `[]`. Must be a list, else `SystemExit("workflow.envPassthrough must be a list of env
  var names")`. Each named var is forwarded into the Docker worker's `environment:` block in the
  generated `.agents/local.compose.yaml`, interpolated from the host env at `docker compose up`
  time (empty string if unset on the host).
- `githubTokenEnv` — type: `string` — required: no — default: none. **Not read anywhere in
  `farrier/farrier/install.py`** — accepted in the mapping but currently inert to farrier itself;
  it exists for the installed workflow's own runtime/prompts (workflows run directly from the
  library and are never copied into the repo) to interpret.
- `storyCoder` — type: `mapping` (opaque) — required: no — default: none. Same as
  `githubTokenEnv`: farrier does not read or validate its contents. Shape it to whatever the
  selected workflow documents; farrier passes the whole `agents.yml` through unread beyond the
  keys listed above.

## A load-valid sample

```yaml
repo:
  name: myrepo
  prefix: myrepo

agents:
  claude: true

packs:
  - go

template:
  go_module: github.com/org/myrepo

workflow:
  branch: main
  envPassthrough:
    - GH_TOKEN
```

---
type: format
slug: agents-yml-config
title: agents.yml (installer config)
---
# agents.yml (installer config)

The YAML mapping [`install`](farrier.md#install) reads to decide which skills, prompts and roots
from the resolved [library directory](concepts/library-directory.md) get rendered
into a target repo's Codex/Claude/Copilot adapters, and which scaffold ids
[`farrier scaffold`](farrier.md#scaffold) may apply. Every top-level key is
optional except `agents:`. `read_yaml` checks the path exists first (`SystemExit("Missing config:
<path>")` if not), parses it with `yaml.safe_load` (an empty file yields `{}` rather than `None`,
so an empty `agents.yml` fails the required-`agents:` check below rather than crashing on a `None`
lookup), then raises `SystemExit("Config must be a YAML mapping: <path>")` if the parsed value
isn't a `dict` (e.g. a bare YAML list or scalar); `render_expected` then walks every key below to
compute the `{output path: content}` map `install`/`install --check` act on.

- file: `agents.yml` at the repo root (or `--config PATH`)
- code: `farrier/farrier/outputs.py::render_expected`

## Fields

### repo
- type: `mapping` — required: no — default: `{}`

Repository identity, merged into the Jinja `repo.*` template context every rendered skill/prompt
sees (`Renderer.repo_context`). Any key placed here is copied through and reachable as
`repo.<key>` in library templates — *except* the three below, which farrier derives and
overwrites.

- `name` — **derived, not settable.** The repo directory's basename through `kebab()`
  (`naming.repo_prefix`). A value written here is overwritten. The same string is what the
  workflow kit keys a repo by (`kit/workspace.py::_repo_name_from_dir`), so making it
  configurable would let one repo answer to two names depending on which tool asked.
- `prefix` — **derived, not settable.** Equal to `name`, and prepended to every installed
  skill/prompt's public name (`<prefix>-<skill-id>`); see `public_name`. The former
  `repo.prefix` / `repo.name` override is gone: it made the generated file set depend on a
  config value rather than on the checkout, so the same committed `agents.yml` rendered
  different filenames in a clone under a different directory name, which `install --check`
  reports as drift with nothing to fix.
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
`skills`/`prompts`/`roots`/`scaffolds` and may itself list `includes:` (other pack ids),
merged recursively — an include cycle raises `SystemExit("Pack include cycle detected at <id>")`.
All selected packs' selections are unioned together (`collect_selection`), then unioned again with
this file's own `skills`/`prompts`/`roots`/`scaffolds` keys below.

### skills / prompts / roots
- type: `list` of `string` — required: no — default: `[]`

Extra individual selections **added on top of** whatever the `packs:` list pulled in (union, never
a replacement of pack-selected items). `skills`/`prompts` entries may be glob patterns; `roots`
entries are compared as literal names:

- `skills` — matched (`matches()`, case-insensitively, dash/dot-normalized) against a selectable
  skill's dotted id, its deprefixed public id, and its library-relative path with/without a
  trailing `.md` stripped. Selected skills are rendered per enabled agent as above.
- `prompts` — same matching, against library `prompts/` sources; suffix stripping also covers
  `.prompt.md` / `.instructions.md`.
- `roots` — literal names (no globbing); `Renderer.render` looks up `library/roots/<root>.md`
  across the layer stack and raises `SystemExit` listing every name no layer provides — only
  *rendered* when `copilot` is enabled, but validated either way.

There is no `workflows:` key. Farrier installs skills and prompts; a workflow is an installed
Python distribution that brings its own command — `pip`/`uv` installs it, and it is run as
`workhorse-<name> run`. A leftover `workflows:` list in a pack or in this file is ignored.

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
no `exclude.roots` or `exclude.scaffolds`; an unwanted root must simply not be listed, and an
unwanted scaffold id is simply never invoked.

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
- type: `mapping` — required: no — default: `{}`

An opaque pass-through block. **Farrier reads nothing in it.** It survives in `agents.yml` because
the *workflow packages* you run read their own keys out of it — so what belongs here is whatever
the workflow you installed documents. Sub-keys are conventionally accepted in either camelCase or
snake_case spelling by the workflows that read them.

- `githubTokenEnv` — type: `string` — required: no — default: none. Names the env var holding a
  GitHub token; read by the workflow kit's `resolve_github_token`, not by farrier.
- `storyCoder` — type: `mapping` (opaque) — required: no — default: none. A workflow-specific
  subtree; farrier does not read or validate its contents.

`repoUrl`, `branch`, `agentsDir` and `envPassthrough` used to live here to parameterize a generated
Docker launcher. That launcher is gone — `workhorse-<name> run` takes its arguments on the command
line —
and those keys are now ignored by everything.

## A load-valid sample

```yaml
agents:
  claude: true

packs:
  - go

template:
  go_module: github.com/org/myrepo

workflow:
  githubTokenEnv: GH_TOKEN
```

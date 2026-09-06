---
type: concept
slug: renderer
title: Renderer
---
# Renderer

Turns a resolved [`agents.yml`](../agents-yml-config.md) selection (skills, prompts, roots)
into the concrete `{output path: file content}` map that
[`render_expected`](../farrier.md#install) writes (or, under `--check`, diffs against disk). One
`Renderer` is constructed per `install` run; its methods each cover one class of generated output —
`render()` (skills/prompts/launcher) and `render_local_instruction()` (`localInstructions`
aggregates) are the two `render_expected` calls directly. (Scaffolds are no longer rendered at
install time — see the [`scaffold` command](../farrier.md#scaffold).) Its selected `Source` records
come from the [source loader](source-loader.md), which excludes a skill's bundled asset Markdown
from the top-level source set.

- code: `farrier/farrier/renderer.py::Renderer`
- detail: [renderer naming and relative output paths](naming.md)
- detail: [generated context manifest](../generated-context-manifest.md)

## Construction

`Renderer(repo, prefix, repo_config, template_values, skills, prompts, policies=None, scope="repo")`:

The `prefix` argument carries the kebab-cased repository dirname produced by
`naming.repo_prefix`; config values do not participate in deriving it. It is prepended to every
generated skill or prompt's public name (`public_name`).

- `repo` — the target repo root (`Path`), the resolved `--repo`.
- `repo_config` — the `agents.yml` `repo:` mapping, copied into `self.repo_context` with `name`
  **overwritten** with the derived prefix (assigned, not defaulted, so a leftover `repo.name` in a
  config cannot shadow it), `prefix` set to the same value, and `root` set to `repo`'s absolute
  posix path. This becomes the Jinja `repo.*` context every rendered skill/prompt template sees
  (`context_manifest` later re-pins `root` to `"."` for the committed manifest).
- `template_values` — the merged `template`/`vars` mapping (`collect_template_values`), exposed to
  templates as both `template.*` and `vars.*`.
- `skills` / `prompts` — the selected `Source` lists (`selected_sources` over
  `load_layered_sources("skill", "library", "skills")` /
  `load_layered_sources("prompt", "library", "prompts")`, so an overlay source shadows a base one
  with the same id — see [the layer stack](library-directory.md#the-layer-stack)), each indexed into
  `self.skill_lookup` / `self.prompt_lookup` via `build_lookup` — keyed by dotted id, deprefixed
  public id, prefixed public name, and library-relative path (with/without `.md`/`.prompt.md`),
  dash-normalized — so the `instruction_ref`/`prompt_ref`/`skill_file`/`isUsingInstruction` template
  helpers below can resolve a reference by any of those spellings. Two sources normalizing to the
  same lookup key raise `SystemExit("Ambiguous selected source id ...")`.
- `policies` — the complete policy source list, copied into a policy lookup without repository
  prefix fallback; policies are included only when named by `localInstructions`.
- `scope` — `repo` by default, or `user`; repository scope emits launchers and manifests, while
  user scope emits only user-harness skills and Claude prompts.

`Rendered` is the output string record used when text also needs executable, verbatim, assumed
ownership, or source-part metadata.

### method: Rendered
- sig: `Rendered(text: str, executable: bool = False, verbatim: bool = False, assumed: bool = False, sources: tuple[str, ...] = (), parts: tuple[tuple[str, str], ...] = ())`
- does: retain output text while carrying write-mode and provenance metadata
- code: `farrier/farrier/renderer.py::Rendered`
- verify: count(subject="rendered output metadata records", equals=1)

### method: __new__
- sig: `Rendered.__new__(cls, text: str, *, executable: bool = False, verbatim: bool = False, assumed: bool = False, sources: tuple[str, ...] = (), parts: tuple[tuple[str, str], ...] = ())`
- does: construct a string-compatible rendered record with the supplied metadata
- code: `farrier/farrier/renderer.py::Rendered.__new__`
- verify: count(subject="string-compatible rendered records", equals=1)

### method: local_instruction_banner
- sig: `local_instruction_banner(sources: list[Source], dest_rel: str) -> str`
- does: create a portable generated-file warning naming all aggregated library sources
- code: `farrier/farrier/renderer.py::local_instruction_banner`
- verify: visible(locator="local instruction provenance banner", text="DO NOT EDIT")

### method: asset_banner
- sig: `asset_banner(asset: Asset, dest_rel: str, overwritten_by: str = ...) -> str`
- does: create a generated-file warning for one bundled Markdown asset
- code: `farrier/farrier/renderer.py::asset_banner`
- verify: visible(locator="asset provenance banner", text="DO NOT EDIT")

### method: root_banner
- sig: `root_banner(source_rel: str, dest_rel: str) -> str`
- does: create a generated-file warning for a Copilot root instruction file
- code: `farrier/farrier/renderer.py::root_banner`
- verify: visible(locator="root instruction provenance banner", text="DO NOT EDIT")

### method: with_banner
- sig: `with_banner(text: str, banner: str) -> str`
- does: insert a banner after front matter or at the beginning of plain text
- code: `farrier/farrier/renderer.py::with_banner`
- verify: count(subject="generated texts with provenance banners", equals=1)

### method: read_asset_text
- sig: `read_asset_text(asset: Asset) -> str`
- does: read a bundled asset as UTF-8 text
- raises: `SystemExit` naming the asset when it is not UTF-8 text
- code: `farrier/farrier/renderer.py::read_asset_text`
- verify: count(subject="UTF-8 bundled asset reads", equals=1)

### method: strip_arguments_placeholder
- sig: `strip_arguments_placeholder(body: str) -> str`
- does: remove standalone `$ARGUMENTS` lines while preserving inline occurrences
- code: `farrier/farrier/renderer.py::strip_arguments_placeholder`
- verify: omits(subject="aggregated prompt body", text="$ARGUMENTS")

### method: user_harness_dir
- sig: `user_harness_dir(target: str) -> str`
- does: map a supported user-scope harness to its home-relative directory
- raises: `SystemExit` for an unknown harness
- code: `farrier/farrier/renderer.py::user_harness_dir`
- verify: count(subject="user harness directory mappings", equals=3)

## `render_templates` — the Jinja helper surface

`render_templates(content, target, from_file)` renders a skill/prompt body with Jinja2
(`StrictUndefined` — an unresolved `template.*`/`vars.*` reference raises unless the source guards
it with `| default(...)`) if `content` contains any of a fixed token list (`instruction_file(`,
`instruction_ref(`, `skill_file(`, `prompt_file(`, `prompt_ref(`, `skill_dir(`,
`isUsingInstruction(`, `find_by_tags(`, `repo.`, `template.`, `vars.`); otherwise it returns
`content` unchanged
(cheap skip for templates using none of these). Helpers exposed to the template:

- `instruction_ref(name)` / `instruction_file(name)` — a relative path (`relative_reference`,
  computed from `from_file`) to `name`'s rendered skill output for this render pass's `target`;
  falls back to `"generated <name> instruction file when installed"` if `name` isn't a
  selected skill.
- `skill_file(name)` — the same resolution as `instruction_ref`. Copilot used to be sent
  through a `copilot-instruction` pseudo-target here, so the two helpers pointed at different
  files for the same skill; the per-skill `.instructions.md` copy is no longer written, and
  every target now resolves to the one open-format skill.
- `prompt_ref(name)` / `prompt_file(name)` — a relative path to `name`'s rendered prompt output for
  `target`; same "generated ... when installed" fallback if unselected.
- `skill_dir()` — a relative path to this `target`'s skill directory (`skill_dir_path`).
- `isUsingInstruction(name)` — `True` iff `name` is a selected skill (for `{% if %}` gating).
- `find_by_tags(*tags)` — the selected skills whose front matter declares **all** of `tags`
  (`skills_with_tags` over the cached `skill_tags`), rendered as their sorted `relative_reference`
  paths, backticked and comma-joined; the empty string when the query is empty or nothing matches.
  The install-time twin of workhorse's Jinja global of the same name, and it must keep rendering the
  same shape, so one library source reads identically whether farrier rendered it into a repo or
  workhorse rendered it from the library at run time.
- `workhorse_var(name)` — emits `{{ name }}` literally, i.e. a *workhorse* template placeholder
  passed through unrendered by farrier's own Jinja pass, so workhorse can substitute it at workflow
  run time (e.g. `{{ workhorse_var('plan_path') }}` → `{{ plan_path }}` in the installed file).
- `repo` / `template` / `vars` — the construction-time contexts above (`vars` and `template` are the
  same merged mapping under two names).
- `target` — the render target string (`"claude"` / `"codex"` / `"copilot"`).

- code: `farrier/farrier/renderer.py::Renderer.render_templates`

## Skill and prompt output paths

`skill_output_path(name, target)` / `prompt_output_path(name, target)` resolve a selected skill's or
prompt's `Source` (`SystemExit("Unknown selected skill/prompt reference: <name>")` if unmatched) and
map it to its per-target generated path:

| target | skill path | prompt path |
|---|---|---|
| `claude` | `.claude/skills/<name>/SKILL.md` | `.claude/commands/<name>.md` |
| `codex` | `.agents/skills/<name>/SKILL.md` | `.agents/prompts/<name>.prompt.md` |
| `copilot` | `.github/skills/<name>/SKILL.md` | `.github/prompts/<name>.prompt.md` |

`<name>` is `public_name(prefix, source)` — the resolved install `prefix` plus the source's
deprefixed public id. An unrecognized `target` string is a `SystemExit` (defensive; every call site
passes a literal from the fixed target set above).

- code: `farrier/farrier/renderer.py::Renderer.skill_output_path`

## `render` — the per-agent output set

`render(agents, roots) -> {Path: str}` is the method `render_expected`
calls to produce almost the whole output map, gated per enabled [`agents:`
name](../agents-yml-config.md#agents):

- **`copilot`** — every selected skill via `generated_skill(source, "copilot", path)`; every
  selected prompt via a plain `render_templates` copy (no front matter rewrite, unlike Claude); and,
  per selected `roots` name resolving to `library/roots/<root>.md` in some layer
  (`find_in_layers`), that file's Jinja-rendered body written
  to **both** `.github/copilot-instructions.md` and `.github/agents/copilot-instructions.md`. A
  root name no layer provides is **not** silently skipped: `render` validates the whole `roots`
  selection up front and raises `SystemExit` with the unknown names, the layers searched, and the
  root names that do exist. (The per-root miss check remains as a guard for a directly-constructed
  `Renderer` in tests.)
- **`codex`** — every selected skill via `generated_skill(source, "codex", path)`; every selected
  prompt via a plain `render_templates` copy.
- **`claude`** — every selected skill via `generated_skill(source, "claude", path)`; every selected
  prompt via `generated_command(source, "claude", path)` (front matter + provenance, unlike
  Codex/Copilot's plain copy).
After the enabled-assistant branches, repository-scope rendering adds the launcher scaffolding.
This output is independent of which assistants are enabled. Farrier installs skills and prompts,
not workflows: a workflow is an installed Python distribution that brings its own
`workhorse-<name>` command, so there is nothing to render per workflow and the launcher's targets
regenerate and verify the adapters above.

The launcher set contains `.agents/agents.mk` (`render_agents_mk`, no arguments), carrying
`agent-install` and `agent-check`. It also contains one
`.agents/agents-context.<assistant>.json` per enabled assistant (`context_manifest(assistant)`,
JSON, sorted and indented), plus the generic `.agents/agents-context.json` aliased to the first
enabled assistant (`"claude"` if none is enabled). When the repository has no root `Makefile`, the
set additionally contains a thin one (`include .agents/agents.mk`); an existing root `Makefile` is
left intact and `ensure_makefile_include` wires it at install time instead.

- code: `farrier/farrier/renderer.py::Renderer.render`

### `context_manifest` — the per-repo run-time manifest

`context_manifest(target)` builds the JSON object written to the per-assistant
`agents-context.*.json` files — everything a workflow prompt shipped **in an installed workflow
package** (never copied into the repo) needs to resolve
`instruction_ref`/`isUsingInstruction`/`template.*`/
`skill_dir` at run time instead of at install time: `template`/`repo` (with `root` pinned to `"."`
so the committed file is machine-independent) /`vars`, `instructions` and `prompts` (every selected
skill/prompt id → its rendered output path, repo-root-relative), `instruction_tags` (the same alias
keys → each skill's declared `tags:`, omitting the skills that declare none — what workhorse's
`find_by_tags` queries), `used_skills` (sorted lookup keys), and `skill_dir` (this `target`'s skill
directory, repo-root-relative).

- code: `farrier/farrier/renderer.py::Renderer.context_manifest`

### `generated_skill` / `generated_command` — front matter + provenance

Both read `source`'s front matter and body (`split_front_matter`), Jinja-render every header value
and the body through `render_templates`, then re-emit front matter carrying the
[generated-file metadata block](../generated-file-metadata.md) (`skill_metadata_block`) that lets
[`farrier source`](../farrier.md#source) resolve the file back to its library origin:

- `generated_skill` — front matter is exactly `name` (`public_name`), `description`
  (`skill_description`: explicit header `description:`, else `"Use for <prefix> repository work
  involving <title>[. Applies to <applyTo>]"`), and the metadata block — which carries the source's
  `tags:` as a `tags:` line inside `metadata:` when it declares any, since that block is the
  agreed-ours namespace every harness's front-matter parser already ignores.
- `generated_command` — front matter is `description` (`command_description`: explicit header
  `description:`, else the body's first `# ` heading), any of `argument-hint`/`model`/
  `allowed-tools` the source header sets (accepting camelCase aliases), and the metadata block.
  Farrier-internal header keys (`agent`, `name`) are dropped — the command name comes from the
  filename.

- code: `farrier/farrier/renderer.py::Renderer.generated_skill`
- code: `farrier/farrier/renderer.py::Renderer.generated_command`

## `render_local_instruction`

 - `render_local_instruction(skill_names, target, output_path, include_readme, prompt_names,
  policy_names)` — concatenates each named source's rendered body (`\n\n---\n\n`-joined) for a
  [`localInstructions`](../agents-yml-config.md#localinstructions) entry, then folds in a sibling
  `README.md` when `include_readme` is true, appending its rendered body under a `## Local README`
  heading. The separate `render_claude_pointer` method controls whether Claude imports the sibling
  README by `@README.md` instead of receiving it through `AGENTS.md`.

- code: `farrier/farrier/renderer.py::Renderer.render_local_instruction`

## Methods

The following sections enumerate the public `Renderer` API. The renderer is a per-install
object: source lookup and output naming use its selected source lists, prefix, target repository,
template values, policies, and repo/user scope.

### method: dest_rel
- sig: `dest_rel(output_path: Path) -> str`
- does: return the output path relative to the renderer repository
- verify: count(subject="repository-relative destination path results", equals=1)
- does: prefix the relative path with `~/` for user-scope renders
- verify: count(subject="user-scope destination paths prefixed with ~/", equals=1)
- raises: `ValueError` when `output_path` is outside the renderer repository
- verify: count(subject="ValueError results for output paths outside the renderer repository", equals=1)
- code: `farrier/farrier/renderer.py::Renderer.dest_rel`

### method: skill_tags
- sig: `skill_tags(source: Source) -> list[str]`
- does: read the source front matter's normalized tags
- does: cache normalized tags by source path so repeated lookups read the source file once
- verify: count(subject="front matter reads for repeated tag lookups of the same skill source", equals=1)
- code: `farrier/farrier/renderer.py::Renderer.skill_tags`

### method: skills_with_tags
- sig: `skills_with_tags(tags: list[str]) -> list[Source]`
- does: return selected skills carrying every requested tag
- verify: count(subject="skills carrying every requested tag for a non-empty query", equals=1)
- does: preserve selected-source order for matching skills
- does: return no skills for an empty tag query
- verify: count(subject="skills returned for an empty tag query", equals=0)
- code: `farrier/farrier/renderer.py::Renderer.skills_with_tags`
- tests: `farrier/tests/test_skill_tags.py::test_skills_with_tags_is_an_and`

### method: skill_source
- sig: `skill_source(name: str) -> Source`
- does: resolve a selected skill by its normalized lookup name
- verify: count(subject="selected skill sources resolved by normalized lookup name", equals=1)
- raises: `SystemExit` naming the unknown selected skill when no source matches
- verify: count(subject="SystemExit results for unknown selected skill names", equals=1)
- code: `farrier/farrier/renderer.py::Renderer.skill_source`

### method: optional_skill_source
- sig: `optional_skill_source(name: str) -> Source | None`
- does: resolve a selected skill without raising when absent
- verify: absent(subject="optional skill lookup result for an unknown selected skill")
- does: accept dotted and dashed names and the repository-prefix fallback for an overlay skill
- verify: count(subject="dotted, dashed, and repository-prefix skill lookup resolutions", equals=3)
- code: `farrier/farrier/renderer.py::Renderer.optional_skill_source`
- tests: `farrier/tests/test_skill_lookup_prefix_fallback.py::test_generic_name_falls_back_to_repo_prefixed_skill`

### method: policy_source
- sig: `policy_source(name: str) -> Source`
- does: resolve a policy by its normalized bare name from the complete policy lookup
- verify: count(subject="policy source resolutions by normalized bare name", equals=1)
- does: reject missing policies with the available-policy catalog
- verify: count(subject="available policy catalog in unknown-policy refusal", equals=1)
- raises: `SystemExit` for an unknown policy name
- verify: count(subject="SystemExit results for unknown policy names", equals=1)
- code: `farrier/farrier/renderer.py::Renderer.policy_source`
- tests: `farrier/tests/test_policies.py::test_unknown_policy_names_the_ones_that_exist`

### method: prompt_source
- sig: `prompt_source(name: str) -> Source`
- does: resolve a selected prompt by its normalized lookup name
- verify: count(subject="selected prompt sources resolved by normalized lookup name", equals=1)
- raises: `SystemExit` naming the unknown selected prompt when no source matches
- verify: count(subject="unknown selected prompt references rejected with a named SystemExit", equals=1)
- code: `farrier/farrier/renderer.py::Renderer.prompt_source`

### method: optional_prompt_source
- sig: `optional_prompt_source(name: str) -> Source | None`
- does: resolve a selected prompt without raising when absent
- verify: count(subject="resolved prompt sources for an unknown name", equals=0)
- code: `farrier/farrier/renderer.py::Renderer.optional_prompt_source`

### method: skill_output_path
- sig: `skill_output_path(name: str, target: str) -> Path`
- does: map a selected skill to its target-specific generated `SKILL.md` path using its public name
- verify: count(subject="selected skills mapped to generated SKILL.md paths using public names", equals=1)
- does: use `.claude`, `.agents`, or `.github` repository directories for Claude, Codex, or Copilot
- verify: count(subject="repository skill output paths using Claude, Codex, and Copilot directories", equals=3)
- does: use the corresponding user harness directory when scope is `user`
- verify: count(subject="user-scope skill output paths using the corresponding harness directory", equals=1)
- raises: `SystemExit` for an unknown skill reference or render target
- verify: count(subject="SystemExit results for unknown skill references or render targets", equals=2)
- code: `farrier/farrier/renderer.py::Renderer.skill_output_path`
- tests: `farrier/tests/test_copilot_open_skills.py::test_skill_output_path_copilot_uses_open_skills_format`

### method: prompt_output_path
- sig: `prompt_output_path(name: str, target: str) -> Path`
- does: map a selected prompt to its target-specific generated prompt path using its public name
- verify: count(subject="target-specific generated prompt output paths for repository targets", equals=3)
- does: permit prompts at user scope only for Claude
- verify: count(subject="user-scope prompt output paths for non-Claude targets", equals=0)
- raises: `SystemExit` for an unknown prompt, unsupported user-scope target, or unknown target
- verify: count(subject="SystemExit results for invalid prompt output path selections", equals=3)
- code: `farrier/farrier/renderer.py::Renderer.prompt_output_path`
- tests: `farrier/tests/test_user_install.py::test_prompts_under_a_non_claude_harness_are_an_error`

### method: skill_dir_path
- sig: `skill_dir_path(target: str) -> Path`
- does: return the target's generated skill directory, using user harness paths when applicable
- verify: count(subject="generated skill directory paths resolved for repository and user scopes", equals=1)
- raises: `SystemExit` for an unknown target
- verify: count(subject="unknown skill directory targets rejected with SystemExit", equals=1)
- code: `farrier/farrier/renderer.py::Renderer.skill_dir_path`

### method: render_templates
- sig: `render_templates(content: str, target: str, from_file: Path) -> str`
- does: leave content unchanged when it contains no Farrier or Jinja helper token
- verify: unchanged(subject="content without Farrier or Jinja helper tokens")
- does: render helper calls with strict undefined handling
- verify: count(subject="rendered helper calls", equals=1)
- does: render `repo`, `template`, `vars`, and `target` values with strict undefined handling
- verify: count(subject="rendered repo, template, vars, and target values", equals=4)
- does: resolve selected skill/prompt references relative to `from_file`, or emit the documented generated-file fallback
- verify: count(subject="resolved skill and prompt references or generated-file fallbacks", equals=1)
- does: emit workhorse runtime variables as literal Jinja placeholders for later substitution
- verify: count(subject="workhorse runtime variables emitted as literal Jinja placeholders", equals=1)
- raises: `SystemExit` naming the missing template value when strict rendering finds an undefined value
- verify: count(subject="undefined template value errors naming the missing value", equals=1)
- code: `farrier/farrier/renderer.py::Renderer.render_templates`
- tests: `farrier/tests/test_skill_tags.py::test_find_by_tags_renders_the_matches_as_a_reference_list`

### method: context_manifest
- sig: `context_manifest(target: str) -> dict[str, Any]`
- does: build the runtime manifest containing template values, repo context, vars, instruction paths, instruction tags, prompt paths, used lookup keys, and target skill directory
- verify: count(subject="runtime manifest top-level fields", equals=8)
- does: pin `repo.root` to `.` so the committed manifest is independent of the install machine
- verify: json_path(path="$.repo.root", equals=".")
- code: `farrier/farrier/renderer.py::Renderer.context_manifest`
- tests: `farrier/tests/test_skill_tags.py::test_context_manifest_publishes_tags_for_every_alias`

### method: skill_description
- sig: `skill_description(source: Source, header: dict[str, str], body: str) -> str`
- does: use an explicit source description when present
- verify: count(subject="generated skill descriptions using explicit source descriptions", equals=1)
- does: otherwise derive a description from the rendered body heading and optional `applyTo` value
- verify: count(subject="generated skill descriptions derived from headings and applyTo values", equals=1)
- code: `farrier/farrier/renderer.py::Renderer.skill_description`

### method: generated_skill
- sig: `generated_skill(source: Source, target: str, output_path: Path) -> str`
- does: render a skill's front matter and body
- verify: count(subject="rendered skill front matter and body", equals=1)
- does: emit the skill's public name
- verify: count(subject="public skill name in generated front matter", equals=1)
- does: emit the skill's description
- verify: count(subject="skill description in generated front matter", equals=1)
- does: emit the skill's tags
- verify: count(subject="skill tags in generated front matter", equals=1)
- does: emit provenance metadata for the skill
- verify: count(subject="skill provenance metadata in generated front matter", equals=1)
- code: `farrier/farrier/renderer.py::Renderer.generated_skill`
- tests: `farrier/tests/test_provenance_banner.py::test_generated_skill_carries_metadata_in_front_matter`

### method: generated_assets
- sig: `generated_assets(source: Source, target: str, skill_path: Path) -> dict[Path, Rendered]`
- does: render Markdown assets beside a generated skill
- does: copy scripts or non-Markdown assets verbatim
- verify: unchanged(subject="copied scripts and non-Markdown asset contents")
- does: mark copied scripts executable
- does: mark Markdown assets with source provenance
- raises: `SystemExit` when a skill asset is requested for a flat target path or is not UTF-8 text
- code: `farrier/farrier/renderer.py::Renderer.generated_assets`
- tests: `farrier/tests/test_skill_assets.py::test_reference_installs_next_to_the_skill_under_every_adapter`

### method: command_description
- sig: `command_description(source: Source, header: dict[str, str], body: str) -> str`
- does: use an explicit prompt description or the first rendered body heading
- verify: count(subject="selected prompt description in the method result", equals=1)
- code: `farrier/farrier/renderer.py::Renderer.command_description`

### method: generated_command
- sig: `generated_command(source: Source, target: str, output_path: Path) -> str`
- does: render a Claude command with a description
- verify: count(subject="generated Claude command descriptions", equals=1)
- does: include supported optional command metadata when present
- verify: count(subject="supported optional command metadata in generated Claude front matter", equals=1)
- does: include source provenance
- verify: count(subject="source provenance in generated Claude front matter", equals=1)
- does: omit Farrier-internal `agent` and `name` headers
- verify: omits(subject="generated Claude front matter", matches="^(agent|name):")
- code: `farrier/farrier/renderer.py::Renderer.generated_command`

### method: render
- sig: `render(agents: dict[str, bool], roots: set[str]) -> dict[Path, str]`
- does: render selected skills and prompts for each enabled assistant adapter
- verify: count(subject="selected skill and prompt outputs for an enabled assistant adapter", equals=1)
- does: render selected Copilot roots into both Copilot instruction paths
- verify: count(subject="Copilot root instruction output paths", equals=2)
- does: validate every selected root even when Copilot is disabled
- verify: count(subject="selected roots validated before assistant rendering", equals=1)
- does: always emit the repository launcher and context manifest at repository scope
- verify: count(subject="repository-scope launcher and context manifest outputs", equals=1)
- does: emit a thin root Makefile only when the repository has no Makefile
- verify: count(subject="thin root Makefile outputs for repositories without a Makefile", equals=1)
- does: emit no launcher or manifest at user scope
- verify: absent(subject="user-scope launcher and context manifest outputs")
- raises: `SystemExit` listing unknown roots and searched layers
- verify: count(subject="unknown-root SystemExit messages listing roots and searched layers", equals=1)
- code: `farrier/farrier/renderer.py::Renderer.render`
- tests: `farrier/tests/test_selection_misses.py::test_unknown_root_fails_even_with_copilot_disabled`

### method: instruction_sources
- sig: `instruction_sources(skill_names: list[str], prompt_names: list[str] | None = None, policy_names: list[str] | None = None) -> list[Source]`
- does: resolve policies first, then skills, then prompts in aggregation order
- verify: json_path(path="$[0].kind", equals="policy")
- raises: `SystemExit` when a named policy, skill, or prompt cannot be resolved
- verify: count(subject="SystemExit exceptions from unresolved policy, skill, and prompt source lookups", equals=3)
- code: `farrier/farrier/renderer.py::Renderer.instruction_sources`
- tests: `farrier/tests/test_policies.py::test_policy_body_is_aggregated_before_skills_and_prompts`

### method: render_local_instruction
- sig: `render_local_instruction(skill_names: list[str], target: str, output_path: Path, include_readme: bool = True, prompt_names: list[str] | None = None, policy_names: list[str] | None = None) -> str`
- does: concatenate resolved policy, skill, and prompt bodies in order with separator rules
- verify: count(subject="resolved policy, skill, and prompt bodies in aggregation order with separators", equals=1)
- does: remove a prompt's standalone `$ARGUMENTS` line before aggregation
- verify: omits(subject="aggregated prompt body", text="$ARGUMENTS")
- does: render and append a sibling README under `## Local README` when enabled and present
- verify: count(subject="rendered sibling README under the Local README heading", equals=1)
- does: return rendered text carrying source and per-part provenance without an in-file banner
- verify: count(subject="source and per-part provenance records in returned rendered text", equals=1)
- code: `farrier/farrier/renderer.py::Renderer.render_local_instruction`
- tests: `farrier/tests/test_provenance_banner.py::test_aggregated_agents_file_carries_no_banner_at_all`

### method: render_claude_pointer
- sig: `render_claude_pointer(skill_names: list[str], output_path: Path, prompt_names: list[str] | None = None, readme_import: bool = False, policy_names: list[str] | None = None) -> str`
- does: resolve the aggregated sources and produce a Claude provenance banner followed by `@AGENTS.md`
- verify: count(subject="Claude provenance banners followed by an AGENTS.md pointer", equals=1)
- does: add `@README.md` only when the caller requests README import
- verify: count(subject="requested README imports in Claude pointers", equals=1)
- code: `farrier/farrier/renderer.py::Renderer.render_claude_pointer`
- tests: `farrier/tests/test_provenance_banner.py::test_claude_pointer_gets_the_html_comment_banner`

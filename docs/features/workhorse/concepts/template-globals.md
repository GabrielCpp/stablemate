---
type: concept
slug: template-globals
title: Template globals and skill references
---
# Template globals and skill references

A prompt author writes `{{ skill_link("story-docs") }}` and the agent reads a link to the skill
file its harness will load. The prompt names the skill by its library name, never by a path.
Workhorse finds the path when the turn renders. It looks in the folders the turn's harness loads
skills from, starting where the turn starts.

`template_globals` builds the Jinja globals every prompt and every inline value renders with.
[`render`](render-prompt.md) and `render_text` install them through `_environment`.
[`render_string`](render-prompt.md#render_string) installs them on its own environment. The set
holds three run helpers, five skill reference helpers and one stub for each retired helper. Farrier
renders a skill body with the same five skill helpers, from the same `SkillRefs` engine.

- code: `workhorse/workhorse/templates.py::template_globals` @5308504a0103
- code: `workhorse/workhorse/templates.py::skill_refs` @5308504a0103
- code: `workhorse/workhorse/templates.py::turn_catalog` @5308504a0103
- code: `workhorse/workhorse/_vendor/stablemate_core/skill_refs.py::SkillRefs` @ebf1b69c7565
- code: `workhorse/workhorse/_vendor/stablemate_core/skill_refs.py::scan_catalog` @ebf1b69c7565
- tests: `workhorse/tests/test_references.py::test_a_turn_resolves_repo_and_home_skills_from_its_cwd`, `workhorse/tests/test_references.py::test_the_harness_picks_the_invocation`, `workhorse/tests/test_references.py::test_a_turn_sees_the_skills_of_its_added_dirs`, `workhorse/tests/test_references.py::test_a_named_miss_stops_the_render`, `workhorse/tests/test_references.py::test_a_quiet_render_keeps_a_placeholder`, `workhorse/tests/test_references.py::test_a_retired_helper_names_its_replacement`

## Contract

- **Input:** `context: dict[str, Any]` is the turn's render context. `template_globals` reads four
  of its keys. `_run_dir` feeds `get_node_output`. `_node_cwd`, `_repo_root` and `_node_add_dirs`
  decide where the skill helpers look. Every key is optional. `quiet: bool = False` is
  keyword-only and decides what a named miss does.
- **Output:** a `dict[str, Any]` of Jinja global names to callables. The caller merges it into
  `Environment.globals`.

The skill helpers build their catalog on the first call, once per render. A render that calls no
skill helper never scans a folder.

## Globals

### `workhorse_var(name)`

`workhorse_var` returns `context.get(name, "")`. A prompt uses it to read a raw value without the
`[template] ⚠` warning a bare `{{ name }}` logs for a missing key.

### `get_node_output(node_id, key, default="")`

`get_node_output` reads one key from an earlier turn's
[`output.json`](../formats/run-artifacts.md) on disk.

1. It returns `default` when `context["_run_dir"]` is empty.
2. It returns `default` when `<run_dir>/<node_id>/output.json` does not exist.
3. It parses the file and returns `data.get(key, default)`.
4. It returns `default` on a JSON decode error or an OS error.

### `agent_cli()`

`agent_cli` returns `AGENT_CLI`, else the config's [`default_cli`](config.md#resolve_default_cli),
stripped and lowercased. [`workhorse-<name> run`](../workhorse.md#run) sets `AGENT_CLI` from its
`--cli` flag before any turn renders. The skill helpers read the same value to pick the harness
folders and the invocation syntax.

### `skill_link(name)`

`skill_link` renders `[<installed name>](<path>)`. The installed name is the skill's front-matter
`name`, which a generated skill may prefix. The path is relative to the turn's directory when the
file sits under the repo root. A file under the home folder renders as `~/...`. Any other file
renders as an absolute path.

### `skill_path(name, relative="")`

`skill_path` renders the path alone. With `relative`, it renders the path of that file inside the
skill's folder, such as `skill_path("story-docs", "references/format.md")`.

### `skill_command(name)`

`skill_command` renders how the active harness invokes the skill.

| harness | rendered text |
|---|---|
| `claude`, `copilot` | `/<installed name>` |
| `codex` | `$<installed name>` |
| any other | ``Read `<path>` and follow its instructions`` |

### `find_by_tags(*tags)`

`find_by_tags` asks for skills by capability instead of by name. It renders a comma-separated link
to every catalog skill whose tags include all of `tags`. A second tag narrows the result. Matches
are sorted by library name, and each name appears once. An empty query or no match renders the
empty string, so a prompt guards the sentence with `{% if %}` or `| default(...)`. A tag is
lowercased before it is compared.

### `has_skill(name)`

`has_skill` returns `True` when the catalog holds `name`. It never raises. A prompt puts an
optional reference inside `{% if has_skill("flutter") %}`, so a repo without that skill neither
renders the reference nor fails on it.

### Retired helpers

The old manifest helpers are still names in the environment, so a prompt that calls one fails
with a message instead of an undefined-name warning. Each stub raises `RetiredHelper`, whose text
reads ``"`<helper>` is retired. Call <replacement> with the skill's library name."``

| retired helper | replacement |
|---|---|
| `instruction_file`, `instruction_ref` | `skill_link` or `skill_path` |
| `instruction_refs`, `instruction_files`, `skill_files`, `prompt_refs`, `prompt_files` | `skill_link` |
| `skill_file`, `skill_dir`, `skill_path_ref`, `prompt_file`, `prompt_ref` | `skill_path` |
| `skill_load_ref` | `skill_command` |
| `isUsingInstruction` | `has_skill` |

- code: `workhorse/workhorse/_vendor/stablemate_core/skill_refs.py::RETIRED_HELPERS` @ebf1b69c7565
- code: `workhorse/workhorse/_vendor/stablemate_core/skill_refs.py::RetiredHelper` @ebf1b69c7565

## Naming a skill

A prompt names a skill by its library name. The library name of a generated skill is the
`metadata.name` farrier writes into its front matter. A hand-written skill has no such key, so its
library name is its front-matter `name`, else its folder name. A prompt file joins the catalog
under its file name without `.md` and `.prompt`. Tags come from `metadata.tags`, else `tags`.

The name stays the same whatever prefix an install adds. One prompt therefore renders in every
repo that installs the skill, under whatever installed name that repo gave it.

## The turn's catalog

`skill_refs` binds the helpers to one turn. It starts from the turn's declared `cwd`
(`_node_cwd`), else the run's `_repo_root`, else the process working directory. `turn_catalog`
then reads what the active harness loads when started there, in this order:

1. The start folder and each parent up to the repo root, the nearest folder holding `.git`.
2. Each of the turn's [`add_dirs`](../formats/workflow-format.md#cwd-and-add_dirs), resolved
   against the start folder. Only claude reads skills from an added directory.
3. The home folder.

The first entry for a name wins. A skill in the turn's folder therefore shadows the same skill at
the repo root, and a repo skill shadows a home skill.

| harness | repo skill folders | repo prompt folders | home folders |
|---|---|---|---|
| `claude` | `.claude/skills` | `.claude/commands` | `.claude/skills`, `.claude/commands` |
| `codex` | `.agents/skills` | `.agents/prompts` | `.agents/skills` |
| `copilot` | `.github/skills`, `.agents/skills`, `.claude/skills` | `.github/prompts` | `.agents/skills` |
| any other | `.claude/skills`, `.agents/skills` | none | `.claude/skills`, `.agents/skills` |

- code: `workhorse/workhorse/_vendor/stablemate_core/skill_refs.py::harness_folders` @ebf1b69c7565
- code: `workhorse/workhorse/_vendor/stablemate_core/skill_refs.py::repo_root` @ebf1b69c7565
- code: `workhorse/workhorse/_vendor/stablemate_core/skill_refs.py::SkillCatalog` @ebf1b69c7565
- tests: `core/tests/test_skill_refs.py::test_the_cwd_wins_over_the_repo_root_and_the_root_over_home`, `core/tests/test_skill_refs.py::test_the_walk_stops_at_the_repo_root`, `core/tests/test_skill_refs.py::test_only_claude_reads_skills_from_the_added_dirs`, `core/tests/test_skill_refs.py::test_each_harness_reads_its_own_home_folder`, `core/tests/test_skill_refs.py::test_a_generated_skill_is_found_by_its_library_name`, `core/tests/test_skill_refs.py::test_a_hand_written_skill_answers_to_its_own_name_and_tags`, `core/tests/test_skill_refs.py::test_a_prompt_joins_the_catalog_under_its_library_name`

## A named miss

`skill_link`, `skill_path` and `skill_command` demand their skill. A name the catalog does not
hold raises `MissingSkill`, whose text reads `no installed skill or prompt is named '<name>'`. The
turn stops with that error. A prompt that renders a placeholder where a path belonged would send
the agent looking for a file nobody installed, so the render refuses instead.

A render with `quiet=True` keeps going. Each miss renders `generated <name> skill when installed`.
No caller passes `quiet` today.

[Reference preflight](reference-preflight.md) finds the same misses before the first turn, for
every reference whose name is a constant.

- code: `workhorse/workhorse/_vendor/stablemate_core/skill_refs.py::MissingSkill` @ebf1b69c7565
- tests: `core/tests/test_skill_refs.py::test_a_named_miss_raises`, `core/tests/test_skill_refs.py::test_a_named_miss_defers_to_the_caller_when_asked`, `core/tests/test_skill_refs.py::test_has_skill_never_raises`

## Methods

### method: template_globals
- sig: `template_globals(context: dict[str, Any], *, quiet: bool = False) -> dict[str, Any]`
- does: return the run helpers, the five skill reference helpers and one raising stub per retired helper
- verify: count(subject="globals a rendered prompt can call", equals=22)
- does: build the turn's skill catalog at most once per call, on the first skill helper call
- verify: count(subject="catalog scans for one render calling three skill helpers", equals=1)
- returns: a mapping of Jinja global names to callables
- verify: count(subject="retired helper stubs in the returned mapping", equals=14)
- code: `workhorse/workhorse/templates.py::template_globals` @5308504a0103
- tests: `workhorse/tests/test_references.py::test_a_retired_helper_names_its_replacement`

### method: skill_refs
- sig: `skill_refs(context: dict[str, Any], *, quiet: bool = False) -> SkillRefs`
- does: start from `_node_cwd`, else the manifest repo root, else the process working directory
- verify: count(subject="start folders a turn resolves skills from", equals=1)
- does: read the turn's added directories from `_node_add_dirs`, relative to the start folder
- verify: count(subject="added directory skills a claude turn resolves", equals=1)
- does: render a missing name as a placeholder only when `quiet` is set
- verify: count(subject="placeholders a quiet render emits for one missing name", equals=1)
- returns: a `SkillRefs` bound to the turn's catalog, the active harness, the start folder, the repo root and the home folder
- verify: count(subject="harnesses a SkillRefs is bound to", equals=1)
- code: `workhorse/workhorse/templates.py::skill_refs` @5308504a0103
- tests: `workhorse/tests/test_references.py::test_a_turn_resolves_repo_and_home_skills_from_its_cwd`, `workhorse/tests/test_references.py::test_a_turn_sees_the_skills_of_its_added_dirs`, `workhorse/tests/test_context_manifest.py::test_a_turn_without_a_cwd_resolves_skills_from_the_manifest_repo`

### method: turn_catalog
- sig: `turn_catalog(cwd: Path, add_dirs: Iterable[Path] = ()) -> SkillCatalog`
- does: scan the folders the active harness loads from `cwd` up to the repo root, then the added directories, then home
- verify: count(subject="catalog entries for one name present in cwd, repo root and home", equals=1)
- returns: the catalog with the most local entry first for each name
- verify: count(subject="entries the catalog answers for one shadowed name", equals=1)
- code: `workhorse/workhorse/templates.py::turn_catalog` @5308504a0103
- tests: `core/tests/test_skill_refs.py::test_the_most_local_entry_wins`, `core/tests/test_skill_refs.py::test_the_walk_stops_at_the_repo_root`

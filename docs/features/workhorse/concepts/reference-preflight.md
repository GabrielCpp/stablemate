---
type: concept
slug: reference-preflight
title: Reference preflight — naming unresolvable skill/prompt references before the
  run
---
# Reference preflight — naming unresolvable skill/prompt references before the run

`instruction_ref("story-docs")` resolves against the [context manifest](../context-manifest.md).
When it does *not* resolve, the [helper](farrier-globals.md#instruction_refname-aliased-as-instruction_file-skill_file)
returns the placeholder `generated story-docs instruction file when installed`, and that sentence
is rendered straight into a live agent prompt where a path belonged. Nothing fails; the agent is
handed prose and left to find the skill itself. This module makes that visible — statically before
the first node, and again at render time for the calls a static scan cannot see.

Farrier used to own an equivalent check (`extract_workflow_dependencies` +
`validate_workflow_dependencies`), but it ran at *install* time against the workflow files farrier
copied. Workflows now run from the library and farrier keeps no workflow knowledge, so the check
belongs where the manifest and the prompts finally meet: the runner.

- code: `workhorse/workhorse/references.py::MissingReference`
- code: `workhorse/workhorse/references.py::resolve_instruction`
- code: `workhorse/workhorse/references.py::referenced_names`
- code: `workhorse/workhorse/references.py::missing_references`
- code: `workhorse/workhorse/references.py::format_missing`

The implementation is covered by `workhorse/tests/test_references.py`.

## Fields

### kind
- type: `str`
- default: none
- required: true
- semantics: reference category, either `skill` or `prompt`
- verify: count(subject="reference kinds on a missing-reference record", equals=1)
- code: `workhorse/workhorse/references.py::MissingReference.kind`

### name
- type: `str`
- default: none
- required: true
- semantics: constant skill or prompt name that did not resolve
- verify: count(subject="reference names on a missing-reference record", equals=1)
- code: `workhorse/workhorse/references.py::MissingReference.name`

### template
- type: `str`
- default: none
- required: true
- semantics: POSIX path of the prompt template relative to the workflow directory
- verify: count(subject="relative template paths on a missing-reference record", equals=1)
- code: `workhorse/workhorse/references.py::MissingReference.template`

## Methods

### __str__
- sig: `__str__(self) -> str`
- does: render the reference kind, quoted name, and relative template path in one operator-facing description
- verify: visible(locator="skill 'story-docs' (referenced in prompts/plan.md)")
- returns: `"{kind} '{name}' (referenced in {template})"`
- verify: visible(locator="skill 'story-docs' (referenced in prompts/plan.md)")
- code: `workhorse/workhorse/references.py::MissingReference.__str__`
- tests: `workhorse/tests/test_references.py::test_format_missing_names_the_cost_and_the_fix`

### resolve_instruction
- sig: `resolve_instruction(instructions: Mapping[str, str], name: str) -> str | None`
- does: return the exact mapping value when `name` is an instruction key
- verify: visible(locator="a.md")
- does: consider only keys without `/` whose key equals `name` or ends with `-<name>` for suffix resolution
- verify: count(subject="eligible namespaced instruction paths", equals=1)
- does: return the one unique resolved path shared by eligible suffix hits
- verify: visible(locator=".agents/skills/process-story-docs/SKILL.md")
- does: treat multiple keys for the same resolved path as one suffix hit
- verify: count(subject="resolved paths for aliased instruction keys", equals=1)
- does: return `None` when no eligible suffix hit exists
- verify: absent(subject="resolved instruction path for an unknown name")
- does: return `None` when eligible suffix hits resolve to different paths
- verify: absent(subject="resolved instruction path for an ambiguous suffix")
- returns: the installed path for a resolved instruction, otherwise `None`
- verify: visible(locator=".agents/skills/process-story-docs/SKILL.md")
- code: `workhorse/workhorse/references.py::resolve_instruction`
- tests: `workhorse/tests/test_references.py::test_exact_match_wins`, `workhorse/tests/test_references.py::test_unique_suffix_resolves_through_pack_namespacing`, `workhorse/tests/test_references.py::test_aliases_of_one_skill_are_not_an_ambiguity`, `workhorse/tests/test_references.py::test_two_packs_ending_the_same_way_resolve_to_nothing`, `workhorse/tests/test_references.py::test_unknown_name_resolves_to_nothing`

### referenced_names
- sig: `referenced_names(source: str) -> set[tuple[str, str]]`
- does: parse the source as Jinja and collect constant-argument calls to required singular skill and prompt helpers
- verify: count(subject="required skill and prompt references found in an AST", equals=5)
- does: classify singular skill helper aliases as `skill` and prompt helper aliases as `prompt`
- verify: count(subject="classified skill and prompt references", equals=5)
- does: exclude plural optional helpers and tag-query helpers from the result
- verify: count(subject="references reported for optional and tag helpers", equals=0)
- does: exclude references inside an installed-skill guard branch while evaluating else and elif branches independently
- verify: count(subject="unguarded references beside a guarded branch", equals=1)
- does: skip calls whose first argument is absent or is not a constant string
- verify: count(subject="constant references retained beside dynamic calls", equals=1)
- does: return an empty set when the Jinja source has a syntax error
- verify: count(subject="references reported from an unparseable template", equals=0)
- returns: a set of `(kind, name)` pairs with no duplicate references
- verify: count(subject="deduplicated reference pairs", equals=1)
- code: `workhorse/workhorse/references.py::referenced_names`
- tests: `workhorse/tests/test_references.py::test_every_helper_alias_is_scanned`, `workhorse/tests/test_references.py::test_plural_helper_arguments_are_never_required`, `workhorse/tests/test_references.py::test_reference_behind_an_installed_skill_guard_is_not_required`, `workhorse/tests/test_references.py::test_non_constant_argument_is_skipped_not_guessed`, `workhorse/tests/test_references.py::test_unparseable_template_yields_nothing`

### missing_references
- sig: `missing_references(workflow_dir: str | Path, context: Mapping[str, Any]) -> list[MissingReference]`
- does: return an empty list when the context has no manifest
- verify: count(subject="missing references from a manifest-free run", equals=0)
- does: scan only regular Markdown files matching `**/prompts/**/*.md` below `workflow_dir`
- verify: count(subject="prompt files scanned including nested flow prompts", equals=1)
- does: ignore unreadable prompt files and non-file glob results
- verify: count(subject="missing references from unreadable or non-file prompt entries", equals=0)
- does: classify an unresolved skill by `resolve_instruction` and an unresolved prompt by exact prompt-map membership
- verify: count(subject="unresolved skill and prompt findings", equals=2)
- does: deduplicate findings with the same kind, name, and relative template path
- verify: count(subject="duplicate missing-reference findings", equals=1)
- does: sort findings by relative template path, kind, and name
- verify: count(subject="stable missing-reference ordering", equals=3)
- returns: a sorted list of `MissingReference` records, or an empty list when every checked reference resolves
- verify: count(subject="sorted missing-reference records", equals=3)
- code: `workhorse/workhorse/references.py::missing_references`
- tests: `workhorse/tests/test_references.py::test_missing_references_names_what_will_not_resolve`, `workhorse/tests/test_references.py::test_nested_prompt_directories_are_scanned`, `workhorse/tests/test_references.py::test_docs_outside_prompts_are_not_scanned`, `workhorse/tests/test_references.py::test_no_manifest_at_all_is_skipped_whole`, `workhorse/tests/test_references.py::test_report_is_stable_across_runs`

### format_missing
- sig: `format_missing(missing: Iterable[MissingReference]) -> str`
- does: return an empty string when the iterable contains no missing references
- verify: absent(subject="operator-facing missing-reference report for an empty collection")
- does: report the number of missing references followed by one indented line per record
- verify: visible(locator="1 reference(s) will not resolve against this repo's context manifest")
- does: include each record's string form in the report
- verify: visible(locator="skill 'story-docs' (referenced in prompts/plan.md)")
- does: explain that unresolved references render placeholder prose into a live agent prompt
- verify: visible(locator="generated story-docs instruction file when installed")
- does: tell the operator to add the skill or prompt to `agents.yml` and rerun `make agent-install`
- verify: visible(locator="agents.yml")
- returns: one operator-facing report string, including a trailing newline for non-empty input
- verify: visible(locator="make agent-install")
- code: `workhorse/workhorse/references.py::format_missing`
- tests: `workhorse/tests/test_references.py::test_format_missing_names_the_cost_and_the_fix`, `workhorse/tests/test_references.py::test_format_missing_of_nothing_is_empty`

## Contract

- **Input:** `workflow_dir: Path` — the running workflow's own directory; `context: Mapping` —
  the loaded manifest context (the reserved `_instructions` / `_prompts` maps).
- **Output:** a sorted `list[MissingReference]` (`kind`, `name`, `template`), stable across runs.
  Empty when everything resolves, when the workflow has no `prompts/`, or when **no manifest was
  loaded at all**.

## What is scanned

`**/prompts/**/*.md` under the workflow directory, and nothing else. The scope is deliberate: a
workflow's own README or design note may show `{{ instruction_ref(...) }}` in a fenced example,
and a documented example is not a broken reference. The leading `**` is what reaches a workflow
whose flows each own their prompts — `coder/dev/prompts/`, `coder/main/prompts/` — since a glob
anchored at the workflow root would sweep only the single-machine workflows and pass vacuously on
every other.

Each file is **parsed as Jinja**, not grepped. The templates are Jinja already, so the call sites
are in the AST — which means every alias of the helper (`instruction_file`, `skill_file`,
`prompt_file`) is covered without listing regexes, and a mention inside prose, a comment or a
string literal is not mistaken for a call. A template that will not parse yields nothing: the
syntax error belongs to the render, and reporting it twice would turn one clear failure into two.

## What is *not* reported

Only *required* references are findings. A prompt has three ways to say a reference is optional,
and all three are exempt from the scan:

| Spelling | Why it is not a finding |
|---|---|
| `instruction_refs(...)` / `instruction_files` / `skill_files`, `prompt_refs` / `prompt_files` (`OPTIONAL_SKILL_HELPERS`, `OPTIONAL_PROMPT_HELPERS`) | The plural helpers ask *which of these did the repo install* and drop the rest. An absent name is the answer, not a defect. |
| `find_by_tags('web', 'tests')` (`TAG_HELPERS`) | Its arguments are **tags, not names**. There is nothing here to resolve, and descending into them would report every tag in every prompt as a missing skill. |
| A reference inside `{% if isUsingInstruction('flutter') %}` (`GUARD_HELPERS`) | It cannot render on a repo without that skill. The `{% else %}`/`{% elif %}` branches are judged on their own, since they render precisely when the guard did not hold. |

This is what a prompt reaching for per-stack skills needs: a Go repo must not be told to go read a
Flutter skill, and must not fail preflight for not having one.

## Two deliberate limits

- **Only constant arguments are checkable.** `instruction_ref(skill)` names something known at
  render time only; it is skipped rather than guessed at. The render-time warning below is what
  covers those.
- **A manifest-free run is skipped whole.** `hello-world` and most tests carry no manifest, so
  "unresolved" is their normal state, not a symptom.

## Resolution rule

`resolve_instruction(instructions, name)` is shared by the preflight and the render path, so the
two can never disagree about what resolves. Exact match first; then a **unique** suffix match on
the last dash-segment, because a prompt asks for a capability (`story-docs`) while a pack is free
to namespace the skill providing it (`process-story-docs`). Uniqueness is judged on the resolved
*path*, not the key — farrier indexes one skill under several aliases, and counting keys would
make every namespaced skill look ambiguous with itself.

## Where it fires

| Moment | Behavior |
|---|---|
| Before the first node (`main.run`) | Every unresolvable constant reference is listed on stderr with the fix (`agents.yml` + `make agent-install`). A **warning**, not an error — the run is degraded, not impossible, and this engine [fails soft](../../../../workhorse/docs/GUARDRAILS.md). |
| At render time (`_farrier_globals`) | A reference that actually resolved to nothing logs one `[template] ⚠` line and keeps the placeholder. Suppressed when the context carries no manifest (nothing was ever expected to resolve) and when the caller passes `quiet=True` (telemetry labels re-render before every node). |

A half-rendered prompt is worse than one carrying a sentence the agent can at least read, so the
placeholder itself is unchanged. What changed is that it is no longer silent.

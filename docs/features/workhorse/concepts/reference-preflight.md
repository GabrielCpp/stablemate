---
type: concept
slug: reference-preflight
title: Reference preflight
---
# Reference preflight

An operator who starts a run learns before the first turn which prompts name a skill this machine
has not installed. Without the sweep, the run would get as far as that turn and stop there.
[`skill_link("story-docs")`](template-globals.md#skill_linkname) raises `MissingSkill` when no
catalog entry answers to `story-docs`, so the turn whose prompt makes the call stops with an error.
This module finds those calls statically, before the first state runs. It also finds every call to
a retired helper, which fails the same way.

The sweep resolves against `turn_catalog(<workspace>)`, the catalog a turn started in the run's
workspace would see. A turn that declares its own `cwd` or `add_dirs` can see more skills than the
workspace does. The render-time check still covers that turn.

- code: `workhorse/workhorse/references.py::MissingReference` @c6ff9b16296e
- code: `workhorse/workhorse/references.py::helpers_called` @c6ff9b16296e
- code: `workhorse/workhorse/references.py::referenced_names` @c6ff9b16296e
- code: `workhorse/workhorse/references.py::missing_references` @c6ff9b16296e
- code: `workhorse/workhorse/references.py::format_missing` @c6ff9b16296e

The implementation is covered by `workhorse/tests/test_references.py`.

## Fields

### kind
- type: `str`
- default: none
- required: true
- semantics: `skill` for a named reference no catalog entry answers, `retired` for a call to a retired helper
- verify: count(subject="reference kinds on a missing-reference record", equals=1)
- code: `workhorse/workhorse/references.py::MissingReference.kind` @c6ff9b16296e

### name
- type: `str`
- default: none
- required: true
- semantics: the skill's library name for kind `skill`, the helper's name for kind `retired`
- verify: count(subject="reference names on a missing-reference record", equals=1)
- code: `workhorse/workhorse/references.py::MissingReference.name` @c6ff9b16296e

### template
- type: `str`
- default: none
- required: true
- semantics: POSIX path of the prompt template relative to the workflow directory
- verify: count(subject="relative template paths on a missing-reference record", equals=1)
- code: `workhorse/workhorse/references.py::MissingReference.template` @c6ff9b16296e

## Methods

### __str__
- sig: `__str__(self) -> str`
- does: render a missing skill as its quoted name and the template that references it
- verify: count(subject="quoted skill names in one missing-skill description", equals=1)
- does: render a retired helper as its backticked name and the template that calls it
- verify: count(subject="backticked helper names in one retired-helper description", equals=1)
- returns: `"skill '{name}' (referenced in {template})"` or ``"retired helper `{name}` (called in {template})"``
- verify: count(subject="templates named in one missing-reference description", equals=1)
- code: `workhorse/workhorse/references.py::MissingReference.__str__` @c6ff9b16296e
- tests: `workhorse/tests/test_references.py::test_format_missing_names_the_cost_and_the_fix`

### helpers_called
- sig: `helpers_called(source: str) -> set[str]`
- does: name every named, tag or retired skill helper the source calls, whatever its arguments
- verify: count(subject="reference helpers named for a template calling one named and one unrelated helper", equals=1)
- returns: the set of helper names called
- verify: count(subject="helper names reported for a template calling no reference helper", equals=0)
- code: `workhorse/workhorse/references.py::helpers_called` @c6ff9b16296e
- tests: `workhorse/tests/test_references.py::test_helpers_called_names_the_reference_helpers_only`

### referenced_names
- sig: `referenced_names(source: str) -> set[tuple[str, str]]`
- does: parse the source as Jinja and collect the constant first argument of each named helper call as kind `skill`
- verify: count(subject="named helper references found in a template calling each named helper once", equals=3)
- does: collect every retired helper call as kind `retired`, whatever its arguments and guards
- verify: count(subject="retired references found for a retired call with a dynamic argument", equals=1)
- does: exclude `find_by_tags` arguments from the result
- verify: count(subject="references reported for a tag query alone", equals=0)
- does: exclude named references inside a `has_skill` guard branch while judging else and elif branches on their own
- verify: count(subject="unguarded references beside a guarded branch", equals=1)
- does: skip named calls whose first argument is absent or is not a constant string
- verify: count(subject="constant references retained beside dynamic calls", equals=1)
- does: return an empty set when the Jinja source has a syntax error
- verify: count(subject="references reported from an unparseable template", equals=0)
- returns: a set of `(kind, name)` pairs with no duplicate references
- verify: count(subject="deduplicated reference pairs", equals=1)
- code: `workhorse/workhorse/references.py::referenced_names` @c6ff9b16296e
- tests: `workhorse/tests/test_references.py::test_every_named_helper_is_scanned`, `workhorse/tests/test_references.py::test_tag_query_arguments_are_not_skill_names`, `workhorse/tests/test_references.py::test_reference_behind_a_has_skill_guard_is_not_required`, `workhorse/tests/test_references.py::test_each_elif_is_judged_by_its_own_test`, `workhorse/tests/test_references.py::test_non_constant_argument_is_skipped_not_guessed`, `workhorse/tests/test_references.py::test_a_retired_helper_is_reported_whatever_its_arguments`, `workhorse/tests/test_references.py::test_unparseable_template_yields_nothing`

### missing_references
- sig: `missing_references(workflow_dir: str | Path, catalog: SkillCatalog) -> list[MissingReference]`
- does: scan only regular Markdown files matching `**/prompts/**/*.md` below `workflow_dir`
- verify: count(subject="prompt files scanned including nested flow prompts", equals=1)
- does: ignore unreadable prompt files and non-file glob results
- verify: count(subject="missing references from unreadable or non-file prompt entries", equals=0)
- does: report a skill reference when the catalog holds no entry under its name
- verify: count(subject="findings for a reference the catalog answers", equals=0)
- does: report every retired helper call
- verify: count(subject="findings for one retired helper call", equals=1)
- does: sort findings by relative template path, kind and name
- verify: count(subject="stable missing-reference ordering", equals=3)
- returns: a sorted list of `MissingReference` records with no duplicates, empty when every reference renders
- verify: count(subject="missing-reference records when every skill is installed", equals=0)
- code: `workhorse/workhorse/references.py::missing_references` @c6ff9b16296e
- tests: `workhorse/tests/test_references.py::test_missing_references_names_what_will_not_render`, `workhorse/tests/test_references.py::test_everything_resolving_reports_nothing`, `workhorse/tests/test_references.py::test_a_flows_own_prompts_are_scanned`, `workhorse/tests/test_references.py::test_docs_outside_prompts_are_not_scanned`, `workhorse/tests/test_references.py::test_report_is_stable_across_runs`

### format_missing
- sig: `format_missing(missing: Iterable[MissingReference]) -> str`
- does: return an empty string when the iterable contains no missing references
- verify: count(subject="characters in the report for an empty collection", equals=0)
- does: open with the number of references that will fail to render
- verify: count(subject="counts stated in a one-record report", equals=1)
- does: list each record's string form on its own indented line
- verify: count(subject="record lines in a one-record report", equals=1)
- does: state that a turn whose prompt makes one stops with an error
- verify: count(subject="consequence lines in a non-empty report", equals=1)
- does: tell the operator to install the skill with `farrier install` and to move a retired helper to its replacement
- verify: count(subject="fix lines in a non-empty report", equals=1)
- returns: one operator-facing report string
- verify: count(subject="reports returned for one call", equals=1)
- code: `workhorse/workhorse/references.py::format_missing` @c6ff9b16296e
- tests: `workhorse/tests/test_references.py::test_format_missing_names_the_cost_and_the_fix`, `workhorse/tests/test_references.py::test_format_missing_of_nothing_is_empty`

## Contract

- **Input:** `workflow_dir: Path` is the running workflow's own directory. `catalog: SkillCatalog`
  is what the run's workspace resolves skills against.
- **Output:** a sorted `list[MissingReference]` (`kind`, `name`, `template`), stable across runs.
  It is empty when every reference renders or when the workflow has no `prompts/` folder.

## What is scanned

The sweep reads `**/prompts/**/*.md` under the workflow directory, and nothing else. A workflow's
README or design note may show `{{ skill_link(...) }}` in a fenced example, and a documented example
is not a broken reference. The leading `**` reaches a workflow whose flows each own their prompts,
such as `coder/dev/prompts/` and `coder/main/prompts/`.

The sweep parses each file as Jinja instead of grepping it. A mention inside prose, a comment or a
string literal is therefore not mistaken for a call. A template that will not parse yields nothing.
The syntax error belongs to the render, and a second report of it would add nothing.

An inline prompt is outside the glob, so the sweep cannot check it.
[`workflow.py`](../formats/workflow-format.md) rejects an inline prompt body that calls any helper
`helpers_called` names. The error tells the author to put that turn in a prompt file.

## What is *not* reported

A named reference is a finding only when it is required. A prompt has two ways to say a skill is
optional, and the sweep exempts both:

| Spelling | Why it is not a finding |
|---|---|
| `find_by_tags('web', 'tests')` (`TAG_HELPERS`) | Its arguments are tags, not names. An empty match renders the empty string, which is the answer and not a defect. |
| A reference inside `{% if has_skill('flutter') %}` (`GUARD_HELPERS`) | It cannot render on a repo without that skill. The `{% else %}` and `{% elif %}` branches are judged on their own, because they render when the guard did not hold. |

A Go repo must not be told to read a Flutter skill, and must not fail preflight for not having one.
A retired helper is reported even inside a guard, because it fails whatever branch it sits in.

## One deliberate limit

Only constant arguments are checkable. `skill_link(name)` names something known at render time
only, so the sweep skips it instead of guessing. The render-time error covers those calls.

## Where it fires

| Moment | Behavior |
|---|---|
| Before the first state of a real run | `run_pyflow` prints the report as a `[workhorse] WARNING:` line and the run continues. A turn that never makes the missing call still runs. |
| `--dry-run` | `run_pyflow` prints the report as a `[workhorse] ERROR:` line and returns `1`, before the graph preflight runs. |
| At render time | A named miss raises `MissingSkill` and a retired helper raises `RetiredHelper`. Either one stops the turn. See [a named miss](template-globals.md#a-named-miss). |

- code: `workhorse/workhorse/pyflow/run.py::run_pyflow` @e11e110ff8f7
- tests: `workhorse/tests/test_pyflow_graph.py::test_an_unresolvable_skill_reference_warns_a_real_run_and_fails_a_dry_one`, `workhorse/tests/test_pyflow_graph.py::test_a_run_whose_skills_are_installed_is_not_warned_about_references`

---
type: concept
slug: reference-preflight
title: Reference preflight — naming unresolvable skill/prompt references before the run
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

- code: `workhorse/workhorse/references.py`
- verify: `workhorse/tests/test_references.py`

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

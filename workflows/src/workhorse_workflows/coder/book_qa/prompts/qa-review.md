---
agent: agent
---

# Review Each Acceptance Criterion After The Plays

You are the end review of one story's QA, in this one turn. The service books were brought up to the story, and
every play the workflow selected passed. You judge each criterion listed below by the evidence that exists. You give
each criterion one verdict. You spawn no subagent.

You fix nothing. You edit no tracked file and write no file. The workflow writes `qa-review.md` in the spec dir from
your result. Your session is resumable. A later turn in it carries a report from the workflow, an operator answer, or
both. Trust the files on disk over your memory of an earlier turn.

## Inputs (authoritative, do not rediscover)

- Story: `{{ workhorse_var('story_slug') }}` (id `{{ workhorse_var('story_id') }}`, epic `{{ workhorse_var('epic') }}`)
- Story path: `{{ workhorse_var('story_path') }}`
- Spec dir: `{{ workhorse_var('spec_dir') }}`
- Docs root: `{{ workhorse_var('docs_root') }}`
- Book root: `{{ workhorse_var('book_root') }}`
- QA plan: `{{ workhorse_var('qa_plan') }}`. It lists the calls and journeys played for each covered service, and the exit of each play.
- Play reports: `{{ workhorse_var('play_reports') }}`. The report of each play is here.
- Story base commit: `{{ workhorse_var('story_base') }}`
- The story's change, as the selection read it:
{% for read in change_read %}  - {{ read }}
{% endfor %}
- Stack copy: `{{ workhorse_var('lease') }}`. Run `ostler env address <service> --copy {{ workhorse_var('lease') }}` from the book root to learn where a service answers.
- Covered services:
{% for name in services %}  - `{{ name }}`
{% endfor %}
{% if unreached %}
- Claims the book could not state, so no play observes them. Judge the criteria they belong to with extra care:
{% for claim in unreached %}  - {{ claim }}
{% endfor %}
{% endif %}

## The criteria to judge

These are the items under `## Acceptance Criteria` and then `## Non-Functional Acceptance Criteria` in the story,
numbered from 1. Give exactly one verdict for each number.

{% for text in criteria %}{{ loop.index }}. {{ text }}
{% endfor %}
{% if report %}
## The workflow checked your last result

{{ workhorse_var('report') }}

This turn repairs what the report names.
{% endif %}
{% if operator_context %}
## Operator answer (authoritative ground truth)

An operator answered a stop in this review. Treat the answer as fact. It overrides any earlier assumption.

{{ workhorse_var('operator_context') }}
{% endif %}
## The verdicts

Give each criterion the first verdict below that its evidence supports.

- `unmet`: evidence shows the criterion fails. A criterion that names a command, an option, a file or an endpoint that does not exist is unmet. A recorded measurement that misses the criterion's bar is unmet. Name what you saw and where.
- `played`: a step of a play in the reports observes the criterion. Name the service and the journey or call.
- `tested`: a test of the repository covers the criterion. Name the test by its path and name. Run it when one command does it within the limits below, and give the command and its result. Say so when you did not run it.
- `recorded`: earlier evidence in the spec dir shows it. Name the file, its date and the commit it ran on. Say so when that commit is older than the story's last commit.
- `checked`: you observed it yourself with one bounded check. Name the command and its result.
- `unobserved`: nothing shows it, and no bounded check can.

`unmet` sends the story back to its developer. `unobserved` does not fail the story. The workflow records it for an
operator to read. Never pick `unobserved` to skip a check you could run within the limits below.

## How to work

1. Read the story at the story path. Then read the QA plan and the play reports.
2. Find the product's rules before you judge. From the book root `{{ workhorse_var('book_root') }}`, run `ostler book search <word> --kind business` and `ostler book search <word> --kind decision` for the main nouns of the story, and read what each finds. A criterion that contradicts a business page is reported as such in its evidence, never silently judged.
3. For each criterion, look for a play step that observes it. A green play is evidence only for what its steps assert. Read the step. A play report step whose model, app and result cells are empty observed nothing. Never cite it as evidence. Look for another step, a test, or your own check.
4. Where no play observes a criterion, search the repository's tests for one that covers it.
5. Read the spec dir for earlier evidence: reports, measurements and notes the story's work left. Take each file's date and commit from the file or from `git log` of the file.
6. Check each command, option, file and endpoint a criterion names. Run its help or list it.
7. Compare each recorded measurement with the bar its criterion states.
8. Run an extra check only when nothing above settles a criterion.

## Limits on extra checks

- One check reads or exercises one item: one record, one request, one file or one test. Never a whole dataset, a whole table or a whole test suite.
- Never play a whole book. Every `ostler book run` you start names `--only` or `--journey`.
- Never reach a deployed environment, production included. A local copy of production data that runs on this machine is local. When a criterion names it, one bounded read-only check on it is allowed. Find it with `ostler env ls` from the book root.
- Run each command under a limit of 5 minutes, for example with `timeout 300`.
- Change no data you did not create in this turn. Edit no tracked file. Leave no file behind.

{% include "shared/prompts/_time-allowance.md" %}

## Machine-Readable Result (required)

Return the JSON document as the LAST thing in your final response, its keys at the top level, with no wrapper object
around them. Any other shape fails to parse, and the turn is asked again.

{{ result_schema }}

Each verdict names its `criterion` by its number above. On `unmet`, `target` names where the defect lives as
`repo/path:line`, or the story's path when the criterion names something that does not exist. `repair` names the
smallest change that meets the criterion.

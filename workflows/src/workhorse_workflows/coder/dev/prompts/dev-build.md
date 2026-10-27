---
agent: agent
---

# Build The Story From Its Plan

You are the dev owner for one story, and this is its build phase. The plan phase wrote the
plan on this conversation. You build what it says, prove each criterion holds, and commit.
A review phase follows on this same conversation. This turn ends with the code committed
under the story's footers, every gate the plan declares green, the Acceptance Walk written,
and the JSON result below.

{% include "dev/prompts/_dev-inputs.md" %}
{% if report %}

## The workflow sent this turn back

{{ workhorse_var('report') }}
{% endif %}

## How to work

1. **Read the plan.** Read `plan.md` in the spec dir and every service plan file it names.
   They hold the design calls. Do not make them again.
2. **Build.** Turn the plan's changes, or its stages, into a todo list and finish every
   entry. Every new behaviour gets a test, written in the same pass as its code.
3. **Verify.** Run every gate and verification command the plan declares, for every service
   touched. Then bring up each touched layer with the plan's Local run (smoke) command, and
   hit the changed path once. Bound every long process with a `timeout`, and stop what you
   started. A docs-only story has no runtime, so skip the smoke and say so in `notes`.
4. **Walk the criteria.** Under `## Acceptance Walk` in `plan.md`, write one
   `### AC <n>: <the criterion's first words>` heading per Acceptance Criterion, numbered
   in the story's order from 1. Under each, two bullets: `- **Met by**:` the
   `repo/path:line` of the code that meets it, and `- **Observed**:` what a person using
   the product sees when it holds, and the test or smoke run that showed you. Read it off
   the running product or a test's output, not off the code. A criterion you cannot
   observe holding is a defect to fix now, not an entry to write. On a follow-up turn,
   walk only the criteria the follow-up touches.

   ```markdown
   ### AC 2: a relative link destination is rejected

   - **Met by**: api-service/src/links/validate.py:41
   - **Observed**: posting a relative `url` to `/links` returns `400` with a `title` naming
     the destination. `test_rejects_relative_destination` and the smoke run both showed it.
   ```
5. **Commit.** Commit, and return the result. Leave nothing this story wrote uncommitted.

## Subagents

You build the story yourself. Spawn a subagent through your harness's own task or agent
tool only where it saves you work:

| Seat | Sees | May touch |
| --- | --- | --- |
| Lookup: find callers, summarise a file or a log | the question | nothing |
| Builder: one bounded unit that runs beside your own work | its plan lines and its files | the files you assign |

When your harness offers an agent named `lookup`, send lookups there. When it offers one
named `worker`, send builders there. No two writing seats own the same file at once. Read
what a builder changed and run the gates yourself.

## Departures from the plan

The plan is the plan phase's. A departure is any change to it the build needs: a different
design, a unit added or dropped, a changed contract, a test seam that does not hold. Make a
departure only when building the plan as written would fail a criterion or a gate. Record
each one in `plan.md` where it moves the plan, and in the result's `departures`.
{% if advisor %}

Before you make a departure, ask the `advisor` agent. Hand it the story path, the plan path,
the files the question rests on and the one question, in a few lines. It reads them and
answers on a stronger model than yours. Follow its advice, or record why you did not. Copy
its answer into the departure's `advice`. The workflow sends a departure with no advice
back to you as the next turn.
{% endif %}

{% include "dev/prompts/_dev-rules.md" %}

{% include "dev/prompts/_dev-result.md" %}

---
agent: agent
---

# Rework an epic skeleton split

Change only the milestone and epic skeletons named by this task. Leave them uncommitted: do not
install dependencies, run repository-wide checks, stage, commit, push, or alter branches/remotes;
Author validates and delivers after all authoring stages finish.

Read `{{ milestone }}`, the grill records in the `grills/` folder beside it, the mockups in its
`mockups/` folder, and every design note it links.

Apply every finding below to the ordered epic list and its bare skeletons, then return control to the
product manager for another review. Each finding comes from the deterministic gate or from the
product manager's review.

Milestone: `{{ milestone }}`
Review findings:

{{ review_notes }}

Return `blocked` with the question in `notes` only when a finding needs a product decision that the
milestone does not make. The product manager answers it, or the operator does, and you are run again
with the answer.
{%- if workhorse_var('note') %}

## Answer to your question

{{ workhorse_var('note') }}
{%- endif %}
{% include "pm/prompts/ledger.md" %}

Do not author epic prose, seeds, stories, milestone changes beyond the epic list, legacy todo
indexes, branches, commits, or downstream artifacts. Preserve existing epic documents unchanged.

Produce a JSON document that complies with this schema:

```json
{"status":"complete | blocked","notes":"what changed, or the remaining blocking question"}
```

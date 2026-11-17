---
agent: agent
---

# Split one milestone into epic skeletons

Change only the milestone and epic skeletons named by this task. Leave them uncommitted: do not
install dependencies, run repository-wide checks, stage, commit, push, or alter branches/remotes;
Author validates and delivers after all authoring stages finish.

Read `{{ milestone }}`, the grill records in the `grills/` folder beside it, the mockups in its
`mockups/` folder, and every design note it links. Set the milestone's epics, in coding order, with
`ostler milestone epics <milestone> <epic>...`. Ostler stores each epic by its id and writes the
`## Epics` section a reader sees, so never edit the `epics:` value or that section by hand. Each
epic must group coherent user journeys and deliver or materially advance an observable milestone
outcome.

Create missing epics with `ostler create epic` first, so Ostler allocates their ids. Leave every new epic as Ostler's bare
skeleton: title plus empty `## Seeds` and `## Stories` sections. Do not author outcome, journey,
acceptance, method, seed, or story prose. Do not edit existing epic documents, legacy
todo indexes, branches, commits, or downstream artifacts. The deterministic gate compares existing
epic fingerprints and all seed/story identities, and rejects prose in newly created skeletons.

Preserve every milestone journey, locked decision, constraint, acceptance requirement, and non-goal
in the split itself. Return `blocked` with the question in `notes` rather than inventing an unresolved
product decision. The product manager answers it, or the operator does, and you are run again with
the answer.
{%- if workhorse_var('note') %}

## Answer to your question

{{ workhorse_var('note') }}
{%- endif %}
{% include "pm/prompts/books.md" %}
{% include "pm/prompts/ledger.md" %}

Produce a JSON document that complies with this schema:

```json
{"status":"complete | blocked","notes":"the ordered skeleton list, or the blocking question"}
```

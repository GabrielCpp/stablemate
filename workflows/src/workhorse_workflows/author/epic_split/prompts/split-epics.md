---
agent: agent
---

# Split one milestone into epic skeletons

Change only the milestone and epic skeletons named by this task. Leave them uncommitted: do not
install dependencies, run repository-wide checks, stage, commit, push, or alter branches/remotes;
Author validates and delivers after all authoring stages finish.

Read the approved roadmap at `{{ roadmap }}` and its milestone at `{{ milestone }}`. Replace the
milestone's `epics` value with one positive, non-empty list in coding order. Each epic must group
coherent user journeys and deliver or materially advance an observable roadmap outcome.

Create missing epics with Ostler so it allocates their ids. Leave every new epic as Ostler's bare
skeleton: title plus empty `## Seeds` and `## Stories` sections. Do not author outcome, journey,
acceptance, method, seed, or story prose. Do not edit existing epic documents, the roadmap, legacy
todo indexes, branches, commits, or downstream artifacts. The deterministic gate compares existing
epic fingerprints and all seed/story identities, and rejects prose in newly created skeletons.

Preserve every roadmap journey, locked decision, constraint, acceptance requirement, and non-goal
in the split itself. Return `blocked` rather than inventing an unresolved product decision.

Produce a JSON document that complies with this schema:

```json
{"status":"complete | blocked","notes":"the ordered skeleton list, or the blocking question"}
```

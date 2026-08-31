---
agent: agent
---

# Rework an epic skeleton split

Change only the milestone and epic skeletons named by this task. Leave them uncommitted: do not
install dependencies, run repository-wide checks, stage, commit, push, or alter branches/remotes;
Author validates and delivers after all authoring stages finish.

Apply every review finding below to the ordered epic list and its bare skeletons, then return control
to the reviewer.

Roadmap: `{{ roadmap }}`
Milestone: `{{ milestone }}`
Review findings:

{{ review_notes }}

Do not author epic prose, seeds, stories, roadmap changes, legacy todo indexes, branches, commits,
or downstream artifacts. Preserve existing epic documents unchanged.

Produce a JSON document that complies with this schema:

```json
{"status":"complete | blocked","notes":"what changed, or the remaining blocking question"}
```

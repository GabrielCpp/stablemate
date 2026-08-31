---
agent: agent
---

# Build one roadmap milestone

Change only the milestone artifact named by this task. Leave it uncommitted: do not install
dependencies, run repository-wide checks, stage, commit, push, or alter branches/remotes; Author
validates and delivers after all authoring stages finish.

Create or reuse exactly one milestone document whose sole `sourceItems` value is
`{{ roadmap }}`. The roadmap is approved and authoritative; read it before naming the milestone.

Use Ostler to allocate a new milestone id when no milestone already owns that source path. Reuse
the existing document when one does. Preserve its current ordered `epics` list verbatim. Do not
create, edit, remove, or reorder epics, and do not write stories, seeds, branches, commits, or
downstream artifacts. The deterministic gate compares every epic document with its pre-turn
fingerprint and verifies that the milestone's epic list did not change.

Produce a JSON document that complies with this schema:

```json
{"status":"complete | blocked","notes":"what was created or reused, or the blocking question"}
```

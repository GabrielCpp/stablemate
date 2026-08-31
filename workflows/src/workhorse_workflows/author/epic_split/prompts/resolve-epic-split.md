---
agent: agent
---

# Diagnose an epic-split operator block

Investigate why the approved roadmap at `{{ roadmap }}` and milestone at `{{ milestone }}` could not
converge on an ordered epic skeleton list. Do not decide scope, edit planning documents, author epic
prose or seeds, branch, commit, or invoke another stage.

Block notes:

{{ block_notes }}

Read `{{ context_path }}` first when it exists. Append concrete findings and options under a
`## Findings` heading, preserving all prior content, and set its first status line to
`STATUS: AWAITING_OPERATOR`.

Produce a JSON document that complies with this schema:

```json
{"decision":"escalated","notes":"the decision required","tried":["evidence checked"]}
```

---
agent: agent
---

# Review an epic skeleton split

Read `{{ milestone }}`, the grill records in the `grills/` folder beside it, the mockups in its
`mockups/` folder, and every design note it links. Read only the epic skeletons the milestone lists. Do
not edit artifacts. Approve only when the one non-empty epic list is dependency-ordered, covers the
milestone's journeys and release boundary without horizontal layer phases, includes no non-goal, and
leaves every listed epic as a bare skeleton with no prose, seeds, or stories.

Produce a JSON document that complies with this schema:

```json
{"status":"approved | needs_rework | blocked","notes":"exact repairs or owner decision required"}
```

---
type: flow
slug: freeze-a-story
title: Freeze a story
---
# Freeze a story

- start: a story's text is approved
- steps:
  - [ostler freeze](../planning.md#ostler-freeze)
- end: the caller reads the fingerprint hash recorded for the story
- verify: exit_status(code=0)
- verify: stdout(matches="freeze story 'TST-01M585PD385GTJPSFXM5M5WV5N'")
- verify: stdout(matches="recorded in .*ids\\.json")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with an unfrozen story

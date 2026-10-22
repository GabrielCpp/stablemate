---
type: format
slug: roadmap-status
title: Roadmap status
---
# Roadmap status

The final roadmap transition result identifies the roadmap file and the lifecycle status written to
it.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::RoadmapStatus` @f9301e7de2f3
- detail: [author shared schemas](../concepts/author-shared-schemas.md)

## Fields

### path
- type: string path
- default: empty string
- required: false
- semantics: roadmap document whose lifecycle was transitioned
- verify: json_path(path="$.path", equals="docs/stories/acme-story/story.md")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::RoadmapStatus` @f9301e7de2f3
- detail: [roadmap status field roles](../concepts/roadmap-status-field-roles.md)

### status
- type: string
- default: empty string
- required: false
- semantics: lifecycle status recorded on the roadmap
- verify: json_path(path="$.status", equals="example status")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::RoadmapStatus` @f9301e7de2f3
- detail: [roadmap status field roles](../concepts/roadmap-status-field-roles.md)

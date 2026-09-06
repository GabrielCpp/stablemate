---
type: format
slug: roadmap-status
title: Roadmap status
---
# Roadmap status

The final roadmap transition result identifies the roadmap file and the lifecycle status written to
it.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::RoadmapStatus`
- detail: [author shared schemas](concepts/author-shared-schemas.md)

## Fields

### path
- type: string path
- default: empty string
- required: false
- semantics: roadmap document whose lifecycle was transitioned
- verify: json_path(path="$.path", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::RoadmapStatus`

### status
- type: string
- default: empty string
- required: false
- semantics: lifecycle status recorded on the roadmap
- verify: json_path(path="$.status", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::RoadmapStatus`

---
type: concept
slug: roadmap-status-field-roles
title: Roadmap status field roles
---
# Roadmap status field roles

`RoadmapStatus` reports the durable result of Author's final roadmap lifecycle transition.
Its two string fields have complementary roles: `path` identifies the roadmap document that
was transitioned, while `status` carries the lifecycle status written to that document.

Neither field supersedes the other or is a substitute for it. Consumers that need to identify
the transitioned roadmap use `path`; consumers that need the resulting lifecycle state use
`status`. The schema declares both fields with an empty-string default, so the source records
no further ranking or selection rule between them.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::RoadmapStatus`
- rule: use `path` for the transitioned roadmap's identity and `status` for its recorded lifecycle state; neither field is preferred over the other

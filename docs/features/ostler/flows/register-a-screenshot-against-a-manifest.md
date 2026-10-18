---
type: flow
slug: register-a-screenshot-against-a-manifest
title: Register a screenshot against a manifest
---
# Register a screenshot against a manifest

- start: a caller has a screenshot, a manifest of elements a QA scan expects, and a previously
  scanned regions file to replay against it
- steps:
  - [ostler vet](../cli.md#ostler-vet)
- end: the report records which documented elements matched a region, which were missing, and
  which rendered region the book never documented
- verify: json_path(path="summary.status", equals="disagreements")
- fixture: [vet manifest and regions](../fixtures/vet-manifest-and-regions.md)
- detail: [Vetting a rendered screen](../concepts/vetting-a-rendered-screen.md)

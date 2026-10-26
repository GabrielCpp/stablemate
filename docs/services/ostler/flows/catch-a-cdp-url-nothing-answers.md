---
type: flow
slug: catch-a-cdp-url-nothing-answers
title: Catch a CDP URL nothing answers
---
# Catch a CDP URL nothing answers

- start: a vet run names `--cdp-url` instead of `--regions`, and nothing is listening at that
  address
- steps:
  - [ostler vet](../cli.md#ostler-vet-cdp)
- end: the scan itself fails, named by the URL it tried, before a manifest is ever read or a
  report is ever built
- verify: exit_status(code=1)
- fixture: [vet manifest and regions](../fixtures/vet-manifest-and-regions.md)
- fixture: [edit scratch repo](../fixtures/edit-scratch-repo.md)
- detail: [Vetting a rendered screen](../concepts/vetting-a-rendered-screen.md)

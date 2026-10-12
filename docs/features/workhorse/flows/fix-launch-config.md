---
type: flow
title: Fix a launch's settings
---
# Fix a launch's settings

An author launches a workflow and gets the backend, config, profile or resume choice wrong. Each
refusal names what to change, and the author works through them until a dry run binds. The rules
behind each refusal are in [profiles and config](../concepts/profiles-and-config.md) and
[run launch](../concepts/run-launch.md).

- steps:
  - [fall-through-to-run](../workhorse.md#fall-through-to-run)
  - [refuse-cli-with-profile](../workhorse.md#refuse-cli-with-profile)
  - [refuse-missing-config](../workhorse.md#refuse-missing-config)
  - [refuse-unknown-profile](../workhorse.md#refuse-unknown-profile)
  - [refuse-profile-without-cli](../workhorse.md#refuse-profile-without-cli)
  - [refuse-undrivable-profile](../workhorse.md#refuse-undrivable-profile)
  - [refuse-two-resume-flags](../workhorse.md#refuse-two-resume-flags)
  - [refuse-unknown-resume-run](../workhorse.md#refuse-unknown-resume-run)
  - [refuse-no-resumable-run](../workhorse.md#refuse-no-resumable-run)
  - [dry-run-workflow](../workhorse.md#dry-run-workflow)
- fixture: seeded-runs
- end: the corrected launch binds every node
- verify: stdout(matches="dry-run ok")
- detail: [profiles and config](../concepts/profiles-and-config.md)

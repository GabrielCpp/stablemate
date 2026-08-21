---
type: story
id: DEPO-01M0JD6ETES74DX0Q5CHHDY1BC
slug: deploy-identity
status: Not started
---
# Story: One deploy identity, one grant, and a nightly sweep

## Dependencies

- Blocked by: artifact-store

## Context

The depot now has somewhere to publish to; this story declares who publishes, what it is
allowed to do, and what expires the result.

The grant is the story. An identity handed to a pipeline is an identity that will end up in a
CI secret store, so what matters is not that it exists but how little it holds: a bucket-level
role on the artifact store alone, never a project role. The two are equally short to write and
only one of them is visible as a difference in the plan.

The sweep arrives in the same story because it is the piece that fails silently. Nothing breaks
when a scheduler job is missing — the depot keeps working and simply stops forgetting — so its
presence has to be something the plan is read for rather than something an outage reports.

## Acceptance Criteria

- The plan creates one deploy service account, and grants it an object-level role on the
  artifact bucket alone — no project-level role is granted to it anywhere in the plan.
- The deploy token reaches the secret version as a secret, so the plan reports its value as
  `[secret]` and no preview prints it.
- The token is stored encrypted in the stack's configuration, so the plan's configuration
  listing reports it as `[secret]` rather than as its value.
- The plan contains exactly one Cloud Scheduler job, running nightly at 03:00 in an explicitly
  stated time zone.
- `make -C pulumi build` and `make -C pulumi plan` still succeed with the identity and the
  sweep added.

## Implementation Status

- **Status**: Not started

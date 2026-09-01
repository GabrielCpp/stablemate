---
type: story
id: DEPO-01M0JD6ETES74DX0Q5CHHDY1BC
slug: deploy-identity
status: Not started
---
# Story: One deploy identity, one grant, and a nightly sweep

## Dependencies

- Blocked by: artifact-store

## Fixtures

(none)

<!-- The stack arranges itself: `make -C pulumi plan` selects the `dev` stack against a local
file backend and writes the preview this story reads. What the run needs beforehand — the Go
module cache and the `gcp` resource plugin — is warmed once with the stack, not per scenario. -->

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

## Non-Functional Acceptance Criteria

(none)

## Technical Notes

- `pulumi/bucket.go::artifactStore` declares the bucket and its readers binding, and takes the
  provider as a `pulumi.ResourceOption` rather than reaching for a default — a new resource
  earns the pinned provider by being passed the same option.
- `pulumi/bucket.go::artifactBucketName` is the name every later grant has to refer to, so a
  bucket-level role is written against it rather than against a project.
- `pulumi/main.go::main` is the one composition point: it builds the pinned provider and calls
  each declaration, which is where a new one is attached.
- `pulumi/main.go::providerVersion` is the pin itself.

## Implementation Status

- **Status**: Not started

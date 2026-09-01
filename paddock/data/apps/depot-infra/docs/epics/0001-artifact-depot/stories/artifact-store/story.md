---
type: story
id: DEPO-01M0JD6ET7WCH0GRFHVQGP1M7V
slug: artifact-store
status: Not started
---
# Story: Publish artifacts to a bucket only the build group reads

## Dependencies

(none)

## Fixtures

(none)

<!-- The stack arranges itself: `make -C pulumi plan` selects the `dev` stack against a local
file backend and writes the preview this story reads. What the run needs beforehand — the Go
module cache and the `gcp` resource plugin — is warmed once with the stack, not per scenario. -->

## Context

The first story is the program itself and the thing it exists to declare: the module, the
stack's configuration, the Makefile that takes a plan, and the bucket every build writes into
with the binding that says who reads it.

The binding ships with the bucket rather than in a later story on purpose. A bucket declared
first and granted later is a bucket whose readers are whoever the project already had, and a
plan taken in between says nothing about that — the plan only ever shows what the program
declares, so an access rule that lives outside the program is invisible to every check that
reads one.

Nothing here is applied. `make -C pulumi plan` is the whole of the observable surface, and
[the runbook](../../../../features/depot/ops/preview-the-plan.md) is how it is taken.

## Acceptance Criteria

- `make -C pulumi build` compiles the program against the pinned provider SDK, and
  `make -C pulumi plan` writes a plan to `pulumi/preview.json` without a credential and
  without reaching a Google API.
- The plan creates the artifact bucket with uniform bucket-level access on, so no object may
  carry an ACL of its own.
- The plan creates that bucket with force-destroy off and versioning on, so neither a teardown
  aimed elsewhere nor an overwrite loses a published artifact.
- The plan's readers binding on that bucket lists exactly the build group, and never `allUsers`
  or `allAuthenticatedUsers`.
- The provider the plan is produced by is pinned by the program rather than resolved from
  whatever plugin the machine has installed.

## Non-Functional Acceptance Criteria

(none)

## Technical Notes

No prior implementation reference exists.

## Implementation Status

- **Status**: Not started

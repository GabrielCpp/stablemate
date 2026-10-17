---
type: spec.plan
---

# Plan: Publish Artifacts to a Bucket Only the Build Group Reads

## 0. Status

This story is **implemented**. The plan is retained as a description of the shipped shape, not a
work order to rebuild it.

## 1. Approach

A Pulumi Go program against the `gcp` provider, planned into `pulumi/preview.json` and never
applied. The stack's backend is a local file backend and its passphrase is stated in the
Makefile, so a plan taken by a check and a plan taken by a person are the same plan.

The provider is pinned at the provider, in the program. A version left to whatever the machine
resolves is a version that changes defaults underneath a program nobody edited, and the plan
that reports the change looks exactly like the plan that did not.

## 2. Files

- `pulumi/main.go` — the entry point, the provider and its pin.
- `pulumi/bucket.go` — the artifact bucket and the readers binding.
- `pulumi/Pulumi.yaml`, `pulumi/Pulumi.dev.yaml` — the project and the `dev` stack's config.
- `pulumi/Makefile` — `build`, `vet`, `preview`, `plan`; the backend and passphrase live here.

## 3. Acceptance Checklist

- [x] The plan declares one artifact bucket, with uniform bucket-level access on.
- [x] The bucket keeps object versioning on and force-destroy off.
- [x] The readers binding on the artifact bucket lists exactly the build group, and no public member.
- [x] The plan is produced by the documented command and names the pinned provider version.

## 4. QA

There is no target to reach and no fixture to seed: `make -C pulumi plan` is the whole
mechanism, and the artifact it writes is the whole evidence. `agents.yml` opts this app's QA
into `make` and `jq` for exactly that, and into nothing else.

Two shapes of assertion are worth telling apart. A property of a resource is read at its path
and compared. A *negative* — no public member on the binding — is read as the whole member
list, because a check that asserts the build group is present passes on a binding that also
holds `allUsers`.

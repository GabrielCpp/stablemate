---
type: spec.plan
---

# Plan: One Deploy Identity, One Grant, and a Nightly Sweep

## 0. Status

This story is **implemented**. The plan is retained as a description of the shipped shape, not a
work order to rebuild it.

## 1. Approach

Two more files on the program story 1 shipped, and two edits to the two files a program cannot
split: `main.go` gains the calls, and the stack's config gains the deploy token.

The grant is written at the bucket rather than at the project, and the role is an object-level
one. Both halves matter separately: a project-level binding with a narrow role is still a
project-level binding, and a bucket-level binding with `roles/editor` is still editor.

## 2. Files

- `pulumi/identity.go` — the service account, its one bucket-level grant, the secret and the
  secret version holding the deploy token.
- `pulumi/scheduler.go` — the nightly artifact sweep.
- `pulumi/main.go` — changed: the entry point calls both.
- `pulumi/Pulumi.dev.yaml` — changed: the stack's config gains the deploy token, encrypted.

## 3. Acceptance Checklist

- [x] The deploy identity's only grant is a bucket-level grant on the artifact store, naming an object-level role.
- [x] No project-level role is granted anywhere in the plan.
- [x] The deploy token reaches the secret version as a secret value, and the plan reports it as `[secret]`.
- [x] The plan declares exactly one Cloud Scheduler job — the artifact sweep — nightly at 03:00 in `Etc/UTC`.

## 4. QA

The same mechanism as story 1: `make -C pulumi plan`, and the JSON it writes.

Two of these criteria are negatives, and both are asserted over the whole plan rather than over
a named resource. "No project-level role" cannot be proved by reading the grant this story
declares — a second, wider grant beside it is exactly the defect — so the assertion enumerates
every IAM resource in the plan and objects to the ones that are not bucket-level. The scheduler
count is the same shape: one job, asserted as a count over the plan, because a check that reads
the sweep's own schedule passes on a plan that also declares a second job beside it.

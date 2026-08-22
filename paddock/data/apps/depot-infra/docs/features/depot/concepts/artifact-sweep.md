---
type: concept
slug: artifact-sweep
title: The artifact sweep
---
# The artifact sweep

- code: pulumi/scheduler.go
- extends:
- consistency: artifact-sweep-job — the plan contains exactly one Cloud Scheduler job — the artifact sweep.
- consistency: artifact-sweep-job — the sweep runs nightly at 03:00 in `Etc/UTC`, stated as an absolute zone so the
  hour does not move under a machine's local time.

Artifacts expire because something deletes them on a schedule. That something is a scheduler job
declared in this program, and it is the piece of the depot most easily lost: nothing fails when it
is missing. The bucket keeps working, every other check passes, and the store grows until somebody
reads the bill.

So the sweep's presence is itself the claim. A plan that does not contain it is a plan that has
stopped expiring artifacts, and that is only visible to a reader who was told to count.

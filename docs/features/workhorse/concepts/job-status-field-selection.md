---
type: concept
slug: job-status-field-selection
title: Job status field selection
---
# Job status field selection

`JobStatus` is one status snapshot, not a set of alternative representations. `poll()` constructs
every member from the job directory, its handle and manifest, the runner record, the current clock,
and the result file in `workhorse/workhorse/job.py::poll`; its declared record is
`workhorse/workhorse/job.py::JobStatus`.

Read `state` first to classify the lifecycle as `missing`, `running`, `finished`, or `lost`. Use
`alive` to distinguish an actively supervised process group from a stale or absent one. For a
running or finished job, `elapsed_s` reports observed duration; compare it with `estimate_s` and
use `overrun_multiple` for the largest announced doubled threshold. `result_ready` says whether
the manifest-selected result file exists, while `tier` says which containment tier was recorded in
the handle. These fields are complementary observations of the same poll, so no field supersedes
or ranks above another.

- code: `workhorse/workhorse/job.py::JobStatus`
- code: `workhorse/workhorse/job.py::poll`
- rule: select the field that answers the lifecycle, liveness, timing, result-readiness, or containment question; no JobStatus field is a replacement for another

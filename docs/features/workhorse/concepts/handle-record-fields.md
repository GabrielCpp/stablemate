---
type: concept
slug: handle-record-fields
title: Handle record fields
---
# Handle record fields

`Handle` is the persisted identity record for one detached supervisor. Its `job_dir`, `pid`,
`pgid`, `started_at`, `tier`, and `labels` values are distinct attributes of that record; the
parent `Handle` field describes the record as a whole. Callers read the attribute required for
their operation rather than selecting one field as an alternative to another.

No field supersedes another. The source declares all six attributes together when `submit`
creates a handle, and `_handle_of` restores every attribute from a recorded handle.

- code: `workhorse/workhorse/job.py::Handle`
- rule: use `Handle` for the supervisor identity record and its named fields for their distinct values; no field is a preferred or deprecated alternative

---
type: concept
slug: machine-scratch
title: Machine scratch directory
---
# Machine scratch directory

Machine scratch is disposable cache state that is never the only copy of run work. It is kept
under the configured Stablemate cache rather than a repository, and is separated by producer and
the resolved absolute subject path so two same-named checkouts cannot share a profile.

- code: `workhorse/workhorse/scratch.py::scratch_dir`
- persistence: scratch-directory — `scratch_dir` creates `<cache-root>/scratch/<kind>/<subject-slug>` when absent

### scratch_dir
- sig: `scratch_dir(kind: str, subject: Path | str) -> Path`
- does: resolves the subject path and combines its readable basename with a ten-character SHA-256 digest
- returns: an existing directory safe for disposable producer state
- verify: created(subject="the scratch directory for the producer and subject")
- code: `workhorse/workhorse/scratch.py::scratch_dir`
- tests: `workhorse/tests/test_scratch.py::test_two_checkouts_with_the_same_name_get_different_scratch`

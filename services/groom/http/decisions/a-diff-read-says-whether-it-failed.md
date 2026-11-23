story: SM-01M6CP871J1D23N6KMN0Z77FWX
date: 2026-11-23
elements: ReadDiff
sources: groom/groom/gitdiff.py, groom/groom/sidecar.py, groom/groom/app.py

A caller that reads a run's diff must tell a clean checkout from a read that did not happen, so the reply says which it was. Either git command failing or timing out fails the whole read, because a diff without its untracked list would claim a partial truth. A sidecar with no checkout to read reports a failed read, not an empty diff.

The sidecar's `getDiff` keeps its `diff` field and adds `untracked` and `failed` beside it, so a consumer that reads only `diff` keeps working. The `/diff/` reply adds `reported`, which is false when the sidecar sent no `failed`. An empty diff with `reported` false comes from a sidecar too old to report failure, so it cannot confirm there are no changes.

This extends `a-pushed-run-has-no-workspace`: a read with no volume and no sidecar answers as a failed read with an empty body.

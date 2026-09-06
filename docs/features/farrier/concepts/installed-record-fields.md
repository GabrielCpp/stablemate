---
type: concept
slug: installed-record-fields
title: Installed record fields
---
# Installed record fields

`Installed` records one pipx distribution that exposes at least one workflow. Its fields are
complementary facts, not competing representations: `distribution` identifies the installed
package; `workflows` lists its runnable `workhorse-<name>` suffixes; `origin` retains pipx's
package name, remote URL, or host path; `version` identifies the installed release; and `editable`
records whether pipx received `--editable`.

No field ranks above another or substitutes for another. Consumers use the field that answers
their question: workflow selection uses `workflows`, local-source mounting uses `origin` together
with `editable`, and diagnostics identify the installed package with `distribution` and `version`.
This distinction matters because a local origin can remain a path after its directory disappears,
allowing the stale source to be reported rather than treated as a package name.

- code: `farrier/farrier/pipx.py::Installed`
- rule: use each field for its distinct record attribute; no field is a preferred replacement for another

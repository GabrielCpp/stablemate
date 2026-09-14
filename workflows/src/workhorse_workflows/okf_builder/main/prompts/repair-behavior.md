# okf-builder - Repair a source-backed behavior gap

Reconcile the affected file or book nodes with these audited source findings. Work on
the book under `{{ features_root }}`; source under `{{ source_root }}` is evidence,
not a repair target. Group related findings into coherent node edits, preserving the
existing node identities and citations. Read the named source to resolve context.
The next gates re-read doctor, symbol coverage, and the two-way semantic audit.

If a finding cannot be grounded, return `partial` with the unresolved reason instead
of inventing behavior or removing a claim merely to clear the audit. Discoveries name
additional documentation work, not implementation changes.

Docs only: write under `{{ features_root }}` and nowhere else. Never run `git` commands
that change the tree — `stash`, `checkout`, `restore`, `reset` — other runs are editing
this checkout uncommitted, and those commands discard their work. Do not run a full
`ostler doctor`; the next gate runs it.

The book was committed just before this turn, so `git diff -- {{ features_root }}` shows exactly
what you changed, and undoing an edit means editing the file back. `{{ baseline }}` is the same
book as a plain copy, for when that commit could not land. Do not commit yourself: the run commits
the book after this turn under your `commit_message`, a `docs({{ service }}): <what changed>`
subject of 72 characters at most, left empty when you changed nothing.

Target: {{ item_target }}

{{ item_context }}

Produce a JSON document complying with this schema:

{{ result_schema }}

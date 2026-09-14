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

Your change is measured against `{{ baseline }}`, a copy of the book taken just before
this turn: `diff -ru {{ baseline }} {{ features_root }}` shows exactly what you changed,
and undoing an edit means copying that file back from the baseline. Never use `HEAD` for
either — this run commits the book only when it is complete, so `git diff` also shows the
run's earlier uncommitted repairs, and restoring from `HEAD` erases them.

Target: {{ item_target }}

{{ item_context }}

Produce a JSON document complying with this schema:

{{ result_schema }}

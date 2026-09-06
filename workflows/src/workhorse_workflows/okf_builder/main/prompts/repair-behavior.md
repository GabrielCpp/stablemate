# okf-builder - Repair a source-backed behavior gap

Reconcile the affected file or book nodes with these audited source findings. Work on
the book under `{{ features_root }}`; source under `{{ source_root }}` is evidence,
not a repair target. Group related findings into coherent node edits, preserving the
existing node identities and citations. Read the named source to resolve context.
The next gates re-read doctor, symbol coverage, and the two-way semantic audit.

If a finding cannot be grounded, return `partial` with the unresolved reason instead
of inventing behavior or removing a claim merely to clear the audit. Discoveries name
additional documentation work, not implementation changes.

Target: {{ item_target }}

{{ item_context }}

Produce a JSON document complying with this schema:

{{ result_schema }}

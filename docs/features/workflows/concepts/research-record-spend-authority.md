---
type: concept
slug: research-record-spend-authority
title: Which record_spend doc is authoritative
---
# Which record_spend doc is authoritative

[Research deterministic nodes](research-deterministic-nodes.md) documents the research node
package's public `@blueprint.node` surface — the functions a workflow state actually calls.
`record_spend` carries that decorator
(`workflows/src/workhorse_workflows/research/nodes/program.py:196`), so its `### record_spend`
entry there is the one a workflow author or state consults for what the node does, raises, and
returns.

[Research program manifest](research-program-manifest.md) documents the plain, undecorated
path-resolution and ledger helpers `program.py` is built from — `parse_flat_yaml`, `slug`,
`launch_dir`, `resolve_repo_root`, `ledger_path`, `read_ledger`, and the rest — none of which
carry `@blueprint.node`. `record_spend` writes through the same `ledger_path`/`LEDGER_HEADER`
machinery that doc already documents, which is why it also lists a `### method: record_spend`
entry; that entry is a second, independent write-up of the same node rather than something only
that document can say.

- rule: the `@blueprint.node`-decorated public interface is documented once, in research deterministic nodes; a manifest- or helper-scoped document may still list a node for context, but points here for what it does rather than restating it.
- prefers: [research deterministic nodes](research-deterministic-nodes.md#record_spend)
- deprecates: [research program manifest](research-program-manifest.md#method-record_spend)

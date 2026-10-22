---
type: concept
slug: research-program-load-authority
title: Which load_program doc is authoritative
---
# Which load_program doc is authoritative

[Research deterministic nodes](research-deterministic-nodes.md) documents the research node
package's public `@blueprint.node` surface — the functions a workflow state actually calls.
`load_program` carries that decorator
(`workflows/src/workhorse_workflows/research/nodes/program.py:236`), so its `### load_program`
entry there is the one a workflow author or state consults for what the node does, raises, and
returns.

[Research program manifest](research-program-manifest.md) documents the plain functions
`load_program` is built from — `parse_flat_yaml`, `slug`, `launch_dir`, `resolve_repo_root`,
`detect_program_from_launch`, `read_agents_yaml_program`, `read_pointer`, `ledger_path`,
`read_ledger` — none of which carry `@blueprint.node` and none of which are documented
anywhere else. That is the manifest doc's reason to exist; its own `### method: load_program`
entry is a second, independent write-up of the same node rather than something only that
document can say.

- rule: the `@blueprint.node`-decorated public interface is documented once, in research deterministic nodes; a manifest- or helper-scoped document may still list a node for context, but points here for what it does rather than restating it.
- prefers: [research deterministic nodes](research-deterministic-nodes.md#load_program)
- deprecates: [research program manifest](research-program-manifest.md#method-load_program)

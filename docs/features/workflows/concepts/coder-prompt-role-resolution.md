---
type: concept
slug: coder-prompt-role-resolution
title: Coder prompt role resolution
---
# Coder prompt role resolution

The resolver turns a registered coder role into the calling flow's prompt envelope, the
optional replacement-body arguments, and the Pydantic reply model that the caller passes back
to the agent. A role is the envelope stem, so the same role may have one envelope in each flow
while one repo or library replacement applies to every copy.

- code: `workflows/src/workhorse_workflows/coder/shared/roles.py::ROLES`
- tests: `workflows/tests/coder/shared/test_roles.py`

The resolver checks overrides in this order: a valid repo-relative or absolute file named by the
repo's `agents.yml` `prompts:` mapping, the first matching `library/prompts/coder/<role>.md` in
the ordered library directories, and finally no body override so the workflow envelope renders
its bundled default. Missing, malformed, or nonexistent overrides are treated as no override.
The repo may put `prompts:` at the top level or under `workflow:`.

## Fields

### prompt

- type: string, flow-relative prompt envelope path
- required: true
- verify: json_path(path="$.prompt", matches="^[^/]+/prompts/[^/]+\\.md$")
- semantics: `<flow>/prompts/<role>.md` selected from the flow class's defining module
- verify: json_path(path="$.prompt", equals="dev/prompts/plan-story.md")
- code: `workflows/src/workhorse_workflows/coder/shared/roles.py::Turn`
- detail: [Coder Turn Record](turn-record.md)

### args

- type: `dict[str, Any]`
- required: true
- verify: json_path(path="$.result_schema", absent=false)
- semantics: always contains the rendered `result_schema`
- verify: json_path(path="$.result_schema", matches="^Produce a JSON document that complies with this schema:")
- semantics: when a body override is found, contains its parent directory as `_body_dir`
- verify: json_path(path="$._body_dir", matches=".+/.+")
- semantics: when a body override is found, contains its namespaced template as `body_template`
- verify: json_path(path="$.body_template", matches="^body/[^/]+\\.md$")
- code: `workflows/src/workhorse_workflows/coder/shared/roles.py::Turn`
- detail: [Coder Turn Record](turn-record.md)

### returns

- type: `type[T]`, where `T` is a Pydantic `BaseModel`
- required: true
- semantics: the same reply model used to render `result_schema` and parse the agent response
- code: `workflows/src/workhorse_workflows/coder/shared/roles.py::Turn`
- detail: [Coder Turn Record](turn-record.md)

## Methods

### turn

- sig: `turn(flow: Any, role: str, *, returns: type[T]) -> Turn[T]`
- does: rejects a role absent from `ROLES` before prompt rendering
- verify: json_path(path="$.exception.message", matches="^unknown prompt role")
- does: selects the envelope under the calling flow's package directory
- verify: json_path(path="$.prompt", equals="dev/prompts/plan-story.md")
- does: renders the supplied reply model into the `result_schema` argument
- verify: json_path(path="$.args.result_schema", matches="^Produce a JSON document that complies with this schema:")
- does: adds body override arguments only when a valid repo or library body exists
- verify: json_path(path="$.args.body_template", absent=true)
- raises: `WorkflowFailed` for an unregistered role or a flow class defined outside `workhorse_workflows.coder`
- verify: json_path(path="$.exception.type", equals="WorkflowFailed")
- returns: a `Turn` containing the envelope path, render arguments, and supplied reply model
- verify: json_path(path="$.returns", equals="FixResult")
- code: `workflows/src/workhorse_workflows/coder/shared/roles.py::turn`
- tests: `workflows/tests/coder/shared/test_roles.py::test_an_unregistered_role_is_caught_on_the_transition`
- tests: `workflows/tests/coder/shared/test_roles.py::test_the_envelope_is_the_calling_flows_own_copy`

### flow_dir

- sig: `flow_dir(flow: Any) -> str`
- does: derives the one-level flow directory from the defining module below `workhorse_workflows.coder`
- verify: json_path(path="$.flow_dir", equals="dev")
- raises: `WorkflowFailed` when the flow is defined outside the coder package
- verify: json_path(path="$.exception.type", equals="WorkflowFailed")
- returns: the flow package name used to prefix its prompt envelope path
- verify: json_path(path="$.flow_dir", equals="dev")
- code: `workflows/src/workhorse_workflows/coder/shared/roles.py::flow_dir`
- tests: `workflows/tests/coder/shared/test_roles.py::test_a_flow_defined_outside_the_package_is_caught_rather_than_mispathed`

The private body helpers are part of `turn`'s contract: `_body` applies repo, overlay, and base
precedence; `_repo_prompts` reads only string-valued mappings and tolerates absent, malformed,
or non-mapping configuration. No external service or persistence is involved.

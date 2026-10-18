---
type: concept
slug: coder-render-schema-contracts
title: Coder rendered schema contracts
---
# Coder rendered schema contracts

The Coder prompt contract is generated from the Pydantic model that parses the same agent reply.
The renderer frames the schema as a JSON document to produce, removes generated object and field
titles, removes object-level class-docstring descriptions, and retains descriptions attached to
individual fields. The companion inspection function walks the root model and every nested model
definition and returns each property whose description is empty, allowing the output-contract
tests to enforce agent-facing field prose.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/render.py::schema_block` @19e01d6482cb
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/render.py::described_fields` @19e01d6482cb
- tests: `workflows/tests/coder/test_output_contracts.py::test_rendered_contracts_ask_for_a_document`
- tests: `workflows/tests/coder/test_output_contracts.py::test_rendered_models_describe_every_field`

## Fields

### field: PREAMBLE
- type: string
- default: `Produce a JSON document that complies with this schema:`
- required: true
- semantics: text placed before every rendered JSON schema so the agent is instructed to produce a document rather than echo the schema
- verify: json_path(path="$.preamble", equals="Produce a JSON document that complies with this schema:")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/render.py::PREAMBLE` @19e01d6482cb

## Methods

### schema_block
- sig: `schema_block(model: type[BaseModel]) -> str`
- does: obtains the supplied model's JSON schema
- verify: count(subject="schema JSON schema generation", equals=1)
- does: removes generated titles from object and field schemas while retaining descriptions attached to fields
- verify: removed(subject="generated title metadata from the rendered schema")
- verify: count(subject="pruned rendered schema metadata", equals=1)
- does: serializes the pruned schema as indented UTF-8 JSON with two-space indentation
- verify: count(subject="indented rendered schema bodies", equals=1)
- does: returns the preamble, a blank line, a fenced json block, and the serialized schema in that order
- verify: count(subject="complete rendered output contracts", equals=1)
- does: frames the block as a document to produce
- verify: count(subject="rendered contracts beginning with the preamble", equals=1)
- does: strips the `"title"` field pydantic would otherwise emit on the object and its fields
- verify: removed(subject="pydantic-derived \"title\" keys from the rendered JSON block")
- returns: a string suitable for insertion into a Coder prompt
- verify: count(subject="schema blocks inserted into Coder prompts", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/render.py::schema_block` @19e01d6482cb
- tests: `workflows/tests/coder/test_output_contracts.py::test_rendered_contracts_ask_for_a_document`

### described_fields
- sig: `described_fields(schema: dict[str, Any]) -> list[str]`
- does: inspects the root schema and each schema in `$defs` for properties without non-blank descriptions
- verify: count(subject="schema properties checked for descriptions", equals=1)
- returns: property identities formatted as `<model>.<field>` for every undescribed property, or an empty list when all properties are described
- verify: json_path(path="$.undescribed_fields", matches="^\[.*\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/render.py::described_fields` @19e01d6482cb
- tests: `workflows/tests/coder/test_output_contracts.py::test_rendered_models_describe_every_field`

### _models
- sig: `_models(schema: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]`
- does: includes the input schema under its title or `root` and appends every `$defs` entry under its definition name
- verify: count(subject="root and nested schema models enumerated", equals=1)
- returns: model names paired with their schema dictionaries in root-first order
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/render.py::_models` @19e01d6482cb

### _pruned
- sig: `_pruned(value: Any) -> Any`
- does: recursively copies dictionaries and lists while removing `title` from every dictionary
- verify: removed(subject="title metadata from the rendered schema")
- verify: count(subject="schema title metadata removed", equals=1)
- does: additionally removes `description` only from dictionaries that contain `properties`, preserving property-level descriptions
- verify: removed(subject="object-level descriptions from the rendered schema")
- verify: count(subject="object-level schema descriptions removed", equals=1)
- does: keeps a field whose own name is `title` or `description`, since it prunes the values of the `properties` mapping and not the mapping's keys
- verify: count(subject="fields named title or description kept in the rendered schema", equals=1)
- does: keeps the first line of every class docstring out of the rendered contract, since pydantic would otherwise lift it onto the object-level `description` and leak the maintainer's rationale to the agent
- verify: absent(subject="class docstring text inside the rendered output contract")
- returns: the recursively pruned value, leaving scalar values unchanged
- verify: count(subject="scalar schema values left unchanged", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/render.py::_pruned` @19e01d6482cb
- tests: `workflows/tests/coder/test_output_contracts.py::test_class_docstrings_stay_out_of_the_contract`

---
type: flow
slug: read-a-stack-files-json-schema
title: Read a stack file's JSON Schema
---
# Read a stack file's JSON Schema

- start: a caller writing a book's ops/stack.yml does not know which keys it accepts
- steps:
  - [ostler env schema](../cli.md#ostler-env-schema)
- end: the caller has the JSON Schema a stack.yml is validated against, straight from the
  code-declared key table
- verify: json_path(path="$schema", equals="https://json-schema.org/draft/2020-12/schema")
- fixture: none, because the schema is built from code, not read from any stack.yml

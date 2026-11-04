---
type: format
slug: tool-server-record
title: Tool server record
---
# Tool server record

A tool server record is one YAML file, `library/mcp/<name>.yml`, that declares one MCP server in no
harness's spelling. The file name is the name a `[user_library.<harness>]` table lists in `mcp`, and
the name the server takes in each harness. [Merged home entries](../concepts/merged-home-entry.md)
are rendered from it.

- file: `library/mcp/<name>.yml` in any library layer, the highest layer holding the name winning
- code: `farrier/farrier/home_entries.py::ToolServer` @734d8438ec2c
- detail: [merged home entry](../concepts/merged-home-entry.md)

## Fields

### field: command
- type: string
- required: true
- semantics: the program the harness starts

### field: args
- type: list of strings
- default: `[]`
- semantics: the program's arguments

### field: env
- type: mapping of strings
- default: `{}`
- semantics: the environment the program starts with, written to the harness config in clear

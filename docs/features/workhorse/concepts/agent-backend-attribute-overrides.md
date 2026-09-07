---
type: concept
slug: agent-backend-attribute-overrides
title: AgentBackend attribute overrides
---
# AgentBackend attribute overrides

Every backend starts with the `AgentBackend` defaults and overrides only the attributes its CLI
changes. These are independent capabilities, not interchangeable implementation choices: an
adapter always needs its own `name`; it sets `default_model` only when it supplies a model rather
than leaving selection to its CLI; and it sets `supports_compaction` only when it can compact a
session in place. The resilience ladder uses the last value to choose compaction or prompt
reframing after context overflow.

- code: `workhorse/workhorse/runner/backends/__init__.py::AgentBackend`
- rule: retain each base attribute unless the CLI changes that capability; override `name` for the registry key, `default_model` for a backend-provided model, and `supports_compaction` only for in-place session compaction
- detail: [AgentBackend documentation scope](agent-backend-documentation-scope.md)

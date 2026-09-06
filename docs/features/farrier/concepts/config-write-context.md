---
type: concept
slug: config-write-context
title: Config write documentation contexts
---
# Config write documentation contexts

`write_config_key` is one shared writer in `stablemate-core`, not two alternative
implementations. Its source describes a top-level string-key write that preserves the rest of the
TOML file, folds legacy files into the unified path, migrates older schemas, and refuses schemas
newer than the running core understands.

The [Farrier home-config node](../home-config.md#reading-and-writing) presents that writer in the
context of Farrier's user-facing configuration commands and explains why those commands cannot
write nested tables. The [Workhorse config node](../../workhorse/concepts/config.md#write_config_key)
is the cross-tool persistence reference: it describes the shared API, schema guard, wrappers, and
consumers. Both views are current, and neither supersedes the other.

- rule: use the Farrier node for command-facing configuration behavior and the Workhorse node for the shared persistence API and its cross-tool consumers; neither node is preferred or deprecated

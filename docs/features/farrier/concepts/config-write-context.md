---
type: concept
slug: config-write-context
title: Config write documentation contexts
---
# Config write documentation contexts

`write_config_key` is one shared writer in `stablemate-core`, not two alternative
implementations. Its source describes a top-level string-key write that preserves the rest of the
TOML file, folds legacy files into the unified path, migrates older schemas, and refuses schemas
newer than the running core understands. `write_library_dir` is its `library_dir`-specific wrapper,
calling that same writer with the path converted to a string.

The [Farrier home-config node](../home-config.md#reading-and-writing) presents that writer in the
context of Farrier's user-facing configuration commands and explains why those commands cannot
write nested tables. The [Workhorse config node](../../workhorse/concepts/config.md#write_config_key)
is the cross-tool persistence reference: it describes the shared API, schema guard, wrappers, and
consumers. Both views are current, and neither supersedes the other.

The [library-directory node](library-directory.md#persisting-the-config-file-candidate) documents
the same `write_library_dir` call at the library-resolution boundary: it explains how
`farrier config set-library` validates and saves the third-precedence overlay candidate. The
[home-config method](../home-config.md#write_library_dir) is the API reference for the wrapper's
single-key persistence behavior. Both are current views of one implementation, not competing
implementations to select between.

- rule: use the library-directory node for the validated `set-library` resolution path, the home-config method for the `write_library_dir` API contract, the Farrier node for other command-facing configuration behavior, and the Workhorse node for the shared persistence API and cross-tool consumers; these views are contextual and none is preferred or deprecated

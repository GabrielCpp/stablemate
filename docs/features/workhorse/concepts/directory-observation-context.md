---
type: concept
slug: directory-observation-context
title: Directory observation context
---
# Directory observation context

`DirectoryObservation` is the per-directory record produced while `observe_scope` walks the
declared cwd and additional directories. It is not an alternative to repository observation:
the repository-observation surface describes the module's observation APIs, scope deduplication,
and snapshot, while the directory-observation-fields concept describes the identity facts carried
by each resulting record. Both are current and neither replaces the other.

Use the repository observation when choosing an API that captures repository or execution-scope
state. Use directory observation fields when reading or serializing the identity of one entry in
that scope. Git-backed entries include their resolved root, origin, branch, and HEAD; unversioned
entries retain their resolved path and role with empty Git identity fields.

- rule: use repository observation for scope and API behavior; use directory observation fields for one scope entry's identity facts

---
type: concept
slug: directory-observation-fields
title: Directory observation fields
---
# Directory observation fields

`DirectoryObservation` describes one distinct directory in an execution scope. Its fields are
complementary rather than competing implementations. Select `path` to identify the resolved
directory, `role` to distinguish the primary cwd from an additional directory, and `vcs` to tell
whether Git identity is available. For a Git directory, use `root`, `origin`, `branch`, and `head`
for the corresponding observed identity facts; for an unversioned directory, those optional Git
fields remain empty. Consumers that need the complete scope entry use the record as a whole or its
string-valued serialization.

- code: `workhorse/workhorse/gitstate.py::DirectoryObservation`
- rule: select the field for the distinct directory identity fact being read; the fields are complementary and have no ranking or replacement relationship
- detail: [Directory observation context](directory-observation-context.md)

---
type: format
slug: epic-split-context
title: Epic split context
---
# Epic split context

The context is the immutable boundary captured before an epic-split agent turn. It identifies the
approved roadmap and its milestone and records graph identities and content fingerprints used to
reject collateral edits.

- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitContext`
- detail: [author epic split subflow](concepts/author-epic-split-subflow.md)

## Fields

### repo_root
- type: string path
- required: true
- semantics: repository root used for all graph reads and validation
- verify: json_path(path="$.repo_root", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitContext`

### roadmap
- type: string repository-relative path
- required: true
- semantics: approved roadmap that must be the milestone's sole source
- verify: json_path(path="$.roadmap", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitContext`

### epics_dir
- type: string path
- required: true
- semantics: configured directory in which epic skeletons are created
- verify: json_path(path="$.epics_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitContext`

### milestone_path
- type: string repository-relative path
- required: true
- semantics: roadmap-owned milestone document selected for splitting
- verify: json_path(path="$.milestone_path", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitContext`

### existing_epics
- type: list of strings
- default: empty list
- required: true
- semantics: epic names present before the split
- verify: json_path(path="$.existing_epics", equals=[])
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitContext`

### milestone_fingerprints
- type: string-to-string map
- default: empty map
- required: true
- semantics: SHA-256 content fingerprints for all milestone documents before the split
- verify: json_path(path="$.milestone_fingerprints", equals={})
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitContext`

### epic_fingerprints
- type: string-to-string map
- default: empty map
- required: true
- semantics: SHA-256 content fingerprints for all existing epic documents before the split
- verify: json_path(path="$.epic_fingerprints", equals={})
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitContext`

### seed_ids
- type: map from epic name to seed-id list
- default: empty map
- required: true
- semantics: seed identities that validation requires to remain unchanged
- verify: json_path(path="$.seed_ids", equals={})
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitContext`

### story_slugs
- type: map from epic name to story-slug list
- default: empty map
- required: true
- semantics: story identities that validation requires to remain unchanged
- verify: json_path(path="$.story_slugs", equals={})
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitContext`

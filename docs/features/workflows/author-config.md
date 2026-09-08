---
type: format
slug: author-config
title: Author workflow configuration
---
# Author workflow configuration

The resolved author paths and layer hints passed from setup to the story-split flow. Paths other
than `repo_root` are repository-relative. `load_config` resolves the consuming repository from its
explicit `repo_dir` input, follows the repository's configured Ostler document roots, and validates
the intake required by the selected mode. The feature book is read-only grounding; configuration
loading does not create a surface inventory.

- code: `workflows/src/workhorse_workflows/author/main/nodes/config.py::load_config`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`
- detail: [author shared paths](concepts/author-shared-paths.md)
- detail: [approved roadmap](concepts/approved-roadmap.md)
- detail: [author story-split subflow](concepts/story-split-subflow.md)
- detail: [author load_config documentation roles](concepts/author-load-config-documentation-roles.md)

## Fields

### repo_root
- type: string path
- default: empty string
- required: false
- semantics: absolute repository root selected from the explicit input or repository markers and used for graph and artifact operations
- verify: json_path(path="$.repo_root", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`
- detail: [author configuration field origin](concepts/author-config-field-origin.md)

### backlog_path
- type: repository-relative string path
- default: empty string
- required: false
- semantics: configured backlog path used for story, story-edit, and epic-edit intake checks
- verify: json_path(path="$.backlog_path", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`
- detail: [author configuration field origin](concepts/author-config-field-origin.md)

### roadmap_path
- type: repository-relative string path
- default: empty string
- required: false
- semantics: the sole approved roadmap path in epic mode, or an empty path in other modes
- verify: json_path(path="$.roadmap_path", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`
- detail: [author configuration field origin](concepts/author-config-field-origin.md)

### epics_dir
- type: repository-relative string path
- default: empty string
- required: false
- semantics: configured epic directory used to resolve the selected epic
- verify: json_path(path="$.epics_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`
- detail: [author configuration field origin](concepts/author-config-field-origin.md)

### features_dir
- type: string path
- default: empty string
- required: false
- semantics: configured feature-book directory exposed as read-only grounding to author prompts
- verify: json_path(path="$.features_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`
- detail: [author configuration field origin](concepts/author-config-field-origin.md)

### layers
- type: list of strings
- default: empty list
- required: false
- semantics: best-effort local-instruction skill paths used as prompt layer hints
- verify: json_path(path="$.layers", matches="^\\[\\]$")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`
- detail: [author configuration field origin](concepts/author-config-field-origin.md)

## Methods

### load_config
- sig: `load_config(logger: logging.Logger, repo_dir: str = "", mode: str = "epic") -> Config`
- does: resolves the consuming repository from `repo_dir`, or from the first ancestor containing `agents.yml` or `docs/epics` when the input is empty
- verify: count(subject="author configuration repository roots", equals=1)
- does: resolves the backlog, epics, and feature-book paths through the configured document roots
- verify: count(subject="author configuration document roots", equals=1)
- does: resolves the sole approved roadmap only when `mode` is `epic`
- verify: count(subject="author configuration roadmap selections", equals=1)
- does: returns local-instruction skill paths from `agents.yml` as prompt hints when each entry has a `skill` value
- verify: count(subject="author configuration layer hints", equals=1)
- does: leaves the feature book as read-only grounding and does not create a surface inventory
- verify: absent(subject="configuration-created feature inventory")
- raises: `WorkflowFailed` when a backlog-dependent mode resolves no backlog file
- verify: count(subject="missing backlog configuration failures", equals=1)
- raises: `WorkflowFailed` in epic mode when no single approved roadmap qualifies
- verify: count(subject="invalid approved roadmap configuration failures", equals=1)
- returns: a `Config` containing the absolute repository root and repository-relative configured paths
- verify: json_path(path="$.repo_root", matches=".+")
- code: `workflows/src/workhorse_workflows/author/main/nodes/config.py::load_config`
- tests: `workflows/tests/author/test_config.py::test_author_config_never_invents_a_surface_inventory`
- tests: `workflows/tests/author/test_config.py::test_epic_authoring_requires_an_approved_roadmap`
- tests: `workflows/tests/author/test_config.py::test_epic_authoring_does_not_fall_back_to_a_backlog`

### _template
- sig: `_template(root: Path) -> dict`
- does: reads `agents.yml` from the resolved repository when it is a regular file
- verify: count(subject="author template reads", equals=1)
- does: returns an empty mapping when the file is missing, unreadable, invalid YAML, or contains a non-mapping value
- verify: json_path(path="$.template", matches="^\\{\\}$")
- returns: the parsed YAML mapping or an empty mapping
- verify: json_path(path="$.template", matches=".*")
- code: `workflows/src/workhorse_workflows/author/main/nodes/config.py::_template`

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

- code: `workflows/src/workhorse_workflows/author/shared/nodes/config.py::load_config` @d32a3c2caaa3
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config` @4460b1deea94
- detail: [author shared paths](../concepts/author-shared-paths.md)
- detail: [author story-split subflow](../concepts/story-split-subflow.md)
- detail: [author load_config documentation roles](../concepts/author-load-config-documentation-roles.md)

## Fields

### repo_root
- type: string path
- default: empty string
- required: false
- semantics: absolute repository root selected from the explicit input or repository markers and used for graph and artifact operations
- verify: json_path(path="$.repo_root", equals="docs/stories")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config` @4460b1deea94
- detail: [author configuration field origin](../concepts/author-config-field-origin.md)

### backlog_path
- type: repository-relative string path
- default: empty string
- required: false
- semantics: configured backlog path used for story, story-edit, and epic-edit intake checks
- verify: json_path(path="$.backlog_path", equals="docs/stories/acme-story/story.md")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config` @4460b1deea94
- detail: [author configuration field origin](../concepts/author-config-field-origin.md)

### milestone_path
- type: repository-relative string path
- default: empty string
- required: false
- semantics: the docs-root-relative path of the approved milestone's `milestone.md` in epic mode, or an empty path in other modes
- verify: json_path(path="$.milestone_path", equals="docs/milestones/acme-launch/milestone.md")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config` @4460b1deea94
- detail: [author configuration field origin](../concepts/author-config-field-origin.md)

### epics_dir
- type: repository-relative string path
- default: empty string
- required: false
- semantics: configured epic directory used to resolve the selected epic
- verify: json_path(path="$.epics_dir", equals="docs/stories/acme-story")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config` @4460b1deea94
- detail: [author configuration field origin](../concepts/author-config-field-origin.md)

### services_dir
- type: string path
- default: empty string
- required: false
- semantics: configured feature-book directory exposed as read-only grounding to author prompts
- verify: json_path(path="$.services_dir", equals="docs/stories/acme-story")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config` @4460b1deea94
- detail: [author configuration field origin](../concepts/author-config-field-origin.md)

### layers
- type: list of strings
- default: empty list
- required: false
- semantics: best-effort local-instruction skill paths used as prompt layer hints
- verify: json_path(path="$.layers", matches="^\\[\\]$")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config` @4460b1deea94
- detail: [author configuration field origin](../concepts/author-config-field-origin.md)

## Methods

### load_config
- sig: `load_config(logger: logging.Logger, repo_dir: str = "", mode: str = "epic") -> Config`
- does: resolves the consuming repository from `repo_dir`, or from the first ancestor containing `agents.yml` or `docs/epics` when the input is empty
- verify: count(subject="author configuration repository roots", equals=1)
- does: resolves the backlog, epics, and feature-book paths through the configured document roots
- verify: count(subject="author configuration document roots", equals=1)
- does: selects the one approved milestone and requires its readiness check to report no error only when `mode` is `epic`
- verify: count(subject="author configuration milestone selections", equals=1)
- does: returns local-instruction skill paths from `agents.yml` as prompt hints when each entry has a `skill` value
- verify: count(subject="author configuration layer hints", equals=1)
- does: leaves the feature book as read-only grounding and does not create a surface inventory
- verify: absent(subject="configuration-created feature inventory")
- raises: `WorkflowFailed` when a backlog-dependent mode resolves no backlog file
- verify: count(subject="missing backlog configuration failures", equals=1)
- raises: `WorkflowFailed` in epic mode when no single approved milestone qualifies or its readiness check reports an error, listing each finding
- verify: count(subject="invalid approved milestone configuration failures", equals=1)
- returns: a `Config` containing the absolute repository root and repository-relative configured paths
- verify: json_path(path="$.repo_root", equals="docs/stories")
- code: `workflows/src/workhorse_workflows/author/shared/nodes/config.py::load_config` @d32a3c2caaa3
- tests: `workflows/tests/author/test_config.py::test_author_config_never_invents_a_surface_inventory`
- tests: `workflows/tests/author/test_config.py::test_epic_authoring_selects_the_approved_milestone_folder`
- tests: `workflows/tests/author/test_config.py::test_epic_authoring_fails_when_no_milestone_is_approved`
- tests: `workflows/tests/author/test_config.py::test_epic_authoring_fails_when_two_milestones_are_approved`
- tests: `workflows/tests/author/test_config.py::test_epic_authoring_fails_on_a_readiness_error_and_lists_it`
- tests: `workflows/tests/author/test_config.py::test_epic_authoring_does_not_fall_back_to_a_backlog`

### approved_milestone_path
- sig: `approved_milestone_path(root: Path) -> str`
- does: selects the one approved milestone through Ostler
- verify: count(subject="approved milestone selections", equals=1)
- raises: `WorkflowFailed` when no milestone or more than one milestone is approved
- verify: count(subject="milestone selection failures", equals=1)
- raises: `WorkflowFailed` listing every error finding when the milestone's readiness check fails
- verify: count(subject="milestone readiness failures", equals=1)
- returns: the docs-root-relative path of the milestone's `milestone.md`
- verify: json_path(path="$", equals="docs/milestones/acme-launch/milestone.md")
- code: `workflows/src/workhorse_workflows/author/shared/nodes/config.py::approved_milestone_path` @944388d4c559
- tests: `workflows/tests/author/test_config.py::test_a_flat_milestone_file_is_not_an_approved_milestone`

### _template
- sig: `_template(root: Path) -> dict`
- does: reads `agents.yml` from the resolved repository when it is a regular file
- verify: count(subject="author template reads", equals=1)
- does: returns an empty mapping when the file is missing, unreadable, invalid YAML, or contains a non-mapping value
- verify: json_path(path="$.template", matches="^\\{\\}$")
- returns: the parsed YAML mapping or an empty mapping
- verify: json_path(path="$.template", equals="example template")
- code: `workflows/src/workhorse_workflows/author/shared/nodes/config.py::_template` @d32a3c2caaa3

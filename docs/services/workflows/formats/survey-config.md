---
type: format
slug: survey-config
title: Survey configuration
---
# Survey configuration

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig` @7db58efbfd66
- detail: [author surveyor subflow](../concepts/author-surveyor-subflow.md)

The resolved repository root and repository-relative paths used by the surveyor and its
artifacts. Every path other than `repo_root` is relative to that root.

## Fields

### repo_root
- type: string
- default: empty string
- required: false
- semantics: resolved absolute repository root
- verify: json_path(path="$.repo_root", equals="docs/stories")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig` @7db58efbfd66
- detail: [survey configuration path roles](../concepts/survey-config-path-roles.md)

### rubric
- type: string path
- default: empty string
- required: false
- semantics: repository-relative survey rubric path
- verify: json_path(path="$.rubric", equals="example rubric")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig` @7db58efbfd66
- detail: [survey configuration path roles](../concepts/survey-config-path-roles.md)

### survey_dir
- type: string path
- default: empty string
- required: false
- semantics: repository-relative directory containing survey artifacts
- verify: json_path(path="$.survey_dir", equals="docs/stories/acme-story")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig` @7db58efbfd66
- detail: [survey configuration path roles](../concepts/survey-config-path-roles.md)

### rules
- type: string path
- default: empty string
- required: false
- semantics: repository-relative unit-rules path
- verify: json_path(path="$.rules", equals="example rules")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig` @7db58efbfd66
- detail: [survey configuration path roles](../concepts/survey-config-path-roles.md)

### inventory
- type: string path
- default: empty string
- required: false
- semantics: repository-relative materialized inventory path
- verify: json_path(path="$.inventory", equals="example inventory")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig` @7db58efbfd66
- detail: [survey configuration path roles](../concepts/survey-config-path-roles.md)

### findings_dir
- type: string path
- default: empty string
- required: false
- semantics: repository-relative directory of per-unit finding records
- verify: json_path(path="$.findings_dir", equals="docs/stories/acme-story")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig` @7db58efbfd66
- detail: [survey configuration path roles](../concepts/survey-config-path-roles.md)

### partition
- type: string path
- default: empty string
- required: false
- semantics: repository-relative finding partition path
- verify: json_path(path="$.partition", equals="example partition")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig` @7db58efbfd66
- detail: [survey configuration path roles](../concepts/survey-config-path-roles.md)

### backlog
- type: string path
- default: empty string
- required: false
- semantics: repository-relative author backlog path
- verify: json_path(path="$.backlog", equals="example backlog")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig` @7db58efbfd66
- detail: [survey configuration path roles](../concepts/survey-config-path-roles.md)

### unit_manifest
- type: string path
- default: empty string
- required: false
- semantics: repository-relative emitted unit-to-cluster manifest path
- verify: json_path(path="$.unit_manifest", equals="example unit manifest")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig` @7db58efbfd66
- detail: [survey configuration path roles](../concepts/survey-config-path-roles.md)

### context
- type: string path
- default: empty string
- required: false
- semantics: repository-relative operator context path
- verify: json_path(path="$.context", equals="Applied the change.")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig` @7db58efbfd66
- detail: [survey configuration path roles](../concepts/survey-config-path-roles.md)

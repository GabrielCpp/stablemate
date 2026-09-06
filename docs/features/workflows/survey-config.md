---
type: format
slug: survey-config
title: Survey configuration
---
# Survey configuration

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig`
- detail: [author surveyor subflow](concepts/author-surveyor-subflow.md)

The resolved repository root and repository-relative paths used by the surveyor and its
artifacts. Every path other than `repo_root` is relative to that root.

## Fields

### repo_root
- type: string
- default: empty string
- required: false
- semantics: resolved absolute repository root
- verify: json_path(path="$.repo_root", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig`

### rubric
- type: string path
- default: empty string
- required: false
- semantics: repository-relative survey rubric path
- verify: json_path(path="$.rubric", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig`

### survey_dir
- type: string path
- default: empty string
- required: false
- semantics: repository-relative directory containing survey artifacts
- verify: json_path(path="$.survey_dir", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig`

### rules
- type: string path
- default: empty string
- required: false
- semantics: repository-relative unit-rules path
- verify: json_path(path="$.rules", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig`

### inventory
- type: string path
- default: empty string
- required: false
- semantics: repository-relative materialized inventory path
- verify: json_path(path="$.inventory", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig`

### findings_dir
- type: string path
- default: empty string
- required: false
- semantics: repository-relative directory of per-unit finding records
- verify: json_path(path="$.findings_dir", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig`

### partition
- type: string path
- default: empty string
- required: false
- semantics: repository-relative finding partition path
- verify: json_path(path="$.partition", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig`

### backlog
- type: string path
- default: empty string
- required: false
- semantics: repository-relative author backlog path
- verify: json_path(path="$.backlog", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig`

### unit_manifest
- type: string path
- default: empty string
- required: false
- semantics: repository-relative emitted unit-to-cluster manifest path
- verify: json_path(path="$.unit_manifest", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig`

### context
- type: string path
- default: empty string
- required: false
- semantics: repository-relative operator context path
- verify: json_path(path="$.context", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig`

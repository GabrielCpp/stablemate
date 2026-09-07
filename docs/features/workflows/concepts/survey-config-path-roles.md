---
type: concept
slug: survey-config-path-roles
title: Survey configuration path roles
---
# Survey configuration path roles

`SurveyConfig` carries one resolved repository root and the paths to the survey artifacts used
throughout a surveyor run. These fields are not alternatives: select the field whose artifact
role matches the value being read or written. `repo_root` is the absolute root; every other
field is a repository-relative path resolved against that root so a checkpoint can run on a
different machine. The schema declares no deprecated field, replacement field, or preference
between these artifact roles.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SurveyConfig`
- rule: use `repo_root` for the resolved repository root and use each other field only for its named survey artifact; no field supersedes another

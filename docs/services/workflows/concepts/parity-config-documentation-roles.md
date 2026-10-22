---
type: concept
slug: parity-config-documentation-roles
title: Parity configuration documentation roles
---
# Parity configuration documentation roles

`ParityConfig` has two complementary documentation views. Read [parity configuration artifact
roles](parity-config-artifact-roles.md) when selecting the repository-relative field for a
baseline, feature book, survey artifact, backlog, or epic directory. Read the [author parity
surveyor subflow](parity-surveyor-subflow.md) when determining how the workflow resolves and
uses that configuration while it surveys, validates, and emits parity artifacts.

The `ParityConfig` declaration defines the shared path shape and states that it is separate from
`SurveyConfig` because the parity workflow has different inputs and no clustering stage. It does
not rank these two documentation views: neither replaces the other, and a reader selects the one
matching the question they need to answer.

- rule: read artifact roles to choose a `ParityConfig` field; read the parity surveyor subflow to understand how that configuration is resolved and used; neither documentation view ranks over or replaces the other

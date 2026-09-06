---
type: concept
slug: workflow-kit-credentials
title: Workflow kit credentials
---
# Workflow kit credentials

The credentials kit is the workflow package's narrow exception to the rule that workflow code
does not read environment variables: credentials stay out of checkpointed parameters, logs, and
telemetry. Its scoped environment helper supplies a freshly minted value only while a callee
needs it, then restores the caller's prior process state even when that callee fails.

- code: `workflows/src/workhorse_workflows/kit/credentials.py::scoped_env`
- tests: `workflows/tests/test_kit_credentials.py::test_scoped_env_sets_the_value_for_the_block_and_clears_it_after`
- tests: `workflows/tests/test_kit_credentials.py::test_scoped_env_restores_a_prior_value_rather_than_clearing_it`
- tests: `workflows/tests/test_kit_credentials.py::test_scoped_env_restores_even_when_the_block_raises`

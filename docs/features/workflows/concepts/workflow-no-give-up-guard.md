---
type: concept
slug: workflow-no-give-up-guard
title: Workflow no-give-up guard
---
# Workflow no-give-up guard

The repository-level no-give-up guard rejects a tracked workflow source tree that reintroduces
the vocabulary of the removed terminal-failure path. This shared test imports the guard without
executing it as a process, asserts that its protected vocabulary retains every mechanism of that
path, proves a planted prohibited line produces a non-zero exit, and confirms the current tree
is clean. The guard implementation is outside this service, so this node documents only the
workflow-owned test contract.

- code: `workflows/tests/test_giveup_guard.py::test_the_vocabulary_survives`
- code: `workflows/tests/test_giveup_guard.py::test_a_reintroduction_fails_the_guard`
- code: `workflows/tests/test_giveup_guard.py::test_the_tree_is_clean`
- tests: `workflows/tests/test_giveup_guard.py::test_the_vocabulary_survives`
- tests: `workflows/tests/test_giveup_guard.py::test_a_reintroduction_fails_the_guard`
- tests: `workflows/tests/test_giveup_guard.py::test_the_tree_is_clean`

---
type: concept
slug: okf-builder-shared-blueprint
title: OKF-builder shared blueprint
---
# OKF-builder shared blueprint

This module owns the single node-registration blueprint used by every OKF-builder flow. Keeping
the object in a module that does not import a flow prevents registration from importing the
composition root; the package initializer re-exports the same object for the workflow registry.

- code: `workflows/src/workhorse_workflows/okf_builder/shared/blueprint.py::blueprint`

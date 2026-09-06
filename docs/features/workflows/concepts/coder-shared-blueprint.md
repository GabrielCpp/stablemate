---
type: concept
slug: coder-shared-blueprint
title: Coder shared blueprint
---
# Coder shared blueprint

This module provides the one node-registration namespace shared by every Coder flow. Node modules
decorate their callables against this object, while the Coder workflow composition root adds the
same blueprint to its registry. Keeping the object in this standalone module lets node modules
import it without importing the package that assembles them.

- code: `workflows/src/workhorse_workflows/coder/shared/blueprint.py::blueprint`

The module constructs the blueprint with the name `coder` and exports that singleton as its only
public module export. The imported `Blueprint` implementation belongs to the Workhorse dependency
and is outside this service's crawl boundary; this node therefore records the registration object,
not the dependency's API.

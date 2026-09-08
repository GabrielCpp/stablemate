---
type: concept
slug: fleet-rows-documentation-contexts
title: Fleet rows documentation contexts
---
# Fleet rows documentation contexts

`fleet_rows` has one implementation and two complementary documentation contexts. The method in
[groom projection module](groom-projection-module.md#method-fleet-rows) is the module-level API:
it identifies the callable, its inputs, and its delegation to `run_row`. The method in [runs fleet
view](../runs-fleet-view.md#method-fleet-rows) is the fleet payload contract: it describes the
rows, filtering, and ordering returned to the dashboard.

Neither context replaces the other. Read the projection-module method when calling or changing
the projection API; read the fleet-view method when consuming or specifying the `runs` array.

- code: groom/groom/projection.py::fleet_rows
- rule: use the projection-module method for the callable contract and the fleet-view method for the returned fleet-row contract; neither is preferred or deprecated.

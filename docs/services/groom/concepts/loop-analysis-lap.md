---
type: concept
slug: loop-analysis-lap
title: Loop analysis lap
---
# Loop analysis lap

One turn of a loop, holding the three numbers needed to rank and analyse convergence of review→rework cycles.

A lap is a single pass through a review gate — one `agent_turn` span within a work item. The cost of a lap is where the loop's money and rework went; the exit rate (work items exiting per lap issued) answers whether a gate is converging.

These three fields stay separate rather than resolving to one number because their distinction is load-bearing: what a harness billed (from the LLM provider) and what the tokens are worth (at groom's rate card) are different claims, and the caller needs to be able to label which one a report is quoting. `suspect_zero` additionally names the turns that cost nothing on the harness side while emitting output — a gap that only matters under subscription auth, where the harness never reports cost.

- code: `groom/groom/store.py::Lap`

## Fields

### field: cost

- type: `float | None`
- semantics: USD billed by the LLM provider for this lap's turn, or NULL when the provider did not report cost

### field: est

- type: `float | None`
- semantics: USD at groom's rate card for this lap's tokens, or NULL when the model has no published rate in `groom.prices`

### field: suspect_zero

- type: `bool`
- semantics: True when the lap reported cost of exactly $0 while emitting output tokens — indicates a cost-reporting gap under subscription auth


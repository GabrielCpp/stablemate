---
type: format
slug: trend-report
title: Trend report
---
# Trend report

- file: none, because it is the structured reply of the grouping turn
- code: `workflows/src/workhorse_workflows/review_debt/schemas.py::TrendReport` @29f1064cf2b6
- detail: [review-debt flow](../flows/review-debt.md)

The grouping turn of the [review-debt flow](../flows/review-debt.md) returns this report. It sorts
every record of the read into clusters that share a cause and singletons whose cause no other
record shares. The flow accepts it only when each id of the read appears exactly once across the
clusters and the singletons.

## Fields

### clusters
- type: list of objects with `name`, `cause` and `ids`
- default: none
- required: true
- semantics: groups of two or more records that share one cause, each with a short name, one cause sentence and the record ids it holds
- verify: json_path(path="$.clusters[0].name", equals="unvalidated input")
- code: `workflows/src/workhorse_workflows/review_debt/schemas.py::Cluster` @29f1064cf2b6

### singletons
- type: list of objects with `id` and `cause`
- default: none
- required: true
- semantics: records whose cause no other record shares, each with its own cause sentence
- verify: json_path(path="$.singletons[0].id", equals="X-4")
- code: `workflows/src/workhorse_workflows/review_debt/schemas.py::Singleton` @29f1064cf2b6

### summary
- type: string
- default: none
- required: true
- semantics: one paragraph for the maintainer that names the trends worth acting on
- verify: json_path(path="$.summary", matches="unvalidated input")
- code: `workflows/src/workhorse_workflows/review_debt/schemas.py::TrendReport.summary` @29f1064cf2b6

---
type: concept
slug: okf-builder-shared-schemas
title: OKF-builder shared schemas
---
# OKF-builder shared schemas

These Pydantic models are the typed values crossing OKF-builder node boundaries. `OkfResult`
ignores unknown keys and removes null input values; its concrete descendants therefore retain
defaults when an agent omits an answer. Settings, drain results, adjudication results, coverage
results, and walkthrough results are represented separately so transitions bind named values to
the receiving node's signature. `SourceRequest` is immutable and rejects repository-escaping
relative roots.

- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py`

## Models

### method: OkfResult
- sig: `OkfResult(data: Any) -> OkfResult`
- does: ignores unknown model keys and drops null dictionary values before validation
- verify: count(subject="OKF-builder result normalization operations", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::OkfResult`

### method: SourceRequest
- sig: `SourceRequest(repo: str, surface: str, root: str = ".", base: str, head: str = "WORKTREE") -> SourceRequest`
- does: requires a lowercase repository identifier, a non-empty surface, and a non-empty base revision
- verify: count(subject="validated OKF-builder source requests", equals=1)
- does: normalizes slash direction and leading/trailing separators in root
- verify: count(subject="normalized OKF-builder source roots", equals=1)
- does: rejects root values equal to or beneath `..`
- verify: count(subject="rejected escaping OKF-builder source roots", equals=0)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::SourceRequest`

### method: Prepared
- sig: `Prepared(...) -> Prepared`
- does: carries resolved build paths, scope identity, book state, source requests, and preparation status with defaults for omitted values
- verify: count(subject="OKF-builder prepared schema results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::Prepared`

### method: Committed
- sig: `Committed(committed: bool = false) -> Committed`
- does: carries whether the completed book produced a commit
- verify: json_path(path="$.committed", equals=false)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::Committed`

### method: Pick
- sig: `Pick(...) -> Pick`
- does: carries selected item identity, budget state, and worklist progress labels
- verify: count(subject="OKF-builder pick schema results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::Pick`

### method: Watermarked
- sig: `Watermarked(advanced: list[str] = [], watermark_error: str = "") -> Watermarked`
- does: reports source files whose stale-citation watermark advanced and any watermark error
- verify: count(subject="OKF-builder watermark schema results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::Watermarked`

### method: Recorded
- sig: `Recorded(...) -> Recorded`
- does: reports worklist counts, newly added rows, and the standing blocked-row set
- verify: count(subject="OKF-builder recorded schema results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::Recorded`

### method: BlockedRows
- sig: `BlockedRows(rows: list[dict[str, Any]] = [], count: int = 0) -> BlockedRows`
- does: carries blocked worklist rows that have not received an adjudication verdict
- verify: count(subject="OKF-builder blocked-row schema results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::BlockedRows`

### method: Evidence
- sig: `Evidence(...) -> Evidence`
- does: carries affected nodes, doctor findings, grounded code references, story evidence, and join warnings for adjudication
- verify: count(subject="OKF-builder evidence schema results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::Evidence`

### method: Adjudication
- sig: `Adjudication(verdict: str = "", chain: str = "", seed_summary: str = "") -> Adjudication`
- does: carries a book, code, or story verdict plus its why-chain and optional code-defect summary
- verify: count(subject="OKF-builder adjudication schema results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::Adjudication`

### method: Applied
- sig: `Applied(...) -> Applied`
- does: reports the applied verdict, affected seed or story, marked nodes, and requeue decision
- verify: count(subject="OKF-builder applied schema results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::Applied`

### method: Checkpoint
- sig: `Checkpoint(...) -> Checkpoint`
- does: carries doctor cleanliness, rendered output, round counters, repair items, and stall signature
- verify: count(subject="OKF-builder checkpoint schema results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::Checkpoint`

### method: SourceInventory
- sig: `SourceInventory(...) -> SourceInventory`
- does: carries the inventory artifact path, source-unit counts, operational-unit count, and inventory error
- verify: count(subject="OKF-builder source inventory schema results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::SourceInventory`

### method: Coverage
- sig: `Coverage(...) -> Coverage`
- does: carries the computed coverage verdict, missing-unit artifacts, re-grounding items, and rescan counter
- verify: count(subject="OKF-builder coverage schema results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::Coverage`

### method: Discovery
- sig: `Discovery(discovered: list[dict[str, Any]] = []) -> Discovery`
- does: carries discovered worklist entries
- verify: count(subject="OKF-builder discovery schema results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::Discovery`

### method: Investigation
- sig: `Investigation(discovered: list[dict[str, Any]] = [], doc_status: str = "", note: str = "") -> Investigation`
- does: carries discovered entries and the documenting turn's status and note
- verify: count(subject="OKF-builder investigation schema results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::Investigation`

### method: Recheck
- sig: `Recheck(discovered: list[dict[str, Any]] = [], needs_journeys: bool = false) -> Recheck`
- does: carries coverage-recheck discoveries and whether journeys are needed
- verify: count(subject="OKF-builder recheck schema results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::Recheck`

### method: WalkTurn
- sig: `WalkTurn(discovered: list[dict[str, Any]] = [], walk_status: str = "") -> WalkTurn`
- does: carries walkthrough discoveries and confirmed, healed, or skipped status
- verify: count(subject="OKF-builder walkthrough turn schema results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::WalkTurn`

### method: WebApp
- sig: `WebApp(...) -> WebApp`
- does: carries whether a web surface exists
- verify: count(subject="OKF-builder web application surface schema results", equals=1)
- does: carries its documented launch path
- verify: count(subject="OKF-builder web application launch schema results", equals=1)
- does: carries its documented health path
- verify: count(subject="OKF-builder web application health schema results", equals=1)
- does: carries its documented application identity
- verify: count(subject="OKF-builder web application identity schema results", equals=1)
- does: carries its documented scratch paths
- verify: count(subject="OKF-builder web application scratch schema results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::WebApp`

### method: AppBoot
- sig: `AppBoot(...) -> AppBoot`
- does: carries application readiness, resolved entry URL, process identity, and process-group identity
- verify: count(subject="OKF-builder application boot schema results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::AppBoot`

### method: BrowserBoot
- sig: `BrowserBoot(...) -> BrowserBoot`
- does: carries shared-browser readiness, CDP endpoint, and optional spawned process identity
- verify: count(subject="OKF-builder browser boot schema results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::BrowserBoot`

### method: TornDown
- sig: `TornDown(torn_down: str = "no") -> TornDown`
- does: carries the string state `yes`, `no`, or `skipped` for teardown
- verify: count(subject="OKF-builder teardown schema results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::TornDown`

### method: WalkSeed
- sig: `WalkSeed(...) -> WalkSeed`
- does: carries walkthrough worklist counts and the number of screens lacking vet evidence
- verify: count(subject="OKF-builder walkthrough seed schema results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/schemas.py::WalkSeed`

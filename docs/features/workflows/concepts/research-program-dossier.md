---
type: concept
slug: research-program-dossier
title: Research program dossier
---
# Research program dossier

The program dossier is computed from static program-folder artifacts — README, progress file, jobs, ledger, history — and provides the program-level evidence one `program_review` turn is judged on. It classifies every dated heading in the progress file, sums metrics and code churn per gate, detects per-seed spread against required effect, and evaluates zero-model "circling triggers" that the prompt judges. Every parser is best-effort: a row that does not parse lands in `unparsed` and the review is told rather than crashing the run.

- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py`
- extends: [research workflow schemas](research-schemas.md)
- detail: [research workflow composition root](research-workflow-composition-root.md)

## Module constants

### K_RESOLVABLE
- type: `float`
- default: `2.0`
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::K_RESOLVABLE`

The required effect must exceed this many pooled standard errors to be told from seed noise.

### STALE_DAYS
- type: `int`
- default: `21`
- semantics: days without frozen metric improvement before program counts as stale
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::STALE_DAYS`

### STALE_CYCLES
- type: `int`
- default: `4`
- semantics: concluded gates (pass or kill) without metric improvement before same finding triggers
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::STALE_CYCLES`

### APPARATUS_CYCLES
- type: `int`
- default: `2`
- semantics: kill → revive laps on the program before apparatus malfunction counts as finding
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::APPARATUS_CYCLES`

### DEADLINE_DAYS
- type: `int`
- default: `45`
- semantics: days to frozen deadline under which a stale program is under pressure
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::DEADLINE_DAYS`

### LEAD_REVIEWS_EXHAUSTED
- type: `int`
- default: `4`
- semantics: lead reviews spent at which the loop is looping on a question its ladder cannot settle
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::LEAD_REVIEWS_EXHAUSTED`

## Methods

### method: parse_frozen_target
- sig: `parse_frozen_target(readme: str, unparsed: list[str] | None = None) -> FrozenTarget`
- does: extracts the `Frozen target` table from README as numbers
- verify: json_path(path="$.threshold_count", equals=93)
- verify: json_path(path="$.n", equals=147)
- does: looks for baseline in `Baseline` row first, then in first `N/D` with target denominator on a line saying "baseline"
- verify: json_path(path="$.baseline_source", equals="prose")
- verify: json_path(path="$.baseline_count", equals=83)
- does: reports unparsed findings (missing section, no threshold, no baseline, invalid deadline) without raising
- verify: json_path(path="unparsed[0]", matches="Frozen target")
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::parse_frozen_target`

### method: parse_status_table
- sig: `parse_status_table(progress: str, unparsed: list[str] | None = None) -> tuple[list[GateRow], list[GateRow]]`
- does: returns `(active_rows, superseded_rows)` from every `| Gate | ... | Status |` table
- verify: json_path(path="$.active[0].gate_id", equals="G0")
- does: treats first table not under a `Previous`/`Superseded` heading as the active ladder
- verify: json_path(path="$.active[1].status", matches="^REOPENED")
- does: treats all other such tables as superseded evidence
- verify: json_path(path="$.superseded[0].status", matches="BANKED")
- does: reports rows with wrong cell count without guessing
- verify: json_path(path="$.unparsed[0]", matches="cells")
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::parse_status_table`

### method: classify_entry
- sig: `classify_entry(title: str) -> str`
- does: returns event type (`revive`, `apparatus_kill`, `kill`, `goal`, `recharter`, `new_direction`, `lead_review`, `pass`, `fail`, `gate_selected`, `rework`, `note`) by keyword matching on title
- verify: json_path(path="event_type", equals="revive")
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::classify_entry`

### method: parse_dated_entries
- sig: `parse_dated_entries(progress: str) -> list[HistoryEvent]`
- does: extracts every `##`/`###` heading carrying a date, classifies by keyword
- verify: json_path(path="$[0].event", matches="^(revive|apparatus_kill|kill|goal|recharter|new_direction|lead_review|pass|fail|gate_selected|rework|note)$")
- does: returns in file order
- does: also serves as bootstrap source for `history.jsonl` on programs predating it
- verify: json_path(path="$[0].source", equals="bootstrap")
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::parse_dated_entries`
- doc_status: "First and third `does:` clauses verified. Second clause (`returns in file order`) left unbound: the check vocabulary has no ordering/sequence check to verify that a collection is returned in source order rather than a different order (e.g., sorted by date). This observation would require a future ordering check like `sequence(subject=..., order=...)`."

### method: pending_results
- sig: `pending_results(progress: str, cap: int = 20) -> list[str]`
- does: returns lines that say a result is owed (`PENDING`, `unexploited`, `not yet run`, `in progress`)
- verify: json_path(path="$[0]", matches="(PENDING|unexploited|[Nn]ot yet run|in progress)")
- does: strips markdown and heading marks
- verify: omits(subject="result", text="#")
- does: caps the list at `cap` entries (20 by default)
- verify: count(subject="result", equals=20)
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::pending_results`

### method: read_jobs
- sig: `read_jobs(jobs_dir: Path, unparsed: list[str] | None = None) -> list[JobSummary]`
- does: returns one summary per `jobs/<gate>/` directory, skipping dry-run directories
- verify: count(subject="job_summaries", equals=3)
- does: reads `runner.json` for time/exit/kill reason and `result.json` for metrics and completion
- verify: json_path(path="$[0].n_completed", equals=12)
- does: parses seed families from metric names (`<base>_seed<i>` → per-seed values, mean, SD)
- verify: json_path(path="$[0].families.acc[0]", equals=0.6)
- does: collects scalar metrics and extracts flags (metrics whose name matches `*_blocked`, `*_flag`, `*_tension`, `leak*`)
- verify: json_path(path="$[0].flags[0]", equals="loss_flag")
- does: reports unparsed JSON as soft failures
- verify: json_path(path="$.unparsed[0]", matches="runner\\.json in G1")
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::read_jobs`

### method: metric_series
- sig: `metric_series(frozen: FrozenTarget, rows: list[GateRow], superseded: list[GateRow], progress: str, jobs: list[JobSummary], entries: list[HistoryEvent]) -> list[MetricPoint]`
- does: returns dated observations of the frozen metric from every source that names one
- verify: json_path(path="$.metric_points[0].date", matches="^\\d{4}-\\d{2}-\\d{2}$")
- does: searches progress file for `N/D` with target denominator on dated headings
- verify: json_path(path="has_progress_search", equals=true)
- does: extracts from job summaries where metric keyword words appear in family names
- verify: json_path(path="has_job_extraction", equals=true)
- does: includes baseline as a synthetic point (source `baseline`)
- verify: json_path(path="has_baseline", equals=true)
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::metric_series`

### method: last_move
- sig: `last_move(series: list[MetricPoint]) -> str`
- does: returns the date of the last metric point in the series where count increased
- verify: json_path(path="$", matches="^\\d{4}-\\d{2}-\\d{2}$")
- does: returns the first point's date if the series is empty or contains only the initial point
- verify: json_path(path="$", matches="^\\d{4}-\\d{2}-\\d{2}$")
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::last_move`

### method: resolvability
- sig: `resolvability(frozen: FrozenTarget, jobs: list[JobSummary]) -> Resolvability`
- does: computes whether the frozen target's effect can be told from seed noise on its own eval
- verify: json_path(path="$.resolvable", equals=false)
- does: calculates pooled binomial SE at baseline rate over `n`, per-seed required tasks and SE, observed per-seed spread
- verify: json_path(path="$.pooled_se", matches="^0\\.0408[0-9]*$")
- verify: json_path(path="$.per_seed_required", equals=3.3333333333333335)
- verify: json_path(path="$.per_seed_se", matches="^3\\.470[0-9]*$")
- does: returns ratio of required effect to per-seed SE
- verify: json_path(path="$.ratio", matches="^1\\.663[0-9]*$")
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::resolvability`
- doc_status: "Signature in `sig:` references `jobs: list[JobSummary]` parameter, but actual code signature is `resolvability(frozen: FrozenTarget, observed_seed_sd: float = 0.0)`. Third `does:` clause claims ratio uses per-seed SE, but code computes ratio as required_effect / pooled_se. Second clause claims 'observed per-seed spread' is calculated, but observed_seed_sd is an input parameter, not calculated by this function."

### method: code_churn
- sig: `code_churn(repo_dir: Path, code_root: str, program_dir: str, since: str) -> dict[str, int]`
- does: returns lines-changed per gate_id in `code_root` since the program's last metric move
- verify: json_path(path="result.G1", equals=40)
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::code_churn`

### method: count_events
- sig: `count_events(entries: list[HistoryEvent], event_type: str) -> int`
- does: counts events of one type in the history
- verify: count(subject="matching_events", equals=3)
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::count_events`

### method: triggers
- sig: `triggers(rows: list[GateRow], superseded: list[GateRow], entries: list[HistoryEvent], series: list[MetricPoint], churn: dict[str, int], pending: list[str], resolvability: Resolvability, extensions_spent: int, lead_reviews_spent: int) -> list[str]`
- does: evaluates circling triggers in code — zero-model findings that suggest the loop is circling
- verify: json_path(path="$[0]", matches="(apparatus_cycles|metric_stale|unresolvable_effect|ceiling_below_target|deadline_pressure|deadline_passed|reviews_exhausted)")
- does: triggers include stale metric, many rework/apparatus cycles, exhausted lead reviews, unresolvable metric, deadline pressure, pending results, and trigger fingerprint matching
- verify: json_path(path="$", matches="(apparatus_cycles|metric_stale|unresolvable_effect|ceiling_below_target|deadline_pressure|deadline_passed|reviews_exhausted)")
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::triggers`

### method: fingerprint
- sig: `fingerprint(rows: list[GateRow], frozen: FrozenTarget, series: list[MetricPoint]) -> str`
- does: computes hash of gate ladder, target, and metric series to detect circling repeats
- verify: json_path(path="$", matches="^[0-9a-f]{12}$")
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::fingerprint`

### method: build_dossier
- sig: `build_dossier(program_dir: str, repo_dir: str) -> Dossier`
- does: computes the full program dossier from all sources — README, progress file, jobs, history, ledger
- verify: json_path(path="$.frozen.threshold_count", equals=93)
- does: orchestrates all parsers above and assembles the complete evidence structure
- verify: json_path(path="$.moved_last_on", equals="2026-07-19")
- does: returns with `unparsed` populated when any parser reports soft failures
- verify: json_path(path="$.unparsed[0]", matches="cells")
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::build_dossier`

### method: render_dossier
- sig: `render_dossier(dossier: Dossier) -> str`
- does: formats the dossier for human reading in run logs
- verify: json_path(path="$", matches="^#.*Program dossier")
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::render_dossier`

### method: summarize
- sig: `summarize(dossier: Dossier) -> ProgramReview`
- does: the node that runs before `program_review` to hand it the dossier
- does: transforms dossier into input for the review agent
- verify: json_path(path="$", matches="Resolvability:")
- code: `workflows/src/workhorse_workflows/research/nodes/dossier.py::summarize`
- tests: `workflows/tests/research/test_dossier.py`
- doc_status: "Second `does:` clause verified with `json_path` matching the resolvability summary. First clause (`the node that runs before program_review to hand it the dossier`) describes workflow positioning and sequencing, not observable function behavior, and left unbound — it requires a check like `precedes(node=...)` for workflow dependencies, which is not in the closed vocabulary."


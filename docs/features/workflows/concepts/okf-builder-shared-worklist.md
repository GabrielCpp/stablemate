---
type: concept
slug: okf-builder-shared-worklist
title: OKF-builder shared worklist
---
# OKF-builder shared worklist

The shared worklist adapter owns JSON persistence for both the build drain and the walkthrough
drain. It stamps a worklist with service, book, scope, and mode identity; selects active work
before pending work; and records completion, discovered children, retries, and operator unblocks.
Items are deduplicated by normalized kind and target. Reopening a completed item increments its
attempt count and blocks it at three attempts rather than looping forever.

- code: `workflows/src/workhorse_workflows/okf_builder/shared/worklist.py`

## Methods

### book_has_docs
- sig: `book_has_docs(features: Path) -> bool`
- does: reports true only when the feature root is a directory containing at least one Markdown file
- verify: count(subject="OKF-builder populated-book checks", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/worklist.py::book_has_docs`

### load_worklist
- sig: `load_worklist(path: Path, service: str, features: Path, *, scope_id: str = "bulk", mode: str = "bulk") -> tuple[dict[str, Any], bool]`
- does: creates a stamped empty worklist when no compatible file exists
- verify: count(subject="items in the fresh OKF-builder worklist", equals=0)
- does: rejects malformed, differently stamped, or completed-without-book worklists as stale and returns a fresh worklist
- verify: count(subject="stale OKF-builder worklist resets", equals=1)
- does: preserves a compatible worklist while refreshing its service, scope, mode, and book stamp
- verify: count(subject="compatible OKF-builder worklist resumes", equals=1)
- returns: the worklist data and whether a reset occurred
- verify: count(subject="OKF-builder worklist load results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/worklist.py::load_worklist`

### select_item
- sig: `select_item(logger: logging.Logger, worklist_path: str, max_items: int = 0, done_baseline: int = 0) -> Pick`
- does: reselects an active item before selecting the first pending item
- verify: count(subject="active-first OKF-builder worklist selections", equals=1)
- does: marks a selected item active and persists the changed worklist
- verify: persists(subject="active OKF-builder worklist item")
- does: returns an empty selection when no active or pending item remains
- verify: json_path(path="$.has_item", equals=false)
- does: returns over-budget without handing out work when pending work remains at the per-run cap
- verify: json_path(path="$.over_budget", equals=true)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/worklist.py::select_item`

### record
- sig: `record(logger: logging.Logger, worklist_path: str, current: dict[str, Any] | None = None, discovered: list[dict[str, Any]] | None = None, doc_status: str = "", note: str = "", max_attempts: int = 3, unblock: bool = False, only: tuple[str, ...] = ()) -> Recorded`
- does: marks the current matching item done and records its documentation status and note
- verify: persists(subject="closed OKF-builder worklist item")
- does: adds valid undiscovered work as pending while deduplicating normalized kind and target
- verify: created(subject="a pending worklist item identified by normalized kind and target")
- verify: count(subject="deduplicated OKF-builder discoveries", equals=1)
- does: reopens a done item when requested and increments its attempt count
- verify: count(subject="reopened OKF-builder worklist items", equals=1)
- does: changes an item to blocked when its retry count reaches the attempt limit
- verify: json_path(path="$.blocked_count", matches="[1-9][0-9]*")
- does: returns blocked rows as the standing operator-gate set
- verify: count(subject="OKF-builder blocked-row reports", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/worklist.py::record`

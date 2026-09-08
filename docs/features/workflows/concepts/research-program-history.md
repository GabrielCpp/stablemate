---
type: concept
slug: research-program-history
title: Research program history
---
# Research program history

The program event log, `history.jsonl`, tracks what the loop did, when, to which gate: one JSON line per event, written by the loop itself from the moment this module exists. A program that predates the file gets one *bootstrapped* from its progress file's dated headings (source: `bootstrap`). Bootstrap is idempotent — runs only when no file exists, and every line says where it came from — so a later reader can weight parsed history below recorded history. Every write is soft: a history line that cannot be written is logged and dropped, never stopping a run.

- code: `workflows/src/workhorse_workflows/research/nodes/history.py`
- extends: [research workflow schemas](research-schemas.md)
- detail: [research workflow composition root](research-workflow-composition-root.md)

## Module constants

### HISTORY_NAME
- type: `str`
- default: `history.jsonl`
- semantics: filename beside program.yml and ledger.yml holding loop event log
- code: `workflows/src/workhorse_workflows/research/nodes/history.py::HISTORY_NAME`

### EVENTS
- type: `tuple[str, ...]`
- default: `gate_selected`, `pass`, `fail`, `kill`, `apparatus_kill`, `build_fix`, `rework`, `rescope`, `lead_review`, `revive`, `new_direction`, `program_review`, `recharter`, `probe_ordered`, `cache_directive`, `goal`
- semantics: event vocabulary; unknown events are still written, dossier only counts these
- code: `workflows/src/workhorse_workflows/research/nodes/history.py::EVENTS`

## Methods

### method: history_path
- sig: `history_path(repo_dir: str, program_dir: str) -> Path`
- does: returns the program-relative path to the event log
- verify: json_path(path="$.path", matches="history\\.jsonl$")
- code: `workflows/src/workhorse_workflows/research/nodes/history.py::history_path`

### method: read_history
- sig: `read_history(path: Path) -> list[HistoryEvent]`
- does: returns every line that parses
- verify: count(subject="events", equals=2)
- does: skips malformed line without failing
- verify: count(subject="events", equals=2)
- does: returns empty list when file does not exist
- verify: count(subject="events", equals=0)
- code: `workflows/src/workhorse_workflows/research/nodes/history.py::read_history`

### method: write_events
- sig: `write_events(path: Path, events: list[HistoryEvent]) -> None`
- does: appends events to the log, one JSON line per event
- does: creates parent directory when it does not exist
- verify: created(subject="history file parent directory")
- code: `workflows/src/workhorse_workflows/research/nodes/history.py::write_events`

### method: append_history
- sig: `append_history(logger: logging.Logger, repo_dir: str, program_dir: str, event: str, gate_id: str = "", note: str = "", fingerprint: str = "", today: str = "") -> HistoryEvent`
- does: appends one event line with soft-fail semantics — the run never stops on bookkeeping
- verify: persists(subject="event")
- does: truncates note to 500 characters
- verify: json_path(path="$.note", matches="^.{0,500}$")
- does: defaults `today` to current date when not supplied
- verify: json_path(path="$.date", matches="^\\d{4}-\\d{2}-\\d{2}$")
- does: sets `source` to `loop` to distinguish from bootstrapped lines
- verify: json_path(path="$.source", equals="loop")
- code: `workflows/src/workhorse_workflows/research/nodes/history.py::append_history`

### method: bootstrap_history
- sig: `bootstrap_history(path: Path, events: list[HistoryEvent]) -> bool`
- does: seeds a missing history file from parsed dated entries
- verify: created(subject="history file")
- does: idempotent by construction — existing file, even empty, is left alone
- verify: unchanged(subject="history file")
- does: marks all bootstrapped lines with `source: bootstrap`
- verify: json_path(path="$.source", equals="bootstrap")
- code: `workflows/src/workhorse_workflows/research/nodes/history.py::bootstrap_history`


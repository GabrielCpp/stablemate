---
type: format
slug: attend-job
title: Attend job
---
# Attend job

One stopped run and everything an attendant needs to start on it. Holds both gate and death metadata; the `kind` field determines which branch applies.

- code: `groom/groom/attend.py::AttendJob`
- detail: [Attendant session transcript](concepts/attend-transcript.md)
- tests: `groom/tests/test_attend.py`

## Fields

### job_id
- type: `str`
- semantics: unique 12-character hex identifier, minted by `uuid.uuid4().hex[:12]`

### run_id
- type: `str`
- required: true
- semantics: identifier of the stopped run

### kind
- type: `str`
- required: true
- semantics: one of `"gate"` or `"death"` — whether the run is blocked on an operator gate or has died without reaching its own end

### workflow
- type: `str`
- required: true
- semantics: name of the workflow being executed

### run_dir
- type: `str`
- required: true
- semantics: absolute path to the run directory (repository-relative for local runs)

### workspace
- type: `str`
- required: true
- semantics: absolute path to the run's workspace
- verify: json_path(path="workspace", matches="^/.*")
- semantics: passed as the working directory (`cwd`) argument when spawning the attendant process
- code: `groom/groom/attend.py::_launch`

### created_at
- type: `float`
- required: true
- semantics: Unix timestamp when the job was created (via `time.time()` at dispatch time)

### gate_path
- type: `str`
- default: `""`
- semantics: (gate kind only) absolute path to the gate file that the run is parked on

### question
- type: `str`
- default: `""`
- semantics: (gate kind only) the verbatim gate body — unparsed, as the run recorded it
- semantics: (gate kind only) three incompatible gate formats exist in the tree — composed escalations, hand-written f-strings, raw validator dumps
- semantics: (gate kind only) the attendant reads the text intact regardless of which of those formats produced it

### failure_class
- type: `str`
- default: `""`
- semantics: (death kind only) machine-readable classification of the failure, parsed from the driver's failure handoff in `inbox.jsonl`

### node
- type: `str`
- default: `""`
- semantics: (death kind only) location in the workflow graph where the run failed, parsed from the failure handoff or checkpoint

### detail
- type: `str`
- default: `""`
- semantics: (death kind only) the failure handoff body from `inbox.jsonl`, or the run's own checkpoint and event log if no handoff exists

## Methods

### as_dict
- sig: `() -> dict`
- does: convert the job to a dictionary (flat, no nesting)
- verify: json_path(path="job_id", matches=".*")
- returns: dict with all fields as top-level keys
- verify: count(subject="keys in result", equals=12)
- code: `groom/groom/attend.py::AttendJob.as_dict`

### reason
- sig: `() -> str`
- does: return one line saying why this dispatch happened, for the row and the pane
- verify: json_path(path="$", matches="^[^\n]+$")
- returns: when `kind == "gate"`, a string of the form `"parked on {gate_path or 'an operator gate'}"`
- verify: json_path(path="$", matches="^parked on ")
- returns: when `kind == "death"`, a string of the form `"died: {failure_class or 'no failure handoff recorded'}"`
- verify: json_path(path="$", matches="^died: ")
- code: `groom/groom/attend.py::AttendJob.reason`

### facts
- sig: `() -> str`
- does: return the job as the attendant reads it — named facts and the gate body or failure details verbatim
- verify: json_path(path="$", matches="^##")
- returns: markdown string with `## The run that stopped` and `## The gate, verbatim` (or `## What the run left behind` for deaths)
- verify: json_path(path="$", matches="## The run that stopped")
- code: `groom/groom/attend.py::AttendJob.facts`

### prompt
- sig: `() -> str`
- does: return the complete attendant prompt — the library doctrine (shipped in `groom/groom/prompts/attend-gate.md`) followed by a separator and the job's `.facts()` output
- verify: json_path(path="$", matches="---")
- returns: the full prompt that will be passed on stdin to the spawned attendant
- verify: json_path(path="$", matches="## The run")
- code: `groom/groom/attend.py::AttendJob.prompt`


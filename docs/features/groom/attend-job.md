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
- required: true
- semantics: unique 12-character hex identifier, minted by `uuid.uuid4().hex[:12]`
- verify: json_path(path="$.job_id", matches="^[0-9a-f]{12}$")
- code: `groom/groom/attend.py::AttendJob.job_id`
- tests: `groom/tests/test_attend.py::test_the_row_is_written_before_the_first_byte_and_flipped_at_exit`

### run_id
- type: `str`
- required: true
- semantics: identifier of the stopped run groom is dispatching an attendant onto — opaque to groom, whatever the caller supplies (the workhorse `container_id` for native rows, the run's own id for container rows)
- verify: json_path(path="run_id", matches="^.+$")
- code: `groom/groom/attend.py::AttendJob.run_id`

### kind
- type: `str`
- required: true
- semantics: one of `"gate"` or `"death"` — whether the run is blocked on an operator gate or has died without reaching its own end

### workflow
- type: `str`
- required: true
- semantics: the workflow name (e.g., `"coder"`, `"okf-builder"`) of the run that stopped, supplied verbatim by the dispatcher at `attend_gate` or `attend_death` and persisted as the `workflow` column on the attendant row
- verify: json_path(path="$.workflow", matches="^.+$")
- code: `groom/groom/attend.py::AttendJob.workflow`

### run_dir
- type: `str`
- required: true
- semantics: the path groom uses to read the run's state — `inbox.jsonl` is read from it to parse the failure class and node for a `death` job, and `checkpoint.json` is read from it to compute the released state when the attendant finishes
- verify: json_path(path="run_dir", matches="^.+$")
- semantics: passed as the attendant process's working directory (`cwd`) when no `workspace` is supplied — `_launch` falls back to `run_dir` before `os.getcwd()` so the attendant still operates inside the run's tree
- code: `groom/groom/attend.py::AttendJob.run_dir`
- tests: `groom/tests/test_attend.py::test_a_dead_run_is_routed_by_the_class_it_recorded`

### workspace
- type: `str`
- required: true
- semantics: absolute path to the run's workspace
- verify: json_path(path="workspace", matches="^/.*")
- semantics: passed as the working directory (`cwd`) argument when spawning the attendant process — `_launch` falls back to `run_dir` then to `os.getcwd()` when `workspace` is empty, so the attendant still operates inside the run's tree
- code: `groom/groom/attend.py::AttendJob.workspace`
- tests: `groom/tests/test_attend.py::test_the_prompt_carries_the_whole_gate_not_the_dashboard_preview`

### created_at
- type: `float`
- required: true
- semantics: Unix timestamp when the job was created (via `time.time()` at dispatch time)
- verify: json_path(path="created_at", matches="^[1-9][0-9]{9,}(?:\\.[0-9]+)?$")
- code: `groom/groom/attend.py::AttendJob.created_at`
- tests: `groom/tests/test_attend.py::test_the_queue_endpoint_lists_the_fleet`

### gate_path
- type: `str`
- default: `""`
- semantics: (gate kind only) absolute path to the gate file that the run is parked on

### question
- type: `str`
- default: `""`
- semantics: (gate kind only) the verbatim gate body — unparsed, as the run recorded it
- verify: json_path(path="question", matches="^.+$")
- semantics: (gate kind only) three incompatible gate formats exist in the tree — composed escalations, hand-written f-strings, raw validator dumps
- semantics: (gate kind only) the attendant reads the text intact regardless of which of those formats produced it
- code: `groom/groom/attend.py::AttendJob.question`
- tests: `groom/tests/test_attend.py::test_a_job_carries_the_gate_body_verbatim`

### failure_class
- type: `str`
- default: `""`
- semantics: (death kind only) machine-readable classification of the failure, parsed from the driver's failure handoff in `inbox.jsonl`

### node
- type: `str`
- default: `""`
- semantics: (death kind only) name of the workflow node the failed turn recorded itself on — `read_failure` reads `inbox.jsonl`, takes the last entry with `kind="failure"`, and parses the `node: <value>` line from its body
- verify: json_path(path="$.node", matches="^.+$")
- semantics: (death kind only) when the row is rebuilt from storage in `_job_from_row`, the field is read from the stored `node` column first and only overwritten by `read_failure(run_dir)` when that call yields a value — so a corpse whose inbox entry has gone missing keeps what its prior attendance recorded
- code: `groom/groom/attend.py::AttendJob.node`
- tests: `groom/tests/test_attend.py::test_a_dead_run_is_routed_by_the_class_it_recorded`

### detail
- type: `str`
- default: `""`
- semantics: (death kind only) the verbatim `body` of the last inbox message with `kind="failure"` in `<run_dir>/inbox.jsonl` — the same entry `read_failure` parses for `failure_class` and `node`, so the field carries every `key: value` line the driver appended (including `error:`, `trace:`, any sibling keys), not just the two groom surfaces
- verify: json_path(path="$.detail", matches="boom")
- semantics: (death kind only) the empty string when no handoff exists — `read_failure` returns `("", "", "")` for a missing or unreadable `inbox.jsonl` or one with no failure entries, and `facts()` then renders `(no failure handoff — read checkpoint.json and events.jsonl)` so the attendant is steered to the run's own trail rather than given an empty body
- semantics: (death kind only) re-read from `inbox.jsonl` on each rebuild — the column is absent from the `attend_sessions` insert (`attend_start` writes the 16 named columns and no more), so `_job_from_row` always asks the run dir what the failure body now says and a resurrected attendant sees whatever was written after its prior attempt died
- code: `groom/groom/attend.py::AttendJob.detail`
- tests: `groom/tests/test_attend.py::test_a_dead_run_is_routed_by_the_class_it_recorded`

## Methods

### as_dict
- sig: `() -> dict`
- does: serialize every field as a top-level dict key with no transformation or nesting
- verify: json_path(path="$.job_id", matches="^[0-9a-f]{12}$")
- returns: dict with exactly 12 entries — `job_id`, `run_id`, `kind`, `workflow`, `run_dir`, `workspace`, `created_at`, `gate_path`, `question`, `failure_class`, `node`, `detail` — each value the field's current value
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

Two consumers, both rows-and-strings. `spawn_headless` is the only call site: it passes the returned line straight into `attend_start(reason=…)`, which writes the `reason` column of the `attend_sessions` row before the spawned process runs. The dashboard pane then reads that column back as `row.reason` to render one column of its attendant log, so the string carries the *because* the row needs to be readable stripped of all its context — a season of attendances, not one in detail. A gate's because is its own path; a death's is the class the driver recorded. The else branch is what makes that property hold for any non-gate kind the construction sites do not produce today: `attend_gate` sets `kind="gate"`, `attend_death` sets `kind="death"`, and `_job_from_row` reads whatever the column says (defaulting to `"gate"` when absent), so anything that is not literally `"gate"` lands on the death line — including a corrupted or future kind.

### facts
- sig: `() -> str`
- does: return the job as the attendant reads it — named facts and the gate body or failure details verbatim
- verify: json_path(path="$", matches="^##")
- returns: a markdown preamble with `## The run that stopped` and the five named facts (`kind`, `run_id`, `workflow`, `run_dir`, `workspace`) followed by the branch-specific section below
- verify: json_path(path="$", matches="## The run that stopped")
- returns: when `kind == "gate"`, the markdown appends a `## The gate, verbatim` section with the body returned by `self.gate_body()` — the full file content unparsed, since three incompatible gate formats exist in the tree and only handing the text over intact covers all of them
- returns: when `kind != "gate"`, the markdown appends a `## What the run left behind` section with `self.detail` or, when `detail` is empty, the fallback text `(no failure handoff — read checkpoint.json and events.jsonl)` steering the attendant to the run's own trail rather than to an empty body
- code: `groom/groom/attend.py::AttendJob.facts`
- tests: `groom/tests/test_attend.py::test_the_prompt_carries_the_whole_gate_not_the_dashboard_preview`

### prompt
- sig: `() -> str`
- does: return the complete attendant prompt — the library doctrine (shipped in `groom/groom/prompts/attend-gate.md`) followed by a separator and the job's `.facts()` output
- verify: json_path(path="$", matches="---")
- returns: the full prompt that will be passed on stdin to the spawned attendant
- verify: json_path(path="$", matches="## The run")
- code: `groom/groom/attend.py::AttendJob.prompt`


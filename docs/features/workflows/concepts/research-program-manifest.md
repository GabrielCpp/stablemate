---
type: concept
slug: research-program-manifest
title: Research program manifest
---
# Research program manifest

Path-resolution and ledger-management helpers for research programs. A "research program" is one folder in the target repo, defined by a flat `<program_dir>/program.yml` manifest beside its README ladder. Program selection uses a five-rung ladder: explicit parameter, launch-directory manifest, committed default in `agents.yml`, legacy pointer file, or failure. Ledger holds program-scoped counters (extensions, lead reviews, program reviews, re-charters) and status, persisted to disk so multi-run programs track cumulative spend and respect per-program budget caps.

- code: `workflows/src/workhorse_workflows/research/nodes/program.py`
- extends: [research workflow schemas](research-schemas.md)
- detail: [research workflow composition root](research-workflow-composition-root.md)
- detail: [research program dossier](research-program-dossier.md)
- detail: [research program history](research-program-history.md)

## Module constants

### REQUIRED
- type: `list[str]`
- default: `["code_root"]`
- semantics: flat manifest keys required before a research program can run
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::REQUIRED`

### ENVELOPE_DEFAULTS
- type: `dict[str, str | int]`
- default: `min_containment=premium, envelope_ram_gb=0, envelope_cpus=0, envelope_gpu=none, envelope_disk_gb=0`
- semantics: resource and containment defaults when a program manifest omits envelope key
- semantics: zero numeric limits are unbounded
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::ENVELOPE_DEFAULTS`

### LEDGER_NAME
- type: `str`
- default: `ledger.yml`
- semantics: program-relative filename holding cumulative spend and status
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::LEDGER_NAME`

### CONCLUDED
- type: `tuple[str, ...]`
- default: `banked`, `reached`, `impossible`
- semantics: ledger statuses that require explicit reauthorization before another run
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::CONCLUDED`

### LEDGER_HEADER
- type: `str`
- semantics: explanatory comment prefix written before every ledger update
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::LEDGER_HEADER`

## Methods

### method: parse_flat_yaml
- sig: `parse_flat_yaml(text: str, source: str) -> dict[str, str]`
- does: parses a flat `key: value` manifest with no nesting, lists, or multiline values
- verify: json_path(path="result[\"key\"]", equals="value")
- does: drops comments from each line
- verify: json_path(path="result[\"key\"]", equals="value")
- raises: `WorkflowFailed` when a line has no `:` separator
- verify: json_path(path="exception.type", equals="WorkflowFailed")
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::parse_flat_yaml`

### method: slug
- sig: `slug(program_dir: str) -> str`
- does: returns a kebab-case slug from a program path
- verify: json_path(path="result", matches="^[a-z0-9]+(-[a-z0-9]+)*$")
- does: strips `specs` and `.` path components from the input path
- verify: omits(subject="result", matches="specs|\\.")
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::slug`

### method: launch_dir
- sig: `launch_dir(launch: str = "") -> Path`
- does: returns the directory the run was launched from
- verify: created(subject="result")
- does: resolves to absolute path, or cwd when empty
- verify: json_path(path="result", matches="^/.*")
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::launch_dir`

### method: resolve_repo_root
- sig: `resolve_repo_root(arg_repo: str, launch: str = "") -> Path`
- does: returns repo root from explicit argument, launch dir's enclosing `.git`, or cwd
- verify: json_path(path="result", matches="^/.*")
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::resolve_repo_root`

### method: detect_program_from_launch
- sig: `detect_program_from_launch(repo_root: Path, launch: str = "") -> str`
- does: walks up from launch dir toward repo_root to find nearest `program.yml`
- verify: json_path(path="result", matches=".+")
- does: returns repo-relative dir of the first enclosing `program.yml`, or empty string
- verify: json_path(path="result", matches="^([^/].*)?$")
- does: stops walk at repo_root boundary
- verify: json_path(path="result", equals="")
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::detect_program_from_launch`

### method: read_agents_yaml_program
- sig: `read_agents_yaml_program(repo_root: Path) -> str`
- does: returns top-level `program:` value from repo's `agents.yml`
- verify: json_path(path="result", matches=".+")
- does: reads from `.agents.yml` as pre-farrier-1.0 fallback
- verify: json_path(path="result", matches=".+")
- does: returns empty string when no program key found or file missing
- verify: json_path(path="result", equals="")
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::read_agents_yaml_program`

### method: read_pointer
- sig: `read_pointer(repo_root: Path) -> str`
- does: returns the legacy `.agents/program` pointer (first non-empty, non-comment line)
- verify: json_path(path="result", matches=".+")
- does: returns empty string when file missing or empty
- verify: json_path(path="result", equals="")
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::read_pointer`

### method: ledger_path
- sig: `ledger_path(repo_root: Path, program_dir: str) -> Path`
- does: returns the program-relative path to the ledger file
- verify: json_path(path="result", matches="ledger\\.yml$")
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::ledger_path`

### method: read_ledger
- sig: `read_ledger(path: Path) -> Ledger`
- does: returns the program's spent counters, or a zeroed ledger when it has none yet
- verify: json_path(path="result.status", equals="active")
- does: tolerant on the way in — a hand-edited count that is not an integer reads as 0
- verify: json_path(path="result.extensions", equals="0")
- does: malformed counter must not be the thing that stops a program from being worked on
- verify: absent(subject="exception")
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::read_ledger`

### method: load_program
- sig: `load_program(logger: logging.Logger, program: str, repo_dir: str, launch_dir_path: str = "", reauthorize: bool = False) -> Program`
- does: selects a research program by five-rung ladder and reads its manifest
- verify: json_path(path="result.program", matches=".+")
- does: rung 1: explicit `program` parameter
- does: rung 2: nearest `program.yml` at-or-above launch directory, bounded by repo root
- does: rung 3: top-level `program:` value in repo's `agents.yml`
- does: rung 4: legacy `.agents/program` pointer
- does: rung 5: raises `WorkflowFailed`
- verify: json_path(path="exception.type", equals="WorkflowFailed")
- does: logs warning when `code_root` does not exist yet (greenfield programs write first experiment into it)
- does: reads program's ledger and checks for concluded status
- verify: json_path(path="result.extensions_spent", matches="^[0-9]+$")
- does: logs warning and carries `active` status when reauthorizing a concluded program
- verify: json_path(path="result.status", equals="active")
- raises: `WorkflowFailed` when `program.yml` is missing or required keys absent
- verify: json_path(path="exception.message", matches="program\\.yml")
- raises: `WorkflowFailed` when README ladder is missing
- verify: json_path(path="exception.message", matches="README\\.md")
- raises: `WorkflowFailed` when program is concluded and `reauthorize` is false
- verify: json_path(path="exception.type", equals="WorkflowFailed")
- returns: `Program` with paths, identity, ledger counters, status, and declared machine envelope
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::load_program`
- detail: [research program load authority](research-program-load-authority.md)

### method: record_spend
- sig: `record_spend(logger: logging.Logger, repo_dir: str, program_dir: str, extensions: int = 0, lead_reviews: int = 0, status: str = "active", program_reviews: int = 0, recharters: int = 0) -> Ledger`
- does: writes the program's spend back to its ledger file for the next run to read
- verify: json_path(path="result.extensions", equals="0")
- does: called on every arm that spends one and just before `publish_results`
- verify: json_path(path="result.status", equals="active")
- does: counter travels with the work it accounts for, not living only in this run's checkpoint
- verify: persists(subject="ledger")
- code: `workflows/src/workhorse_workflows/research/nodes/program.py::record_spend`
- detail: [research record spend authority](research-record-spend-authority.md)


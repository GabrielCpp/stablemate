---
type: concept
slug: visit-key
title: Agent visit key
---
# Agent visit key

`VisitKey` is the shared identity for one agent-node visit. It joins the prompt/output archive,
the backend session map, and the transcript capture as `<generation>-<seq>-<node>`; sequence
padding makes lexical order chronological.

- code: `workhorse/workhorse/turnkey.py::VisitKey`

### slug
- sig: `VisitKey.slug -> str`
- returns: the zero-padded `<generation:03d>-<seq:05d>-<node>` filename stem
- code: `workhorse/workhorse/turnkey.py::VisitKey.slug`

### attributes
- sig: `VisitKey.attributes() -> dict[str, int | str]`
- returns: generation, sequence, and node fields, plus `chain` only when a chain is present
- code: `workhorse/workhorse/turnkey.py::VisitKey.attributes`

### read_generation
- sig: `read_generation(run_dir: Path | None) -> int`
- returns: the integer in `resume_generation`, or `0` when the directory is absent or unreadable
- code: `workhorse/workhorse/turnkey.py::read_generation`

### begin
- sig: `begin(run_dir: Path | None, node_id: str, *, chain: str = "") -> VisitKey`
- does: allocates the next per-run sequence and makes the resulting key current
- does: keeps numbering nested-flow visits in the parent run's sequence
- returns: a key containing generation, sequence, node, and optional chain
- code: `workhorse/workhorse/turnkey.py::begin`
- tests: `workhorse/tests/test_turnkey.py::test_a_visit_key_names_the_node_the_generation_and_the_visit`

### current
- sig: `current() -> VisitKey | None`
- returns: the in-flight visit, or `None` outside an engine-opened visit
- code: `workhorse/workhorse/turnkey.py::current`

### clear
- sig: `clear() -> None`
- does: clears the current key and resets the process-local fallback sequence
- returns: `None`
- code: `workhorse/workhorse/turnkey.py::clear`

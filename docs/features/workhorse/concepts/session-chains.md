---
type: concept
slug: session-chains
title: Agent session chains
---
# Agent session chains

Agent turns normally use one clean backend context per node. A named chain is the deliberate
exception: its key is sanitized into a file under `<run-dir>/.sessions/`, and later laps resume
the session id stored there. The chain key is not itself a backend session id.

- code: `workhorse/workhorse/sessions.py`

### slug
- sig: `slug(key: str) -> str`
- does: replaces every character outside letters, digits, dot, underscore, and hyphen with a hyphen
- does: strips leading and trailing hyphens and uses `chain` when the result is empty
- returns: one safe filename component
- code: `workhorse/workhorse/sessions.py::slug`

### chain_path
- sig: `chain_path(run_dir: Path, key: str) -> Path`
- returns: `<run_dir>/.sessions/<slug(key)>`
- code: `workhorse/workhorse/sessions.py::chain_path`

### read_chain
- sig: `read_chain(run_dir: Path, key: str) -> str`
- consistency: returns an empty string without reading chain storage when the key is empty
- does: reads and strips the chain file when it exists
- returns: the opaque backend session id, or an empty string when unavailable
- code: `workhorse/workhorse/sessions.py::read_chain`
- verify: json_path(path="$.session_id", equals="")
- tests: `workhorse/tests/test_session_chain.py::test_the_id_a_chain_is_on_is_readable_so_a_state_can_checkpoint_it`

### run_dir_of
- sig: `run_dir_of(session_id_path: Path) -> Path`
- returns: the parent of `.sessions/<key>` for a chain file, otherwise the supplied file's parent
- code: `workhorse/workhorse/sessions.py::run_dir_of`

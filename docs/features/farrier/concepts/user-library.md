---
type: concept
slug: user-library
title: User library
---
# User library

User-library configuration selects skills and prompts once for all repositories, by harness, in
the shared stablemate configuration.

## Methods

### method: _table
- sig: `_table(value: Any, name: str) -> dict[str, Any]`
- does: validate that a configuration value is a TOML table
- raises: `SystemExit` naming the invalid table
- verify: count(subject="validated user-library tables", equals=1)
- code: `farrier/farrier/user_library.py::_table`

### method: user_library_tables
- sig: `user_library_tables(config: dict[str, Any]) -> dict[str, dict[str, Any]]`
- does: return non-empty Claude, Codex, and Copilot tables in fixed harness order
- raises: `SystemExit` for unknown harness tables or malformed values
- verify: count(subject="configured user-library harness tables", equals=1)
- code: `farrier/farrier/user_library.py::user_library_tables`

### method: user_template_values
- sig: `user_template_values(config: dict[str, Any]) -> dict[str, Any]`
- does: return one validated template mapping shared by every configured harness
- verify: count(subject="shared user-library template values", equals=1)
- code: `farrier/farrier/user_library.py::user_template_values`

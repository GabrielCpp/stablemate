---
type: concept
slug: user-library
title: User library
---
# User library

User-library configuration selects skills and prompts once for all repositories, by harness, in
the shared stablemate configuration.

## Methods

### method: user_library_tables
- sig: `user_library_tables(home: HomeConfig) -> dict[str, Selection]`
- does: return non-empty Claude, Codex, and Copilot tables in fixed harness order
- raises: `SystemExit` for unknown harness tables
- verify: count(subject="configured user-library harness tables", equals=1)
- code: `farrier/farrier/user_library.py::user_library_tables` @c71b69ee84ae

### method: user_template_values
- sig: `user_template_values(home: HomeConfig) -> dict[str, Any]`
- does: return the template mapping of the loaded home config shared by every configured harness
- verify: count(subject="shared user-library template values", equals=1)
- code: `farrier/farrier/user_library.py::user_template_values` @ec4996d8b8ce

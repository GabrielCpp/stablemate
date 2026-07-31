"""Makes `tests/coder/` a package, so its per-flow `test_flow.py` modules are distinct
from `tests/author/`'s rather than a name collision pytest reports as an import-file
mismatch. The layout mirrors the package under test: one directory per machine, and the
main graph's own suite at the top."""

---
type: concept
slug: workspace-volume-skip-directory-names
title: Workspace volume skip directory names
---
# Workspace volume skip directory names

The Docker I/O module owns one skip-directory tuple for its workspace-volume scans:
`.git`, `node_modules`, `__pycache__`, and `.venv`. Both readers use that same tuple to build
their `find` pruning expressions, so their different outputs do not imply different traversal
policies. The tuple also mirrors the sidecar's skip-directory set, keeping fallback Docker reads
and in-container scans aligned on the heavy or non-domain directories they omit.

Choose the reader that serves the requested operation: the awaiting-file reader searches
remaining regular files for the operator-gate status pattern, while the file-list reader returns
all remaining regular file paths below its selected repository root. Neither reader supersedes
the other, and neither is the authoritative definition of these names; both consume the module's
shared tuple.

- code: groom/groom/docker_io.py::_SKIP_DIRS
- rule: use the shared Docker I/O skip-directory tuple for either workspace-volume scan; choose the awaiting-file reader for gate-candidate discovery and the file-list reader for repository tree output, with no ranking between the readers
- tests: groom/tests/test_docker_io.py::test_grep_awaiting_files_prunes_heavy_dirs_and_parses_paths
- tests: groom/tests/test_docker_io.py::test_list_files_returns_repo_relative_paths_and_prunes_vendor_dirs

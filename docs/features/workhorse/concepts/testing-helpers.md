---
type: concept
title: Testing helpers
---
# Testing helpers

A workflow author tests a workflow against real git and real files, never against mocks of them.
Workhorse ships the helpers for that in `workhorse.testing`, so every workflow's tests build their
repositories and check their artifacts the same way.

- `make_git_repo(path, name="test")` creates `path` and makes it a git repository on branch
  `main`. It sets the commit identity to `t` and `t@t.com`, writes `README.md` holding
  `# <name>` unless one exists, and commits everything as `init`. It returns the path.
- `assert_file(sandbox, rel)` fails unless `rel` exists under `sandbox`.
- `assert_file_contains(sandbox, rel, text)` fails unless that file exists and contains `text`.
  The failure message prints the file's actual content.
- `assert_json_file(sandbox, rel, subset)` fails unless that file parses as JSON and matches
  `subset`. A dict subset checks only the keys it names. A list subset must equal the whole file.

A whole-workflow test drives the workflow in the test process, with no CLI subprocess. It answers
agent turns through the run's agent runner and swaps node functions through the registry's node
index, so no stand-in outlives the run. A dry run uses the same node index to put a stand-in
behind every node, as the [state machine engine](state-machine-engine.md) runs it.

The engine's own suite runs with no network and no real sleeps. Each test injects a fake agent
backend and a fake clock, as the [shared core](shared-core.md) clock rule allows. The engine's
`Makefile` names the tasks:

- `make help` lists the targets.
- `make install` syncs the local virtual environment from `uv.lock`.
- `make test` runs the suite.
- `make build` builds the sdist and the wheel into `dist/`, and `make check` lists the wheel's
  contents.
- `make verify-install` installs the published package from PyPI and imports its public API.
- `make version` prints the distribution name and version.
- `make clean` removes the build artifacts.

None of these targets publishes a release.

- code: `workhorse/workhorse/testing.py::make_git_repo` @b3e94faa9b91
- code: `workhorse/workhorse/testing.py::assert_file` @b3e94faa9b91
- code: `workhorse/workhorse/testing.py::assert_file_contains` @b3e94faa9b91
- code: `workhorse/workhorse/testing.py::assert_json_file` @b3e94faa9b91
- code: `workhorse/Makefile` @704799b57fac
- code: `workhorse/AGENTS.md` @a8083c1ef068
- code: `workhorse/docs/DEVELOPMENT.md` @8a48e4391e3e

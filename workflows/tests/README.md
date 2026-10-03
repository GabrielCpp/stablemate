# tests

The tests for the `workflows` package. Each subdirectory holds one workflow family's tests.

## Map

- `_fakes.py`: the test doubles for the ports a workflow drive is handed.
- `author/`: the `author` workflow's tests.
- `coder/`: the `coder` workflow's tests.
- `new/`: the `workhorse-new` scaffold's tests, and drives of the workflow it writes.
- `okf_book/`: the `okf-book` workflow's tests, and the fixtures they drive.
- `research/`: the `research` workflow's tests, and the program folder fixture they read.

# First win: a workflow that fixes a failing test

In ten minutes you will write a workflow of your own and watch it make a red test go green. The workflow hands a task to an agent, runs `pytest`, and sends the agent back with the failure until `pytest` exits 0.

You need `uv`, `git` and Python 3.12 or newer. The last step also needs the `claude` CLI, installed and signed in.

## 1. Install workhorse-workflows

```bash
uv tool install workhorse-workflows
uv tool install pytest
```

The first line gives you `workhorse-new` and the shipped workflows. The second puts `pytest` on your PATH, because the workflow you write runs it as its check.

## 2. Make a repo with a failing test

```bash
mkdir demo && cd demo
git init -q
cat > calc.py <<'EOF'
def add(a, b):
    return a - b
EOF
cat > test_calc.py <<'EOF'
from calc import add


def test_add():
    assert add(2, 3) == 5
EOF
git add . && git commit -qm "add has a bug"
pytest
```

`pytest` fails, which is the point:

```
FAILED test_calc.py::test_add - assert -1 == 5
```

## 3. Write the workflow, then run it

Go back up one level, so the workflow lives beside your repo and not inside it:

```bash
cd ..
workhorse-new fix-tests --check "pytest"
```

```
wrote ./fix-tests
```

That directory is a complete Python distribution. `src/fix_tests/workflow.py` holds the states, and `src/fix_tests/prompts/fix.md` is what the agent reads each round. Install it as a tool:

```bash
uv tool install ./fix-tests
```

Now dry-run it from inside the repo. A dry run stubs the agent and the check, so it starts no agent and changes nothing:

```bash
cd demo
workhorse-fix-tests run --dry-run
```

```
[workhorse] dry-run ok — every node ran its stand-in — artifacts in .../demo/.agents/runs/fix-tests-dry-run
```

Then do the real run:

```bash
workhorse-fix-tests run --cli claude
```

**The real run starts an agent that edits files and runs commands in this repo without asking your permission.** Run it in a place where that is safe, such as a throwaway clone or a virtual machine. Isolating the run is your job. The workflow does not do it for you.

## 4. What you see at the end

Each round prints a short trail. The agent works, then the check runs. A run that passes in one round ends like this:

```
[workhorse.engine] [workhorse] state  → start
[workhorse.engine] [workhorse] agent  → fix
[workhorse.engine] round 1: <one sentence from the agent about what it changed>
[workhorse.engine] [workhorse] state  → verify — the agent finished its turn
[workhorse.engine] [workhorse] call   → run_check
[workhorse.engine] [workhorse] done   ← verify — `pytest` exited 0 in round 1
[workhorse] done — artifacts in .../demo/.agents/runs/fix-tests-default
```

Your repo now holds the fix as an uncommitted change:

```bash
git diff
pytest
```

`git diff` shows `return a - b` turned into `return a + b`, and `pytest` passes. The commit is yours to make.

When `pytest` still fails after a round, the workflow sends the agent back with the tail of the output. After five rounds it stops with an error that quotes the last output. Give it more rounds with `--params '{"max_rounds": 8}'`.

## Next

- Change the check. `workhorse-new lint-clean --check "ruff check ."` writes a workflow that loops until the linter is quiet.
- Give the agent a task beyond the check with `--params '{"task": "..."}'`.
- Edit `prompts/fix.md` and `workflow.py`, reinstall with `uv tool install --reinstall ./fix-tests`, and dry-run again after every edit. [AUTHORING.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/AUTHORING.md) covers states, nodes and checkpoints.

# stablemate-library

**The base library — the workflows, scaffolds and toolchain skills that ship with
stablemate, packaged as a wheel so `pip install` alone is enough to run them.**

```bash
pip install stablemate-library
workhorse run coder          # resolves from the base — no config, no clone
```

Installing this package is the batteries-included entry point: it pulls the
engines (`workhorse-agent`, `farrier`, `ostler`) *and* the content that drives
them, at versions known to work together.

## What's in it

| Path | Contents |
|---|---|
| `workflows/` | the workflow graphs `workhorse run <name>` executes |
| `scaffolds/` | the definitions `farrier scaffold <id>` applies |
| `library/skills/stablemate/` | the skills documenting the toolchain |

That's the whole payload — markdown and YAML. The only Python here is
`base_dir()`, the accessor telling the tools where the content landed, in the
same shape as `certifi.where()`.

## Layering

The base is the **lowest-precedence** library layer. Farrier and workhorse both
resolve content across a search path:

```
1. --library / $FARRIER_LIBRARY_DIR  (explicit override)
2. the configured overlay            (farrier config set-library <dir>)
3. this package                      (the base — always present once installed)
```

An overlay shadows the base name-for-name: define a skill, pack or workflow with
the same id and yours wins. So a private library can extend the base without
forking it, and the base can be absent entirely (the tools fall back to
overlay-only behaviour, as before).

## Dependency direction

This package depends on the tools; **the tools never depend back on it.** They
discover it with an optional import:

```python
try:
    from stablemate_library import base_dir
except ImportError:
    base_dir = None   # overlay-only
```

That direction is deliberate. The workflows here call `ostler` and `workhorse`,
so this package is the one that knows which tool versions its content needs — and
it pins them in `pyproject.toml`. A dependency back would close a cycle, and it
would also drag a content edit (a reworded prompt) into a version bump of the
installer, which is exactly the churn the split exists to prevent.

## Versioning

The major version tracks the **library layout contract** (`library/skills/<group>/<name>/SKILL.md`,
`workflows/<name>/workflow.yaml`). Minor and patch track content. Pin this package
— it names a coherent, tested bundle of workflows plus the engines that run them.

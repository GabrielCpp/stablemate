---
name: python-dead-code
description: "Find and delete Python code that no production path reaches: modules only tests import, modules nothing imports, and unused functions, classes and constants. Ships a stdlib reachability script and pairs it with vulture for unused symbols. Every candidate is verified against dynamic references before deletion, and a dead module leaves with its tests and its doc mentions. Load before a refactor or a target-architecture pass, when a module looks orphaned, or when asked to trim, prune or clean up unused code. Applies to **/*.py."
tags: [architecture, standards, refactoring]
---

# Python dead code

Dead code costs the next reader twice. An agent searching for an owner finds the dead
module, trusts it, and builds on it. A test that exercises only dead code keeps it green,
so the suite reports health for code no user runs. Trim it before any restructuring, so
the target architecture is drawn around code that runs.

## What counts as dead

- **A module no root reaches.** A root is an entry point: a declared script, a
  `__main__` guard, a plugin registration. A module reached only
  through a test is dead. Its test keeps it compiling and nothing more.
- **A symbol nothing references.** A function, class, method, constant or parameter that
  no reachable code names.
- **A branch that cannot run.** A flag nobody sets, a mode nobody selects, a fallback for
  a producer that always exists.

## Tools

| Finds | Command |
|-------|---------|
| Unreachable modules | `python3 <skill>/scripts/py_unreachable.py` (this skill) |
| Unused symbols | `uvx vulture <pkg> --exclude '*_test.py,test_*.py,tests' --min-confidence 60` |

Run vulture through `uvx`. Do not add it as a dependency for one pass.

Exclude tests from the symbol scan. A symbol that only a test calls is dead, and a scan
that counts test usage reports it as used. Keep vulture at 60: at 80 it reports unused
imports and arguments only, and every unused function sits at 60. Expect noise at 60 from
format tables and enum members that mirror an external spec. Those stay, because the spec
defines them and a reader needs the full table.

### `py_unreachable.py`

It builds the import graph of every tracked `.py` file with `ast` and walks it from the
roots. Test files (`*_test.py`, `test_*.py`, `conftest.py`, anything under `tests/`) are
never roots, so a module they alone import shows as unreachable.

Roots it finds by itself:

- `[project.scripts]`, `[project.gui-scripts]` and `[project.entry-points]` in
  `pyproject.toml`.
- Any module with an `if __name__ == ...` guard, and any `__main__.py`.
- Literal strings passed to `importlib.import_module`, followed from reached modules.

Roots it cannot see, such as a framework that loads modules by path or a config file
naming handlers, go in `.agent-checks.toml`:

```toml
[dead-code]
roots = ["myapp.plugins.loader", "myapp.handlers"]
```

The first command prints the report. `--root` adds a root for one run. `--check` exits 1
when anything is dead.

```bash
python3 <skill>/scripts/py_unreachable.py
python3 <skill>/scripts/py_unreachable.py --root x.y
python3 <skill>/scripts/py_unreachable.py --check
```

The report splits unreachable modules into "imported by tests only" and "imported by
nothing", each with its line count. A `__main__` guard makes a module a root even when
the guard only runs a demo. Read each guarded root and ask whether a user runs it.

## Procedure

1. **Run the tools.** Collect the module list and the symbol list.
2. **Verify each candidate.** A tool sees static references only. For each name, search
   the whole repo, including non-code files, for:
   - the module path, dotted and slashed, and the bare file stem;
   - the symbol name as a string (`getattr`, registries, `__all__`, templates, config,
     Makefiles, CI files, shell scripts);
   - its use from a sibling repo, when the package is published or vendored.
   A hit that is a real load moves the candidate to "alive, add the root to config". A
   hit in prose moves nowhere. That prose gets fixed in step 4.
3. **Classify.** Every candidate lands in one of three rows:
   - **delete**: no real reference.
   - **wire in**: the code is wanted and the missing call is the bug. Name the caller
     that should use it and treat that as a feature, not a trim. The usual sign is an
     unused accessor on a source of truth, such as `artifacts_by_tier` on an ontology,
     next to a caller that hardcodes the same list. That caller is the defect, and
     deleting the accessor would bless it.
   - **keep with a root**: something loads it dynamically. Add it to
     `[dead-code] roots` so the next run stays quiet.
4. **Delete completely.** A dead module leaves with:
   - its tests, since a test of deleted code has nothing to test;
   - its fixtures and data files that nothing else reads;
   - every mention in `AGENTS.md`, `README.md`, maps and skills, found by grepping the
     module name;
   - re-exports in `__init__.py`.
   Then delete what the deletion orphaned. Re-run the tools until the list is empty or
   holds only "wire in" rows.
5. **Prove behaviour held.** Run the full check suite. For a program with deterministic
   output, compare output before and after on fixed inputs. Deleting dead code never
   changes output. A changed output means the code was alive.

## Rules

- **One deletion commit per concern.** A reviewer reads "remove unused reachability
  module and its tests" in one screen. A 40-file prune with unrelated renames hides a
  live deletion.
- **Never comment code out.** Git holds the history.
- **A test is not a user.** A module that only its test imports is dead, however good the
  test is. The counter-case is a library whose public API has no in-repo caller. There
  the API surface is the root, and it goes in `[dead-code] roots`.
- **A compatibility shim has an end date.** A re-export kept "for old callers" names the
  callers. When none remain in any repo that consumes it, it goes.

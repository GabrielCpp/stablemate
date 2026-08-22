"""The disk the tally stories observe, and the one way they are allowed to touch it.

`tally` is a command, and every story reaches it the same way: `python3 -m tally` through the
`python3` tool `agents.yml` opts into, over a process boundary. Reading what the command left
behind is the same boundary — there is no `open()` in a plan and nothing here leans on
`pathlib` from inside the harness, because a plan that wrote the file with `pathlib` would be
reaching around the thing it is supposed to be testing through.

That made the same four snippets and the same five wrappers appear in all three plans, which is
the drift this module exists to stop: `import-csv`, `ledger-init-add` and `report-export` each
carried their own copy of the digest reader, and a fix to one of them was a fix to one of them.

What stays in the plan is the *claim*. Every helper here takes its `covers` from the caller and
never writes one of its own, so the obligation a precondition speaks for is still a literal in
the story that owns it, readable off that plan's AST, and a story cannot silently inherit an id
that belongs to its neighbour.
"""

import json

from ostler_qa import Qa

#: Read one file as evidence: whether it is there, its digest, and its text. The digest is the
#: load-bearing half — a ledger that was rewritten with identical content is not the thing
#: `#init-a-ledger:does:2` promises, and only the bytes distinguish the two.
READ = """
import hashlib, json, pathlib, sys
p = pathlib.Path(sys.argv[1])
if p.is_file():
    raw = p.read_bytes()
    json.dump({"exists": True, "sha256": hashlib.sha256(raw).hexdigest(), "text": raw.decode("utf-8")}, sys.stdout)
else:
    json.dump({"exists": False, "sha256": None, "text": None}, sys.stdout)
"""

#: Every file under a directory, keyed by its path and valued by its digest — the witness for
#: "no write at all", which no check on the ledger alone can give. A dry run that "wrote
#: somewhere else instead" is invisible to any check that only looks at the ledger.
#:
#: It accepts either the directory or a file that lives in it, and resolves that inside the
#: snippet, so a scenario that owns a ledger can name its ledger and still never do path
#: arithmetic of its own.
CENSUS = """
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
if not root.is_dir():
    root = root.parent
found = {}
for entry in sorted(root.rglob("*")):
    if entry.is_file():
        found[str(entry.relative_to(root))] = hashlib.sha256(entry.read_bytes()).hexdigest()
json.dump(found, sys.stdout)
"""

#: Lay a file down for the product to read, over the same boundary everything else crosses.
WRITE = """
import pathlib, sys
path = pathlib.Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(sys.argv[2], encoding="utf-8")
"""


def run(qa: Qa, ledger, *argv, timeout: float = 120.0):
    """One invocation of the product, on the ledger this scenario owns.

    `qa.tool` runs at the repo root and cannot be handed a working directory, which is why
    every invocation names its ledger with `--file`: each scenario owns a directory under the
    evidence dir, and no two of them race for one `tally.json`.
    """
    return qa.tool("python3").run("-m", "tally", "--file", str(ledger), *argv, timeout=timeout)


def read_file(qa: Qa, path, covers: list[str]):
    """What is on disk at `path`, read by a separate process after the command exited."""
    got = qa.tool("python3").run("-c", READ, str(path), timeout=60.0)
    qa.require(
        f"the harness can read {path.name} back off disk",
        got.ok,
        actual=got.stderr[-2000:],
        covers=covers,
    )
    return json.loads(got.stdout)


def census_dir(qa: Qa, where, covers: list[str]):
    """Every file in `where`, by digest — or in the directory `where` lives in, if it is a file."""
    got = qa.tool("python3").run("-c", CENSUS, str(where), timeout=60.0)
    qa.require(
        "the harness can census the directory the scenario owns",
        got.ok,
        actual=got.stderr[-2000:],
        covers=covers,
    )
    return json.loads(got.stdout)


def write_file(qa: Qa, path, text, covers: list[str]):
    """Put a file where the product will read it, without touching the disk from the plan."""
    got = qa.tool("python3").run("-c", WRITE, str(path), text, timeout=60.0)
    qa.require(
        f"the harness can lay down {path.name} for the product to read",
        got.ok,
        actual=got.stderr[-2000:],
        covers=covers,
    )


def list_entries(qa: Qa, ledger, covers: list[str]):
    """The entries the ledger holds right now."""
    return json.loads(read_file(qa, ledger, covers)["text"])["entries"]

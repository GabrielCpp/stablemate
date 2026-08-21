"""The frozen QA plan for `import-csv`.

Same mechanism as story 1 and for the same reasons: the product is reached over a process
boundary as `python3 -m tally`, through the `python3` tool `agents.yml` opts into, and the
target's `driver` is `python` because that names the harness the body runs in — there is no
driver that names a transport. Nothing here imports `tally`.

What is new is that a scenario has to put a file on disk before the product reads it, and it
does that the same way it reads one: by handing a snippet to `python3`. A plan that wrote the
CSV with `pathlib` would be reaching around the boundary it is supposed to be testing through.

The two claims this story exists to make are both invisible to a single successful import.
`#import-a-csv:consistency:1` is only observable on the *second* import of the same file, and
`#import-a-malformed-row:does:1` is only observable in the bytes of a ledger that was not
written — so both are asserted against a count and a digest, never against what the command
said about itself.
"""

import json

from ostler_qa import Qa, plan, scenario, target


plan(run_id="qa-import-csv", story="import-csv")

tally = target("tally", driver="python")

# Obligation ids are written out in full at every assertion, never factored into a constant:
# `ostler qa validate` reads a `covers=` list statically off the AST, so a computed id claims
# nothing.

#: Read one file as evidence: whether it is there, its digest, and its text.
READ = """
import hashlib, json, pathlib, sys
p = pathlib.Path(sys.argv[1])
if p.is_file():
    raw = p.read_bytes()
    json.dump({"exists": True, "sha256": hashlib.sha256(raw).hexdigest(), "text": raw.decode("utf-8")}, sys.stdout)
else:
    json.dump({"exists": False, "sha256": None, "text": None}, sys.stdout)
"""

#: Every file beside the named one, keyed by its path and valued by its digest — the witness
#: for "no write at all", which no check on the ledger alone can give. It is handed a file
#: rather than a directory so the plan never does path arithmetic of its own: the scenario
#: names its ledger, and the snippet censuses the directory that ledger lives in.
CENSUS = """
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1]).parent
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

#: Three expenses, none of them already in a freshly initialised ledger.
THREE_ROWS = (
    "who,what,amount_cents,spent_on\n"
    "ana,taxi,1250,2026-03-01\n"
    "bo,dinner,4400,2026-03-01\n"
    "ana,museum,1800,2026-03-02\n"
)

#: The same file with a fourth row that is not an expense. Line 4 is the offending one, and
#: the book promises the refusal names it by its 1-based number.
ROW_FOUR_IS_NOT_MONEY = (
    "who,what,amount_cents,spent_on\n"
    "ana,taxi,1250,2026-03-01\n"
    "bo,dinner,4400,2026-03-01\n"
    "ana,museum,twenty euro,2026-03-02\n"
)


def run(qa: Qa, ledger, *argv, timeout: float = 120.0):
    """One invocation of the product, on the ledger this scenario owns."""
    return qa.tool("python3").run("-m", "tally", "--file", str(ledger), *argv, timeout=timeout)


def read(qa: Qa, path):
    """What is on disk at `path`, read by a separate process after the command exited."""
    got = qa.tool("python3").run("-c", READ, str(path), timeout=60.0)
    qa.require(
        f"the harness can read {path.name} back off disk",
        got.ok,
        actual=got.stderr[-2000:],
        covers=["okf:docs/features/tally/tally.md#import:contract"],
    )
    return json.loads(got.stdout)


def census(qa: Qa, sibling):
    """Every file in the directory `sibling` lives in, by digest."""
    got = qa.tool("python3").run("-c", CENSUS, str(sibling), timeout=60.0)
    qa.require(
        "the harness can census the directory the ledger lives in",
        got.ok,
        actual=got.stderr[-2000:],
        covers=["okf:docs/features/tally/tally.md#import:contract"],
    )
    return json.loads(got.stdout)


def write(qa: Qa, path, text):
    """Put a file where the product will read it, without touching the disk from the plan."""
    got = qa.tool("python3").run("-c", WRITE, str(path), text, timeout=60.0)
    qa.require(
        f"the harness can lay down {path.name} for the product to read",
        got.ok,
        actual=got.stderr[-2000:],
        covers=["okf:docs/features/tally/tally.md#import:contract"],
    )


def entries(qa: Qa, ledger):
    """The entries the ledger holds right now."""
    return json.loads(read(qa, ledger)["text"])["entries"]


@scenario(
    target=tally,
    mechanism="live",
    timeout=600.0,
    covers=[
        "okf:docs/features/tally/tally.md#import:contract",
        "okf:docs/features/tally/tally.md#import:does:1",
        "okf:docs/features/tally/tally.md#import-a-csv:consistency:1",
        "okf:docs/features/tally/tally.md#import-a-csv:contract",
        "okf:docs/features/tally/tally.md#import-a-csv:does:1",
    ],
    preconditions=[
        "the scenario owns a directory under the evidence dir holding a freshly initialised ledger",
        "the CSV is written by a separate process, not by the plan",
    ],
    checkpoints=[
        "importing a three-row file into an empty ledger adds all three and exits 0",
        "importing the same file a second time exits 0 and leaves three",
        "the entries after the second import are the same three, not three of six",
    ],
    forbid=[
        "asserting idempotence by the second import's exit code — the doubling form of this defect exits 0",
        "importing only once, which cannot distinguish `merge` from `extend`",
    ],
)
def importing_the_same_file_twice_leaves_what_importing_it_once_left(qa: Qa) -> None:
    """`#import-a-csv`, including the half that only the second run can see."""
    ledger = qa.artifact("import/tally.json", kind="json")
    rows = qa.artifact("import/trip.csv", kind="log")

    started = run(qa, ledger, "init", "--currency", "EUR")
    qa.require(
        "the scenario could initialise the ledger it imports into",
        started.ok,
        actual=started.stderr[-2000:],
        covers=["okf:docs/features/tally/tally.md#import-a-csv:contract"],
    )
    write(qa, rows, THREE_ROWS)

    before = entries(qa, ledger)
    qa.require(
        "the ledger holds none of the rows before the import",
        len(before) == 0,
        actual=before,
        expected=[],
        covers=["okf:docs/features/tally/tally.md#import-a-csv:does:1"],
    )

    imported = run(qa, ledger, "import", str(rows))
    qa.check(
        "`tally import` on a file whose every row parses exits 0",
        imported.exit_code == 0,
        actual=imported.exit_code,
        expected=0,
        covers=[
            "okf:docs/features/tally/tally.md#import:contract",
            "okf:docs/features/tally/tally.md#import:does:1",
        ],
    )

    after = entries(qa, ledger)
    qa.verify(
        "created",
        (before, after),
        subject="the rows the ledger did not already hold",
        covers=[
            "okf:docs/features/tally/tally.md#import-a-csv:consistency:1",
            "okf:docs/features/tally/tally.md#import-a-csv:contract",
            "okf:docs/features/tally/tally.md#import-a-csv:does:1",
        ],
    )

    # The second import is the assertion. A `merge` that appends instead of merging is
    # indistinguishable from a correct one up to this line: same exit code, same message
    # shape, same ledger. What separates them is how many entries are in the file after.
    again = run(qa, ledger, "import", str(rows))
    qa.check(
        "importing the same file a second time exits 0",
        again.exit_code == 0,
        actual=again.exit_code,
        expected=0,
        covers=["okf:docs/features/tally/tally.md#import-a-csv:consistency:1"],
    )

    settled = entries(qa, ledger)
    qa.verify(
        "count",
        settled,
        subject="entries in the ledger",
        equals=3,
        covers=[
            "okf:docs/features/tally/tally.md#import-a-csv:consistency:1",
            "okf:docs/features/tally/tally.md#import-a-csv:contract",
            "okf:docs/features/tally/tally.md#import-a-csv:does:1",
        ],
    )
    qa.check(
        "the entries after the second import are the three the file held",
        sorted(entry["what"] for entry in settled) == ["dinner", "museum", "taxi"],
        actual=sorted(entry["what"] for entry in settled),
        expected=["dinner", "museum", "taxi"],
        covers=["okf:docs/features/tally/tally.md#import-a-csv:consistency:1"],
    )


@scenario(
    target=tally,
    mechanism="live",
    timeout=600.0,
    covers=[
        "okf:docs/features/tally/tally.md#import-a-malformed-row:contract",
        "okf:docs/features/tally/tally.md#import-a-malformed-row:does:1",
        "okf:docs/features/tally/tally.md#import-a-malformed-row:errors:1",
        "okf:docs/features/tally/tally.md#import-a-malformed-row:status:1",
    ],
    preconditions=[
        "the ledger already holds an entry, so a partial import has something to be partial against",
        "the offending row is the last of three, so a whole-file refusal and a row-by-row one differ observably",
    ],
    checkpoints=[
        "a file with a row that is not an expense exits 2",
        "the message names the 1-based line number of that row",
        "the ledger is byte-for-byte what it was before the import",
    ],
    forbid=[
        "asserting the diagnostic without asserting the exit code, or the exit code without the file",
        "reading the ledger as parsed JSON instead of as bytes — a rewrite with equal content is still a rewrite",
    ],
)
def a_malformed_row_refuses_the_whole_file_and_leaves_the_ledger_alone(qa: Qa) -> None:
    """`#import-a-malformed-row`: three separable claims, each with its own witness."""
    ledger = qa.artifact("malformed/tally.json", kind="json")
    rows = qa.artifact("malformed/trip.csv", kind="log")

    started = run(qa, ledger, "init", "--currency", "EUR")
    qa.require(
        "the scenario could initialise the ledger",
        started.ok,
        actual=started.stderr[-2000:],
        covers=["okf:docs/features/tally/tally.md#import-a-malformed-row:contract"],
    )
    recorded = run(qa, ledger, "add", "ana", "taxi", "1250", "2026-03-01")
    qa.require(
        "the ledger holds an entry the refused import could destroy",
        recorded.ok,
        actual=recorded.stderr[-2000:],
        covers=["okf:docs/features/tally/tally.md#import-a-malformed-row:does:1"],
    )
    write(qa, rows, ROW_FOUR_IS_NOT_MONEY)

    before = read(qa, ledger)
    refused = run(qa, ledger, "import", str(rows))
    after = read(qa, ledger)

    qa.check(
        "`tally import` on a file with a row that is not an expense exits 2",
        refused.exit_code == 2,
        actual=refused.exit_code,
        expected=2,
        covers=["okf:docs/features/tally/tally.md#import-a-malformed-row:status:1"],
    )
    qa.check(
        "the refusal names the 1-based line number of the offending row",
        "line 4" in refused.stderr,
        actual=refused.stderr[-2000:],
        expected="a message naming line 4",
        covers=["okf:docs/features/tally/tally.md#import-a-malformed-row:errors:1"],
    )
    qa.verify(
        "unchanged",
        ({"tally.json": before["sha256"]}, {"tally.json": after["sha256"]}),
        subject="tally.json",
        covers=[
            "okf:docs/features/tally/tally.md#import-a-malformed-row:contract",
            "okf:docs/features/tally/tally.md#import-a-malformed-row:does:1",
            "okf:docs/features/tally/tally.md#import-a-malformed-row:errors:1",
            "okf:docs/features/tally/tally.md#import-a-malformed-row:status:1",
        ],
    )
    qa.check(
        "the one entry the ledger held before the refused import is still the only one",
        len(json.loads(after["text"])["entries"]) == 1,
        actual=json.loads(after["text"])["entries"],
        expected="the single entry added before the import",
        covers=["okf:docs/features/tally/tally.md#import-a-malformed-row:does:1"],
    )


@scenario(
    target=tally,
    mechanism="live",
    timeout=600.0,
    covers=[
        "okf:docs/features/tally/tally.md#dry-run:contract",
        "okf:docs/features/tally/tally.md#dry-run:default:1",
        "okf:docs/features/tally/tally.md#dry-run:required:1",
        "okf:docs/features/tally/tally.md#dry-run:semantics:1",
        "okf:docs/features/tally/tally.md#dry-run:semantics:2",
        "okf:docs/features/tally/tally.md#dry-run:semantics:3",
    ],
    preconditions=[
        "the scenario owns a directory nothing else writes to, so a census of it is a census of what the command did",
        "the ledger holds an entry, so a dry run that wrote would be observable as a change rather than as a creation",
    ],
    checkpoints=[
        "`import --dry-run` exits 0 and still says what it would have done",
        "every file in the scenario's directory is byte-for-byte what it was — not just the ledger",
        "the same import without the flag does change it, which is what makes the flag's absence the default",
    ],
    forbid=[
        "censusing only the ledger — `semantics:2` is the claim that nothing was written *anywhere*",
        "taking the dry run's own report as evidence that it did not write",
    ],
)
def a_dry_run_reports_what_it_would_do_and_writes_nothing_anywhere(qa: Qa) -> None:
    """`#dry-run` over `import`, witnessed by a census rather than by the ledger."""
    ledger = qa.artifact("dry-run/tally.json", kind="json")
    rows = qa.artifact("dry-run/trip.csv", kind="log")

    started = run(qa, ledger, "init", "--currency", "EUR")
    recorded = run(qa, ledger, "add", "ana", "taxi", "1250", "2026-03-01")
    qa.require(
        "the scenario could set up a ledger with something in it",
        started.ok and recorded.ok,
        actual=started.stderr[-1000:] + recorded.stderr[-1000:],
        covers=["okf:docs/features/tally/tally.md#dry-run:contract"],
    )
    write(qa, rows, THREE_ROWS)

    before = census(qa, ledger)
    previewed = run(qa, ledger, "import", str(rows), "--dry-run")
    after = census(qa, ledger)

    qa.check(
        "`import --dry-run` exits 0",
        previewed.exit_code == 0,
        actual=previewed.exit_code,
        expected=0,
        covers=[
            "okf:docs/features/tally/tally.md#dry-run:contract",
            "okf:docs/features/tally/tally.md#dry-run:semantics:3",
        ],
    )
    qa.check(
        "it still reports what it would have done",
        "dry-run" in previewed.stderr,
        actual=previewed.stderr[-2000:],
        expected="a line on stderr naming the dry run",
        covers=["okf:docs/features/tally/tally.md#dry-run:semantics:3"],
    )
    qa.check(
        "every file in the scenario's directory is byte-for-byte what it was",
        after == before,
        actual=after,
        expected=before,
        covers=[
            "okf:docs/features/tally/tally.md#dry-run:semantics:1",
            "okf:docs/features/tally/tally.md#dry-run:semantics:2",
        ],
    )
    qa.check(
        "and no file appeared or vanished, which a write-somewhere-else would show as either",
        sorted(after) == sorted(before),
        actual=sorted(after),
        expected=sorted(before),
        covers=["okf:docs/features/tally/tally.md#dry-run:semantics:2"],
    )

    # The default is only a claim if the flag's absence behaves differently. Same command,
    # same file, one flag less.
    committed = run(qa, ledger, "import", str(rows))
    landed = census(qa, ledger)
    qa.check(
        "the same import without the flag does write, so `false` is the default rather than the only behaviour",
        committed.exit_code == 0 and landed != before,
        actual=sorted(landed),
        expected="a directory whose ledger digest has moved",
        covers=[
            "okf:docs/features/tally/tally.md#dry-run:default:1",
            "okf:docs/features/tally/tally.md#dry-run:required:1",
        ],
    )


@scenario(
    target=tally,
    mechanism="live",
    timeout=600.0,
    covers=[
        "okf:docs/features/tally/tally.md#file:contract",
        "okf:docs/features/tally/tally.md#file:default:1",
        "okf:docs/features/tally/tally.md#file:required:1",
        "okf:docs/features/tally/tally.md#file:semantics:1",
        "okf:docs/features/tally/tally.md#file:semantics:2",
    ],
    preconditions=[
        "two ledgers in one directory, each named on its own invocations",
        "the default and the optionality are read off `--help`, because a command run without `--file` would write into the repo root: `qa.tool` has no working directory to give it",
    ],
    checkpoints=[
        "an import into one ledger leaves the other exactly as it was",
        "`--help` states the default is `tally.json` and shows `--file` as optional",
        "`--file` after the subcommand is refused, so one invocation names one ledger",
    ],
    forbid=[
        "running the product without `--file` — that writes wherever the tool happens to run",
    ],
)
def two_ledgers_in_one_directory_never_see_each_other(qa: Qa) -> None:
    """`#file`: the separation, and the two claims about the flag itself."""
    here = qa.artifact("two-ledgers/tally.json", kind="json")
    there = qa.artifact("two-ledgers/other.json", kind="json")
    rows = qa.artifact("two-ledgers/trip.csv", kind="log")

    first = run(qa, here, "init", "--currency", "EUR")
    second = run(qa, there, "init", "--currency", "EUR")
    qa.require(
        "the scenario could create two ledgers side by side",
        first.ok and second.ok,
        actual=first.stderr[-1000:] + second.stderr[-1000:],
        covers=["okf:docs/features/tally/tally.md#file:contract"],
    )
    write(qa, rows, THREE_ROWS)

    untouched = read(qa, there)
    imported = run(qa, here, "import", str(rows))
    qa.check(
        "an import names the ledger it acts on and exits 0",
        imported.exit_code == 0,
        actual=imported.exit_code,
        expected=0,
        covers=["okf:docs/features/tally/tally.md#file:contract"],
    )
    qa.check(
        "the ledger it named holds the three rows",
        len(entries(qa, here)) == 3,
        actual=len(entries(qa, here)),
        expected=3,
        covers=["okf:docs/features/tally/tally.md#file:semantics:1"],
    )
    stood = read(qa, there)
    qa.check(
        "the other ledger in the same directory is byte-for-byte what it was",
        stood["sha256"] == untouched["sha256"],
        actual=stood["sha256"],
        expected=untouched["sha256"],
        covers=["okf:docs/features/tally/tally.md#file:semantics:1"],
    )

    helped = qa.tool("python3").run("-m", "tally", "--help", timeout=60.0)
    qa.check(
        "`--help` states the default ledger is `tally.json`",
        "default: tally.json" in helped.stdout,
        actual=helped.stdout[-2000:],
        expected="a usage line naming tally.json as the default",
        covers=["okf:docs/features/tally/tally.md#file:default:1"],
    )
    qa.check(
        "`--help` shows `--file` as optional",
        "[--file FILE]" in helped.stdout,
        actual=helped.stdout[-2000:],
        expected="an optional --file in the usage line",
        covers=["okf:docs/features/tally/tally.md#file:required:1"],
    )

    misplaced = qa.tool("python3").run(
        "-m", "tally", "import", str(rows), "--file", str(there), timeout=60.0
    )
    qa.check(
        "`--file` after the subcommand is refused, so one invocation cannot name two ledgers",
        misplaced.exit_code != 0,
        actual=misplaced.exit_code,
        expected="a non-zero exit",
        covers=["okf:docs/features/tally/tally.md#file:semantics:2"],
    )

"""The frozen QA plan for `report-export`.

Same mechanism as the two stories before it — `python3 -m tally` through the `python3` tool,
`driver="python"` for the harness the body runs in, nothing imported from `tally`.

What this story adds is that the observable is a *stream*, and the two claims it has to make
about that stream are claims about the whole of it rather than about anything in it.
`#report-as-json:consistency:1` says stdout carries exactly one JSON object, so the assertion
is that the entire captured stdout parses as one document — a grep for a total passes on a
stream with a line of prose in front of it, and a caller's `json.load` does not. And
`#export-to-csv:consistency:1` says the first line is the header, so the assertion reads line
one as a header rather than counting lines or checking the file arrived: an export missing its
header is valid CSV with correct values in every field.

The empty ledger is exported too, and on purpose. "Header, whether or not the ledger has
entries" is the half of that bullet that a populated export cannot distinguish from an export
that writes a header only when it has something to put under it.
"""

import json

from ostler_qa import Qa, plan, scenario, target


plan(run_id="qa-report-export", story="report-export")

tally = target("tally", driver="python")

#: Read one file as evidence: whether it is there, its digest, and its text.
_READ = """
import hashlib, json, pathlib, sys
p = pathlib.Path(sys.argv[1])
if p.is_file():
    raw = p.read_bytes()
    json.dump({"exists": True, "sha256": hashlib.sha256(raw).hexdigest(), "text": raw.decode("utf-8")}, sys.stdout)
else:
    json.dump({"exists": False, "sha256": None, "text": None}, sys.stdout)
"""


#: Every file under a directory, keyed by its path and valued by its digest.
_CENSUS = """
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
_WRITE = """
import pathlib, sys
path = pathlib.Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(sys.argv[2], encoding="utf-8")
"""


def run(qa: Qa, ledger, *argv, timeout: float = 120.0):
    """One invocation of the product, on the ledger this scenario owns.

    Duplicated per plan rather than shared through a fixture module: `qa: {fixture_modules:}`
    is retired, and this plan is frozen corpus, so the cost of the duplicate is a fixed one.
    """
    return qa.tool("python3").run("-m", "tally", "--file", str(ledger), *argv, timeout=timeout)


def read(qa: Qa, path):
    """What is on disk at `path`, read by a separate process after the command exited."""
    covers = ["okf:docs/features/tally/tally.md#export:contract"]
    got = qa.tool("python3").run("-c", _READ, str(path), timeout=60.0)
    qa.require(
        f"the harness can read {path.name} back off disk",
        got.ok,
        actual=got.stderr[-2000:],
        covers=covers,
    )
    return json.loads(got.stdout)


def lines(qa: Qa, record):
    """The lines of a file read by `read`, or nothing at all when it is not there.

    Read through `qa.field` rather than by subscript: a fixture that came back shaped
    differently would raise here and take the whole scenario down as `unproven`, where
    `MISSING` lets the assertion downstream go red and say so.
    """
    if not qa.field(record, "exists"):
        return []
    return [line for line in qa.field(record, "text").splitlines() if line != ""]


def entries(qa: Qa, ledger):
    """The entries the ledger holds right now."""
    text = qa.field(read(qa, ledger), "text")
    return qa.field(json.loads(text), "entries")


def census(qa: Qa, sibling):
    """Every file in the directory `sibling` lives in, by digest."""
    got = qa.tool("python3").run("-c", _CENSUS, str(sibling), timeout=60.0)
    qa.require(
        "the harness can census the directory the scenario owns",
        got.ok,
        actual=got.stderr[-2000:],
    )
    return json.loads(got.stdout)


def write(qa: Qa, path, text):
    """Put a file where the product will read it, without touching the disk from the plan."""
    got = qa.tool("python3").run("-c", _WRITE, str(path), text, timeout=60.0)
    qa.require(
        f"the harness can lay down {path.name} for the product to read",
        got.ok,
        actual=got.stderr[-2000:],
    )


#: One expense, importable into a ledger the same way `add` would put one there.
ONE_ROW = "who,what,amount_cents,spent_on\ncyd,coffee,300,2026-03-03\n"


def trip(qa: Qa, ledger):
    """A ledger in EUR holding three expenses across two people."""
    before = read(qa, ledger)
    started = run(qa, ledger, "init", "--currency", "EUR")
    qa.require(
        "the scenario could initialise the ledger it reports on",
        started.ok,
        actual=started.stderr[-1000:],
        covers=[
            "okf:docs/features/tally/tally.md:contract",
            "okf:docs/features/tally/tally.md#init:contract",
        ],
    )
    qa.verify(
        "created",
        (lines(qa, before), lines(qa, read(qa, ledger))),
        subject="tally.json",
        covers=["okf:docs/features/tally/tally.md#init:does:1"],
    )

    first = run(qa, ledger, "add", "ana", "taxi", "1250", "2026-03-01")
    qa.require(
        "the scenario could record the first expense",
        first.ok,
        actual=first.stderr[-500:],
        covers=["okf:docs/features/tally/tally.md#add:contract"],
    )
    qa.verify(
        "count",
        entries(qa, ledger),
        subject="entries in the ledger",
        equals=1,
        covers=["okf:docs/features/tally/tally.md#add:does:1"],
    )

    spent = [
        run(qa, ledger, "add", "bo", "dinner", "4400", "2026-03-01"),
        run(qa, ledger, "add", "ana", "museum", "1800", "2026-03-02"),
    ]
    qa.require(
        "the scenario could build the ledger it reports on",
        all(one.ok for one in spent),
        actual="".join(one.stderr[-500:] for one in spent),
        covers=["okf:docs/features/tally/tally.md#report:contract"],
    )


@scenario(
    target=tally,
    mechanism="live",
    timeout=600.0,
    covers=[
        "ac:1",
        "ac:2",
        "ac:3",
        "okf:docs/features/tally/tally.md:contract",
        "okf:docs/features/tally/tally.md#init:contract",
        "okf:docs/features/tally/tally.md#init:does:1",
        "okf:docs/features/tally/tally.md#add:contract",
        "okf:docs/features/tally/tally.md#add:does:1",
        "okf:docs/features/tally/tally.md#report:contract",
        "okf:docs/features/tally/tally.md#report:does:1",
        "okf:docs/features/tally/tally.md#report-as-json:consistency:1",
        "okf:docs/features/tally/tally.md#report-as-json:consistency:2",
        "okf:docs/features/tally/tally.md#report-as-json:contract",
        "okf:docs/features/tally/tally.md#report-as-json:does:1",
    ],
    preconditions=[
        "the ledger holds three expenses across two people, so per-person and overall totals differ",
        "the ledger was initialised in EUR, which is the code every report must state",
    ],
    checkpoints=[
        "the whole of stdout parses as one JSON document, not just some line in it",
        "the report states the currency the ledger was initialised with",
        "the progress line the command writes is on stderr, and stdout holds nothing but the object",
        "the totals are the ledger's, and `total_cents` is the sum of `per_person`",
    ],
    forbid=[
        "grepping stdout for a total — that passes on a stream with a line of prose in front of the object",
        "reading only the last line of stdout, which is the same pass by another route",
    ],
)
def report_json_puts_one_object_on_stdout_and_everything_else_on_stderr(qa: Qa) -> None:
    """`#report-as-json`: the report, and the purity of the stream carrying it."""
    ledger = qa.artifact("report/tally.json", kind="json")
    trip(qa, ledger)

    plain = run(qa, ledger, "report")
    qa.check(
        "`tally report` totals the ledger and exits 0",
        plain.exit_code == 0 and "3 entries" in plain.stdout,
        actual=plain.stdout[-2000:],
        expected="a report naming 3 entries",
        covers=[
            "ac:1",
            "okf:docs/features/tally/tally.md#report:contract",
            "okf:docs/features/tally/tally.md#report:does:1",
        ],
    )

    piped = run(qa, ledger, "report", "--json")
    qa.check(
        "`tally report --json` exits 0",
        piped.exit_code == 0,
        actual=piped.exit_code,
        expected=0,
        covers=["ac:2", "okf:docs/features/tally/tally.md#report-as-json:contract"],
    )

    # The whole stream, in one call, the way a caller who piped this reads it. A progress
    # line in front of the object leaves every field of the report correct and this line the
    # only thing that fails.
    decoded = None
    parsed = True
    try:
        decoded = json.loads(piped.stdout)
    except json.JSONDecodeError:
        parsed = False
    qa.check(
        "the whole of stdout parses as exactly one JSON document",
        parsed and isinstance(decoded, dict),
        actual=piped.stdout[-2000:],
        expected="one JSON object and nothing else on stdout",
        covers=["ac:2", "okf:docs/features/tally/tally.md#report-as-json:consistency:1"],
    )
    qa.require(
        "there is a report to make claims about",
        parsed,
        actual=piped.stdout[-2000:],
        covers=["okf:docs/features/tally/tally.md#report-as-json:consistency:1"],
    )
    qa.verify(
        "json_path",
        decoded,
        path="$.currency",
        equals="EUR",
        covers=[
            "ac:3",
            "okf:docs/features/tally/tally.md#report-as-json:consistency:1",
            "okf:docs/features/tally/tally.md#report-as-json:consistency:2",
            "okf:docs/features/tally/tally.md#report-as-json:contract",
            "okf:docs/features/tally/tally.md#report-as-json:does:1",
        ],
    )
    qa.check(
        "the human-facing progress line is on stderr",
        "totalling" in piped.stderr and "totalling" not in piped.stdout,
        actual={"stdout": piped.stdout[-1000:], "stderr": piped.stderr[-1000:]},
        expected="the progress line on stderr and absent from stdout",
        covers=["ac:2", "okf:docs/features/tally/tally.md#report-as-json:consistency:2"],
    )
    qa.verify(
        "json_path",
        decoded,
        path="$.total_cents",
        equals="7450",
        covers=[
            "ac:1",
            "ac:3",
            "okf:docs/features/tally/tally.md#report:does:1",
            "okf:docs/features/tally/tally.md#report-as-json:does:1",
        ],
    )
    qa.check(
        "the totals are the ledger's, and the overall is the sum of the per-person ones",
        qa.field(decoded, "entries") == 3 and (sum(qa.field(decoded, "per_person").values()) == qa.field(decoded, "total_cents")),
        actual=decoded,
        expected={"entries": 3, "total_cents": 7450, "per_person": {"ana": 3050, "bo": 4400}},
        covers=["ac:1", "ac:3", "okf:docs/features/tally/tally.md#report-as-json:does:1"],
    )


@scenario(
    target=tally,
    mechanism="live",
    timeout=600.0,
    covers=[
        "ac:4",
        "ac:5",
        "okf:docs/features/tally/tally.md#export:contract",
        "okf:docs/features/tally/tally.md#export:does:1",
        "okf:docs/features/tally/flows/track-a-trip.md:start:1",
        "okf:docs/features/tally/flows/track-a-trip.md:end:1",
        "okf:docs/features/tally/flows/track-a-trip.md:end-state",
        "okf:docs/features/tally/tally.md#export-to-csv:consistency:1",
        "okf:docs/features/tally/tally.md#export-to-csv:contract",
        "okf:docs/features/tally/tally.md#export-to-csv:does:1",
    ],
    preconditions=[
        "the ledger is built the way the journey builds one, with `init` and then `add`",
        "the destination does not exist before the export, so `created` has both halves",
        "a second, empty ledger is exported too — the header claim is 'whether or not the ledger has entries'",
    ],
    checkpoints=[
        "the report the journey reads before handing the trip on states the currency it was initialised with",
        "the export writes a file that was not there, and exits 0",
        "its first line is the header `who,what,amount_cents,spent_on`",
        "it holds one line per entry under that header",
        "the export of an empty ledger is the header alone, not an empty file",
    ],
    forbid=[
        "counting lines, or asserting only that the file arrived — both pass on an export with no header",
        "reading the first record with a header-aware CSV reader, which consumes line one whatever it says",
    ],
)
def an_export_leads_with_its_header_even_when_there_is_nothing_under_it(qa: Qa) -> None:
    """`#export-to-csv`: the file, and the line every reader of it skips."""
    ledger = qa.artifact("export/tally.json", kind="json")
    destination = qa.artifact("export/trip.csv", kind="log")
    trip(qa, ledger)

    before = read(qa, destination)
    qa.require(
        "nothing is at the destination before the export",
        not qa.field(before, "exists"),
        actual=before,
        covers=["okf:docs/features/tally/tally.md#export:contract"],
    )

    exported = run(qa, ledger, "export", str(destination))
    qa.check(
        "`tally export` exits 0 and says how many rows it wrote",
        exported.exit_code == 0 and "3 rows" in exported.stderr,
        actual={"exit": exported.exit_code, "stderr": exported.stderr[-1000:]},
        expected="exit 0 and a stderr line naming 3 rows",
        covers=[
            "ac:4",
            "okf:docs/features/tally/tally.md#export:contract",
            "okf:docs/features/tally/tally.md#export:does:1",
            "okf:docs/features/tally/flows/track-a-trip.md:end:1",
        ],
    )

    after = read(qa, destination)
    qa.verify(
        "created",
        (lines(qa, before), lines(qa, after)),
        subject="the exported CSV file",
        covers=[
            "okf:docs/features/tally/tally.md#export:does:1",
            "okf:docs/features/tally/tally.md#export-to-csv:consistency:1",
            "okf:docs/features/tally/tally.md#export-to-csv:contract",
            "okf:docs/features/tally/tally.md#export-to-csv:does:1",
        ],
    )

    written = lines(qa, after)
    qa.check(
        "its first line is the header, read as a line rather than skipped as one",
        written[:1] == ["who,what,amount_cents,spent_on"],
        actual=written[:1],
        expected=["who,what,amount_cents,spent_on"],
        covers=["ac:5", "okf:docs/features/tally/tally.md#export-to-csv:consistency:1"],
    )
    qa.check(
        "under it is one line per entry in the ledger",
        len(written) == 4,
        actual=written,
        expected="a header and three data lines",
        covers=["ac:4", "okf:docs/features/tally/flows/track-a-trip.md:end:1", "okf:docs/features/tally/tally.md#export-to-csv:does:1"],
    )

    # `init`, `add`, `report`, `export` is the whole journey, and the trip that has just been
    # handed on is only the trip that was started if the ledger behind the CSV still says so.
    walked = run(qa, ledger, "report", "--json")
    qa.require(
        "the journey's ledger still reports after the trip has been handed on",
        walked.ok,
        actual=walked.stderr[-1000:],
        covers=["okf:docs/features/tally/flows/track-a-trip.md:end-state"],
    )
    qa.verify(
        "json_path",
        json.loads(walked.stdout),
        path="$.currency",
        equals="EUR",
        covers=["okf:docs/features/tally/flows/track-a-trip.md:start:1", "okf:docs/features/tally/flows/track-a-trip.md:end:1", "okf:docs/features/tally/flows/track-a-trip.md:end-state"],
    )

    # The other half of the bullet: an export whose header appears only when there is data
    # is indistinguishable from a correct one up to here.
    empty_ledger = qa.artifact("export-empty/tally.json", kind="json")
    empty_csv = qa.artifact("export-empty/trip.csv", kind="log")
    started = run(qa, empty_ledger, "init", "--currency", "EUR")
    emptied = run(qa, empty_ledger, "export", str(empty_csv))
    qa.require(
        "the scenario could export a ledger with nothing in it",
        started.ok and emptied.ok,
        actual=started.stderr[-1000:] + emptied.stderr[-1000:],
        covers=["okf:docs/features/tally/tally.md#export-to-csv:consistency:1"],
    )
    qa.check(
        "the export of an empty ledger is the header alone",
        lines(qa, read(qa, empty_csv)) == ["who,what,amount_cents,spent_on"],
        actual=lines(qa, read(qa, empty_csv)),
        expected=["who,what,amount_cents,spent_on"],
        covers=["ac:5", "okf:docs/features/tally/tally.md#export-to-csv:consistency:1"],
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
        "two ledgers in one directory, with different contents, each named on its own invocations",
        "the default and the optionality are read off `--help`: a command run without `--file` would act on whatever ledger is at the tool's working directory",
    ],
    checkpoints=[
        "a report names the ledger it totals, and gets that ledger's numbers rather than the neighbour's",
        "`--help` states the default is `tally.json` and shows `--file` as optional",
        "`--file` after the subcommand is refused, so one invocation names one ledger",
    ],
    forbid=[
        "running the product without `--file` — that acts wherever the tool happens to run",
        "giving the two ledgers the same contents, which makes reading the wrong one invisible",
    ],
)
def a_report_totals_the_ledger_it_was_given_and_not_its_neighbour(qa: Qa) -> None:
    """`#file`, over the reading commands: the separation, and the flag's own two claims."""
    here = qa.artifact("two-ledgers/tally.json", kind="json")
    there = qa.artifact("two-ledgers/other.json", kind="json")

    trip(qa, here)
    started = run(qa, there, "init", "--currency", "EUR")
    lone = run(qa, there, "add", "cyd", "coffee", "300", "2026-03-03")
    qa.require(
        "the second ledger exists and holds something the first one does not",
        started.ok and lone.ok,
        actual=started.stderr[-1000:] + lone.stderr[-1000:],
        covers=["okf:docs/features/tally/tally.md#file:contract"],
    )

    neighbour = run(qa, there, "report", "--json")
    qa.check(
        "a report names the ledger it totals and exits 0",
        neighbour.exit_code == 0,
        actual=neighbour.exit_code,
        expected=0,
        covers=["okf:docs/features/tally/tally.md#file:contract"],
    )
    qa.check(
        "and it gets that ledger's numbers, not the other one's in the same directory",
        qa.field(json.loads(neighbour.stdout), "total_cents") == 300,
        actual=json.loads(neighbour.stdout),
        expected="the 300 the second ledger holds, not the 7450 the first does",
        covers=["okf:docs/features/tally/tally.md#file:semantics:1"],
    )

    # A read cannot violate the separation; only a write can. Put one against the named
    # ledger, with the neighbour's digest either side of it.
    untouched = read(qa, there)
    landed = run(qa, here, "add", "dee", "tram", "180", "2026-03-04")
    qa.require(
        "the named ledger took an expense",
        landed.ok,
        actual=landed.stderr[-2000:],
        covers=["okf:docs/features/tally/tally.md#file:contract"],
    )
    stood = read(qa, there)
    qa.verify(
        "unchanged",
        ({"other.json": qa.field(untouched, "sha256")}, {"other.json": qa.field(stood, "sha256")}),
        subject="the ledger --file did not name",
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

    misplaced = qa.tool("python3").run("-m", "tally", "report", "--file", str(there), timeout=60.0)
    qa.check(
        "`--file` after the subcommand is refused, so one invocation cannot name two ledgers",
        misplaced.exit_code != 0,
        actual=misplaced.exit_code,
        expected="a non-zero exit",
        covers=["okf:docs/features/tally/tally.md#file:semantics:2"],
    )


@scenario(
    target=tally,
    mechanism="live",
    timeout=600.0,
    covers=[
        "okf:docs/features/tally/tally.md#import:contract",
        "okf:docs/features/tally/tally.md#import:does:1",
        "okf:docs/features/tally/tally.md#dry-run:contract",
        "okf:docs/features/tally/tally.md#dry-run:default:1",
        "okf:docs/features/tally/tally.md#dry-run:required:1",
        "okf:docs/features/tally/tally.md#dry-run:semantics:1",
        "okf:docs/features/tally/tally.md#dry-run:semantics:2",
        "okf:docs/features/tally/tally.md#dry-run:semantics:3",
    ],
    preconditions=[
        "a ledger built the way the journey builds one, with `init` and then `add`",
        "one more expense sits in a CSV file this scenario owns, not yet in the ledger",
    ],
    checkpoints=[
        "`import --dry-run` exits 0, reports what it would do, and writes nothing anywhere",
        "the same import without the flag does write, so the flag's absence is the default",
        "the report this story reads counts an expense `import` put there, not only ones `add` did",
    ],
    forbid=[
        "reading the dry run's own report as evidence that it did not write",
        "trusting the ledger digest alone — a dry run that wrote somewhere else in the directory would pass that check",
    ],
)
def a_report_totals_what_import_puts_in_the_ledger_and_a_dry_run_leaves_alone(qa: Qa) -> None:
    """`#import`, `#dry-run`: the two claims `report` and `export` both depend on the ledger holding correctly, over the file `--dry-run` and `import` share with every other command."""
    ledger = qa.artifact("import-and-dry-run/tally.json", kind="json")
    rows = qa.artifact("import-and-dry-run/extra.csv", kind="log")

    trip(qa, ledger)
    write(qa, rows, ONE_ROW)

    before = census(qa, ledger)
    previewed = run(qa, ledger, "import", str(rows), "--dry-run")
    after = census(qa, ledger)

    qa.verify(
        "exit_status",
        previewed,
        code=0,
        label="`import --dry-run` exits 0",
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
    qa.verify(
        "unchanged",
        (before.get("tally.json"), after.get("tally.json")),
        subject="tally.json",
        covers=["okf:docs/features/tally/tally.md#dry-run:semantics:1"],
    )
    qa.verify(
        "unchanged",
        (before, after),
        subject="the working directory",
        covers=["okf:docs/features/tally/tally.md#dry-run:semantics:2"],
    )

    before_entries = entries(qa, ledger)
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
            "okf:docs/features/tally/tally.md#import:contract",
        ],
    )

    after_entries = entries(qa, ledger)
    qa.verify(
        "created",
        (before_entries, after_entries),
        subject="the rows the ledger did not already hold",
        covers=["okf:docs/features/tally/tally.md#import:does:1"],
    )

    totalled = run(qa, ledger, "report")
    qa.check(
        "the report totals the imported expense together with what `add` put there",
        totalled.exit_code == 0 and "4 entries" in totalled.stdout,
        actual=totalled.stdout[-2000:],
        expected="a report naming 4 entries",
        covers=["okf:docs/features/tally/tally.md#import:does:1"],
    )

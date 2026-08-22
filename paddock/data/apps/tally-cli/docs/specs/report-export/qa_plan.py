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
READ = """
import hashlib, json, pathlib, sys
p = pathlib.Path(sys.argv[1])
if p.is_file():
    raw = p.read_bytes()
    json.dump({"exists": True, "sha256": hashlib.sha256(raw).hexdigest(), "text": raw.decode("utf-8")}, sys.stdout)
else:
    json.dump({"exists": False, "sha256": None, "text": None}, sys.stdout)
"""


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
        covers=["okf:docs/features/tally/tally.md#export:contract"],
    )
    return json.loads(got.stdout)


def lines(record):
    """The lines of a file read by `read`, or nothing at all when it is not there."""
    if not record["exists"]:
        return []
    return [line for line in record["text"].splitlines() if line != ""]


def trip(qa: Qa, ledger):
    """A ledger in EUR holding three expenses across two people."""
    started = run(qa, ledger, "init", "--currency", "EUR")
    spent = [
        run(qa, ledger, "add", "ana", "taxi", "1250", "2026-03-01"),
        run(qa, ledger, "add", "bo", "dinner", "4400", "2026-03-01"),
        run(qa, ledger, "add", "ana", "museum", "1800", "2026-03-02"),
    ]
    qa.require(
        "the scenario could build the ledger it reports on",
        started.ok and all(one.ok for one in spent),
        actual=started.stderr[-1000:] + "".join(one.stderr[-500:] for one in spent),
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
    qa.check(
        "the totals are the ledger's, and the overall is the sum of the per-person ones",
        qa.field(decoded, "entries") == 3 and qa.field(decoded, "total_cents") == 7450 and (sum(qa.field(decoded, "per_person").values()) == qa.field(decoded, "total_cents")),
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
        (lines(before), lines(after)),
        subject="the exported CSV file",
        covers=[
            "okf:docs/features/tally/tally.md#export-to-csv:consistency:1",
            "okf:docs/features/tally/tally.md#export-to-csv:contract",
            "okf:docs/features/tally/tally.md#export-to-csv:does:1",
        ],
    )

    written = lines(after)
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
        lines(read(qa, empty_csv)) == ["who,what,amount_cents,spent_on"],
        actual=lines(read(qa, empty_csv)),
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

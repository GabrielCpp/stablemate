"""The frozen QA plan for `ledger-init-add`.

The product is a command, and it is reached as one: every invocation below goes through
`qa.tool("python3")` as `python3 -m tally`, over a process boundary, and the observable is an
exit code, two streams, and the files the command left behind. Nothing here imports `tally` —
`ostler.qa.lint` is an AST allowlist and reserves the process for ostler's approved tools — so
the app being written in the harness's own language changes nothing about how it is reached.
There is no port and no service to start.

The target's `driver` is `python`, which names the *harness* a scenario body runs in, not the
transport to the product: `ostler_qa.DRIVERS` is `("python", "playwright", "maestro")` and
there is no separate driver for "a command". A plan that reaches its product over a process
boundary and one that reaches it over HTTP are both `python` here; what differs is the body.

`qa.tool` runs at the repo root and cannot be handed a working directory, which is why every
invocation here names its ledger with `--file`: each scenario owns a directory under the
evidence dir, and no two of them race for one `tally.json`.

Reading a file is the same process boundary. There is no `open()` in a plan and nothing here
leans on `pathlib` to touch the disk; a snippet handed to `python3` reads the bytes and prints
a digest, which is also what makes "byte-for-byte unchanged" an assertion rather than a
paraphrase of it.
"""

import json

from _fixtures.disk import census_dir, read_file, run
from ostler_qa import Qa, plan, scenario, target


plan(run_id="qa-ledger-init-add", story="ledger-init-add")

tally = target("tally", driver="python")

# Obligation ids are written out in full at every assertion, never factored into a constant:
# `ostler qa validate` reads a `covers=` list statically off the AST, so a computed id claims
# nothing.


def read(qa: Qa, path):
    """What is on disk at `path`, read by a separate process after the command exited."""
    return read_file(qa, path, ["okf:docs/features/tally/concepts/ledger-file.md:contract"])


def census(qa: Qa, directory):
    """Every file in `directory`, by digest — the witness for "no write at all"."""
    return census_dir(qa, directory, ["okf:docs/features/tally/concepts/ledger-file.md:contract"])


@scenario(
    target=tally,
    mechanism="live",
    timeout=600.0,
    covers=[
        "ac:1",
        "ac:2",
        "okf:docs/features/tally/concepts/ledger-file.md:consistency:1",
        "okf:docs/features/tally/concepts/ledger-file.md:contract",
        "okf:docs/features/tally/concepts/ledger-file.md:persistence:1",
        "okf:docs/features/tally/flows/track-a-trip.md:end-state",
        "okf:docs/features/tally/flows/track-a-trip.md:end:1",
        "okf:docs/features/tally/flows/track-a-trip.md:start:1",
        "okf:docs/features/tally/tally.md:contract",
        "okf:docs/features/tally/tally.md#init:contract",
        "okf:docs/features/tally/tally.md#init:does:1",
        "okf:docs/features/tally/tally.md#init-a-ledger:contract",
        "okf:docs/features/tally/tally.md#init-a-ledger:does:1",
        "okf:docs/features/tally/tally.md#init-a-ledger:does:2",
        "okf:docs/features/tally/tally.md#init-a-ledger:status:1",
        "okf:docs/features/tally/tally.md#init-a-ledger:status:2",
        "okf:docs/features/tally/tally.md#init-a-ledger:when:1",
    ],
    preconditions=[
        "the scenario owns an empty directory under the evidence dir, so `init` runs against both states the book names",
        "the ledger is named with `--file`; nothing here depends on the process's working directory",
    ],
    checkpoints=[
        "`init` in an empty directory creates the ledger and exits 0",
        "the file it wrote is one JSON object with a currency and an entries array, complete before the process exited",
        "`init` where a ledger already holds an entry exits 1",
        "and leaves that file byte-for-byte as it was",
    ],
    forbid=[
        "asserting the refusal by its exit code alone — the destructive form of this defect truncates the ledger and still says the right thing",
        "comparing the parsed ledger instead of its bytes",
    ],
)
def init_creates_the_ledger_and_refuses_to_overwrite_one(qa: Qa) -> None:
    """Both halves of `#init-a-ledger`, and the one that is only visible in the bytes."""
    ledger = qa.artifact("init/tally.json", kind="json")

    before = read(qa, ledger)
    qa.require(
        "the scenario starts with no ledger",
        qa.field(before, "exists") is False,
        actual=qa.field(before, "exists"),
        expected=False,
        covers=["okf:docs/features/tally/tally.md#init-a-ledger:when:1"],
    )

    created = run(qa, ledger, "init", "--currency", "EUR")
    qa.check(
        "`tally init` in a directory with no ledger exits 0",
        created.exit_code == 0,
        actual=created.exit_code,
        expected=0,
        covers=[
            "ac:1",
            "okf:docs/features/tally/tally.md:contract",
            "okf:docs/features/tally/tally.md#init:contract",
            "okf:docs/features/tally/tally.md#init:does:1",
            "okf:docs/features/tally/tally.md#init-a-ledger:status:1",
        ],
    )

    after = read(qa, ledger)
    qa.verify(
        "created",
        (before["text"], after["text"]),
        subject="tally.json",
        covers=[
            "ac:1",
            "okf:docs/features/tally/flows/track-a-trip.md:end-state",
            "okf:docs/features/tally/flows/track-a-trip.md:end:1",
            "okf:docs/features/tally/flows/track-a-trip.md:start:1",
            "okf:docs/features/tally/tally.md#init-a-ledger:contract",
            "okf:docs/features/tally/tally.md#init-a-ledger:does:1",
            "okf:docs/features/tally/tally.md#init-a-ledger:does:2",
            "okf:docs/features/tally/tally.md#init-a-ledger:status:1",
            "okf:docs/features/tally/tally.md#init-a-ledger:status:2",
            "okf:docs/features/tally/tally.md#init-a-ledger:when:1",
        ],
    )

    # Read back by a process that started after `init` exited: whatever it can parse is what
    # the previous process had finished writing.
    document = json.loads(after["text"])
    qa.check(
        "the ledger is one JSON object with a currency string and an entries array",
        isinstance(document.get("currency"), str) and isinstance(document.get("entries"), list),
        actual=sorted(document),
        expected=["currency", "entries"],
        covers=[
            "okf:docs/features/tally/concepts/ledger-file.md:consistency:1",
            "okf:docs/features/tally/concepts/ledger-file.md:contract",
            "okf:docs/features/tally/concepts/ledger-file.md:persistence:1",
            "okf:docs/features/tally/tally.md#init:does:1",
        ],
    )
    qa.check(
        "the ledger it created holds no entries",
        len(qa.field(document, "entries")) == 0,
        actual=qa.field(document, "entries"),
        expected=[],
        covers=["ac:1", "okf:docs/features/tally/tally.md#init-a-ledger:does:1"],
    )

    # A ledger with something in it, so a truncating `init` has something to destroy. An empty
    # ledger is the one state where the destructive defect and the refusal look identical.
    recorded = run(qa, ledger, "add", "ana", "taxi", "1250", "2026-03-01")
    qa.require(
        "the scenario could put an entry in the ledger to be protected",
        recorded.ok,
        actual=recorded.stderr[-2000:],
        covers=["okf:docs/features/tally/tally.md#init-a-ledger:does:2"],
    )
    held = read(qa, ledger)

    refused = run(qa, ledger, "init", "--currency", "USD")
    qa.check(
        "`tally init` where a ledger is already there exits 1",
        refused.exit_code == 1,
        actual=refused.exit_code,
        expected=1,
        covers=[
            "ac:2",
            "okf:docs/features/tally/tally.md:contract",
            "okf:docs/features/tally/tally.md#init-a-ledger:status:2",
        ],
    )

    # The bytes, not the parse. A truncation to an empty ledger in the same currency differs
    # from what was there only in the entries array, and a re-init that rewrote identical
    # content is still a write the book forbids.
    stood = read(qa, ledger)
    qa.verify(
        "unchanged",
        ({"tally.json": held["sha256"]}, {"tally.json": stood["sha256"]}),
        subject="tally.json",
        covers=[
            "ac:2",
            "okf:docs/features/tally/tally.md#init-a-ledger:contract",
            "okf:docs/features/tally/tally.md#init-a-ledger:does:1",
            "okf:docs/features/tally/tally.md#init-a-ledger:does:2",
            "okf:docs/features/tally/tally.md#init-a-ledger:status:1",
            "okf:docs/features/tally/tally.md#init-a-ledger:status:2",
            "okf:docs/features/tally/tally.md#init-a-ledger:when:1",
        ],
    )
    qa.check(
        "the entry the refused `init` was standing on is still in the ledger",
        len(qa.field(json.loads(qa.field(stood, "text")), "entries")) == 1,
        actual=qa.field(json.loads(qa.field(stood, "text")), "entries"),
        expected=1,
        covers=[
            "ac:2",
            "okf:docs/features/tally/tally.md#init-a-ledger:does:2",
            "okf:docs/features/tally/concepts/ledger-file.md:persistence:1",
        ],
    )


@scenario(
    target=tally,
    mechanism="live",
    timeout=600.0,
    covers=[
        "ac:1",
        "okf:docs/features/tally/tally.md#currency:contract",
        "okf:docs/features/tally/tally.md#currency:default:1",
        "okf:docs/features/tally/tally.md#currency:required:1",
        "okf:docs/features/tally/tally.md#currency:semantics:1",
    ],
    preconditions=[
        "two ledgers, each named with `--file`: one initialised with `--currency` and one without it",
    ],
    checkpoints=[
        "`init` without `--currency` records EUR",
        "`init --currency USD` records USD",
        "a later `add` does not change the code the report states",
    ],
    forbid=[
        "asserting the default off `--help` — the claim is what `init` *recorded*, not what it advertises",
        "waiting for `report` to state it: this story has no `report`, and the ledger is where the code lives",
    ],
)
def the_currency_is_recorded_once_at_init_and_never_moves(qa: Qa) -> None:
    """`--currency` is optional, defaults to EUR, and is written once."""
    default = qa.artifact("currency/default.json", kind="json")
    named = qa.artifact("currency/named.json", kind="json")

    fell_back = run(qa, default, "init")
    qa.check(
        "`init` runs with no `--currency` at all",
        fell_back.exit_code == 0,
        actual=fell_back.stderr[-2000:],
        expected=0,
        covers=["okf:docs/features/tally/tally.md#currency:required:1"],
    )
    # The ledger itself is what the product wrote, and in this story it is the only place the
    # code exists: `report` is a later story, so there is nothing yet that states it back.
    told = read(qa, default)
    qa.verify(
        "json_path",
        json.loads(told["text"]),
        path="$.currency",
        equals="EUR",
        covers=[
            "ac:1",
            "okf:docs/features/tally/tally.md#currency:contract",
            "okf:docs/features/tally/tally.md#currency:default:1",
        ],
    )

    chosen = run(qa, named, "init", "--currency", "USD")
    qa.require(
        "`init --currency USD` succeeds",
        chosen.ok,
        actual=chosen.stderr[-2000:],
        covers=["okf:docs/features/tally/tally.md#currency:contract"],
    )
    spent = run(qa, named, "add", "bo", "coffee", "350", "2026-03-02")
    qa.require(
        "an expense lands in the ledger that named its currency",
        spent.ok,
        actual=spent.stderr[-2000:],
        covers=["okf:docs/features/tally/tally.md#currency:semantics:1"],
    )
    still = json.loads(read(qa, named)["text"])
    qa.check(
        "the code the ledger was created with is still the code it holds after an expense",
        qa.field(still, "currency") == "USD",
        actual=qa.field(still, "currency"),
        expected="USD",
        covers=[
            "ac:1",
            "okf:docs/features/tally/tally.md#currency:semantics:1",
            "okf:docs/features/tally/tally.md#currency:contract",
        ],
    )
    qa.check(
        "the two ledgers did not converge on one currency",
        qa.field(json.loads(qa.field(told, "text")), "currency") != qa.field(still, "currency"),
        actual=[qa.field(json.loads(qa.field(told, "text")), "currency"), qa.field(still, "currency")],
        expected=["EUR", "USD"],
        covers=["okf:docs/features/tally/tally.md#currency:default:1"],
    )


@scenario(
    target=tally,
    mechanism="live",
    timeout=600.0,
    covers=[
        "ac:3",
        "ac:4",
        "ac:6",
        "okf:docs/features/tally/concepts/ledger-file.md:consistency:2",
        "okf:docs/features/tally/concepts/ledger-file.md:persistence:1",
        "okf:docs/features/tally/tally.md:contract",
        "okf:docs/features/tally/tally.md#add:contract",
        "okf:docs/features/tally/tally.md#add:does:1",
        "okf:docs/features/tally/tally.md#add-an-expense:contract",
        "okf:docs/features/tally/tally.md#add-an-expense:does:1",
        "okf:docs/features/tally/tally.md#add-an-expense:errors:1",
        "okf:docs/features/tally/tally.md#add-an-expense:status:1",
        "okf:docs/features/tally/tally.md#add-an-expense:status:2",
    ],
    preconditions=[
        "a ledger this scenario created, holding nothing, so the count after one `add` is the count of that `add`",
    ],
    checkpoints=[
        "one `add` leaves exactly one entry, on disk, and exits 0",
        "an amount that is not a positive whole number of cents exits 2",
        "and the ledger is byte-for-byte what it was before that attempt",
        "no temporary file is left beside the ledger by either invocation",
    ],
    forbid=[
        "provoking the refusal with a value argparse rejects — the rule under test belongs to the ledger, not to the parser",
        "asserting the refusal by its message and not by the ledger",
    ],
)
def add_records_one_expense_and_refuses_an_amount_that_is_not_money(qa: Qa) -> None:
    """The success path, the refusal, and the file that must not have moved under it."""
    ledger = qa.artifact("add/tally.json", kind="json")
    directory = ledger.parent

    started = run(qa, ledger, "init")
    qa.require(
        "the scenario has a ledger to add to",
        started.ok,
        actual=started.stderr[-2000:],
        covers=["okf:docs/features/tally/tally.md#add:contract"],
    )

    recorded = run(qa, ledger, "add", "ana", "dinner", "4200", "2026-03-03")
    qa.check(
        "`tally add` exits 0 when the expense was recorded",
        recorded.exit_code == 0,
        actual=recorded.exit_code,
        expected=0,
        covers=[
            "ac:3",
            "okf:docs/features/tally/tally.md:contract",
            "okf:docs/features/tally/tally.md#add:does:1",
            "okf:docs/features/tally/tally.md#add-an-expense:status:1",
        ],
    )

    held = read(qa, ledger)
    qa.verify(
        "count",
        json.loads(held["text"])["entries"],
        subject="entries in the ledger",
        equals=1,
        covers=[
            "ac:3",
            "okf:docs/features/tally/tally.md#add-an-expense:contract",
            "okf:docs/features/tally/tally.md#add-an-expense:does:1",
            "okf:docs/features/tally/tally.md#add-an-expense:errors:1",
            "okf:docs/features/tally/tally.md#add-an-expense:status:1",
            "okf:docs/features/tally/tally.md#add-an-expense:status:2",
        ],
    )
    qa.check(
        "the expense was on disk before the process exited",
        qa.field(json.loads(qa.field(held, "text")), "entries.0.who") == "ana",
        actual=qa.field(json.loads(qa.field(held, "text")), "entries.0"),
        expected="ana",
        covers=[
            "ac:3",
            "okf:docs/features/tally/concepts/ledger-file.md:persistence:1",
            "okf:docs/features/tally/tally.md#add:does:1",
        ],
    )

    # `-1200` is not a positive whole number of cents, and reaches the ledger's rule rather
    # than the parser's: `AMOUNT_CENTS` is a positional string, so argparse hands it over.
    refused = run(qa, ledger, "add", "bo", "refund", "-1200", "2026-03-04")
    qa.check(
        "an amount that is not money exits 2",
        refused.exit_code == 2,
        actual=refused.exit_code,
        expected=2,
        covers=[
            "ac:4",
            "okf:docs/features/tally/tally.md:contract",
            "okf:docs/features/tally/tally.md#add-an-expense:status:2",
            "okf:docs/features/tally/tally.md#add-an-expense:errors:1",
        ],
    )
    qa.check(
        "the refusal says so on stderr and puts nothing on stdout",
        len(refused.stderr.strip()) > 0 and refused.stdout == "",
        actual=[refused.stdout, refused.stderr[-500:]],
        expected="a diagnostic on stderr and an empty stdout",
        covers=["ac:6", "okf:docs/features/tally/tally.md#add-an-expense:errors:1"],
    )

    stood = read(qa, ledger)
    qa.verify(
        "unchanged",
        ({"tally.json": held["sha256"]}, {"tally.json": stood["sha256"]}),
        subject="tally.json",
        covers=[
            "ac:4",
            "okf:docs/features/tally/tally.md#add-an-expense:contract",
            "okf:docs/features/tally/tally.md#add-an-expense:does:1",
            "okf:docs/features/tally/tally.md#add-an-expense:errors:1",
            "okf:docs/features/tally/tally.md#add-an-expense:status:1",
            "okf:docs/features/tally/tally.md#add-an-expense:status:2",
        ],
    )

    # The rename is not observable from outside as an instant, but its residue is: a write
    # that did not complete the rename leaves the temporary path sitting beside the ledger.
    left = census(qa, directory)
    qa.check(
        "no half-written ledger is left beside the file",
        sorted(left) == ["tally.json"],
        actual=sorted(left),
        expected=["tally.json"],
        covers=["okf:docs/features/tally/concepts/ledger-file.md:consistency:2"],
    )


@scenario(
    target=tally,
    mechanism="live",
    timeout=600.0,
    covers=[
        "ac:5",
        "ac:6",
        "okf:docs/features/tally/tally.md#dry-run:contract",
        "okf:docs/features/tally/tally.md#dry-run:default:1",
        "okf:docs/features/tally/tally.md#dry-run:required:1",
        "okf:docs/features/tally/tally.md#dry-run:semantics:1",
        "okf:docs/features/tally/tally.md#dry-run:semantics:2",
        "okf:docs/features/tally/tally.md#dry-run:semantics:3",
    ],
    preconditions=[
        "a ledger holding one entry, so a dry run has both something to leave alone and something it could plausibly rewrite",
    ],
    checkpoints=[
        "`add --dry-run` exits 0 and says on stderr what it would have done",
        "the ledger's bytes are what they were",
        "no other file in the directory changed and no new one appeared",
        "the same command without the flag does write, which is what makes the default false",
    ],
    forbid=[
        "checking only the ledger — a dry run that wrote somewhere else instead is invisible to that",
        "reading the flag's default out of `--help` when the command can be run both ways",
    ],
)
def a_dry_run_reports_what_it_would_do_and_writes_nothing_anywhere(qa: Qa) -> None:
    """`--dry-run` is optional, off by default, and makes no write at all."""
    ledger = qa.artifact("dry-run/tally.json", kind="json")
    directory = ledger.parent

    started = run(qa, ledger, "init")
    qa.require(
        "the scenario has a ledger",
        started.ok,
        actual=started.stderr[-2000:],
        covers=["okf:docs/features/tally/tally.md#dry-run:contract"],
    )
    seeded = run(qa, ledger, "add", "ana", "hotel", "9000", "2026-03-05")
    qa.require(
        "the ledger holds something a dry run could damage",
        seeded.ok,
        actual=seeded.stderr[-2000:],
        covers=["okf:docs/features/tally/tally.md#dry-run:semantics:1"],
    )

    before = census(qa, directory)
    previewed = run(qa, ledger, "add", "bo", "train", "3300", "2026-03-06", "--dry-run")
    after = census(qa, directory)

    qa.check(
        "a dry run still exits 0",
        previewed.exit_code == 0,
        actual=previewed.exit_code,
        expected=0,
        covers=[
            "ac:5",
            "okf:docs/features/tally/tally.md#dry-run:contract",
            "okf:docs/features/tally/tally.md#dry-run:semantics:3",
        ],
    )
    qa.check(
        "a dry run still reports what it would have done, on stderr",
        "dry-run" in previewed.stderr and previewed.stdout == "",
        actual=[previewed.stdout, previewed.stderr[-500:]],
        expected="a preview line on stderr and an empty stdout",
        covers=["ac:5", "ac:6", "okf:docs/features/tally/tally.md#dry-run:semantics:3"],
    )
    qa.check(
        "the ledger's bytes are what they were",
        before.get("tally.json") == after.get("tally.json"),
        actual=[before.get("tally.json"), after.get("tally.json")],
        expected="one digest, twice",
        covers=["ac:5", "okf:docs/features/tally/tally.md#dry-run:semantics:1"],
    )
    qa.check(
        "and nothing else in the directory was written either — no new file, no changed one",
        before == after,
        actual=after,
        expected=before,
        covers=[
            "ac:5",
            "okf:docs/features/tally/tally.md#dry-run:semantics:2",
            "okf:docs/features/tally/tally.md#dry-run:contract",
        ],
    )

    # The default is false, proven by running the same command without the flag rather than by
    # reading a help string: what `default:` means here is what the command does.
    committed = run(qa, ledger, "add", "bo", "train", "3300", "2026-03-06")
    settled = census(qa, directory)
    qa.check(
        "the same `add` without `--dry-run` does write, so off is the default",
        committed.ok and settled.get("tally.json") != after.get("tally.json"),
        actual=[committed.exit_code, settled.get("tally.json"), after.get("tally.json")],
        expected="a different digest, from an invocation that differs only by the flag",
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
        "okf:docs/features/tally/tally.md:contract",
        "okf:docs/features/tally/tally.md#file:contract",
        "okf:docs/features/tally/tally.md#file:default:1",
        "okf:docs/features/tally/tally.md#file:required:1",
        "okf:docs/features/tally/tally.md#file:semantics:1",
        "okf:docs/features/tally/tally.md#file:semantics:2",
    ],
    preconditions=[
        "two ledgers in one directory, so `--file` is the only thing separating them",
    ],
    checkpoints=[
        "an `add` against one ledger leaves the other holding nothing",
        "`--file` is optional and defaults to `tally.json`",
        "`--file` is global: given after the command name it is not accepted",
    ],
    forbid=[
        "running without `--file` to prove the default — that writes into whatever directory the harness happens to be in",
    ],
)
def two_ledgers_in_one_directory_never_see_each_other(qa: Qa) -> None:
    """`--file` names the ledger, once per invocation, before the command."""
    here = qa.artifact("file/trip.json", kind="json")
    there = qa.artifact("file/rent.json", kind="json")

    for ledger in (here, there):
        started = run(qa, ledger, "init")
        qa.require(
            f"the scenario could create {ledger.name}",
            started.ok,
            actual=started.stderr[-2000:],
            covers=["okf:docs/features/tally/tally.md#file:contract"],
        )

    recorded = run(qa, here, "add", "ana", "ferry", "2600", "2026-03-07")
    qa.require(
        "one of the two ledgers took an expense",
        recorded.ok,
        actual=recorded.stderr[-2000:],
        covers=["okf:docs/features/tally/tally.md#file:semantics:1"],
    )

    trip = json.loads(read(qa, here)["text"])
    rent = json.loads(read(qa, there)["text"])
    qa.check(
        "the ledger that was written holds the expense",
        len(qa.field(trip, "entries")) == 1,
        actual=qa.field(trip, "entries"),
        expected=1,
        covers=["okf:docs/features/tally/tally.md#file:semantics:1"],
    )
    qa.check(
        "the other ledger in the same directory never saw it",
        len(qa.field(rent, "entries")) == 0,
        actual=qa.field(rent, "entries"),
        expected=0,
        covers=[
            "okf:docs/features/tally/tally.md#file:semantics:1",
            "okf:docs/features/tally/tally.md#file:contract",
        ],
    )

    # The default and the optionality are read off the product's own usage rather than
    # exercised: running without `--file` would write into the harness's working directory,
    # which is the repo, and a check that damages the tree it is measuring is not a check.
    described = qa.tool("python3").run("-m", "tally", "--help", timeout=60.0)
    qa.check(
        "`--file` is optional and the product states its default",
        "default: tally.json" in described.stdout and "[--file FILE]" in described.stdout,
        actual=described.stdout[:600],
        expected="an optional `--file` documented as defaulting to tally.json",
        covers=[
            "okf:docs/features/tally/tally.md#file:default:1",
            "okf:docs/features/tally/tally.md#file:required:1",
        ],
    )

    # Global means before the command, and one invocation names one ledger. Given after the
    # command name it is not a second ledger — it is not accepted at all.
    misplaced = qa.tool("python3").run(
        "-m", "tally", "add", "ana", "ferry", "2600", "2026-03-07", "--file", str(here), timeout=60.0
    )
    qa.check(
        "`--file` after the command name is refused rather than quietly meaning something else",
        misplaced.exit_code != 0,
        actual=[misplaced.exit_code, misplaced.stderr[-500:]],
        expected="a non-zero exit",
        covers=[
            "okf:docs/features/tally/tally.md:contract",
            "okf:docs/features/tally/tally.md#file:semantics:2",
        ],
    )

# The check vocabulary

The fourteen named checks a `verify:` bullet may call, their signatures, and — the part that
matters when judging whether a check earns its bullet — **the defect each one excludes**. A check
that excludes no plausible defect is a rubber stamp, and `doctor` refuses it as `weak-check`.
Companion to [`../SKILL.md`](../SKILL.md) and to [bullet-grammar.md](bullet-grammar.md), which
says where the bullet goes and what it binds to.

`ostler checks` and `ostler checks <name> --json` print this **live** from
`ostler/ostler/checks.py`. The tool is the authority; run it before writing a call you have not
written before, not after `doctor` refuses one.

## How to read a signature

- `name*` — required argument.
- `one of …` — at least one of the listed arguments must be present. `required` cannot express
  this: each is optional alone, and it is the *choice* that is mandatory. Without it, a check can
  be spelled so nothing it observes can come out false.
- Types are `str`, `int`, `bool`, `scalar`, `str[]`.
- Arguments marked *(path)* are paths into the observed document, not free prose. Both resolvers
  strip a leading `$` root token, so `$.policy.id` and `policy.id` name the same field.

Arguments are parsed as **literals only**, via `ast` (`checks.py:265-310`) — no expressions, no
names, no interpolation. A `verify:` whose value is a test path is not a parse failure to fix in
place: it is a category error, and `parse_check` redirects it to `tests:`.

## The vocabulary

### `http_status(code: int*, title: str, path: str)`
Excludes a branch that returns the right shape under the wrong status, and an error response
distinguished from its siblings only by a body nobody read.

### `json_path(path: str* (path), equals: scalar, matches: str, absent: bool)` — one of `equals`, `matches`, `absent`
Excludes a field asserted by presence rather than value, which passes on the default the defect
also produces.

### `unchanged(subject: str*, except_fields: str[])`
Excludes collateral damage outside the field under test — the defect a diff that masks the whole
object before comparing cannot see.

### `keys_unchanged(subject: str*)`
Excludes a move implemented as a copy: every object compared individually matches, and only the
key inventory shows the old one is still there.

### `count(subject: str*, equals: int*)`
Excludes an operation that produced the expected item *and* extras nobody counted.

### `absent(subject: str*)`
Excludes a delete that hid the thing from one surface and left it readable on another.

### `created(subject: str*)`
Excludes a thing that was already there reported as created. A presence check run only afterwards
passes identically on a no-op, so the absence *before* the action is part of the observation
rather than an assumption about it.

### `removed(subject: str*)`
Excludes a delete asserted only by absence afterwards, which passes identically when the subject
was never there — the presence before the action is what makes the disappearance attributable to
it.

### `visible(locator: str*, text: str)`
Excludes an element present in the tree but not on the screen, and the right widget showing the
wrong content.

### `persists(subject: str*)`
Excludes a write observed only through the same session that made it, which cannot tell a commit
from a cache.

### `emitted(event: str*, count: int)`
Excludes an effect asserted at its source instead of at its subscriber, and an at-most-once
effect fired twice.

### `omits(subject: str* (path), text: str, matches: str)` — one of `text`, `matches`
Excludes a value the response was never supposed to carry — a refusal quoting the credential it
rejected, an error echoing an internal path. Every other check in this vocabulary passes over
this, because they all assert what the subject *does* hold and a clause about what it may **not**
hold has no positive form.

### `exit_status(code: int*)`
Excludes a command that failed, or succeeded for the wrong reason, where the plan only read its
output — a tool result asserted by what it printed passes identically when the process printed it
on the way to a non-zero exit.

### `conflict_on_stale(subject: str*, token: str)`
Excludes an unconditional overwrite standing in for compare-and-swap — a write followed by a read
cannot tell them apart, only a stale write refused can.

## Why the vocabulary is small

Every entry has to name a defect class that a plausible *weaker* assertion lets through, and
every entry costs a harness callable that has to behave identically under every driver. Growing
it is a deliberate act, not a convenience. If no check fits, the claim is usually the thing that
needs splitting — see [bullet-grammar.md](bullet-grammar.md).

## The lifecycle pair

`created` and `removed` are the two checks `doctor` reaches for by name
(`LIFECYCLE_CHECKS`, `doctor.py:856`). When a normative bullet states a lifecycle change and the
declared checks read only the state *afterwards*, that is `unstated-precondition` (warn): the
after-state is the same state a no-op leaves when the subject was already there.

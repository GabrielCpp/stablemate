"""Whether a declared check can go red at all — measured, not assumed.

`ostler doctor` refuses the two spellings that are *statically* rubber stamps. That is a
list of known shapes, and the property it stands in for is bigger: an assertion earns a
claim's `covered` only if there is an observation of the product that would have made it
fail. Nothing asked that question of the other ten checks, so a call could be legal,
declared, invoked, green — and incapable of any other verdict.

This asks it by experiment. Every verifier is a pure function of `(observed, args)`
(`harness/ostler_qa.py`), so a witness observation can be synthesized from the declared
call, perturbed, and re-verified in-process: no app, no browser, no run. A call is
**sensitive** when the witness is green and at least one perturbation turns it red, and
**insensitive** when every perturbation leaves it green — the same verdict whatever the
product did, which is what a rubber stamp is.

The perturbations are deliberately the ones a defect produces: the field the claim names
is missing or holds something else, the route that answered was a different one, the
ledger the write was supposed to leave alone moved, the refusal carries the credential.
A mutator family is only worth trusting once the corpus's real catches survive it, which
is why the seeded-defect books are the calibration set rather than a demo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ostler import checks, model, registry
from ostler.model import Graph
from ostler.qa.outcome import QaOutcome
from ostler.qa.harness_host import load_harness_module

_harness = load_harness_module("ostler_qa")
_VERIFIERS = _harness.VERIFIERS

#: A value nothing in a book asks for, used where a mutation needs "something else".
_OTHER = "∅ not what was claimed"


class _Response:
    """The little of a response a verifier reads: a status, a body, the route that answered."""

    def __init__(self, status: int, body: Any, url: str) -> None:
        self.status_code = status
        self.url = url
        self.text = str(body)
        self._body = body

    def json(self) -> Any:
        return self._body


class _Locator:
    """The little of a page element a verifier reads."""

    def __init__(self, *, visible: bool, text: str) -> None:
        self._visible = visible
        self._text = text

    def is_visible(self) -> bool:
        return self._visible

    def inner_text(self) -> str:
        return self._text


@dataclass(frozen=True)
class Trial:
    """One declared call, put to the experiment."""

    call: str
    witnessed: bool
    flipped: tuple[str, ...]
    survived: tuple[str, ...]
    note: str = ""

    @property
    def sensitive(self) -> bool:
        """Green on the witness, and red under *every* mutation the call is meant to catch.

        A survivor is a defect this call admits, so one is enough to disqualify it: an
        `any(flipped)` rule would score `json_path("claim.status", matches=".*")` sensitive
        off the field-absence mutation alone, while the mutation that matters — the field
        holding something else — walks straight past it. `_plan` lists only mutations the
        call is expected to catch, which is what makes "all of them" the honest bar.
        """
        return self.witnessed and bool(self.flipped) and not self.survived


@dataclass(frozen=True)
class ClaimReport:
    """One obligation, and what its checks could be made to say."""

    claim: str
    path: str
    line: int
    trials: tuple[Trial, ...]

    @property
    def status(self) -> str:
        if not self.trials:
            return "undeclared"
        return "sensitive" if any(t.sensitive for t in self.trials) else "insensitive"


# -- witnesses ---------------------------------------------------------------


def _set_path(document: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """A document in which `path` resolves to `value`, built the way `resolve_path` walks.

    A selector step is witnessed by the smallest document that satisfies it: `[*]` by a
    one-element list, `[?(@.key==v)]` by a one-element list whose element carries `key: v`
    beside whatever the rest of the path puts there.
    """
    steps = _steps(path)
    cursor: Any = document
    for step, following in zip(steps, [*steps[1:], None], strict=True):
        nxt: Any = [] if isinstance(following, int | _harness._Wild | _harness.Filter) else {}
        if isinstance(step, _harness._Wild | _harness.Filter):
            # One element is the smallest list a selector is satisfied by; a filter's element
            # carries the key it selects on beside whatever the rest of the path puts there.
            if not cursor:
                cursor.append(None)
            if following is None:
                cursor[0] = value if isinstance(step, _harness._Wild) else (value if isinstance(value, dict) else {})
            elif cursor[0] is None:
                cursor[0] = nxt
            if isinstance(step, _harness.Filter) and isinstance(cursor[0], dict):
                _set_path(cursor[0], step.key, step.value)
            cursor = cursor[0]
            continue
        if isinstance(step, int):
            while len(cursor) <= step:
                cursor.append(None)
            cursor[step] = value if following is None else nxt
            cursor = cursor[step]
        else:
            cursor[step] = value if following is None else cursor.get(step) or nxt
            cursor = cursor[step]
    return document


def _steps(path: str) -> list[Any]:
    return _harness.path_steps(path)


def _collection(subject: str, size: int) -> dict[str, Any]:
    """A document in which `count(subject=)` finds `size` things.

    A subject naming a collection holds a list of that many; a subject ending in a selector
    (`people[*].trips[*]`, `people[?(@.active==true)]`) counts what the selector selects, so
    the list sits where the selector reads it and each element satisfies it.
    """
    items: list[Any] = [{"i": i} for i in range(size)]
    steps = _steps(subject)
    last = steps[-1] if steps else None
    if last is None:
        return _set_path({}, subject, items)
    if isinstance(last, _harness._Wild | _harness.Filter):
        marker = "[*]" if isinstance(last, _harness._Wild) else "[?("
        parent = subject[: subject.rfind(marker)]
        if isinstance(last, _harness.Filter):
            key, value = last.key, last.value
            items = [_set_path(item, key, value) for item in items]
        return _set_path({}, parent, items)
    return _set_path({}, subject, items)


def _drop_path(document: Any, path: str) -> Any:
    """The same document with the leaf `path` names taken out of it."""
    steps = _steps(path)
    cursor = document
    for step in steps[:-1]:
        cursor = cursor[0] if isinstance(step, _harness._Wild | _harness.Filter) else cursor[step]
    last = steps[-1]
    if isinstance(last, _harness._Wild | _harness.Filter):
        cursor.clear()
    elif isinstance(last, int):
        del cursor[last]
    else:
        cursor.pop(last, None)
    return document


def _int(value: Any) -> int:
    """A declared numeric argument as a number, whichever way the book spelled it."""
    return int(str(value))


_PATHLIKE = re.compile(
    r"^\$?\.?[A-Za-z_][\w-]*"
    r"(?:\.[A-Za-z_][\w-]*|\[\d+\]|\[\*\]|\[\?\(@\.[^=\s)]+\s*==\s*[^)]+\)\])*$"
)


def _matching(pattern: str) -> str | None:
    """A string the pattern accepts, or None when this harness cannot invent one.

    A witness has to be a real member of the language, not a plausible one: an invention the
    pattern rejects would report a discriminating check as unwitnessed, and one the pattern
    accepts by accident would credit sensitivity the experiment never showed. So everything
    built here is checked against the pattern itself before it is returned, and a shape the
    builder does not understand returns None rather than a guess.
    """
    for candidate in (pattern, *pattern.split("|")):
        plain = candidate.strip("^$")
        if re.escape(plain) == plain and re.search(pattern, plain):
            return plain
    built = _synthesize(pattern.split("|")[0])
    return built if built is not None and re.search(pattern, built) else None


_CLASS_POOL = "abcdefghijklmnopqrstuvwxyz0123456789_-"
_ESCAPES = {"d": "5", "w": "a", "s": " ", "S": "a", "W": " ", "D": "a"}


def _synthesize(pattern: str) -> str | None:
    """One member of a small regular language: literals, classes, groups, counted repeats.

    Deliberately partial. The patterns a book writes are shapes of a leaked value — a token
    prefix, a digit run, a header — and the general problem is not worth solving to witness
    them. Anything past this vocabulary is the caller's None.
    """
    out: list[str] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char in "^$":
            i += 1
            continue
        if char == "\\" and i + 1 < len(pattern):
            piece, i = _ESCAPES.get(pattern[i + 1], pattern[i + 1]), i + 2
        elif char == "[":
            end = pattern.find("]", i + 1)
            if end < 0:
                return None
            piece, i = _from_class(pattern[i + 1 : end]), end + 1
            if piece is None:
                return None
        elif char == "(":
            end = pattern.find(")", i + 1)
            if end < 0 or "(" in pattern[i + 1 : end]:
                return None
            inner = _synthesize(pattern[i + 1 : end].lstrip("?:").split("|")[0])
            if inner is None:
                return None
            piece, i = inner, end + 1
        elif char in "*+?{})]":
            return None
        else:
            piece, i = char, i + 1
        repeat, i = _repeat(pattern, i)
        out.append(piece * repeat)
    return "".join(out)


def _from_class(body: str) -> str | None:
    """One character the class admits, ranges expanded, negation honoured."""
    negated = body.startswith("^")
    members, chars = set(), body.lstrip("^").replace("\\", "")
    index = 0
    while index < len(chars):
        if index + 2 < len(chars) and chars[index + 1] == "-":
            members |= {chr(c) for c in range(ord(chars[index]), ord(chars[index + 2]) + 1)}
            index += 3
        else:
            members.add(chars[index])
            index += 1
    usable = sorted(set(_CLASS_POOL) - members) if negated else sorted(members)
    return usable[0] if usable else None


def _repeat(pattern: str, i: int) -> tuple[int, int]:
    """How many times the piece just read repeats, and where the pattern continues.

    The lower bound, always: the shortest witness is the one least likely to satisfy some
    *other* clause of the pattern by accident, and a `{6,}` witnessed by six characters is
    as much a member of the language as one witnessed by sixty.
    """
    if i >= len(pattern):
        return 1, i
    if pattern[i] == "+":
        return 1, i + 1
    if pattern[i] in "*?":
        return 0, i + 1
    if pattern[i] == "{":
        end = pattern.find("}", i)
        low = pattern[i + 1 : end].split(",")[0]
        if end > 0 and low.isdigit():
            return int(low), end + 1
    return 1, i


def _plan(call: checks.CheckCall) -> tuple[Any, list[tuple[str, Any]], str]:
    """The witness observation, the mutations to try against it, and why there are none.

    Every mutation listed is one the call is *expected* to catch — a claim's own field gone
    or altered, a different route, a ledger that moved. A mutation the check is allowed to
    stay green under (an `except_fields` entry changing) is not a perturbation of the claim
    and is not listed: the survivors are meant to read as defects.
    """
    args = call.args
    name = call.name
    if name == "http_status":
        code = _int(args["code"])
        route = str(args.get("path", "/witness"))
        body = {"title": args["title"]} if "title" in args else {}
        witness = _Response(code, body, f"http://witness{route}")
        mutations: list[tuple[str, Any]] = [
            ("the route answered a different status", _Response(500 if code != 500 else 400, body, f"http://witness{route}")),
        ]
        if "path" in args:
            mutations.append(("a different request answered", _Response(code, body, "http://witness/elsewhere")))
        if "title" in args:
            mutations.append(("the refusal names something else", _Response(code, {"title": _OTHER}, f"http://witness{route}")))
        return witness, mutations, ""
    if name == "json_path":
        path = str(args["path"])
        if "absent" in args:
            # A presence assertion is only defeated by absence: `absent=false` says the field
            # is there and says nothing about what it holds, so a changed value surviving is
            # the check working, not a rubber stamp.
            if args["absent"]:
                return {}, [("the field the claim forbids is there", _set_path({}, path, "x"))], ""
            return _set_path({}, path, "x"), [("the field the claim requires is missing", {})], ""
        if "equals" in args:
            value: Any = args["equals"]
        elif "matches" in args:
            found = _matching(str(args["matches"]))
            if found is None:
                return None, [], f"no witness value can be invented for /{args['matches']}/"
            value = found
        else:
            value = "x"
        witness = _set_path({}, path, value)
        mutations = [("the field holds something else", _set_path({}, path, _OTHER))]
        if "matches" not in args or _matching(str(args.get("matches", ""))) is not None:
            mutations.append(("the field is not there at all", _drop_path(_set_path({}, path, value), path)))
        return witness, mutations, ""
    if name == "unchanged":
        declared = args.get("except_fields", [])
        allowed = [str(field) for field in declared] if isinstance(declared, list) else []
        before = {"claimed": 1, "also_claimed": 2, **{field: 1 for field in allowed}}
        return (
            (before, dict(before)),
            [("a field the claim protects changed", (before, {**before, "claimed": 9}))],
            "",
        )
    if name == "keys_unchanged":
        before = {"a": 1, "b": 2}
        return (
            (before, dict(before)),
            [
                ("an entry left the ledger", (before, {"a": 1})),
                ("an entry appeared in the ledger", (before, {**before, "c": 3})),
            ],
            "",
        )
    if name == "count":
        want = _int(args["equals"])
        subject = str(args["subject"])
        if _PATHLIKE.match(subject):
            return (
                _collection(subject, want),
                [
                    ("the collection holds one more", _collection(subject, want + 1)),
                    ("the collection is not in the answer", {}),
                ],
                "",
            )
        return [{"i": i} for i in range(want)], [("the collection holds one more", [{"i": i} for i in range(want + 1)])], ""
    if name == "absent":
        return None, [("the subject is there after all", ["something"])], ""
    if name == "created":
        return (None, {"id": "x"}), [
            ("it was already there before the action", ({"id": "x"}, {"id": "x"})),
            ("nothing was created", (None, None)),
        ], ""
    if name == "removed":
        return ({"id": "x"}, None), [
            ("it was never there to remove", (None, None)),
            ("it is still there afterwards", ({"id": "x"}, {"id": "x"})),
        ], ""
    if name == "visible":
        text = str(args.get("text", "witness"))
        witness = _Locator(visible=True, text=text)
        mutations = [("the element is not on the page", _Locator(visible=False, text=text))]
        if "text" in args:
            mutations.append(("the element reads something else", _Locator(visible=True, text=_OTHER)))
        return witness, mutations, ""
    if name == "persists":
        return ("written", "written"), [
            ("nothing was re-read after the restart", ("written", None)),
            ("what came back is not what was written", ("written", _OTHER)),
        ], ""
    if name == "emitted":
        want = _int(args["count"]) if "count" in args else 1
        witness = [{"event": i} for i in range(want)]
        mutations = [("nothing was emitted", [])]
        if "count" in args:
            mutations.append(("one more was emitted", [{"event": i} for i in range(want + 1)]))
        return witness, mutations, ""
    if name == "omits":
        subject = str(args["subject"])
        leak = str(args["text"]) if "text" in args else _matching(str(args.get("matches", "")))
        if leak is None:
            return None, [], f"no leaking value can be invented for /{args.get('matches')}/"
        clean = "a message that says nothing it may not"
        if _PATHLIKE.match(subject):
            return _set_path({}, subject, clean), [
                ("the subject carries what it may not", _set_path({}, subject, f"… {leak} …")),
            ], ""
        return clean, [("the observation carries what it may not", f"… {leak} …")], ""
    if name == "exit_status":
        code = _int(args["code"])
        return SimpleNamespace(exit_code=code), [
            ("the process exited differently", SimpleNamespace(exit_code=code + 1 if code == 0 else 0)),
        ], ""
    if name == "conflict_on_stale":
        url = "http://witness/subject"
        return _Response(409, {}, url), [("the stale write was accepted", _Response(200, {}, url))], ""
    return None, [], f"`{name}` has no witness in this harness"  # pragma: no cover - vocabulary drift


def trial(call: checks.CheckCall) -> Trial:
    """Put one declared call to the experiment: green on a witness, red on a defect."""
    witness, mutations, note = _plan(call)
    verifier = _VERIFIERS.get(call.name)
    if verifier is None or not mutations:
        return Trial(call.text(), False, (), (), note or f"`{call.name}` has no verifier")
    if not _green(verifier, witness, call.args):
        return Trial(call.text(), False, (), (), "the witness this harness builds does not satisfy the call")
    flipped, survived = [], []
    for label, mutated in mutations:
        (survived if _green(verifier, mutated, call.args) else flipped).append(label)
    return Trial(call.text(), True, tuple(flipped), tuple(survived))


def _green(verifier: Any, observed: Any, args: Any) -> bool:
    """The verifier's verdict, with a raise reading as red.

    A verifier raises when the observation is the wrong *shape* for the check, which is a
    defect in the scenario rather than in the product — but here the shapes are this
    module's, so a raise means the mutation was not one the check could look at, and
    counting it as a catch would credit sensitivity this experiment did not show.
    """
    try:
        passed, _, _ = verifier(observed, args)
    except Exception:  # noqa: BLE001 — every failure to compare is "not green"
        return False
    return bool(passed)


def _minted(node: model.UINode) -> list[tuple[str, int]]:
    """Every claim obligation the node mints, keyed the way its id is numbered.

    The same walk as `_obligations` in `qa/context.py`: one per normative bullet, counted per
    key in document order. Read here rather than taken from `attributed_checks` because that
    map holds only the bullets a `verify:` was attached to, and a claim nothing observes is
    precisely the one this report exists to name.
    """
    normative = set(registry.normative_keys(node.type))
    counts: dict[str, int] = {}
    minted: list[tuple[str, int]] = []
    for row in node.bullet_order:
        key = str(row[0])
        if key in normative:
            counts[key] = counts.get(key, 0) + 1
            minted.append((key, counts[key]))
    return minted


def report(graph: Graph) -> list[ClaimReport]:
    """Every obligation the book mints, and whether the checks on it can go red.

    Every obligation, not every obligation that declares a check. Skipping the undeclared ones
    makes the metric flatter the book that asserts least: a claim with no check at all would
    leave the denominator rather than fail, so a book could reach `9/9` by never observing the
    other fifty-eight things it promises. `ClaimReport.status` has always had an `undeclared`
    arm for this; it just had no way to fire.
    """
    rows: list[ClaimReport] = []
    for node in graph.ui_nodes:
        if registry.ui_type(node.type) is None:
            continue
        rel = _rel(node.path, graph.root)
        contract, per_claim = registry.attributed_checks(node.type, node.bullet_order)
        claims = [(f"{node.id}:contract", contract)]
        claims += [(f"{node.id}:{key.replace(' ', '-')}:{index}", per_claim.get((key, index), []))
                   for key, index in _minted(node)]
        for claim, values in claims:
            calls = [call for call in (checks.parse_check(value) for value in values)
                     if isinstance(call, checks.CheckCall)]
            rows.append(ClaimReport(claim, rel, node.line, tuple(trial(call) for call in calls)))
    return sorted(rows, key=lambda row: (row.path, row.line, row.claim))


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:  # pragma: no cover - a node outside the repo it was loaded from
        return path.as_posix()


def render(rows: list[ClaimReport]) -> str:
    """The report, as the operator and the QA-plan repair lap read it."""
    if not rows:
        return "this book mints no claim — nothing to put to the experiment"
    lines = []
    for row in rows:
        if row.status == "sensitive" and not any(t.survived or not t.witnessed for t in row.trials):
            continue
        # Not `{row.path}#{row.claim}`: the claim id already opens with the file path, so
        # prefixing it printed the path twice and produced a string no `covers=` list could
        # be grepped for. `row.path` still orders the rows and still rides in the JSON.
        lines.append(f"{row.status:<12} {row.claim}")
        if not row.trials:
            lines.append("    unobserved   no `verify:` is attached to this claim")
        for trial_ in row.trials:
            if not trial_.witnessed:
                lines.append(f"    unwitnessed  {trial_.call} — {trial_.note}")
            elif not trial_.flipped:
                lines.append(f"    always green {trial_.call} — survived: {', '.join(trial_.survived)}")
            elif trial_.survived:
                lines.append(f"    partial      {trial_.call} — survived: {', '.join(trial_.survived)}")
    insensitive = [row for row in rows if row.status == "insensitive"]
    undeclared = [row for row in rows if row.status == "undeclared"]
    # Counted apart from the insensitive ones, and never folded into a clean verdict: an
    # unobserved claim is a hole in the book rather than a weak assertion, and `doctor` is
    # where it is refused. Saying "every declared check can go red" over a book that declares
    # almost none is true and useless.
    if insensitive or undeclared:
        verdict = (
            f"{len(rows)} claims put to the experiment, "
            f"{len(insensitive)} insensitive, {len(undeclared)} unobserved"
        )
    else:
        verdict = f"every claim can be made to fail ({len(rows)} claim{'' if len(rows) == 1 else 's'})"
    return "\n".join([*lines, verdict]) if lines else verdict


def cmd_sensitivity(root: Path, *, node: str = "") -> QaOutcome:
    """Report which claims are observed by a check that could have failed."""
    graph = model.load(cwd=root)
    rows = [row for row in report(graph) if not node or node in row.claim or node in row.path]
    insensitive = [row.claim for row in rows if row.status == "insensitive"]
    return QaOutcome(
        ok=not insensitive,
        message=render(rows),
        status="insensitive" if insensitive else "sensitive",
        data={
            "claims": [
                {
                    "claim": row.claim,
                    "path": row.path,
                    "line": row.line,
                    "status": row.status,
                    "trials": [
                        {
                            "call": t.call,
                            "witnessed": t.witnessed,
                            "flipped": list(t.flipped),
                            "survived": list(t.survived),
                            "note": t.note,
                        }
                        for t in row.trials
                    ],
                }
                for row in rows
            ],
            "insensitive": insensitive,
        },
    )

"""Whether a declared check can go red at all — measured, not assumed."""

from __future__ import annotations

import functools
import importlib
import re
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from collections.abc import Callable, Mapping
from typing import Any

from ostler import checks, model, registry
from ostler.model import Graph
from ostler.qa.outcome import QaOutcome
from ostler.qa.harness_host import load_harness_module

_parser = importlib.import_module("re._parser")

_harness = load_harness_module("ostler_qa")
_path_grammar = load_harness_module("ostler_qa_paths")
_VERIFIERS = _harness.VERIFIERS
_UNSATISFIABLE = _harness.UNSATISFIABLE

_OTHER = "∅ not what was claimed"


def matches_admits_other(pattern: str) -> bool:
    """Whether a `json_path(matches=...)` pattern would let `_OTHER` through."""
    return re.search(pattern, _OTHER) is not None


class _Response:
    """The little of a response a verifier reads: a status, a body, its headers, the route that answered."""

    def __init__(self, status: int, body: Any, url: str,
                 headers: dict[str, str] | None = None) -> None:
        self.status_code = status
        self.url = url
        self.headers = headers or {}
        self.text = str(body)
        self._body = body

    def json(self) -> Any:
        return self._body


class _Locator:
    """The little of a page element a verifier reads."""

    def __init__(self, *, visible: bool, text: str, enabled: bool = True) -> None:
        self._visible = visible
        self._text = text
        self._enabled = enabled

    def is_visible(self) -> bool:
        return self._visible

    def is_enabled(self) -> bool:
        return self._enabled

    def inner_text(self) -> str:
        return self._text


class _Keyboard:
    """The keypress half of a page, and the record of which key was pressed."""

    def __init__(self, element: "_Focusable") -> None:
        self._element = element

    def press(self, key: str) -> None:
        self._element.receive_key(key)


class _Page:
    """The one attribute `focusable` reaches through the locator to find."""

    def __init__(self, element: "_Focusable") -> None:
        self.keyboard = _Keyboard(element)


class _Focusable:
    """A control that may or may not take focus, and may or may not fire on a key."""

    def __init__(self, *, takes_focus: bool, fires_on: str | None = None) -> None:
        self._takes_focus = takes_focus
        self._fires_on = fires_on
        self._focused = False
        self._armed = False
        self._activated = False
        self.page = _Page(self)

    def focus(self) -> None:
        self._focused = self._takes_focus

    def receive_key(self, key: str) -> None:
        if self._focused and self._armed and key == self._fires_on:
            self._activated = True

    def evaluate(self, expression: str) -> Any:
        """Answer the three expressions `_verify_focusable` sends, and refuse a fourth."""
        if "document.activeElement" in expression:
            return self._focused
        if "addEventListener" in expression:
            self._armed = True
            self._activated = False
            return None
        if "__ostlerActivated === true" in expression:
            return self._activated
        raise NotImplementedError(  # pragma: no cover - guards a verifier change
            f"the focusable witness does not know what to answer for {expression!r}"
        )


@dataclass(frozen=True)
class Trial:
    """One declared call, put to the experiment."""

    call: str
    witnessed: bool
    flipped: tuple[str, ...]
    survived: tuple[str, ...]
    note: str = ""
    unsatisfiable: bool = False

    @property
    def sensitive(self) -> bool:
        """Green on the witness, and red under *every* mutation the call is meant to catch."""
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
        """What the experiment showed: `unsatisfiable`, `sensitive`, `insensitive`, `unwitnessed`, `undeclared`."""
        if not self.trials:
            return "undeclared"
        if any(t.unsatisfiable for t in self.trials):
            return "unsatisfiable"
        if any(t.sensitive for t in self.trials):
            return "sensitive"
        return "insensitive" if any(t.witnessed for t in self.trials) else "unwitnessed"




def _set_path(document: dict[str, Any], path: str, value: Any) -> Any:
    """A document in which `path` resolves to `value`, built the way `resolve_path` walks."""
    steps = _steps(path)
    if not steps:
        return value
    root: Any = [] if isinstance(steps[0], int | _path_grammar.Wild | _path_grammar.Filter) else document
    cursor: Any = root
    for step, following in zip(steps, [*steps[1:], None], strict=True):
        nxt: Any = [] if isinstance(following, int | _path_grammar.Wild | _path_grammar.Filter) else {}
        if isinstance(step, _path_grammar.Wild | _path_grammar.Filter):
            if not cursor:
                cursor.append(None)
            if following is None:
                cursor[0] = value if isinstance(step, _path_grammar.Wild) else (value if isinstance(value, dict) else {})
            elif cursor[0] is None:
                cursor[0] = nxt
            if isinstance(step, _path_grammar.Filter) and isinstance(cursor[0], dict):
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
    return root


def _steps(path: str) -> list[Any]:
    return _path_grammar.path_steps(path)


def _collection(subject: str, size: int) -> dict[str, Any]:
    """A document in which `count(subject=)` finds `size` things."""
    items: list[Any] = [{"i": i} for i in range(size)]
    steps = _steps(subject)
    last = steps[-1] if steps else None
    if last is None:
        return _set_path({}, subject, items)
    if isinstance(last, _path_grammar.Wild | _path_grammar.Filter):
        marker = "[*]" if isinstance(last, _path_grammar.Wild) else "[?("
        parent = subject[: subject.rfind(marker)]
        if isinstance(last, _path_grammar.Filter):
            key, value = last.key, last.value
            items = [_set_path(item, key, value) for item in items]
        return _set_path({}, parent, items)
    return _set_path({}, subject, items)


def _drop_path(document: Any, path: str) -> Any:
    """The same document with the leaf `path` names taken out of it."""
    steps = _steps(path)
    if not steps:
        return None
    cursor = document
    for step in steps[:-1]:
        cursor = cursor[0] if isinstance(step, _path_grammar.Wild | _path_grammar.Filter) else cursor[step]
    last = steps[-1]
    if isinstance(last, _path_grammar.Wild | _path_grammar.Filter):
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
    """A string the pattern accepts, or None when this harness cannot invent one."""
    for candidate in (pattern, *pattern.split("|")):
        plain = candidate.strip("^$")
        if re.escape(plain) == plain and re.search(pattern, plain):
            return plain
    built = _synthesize(pattern)
    return built if built is not None and re.search(pattern, built) else None


def _avoiding(pattern: str | None, text: str | None) -> str | None:
    """A string the pattern rejects and the forbidden text stays out of, or None when there is none."""
    for candidate in ("a message that says nothing it may not", "", *_CLASS_POOL, "\n"):
        if text is not None and text in candidate:
            continue
        if pattern is None or re.search(pattern, candidate) is None:
            return candidate
    return None


_CLASS_POOL = "abcdefghijklmnopqrstuvwxyz0123456789_-"


def _synthesize(pattern: str) -> str | None:
    """One member of the language, read off the parse tree the `re` module itself builds."""
    try:
        tree = _parser.parse(pattern)
    except re.error:
        return None
    out: list[str] = []
    groups: dict[int, str] = {}
    return "".join(out) if _emit(tree, out, groups) else None


def _emit(tree: Any, out: list[str], groups: dict[int, str]) -> bool:
    """Append one member of *tree* to *out*, answering whether every piece could be inhabited."""
    for op, av in tree:
        name = op.name
        if name == "LITERAL":
            out.append(chr(av))
        elif name == "NOT_LITERAL":
            out.append(next((c for c in _CLASS_POOL if c != chr(av)), "a"))
        elif name == "ANY":
            out.append("a")
        elif name == "IN":
            char = _from_set(av)
            if char is None:
                return False
            out.append(char)
        elif name in {"MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT"}:
            low, _, body = av
            for _ in range(max(low, 0)):
                if not _emit(body, out, groups):
                    return False
        elif name == "SUBPATTERN":
            group, _, _, body = av
            mark = len(out)
            if not _emit(body, out, groups):
                return False
            if isinstance(group, int):
                groups[group] = "".join(out[mark:])
        elif name == "ATOMIC_GROUP":
            if not _emit(av, out, groups):
                return False
        elif name == "BRANCH":
            if not _branch(av[1], out, groups):
                return False
        elif name == "GROUPREF":
            out.append(groups.get(av, ""))
        elif name == "AT":
            if av.name == "AT_BOUNDARY" and out and out[-1][-1:].isalnum():
                out.append(" ")
        elif name in {"ASSERT", "ASSERT_NOT", "GROUPREF_EXISTS", "DIRECTIVE"}:
            continue
        else:  # pragma: no cover - a construct `re` grows later
            return False
    return True


def _branch(arms: Any, out: list[str], groups: dict[int, str]) -> bool:
    """The first arm of an alternation this harness can inhabit."""
    for arm in arms:
        piece: list[str] = []
        if _emit(arm, piece, dict(groups)):
            out.extend(piece)
            return True
    return False


def _from_set(members: Any) -> str | None:
    """One character the class admits, ranges expanded, negation honoured."""
    negated = any(op.name == "NEGATE" for op, _ in members)
    admitted: set[str] = set()
    classes: list[str] = []
    for op, av in members:
        if op.name == "LITERAL":
            admitted.add(chr(av))
        elif op.name == "RANGE":
            admitted |= {chr(c) for c in range(av[0], av[1] + 1)}
        elif op.name == "CATEGORY":
            if av.name not in _CATEGORY:
                return None
            admitted.add(_CATEGORY[av.name])
            classes.append(av.name)
        elif op.name == "NEGATE":
            continue
        else:  # pragma: no cover - a class construct `re` grows later
            return None
    if not negated:
        usable = sorted(admitted)
        return usable[0] if usable else None
    excluded = admitted | {c for c in _CLASS_POOL
                           for name in classes if _CATEGORY_HOLDS[name](c)}
    usable = sorted(set(_CLASS_POOL) - excluded)
    return usable[0] if usable else None


_CATEGORY = {
    "CATEGORY_DIGIT": "5", "CATEGORY_NOT_DIGIT": "a",
    "CATEGORY_WORD": "a", "CATEGORY_NOT_WORD": " ",
    "CATEGORY_SPACE": " ", "CATEGORY_NOT_SPACE": "a",
}

def _word(char: str) -> bool:
    """Whether `\\w` admits the character."""
    return char.isalnum() or char == "_"


_CATEGORY_HOLDS: dict[str, Callable[[str], bool]] = {
    "CATEGORY_DIGIT": str.isdigit,
    "CATEGORY_NOT_DIGIT": lambda c: not c.isdigit(),
    "CATEGORY_WORD": _word,
    "CATEGORY_NOT_WORD": lambda c: not _word(c),
    "CATEGORY_SPACE": str.isspace,
    "CATEGORY_NOT_SPACE": lambda c: not c.isspace(),
}


def _printed(stream: str, text: str) -> Any:
    """A finished command that printed `text` on `stream` and nothing on the other."""
    return _harness.ToolResult(
        command=["witness"],
        stdout=text if stream == "stdout" else "",
        stderr=text if stream == "stderr" else "",
        exit_code=0,
    )


@dataclass(frozen=True)
class _WitnessTexts:
    """A text holding what a call names, and a text holding none of it."""

    matching: str
    other: str


@dataclass(frozen=True)
class _NoWitness:
    """Why no pair of texts can tell a call's pass from its failure."""

    reason: str


_WitnessPlan = tuple[Any, list[tuple[str, Any]], str]


def _witness_texts(args: Mapping[str, Any]) -> _WitnessTexts | _NoWitness:
    """A text holding what the call's `text=` and `matches=` name and one holding neither, or why no such pair exists."""
    pattern = str(args["matches"]) if "matches" in args else None
    expected_output = str(args.get("text", ""))
    if pattern is not None and re.search(pattern, expected_output) is None:
        matched = _matching(pattern)
        if matched is None:
            return _NoWitness(f"no output can be invented for /{pattern}/")
        expected_output = f"{expected_output} {matched}".strip()
    other_output = _avoiding(pattern, str(args["text"]) if "text" in args else None)
    if other_output is None:
        return _NoWitness(f"every output carries something /{pattern}/ matches")
    return _WitnessTexts(matching=expected_output, other=other_output)


def _plan_stream(stream: str, args: Mapping[str, Any]) -> _WitnessPlan:
    """A tool result that printed what the call names on `stream`, and the results that printed it elsewhere or not at all."""
    texts = _witness_texts(args)
    if isinstance(texts, _NoWitness):
        return None, [], texts.reason
    expected_output, other_output = texts.matching, texts.other
    other_stream = "stderr" if stream == "stdout" else "stdout"
    return _printed(stream, expected_output), [
        (f"the command printed something else on {stream}", _printed(stream, other_output)),
        (f"the command printed it on {other_stream} instead", _printed(other_stream, expected_output)),
    ], ""

def _plan_contents(args: Mapping[str, Any]) -> _WitnessPlan:
    """A working directory whose file holds what the call names, and the directories where it holds something else or is not there."""
    texts = _witness_texts(args)
    if isinstance(texts, _NoWitness):
        return None, [], texts.reason
    expected, other = texts.matching, texts.other
    subject = str(args["subject"])
    return {subject: expected}, [
        ("the file holds something else", {subject: other}),
        ("the file is not there", {}),
    ], ""


def _plan(call: checks.CheckCall) -> _WitnessPlan:
    """The witness observation, the mutations to try against it, and why there are none: in the file a `file=` names, when the call names one."""
    witness, mutations, note = _plan_observed(call)
    if "file" not in call.args or witness is None:
        return witness, mutations, note
    name = str(call.args["file"])
    return {name: witness}, [
        *((label, {name: mutated}) for label, mutated in mutations),
        ("the file is not there", {}),
    ], note


def _plan_observed(call: checks.CheckCall) -> _WitnessPlan:
    """The witness observation, the mutations to try against it, and why there are none. Every check in the vocabulary has a planner."""
    return _PLANNERS[call.name](call.args)


def _plan_http_status(args: Mapping[str, Any]) -> _WitnessPlan:
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


def _plan_response_header(args: Mapping[str, Any]) -> _WitnessPlan:
    header = str(args["name"])
    if "equals" in args:
        value = str(args["equals"])
    else:
        found = _matching(str(args["matches"]))
        if found is None:
            return None, [], f"no witness value can be invented for /{args['matches']}/"
        value = found
    witness = _Response(200, {}, "http://witness/", {header: value})
    mutations: list[tuple[str, Any]] = [("the response does not carry the header", _Response(200, {}, "http://witness/"))]
    if "matches" not in args or not matches_admits_other(str(args["matches"])):
        mutations.append(("the header carries another value",
                          _Response(200, {}, "http://witness/", {header: _OTHER})))
    return witness, mutations, ""


def _plan_json_path(args: Mapping[str, Any]) -> _WitnessPlan:
    path = str(args["path"])
    if "absent" in args:
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
    mutations: list[tuple[str, Any]] = []
    if "matches" not in args or not matches_admits_other(str(args["matches"])):
        mutations.append(("the field holds something else", _set_path({}, path, _OTHER)))
    if "matches" not in args or _matching(str(args.get("matches", ""))) is not None:
        mutations.append(("the field is not there at all", _drop_path(_set_path({}, path, value), path)))
    return witness, mutations, ""


def _plan_unchanged(args: Mapping[str, Any]) -> _WitnessPlan:
    declared = args.get("except_fields", [])
    allowed = [str(field) for field in declared] if isinstance(declared, list) else []
    before = {"claimed": 1, "also_claimed": 2, **{field: 1 for field in allowed}}
    return (
        (before, dict(before)),
        [("a field the claim protects changed", (before, {**before, "claimed": 9}))],
        "",
    )


def _plan_keys_unchanged(_args: Mapping[str, Any]) -> _WitnessPlan:
    before = {"a": 1, "b": 2}
    return (
        (before, dict(before)),
        [
            ("an entry left the ledger", (before, {"a": 1})),
            ("an entry appeared in the ledger", (before, {**before, "c": 3})),
        ],
        "",
    )


def _plan_count(args: Mapping[str, Any]) -> _WitnessPlan:
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


def _plan_absent(_args: Mapping[str, Any]) -> _WitnessPlan:
    return None, [("the subject is there after all", ["something"])], ""


def _plan_created(_args: Mapping[str, Any]) -> _WitnessPlan:
    return (None, {"id": "x"}), [
        ("it was already there before the action", ({"id": "x"}, {"id": "x"})),
        ("nothing was created", (None, None)),
    ], ""


def _plan_removed(_args: Mapping[str, Any]) -> _WitnessPlan:
    return ({"id": "x"}, None), [
        ("it was never there to remove", (None, None)),
        ("it is still there afterwards", ({"id": "x"}, {"id": "x"})),
    ], ""


def _plan_visible(args: Mapping[str, Any]) -> _WitnessPlan:
    text = str(args.get("text", "witness"))
    witness = _Locator(visible=True, text=text)
    mutations: list[tuple[str, Any]] = [("the element is not on the page", _Locator(visible=False, text=text))]
    if "text" in args:
        mutations.append(("the element reads something else", _Locator(visible=True, text=_OTHER)))
    return witness, mutations, ""


def _plan_actionable(_args: Mapping[str, Any]) -> _WitnessPlan:
    return _Locator(visible=True, text="witness", enabled=True), [
        ("the control is disabled", _Locator(visible=True, text="witness", enabled=False)),
    ], ""


def _plan_focusable(args: Mapping[str, Any]) -> _WitnessPlan:
    key = str(args["activates"]) if "activates" in args else None
    witness = _Focusable(takes_focus=True, fires_on=key)
    mutations: list[tuple[str, Any]] = [
        ("the control cannot be reached by the keyboard", _Focusable(takes_focus=False, fires_on=key)),
    ]
    if key is not None:
        mutations.append(
            ("the control takes focus but the key does nothing", _Focusable(takes_focus=True, fires_on=None)),
        )
    return witness, mutations, ""


def _plan_inert(_args: Mapping[str, Any]) -> _WitnessPlan:
    return _Locator(visible=True, text="witness", enabled=False), [
        ("the control still accepts the action",
         _Locator(visible=True, text="witness", enabled=True)),
    ], ""


def _plan_persists(_args: Mapping[str, Any]) -> _WitnessPlan:
    return ("written", "written"), [
        ("nothing was re-read after the restart", ("written", None)),
        ("what came back is not what was written", ("written", _OTHER)),
    ], ""


def _plan_emitted(args: Mapping[str, Any]) -> _WitnessPlan:
    want = _int(args["count"]) if "count" in args else 1
    witness = [{"event": i} for i in range(want)]
    mutations: list[tuple[str, Any]] = []
    if want != 0:
        mutations.append(("nothing was emitted", []))
    if "count" in args:
        mutations.append(("one more was emitted", [{"event": i} for i in range(want + 1)]))
    return witness, mutations, ""


def _plan_omits(args: Mapping[str, Any]) -> _WitnessPlan:
    subject = str(args["subject"])
    pattern = str(args["matches"]) if "matches" in args else None
    leak = str(args["text"]) if "text" in args else _matching(pattern or "")
    if leak is None:
        return None, [], f"no leaking value can be invented for /{args.get('matches')}/"
    clean = _avoiding(pattern, str(args["text"]) if "text" in args else None)
    if clean is None:
        return None, [], f"every observation carries something /{pattern}/ matches"
    framed = f"… {leak} …"
    if pattern is None or re.search(pattern, framed):
        tainted = framed
    elif re.search(pattern, leak):
        tainted = leak
    else:
        tainted = None
    if tainted is None:
        return None, [], f"no perturbation of /{pattern}/ would itself violate the claim"
    if _PATHLIKE.match(subject):
        return _set_path({}, subject, clean), [
            ("the subject carries what it may not", _set_path({}, subject, tainted)),
        ], ""
    return clean, [("the observation carries what it may not", tainted)], ""


def _plan_exit_status(args: Mapping[str, Any]) -> _WitnessPlan:
    code = _int(args["code"])
    return SimpleNamespace(exit_code=code), [
        ("the process exited differently", SimpleNamespace(exit_code=code + 1 if code == 0 else 0)),
    ], ""


def _plan_conflict_on_stale(_args: Mapping[str, Any]) -> _WitnessPlan:
    url = "http://witness/subject"
    return _Response(409, {}, url), [("the stale write was accepted", _Response(200, {}, url))], ""


_PLANNERS: dict[str, Callable[[Mapping[str, Any]], _WitnessPlan]] = {
    "http_status": _plan_http_status,
    "response_header": _plan_response_header,
    "json_path": _plan_json_path,
    "unchanged": _plan_unchanged,
    "keys_unchanged": _plan_keys_unchanged,
    "count": _plan_count,
    "absent": _plan_absent,
    "created": _plan_created,
    "removed": _plan_removed,
    "visible": _plan_visible,
    "actionable": _plan_actionable,
    "focusable": _plan_focusable,
    "inert": _plan_inert,
    "persists": _plan_persists,
    "emitted": _plan_emitted,
    "omits": _plan_omits,
    "exit_status": _plan_exit_status,
    "stdout": functools.partial(_plan_stream, "stdout"),
    "stderr": functools.partial(_plan_stream, "stderr"),
    "contents": _plan_contents,
    "conflict_on_stale": _plan_conflict_on_stale,
}


def unsatisfiable(call: checks.CheckCall) -> str:
    """Why no observation can satisfy this call, or empty when one can."""
    rule = _UNSATISFIABLE.get(call.name)
    return str(rule(call.args)) if rule is not None else ""


def trial(call: checks.CheckCall) -> Trial:
    """Put one declared call to the experiment: green on a witness, red on a defect."""
    refused = unsatisfiable(call)
    if refused:
        return Trial(call.text(), False, (), (), refused, unsatisfiable=True)
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
    """The verifier's verdict, with a raise reading as red."""
    try:
        passed, _, _ = verifier(observed, args)
    except Exception:  # noqa: BLE001 — every failure to compare is "not green"
        return False
    return bool(passed)


def _minted(node: model.UINode) -> list[tuple[str, int]]:
    """Every claim obligation the node mints, keyed the way its id is numbered."""
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
    """Every obligation the book mints, and whether the checks on it can go red."""
    rows: list[ClaimReport] = []
    for node in graph.ui_nodes:
        if registry.ui_type(node.type) is None:
            continue
        rel = _rel(node.path, graph.root)
        contract, per_claim = registry.attributed_checks(node.type, node.bullet_order, node.combiners)
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
        lines.append(f"{row.status:<12} {row.claim}")
        if not row.trials:
            lines.append("    unobserved   no `verify:` is attached to this claim")
        for trial_ in row.trials:
            if trial_.unsatisfiable:
                lines.append(f"    impossible   {trial_.call} — {trial_.note}")
            elif not trial_.witnessed:
                lines.append(f"    unwitnessed  {trial_.call} — {trial_.note}")
            elif not trial_.flipped:
                lines.append(f"    always green {trial_.call} — survived: {', '.join(trial_.survived)}")
            elif trial_.survived:
                lines.append(f"    partial      {trial_.call} — survived: {', '.join(trial_.survived)}")
    insensitive = [row for row in rows if row.status == "insensitive"]
    undeclared = [row for row in rows if row.status == "undeclared"]
    unwitnessed = [row for row in rows if row.status == "unwitnessed"]
    impossible = [row for row in rows if row.status == "unsatisfiable"]
    if insensitive or undeclared or unwitnessed or impossible:
        verdict = (
            f"{len(rows)} claims put to the experiment, "
            f"{len(insensitive)} insensitive, {len(undeclared)} unobserved, "
            f"{len(impossible)} impossible (no observation could satisfy the call), "
            f"{len(unwitnessed)} unwitnessed (this harness could not build a witness)"
        )
    else:
        verdict = f"every claim can be made to fail ({len(rows)} claim{'' if len(rows) == 1 else 's'})"
    return "\n".join([*lines, verdict]) if lines else verdict


def cmd_sensitivity(root: Path, *, node: str = "") -> QaOutcome:
    """Report which claims are observed by a check that could have failed."""
    graph = model.load(cwd=root)
    rows = [row for row in report(graph) if not node or node in row.claim or node in row.path]
    insensitive = [row.claim for row in rows if row.status == "insensitive"]
    unwitnessed = [row.claim for row in rows if row.status == "unwitnessed"]
    impossible = [row.claim for row in rows if row.status == "unsatisfiable"]
    return QaOutcome(
        ok=not (insensitive or impossible),
        message=render(rows),
        status="unsatisfiable" if impossible else ("insensitive" if insensitive else "sensitive"),
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
                            "unsatisfiable": t.unsatisfiable,
                        }
                        for t in row.trials
                    ],
                }
                for row in rows
            ],
            "insensitive": insensitive,
            "unwitnessed": unwitnessed,
            "unsatisfiable": impossible,
        },
    )

"""Every example a skill teaches goes through the parsers, the doctor and the compiler that judge a real book."""
from __future__ import annotations

import argparse
import functools
import re
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from posixpath import normpath

import pytest

from ostler import acts, checks, cli, doctor, registry
from ostler.model import load
from ostler.qa import context as qa_context
from ostler.qa.compile import compile_plan_gaps

SKILLS = Path(__file__).resolve().parents[2] / "base-library/library/skills"
NODE_TYPES = "ostler/ostler-okf/references/node-types"
FENCE = re.compile(r"^```markdown(?P<info>[^\n]*)\n(?P<body>.*?)^```", re.S | re.M)
CLAIM = re.compile(r"^\s*(?:\d+\.\s+)?- (verify|arrange|intercept): (.+)$", re.M)
LINK = re.compile(r"\]\(([^)#\s]+\.md)(?:#([a-z0-9-]+))?\)|\"([^\"#\s]+\.md)#([a-z0-9-]+)\"")
KEYED_LINK = re.compile(r"^\s*- ([a-z-]+):[^\n]*\]\(([^)#\s]+\.md)[^)]*\)", re.M)
FIXTURE = re.compile(r"^\s*- fixture: ([a-z0-9-]+)", re.M)
FACT = re.compile(r"@([a-z0-9-]+)\.([a-z0-9_-]+)")
SIBLING = re.compile(r"\]\(#([a-z0-9-]+)\)|locator=\"#([a-z0-9-]+)\"")
OWN_HEADING = re.compile(r"^### (.+)$", re.M)
EXAMPLE_PATH = re.compile(r'path=\"(/[^\"]*)\"')
EXPECT = re.compile(r"\bexpect=([a-z-]+(?:,[a-z-]+)*)")
PAGE_TYPE = re.compile(r"^type: (\S+)", re.M)
BASH_FENCE = re.compile(r"^```(?:bash|sh|shell)\n(.*?)^```", re.S | re.M)
INLINE_COMMAND = re.compile(r"`((?:timeout \d+ )?(?:uv run (?:--all-packages )?)?ostler [^`]+)`")
COMMAND_START = re.compile(r"(?:^|\s)ostler ")
COMMAND_END = re.compile(r"\s(?:\||&&|\|\||;|>|<<?\s|#)\s?")

PARSERS = {"verify": checks.parse_check, "arrange": acts.parse_act, "intercept": checks.parse_intercept}
FICTIONAL_PROJECT = {
    "dangling-code-ref": "an example cites source its own fictional project holds",
    "missing-code-symbol": "an example cites source its own fictional project holds",
    "stale-citation": "an example cites source its own fictional project holds",
}
ABSENT_NEIGHBOUR = {
    "unreached-data-state": "the walk that reads a data state lives on another page",
    "unread-condition": "the data state a `when:` links lives on another page",
    "precondition-discharged-by-arrangement": "this gap only says a `when:` is met by its arrangement",
    "unresolved-precondition": "the value a linked path takes is captured on a page the example only links",
}
FRAGMENT_ONLY = {"empty-required-section": "the host of a fragment is a stub that lists nothing else"}
PAGE_WIDE = (":contract", ":end-state")
FRAGMENT_HOSTS = {"component": "screen", "interaction": "screen", "invocation": "server", "method": "server",
                  "field": "format", "step": "runbook", "fixture": "fixture"}
SCREEN_STUB = "- route: /\n- requires: none\n- params: none\n\n## Screen states\n\n### Loaded\n\n- shows: the page\n"
SERVER_STUB = "- entry-url: http://localhost:8000\n\n## Endpoints\n\n"
GRPC_STUB = "- entry-url: http://localhost:8000\n\n## RPCs\n\n"
ENDPOINT_STUB = "- method: GET\n- path: /stub\n- does: answers\n- verify: http_status(code=200, path=\"/stub\")\n"
HOST_BULLETS = {"screen": SCREEN_STUB, "server": SERVER_STUB, "grpc-server": GRPC_STUB, "endpoint": ENDPOINT_STUB,
                "cli": "- binary: stub\n"}
NEIGHBOUR_TYPES = {"server": "server", "surfaces": "server", "environment": "environment", "launch-screen": "screen",
                   "open": "screen"}
LISTING = {"endpoint", "rpc"}
DRIVERS = {"cli": "cli", "command": "cli", "server": "http", "endpoint": "http", "grpc-server": "grpc", "rpc": "grpc",
           "screen": "web", "flow": "http"}


@dataclass(frozen=True)
class Example:
    source: str
    line: int
    body: str
    expected: frozenset[str]

    def __str__(self) -> str:
        return f"{self.source}:{self.line}"

    @property
    def is_page(self) -> bool:
        return self.body.startswith("---")

    @property
    def is_fragment(self) -> bool:
        return self.source.startswith(NODE_TYPES) and self.body.startswith(("### ", "## "))

    @property
    def node_type(self) -> str:
        return Path(self.source).stem

    @property
    def own_anchors(self) -> frozenset[str]:
        return frozenset(re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") for name in OWN_HEADING.findall(self.body))


def _skill_pages() -> Iterator[tuple[str, str]]:
    for path in sorted(SKILLS.rglob("*.md")):
        yield path.relative_to(SKILLS).as_posix(), path.read_text(encoding="utf-8")


def _examples() -> list[Example]:
    found = []
    for source, text in _skill_pages():
        for fence in FENCE.finditer(text):
            expect = EXPECT.search(fence["info"])
            found.append(Example(
                source,
                text.count("\n", 0, fence.start()) + 1,
                fence["body"],
                frozenset(expect[1].split(",")) if expect else frozenset(),
            ))
    return found


EXAMPLES = _examples()
PARSED = [example for example in EXAMPLES if not example.expected and CLAIM.search(example.body)]
COMPILED = [example for example in EXAMPLES if (example.is_page or example.is_fragment) and CLAIM.search(example.body)]


def _page_text(example: Example) -> str:
    if example.is_page:
        return example.body
    node = registry.UI_TYPES_BY_NAME.get(example.node_type)
    host = FRAGMENT_HOSTS.get(example.node_type) or (node.host_page_types[0] if node else "concept")
    heading = "" if example.body.startswith("## ") or node is None else f"## {node.heading}\n\n"
    siblings = "".join(
        f"\n### {name}\n\n- role: button\n- name: {name}\n"
        for name in sorted({left or right for left, right in SIBLING.findall(example.body)})
        if f"### {name}\n" not in example.body
    )
    neighbours = "Components" if host == "screen" else "Neighbours"
    components = f"\n## {neighbours}\n{siblings}" if siblings else ""
    return f"---\ntype: {host}\n---\n\n# Host\n\n{HOST_BULLETS.get(host, '')}\n{heading}{example.body}{components}"


def _write_stubs(root: Path, home: Path, page: str, kind: str) -> str:
    surface = "example.md"
    keys = {relative: key for key, relative in KEYED_LINK.findall(page)}
    anchors: dict[str, set[str]] = {}
    for link, anchor, located, control in LINK.findall(page):
        anchors.setdefault(link or located, set()).update(filter(None, (anchor, control)))
    for relative, named in anchors.items():
        neighbour = Path(normpath(home / relative))
        if root not in neighbour.parents:
            continue
        key = keys.get(relative, "")
        stub = NEIGHBOUR_TYPES.get(key, "endpoint" if kind == "flow" else "screen" if named else "concept")
        if (key, kind) == ("server", "rpc"):
            stub = "grpc-server"
        if key in {"on", "observe"} or (kind == "server" and not key):
            stub = "endpoint"
        listing = "- [example](example.md)\n" if key == "server" and kind in LISTING else ""
        headings = "".join(f"\n### {name}\n\n- role: button\n- name: {name}\n" for name in sorted(named))
        section = f"\n## Components\n{headings}" if headings else ""
        neighbour.parent.mkdir(parents=True, exist_ok=True)
        bullets = HOST_BULLETS.get(stub, "")
        if stub == "endpoint" and (named_path := EXAMPLE_PATH.search(page)):
            bullets = bullets.replace("/stub", named_path[1])
        neighbour.write_text(f"---\ntype: {stub}\n---\n\n# Stub\n\n{bullets}{listing}{section}", encoding="utf-8")
        if key == "server":
            surface = relative
    return surface


def _write_fixtures(home: Path, page: str) -> None:
    facts: dict[str, set[str]] = {}
    for name, key in FACT.findall(page):
        facts.setdefault(name, set()).add(key)
    for name in {*FIXTURE.findall(page), *facts} - {"none"}:
        provided = "".join(f"  - {key} — a fact\n    - is: value\n" for key in sorted(facts.get(name, ())))
        provides = f"- provides:\n{provided}" if provided else ""
        (home / f"{name}.md").write_text(
            f"---\ntype: fixture\n---\n\n# {name}\n\n{provides}\n## Steps\n\n### seed\n\n- kind: seed\n- run: true\n",
            encoding="utf-8",
        )


def _book(root: Path, example: Example) -> str:
    """A throwaway book holding the example, a stub per page it links, and the runbook that drives it."""
    page = _page_text(example)
    home = root / "docs/services/demo/pages"
    home.mkdir(parents=True)
    _write_fixtures(home, page)
    (home / "example.md").write_text(page, encoding="utf-8")
    page_type = PAGE_TYPE.search(page)
    kind = page_type[1] if page_type else "concept"
    surface = _write_stubs(root, home, page, kind)
    if kind in DRIVERS:
        (home / "drive.md").write_text(
            f"---\ntype: runbook\n---\n\n# Drive\n\n- driver: {DRIVERS[kind]}\n"
            f"- entry-url: http://localhost:8000\n- surfaces: [surface]({surface})\n",
            encoding="utf-8",
        )
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "book"], check=True)
    return "docs/services/demo/pages/example.md"


def _is_own(example: Example, obligation_id: str) -> bool:
    anchor = obligation_id.partition("#")[2].partition(":")[0]
    return not (example.is_fragment and example.own_anchors) or anchor in example.own_anchors


def _findings(root: Path, path: str, example: Example) -> dict[str, list[str]]:
    """Every doctor error and compile gap the example earns, by code, leaving out what its absent neighbours cause."""
    found: dict[str, list[str]] = {}
    for finding in doctor.run(load(root)).findings:
        if finding.severity == "error" and (finding.path or "").startswith(path):
            found.setdefault(finding.code, []).append(finding.message)
    result = compile_plan_gaps(qa_context.book_context(root), story="examples", base_url="http://localhost:8000")
    for gap in result.gaps:
        if (
            path in gap.obligation_id
            and _is_own(example, gap.obligation_id)
            and not (gap.kind == "no-verify-declared" and gap.obligation_id.endswith(PAGE_WIDE))
        ):
            found.setdefault(gap.kind, []).append(f"{gap.obligation_id}: {gap.detail}")
    excused = {*FICTIONAL_PROJECT, *ABSENT_NEIGHBOUR, *(FRAGMENT_ONLY if example.is_fragment else ())}
    return {code: messages for code, messages in found.items() if code not in excused}


_parser = functools.cache(cli._build_parser)


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return {name: choice for name, choice in action.choices.items() if isinstance(choice, argparse.ArgumentParser)}
    return {}


def _positional_choices(parser: argparse.ArgumentParser) -> list[tuple[object, ...] | None]:
    return [
        tuple(action.choices) if action.choices is not None else None
        for action in parser._actions
        if not action.option_strings and not isinstance(action, argparse._SubParsersAction)
    ]


def _is_literal(token: str) -> bool:
    return re.fullmatch(r"[a-z][a-z0-9-]*", token) is not None


def command_problems(command: str) -> list[str]:
    """What the real command line would refuse in *command*, a skill's spelling of one ostler call."""
    tokens = COMMAND_END.split(COMMAND_START.split(command, maxsplit=1)[1])[0].split()
    parser = _parser()
    choices: list[tuple[object, ...] | None] = []
    problems = []
    options = {option for action in parser._actions for option in action.option_strings}
    skip = False
    for raw in tokens:
        token = raw.strip("[](),.:'\"")
        if skip:
            skip = False
        elif token == "-C":
            skip = True
        elif token == "--" or "<" in token and not token.startswith("-"):
            if token == "--":
                break
            if _subparsers(parser):
                break
            choices = choices[1:]
        elif token.startswith("--"):
            for flag in token.split("=")[0].split("|"):
                if flag not in options:
                    problems.append(f"{flag} is no flag of `ostler ... {parser.prog.rpartition(' ')[2]}`")
        elif token.startswith("-"):
            continue
        elif subparsers := _subparsers(parser):
            if token not in subparsers:
                if _is_literal(token):
                    problems.append(f"{token} is no command of `{parser.prog}`")
                break
            parser = subparsers[token]
            choices = _positional_choices(parser)
            options |= {option for action in parser._actions for option in action.option_strings}
        elif choices:
            allowed, choices = choices[0], choices[1:]
            if allowed is not None and _is_literal(token) and token not in allowed:
                problems.append(f"{token} is not one of {sorted(map(str, allowed))}")
    return problems


def _commands() -> Iterator[tuple[str, str]]:
    for source, text in _skill_pages():
        for fence in BASH_FENCE.finditer(text):
            for line in fence[1].splitlines():
                if COMMAND_START.search(line) and not line.lstrip().startswith("#"):
                    yield source, line
        for line in BASH_FENCE.sub("", text).splitlines():
            for span in INLINE_COMMAND.findall(line):
                yield source, span


@pytest.mark.parametrize("example", PARSED, ids=str)
def test_every_claim_line_parses(example: Example) -> None:
    refused = [
        line[0]
        for line in ((match[0], PARSERS[match[1]](match[2].strip())) for match in CLAIM.finditer(example.body))
        if isinstance(line[1], checks.Refusal)
    ]
    assert refused == []


@pytest.mark.parametrize("example", COMPILED, ids=str)
def test_every_example_earns_only_what_it_declares(example: Example, tmp_path: Path) -> None:
    found = _findings(tmp_path, _book(tmp_path, example), example)
    assert set(found) == set(example.expected), "\n".join(line for lines in found.values() for line in lines)


def test_every_command_a_skill_spells_exists() -> None:
    wrong = [f"{source}: {command}: {problem}" for source, command in _commands() for problem in command_problems(command)]
    assert wrong == []


@pytest.mark.parametrize("command", [
    "ostler nonsense",
    "ostler doctor --nonsense",
    "timeout 30 ostler scaffold nonsense thing --service acme",
    "ostler query nonsense",
    "ostler qa nonsense",
])
def test_a_command_the_cli_refuses_goes_red(command: str) -> None:
    assert command_problems(command)


@pytest.mark.parametrize("command", [
    "ostler doctor --path docs/services/acme",
    "ostler -C ../other doctor",
    "timeout 30 ostler scaffold screen link-editor --service acme",
    "ostler env exec -- pytest --nonsense",
    "ostler search <term> [--type concept|flow]",
])
def test_a_command_the_cli_takes_stays_green(command: str) -> None:
    assert command_problems(command) == []

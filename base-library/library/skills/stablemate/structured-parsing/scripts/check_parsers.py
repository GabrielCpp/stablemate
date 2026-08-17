#!/usr/bin/env python3
"""Guard the "parse, don't match" rule. Wired into `make test`.

A format with a grammar — YAML, Markdown, JSON, a programming language, a unified diff —
has a parser, and a regex over its raw text is a re-implementation of that parser with
none of its cases. The failures are silent in both directions, which is what makes them
expensive: this pass found `load_jsonc` truncating every config containing a URL (`//`
inside a string literal is not a comment), three different frontmatter fences that
disagreed about what closes one, and markdown link/bullet regexes that matched inside
fenced code blocks. None of those raised; they returned confidently wrong answers.

So this flags **regex pattern literals whose text encodes a known format's grammar** and
names the parser to use instead. The rule, its boundary and the parser-per-format table
live in the `structured-parsing` skill (base-library).

**What this is not.** It is a pattern-shape denylist, not semantic analysis. It knows the
shapes that have gone wrong here; it cannot prove an arbitrary regex is not parsing a
format, and it says nothing about a pattern built at runtime from non-literal parts. Same
character as `check_public.py`: a guard against a known silent failure, not a proof.

Regex remains the right tool for text that has no grammar — an agent CLI's log line, a
cap-reset message, a token counter — and for identifier validators and slugifiers, which
constrain a string rather than parse one. Those shapes are not flagged at all. Where a
format genuinely has no parser available (Go, TypeScript, PHP, Twig, Makefile) the site is
declared in `ALLOWED` with the reason, and the reason is printed on any failure.

Run:
    uv run python base-library/library/skills/stablemate/structured-parsing/scripts/check_parsers.py
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    """The repo being checked, found by ascent rather than by a fixed depth.

    This script installs beside its skill, so how deep it sits under the repo is the
    library's layout and not this rule's — a `parents[N]` was true only while it lived in
    `<repo>/scripts/`, and went silently wrong the moment the skill carried it elsewhere.
    Ascending to the working copy's own marker is the one form that survives the move.
    """
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".git").exists():
            return candidate
    return Path.cwd()


REPO = _repo_root()

#: `re` functions that take a pattern as their first argument.
RE_FUNCS = frozenset(
    {"compile", "search", "match", "fullmatch", "findall", "finditer", "sub", "subn", "split"}
)

# --------------------------------------------------------------------------------------
# The shapes
# --------------------------------------------------------------------------------------
# Each detector is a regex matched against the *text of the pattern literal*, so `\\A` below
# means the two characters a pattern spells `\A`. What the detectors look for is a pattern
# that anchors itself to a line and then describes a document's punctuation — that is a
# grammar being re-implemented, whatever the format.

#: How a pattern spells "start of a line": `^`, `\A`, or the newline it scans past.
_ANCHOR = r"(?:\^|\\A|\\n)"
#: How a pattern spells "optional leading whitespace".
_INDENT = r"(?:\\s\*|\[ \\t\]\*|\\t\*| \*)?"
#: How a pattern spells "the whitespace after a delimiter", before whatever follows it.
_GAP = r"(?:(?:\\s|\\t|\[ \\t\]| )[*+]?)"

DETECTORS: dict[str, tuple[str, str]] = {
    # shape: (detector over the pattern text, the parser to use instead)
    "frontmatter-fence": (
        _ANCHOR + r"\(?-{3}",
        "ostler.markdown.split (or farrier.frontmatter) — a real front_matter token",
    ),
    "html-comment": (
        r"<!--",
        "ostler.markdown — the html_block / html_inline token",
    ),
    "md-heading": (
        _ANCHOR + _INDENT + r"\\?#",
        "ostler.markdown — Section / find_section / Section.body",
    ),
    "md-link": (
        r"\\\]\\\(|!\\\[",
        "ostler.markdown — iter_links / References, which never match inside code",
    ),
    "md-bullet": (
        _ANCHOR + _INDENT + r"(?:\\?[-*+]|\[[-*+\\ ]+\])" + _GAP,
        "ostler.markdown — Section.bullets / Bullet.label / .value / .bracketed",
    ),
    "code-fence": (
        r"```|~~~",
        "ostler.markdown — the fence token (a fenced block is not prose)",
    ),
    "md-table": (
        r"(?:" + _ANCHOR + _INDENT + r"\\\||\\\|\s*:?-{3,})",
        "ostler.markdown — Section.tables / Table.records / Table.column",
    ),
    "diff-hunk": (
        r"(?:@@|" + _ANCHOR + r"(?:\\\+){3})",
        "unidiff — PatchSet, which tells a hunk header from a line that was added",
    ),
    "lang-decl": (
        r"\b(?:async|def|class|function|func|fn|interface|enum)\b",
        "ast, for Python. No stdlib parser exists for the other languages — declare it below",
    ),
    "path-suffix": (
        r"\\\.\((?:\?:)?[A-Za-z0-9?|]*\|[A-Za-z0-9?|]*\)",
        "pathlib.Path(...).suffix against a set — an alternation is not where a suffix begins",
    ),
    "key-line": (
        _ANCHOR + _INDENT + r"[^\n]{0,80}?:" + _GAP + r"?\(",
        "yaml.safe_load for YAML; for a line protocol of our own, the one shared reader",
    ),
    "brace-span": (
        r"\\\{[\s\S]{0,20}(?:\.\*|\[\\s\\S\]\*)[\s\S]{0,20}\\\}",
        "json.JSONDecoder().raw_decode scanned from each `{` — a brace span is not a value",
    ),
}

#: `(path relative to the repo, shape)` → why that shape is right there. Printed on failure,
#: and checked for staleness: an entry that no longer matches anything fails too, so a reason
#: cannot outlive the code it excuses and the list stays readable as a list of real exceptions.
ALLOWED: dict[tuple[str, str], str] = {
    ("ostler/ostler/qa/context.py", "lang-decl"): (
        "the last-resort line scan for a language *no* grammar reads — `.rb`, `.java`, `.rs`. "
        "Every language `ostler.syntax` knows is parsed (`inventory.extents`) and never reaches "
        "this; attributing a changed hunk to the nearest declaration-shaped line above it is "
        "worse than a parse and better than reporting the diff touched nothing"
    ),
    ("ostler/ostler/qa/context.py", "html-comment"): (
        "`<!--` here is one of five comment syntaxes (`//`, `#`, `/*`, `--`, `<!--`) in the "
        "generated-file marker every code generator copies from Go. That is a sentence to find "
        "in a source file of any language, not an HTML block in a markdown document"
    ),
    ("workhorse/workhorse/gates.py", "key-line"): (
        "the `STATUS:` / `SCOPE:` gate header — our own two-line protocol, not a format with a "
        "grammar, so regex is right. This module exists so there is exactly one copy of it: the "
        "pattern used to be retyped on both sides of the same file (a workflow writes the "
        "header, groom's UI reads and rewrites it), where a divergence is a gate that never opens"
    ),
    ("groom/groom/gates.py", "md-heading"): (
        "locating the `## Questions from the agent` section of a gate file for a *preview* in "
        "the UI. Best-effort by construction — it falls back to a truncated dump of the whole "
        "file — and it reads a file this codebase wrote, not a document a user authored"
    ),
}


def _normalise(pattern: str) -> str:
    """Regex punctuation that would otherwise read as the document's punctuation.

    `(?:` carries a colon that has nothing to do with a `key: value` line, and a lookahead's
    `(` is not a value being captured. Both are rewritten before the detectors see them, so
    the shapes below can be about the format rather than about regex syntax.
    """
    pattern = re.sub(r"\(\?P<[^>]*>|\(\?:", "(", pattern)
    return re.sub(r"\(\?(?:<?[=!]|>)", "\u27ea", pattern)


# --------------------------------------------------------------------------------------
# The scan
# --------------------------------------------------------------------------------------
def _python_files() -> list[Path]:
    """Every `.py` the repo would ship, minus tests, frozen artifacts, and this file.

    Tracked **and** not-yet-added (`--others --exclude-standard`), unlike `check_public.py`,
    which asks a different question: that one is about what ships, and an unadded file does
    not. This one is about code being written, and a module is at its most worth checking
    before its first `git add` — the whole point is to catch the shape while it is being
    typed rather than after it is history.

    - **Tests** name the shapes they test, so scanning them would flag the very fixtures
      that pin the parsers' behaviour.
    - **`docs/plans/**`** is history: those modules declare themselves superseded and nothing
      imports or runs them. Rewriting a frozen artifact to satisfy a check would make it a
      worse record of what was actually built.
    - **This file** spells out every shape it looks for, so it matches itself on all of them.
    """
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    paths = []
    for rel in out.stdout.split():
        parts = Path(rel).parts
        if "tests" in parts or Path(rel).name.startswith("test_"):
            continue
        if parts[:2] == ("docs", "plans") or rel == "scripts/check_parsers.py":
            continue
        paths.append(REPO / rel)
    return sorted(paths)


def _module_strings(tree: ast.AST) -> dict[str, str]:
    """Module-level `NAME = "…"` bindings, so an f-string's `{NAME}` can be substituted in.

    A grammar written as a regex is usually written in pieces — a suffix alternation named
    once, interpolated into the pattern that uses it. Reading only the f-string's constant
    parts hides exactly the piece that carries the format, which is how a suffix alternation
    interpolated as `{_EXTS}` sat here unflagged.
    """
    return {
        target.id: node.value.value
        for node in getattr(tree, "body", ())
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
        if isinstance(node.value.value, str)
        for target in node.targets
        if isinstance(target, ast.Name)
    }


def _pattern_text(node: ast.expr, consts: dict[str, str]) -> str | None:
    """The literal text of a pattern argument, or None when it is not literal.

    An f-string counts for its constant parts, plus any `{NAME}` naming a module-level
    string: `rf"^-\\s*{key}:"` is still an anchored bullet regardless of what `key` is.
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue) and isinstance(value.value, ast.Name):
                parts.append(consts.get(value.value.id, ""))
        return "".join(parts) or None
    return None


def _patterns(tree: ast.AST):
    """Every `re.<func>(<literal>, …)` in a module, as `(lineno, pattern text)`."""
    consts = _module_strings(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "re"
            and func.attr in RE_FUNCS
        ):
            continue
        if (text := _pattern_text(node.args[0], consts)) is not None:
            yield node.lineno, text


def check_parsers() -> list[str]:
    """Every format-shaped regex is either gone or declared, and every declaration is live."""
    detectors = {shape: re.compile(rx) for shape, (rx, _) in DETECTORS.items()}
    problems: list[str] = []
    used: set[tuple[str, str]] = set()
    scanned = 0

    for path in _python_files():
        rel = path.relative_to(REPO).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        scanned += 1
        for lineno, pattern in _patterns(tree):
            normalised = _normalise(pattern)
            for shape, detector in detectors.items():
                if not detector.search(normalised):
                    continue
                if (rel, shape) in ALLOWED:
                    used.add((rel, shape))
                    continue
                problems.append(
                    f"{rel}:{lineno}: [{shape}] {pattern!r}\n"
                    f"      use instead: {DETECTORS[shape][1]}"
                )

    for key in ALLOWED:
        if key not in used:
            problems.append(
                f"{key[0]}: the [{key[1]}] exemption no longer matches anything — delete it "
                f"from ALLOWED in scripts/check_parsers.py"
            )

    if not problems:
        print(f"ok: no format-shaped regex outside the {len(ALLOWED)} declared sites "
              f"({scanned} modules scanned)")
    return problems


def main() -> int:
    problems = check_parsers()
    if not problems:
        return 0
    print("\nFAIL check_parsers:", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    print(
        "\nA format with a grammar gets its parser; a regex over its raw text is that parser "
        "re-implemented without its cases, and it fails silently. See the "
        "`stablemate-structured-parsing` skill for the rule, the parser-per-format table, and "
        "how to declare an exemption when no parser exists.",
        file=sys.stderr,
    )
    if ALLOWED:
        print("\nAlready declared:", file=sys.stderr)
        for (path, shape), why in sorted(ALLOWED.items()):
            print(f"  {path} [{shape}] — {why}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

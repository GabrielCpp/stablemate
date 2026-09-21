#!/usr/bin/env python3
"""Guard the "parse, don't match" rule."""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path

CONFIG = ".agent-checks.toml"
TABLE = "check-parsers"

RE_FUNCS = frozenset(
    {"compile", "search", "match", "fullmatch", "findall", "finditer", "sub", "subn", "split"}
)


_ANCHOR = r"(?:\^|\\A|\\n)"
_INDENT = r"(?:\\s\*|\[ \\t\]\*|\\t\*| \*)?"
_GAP = r"(?:(?:\\s|\\t|\[ \\t\]| )[*+]?)"

DETECTORS: dict[str, tuple[str, str]] = {
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


def _normalise(pattern: str) -> str:
    """Regex punctuation that would otherwise read as the document's punctuation."""
    pattern = re.sub(r"\(\?P<[^>]*>|\(\?:", "(", pattern)
    return re.sub(r"\(\?(?:<?[=!]|>)", "\u27ea", pattern)


def declarations(root: Path) -> dict:
    """What *root*'s repo declares to this check, from its `.agent-checks.toml`."""
    config = root / CONFIG
    if not config.is_file():
        return {}
    return tomllib.loads(config.read_text(encoding="utf-8")).get(TABLE, {})


def _python_files(root: Path, exclude: list[str]) -> list[Path]:
    """Every `.py` the repo would ship, minus tests, declared exclusions, and this file."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    excluded = tuple(Path(entry).parts for entry in exclude)
    paths = []
    for rel in out.stdout.split():
        parts = Path(rel).parts
        if "tests" in parts or Path(rel).name.startswith("test_"):
            continue
        if Path(rel).name == Path(__file__).name:
            continue
        if any(parts[: len(prefix)] == prefix for prefix in excluded):
            continue
        paths.append(root / rel)
    return sorted(paths)


def _module_strings(tree: ast.AST) -> dict[str, str]:
    """Module-level `NAME = "…"` bindings, so an f-string's `{NAME}` can be substituted in."""
    return {
        target.id: node.value.value
        for node in getattr(tree, "body", ())
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
        if isinstance(node.value.value, str)
        for target in node.targets
        if isinstance(target, ast.Name)
    }


def _pattern_text(node: ast.expr, consts: dict[str, str]) -> str | None:
    """The literal text of a pattern argument, or None when it is not literal."""
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


def _allowed(declared: dict) -> dict[tuple[str, str], str]:
    """The declared exemptions as `(path, shape) → why`, from the nested TOML tables."""
    return {
        (path, shape): why
        for path, shapes in declared.get("allow", {}).items()
        for shape, why in shapes.items()
    }


def check_parsers(root: Path) -> list[str]:
    """Every format-shaped regex is either gone or declared, and every declaration is live."""
    declared = declarations(root)
    allowed = _allowed(declared)
    detectors = {shape: re.compile(rx) for shape, (rx, _) in DETECTORS.items()}
    problems: list[str] = []
    used: set[tuple[str, str]] = set()
    scanned = 0

    for path in _python_files(root, declared.get("exclude", [])):
        rel = path.relative_to(root).as_posix()
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
                if (rel, shape) in allowed:
                    used.add((rel, shape))
                    continue
                problems.append(
                    f"{rel}:{lineno}: [{shape}] {pattern!r}\n"
                    f"      use instead: {DETECTORS[shape][1]}"
                )

    for key in allowed:
        if key not in used:
            problems.append(
                f"{key[0]}: the [{key[1]}] exemption no longer matches anything — delete it "
                f"from [{TABLE}.allow] in {CONFIG}"
            )

    if not problems:
        print(f"ok: no format-shaped regex outside the {len(allowed)} declared sites "
              f"({scanned} modules scanned)")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(), help=f"repo holding {CONFIG} (default: cwd)"
    )
    args = parser.parse_args()

    allowed = _allowed(declarations(args.root))
    problems = check_parsers(args.root)
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
    if allowed:
        print("\nAlready declared:", file=sys.stderr)
        for (path, shape), why in sorted(allowed.items()):
            print(f"  {path} [{shape}] — {why.strip()}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

"""Move a repo's dotenv onto its environment page: literals onto the page, secrets into saddlebag."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TextIO

from ostler import markdown, model
from ostler.edit import FileChange
from ostler.environments import commands, inject, page
from ostler.environments.runtime import Runner, run_command

_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")
_EXPORT = re.compile(r"export\s+")
_COMMENT = re.compile(r"\s+#.*$")


def _unquote(text: str) -> str:
    if text[:1] in ("'", '"'):
        end = text.find(text[0], 1)
        return text[1:end] if end > 0 else text[1:]
    return _COMMENT.sub("", text).strip()


def parse_assignments(text: str) -> dict[str, str]:
    """The dotenv's `KEY=value` lines in file order, read the way `saddlebag env` reads them."""
    found: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if match := _EXPORT.match(line):
            line = line[match.end():]
        key, sep, rest = line.partition("=")
        key = key.strip()
        if sep and _KEY.fullmatch(key):
            found[key] = _unquote(rest.strip())
    return found


def _variable_line(name: str, value: str | None) -> str:
    return f"  - {name}: {page.HELD_MARK if value is None else value}"


def _block(entries: list[tuple[str, str | None]]) -> list[str]:
    return ["- variables:", *(_variable_line(name, value) for name, value in entries)]


def rewrite_variables(text: str, entries: list[tuple[str, str | None]]) -> str:
    """*text* with its `variables:` bullet replaced by *entries*, or one added when the page has none."""
    doc = markdown.split(text)
    lines = doc.body.split("\n")
    block = _block(entries)
    bullet = doc.find_bullet("variables")
    if bullet is not None:
        lines[bullet.line_start:bullet.line_end] = block
    else:
        tops = [b for b in doc.walk_bullets()
                if not any(o is not b and o.line_start <= b.line_start < o.line_end
                           for o in doc.walk_bullets())]
        if tops:
            at = tops[-1].line_end
            lines[at:at] = block
        else:
            while lines and not lines[-1].strip():
                lines.pop()
            lines += ["", *block, ""] if lines else [*block, ""]
    doc.replace_body(lines)
    return doc.render()


def _tail(text: str | None) -> str:
    return "\n".join((text or "").strip().splitlines()[-5:])


def cmd_import_dotenv(root: Path, file: Path, token: str, *, runner: Runner = run_command,
                      out: TextIO = sys.stdout) -> commands.EnvOutcome:
    """Put *file*'s literals on the environment page *token* names and its secrets into saddlebag."""
    fail = commands._fail
    try:
        node = page.find_environment(model.load(root), token)
        slug = page.slug_of(node)
        current = page.read_variables(node)
    except (LookupError, page.VariableError) as exc:
        return fail(str(exc))
    try:
        verdicts = inject.classify_file(file, runner)
    except inject.ClassifyError as exc:
        return fail(str(exc))
    try:
        values = parse_assignments(file.read_text(encoding="utf-8"))
    except OSError as exc:
        return fail(f"cannot read {file}: {exc.strerror or exc}")
    keys = list(dict.fromkeys(key for key, _ in verdicts))
    rules = dict(verdicts)
    for key in keys:
        if not page.is_variable_name(key):
            return fail(f"{file}: {key} is not a name the page can hold")
        if rules[key] is None and key not in values:
            return fail(f"{file}: {key} is in saddlebag's reading of the file and not in "
                        f"ostler's; fix the line")
        if rules[key] is None and values[key] == page.HELD_MARK:
            return fail(f"{file}: {key} has the value `{page.HELD_MARK}`, which the page reads "
                        f"as a held name; change the value or store the key in saddlebag")
    secret = [key for key in keys if rules[key] is not None]
    already: list[str] = []
    if secret:
        try:
            held_vars = {var for _, var in inject.records(slug, runner)}
        except inject.ResolutionError as exc:
            return fail(str(exc))
        already = [key for key in secret if key in held_vars]
    imported = [key for key in secret if key not in already]
    incoming = {key: None if rules[key] is not None else values[key] for key in keys}
    merged = [(name, incoming.pop(name) if name in incoming else value)
              for name, value in current.entries]
    merged += list(incoming.items())

    old = node.path.read_text(encoding="utf-8")
    change = FileChange(node.path, old, rewrite_variables(old, merged))
    print(change.diff(), file=out, end="")
    node.path.write_text(change.new, encoding="utf-8")

    stored: list[str] = []
    if imported:
        argv = ["saddlebag", "env", "import", str(file), "--keys", ",".join(imported),
                "--tag", f"environment={slug}", "--prefix", f"{slug}-"]
        try:
            outcome = runner(argv, capture=True)
        except OSError as exc:
            return fail(f"saddlebag could not run: {exc.strerror or exc}; the page names "
                        f"{', '.join(imported)} as held")
        stored = [line for line in (outcome.stdout or "").splitlines() if line.strip()]
        if outcome.returncode != 0:
            tail = _tail(outcome.stderr)
            create = f"saddlebag secret create <name> --var <KEY> --tag environment={slug}"
            return fail(
                f"saddlebag env import exited {outcome.returncode} after the page was written; "
                f"the page names {', '.join(imported)} as held, and `{create}` finishes the "
                f"registration" + (f":\n{tail}" if tail else ""),
                stored=stored)

    try:
        shown = node.path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        shown = str(node.path)
    lines = [f"{len(keys)} lines: {len(secret)} held, {len(keys) - len(secret)} literal"]
    if already:
        lines.append(f"{len(already)} already held")
    lines += stored
    lines.append(f"next: review the diff above and commit {shown}; `ostler env dotenv {slug}` "
                 f"writes the file back when a tool still wants one")
    return commands.EnvOutcome(True, "\n".join(lines), {
        "ok": True, "page": str(node.path), "lines": len(keys), "held": len(secret),
        "literal": len(keys) - len(secret), "imported": imported, "already_held": already})

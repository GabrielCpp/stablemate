"""The `STATUS:` / `SCOPE:` header on the file an `Await` waits on.

`Await(path, questions, …)` writes the ask and polls the file's mtime; what the file
*says* once someone has written back is this header — two whole lines, each a keyword and
a token:

    STATUS: AWAITING_OPERATOR
    SCOPE: epic

It is a line protocol, not a format with a grammar, so a regex is the right tool here (the
`stablemate-structured-parsing` skill draws that boundary, and `scripts/check_parsers.py`
declares this module as the reason). What was wrong was having **five** of them: the same
pattern was retyped in `groom.gates`, in three workflow node modules, and once more in a
superseded design artifact, each with its own reader and its own rewrite. Nothing made
them agree; a fix to one — tolerating a tab, or a status the writer lower-cased — reached
none of the others, and the file is a handshake between a workflow that writes it and an
operator UI that reads it, so a divergence is a gate that never opens.

Deliberately **vocabulary-free**: this returns the raw token and never names one. Which
states a given file may be in is the caller's business and differs between them — an
operator gate cycles `AWAITING_OPERATOR` → `ANSWERED` → `CONSUMED`, a feedback inbox only
`NEW` → `CONSUMED` — and `SCOPE`'s values are a workflow's own vocabulary, which the
engine must not learn.
"""

from __future__ import annotations

import re

#: A whole-line `KEY: value`, matched at the start of any line, value being the first
#: run of non-whitespace. Tabs are allowed after the colon because a human hand-edits
#: these files.
_STATUS_RE = re.compile(r"^STATUS:[ \t]*(\S+)", re.MULTILINE)
_SCOPE_RE = re.compile(r"^SCOPE:[ \t]*(\S+)", re.MULTILINE)


def status_of(text: str) -> str:
    """The `STATUS:` token, upper-cased; ``""`` when the file carries no such line.

    Absent is its own answer, distinct from every state — a file a human pasted notes
    into without the header is not in any of them, and each caller decides what that
    means (usually: treat it as new, forgivingly).
    """
    match = _STATUS_RE.search(text)
    return match.group(1).upper() if match else ""


def scope_of(text: str) -> str:
    """The `SCOPE:` token, lower-cased; ``""`` when absent. The values are the caller's."""
    match = _SCOPE_RE.search(text)
    return match.group(1).lower() if match else ""


def set_status(text: str, status: str) -> str:
    """`text` with its first `STATUS:` line reading `status` — added at the top if absent.

    Rewriting only the first line is what makes reading a file *consume* it: a follow-up
    block quoting an earlier `STATUS:` in prose stays quoted rather than being flipped
    too, so a re-block re-arms instead of looping on its own history.
    """
    if _STATUS_RE.search(text):
        return _STATUS_RE.sub(f"STATUS: {status}", text, count=1)
    return f"STATUS: {status}\n\n{text}"

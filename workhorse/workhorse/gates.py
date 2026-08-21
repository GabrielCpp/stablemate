"""The `STATUS:` / `SCOPE:` header on the file an `Await` waits on.

`Await(path, questions, …)` writes a canonical operator ask and polls the file's mtime;
what the file says before and after someone writes back is this header — two whole lines,
each a keyword and a token:

    STATUS: AWAITING_OPERATOR
    SCOPE: epic

It is a line protocol, not a format with a grammar, so a regex is the right tool here (the
`stablemate-structured-parsing` skill draws that boundary, and `.agent-checks.toml`
declares this module with the reason). What was wrong was having **five** of them: the same
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

from markdown_it import MarkdownIt

#: A whole-line `KEY: value`, matched at the start of any line, value being the first
#: run of non-whitespace. Tabs are allowed after the colon because a human hand-edits
#: these files.
_STATUS_RE = re.compile(r"^STATUS:[ \t]*(\S+)", re.MULTILINE)
_SCOPE_RE = re.compile(r"^SCOPE:[ \t]*(\S+)", re.MULTILINE)
_MARKDOWN = MarkdownIt("commonmark")
_QUESTION_HEADINGS = {"question from the agent", "questions from the agent"}


def _has_question_heading(text: str) -> bool:
    tokens = _MARKDOWN.parse(text)
    for opening, title in zip(tokens, tokens[1:], strict=False):
        if opening.type != "heading_open" or opening.tag != "h2" or title.type != "inline":
            continue
        if " ".join(title.content.split()).casefold() in _QUESTION_HEADINGS:
            return True
    return False


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


def format_operator_gate(questions: str) -> str:
    """Return a canonical, Groom-discoverable operator gate.

    A workflow may hand :class:`~workhorse.pyflow.Await` either plain questions or a
    complete context file. Plain text gets the standard heading; structured content is
    only re-armed so its sections are not wrapped or duplicated.
    """
    body = questions.strip()
    if status_of(body) or _has_question_heading(body):
        return set_status(body, "AWAITING_OPERATOR").rstrip() + "\n"
    return (
        "STATUS: AWAITING_OPERATOR\n\n"
        "## Questions from the agent\n\n"
        f"{body}\n"
    )


def append_operator_gate(existing: str, questions: str) -> str:
    """An operator gate that already exists, re-armed with `questions` appended.

    The first `STATUS:` line is set in place and **everything already in the file is
    kept** — content this engine did not write included. The same file is both the
    question channel and the answer channel, so what is already there is either the
    operator's answers, which a run resumed from this gate still has to read, or the
    history of an earlier block, which is the evidence about whether this one is
    recurring. Replacing the file wholesale lost both: a benchmark round that blocked
    twice on one gate ended with a five-line file, the answers it had been given at the
    first block gone.

    Appending costs nothing, because only the first `STATUS:` line is read: nothing
    written below it can contradict the state this puts the gate in.
    """
    block = _STATUS_RE.sub("", format_operator_gate(questions), count=1).strip()
    return f"{set_status(existing, 'AWAITING_OPERATOR').rstrip()}\n\n{block}\n"

"""The `STATUS:` / `SCOPE:` header on the file an `Await` waits on."""

from __future__ import annotations

import re

from markdown_it import MarkdownIt

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
    """The `STATUS:` token, upper-cased; ``""`` when the file carries no such line."""
    match = _STATUS_RE.search(text)
    return match.group(1).upper() if match else ""


def scope_of(text: str) -> str:
    """The `SCOPE:` token, lower-cased; ``""`` when absent."""
    match = _SCOPE_RE.search(text)
    return match.group(1).lower() if match else ""


def set_status(text: str, status: str) -> str:
    """`text` with its first `STATUS:` line reading `status` — added at the top if absent."""
    if _STATUS_RE.search(text):
        return _STATUS_RE.sub(f"STATUS: {status}", text, count=1)
    return f"STATUS: {status}\n\n{text}"


def format_operator_gate(questions: str) -> str:
    """Return a canonical, Groom-discoverable operator gate."""
    body = questions.strip()
    if status_of(body) or _has_question_heading(body):
        return set_status(body, "AWAITING_OPERATOR").rstrip() + "\n"
    return (
        "STATUS: AWAITING_OPERATOR\n\n"
        "## Questions from the agent\n\n"
        f"{body}\n"
    )


def apply_answer(text: str, answer: str) -> str:
    """`text` answered: the first `STATUS:` flips to `ANSWERED`, `answer` lands below."""
    answered = set_status(text, "ANSWERED")
    answer = answer.strip()
    if not answer:
        return answered
    return answered.rstrip() + f"\n\n{answer}\n"


def append_operator_gate(existing: str, questions: str) -> str:
    """An operator gate that already exists, re-armed with `questions` appended."""
    block = _STATUS_RE.sub("", format_operator_gate(questions), count=1).strip()
    return f"{set_status(existing, 'AWAITING_OPERATOR').rstrip()}\n\n{block}\n"

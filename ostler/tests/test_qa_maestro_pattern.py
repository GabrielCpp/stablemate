"""The Maestro `text:` regex reads a book value the way the browser driver does."""

from __future__ import annotations

import re

import pytest

from ostler.qa.harness_host import load_harness_module

elements = load_harness_module("ostler_qa_elements")

TICKET = "{ticket.title}, {ticket.status_label}, {ticket.category_label}"

CASES: list[tuple[str, str, str | None, str, bool]] = [
    ("same case", "Open tickets", None, "Open tickets", True),
    ("different case", "Open tickets", None, "OPEN Tickets", True),
    ("required mark", "Email", None, "Email *", True),
    ("extra word", "Open tickets", None, "Open tickets now", False),
    ("split words", "Open tickets", None, "Open\ntickets", True),
    ("metacharacter", "Open tickets (3)", None, "Open tickets (3)", True),
    ("metacharacter is not a group", "Open tickets (3)", None, "Open tickets 3", False),
    ("dot is not a wildcard", "v1.2", None, "v1x2", False),
    ("three holes", TICKET, None, "Printer jams, Received, Billing", True),
    ("three holes, too few", TICKET, None, "Printer jams, Received", False),
    ("template is case-sensitive", "Ticket {ticket.id}", None, "ticket 4", False),
    ("template hole", "Ticket {ticket.id}", None, "Ticket 4", True),
    ("empty hole", "Title{draft.title_error}", None, "Title", True),
    ("hole holding a line", "Title{draft.title_error}", None, "Title\nTitle is required", True),
    ("hole with a wrong prefix", "Title{draft.title_error}", None, "Subtitle", False),
    ("text present", "Open tickets", "tick", "Open tickets", True),
    ("text absent", "Open tickets", "Received", "Open tickets", False),
    ("text in another case", "Open tickets", "TICK", "Open tickets", False),
    ("text with a newline label", "Open tickets", "tick", "Open\ntickets", True),
    ("text only with a newline label", "", "Received", "Printer jams\nReceived", True),
    ("template and text", TICKET, "Received", "Printer jams, Received, Billing", True),
    ("template and absent text", TICKET, "Shipped", "Printer jams, Received, Billing", False),
    ("text only", "", "Received", "Printer jams, Received", True),
    ("text only, another case", "", "Received", "printer jams, received", False),
    ("text with a metacharacter", "", "a.b (c)", "x a.b (c) y", True),
    ("text with a quote end", "", r"a\Eb", r"xa\Eby", True),
    ("non-breaking space between words", "Open tickets", None, "Open\u00a0tickets", True),
    ("accented case", "Paramètres", None, "PARAMÈTRES", True),
    ("accented letter is not punctuation", "Paramètres", None, "éParamètres", False),
]


def browser_verdict(name: str, text: str | None, label: str) -> bool:
    if name:
        build = elements.template_pattern if re.search(r"\$?\{[^{}]*\}", name) else elements.name_pattern
        if build(name).search(label) is None:
            return False
    return text is None or text in label


def java_to_python(pattern: str) -> str:
    """The test-only translation of the Java regex to Python's: `\\Q..\\E` quoting, `\\z` and the Unicode classes Python has by default."""
    quoted = re.sub(r"\\Q(.*?)\\E", lambda found: re.escape(found.group(1)), pattern)
    return quoted.replace(r"\z", r"\Z").replace("(?sU)", "(?s)")


def phone_verdict(name: str, text: str | None, label: str) -> bool:
    pattern = java_to_python(elements.maestro_pattern(name, text=text))
    return re.fullmatch(pattern, label, flags=re.IGNORECASE | re.DOTALL) is not None


@pytest.mark.parametrize(("case", "name", "text", "label", "expected"), CASES, ids=[c[0] for c in CASES])
def test_the_phone_pattern_and_the_browser_agree_on_every_label(
    case: str, name: str, text: str | None, label: str, expected: bool,
) -> None:
    assert browser_verdict(name, text, label) is expected
    assert phone_verdict(name, text, label) is expected


def test_java_quote_closes_and_reopens_around_an_embedded_end_marker() -> None:
    assert elements.java_quote(r"a\Eb") == r"\Qa\E\\E\Qb\E"

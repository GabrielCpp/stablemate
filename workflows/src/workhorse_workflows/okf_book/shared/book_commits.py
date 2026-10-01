"""The messages a book is committed under, which tell a rerun whether this workflow finished it."""
from __future__ import annotations

import re


def book_commit_subject(service: str) -> str:
    """The subject of a book this workflow's writer finished."""
    return f"docs({service}): write the {service} book"


def unfinished_book_commit_subject(service: str) -> str:
    """The subject of the pages a failed writer turn left, so a rerun sends a writer to finish them."""
    return f"docs({service}): keep the unfinished {service} book"


def rooted_book_commit_subject(service: str) -> str:
    """The subject of the entries page code wrote for a book that had none."""
    return f"docs({service}): root the {service} book"


BOOK_TRAILER = "Okf-Book"
REPAIRED = "repaired"
SUBJECT_LIMIT = 72
_TYPE_PREFIX = re.compile(r"^[a-z]+(\([^)]*\))?!?: ")


def repaired_book_commit_subject(service: str) -> str:
    """The subject of the pages one repair turn changed when nothing describes them, and of every repair commit made before the trailer."""
    return f"docs({service}): repair pages of the {service} book"


def repaired_book_commit_message(service: str, description: str = "", body: str = "") -> str:
    """The message of the pages one repair turn changed: a subject that says what changed, and the trailer that marks a repair.

    A rerun checks and runs a book whose last commit carries the trailer as this workflow's own, and never repairs it again.
    """
    subject = f"docs({service}): {description}" if description else repaired_book_commit_subject(service)
    return "\n\n".join(part for part in (subject, body.strip(), f"{BOOK_TRAILER}: {REPAIRED}") if part)


def repair_description_refusal(service: str, description: str) -> str:
    """Why *description* cannot follow `docs(<service>): ` in a repair subject, or "" when it can."""
    subject = f"docs({service}): {description}"
    refusals = (
        (not description.strip() or "\n" in description, "the description is one non-empty line"),
        (description != description.strip(), "the description has no leading or trailing spaces"),
        (
            bool(_TYPE_PREFIX.match(description)),
            f"the description leaves out the type prefix, since the subject already starts with `docs({service}): `",
        ),
        (description[:1].isupper(), "the description starts lowercase"),
        (description.endswith("."), "the description ends without a period"),
        (len(subject) > SUBJECT_LIMIT, f"the subject {subject!r} is {len(subject)} characters, over {SUBJECT_LIMIT}"),
    )
    return next((reason for refused, reason in refusals if refused), "")

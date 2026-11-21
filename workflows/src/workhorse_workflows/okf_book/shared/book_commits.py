"""The messages a book is committed under, which tell a rerun whether this workflow finished it."""
from __future__ import annotations



def book_commit_subject(service: str) -> str:
    """The subject of a book this workflow's writer finished."""
    return f"docs({service}): write the {service} book"


def unfinished_book_commit_subject(service: str) -> str:
    """The subject of the pages a failed writer turn left, so a rerun sends a writer to finish them."""
    return f"docs({service}): keep the unfinished {service} book"


BOOK_TRAILER = "Okf-Book"
REPAIRED = "repaired"


def repaired_book_commit_subject(service: str) -> str:
    """The subject of the pages one repair turn changed when nothing describes them, and of every repair commit made before the trailer."""
    return f"docs({service}): repair pages of the {service} book"


def repaired_book_commit_message(service: str, description: str = "", body: str = "") -> str:
    """The message of the pages one repair turn changed: a subject that says what changed, and the trailer that marks a repair.

    A rerun checks and runs a book whose last commit carries the trailer as this workflow's own, and never repairs it again.
    """
    subject = f"docs({service}): {description}" if description else repaired_book_commit_subject(service)
    return "\n\n".join(part for part in (subject, body.strip(), f"{BOOK_TRAILER}: {REPAIRED}") if part)


SUBJECT_LIMIT = 72


def batch_suffix(batch: int) -> str:
    """What a later batch of a book adds to its commit subject."""
    return f" (batch {batch})" if batch > 1 else ""


def caught_up_book_commit_subject(service: str, batch: int = 1) -> str:
    """The subject of a book this workflow's catch-up brought up to the app's HEAD, with the batch it was committed in when that is a later one and the subject still fits."""
    subject = f"docs({service}): catch the {service} book up with the app"
    return next((line for line in (subject + batch_suffix(batch), subject) if len(line) <= SUBJECT_LIMIT), subject)


def format_book_commit_subject(service: str, batch: int = 1) -> str:
    """The subject of a book this workflow's catch-up moved onto the current book format, naming the book once and then shortening the rest where the service's name is long. A later batch adds its number where the subject still fits, and drops it where the shortest wording cannot carry it."""
    options = (
        f"docs({service}): move the {service} book onto the current book format",
        f"docs({service}): move the book onto the current book format",
        f"docs({service}): adopt the current book format",
    )
    suffix = batch_suffix(batch)
    fits = [subject for subject in options if len(subject + suffix) <= SUBJECT_LIMIT]
    if fits:
        return fits[0] + suffix
    return next((subject for subject in options if len(subject) <= SUBJECT_LIMIT), options[-1])

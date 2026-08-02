"""Conventional Commit subjects for everything the coder workflow writes to git.

The coder commits into *other people's* repositories, and those repositories cut releases
with **release-please**, which reads commit subjects and squash-merge PR titles and nothing
else. A subject like `0004-checkout: guest-cart` parses as no type at all, so a story that
shipped a user-facing feature produces no version bump and no changelog entry — the work
lands and the release never mentions it. That is the failure this module exists to prevent,
and it is why the subject shape is built here rather than interpolated at each callsite:
there are eight of them (story commits in every affected repo, the status stamp, the two
marker commits, the queue prune, the epic PR title, the story PR title, and the merge
commit), and one of them drifting is one release going silent.

**A story is `feat`.** The coder has no signal that would let it choose a type per story —
the story documents behavior, not the semver consequence of implementing it — so it does
not guess. `feat` is the honest default because a story is by construction new documented
behavior, and it is the *safe* default because the failure mode is a minor bump where a
patch would have done, rather than a shipped feature nobody was told about. The give-up
markers keep `feat` for the same reason: the story's code is in that commit, whatever the
marker says about its QA. What is *not* a story — the status stamp, the queue prune — is
typed `docs`/`chore`, which release-please correctly declines to release.

**The scope is the package, not the epic.** In a release-please monorepo config the scope
selects the component whose version moves; an epic name selects nothing and would be
noise in every changelog. The epic and story slugs go in the body instead, where a human
triaging `git log` still finds them.
"""
from __future__ import annotations

import re
from pathlib import Path

#: Conventional Commits imposes no subject length, but release notes and `git log --oneline`
#: both read a subject at terminal width, and every host truncates past roughly this.
SUBJECT_LIMIT = 72

#: What survives in a scope: release-please matches its configured component names against
#: this text, so anything that is not a plausible package name is dropped rather than
#: escaped into something that matches nothing.
_SCOPE_STRIP = re.compile(r"[^a-z0-9._-]+")


def scope(name: str) -> str:
    """The Conventional Commit scope for a repo/package name (`""` when nothing survives).

    Takes the workspace key where there is one — that is the name the workspace file and
    release-please config both spell the package with — and a directory name otherwise.
    """
    cleaned = _SCOPE_STRIP.sub("-", name.strip().lower()).strip("-.")
    return cleaned


def describe(text: str) -> str:
    """Normalize a story heading into a Conventional Commit description.

    Lowercases the first word and drops a trailing period, the two things that make a
    document heading read as a heading in a changelog. An identifier-shaped first word
    (`STORY-1`, `OAuth`) is left alone: lowercasing it would rename the thing it names.
    """
    stripped = " ".join(text.split()).rstrip(".")
    if not stripped:
        return ""
    head, _, tail = stripped.partition(" ")
    if head[1:].islower() or not head[1:]:
        head = head[0].lower() + head[1:]
    return f"{head} {tail}".strip()


def subject(kind: str, package: str, description: str, marker: str = "") -> str:
    """`<kind>(<package>): <description> <marker>`, trimmed to :data:`SUBJECT_LIMIT`.

    `marker` is the give-up annotation (`[QA FAILED …]`) and is never what gets trimmed —
    it is the first thing a human triaging the epic PR reads, and a subject that lost half
    of it reads as a story that passed. The description gives way instead, and if even a
    minimal description will not fit beside the marker the limit does.
    """
    head = f"{kind}({package})" if package else kind
    body = describe(description) or "no description"
    tail = f" {marker}" if marker else ""
    budget = SUBJECT_LIMIT - len(f"{head}: {tail}")
    if len(body) > budget:
        body = body[: max(budget, 0)].rstrip(" -–—:,") or body.split(" ")[0]
    return f"{head}: {body}{tail}"


def message(
    kind: str,
    package: str,
    description: str,
    marker: str = "",
    epic: str = "",
    story: str = "",
) -> str:
    """A full commit message: the conventional subject, plus the epic/story it came from.

    The trailers are the coder's audit trail. They are *not* in the subject because the
    subject is what a changelog quotes verbatim, and a reader of the released changelog
    has no doc graph to resolve `0004-checkout` against.
    """
    lines = [subject(kind, package, description, marker)]
    trailers = [f"{label}: {value}" for label, value in (("Epic", epic), ("Story", story)) if value]
    if trailers:
        lines.extend(["", *trailers])
    return "\n".join(lines)


def story_description(root: Path, story_path: str, fallback: str = "") -> str:
    """The story's `# ` heading, normalized — what its commit and its PR title both say.

    The heading is the one sentence a human wrote about this story, so it is what belongs
    in a changelog; the slug is the fallback because it always exists and is greppable, not
    because it reads well.
    """
    full = root / story_path if story_path else None
    if full is not None and full.is_file():
        try:
            for line in full.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("# "):
                    return describe(stripped[2:])
        except OSError:
            pass
    return describe(fallback)


__all__ = ["SUBJECT_LIMIT", "describe", "message", "scope", "story_description", "subject"]

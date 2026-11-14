from datetime import date

from ostler.book import Journey, OwnerRefused

from ..endpoints import FinishFromDigest, ReadDigest, ReadDigestEntry


class TheTodoApiTurnsACallerAway(Journey):
    """A caller with no credential, and a caller who asks for a todo nobody added, get the todo
    API's refusal back from the digest as it came, whether they read or finish."""

    def steps(self, today: date):
        yield OwnerRefused(ReadDigest(by=None))
        yield OwnerRefused(ReadDigestEntry("nobody-added-this", by=None))
        yield OwnerRefused(ReadDigestEntry("nobody-added-this"))
        yield OwnerRefused(FinishFromDigest("nobody-added-this", by=None))
        yield OwnerRefused(FinishFromDigest("nobody-added-this"))

from datetime import date

from ostler.book import Journey, Refused

from ..endpoints import ReadDigest, ReadDigestEntry


class TheTodoApiTurnsACallerAway(Journey):
    """A caller with no credential, and a caller who asks for a todo nobody added, get the todo
    API's refusal word for word."""

    def steps(self, today: date):
        yield Refused(ReadDigest(by=None), 401, "Unauthorized")
        yield Refused(ReadDigestEntry("nobody-added-this", by=None), 401, "Unauthorized")
        yield Refused(ReadDigestEntry("nobody-added-this"), 404, "Not found")

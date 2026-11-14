from ostler.book import request
from ostler.book.screen import Lists

from .labels import ANYONE, NOBODY

RECEIVED = request("GET", "/users")


def by_name(users):
    """the users received, by name"""
    return sorted(u["name"] for u in users)


FILTER = Lists(head=(ANYONE,), given=RECEIVED, derived=by_name)
FORM = Lists(head=(NOBODY,), given=RECEIVED, derived=by_name)

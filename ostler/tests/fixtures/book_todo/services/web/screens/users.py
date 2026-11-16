from ostler.book import request
from ostler.book import in_order, no_repeat
from ostler.book.screen import Lists

from .labels import ANYONE, NOBODY

RECEIVED = request("GET", "/users")


def by_name(users):
    """the users received, by name"""
    return sorted(u["name"] for u in users)


def owners(model, by):
    """everyone a todo the list holds is assigned to"""
    return sorted({t.assignee for t in model.todos if t.assignee})


FILTER = Lists(head=(ANYONE,), given=RECEIVED, derived=by_name, always=owners, entries=(in_order(), no_repeat()), picked=ANYONE)
FORM = Lists(head=(NOBODY,), given=RECEIVED, derived=by_name, entries=(in_order(), no_repeat()), picked=NOBODY)
EDIT = Lists(head=(NOBODY,), given=RECEIVED, derived=by_name, entries=(in_order(), no_repeat()))

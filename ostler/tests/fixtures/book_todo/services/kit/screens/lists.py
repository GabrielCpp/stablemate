from ostler.book import handed, request
from ostler.book.screen import Lists

from ...web.screens.labels import ANYONE, NOBODY


def by_name(users):
    """the users, by name"""
    return sorted(u["name"] for u in users)


def handed_by_name(data):
    """the users the page was handed, by name"""
    return by_name(data["users"])


HANDED = Lists(head=(NOBODY,), given=handed("/"), derived=handed_by_name)
FETCHED_USERS = request("GET", "/api/users")
FETCHED = Lists(head=(ANYONE,), given=FETCHED_USERS, derived=by_name)

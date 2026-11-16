"""The rules every entry of the todo list holds, whoever made the todo."""

from ostler.book.entries import has, no_repeat

HAS_ID = has("id")
HAS_TITLE = has("title")
ONCE = no_repeat("id")
TODOS = (HAS_ID, HAS_TITLE, ONCE)

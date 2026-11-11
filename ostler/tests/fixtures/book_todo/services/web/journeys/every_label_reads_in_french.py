from datetime import date

from ostler.book import Check, Journey

from ..fixtures import todo
from ..interactions import AddTodo


class EveryLabelReadsInFrench(Journey):
    """Opened in French, every control a reader can see carries its French label
    as its accessible name, on the list, the add form, the edit form and the
    remove dialog."""

    lang = "fr"

    def steps(self, today: date):
        plantes = todo("Arroser les plantes")
        yield AddTodo(plantes)
        yield Check("list and add form labels", lambda s: s.wrong_labels("fr"))
        yield Check("edit form labels", lambda s: s.wrong_labels_in_edit("fr", plantes))
        yield Check("remove dialog labels", lambda s: s.wrong_labels_in_remove("fr", plantes))

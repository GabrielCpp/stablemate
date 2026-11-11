from datetime import date

from ostler.book import Check, Journey, Listed

from ..fixtures import assigned
from ..interactions import AddTodo


class SaveTwiceMakesOneTodo(Journey):
    """Ana types a chore and, impatient, presses Save a second time while the
    first request is out. One todo lands, because Save is disabled while
    saving."""

    def steps(self, today: date):
        cat = assigned("ana", title="Feed the cat")
        yield AddTodo(cat)
        yield Check("Save is disabled while saving and the form is clear after",
                    lambda s: s.save_was_disabled_while_saving("Feed the cat again"))
        yield Listed(cat)

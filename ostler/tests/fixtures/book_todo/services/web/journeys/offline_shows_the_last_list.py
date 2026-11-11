from datetime import date

from ostler.book import Check, Given, Journey, Listed, Undo

from ..fixtures import Network, todo
from ..interactions import AddTodo, SetNetwork

OFFLINE = Given(SetNetwork(Network(offline=True)), undo=SetNetwork(Network(offline=False)))


class OfflineShowsTheLastList(Journey):
    """Ana adds two chores, then loses the network. The list she saw stays on
    screen with a banner, Save and Remove are off, and when the network returns
    the list is fresh again."""

    alone = True

    def steps(self, today: date):
        bike, chain = todo("Charge the bike"), todo("Oil the chain")
        yield AddTodo(bike)
        yield AddTodo(chain)
        yield OFFLINE
        yield Check("the offline banner is shown", lambda s: s.banner_shown())
        yield Listed(chain, bike)
        yield Check("Save is disabled", lambda s: s.disabled(s.add_save))
        yield Check("Remove is disabled", lambda s: s.disabled(s.remove, chain))
        yield Undo(OFFLINE)
        tyres = todo("Pump the tyres")
        yield AddTodo(tyres)
        yield Listed(tyres, chain, bike)

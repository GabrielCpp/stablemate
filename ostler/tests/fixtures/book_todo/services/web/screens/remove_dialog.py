from ostler.book import Phase, Screen, Stored, T, Transition, When, request
from ostler.book.screen import Button, Text

confirm = Button("remove-confirm", T("Yes, remove", "Oui, supprimer"), "DELETE /todos/{id}")
keep = Button("remove-cancel", T("Keep it", "Garder"), "closes without a request")
question = Text("remove-dialog", T("Remove this todo?", "Supprimer cette tâche ?"), does="role=dialog")

open_phase = Phase("open", shows=(question, confirm, keep))
removing = Phase("removing", disabled=(confirm, keep))


class RemoveDialog(Screen):
    api = "/todos"
    sends = (request("DELETE", "/todos"),)
    name = T("Remove this todo?", "Supprimer cette tâche ?")
    reached_from = "ListPage.row-remove"
    question = question
    confirm = confirm
    keep = keep
    stored = (Stored("removingId", "the row asked about", "the row's id"),)
    phases = (open_phase, removing)
    transitions = (
        Transition(open_phase, When("click", confirm), removing),
        Transition(removing, When("204"), open_phase, then="removingId = null; dialog closed; list refetched"),
        Transition(removing, When("4xx or 5xx"), open_phase, then="the error text is shown in the dialog"),
        Transition(open_phase, When("click", keep), open_phase, then="removingId = null; dialog closed"),
    )

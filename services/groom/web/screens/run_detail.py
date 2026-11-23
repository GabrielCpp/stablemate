from ostler.book import Field as Wire, Str, request
from ostler.book.screen import Button, Field, Screen, Text


class RunDetail(Screen):
    source = ("groom/groom/templates/dashboard.html", "groom/groom/assets/dashboard.js")
    route = "/"
    name = "Run detail"
    api = "/api"
    sends = (request("GET", "/api/run/{id}/overview"), request("GET", "/api/state"), request("GET", "/api/settings/attend"))
    root = Text("#detail .detail-head", does="the selected run's header: its state dot, repo and branch, id and state")
    repo = Text("#detail .repo-branch", "repo", does="the repo and branch of the run")
    run_id = Text("#detail .run-id", "run id", does="the whole id of the run")
    waiting = Text("#detail .gate-line b", "Waiting on you", does="the line over a gate the run waits on")
    gate_path = Text("#detail .gate-meta", "gate path", does="the gate file the run waits on")
    question = Text("#detail .question", "question", does="the question of the gate, rendered as markdown")
    answer = Field("#detail form.answer textarea", "Your answer", does="the text sent back to the run",
                   takes="answer", holds=Wire(Str(), required=False, nullable=True))
    send = Button("#detail form.answer button[type=submit]", "Send answer", does="sends the answer to the run's gate")
    close = Button("#detail .close-detail", "Close run detail", does="closes the run's detail pane")
    overview = Text("#tab-overview", "Overview", does="the tab of the run's cost and facts, refreshed in place when a span batch of the run commits")
    activity = Text("#tab-activity", "Activity", does="the tab of the run's turns")
    rejected = Text("#toasts", "toast", does="the notice shown when groom refuses the answer, with the reason groom gave")

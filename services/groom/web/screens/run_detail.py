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
    now = Text(
        "#detail .now",
        "Where the run is now",
        does="the strip above the Overview of a live run: the current node, how long the node has been open, the current turn, step or wait with the node's norm, agent idle and the last beat. Each length counts up every second in the browser with no reload. The norm reads 'a turn here usually takes' or 'this step usually takes'. Under five comparable runs it reads 'no norm yet: N comparable runs'. A wait on the operator reads 'Waiting on you' with 'no norm while waiting'",
    )
    past_norm = Text(
        "#detail .now .warn",
        "longer than usual",
        does="the words, beside the warning color, that mark a turn or step lasting longer than its node's norm",
    )
    overview = Text("#tab-overview", "Overview", does="the tab of the run's cost and facts, refreshed in place when a span batch of the run commits, with the strip of a live run above it")
    just_started = Text(
        "#tab-overview",
        "No finished work yet",
        does="the Overview of a run with no finished node: 'No finished work yet' and 'Figures appear when the first node finishes', with no tile and no problem count. The tiles take its place in the same pane, with no reload, once the first node finishes",
    )
    cost_tile = Text(
        "#detail-cost-tile",
        "Cost so far",
        does="the cost of the run. A live run reads 'as of the last finished turn' with its age, 'N of M turns priced' and the cost per active hour, which is the cost over the active time and is left out while the run has no active time. A backend that reports no cost reads '<backend> reports no cost' with 'est $X at list price' when groom can estimate; an ended run reads 'est $X' with 'estimate: this backend reports no cost'. An estimate never appears without that label",
    )
    active_tile = Text(
        "#detail-active-tile",
        "Active time",
        does="the active time of the run with its wall time and its session count beside it, as '<wall> wall, N sessions'. Wall time never appears without the active time. A session is a distinct resume generation, and a run never resumed has one",
    )
    items_tile = Text(
        "#detail-items-tile",
        "Work items",
        does="the items done out of the total. The cost divided by the finished items reads '$X per finished item', and a run with no finished item reads 'none finished yet' with no per-item figure. A run with no price reads 'no cost per item without a price'",
    )
    turns_tile = Text(
        "#detail-turns-tile",
        "Agent turns",
        does="the number of agent turns with 'N backend retries' beside it. The retries equal the sum of the Retries column of the flow tree",
    )
    attention_tile = Text(
        "#detail-attention-tile",
        "Attention",
        does="the gates of the run, the time spent waiting on them and the problem count. With any problems, the count is a button that opens the Activity tab with problems on. It counts failed steps, backend retries, failed gate checks and churn alerts, so it is never below the retries, and an answered gate does not count",
    )
    activity = Text("#tab-activity", "Activity", does="the tab of the run's turns")
    rejected = Text("#toasts .toast:has(.t-title:text(\"answer not taken\"))", "toast", does="the notice shown when groom refuses the answer, with the reason groom gave")

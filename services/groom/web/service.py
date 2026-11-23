"""groom's dashboard, as ostler loads it."""

from __future__ import annotations

from typing import cast

from ostler.book import App, Because, Endpoint, Environment, Service, Unseen

from .. import fixtures
from ..model.actions import AnswerFromPage
from ..model.state import Dashboard, DashboardOff
from ..stack import PORT, stack
from .health import TheDashboardShowsTheFleet
from .interactions import ALL as INTERACTIONS
from .interactions import AnswerTheGate
from .journeys import ALL as JOURNEYS
from .lifecycle import MATRICES
from .screens import ALL as SCREENS
from .surface import GroomDashboard

LOCAL = Environment("local", {"web": f"http://127.0.0.1:{PORT}"})

service = Service[Dashboard](
    name="web",
    environments={"local": LOCAL},
    default_environment="local",
    languages=("en",),
    new_model=DashboardOff,
    surface=GroomDashboard,
    journeys=JOURNEYS,
    health=(TheDashboardShowsTheFleet,),
    stack=stack,
    app=App(
        roots=("groom/groom/assets", "groom/groom/templates"),
        verified="VERIFIED",
        ignore=(
            "groom/groom/assets/README.md",
            "groom/groom/assets/*.css",
            "groom/groom/assets/*.png",
            "groom/groom/assets/diff2html.min.js",
            "groom/groom/assets/highlight.min.js",
            "groom/groom/assets/htm-preact.js",
            "groom/groom/assets/marked.min.js",
            "groom/groom/assets/purify.min.js",
        ),
    ),
    screens=SCREENS,
    interactions=INTERACTIONS,
    matrices=MATRICES,
    watch=(),
    unseen=(
        Unseen(cast(type[Endpoint], AnswerTheGate), "inputs", Because.NEVER_FILLED, "groom refuses every answer of a pushed run the same way, so no answer succeeds for an input class to vary"),
        Unseen(AnswerFromPage, Because.RUNTIME, "groom refuses every answer of a pushed run, so no play has the model accept the call"),
    ),
    words={**{i.__name__: i for i in INTERACTIONS}, **{name: getattr(fixtures, name) for name in fixtures.__all__}},
)

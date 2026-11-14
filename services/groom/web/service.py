"""groom's dashboard, as ostler loads it."""

from __future__ import annotations

from ostler.book import App, Environment, Service

from .. import fixtures
from ..model.state import Dashboard, DashboardOff
from ..stack import PORT, stack
from .health import TheDashboardShowsTheFleet
from .interactions import ALL as INTERACTIONS
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
    app=App(roots=("groom/groom",), verified="VERIFIED", ignore=()),
    screens=SCREENS,
    interactions=INTERACTIONS,
    matrices=MATRICES,
    watch=(),
    words={**{i.__name__: i for i in INTERACTIONS}, **{name: getattr(fixtures, name) for name in fixtures.__all__}},
)

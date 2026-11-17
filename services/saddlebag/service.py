"""saddlebag, as ostler loads it."""

from __future__ import annotations

from ostler.book import App, Because, Environment, Service, Stack, Unseen

from .commands import ALL as ENDPOINTS, Export, Fill, GuardBare, Look, TypeInto
from .journeys import ALL as JOURNEYS
from .model import SecretRecord, Store
from .model.files import FileRecord
from .model.lifecycle import MATRICES
from .surface import SaddlebagCli

LOCAL = Environment("local", {})

service = Service[Store](
    name="saddlebag",
    environments={"local": LOCAL},
    default_environment="local",
    new_model=Store,
    surface=SaddlebagCli,
    journeys=JOURNEYS,
    stack=lambda log_dir: Stack((), log_dir),
    endpoints=ENDPOINTS,
    matrices=MATRICES,
    watch=(Look(),),
    unseen=(
        Unseen(Fill, "inputs", Because.OUTSIDE,
               "a fill succeeds only against a Chromium listening on a DevTools port, which the book's sandbox does not start."),
        Unseen(TypeInto, "inputs", Because.OUTSIDE,
               "a type succeeds only on a ready Android device behind adb, and the sandbox's PATH holds no adb."),
        Unseen(Export, "inputs", Because.OUTSIDE,
               "an export succeeds only from a terminal a person answers, and the book runs every command with none."),
        Unseen(Fill, "0", Because.OUTSIDE, "a fill is typed into a page of a Chromium the sandbox does not start."),
        Unseen(TypeInto, "0", Because.OUTSIDE, "a type reaches a device behind adb, and the sandbox's PATH holds no adb."),
        Unseen(Export, "0", Because.OUTSIDE, "an export is written after a person confirms it at a terminal."),
        Unseen(Export, "1", Because.OUTSIDE, "an export that exists, is declined or finds the store down comes after the terminal check."),
        Unseen(GuardBare, "inputs", Because.RUNTIME, "a bare guard takes no input a run could vary."),
    ),
    records=(SecretRecord, FileRecord),
    app=App(roots=("saddlebag/saddlebag",), verified="VERIFIED",
            ignore=("saddlebag/saddlebag/__init__.py", "saddlebag/saddlebag/README.md", "saddlebag/saddlebag/_vendor/*", "saddlebag/saddlebag/lookup.py")),
)

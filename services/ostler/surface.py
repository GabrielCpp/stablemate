"""ostler run in a sandbox: the plan repository it starts from and the environment it sees."""

from __future__ import annotations

from ostler.book import CommandSurface, Environment, Seed

PREFIX = "TST"
EPIC_IDS = {
    "0001-first": "TST-01M585P778TKS9VRC0053BQDSZ",
    "0002-second": "TST-01M585PEGMRE3FWETV74QRSSY3",
    "0003-third": "TST-01M585PF6G57AQ3V1JZA5X8PKY",
}
TITLES = {"0001-first": "First epic", "0002-second": "Second epic", "0003-third": "Third epic"}
STORIES = {
    "0001-first": (("alpha", "TST-01M585P7WKBH9YJ8E6NA73W4S9"), ("bravo", "TST-01M585P8MYP5WJAMJ89Z981GEG")),
    "0002-second": (("sx", "TST-01M585PFWZZXH4Y6KNMH1VK58H"),),
    "0003-third": (),
}


def epic_page(name: str) -> str:
    stories = "".join(
        f"\n### {slug}\n- title: Story {slug}\n- id: {ident}\n- covers: (none)\n" for slug, ident in STORIES[name])
    return (f"---\ntype: epic\nid: {EPIC_IDS[name]}\ntitle: {TITLES[name]}\nstatus: planned\n---\n"
            f"# Epic: {TITLES[name]}\n\n## Seeds\n\n## Stories\n{stories}")


def story_page(slug: str, ident: str) -> str:
    return (f"---\ntype: story\nid: {ident}\nslug: {slug}\nstatus: Not started\n---\n# Story: Story {slug}\n\n"
            "## Dependencies\n\n(none)\n\n## Fixtures\n\n(none)\n\n## Context\n\n## Acceptance Criteria\n\n"
            "## Non-Functional Acceptance Criteria\n\n## Technical Notes\n\n## Implementation Status\n\n"
            "- **Status**: Not started\n")


def index_page(names: tuple[str, ...]) -> str:
    rows = "".join(f"- [{n}]({n}/epic.md) — {TITLES[n]}\n" for n in names)
    return f"# Epics\n\nThe ordered work queue for this repo (the OKF index of the epics bundle).\n\n{rows}"


def files() -> dict[str, str]:
    out = {"agents.yml": f"repo:\n  id_prefix: {PREFIX}\n", "home/.keep": ""}
    out["art/epics/index.md"] = index_page(("0001-first", "0002-second"))
    for name in EPIC_IDS:
        out[f"art/epics/{name}/epic.md"] = epic_page(name)
        for slug, ident in STORIES[name]:
            out[f"art/epics/{name}/stories/{slug}/story.md"] = story_page(slug, ident)
    return out


SEED = Seed(files(), name="plan")

ENVIRONMENT = {
    "HOME": "<sandbox>/home",
    "OSTLER_INDEX_DIR": "<sandbox>/index",
    "STABLEMATE_ARTIFACTS_DIR": "<sandbox>/art",
}


class OstlerCli(CommandSurface):
    def __init__(self, environment: Environment):
        super().__init__(SEED, ENVIRONMENT)

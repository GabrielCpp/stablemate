"""ostler run in a sandbox: the plan repository it starts from and the environment it sees."""

from __future__ import annotations

from ostler.book import CommandSurface, Environment, Seed

from .demo import FILES as DEMO_BOOK
from .fixtures import ALPHA, BRAVO, EPICS, FIRST, SECOND, SLUG_OF, SX, THIRD

PREFIX = "TST"
TITLES = {FIRST: "First epic", SECOND: "Second epic", THIRD: "Third epic"}
STORIES = {FIRST: (("alpha", ALPHA), ("bravo", BRAVO)), SECOND: (("sx", SX),), THIRD: ()}


def epic_page(eid: str) -> str:
    stories = "".join(
        f"\n### {slug}\n- title: Story {slug}\n- id: {ident}\n- covers: (none)\n" for slug, ident in STORIES[eid])
    return (f"---\ntype: epic\nid: {eid}\nslug: {SLUG_OF[eid]}\ntitle: {TITLES[eid]}\nstatus: planned\n---\n"
            f"# Epic: {TITLES[eid]}\n\n## Seeds\n\n## Stories\n{stories}")


def story_page(slug: str, ident: str) -> str:
    return (f"---\ntype: story\nid: {ident}\nslug: {slug}\nstatus: Not started\n---\n# Story: Story {slug}\n\n"
            "## Dependencies\n\n(none)\n\n## Fixtures\n\n(none)\n\n## Context\n\n## Acceptance Criteria\n\n"
            "## Non-Functional Acceptance Criteria\n\n## Technical Notes\n\n## Implementation Status\n\n"
            "- **Status**: Not started\n")


GOOD_PLAN = (
    "from ostler_qa import Qa, plan, scenario, target\n\nplan(run_id=\"RUN-1\", story=\"alpha\")\n\ncli = target(\"cli\")\n\n\n"
    "@scenario(target=cli, mechanism=\"fixture\", covers=[\"ac-1\"])\ndef adds_up(qa: Qa) -> None:\n    \"\"\"Arithmetic holds.\"\"\"\n"
    "    qa.check(\"one and one make two\", 1 + 1 == 2, actual=2, expected=2, covers=[\"ac-1\"])\n")
BAD_PLAN = (
    "import os\nfrom ostler_qa import Qa, plan, scenario, target\n\nplan(run_id=\"RUN-9\", story=\"alpha\")\n\ncli = target(\"cli\")\n\n\n"
    "@scenario(target=cli, mechanism=\"fixture\", covers=[\"ac-1\"])\ndef claims_nothing(qa: Qa) -> None:\n"
    "    \"\"\"Claims coverage with no check.\"\"\"\n    os.getcwd()\n")
BLOCKED_PLAN = (
    "from ostler_qa import Qa, plan, scenario, secret, target\n\nplan(run_id=\"RUN-{id}\", story=\"alpha\")\n\n"
    "{name} = target(\"{name}\", driver=\"{driver}\", {where})\n\nTOKEN = secret(\"token\", from_env=\"OSTLER_BOOK_NOT_SET\")\n\n\n"
    "@scenario(target={name}, mechanism=\"live\", covers=[\"ac-1\"])\ndef opens(qa: Qa) -> None:\n    \"\"\"The target opens.\"\"\"\n"
    "    qa.check(\"it opens\", True, covers=[\"ac-1\"])\n")
WEB_PLAN = BLOCKED_PLAN.format(id="W", name="web", driver="playwright", where='base_url="http://localhost:5173"')
PHONE_PLAN = BLOCKED_PLAN.format(id="P", name="phone", driver="maestro", where='app_id="com.acme.app"')
GRPC_PLAN = (
    "from ostler_qa import Qa, plan, scenario, target\n\nplan(run_id=\"RUN-G\", story=\"alpha\")\n\nrpc = target(\"rpc\")\n\n\n"
    "@scenario(target=rpc, mechanism=\"live\", covers=[\"ac-1\"])\ndef pings(qa: Qa) -> None:\n    \"\"\"The service answers a ping.\"\"\"\n"
    "    reply = qa.grpc.call(\"localhost:1\", \"acme.Service/Ping\", {})\n"
    "    qa.check(\"it answers\", reply.code == \"OK\", actual=reply.code, expected=\"OK\", covers=[\"ac-1\"])\n")
OLD_BACKLOG = "- [OLD-1] Tidy the thing\n- [OLD-2] Rename the other\n"


def files() -> dict[str, str]:
    out = {"agents.yml": f"repo:\n  id_prefix: {PREFIX}\nbook:\n  home: repo\n", "home/.keep": "",
           "unmoved/agents.yml": "repo:\n  id_prefix: U\n", "unmoved/services/old/service.py": "from ostler.book import Service\n", "plans/qa_plan.py": GOOD_PLAN,
           "plans/bad/qa_plan.py": BAD_PLAN, "plans/web/qa_plan.py": WEB_PLAN, "plans/phone/qa_plan.py": PHONE_PLAN,
           "plans/grpc/qa_plan.py": GRPC_PLAN, "vet/regions.json": "[]", "vet/manifest.json": "{}", "old-backlog.md": OLD_BACKLOG}
    out.update(DEMO_BOOK)
    for eid in EPICS:
        out[f"art/epics/{eid}/epic.md"] = epic_page(eid)
        for slug, ident in STORIES[eid]:
            out[f"art/epics/{eid}/stories/{ident}/story.md"] = story_page(slug, ident)
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

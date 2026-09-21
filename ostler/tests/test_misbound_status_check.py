"""`misbound-status-check` — a status-shaped check that document order bound to the wrong claim."""

from __future__ import annotations

from pathlib import Path

from ostler import doctor, registry
from ostler.model import load

from conftest import write


def all_codes(report):
    return {f.code for f in report.findings}


def _run(repo: Path):
    return doctor.run(load(repo))


def test_fires_on_the_globex_shape(repo: Path):
    write(repo / "docs/features/acme/http/api-service.md",
          "---\ntype: server\nslug: api-service\ntitle: API service\n---\n# API service\n\n"
          "## Endpoints\n\n### get-health\n"
          "- method: GET\n- path: /healthz\n"
          "- does: reports the process is up\n"
          "- status: 200\n- errors:\n- auth: none\n"
          '- verify: http_status(200, path="/healthz")\n'
          "- code: `app/api-service/service.go::Server.handleHealth`\n")
    report = _run(repo)
    hits = [f for f in report.findings if f.code == "misbound-status-check"]
    assert len(hits) == 1, report.findings
    hit = hits[0]
    assert hit.severity == "error"
    assert hit.fixable is True
    assert hit.ref == "docs/features/acme/http/api-service.md#get-health#verify:1"
    assert "200" in hit.message and "auth:1" in hit.message and "status:1" in hit.message
    assert hit.suggestion is not None
    assert "status:1" in hit.suggestion and "verify:" in hit.suggestion


def test_silent_when_the_check_is_correctly_bound_under_status(repo: Path):
    write(repo / "docs/features/acme/http/api-service.md",
          "---\ntype: server\nslug: api-service\ntitle: API service\n---\n# API service\n\n"
          "## Endpoints\n\n### get-health\n"
          "- method: GET\n- path: /healthz\n"
          "- does: reports the process is up\n"
          '- status: 200\n- verify: http_status(200, path="/healthz")\n'
          "- errors:\n- auth: none\n"
          "- code: `app/api-service/service.go::Server.handleHealth`\n")
    assert "misbound-status-check" not in all_codes(_run(repo))


def test_silent_when_the_code_appears_only_under_errors(repo: Path):
    write(repo / "docs/features/acme/http/claims-api.md",
          "---\ntype: server\nslug: claims-api\ntitle: Claims API\n---\n# Claims API\n\n"
          "## Endpoints\n\n### get-claim\n"
          "- method: GET\n- path: /claims/{id}\n"
          "- does: returns the claim record\n"
          "- status: 200\n"
          '- verify: http_status(200, path="/claims/{id}")\n'
          "- errors: 401 when the caller holds no session, same as an anonymous call\n"
          '- verify: http_status(401, path="/claims/{id}")\n'
          "- auth: any signed-in adjuster\n"
          "- code: `app/claims-api/service.go::Server.handleGetClaim`\n")
    assert "misbound-status-check" not in all_codes(_run(repo))


def test_silent_for_a_non_status_check(repo: Path):
    write(repo / "docs/features/acme/http/api-service.md",
          "---\ntype: server\nslug: api-service\ntitle: API service\n---\n# API service\n\n"
          "## Endpoints\n\n### get-health\n"
          "- method: GET\n- path: /healthz\n"
          "- does: reports the process is up\n"
          "- status: 200\n- errors:\n- auth: none\n"
          '- verify: visible(locator="#status", text="ok")\n'
          "- code: `app/api-service/service.go::Server.handleHealth`\n")
    assert "misbound-status-check" not in all_codes(_run(repo))


def test_fires_on_a_command_against_its_exits_bullet(repo: Path):
    write(repo / "docs/features/acme/shortener-cli.md",
          "---\ntype: cli\nslug: shortener\ntitle: Shortener\n---\n# Shortener\n\n"
          "- binary: `shortener`\n\n"
          "## Commands\n\n### create\n"
          "- usage: shortener create <url>\n"
          "- args: url — the URL to shorten\n"
          "- does: mints a short link for the given URL\n"
          "- exits: 0 on success\n"
          "- errors: prints \"invalid url\" when the argument does not parse\n"
          '- run: invoke(argv=["create", "https://example.com"])\n'
          "- verify: exit_status(code=0)\n"
          "- code: `shortener/cli.py::create`\n")
    report = _run(repo)
    hits = [f for f in report.findings if f.code == "misbound-status-check"]
    assert len(hits) == 1, report.findings
    assert hits[0].ref == "docs/features/acme/shortener-cli.md#create#verify:1"
    assert "exits:1" in hits[0].message


def test_a_command_claim_checked_with_no_run_bullet_to_bind_to_is_flagged(repo: Path):
    """`usage:`/`flags:`/`args:` describe every way to call the command, not the one concrete invocation a claim was checked against — so a checked claim with no `run:` at all compiles to nothing."""
    write(repo / "docs/features/acme/shortener-cli.md",
          "---\ntype: cli\nslug: shortener\ntitle: Shortener\n---\n# Shortener\n\n"
          "- binary: `shortener`\n\n"
          "## Commands\n\n### create\n"
          "- usage: shortener create <url>\n"
          "- args: url — the URL to shorten\n"
          "- does: mints a short link for the given URL\n"
          "- exits: 0 on success\n"
          "- verify: exit_status(code=0)\n"
          "- code: `shortener/cli.py::create`\n")
    report = _run(repo)
    hits = [f for f in report.findings if f.code == "unbound-command-claim"]
    assert len(hits) == 1, report.findings
    assert hits[0].ref == "docs/features/acme/shortener-cli.md#create#exits:1"


def test_silent_on_an_invocation_correctly_bound_under_status(repo: Path):
    write(repo / "docs/features/acme/cli/wh.md",
          "---\ntype: cli\nslug: wh\ntitle: WH\n---\n# WH\n\n"
          "## Invocations\n\n### run\n- on: [wh](#wh)\n- trigger: `wh run`\n"
          "- does:\n  - state: runs\n- code: `wh/run.py::run`\n"
          "- status: `0` on success\n- verify: exit_status(code=0)\n")
    assert "misbound-status-check" not in all_codes(_run(repo))


def test_one_finding_per_authored_bullet_when_the_first_verify_fans_out(repo: Path):
    """The `does: all` shape `post-widgets` shipped with: one `verify:` sits under a nested normative list with two children — so `attributed_checks` fans it out to both — and a second, correctly-bound `verify:` follows below, under its own `errors:` claim."""
    write(repo / "docs/features/acme/http/api-service.md",
          "---\ntype: server\nslug: api-service\ntitle: API service\n---\n# API service\n\n"
          "## Endpoints\n\n### post-widgets\n"
          "- method: POST\n- path: /api/widgets\n"
          "- does: all\n"
          "  - creates a widget from the given fields\n"
          "  - returns the created widget in the response body\n"
          '- verify: http_status(201, path="/api/widgets")\n'
          "- status: 201\n"
          "- errors: 422 with an error body when the input is invalid\n"
          '- verify: http_status(422, path="/api/widgets")\n'
          "- auth: none\n"
          "- code: `app/api-service/service.go::Server.handleCreate`\n")
    report = _run(repo)
    hits = [f for f in report.findings if f.code == "misbound-status-check"]
    assert len(hits) == 1, report.findings
    assert hits[0].ref == "docs/features/acme/http/api-service.md#post-widgets#verify:1"
    assert "201" in hits[0].message and "status:1" in hits[0].message


def test_indexed_engine_agrees_with_attributed_checks(repo: Path):
    """`attributed_check_bullets` is a second projection of the same walk `attributed_checks` runs, not a second binder — the two must never disagree about which values are bound to the node's own contract or to which claim, only about whether the authored index rides along."""
    write(repo / "docs/features/acme/http/api-service.md",
          "---\ntype: server\nslug: api-service\ntitle: API service\n---\n# API service\n\n"
          "## Endpoints\n\n### post-widgets\n"
          "- method: POST\n- path: /api/widgets\n"
          "- does: all\n"
          "  - creates a widget from the given fields\n"
          "  - returns the created widget in the response body\n"
          '- verify: http_status(201, path="/api/widgets")\n'
          "- status: 201\n"
          "- errors: 422 with an error body when the input is invalid\n"
          '- verify: http_status(422, path="/api/widgets")\n'
          "- auth: none\n"
          "- code: `app/api-service/service.go::Server.handleCreate`\n")
    book = load(repo)
    node = next(n for n in book.ui_nodes if n.id.endswith("#post-widgets"))

    contract, per_claim = registry.attributed_checks(node.type, node.bullet_order, node.combiners)
    indexed_contract, indexed_per_claim = registry.attributed_check_bullets(
        node.type, node.bullet_order, node.combiners)

    assert contract == [value for _, value in indexed_contract]
    assert set(per_claim) == set(indexed_per_claim)
    for claim in per_claim:
        assert per_claim[claim] == [value for _, value in indexed_per_claim[claim]]

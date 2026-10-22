from __future__ import annotations

API = "docs/services/acme/http/api.md"
FLOW = "docs/services/acme/flows/pay-a-bill.md"
FIXTURE = "docs/services/acme/fixtures/issued-bill.md"
RUNBOOK = "docs/services/acme/ops/qa-stack.md"

RUNBOOK_PAGE = """---
type: runbook
title: QA stack
---
# QA stack

- driver: http
- surfaces: [Bills API](../http/api.md)
- entry-url: http://localhost:18101
- health-path: /healthz
- stop: docker compose down -v
- working-directory: app

## Steps

### serve

- kind: service
- run: docker compose up -d --wait
- health: curl -fsS http://localhost:18099/healthz
"""

FIXTURE_PAGE = """---
type: fixture
title: Issued bill
---
# Issued bill

- provides:
  - bill_id — the id of an issued bill
    - from: [seed-it](#seed-it)
    - read: bill.id

## Steps

### seed-it
- kind: seed
- run: ./scripts/seed-bill.sh
"""

ENDPOINTS = """## Endpoints

### create-bill
- method: POST
- path: /bills
- arrange: no_body()
- status: 201 with the new bill
- capture: bill_id from $.id
- verify: http_status(code=201)

### get-bill
- method: GET
- path: /bills/{bill_id}
- verify: http_status(code=200)

### pay-bill
- method: POST
- path: /bills/{bill_id}/pay
- arrange: no_body()
- verify: http_status(code=200)
"""

ISSUED = """### Bill issued
- of: bill
- observe: [read the bill](#get-bill)
- verify: json_path(path="$.status", equals="issued")
"""

PAID = """### Bill paid
- of: bill
- observe: [read the bill](#get-bill)
- verify: json_path(path="$.status", equals="paid")
"""


def api_page(*, endpoints: str = ENDPOINTS, states: str = ISSUED + "\n" + PAID, pay_moves: str = "") -> str:
    endpoints = endpoints.replace("- path: /bills/{bill_id}/pay\n", f"- path: /bills/{{bill_id}}/pay\n{pay_moves}")
    section = f"\n## Data states\n\n{states}" if states else ""
    return f"""---
type: server
title: Bills API
---
# Bills API

- entry-url: http://localhost:18101

{endpoints}{section}"""


PAY_MOVES = "- moves: [Bill issued](#bill-issued) to [Bill paid](#bill-paid)\n"

FLOW_PAGE = """---
type: flow
title: Pay a bill
---
# Pay a bill

- start: [Bills API](../http/api.md)
- steps:
  - [create-bill](../http/api.md#create-bill)
  - [pay-bill](../http/api.md#pay-bill)
- end: [Bills API](../http/api.md)
"""

PAID_FIXTURE = "docs/services/acme/fixtures/paid-bill.md"

PAID_FIXTURE_PAGE = FIXTURE_PAGE.replace("title: Issued bill", "title: Paid bill").replace(
    "# Issued bill", "# Paid bill").replace("an issued bill", "a paid bill").replace(
    "seed-bill.sh", "seed-paid-bill.sh")

VOID = """### Bill void
- of: bill
- observe: [read the bill](#get-bill)
- verify: json_path(path="$.status", equals="void")
"""

VOID_ENDPOINT = """
### void-bill
- method: POST
- path: /bills/{bill_id}/void
- arrange: no_body()
- verify: http_status(code=200)
"""

ISSUED_ARRANGED = ISSUED + "- fixture: [issued-bill](../fixtures/issued-bill.md)\n"

PAID_ARRANGED = PAID + "- fixture: [paid-bill](../fixtures/paid-bill.md)\n"

VOID_FROM_ISSUED = "- moves: [Bill issued](#bill-issued) to [Bill void](#bill-void)\n"

VOID_FROM_PAID = "- moves: [Bill paid](#bill-paid) to [Bill void](#bill-void)\n"


def void_page(*, void_moves: str, states: str = ISSUED_ARRANGED + "\n" + PAID_ARRANGED + "\n" + VOID,
              pay_moves: str = "") -> str:
    void = VOID_ENDPOINT.replace("- path: /bills/{bill_id}/void\n", f"- path: /bills/{{bill_id}}/void\n{void_moves}")
    return api_page(endpoints=ENDPOINTS + void, states=states, pay_moves=pay_moves)


CLI = "docs/services/tally/tally.md"
CLI_FLOW = "docs/services/tally/flows/pay-a-bill.md"
CLI_PAY_MOVES = "- moves: [Bill issued](#issued) to [Bill paid](#paid)\n"

CLI_STATES = """## Data states

### issued
- of: bill
- observe: [show](#show)
- verify: json_path(path="$.status", equals="issued")

### paid
- of: bill
- observe: [show](#show)
- verify: json_path(path="$.status", equals="paid")
"""

CLI_INVOCATIONS = """
## Invocations

### pay-a-paid-bill
- on: [pay](#pay)
- trigger: the caller pays a bill that is already paid.
- when: [paid](#paid)
- run: invoke(argv=["pay"])
- verify: exit_status(code=0)
"""


def cli_page(*, pay_moves: str = CLI_PAY_MOVES, states: str = CLI_STATES, invocations: str = "") -> str:
    return f"""---
type: cli
title: Tally
---
# Tally

- binary: tally

## Commands

### add
- run: invoke(argv=["add"])
- verify: exit_status(code=0)

### pay
{pay_moves}- run: invoke(argv=["pay"])
- verify: exit_status(code=0)

### show
- run: invoke(argv=["show"])
- verify: exit_status(code=0)
{invocations}
{states}"""


def cli_flow_page(*steps: str) -> str:
    listed = "\n".join(f"  - [{step}](../tally.md#{step})" for step in steps)
    return f"""---
type: flow
title: Pay a bill
---
# Pay a bill

- start: [Tally](../tally.md)
- fixture: none, because nothing is arranged
- steps:
{listed}
- end: [Tally](../tally.md)
"""

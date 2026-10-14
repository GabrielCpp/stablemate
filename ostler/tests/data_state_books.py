from __future__ import annotations

API = "docs/features/acme/http/api.md"
FLOW = "docs/features/acme/flows/pay-a-bill.md"
FIXTURE = "docs/features/acme/fixtures/issued-bill.md"
RUNBOOK = "docs/features/acme/ops/qa-stack.md"

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

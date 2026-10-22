from __future__ import annotations

API = "docs/services/acme/http/orders.md"
FLOW = "docs/services/acme/flows/place-an-order.md"
QUOTA_FIXTURE = "docs/services/acme/fixtures/quota-used-up.md"

QUOTA_FIXTURE_PAGE = """---
type: fixture
title: Quota used up
---
# Quota used up

## Steps

### use-it-up
- kind: seed
- run: ./scripts/use-quota.sh
"""

ORDERS = """---
type: server
title: Orders API
---
# Orders API

- entry-url: http://localhost:18101

## Endpoints

### create-order
- method: POST
- path: /orders
- arrange: no_body()
- status: 201 with the new order
- verify: http_status(code=201)
{create_moves}
### read-quota
- method: GET
- path: /quota
- verify: http_status(code=200)

## Invocations

### over-quota
- on: [create-order](#create-order)
- trigger: an order arrives
- when: [Quota reached](#quota-reached)
- does: refuses the order
- arrange: no_body()
- status: 409
- verify: http_status(code=409)

## Data states

### Quota open
- of: quota
- observe: [read the quota](#read-quota)
- verify: json_path(path="$.remaining", equals="some")
- fixture: none, because a fresh account is open

### Quota reached
- of: quota
- observe: [read the quota](#read-quota)
- verify: json_path(path="$.remaining", equals="none")
- fixture: [quota-used-up](../fixtures/quota-used-up.md)
"""

REACHING_MOVES = "- moves: [Quota open](#quota-open) to [Quota reached](#quota-reached)\n"


def orders_page(create_moves: str = "") -> str:
    return ORDERS.replace("{create_moves}", create_moves)


def flow_page(steps: tuple[str, ...], fixture: str = "") -> str:
    rows = "".join(f"  - [{step}](../http/orders.md#{step})\n" for step in steps)
    return f"""---
type: flow
title: Place an order
---
# Place an order

- start: [Orders API](../http/orders.md)
- steps:
{rows}- end: [Orders API](../http/orders.md)
{fixture}"""

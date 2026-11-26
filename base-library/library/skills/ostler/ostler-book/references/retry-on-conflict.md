# Retry on a documented conflict

The client's `transport(method, url, headers, data)` is the one place a request leaves the book.
`Client` sends HTTP and `GrpcClient` sends gRPC, and both return `(status, body)`. A subclass
overrides `transport`, and the surface builds that subclass in its `__init__`, where it builds the
client today.

## gRPC

```python
import json

from ostler.book import Code, GrpcClient, GrpcSurface

RACED = "stale write, send again"
ATTEMPTS = 5


def raced(status, raw) -> bool:
    if status != Code.FAILED_PRECONDITION:
        return False
    try:
        return json.loads(raw).get("message") == RACED
    except ValueError:
        return False


class Retrying(GrpcClient):
    def transport(self, method, url, headers, data):
        status, raw = super().transport(method, url, headers, data)
        for _ in range(ATTEMPTS - 1):
            if not raced(status, raw):
                break
            status, raw = super().transport(method, url, headers, data)
        return status, raw


class OrderSurface(GrpcSurface):
    def __init__(self, environment):
        super().__init__(Retrying(environment.address("orders"), plaintext=True))
```

`GrpcClient` reports a refused call as `{"message": ...}`, so the message test reads that key.

## HTTP

The same loop over `Client`, with the signal the app documents. Here it is a 409 whose body names
the stale version.

```python
from ostler.book import Client, HttpSurface

STALE = b"stale version"
ATTEMPTS = 5


def raced(status, raw) -> bool:
    return status == 409 and STALE in raw


class Retrying(Client):
    def transport(self, method, url, headers, data):
        status, raw = super().transport(method, url, headers, data)
        for _ in range(ATTEMPTS - 1):
            if not raced(status, raw):
                break
            status, raw = super().transport(method, url, headers, data)
        return status, raw


class OrderSurface(HttpSurface):
    def __init__(self, environment):
        super().__init__(Retrying(environment.address("orders")))
```

`transport` sees the status and the body, never the response headers. A signal that lives only in
a header, such as `Retry-After`, is out of its reach. Report it under "what the format could not
express" and leave the call unretried.

class BookError(Exception):
    """The book contradicts itself or the call it builds: a path parameter with
    no value, a field the body does not declare. Never the app's fault."""


class Unhealthy(Exception):
    """The environment cannot be judged: a host does not answer, a gateway
    stands in for the app, or a health journey fails. Never the app's verdict."""

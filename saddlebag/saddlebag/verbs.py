"""The counter: every verb handler, over one store."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Any

from saddlebag import browser, totp
from saddlebag.models import VALUE_FIELDS, Secret, Tag, matches, parse_tag, validate_field, validate_name, validate_var
from saddlebag.protocol import Reply, Request
from saddlebag.store import SecretStore, StoreUnavailable

logger = logging.getLogger(__name__)

VAULT_TOKEN_FILE = Path("~/.vault-token")


class RequestError(Exception):
    """The request cannot be honoured. The message goes back to the caller."""


def _text(args: dict[str, Any], key: str, *, required: bool = True) -> str | None:
    value = args.get(key)
    if value is None:
        if required:
            raise RequestError(f"missing argument {key!r}")
        return None
    if not isinstance(value, str):
        raise RequestError(f"argument {key!r} must be a string")
    return value


def _required(args: dict[str, Any], key: str) -> str:
    value = _text(args, key)
    assert value is not None
    return value


def _tags(args: dict[str, Any], key: str = "tags") -> frozenset[Tag]:
    raw = args.get(key) or []
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise RequestError(f"argument {key!r} must be a list of key=value strings")
    try:
        return frozenset(parse_tag(item) for item in raw)
    except ValueError as exc:
        raise RequestError(str(exc)) from exc


def _checked[T](check: Callable[[str], T], value: str) -> T:
    try:
        return check(value)
    except ValueError as exc:
        raise RequestError(str(exc)) from exc


class Verbs:
    """The verb handlers over one store, used in-process or behind the daemon."""

    def __init__(self, store: SecretStore, browser_endpoint: str, route: str, token_source: str | None = None) -> None:
        self.store = store
        self.route = route
        self.browser_endpoint = browser_endpoint
        self.token_source = token_source

    def handle(self, request: Request) -> Reply:
        handler = getattr(self, f"verb_{request.verb}", None)
        if handler is None:
            return Reply(False, error=f"unknown verb {request.verb!r}")
        try:
            return Reply(True, handler(request.args))
        except RequestError as exc:
            return Reply(False, error=str(exc))
        except (browser.BrowserError, StoreUnavailable) as exc:
            return Reply(False, error=str(exc))
        except Exception as exc:
            logger.error("verb %s failed with %s", request.verb, type(exc).__name__)
            return Reply(False, error=f"{request.verb} failed inside the daemon: {type(exc).__name__}")

    def _existing(self, args: dict[str, Any]) -> Secret:
        name = _required(args, "name")
        secret = self.store.get(name)
        if secret is None:
            raise RequestError(f"no such secret: {name}")
        return secret

    def _matching(self, tags: frozenset[Tag]) -> list[Secret]:
        found = (self.store.get(name) for name in self.store.names())
        return [secret for secret in found if secret is not None and matches(secret.tags, tags)]

    def verb_ping(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"version": _pkg_version("stablemate-saddlebag")}

    def verb_list(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"secrets": [secret.to_dict() for secret in self._matching(_tags(args))]}

    def verb_tags(self, args: dict[str, Any]) -> dict[str, Any]:
        pairs = {pair for secret in self._matching(_tags(args)) for pair in secret.tags}
        return {"tags": [list(pair) for pair in sorted(pairs)]}

    def verb_create(self, args: dict[str, Any]) -> dict[str, Any]:
        name = _checked(validate_name, _required(args, "name"))
        if self.store.get(name) is not None:
            raise RequestError(f"secret {name} already exists")
        var = _text(args, "var", required=False)
        secret = Secret(
            name=name,
            username=_text(args, "username", required=False),
            description=_text(args, "description", required=False),
            var=_checked(validate_var, var) if var is not None else None,
            tags=_tags(args),
        )
        self.store.create(secret)
        return {"secret": secret.to_dict()}

    def verb_set(self, args: dict[str, Any]) -> dict[str, Any]:
        secret = self._existing(args)
        field = _checked(lambda f: validate_field(f, VALUE_FIELDS), _required(args, "field"))
        value = _required(args, "value")
        if not value:
            raise RequestError("the value is empty")
        if field == "totp":
            try:
                totp.decode_seed(value)
            except totp.SeedError as exc:
                raise RequestError(str(exc)) from exc
        self.store.set_value(secret.name, field, value)
        return {"name": secret.name, "field": field, "characters": len(value)}

    def verb_unset(self, args: dict[str, Any]) -> dict[str, Any]:
        secret = self._existing(args)
        field = _checked(lambda f: validate_field(f, VALUE_FIELDS), _required(args, "field"))
        self.store.unset_value(secret.name, field)
        return {"name": secret.name, "field": field}

    def verb_remove(self, args: dict[str, Any]) -> dict[str, Any]:
        secret = self._existing(args)
        self.store.remove(secret.name)
        return {"name": secret.name}

    def verb_tag(self, args: dict[str, Any]) -> dict[str, Any]:
        secret = self._existing(args)
        self.store.retag(secret.name, secret.tags | _tags(args))
        return {"name": secret.name}

    def verb_untag(self, args: dict[str, Any]) -> dict[str, Any]:
        secret = self._existing(args)
        self.store.retag(secret.name, secret.tags - _tags(args))
        return {"name": secret.name}

    def _value(self, secret: Secret, field: str) -> str:
        value = self.store.value(secret.name, field)
        if value is None:
            hint = f" Store one with: saddlebag secret set {secret.name} --field {field}" if field in VALUE_FIELDS else ""
            raise RequestError(f"{secret.name} has no {field}.{hint}")
        return value

    def verb_fill(self, args: dict[str, Any]) -> dict[str, Any]:
        secret = self._existing(args)
        field = _checked(validate_field, _required(args, "field"))
        selector = _required(args, "selector")
        value = self._value(secret, field)
        detail: dict[str, Any] = {}
        if field == "totp":
            minimum = args.get("min_seconds", 5)
            if not isinstance(minimum, int):
                raise RequestError("argument 'min_seconds' must be an integer")
            remaining = totp.seconds_remaining()
            if remaining < minimum:
                time.sleep(remaining)
                remaining = totp.seconds_remaining()
            try:
                value = totp.code(value)
            except totp.SeedError as exc:
                raise RequestError(f"{secret.name}: {exc}") from exc
            detail["valid_for_seconds"] = remaining
        endpoint = _text(args, "cdp", required=False) or self.browser_endpoint
        target = browser.select_target(browser.list_targets(endpoint), _text(args, "url_contains", required=False))
        session = browser.WebSocketSession(target.websocket_url)
        try:
            length = browser.fill(session, selector, value)
        finally:
            session.close()
        return {"name": secret.name, "field": field, "selector": selector, "characters": length, "url": target.url, **detail}

    def verb_env(self, args: dict[str, Any]) -> dict[str, Any]:
        tags = _tags(args)
        values: dict[str, str] = {}
        owners: dict[str, str] = {}
        if tags:
            matched = self._matching(tags)
            if not matched:
                raise RequestError("no secret carries all of those tags")
            for secret in matched:
                if secret.var is None:
                    raise RequestError(f"{secret.name} matches the tags but has no var to fill")
                if secret.var in owners:
                    raise RequestError(f"{owners[secret.var]} and {secret.name} both fill {secret.var}")
                owners[secret.var] = secret.name
                values[secret.var] = self._value(secret, "password")
        bindings = args.get("bindings") or []
        if not isinstance(bindings, list):
            raise RequestError("argument 'bindings' must be a list")
        for binding in bindings:
            if not isinstance(binding, dict):
                raise RequestError("each binding must be an object")
            var = _checked(validate_var, _required(binding, "var"))
            secret = self._existing(binding)
            field = _checked(validate_field, _text(binding, "field", required=False) or "password")
            values[var] = self._value(secret, field)
        return {"values": values}

    def verb_doctor(self, args: dict[str, Any]) -> dict[str, Any]:
        health = self.store.health()
        bare: list[str] = []
        if health.reachable:
            bare = [secret.name for secret in map(self.store.get, self.store.names()) if secret and not secret.fields]
        return {
            "backend": health.backend,
            "route": self.route,
            "version": _pkg_version("stablemate-saddlebag"),
            "store_reachable": health.reachable,
            "vault_authenticated": health.reachable,
            "secrets_without_value": bare,
            "missing_items": list(health.missing_items),
            "orphan_items": None if health.orphan_items is None else list(health.orphan_items),
            "token_source": self.token_source,
            "vault_token_file": VAULT_TOKEN_FILE.expanduser().exists(),
        }

"""One gRPC call, declared once and sent through the declaration.

A service writes one subclass of `Rpc` per unary call and names it once, as
`package.Service/Method`. The request message is the body. Every answer is a
status code by name with the shape that comes with it. A field is named as the
proto file names it, `team_id`, in a request and in an answer. On the wire a call is a
POST to `/package.Service/Method`, so a call has everything an endpoint has:
its input classes, its witness, the model action it carries.

The call goes out through `grpcurl`, which reads the service's own description
by reflection, so a book needs no generated code. A credential reaches grpcurl
through its environment, never its command line.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Callable, ClassVar, Mapping, cast

from ostler.book.errors import BookError, Unhealthy
from ostler.book.http import Answer, Auth, Client, Endpoint, Field, Int, List, Map, Object, Shape, Str
from ostler.book.httpsurface import HttpSurface
from ostler.book.status import Code, Status

STATUS = Object("Status", message=Field(Str()))
"""The body of every answer that is not OK: the message the service gave."""

VARIABLE = "BOOK_GRPC_H"
DOWN = ("Failed to dial target host", "connection refused", "context deadline exceeded", "failed to query for service descriptor")


def status_message(body: object) -> str:
    """The message of a gRPC status."""
    return str(cast("dict[str, object]", body).get("message", "")) if isinstance(body, dict) else str(body)


def json_name(field: str) -> str:
    """The name protobuf's JSON form gives a field: `team_id` is `teamId`."""
    head, *rest = field.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def proto_named(shape: Shape | None, value: object) -> object:
    """An answer as the proto file has it: every declared field under its proto
    name, and a 64-bit integer, which travels as text, as a number."""
    if isinstance(shape, Object) and isinstance(value, dict):
        back = {json_name(name): name for name in shape.fields}
        out: dict[str, object] = {}
        for key, item in cast("dict[str, object]", value).items():
            name = back.get(key, key)
            spec = shape.fields.get(name)
            out[name] = proto_named(spec.shape, item) if spec is not None else item
        return out
    if isinstance(shape, List) and isinstance(value, list):
        return [proto_named(shape.of, item) for item in cast("list[object]", value)]
    if isinstance(shape, Map) and isinstance(value, dict):
        return {key: proto_named(shape.of, item) for key, item in cast("dict[str, object]", value).items()}
    if isinstance(shape, Int) and isinstance(value, str) and value.removeprefix("-").isdigit():
        return int(value)
    return value


class Rpc(Endpoint, abstract=True):
    """Subclass per unary call. `rpc` names it; `body` is its request message."""

    rpc: ClassVar[str] = ""
    method: ClassVar[str] = "POST"
    unauthenticated: ClassVar[Status] = Code.UNAUTHENTICATED
    typed_wire: ClassVar[bool] = True

    def __init_subclass__(cls, abstract: bool = False) -> None:
        if abstract:
            return
        name = cls.__name__
        service, _, called = cls.rpc.partition("/")
        if not service or not called or "/" in called:
            raise BookError(f"{name}: rpc is written package.Service/Method, not {cls.rpc!r}")
        if cls.params.fields or cls.query is not None:
            raise BookError(f"{name}: a call carries every input in its request message, the body")
        named = [a.status for a in cls.answers if not isinstance(a.status, Code)]
        if named:
            raise BookError(f"{name}: a call answers a status code by name, such as Code.NOT_FOUND, not {named[0]!r}")
        cls.path = "/" + cls.rpc
        super().__init_subclass__()

    @classmethod
    def route(cls) -> str:
        return cls.rpc

    @classmethod
    def read(cls, answer: Answer, raw: bytes) -> object:
        return proto_named(answer.body, super().read(answer, raw))


class GrpcClient(Client):
    """Where each service listens, as `host:port`, and what each caller holds."""

    def __init__(self, base: str, credentials: Mapping[Auth, str] | None = None, timeout: float = 10,
                 message_of: Callable[[object], str] = status_message, hosts: Mapping[str, str] | None = None,
                 plaintext: bool = True, binary: str = "grpcurl"):
        super().__init__(base, credentials, timeout, message_of, hosts)
        self.plaintext = plaintext
        self.binary = binary

    def transport(self, method: str, url: str, headers: dict[str, str], data: bytes | None) -> tuple[Status, bytes]:
        target, _, symbol = url.partition("/")
        command = [self.binary, "-format", "json", "-emit-defaults", "-format-error", "-max-time", str(self.timeout)]
        if self.plaintext:
            command.append("-plaintext")
        environment = dict(os.environ)
        sent = {name: value for name, value in headers.items() if name.lower() != "content-type"}
        if sent:
            command.append("-expand-headers")
        for position, (name, value) in enumerate(sent.items()):
            environment[f"{VARIABLE}{position}"] = value
            command += ["-H", f"{name}: ${{{VARIABLE}{position}}}"]
        command += ["-d", "@", target, symbol]
        try:
            done = subprocess.run(command, input=data or b"{}", capture_output=True, env=environment,
                                  timeout=self.timeout + 5, check=False)
        except FileNotFoundError:
            raise BookError(f"{self.binary} is not on PATH; a gRPC call is sent through it") from None
        except subprocess.TimeoutExpired:
            raise Unhealthy(f"{symbol} at {target} did not answer in {self.timeout}s") from None
        if done.returncode == 0:
            answered = done.stdout.strip()
            return Code.OK, b"" if answered == b"{}" else answered
        said = done.stderr.decode(errors="replace").strip()
        status = _status(said)
        if status is not None:
            code, message = status
            return code, json.dumps({"message": message}).encode()
        if any(mark in said for mark in DOWN):
            raise Unhealthy(f"{symbol} at {target} did not answer: {said.splitlines()[-1] if said else 'no word from grpcurl'}")
        raise BookError(f"{symbol} could not be sent: {said or 'grpcurl gave no reason'}")


def _status(said: str) -> tuple[Code, str] | None:
    """The status grpcurl printed for a call the service turned away."""
    start = said.find("{")
    if start < 0:
        return None
    try:
        found = json.loads(said[start:])
    except ValueError:
        return None
    if not isinstance(found, dict) or not isinstance(found.get("code"), int):
        return None
    return Code.numbered(found["code"]), str(found.get("message", ""))


class GrpcSurface(HttpSurface):
    """Every step is a call sent as declared, and after it the watch reads are taken."""

    name = "grpc"

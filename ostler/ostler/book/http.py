"""One HTTP endpoint, declared once and called through the declaration.

A service writes one subclass per endpoint and gives it no method. The class
body is the whole contract: method, path, the credentials it accepts, the shape
of its path parameters, query and body, and every answer it may give with the
shape of that answer's body. `send` fills the path from the declaration, picks a
credential the client holds, serialises the call, and refuses to accept an
answer the declaration does not list or a body that does not fit the shape
declared for that status. That is the check an OpenAPI document promises and
never performs.
"""

from __future__ import annotations

from ostler.book import tree
from ostler.book.boundary import Passes, Reaches
from ostler.book.cast import KEEP, SOLE, Actor
from ostler.book.contracts import STREAMING
from ostler.book.domain import Action, Fixture, Heard, On
from ostler.book.entries import says
from ostler.book.errors import BookError, Unhealthy
from ostler.book.http_canon import (
    SET,
    Canon,
    Page,
    Unknown,
    _alone,
    _expr,
    _id_values,
    _known,
    _loose,
    _unknown,
    apart,
    breaches,
    canonical,
    learn_tokens,
    opaque_fields,
    states,
)
from ostler.book.http_endpoint import (
    _PARAM,
    GATEWAY,
    METHODS,
    Endpoint,
)
from ostler.book.http_fields import (
    _as_values,
    _id_fields,
    _prepared,
    bare_ids,
    identity_lines,
    named_shapes,
    token_fields,
)
from ostler.book.http_identities import (
    Identities,
    Reference,
    Reply,
    real_id,
    real_token,
    unknown_value,
    wired,
)
from ostler.book.http_objects import (
    DIMENSIONS,
    TWINS,
    Answer,
    ApiKey,
    Auth,
    Bearer,
    Field,
    List,
    Object,
    _list_twins,
    _num_twins,
    _real,
    _str_twins,
    _wire,
    _written_day,
    blind,
    error_field,
    problem,
    twins,
)
from ostler.book.http_paths import (
    VALUES_KEPT,
    Witness,
    declared_paths,
    domain_paths,
    has_domain,
    real_paths,
)
from ostler.book.http_shapes import (
    _CROCKFORD,
    FORMS,
    Bool,
    Bytes,
    Enum,
    Form,
    Id,
    Int,
    Itself,
    Map,
    Num,
    Shape,
    Str,
    Token,
    _ulid,
)
from ostler.book.http_transport import (
    Client,
    OffShape,
    Undeclared,
)
from ostler.book.model import attribute
from ostler.book.outcome import Refusal, Refusals
from ostler.book.signed import Signed
from ostler.book.status import Code, Status, refused, succeeded

__all__ = [
    "tree",
    "Passes",
    "Reaches",
    "KEEP",
    "SOLE",
    "Actor",
    "STREAMING",
    "Action",
    "Fixture",
    "Heard",
    "On",
    "says",
    "BookError",
    "Unhealthy",
    "attribute",
    "Refusal",
    "Refusals",
    "Signed",
    "Code",
    "Status",
    "refused",
    "succeeded",
    "Answer",
    "ApiKey",
    "Auth",
    "Bearer",
    "Bool",
    "Bytes",
    "Canon",
    "Client",
    "DIMENSIONS",
    "Endpoint",
    "Enum",
    "FORMS",
    "Field",
    "Form",
    "GATEWAY",
    "Id",
    "Identities",
    "Int",
    "Itself",
    "List",
    "METHODS",
    "Map",
    "Num",
    "Object",
    "OffShape",
    "Page",
    "Reference",
    "Reply",
    "SET",
    "Shape",
    "Str",
    "TWINS",
    "Token",
    "Undeclared",
    "Unknown",
    "VALUES_KEPT",
    "Witness",
    "_CROCKFORD",
    "_PARAM",
    "_alone",
    "_as_values",
    "_expr",
    "_id_fields",
    "_id_values",
    "_known",
    "_list_twins",
    "_loose",
    "_num_twins",
    "_prepared",
    "_real",
    "_str_twins",
    "_ulid",
    "_unknown",
    "_wire",
    "_written_day",
    "apart",
    "bare_ids",
    "blind",
    "breaches",
    "canonical",
    "declared_paths",
    "domain_paths",
    "error_field",
    "has_domain",
    "identity_lines",
    "learn_tokens",
    "named_shapes",
    "opaque_fields",
    "problem",
    "real_id",
    "real_paths",
    "real_token",
    "states",
    "token_fields",
    "twins",
    "unknown_value",
    "wired",
]

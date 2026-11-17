"""What a person types after `saddlebag`, as the model reads it. A field is named as the
argument is and left None where the person leaves the flag out."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Self

from ostler.book import Actor, Fixture

from .model import guard, words

ACME = "acme"
BETA = "beta"
ACME_VAR = "ACME_PW"
BETA_VAR = "BETA_PW"
ACME_PASSWORD = "hunter2hunter2"
BETA_PASSWORD = "short"
ACME_SEED = "JBSWY3DPEHPK3PXP"
NEW_SEED = "GEZDGNBVGY3TQOJQ"
DOTENV = "app.env"
EXPORT = "backup.saddlebag.json"
SELECTOR = "#user"
DEAD_BROWSER = "http://127.0.0.1:1"
DOTENV_KEYS = ("PORT", "LOG_LEVEL", "API_TOKEN", "ACME_PW", "STAGING_URL")


@dataclass
class VersionArgs(Fixture):
    pass


@dataclass
class ListArgs(Fixture):
    tag: list[str] | None = None
    json: bool | None = None

    @property
    def bad_tag(self) -> str:
        return repr(words.first_bad_tag(self.tag))


@dataclass
class TagsArgs(Fixture):
    tag: list[str] | None = None

    @property
    def bad_tag(self) -> str:
        return repr(words.first_bad_tag(self.tag))


@dataclass
class CreateArgs(Fixture):
    name: str | None = None
    username: str | None = None
    description: str | None = None
    var: str | None = None
    tag: list[str] | None = None
    meta: list[str] | None = None
    json: bool | None = None

    @property
    def bad_tag(self) -> str:
        return repr(words.first_bad_tag(self.tag))

    @property
    def bad_meta(self) -> str:
        return repr(words.first_bad_meta(self.meta))

    @property
    def bad_meta_key(self) -> str:
        bad = words.first_bad_meta(self.meta)
        return repr(bad.partition("=")[0].strip()) if bad is not None else ""

    @property
    def twice(self) -> str:
        return words.repeated_meta(self.meta) or ""

    @property
    def quoted_name(self) -> str:
        return repr(self.name)

    @property
    def quoted_var(self) -> str:
        return repr(self.var)

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[Self]:
        makes: tuple[dict[str, Any], ...] = (
            dict(name=ACME, username="ana", description="the acme login", var=ACME_VAR, tag=["env=ci", "team=a"],
                 meta=["realm=prod"]),
            dict(name=BETA, var=BETA_VAR, tag=["env=ci", "team=b"]),
        )
        return tuple(cls(**make) for make in makes if make["name"] not in state.secrets)


class Quotes:
    """What a command that names a field quotes back."""

    field: str | None

    @property
    def quoted_field(self) -> str:
        return repr(self.field)


@dataclass
class SetArgs(Quotes, Fixture):
    name: str | None = None
    field: str | None = None
    value: str | None = None

    @property
    def seed_fault(self) -> str:
        return words.seed_fault((self.value or "").rstrip("\r\n")) or ""

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[Self]:
        return tuple(cls(name=r.name, value=v, field=field)
                     for r in state.secrets for field, v in (("password", ACME_PASSWORD), ("totp", ACME_SEED)))


@dataclass
class UnsetArgs(Quotes, Fixture):
    name: str | None = None
    field: str | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[Self]:
        return tuple(cls(name=r.name, field=field) for r in state.secrets for field in r.fields)


@dataclass
class RemoveArgs(Fixture):
    name: str | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[Self]:
        return tuple(cls(name=r.name) for r in state.secrets)


@dataclass
class Pair(Fixture):
    name: str | None = None
    first: str | None = None
    second: str | None = None

    @property
    def given(self) -> list[str]:
        return [t for t in (self.first, self.second) if t is not None]


@dataclass
class TagArgs(Pair):
    @property
    def bad_tag(self) -> str:
        return repr(words.first_bad_tag(self.given))

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[Self]:
        return tuple(cls(name=r.name, first="stage=blue") for r in state.secrets)


@dataclass
class UntagArgs(TagArgs):
    pass


@dataclass
class MetaArgs(Pair):
    @property
    def bad_meta(self) -> str:
        return repr(words.first_bad_meta(self.given))

    @property
    def bad_meta_key(self) -> str:
        bad = words.first_bad_meta(self.given)
        return repr(bad.partition("=")[0].strip()) if bad is not None else ""

    @property
    def twice(self) -> str:
        return words.repeated_meta(self.given) or ""

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[Self]:
        return tuple(cls(name=r.name, first="region=eu") for r in state.secrets)


@dataclass
class UnmetaArgs(Fixture):
    name: str | None = None
    first: str | None = None
    second: str | None = None

    @property
    def given(self) -> list[str]:
        return [k for k in (self.first, self.second) if k is not None]

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[Self]:
        return tuple(cls(name=r.name, first=key) for r in state.secrets for key, _ in r.metadata)


class Reads:
    """What a command that reads one field of a secret quotes back."""

    field: str | None

    @property
    def named_field(self) -> str:
        return self.field or "password"

    @property
    def field_repr(self) -> str:
        return repr(self.named_field)

    @property
    def key(self) -> str:
        return self.named_field[5:]

    @property
    def key_repr(self) -> str:
        return repr(self.key)


@dataclass
class FillArgs(Reads, Fixture):
    name: str | None = None
    field: str | None = None
    selector: str | None = None
    url_contains: str | None = None
    cdp: str | None = None
    min_seconds: int | None = None
    json: bool | None = None

    @property
    def cdp_repr(self) -> str:
        return repr(self.cdp)


@dataclass
class TypeArgs(Reads, Fixture):
    name: str | None = None
    field: str | None = None
    device: str | None = None
    min_seconds: int | None = None
    json: bool | None = None


@dataclass
class ExecArgs(Fixture):
    tag: list[str] | None = None
    env: list[str] | None = None
    run: str | None = None
    show: str | None = None

    @property
    def bad_tag(self) -> str:
        return repr(words.first_bad_tag(self.tag))

    @property
    def bad_binding(self) -> str:
        return repr(next((e for e in self.env or () if words.binding_of(e) is None), None))

    @property
    def binding(self) -> tuple[str, str, str] | None:
        return words.binding_of(self.env[0]) if self.env else None

    @property
    def binding_var(self) -> str:
        return repr(self.binding[0]) if self.binding else ""

    @property
    def binding_name(self) -> str:
        return self.binding[1] if self.binding else ""

    @property
    def binding_field(self) -> str:
        return self.binding[2] if self.binding else ""

    @property
    def binding_field_repr(self) -> str:
        return repr(self.binding_field)

    @property
    def binding_key(self) -> str:
        return self.binding_field[5:]

    @property
    def binding_key_repr(self) -> str:
        return repr(self.binding_key)


@dataclass
class EnvArgs(Fixture):
    file: str | None = None


@dataclass
class EnvShowArgs(EnvArgs):
    pass


@dataclass
class EnvKeysArgs(EnvArgs):
    pass


@dataclass
class EnvClassifyArgs(Fixture):
    file: str | None = None
    json: bool | None = None


@dataclass
class EnvImportArgs(Fixture):
    file: str | None = None
    keys: str | None = None
    tag: list[str] | None = None
    prefix: str | None = None
    json: bool | None = None

    @property
    def listed(self) -> list[str]:
        return [k.strip() for k in (self.keys or "").split(",") if k.strip()]

    def named(self, key: str) -> str:
        return (self.prefix or "") + key.lower().replace("_", "-")

    @property
    def bad_tag(self) -> str:
        return repr(words.first_bad_tag(self.tag))

    @property
    def first_missing(self) -> str:
        return next((k for k in self.listed if k not in DOTENV_KEYS), "")

    @property
    def first_unnamed(self) -> str:
        return next((k for k in self.listed if words.NAME.fullmatch(self.named(k)) is None), "")

    @property
    def first_unnamed_name(self) -> str:
        return repr(self.named(self.first_unnamed)) if self.first_unnamed else ""

    @property
    def first_name(self) -> str:
        return self.named(self.listed[0]) if self.listed else ""

    @property
    def second_name(self) -> str:
        return self.named(self.listed[1]) if len(self.listed) > 1 else ""

    @property
    def first_var_repr(self) -> str:
        return repr(self.listed[0]) if self.listed else ""


@dataclass
class EnvSetArgs(Fixture):
    file: str | None = None
    key: str | None = None
    value: str | None = None

    @property
    def key_repr(self) -> str:
        return repr(self.key)


@dataclass
class ExportArgs(Fixture):
    file: str | None = None


@dataclass
class ImportArgs(Fixture):
    file: str | None = None
    replace: bool | None = None
    json: bool | None = None


@dataclass
class GuardHookArgs(Fixture):
    payload: str | None = None

    @property
    def reason(self) -> str:
        return guard.decide(self.payload or "") or ""


@dataclass
class GuardInstallArgs(Fixture):
    user: bool | None = None
    project: bool | None = None


@dataclass
class GuardBareArgs(Fixture):
    pass


@dataclass
class DoctorArgs(Fixture):
    json: bool | None = None


@dataclass
class ServeArgs(Fixture):
    socket: str | None = None
    vault_addr: str | None = None
    cdp: str | None = None
    keep_token: bool | None = None
    token: str | None = None


@dataclass
class LookArgs(Fixture):
    pass


def version() -> VersionArgs:
    return VersionArgs()


def list_(*, tag: list[str] | None = None, json: bool | None = None) -> ListArgs:
    return ListArgs(tag=tag, json=json)


def tags(*, tag: list[str] | None = None) -> TagsArgs:
    return TagsArgs(tag=tag)


def create(name: str | None = ACME, *, username: str | None = None, description: str | None = None,
           var: str | None = None, tag: list[str] | None = None, meta: list[str] | None = None,
           json: bool | None = None) -> CreateArgs:
    return CreateArgs(name=name, username=username, description=description, var=var, tag=tag, meta=meta, json=json)


def acme(*, json: bool | None = None) -> CreateArgs:
    return create(ACME, username="ana", description="the acme login", var=ACME_VAR, tag=["env=ci", "team=a"],
                  meta=["realm=prod"], json=json)


def beta() -> CreateArgs:
    return create(BETA, var=BETA_VAR, tag=["env=ci", "team=b"])


def set_value(name: str | None = ACME, value: str | None = ACME_PASSWORD, *, field: str | None = None) -> SetArgs:
    return SetArgs(name=name, field=field, value=value)


def set_seed(name: str | None = ACME, value: str | None = ACME_SEED) -> SetArgs:
    return SetArgs(name=name, field="totp", value=value)


def unset(name: str | None = ACME, field: str | None = "password") -> UnsetArgs:
    return UnsetArgs(name=name, field=field)


def remove(name: str | None = ACME) -> RemoveArgs:
    return RemoveArgs(name=name)


def tag(name: str | None = ACME, first: str | None = "stage=blue", second: str | None = None) -> TagArgs:
    return TagArgs(name=name, first=first, second=second)


def untag(name: str | None = ACME, first: str | None = "team=a", second: str | None = None) -> UntagArgs:
    return UntagArgs(name=name, first=first, second=second)


def meta(name: str | None = ACME, first: str | None = "region=eu", second: str | None = None) -> MetaArgs:
    return MetaArgs(name=name, first=first, second=second)


def unmeta(name: str | None = ACME, first: str | None = "realm", second: str | None = None) -> UnmetaArgs:
    return UnmetaArgs(name=name, first=first, second=second)


def fill(name: str | None = ACME, *, field: str | None = None, selector: str | None = SELECTOR,
         url_contains: str | None = None, cdp: str | None = DEAD_BROWSER, json: bool | None = None) -> FillArgs:
    return FillArgs(name=name, field=field, selector=selector, url_contains=url_contains, cdp=cdp, json=json)


def type_(name: str | None = ACME, *, field: str | None = None, device: str | None = None,
          json: bool | None = None) -> TypeArgs:
    return TypeArgs(name=name, field=field, device=device, json=json)


def run(show: str | None, *, tag: list[str] | None = None, env: list[str] | None = None,
        program: str | None = "printenv") -> ExecArgs:
    return ExecArgs(tag=tag, env=env, run=program, show=show)


def doctor(*, json: bool | None = None) -> DoctorArgs:
    return DoctorArgs(json=json)


def look() -> LookArgs:
    return LookArgs()


DENY_PAYLOAD = '{"tool_name": "Bash", "tool_input": {"command": "cat app.env"}}'
ALLOW_PAYLOAD = '{"tool_name": "Bash", "tool_input": {"command": "ls"}}'
EXAMPLE_PAYLOAD = '{"tool_name": "Read", "tool_input": {"file_path": ".env.example"}}'
KEY_PAYLOAD = '{"tool_name": "Read", "tool_input": {"file_path": "server.pem"}}'
EXPORT_PAYLOAD = '{"tool_name": "Read", "tool_input": {"file_path": "backup.saddlebag.json"}}'
EXEC_PAYLOAD = '{"tool_name": "Bash", "tool_input": {"command": "saddlebag exec --env X=acme -- cat app.env"}}'


def env_show(file: str | None = DOTENV) -> EnvShowArgs:
    return EnvShowArgs(file=file)


def env_keys(file: str | None = DOTENV) -> EnvKeysArgs:
    return EnvKeysArgs(file=file)


def env_classify(file: str | None = DOTENV, *, json: bool | None = None) -> EnvClassifyArgs:
    return EnvClassifyArgs(file=file, json=json)


def env_import(keys: str | None = "PORT,LOG_LEVEL", *, file: str | None = DOTENV, tag: list[str] | None = None,
               prefix: str | None = None, json: bool | None = None) -> EnvImportArgs:
    return EnvImportArgs(file=file, keys=keys, tag=tag, prefix=prefix, json=json)


def env_set(key: str | None = "PORT", value: str | None = "9090", *, file: str | None = DOTENV) -> EnvSetArgs:
    return EnvSetArgs(file=file, key=key, value=value)


def export(file: str | None = EXPORT) -> ExportArgs:
    return ExportArgs(file=file)


def import_(file: str | None = EXPORT, *, replace: bool | None = None, json: bool | None = None) -> ImportArgs:
    return ImportArgs(file=file, replace=replace, json=json)


def hook(payload: str | None = DENY_PAYLOAD) -> GuardHookArgs:
    return GuardHookArgs(payload=payload)


def install_guard(*, user: bool | None = None, project: bool | None = True) -> GuardInstallArgs:
    return GuardInstallArgs(user=user, project=project)


def serve(*, socket: str | None = None, vault_addr: str | None = None, keep_token: bool | None = None,
          token: str | None = None) -> ServeArgs:
    return ServeArgs(socket=socket, vault_addr=vault_addr, keep_token=keep_token, token=token)

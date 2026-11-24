"""Why saddlebag says no. The message is the one it prints after `saddlebag: `, word for word, with the sandbox
written `<sandbox>`. A rule reads the request (`a`) and the store (`s`)."""

from __future__ import annotations

from typing import Any

from ostler.book import Actor, Exited, Rule

from ..fixtures import (CreateArgs, DoctorArgs, EditArgs, EnvImportArgs, EnvSetArgs, ExecArgs, ExportArgs,
                        FillArgs, GuardInstallArgs, ImportArgs, ServeArgs, SetArgs, TypeArgs, UnmetaArgs, UnsetArgs)
from . import world, words
from .files import BACKEND_DAEMON, BROKEN, CONFIG, EXPORT, FOREIGN
from .state import Store

FAILED = Exited(1)
USAGE = Exited(2)

Request = Any


def daemon_chosen(s: Store) -> bool:
    return BACKEND_DAEMON in s.files[CONFIG].holds


def _no_daemon(a: Request, s: Store, by: Actor | None) -> bool:
    return daemon_chosen(s)


def _no_secret(a: Request, s: Store, by: Actor | None) -> bool:
    return a.name not in s.secrets


def _invalid_name(a: CreateArgs, s: Store, by: Actor | None) -> bool:
    return words.NAME.fullmatch(a.name or "") is None


def _exists(a: CreateArgs, s: Store, by: Actor | None) -> bool:
    return a.name in s.secrets


def _invalid_var(a: CreateArgs, s: Store, by: Actor | None) -> bool:
    return a.var is not None and words.VAR.fullmatch(a.var) is None


def _nothing_to_edit(a: EditArgs, s: Store, by: Actor | None) -> bool:
    return a.username is None and a.description is None and a.var is None


def _edit_invalid_var(a: EditArgs, s: Store, by: Actor | None) -> bool:
    return bool(a.var) and words.VAR.fullmatch(a.var or "") is None


def _bad_tag(a: Request, s: Store, by: Actor | None) -> bool:
    return words.first_bad_tag(getattr(a, "given", None) or getattr(a, "tag", None)) is not None


def _bad_meta_shape(a: Request, s: Store, by: Actor | None) -> bool:
    texts = getattr(a, "given", None) or getattr(a, "meta", None) or []
    bad = words.first_bad_meta(texts)
    return bad is not None and not words.split(bad)[0]


def _bad_meta_key(a: Request, s: Store, by: Actor | None) -> bool:
    texts = getattr(a, "given", None) or getattr(a, "meta", None) or []
    bad = words.first_bad_meta(texts)
    return bad is not None and words.split(bad)[0]


def _meta_twice(a: Request, s: Store, by: Actor | None) -> bool:
    return bool(words.repeated_meta(getattr(a, "given", None) or getattr(a, "meta", None)))


def _no_such_field_to_set(a: SetArgs, s: Store, by: Actor | None) -> bool:
    return a.field is not None and a.field not in ("password", "totp")


def _no_field_to_unset(a: UnsetArgs, s: Store, by: Actor | None) -> bool:
    return a.field is None


def _no_such_field_to_unset(a: UnsetArgs, s: Store, by: Actor | None) -> bool:
    return a.field is not None and a.field not in ("password", "totp")


def _empty_stdin(a: SetArgs, s: Store, by: Actor | None) -> bool:
    return not (a.value or "").rstrip("\r\n").strip()


def _bad_seed(a: SetArgs, s: Store, by: Actor | None) -> bool:
    return a.field == "totp" and words.seed_fault((a.value or "").rstrip("\r\n")) is not None


def _unmeta_invalid(position: str):
    def broken(a: UnmetaArgs, s: Store, by: Actor | None) -> bool:
        key = getattr(a, position)
        return key is not None and words.META_KEY.fullmatch(key) is None
    return broken


def _unmeta_lacking(position: str):
    def broken(a: UnmetaArgs, s: Store, by: Actor | None) -> bool:
        key = getattr(a, position)
        secret = s.secrets.get(a.name)
        return key is not None and secret is not None and key not in dict(secret.metadata)
    return broken


DAEMON = "no saddlebag daemon on <sandbox>/run/saddlebag.sock: start one with `saddlebag serve`"
META_KEY = "use letters, digits, '_' and '-', with no '.' or '='"
USAGE_SET = "usage: saddlebag secret set [-h] [--field {password,totp}] name\nsaddlebag secret set: error: "
USAGE_UNSET = "usage: saddlebag secret unset [-h] --field {password,totp} name\nsaddlebag secret unset: error: "

no_daemon = Rule[Request, Store](
    "saddlebag: " + DAEMON, _no_daemon, FAILED,
    why="a preference for the daemon sends every verb to its socket, and nothing listens there.")
no_secret = Rule[Request, Store]("saddlebag: no such secret: {name}", _no_secret, FAILED)

bad_tag = Rule[Request, Store]("saddlebag: invalid tag {bad_tag}: expected key=value", _bad_tag, USAGE)
bad_meta_shape = Rule[Request, Store]("saddlebag: invalid metadata {bad_meta}: expected key=value", _bad_meta_shape, USAGE)
bad_meta_key = Rule[Request, Store]("saddlebag: invalid metadata key {bad_meta_key}: " + META_KEY, _bad_meta_key, USAGE)
meta_twice = Rule[Request, Store]("saddlebag: metadata {twice} is given twice", _meta_twice, FAILED)

invalid_name = Rule[CreateArgs, Store](
    "saddlebag: invalid secret name {quoted_name}: use letters, digits, '.', '_' and '-'", _invalid_name, FAILED)
already_exists = Rule[CreateArgs, Store]("saddlebag: secret {name} already exists", _exists, FAILED)
invalid_var = Rule[CreateArgs, Store]("saddlebag: invalid environment variable name {quoted_var}", _invalid_var, FAILED)

nothing_to_edit = Rule[EditArgs, Store](
    "saddlebag: give at least one of --username, --description or --var", _nothing_to_edit, USAGE)
edit_invalid_var = Rule[EditArgs, Store]("saddlebag: invalid environment variable name {quoted_var}", _edit_invalid_var, FAILED)

no_such_field_to_set = Rule[SetArgs, Store](
    USAGE_SET + "argument --field: invalid choice: {quoted_field} (choose from 'password', 'totp')",
    _no_such_field_to_set, USAGE)
empty_stdin = Rule[SetArgs, Store]("saddlebag: stdin gave an empty value", _empty_stdin, USAGE)
bad_seed = Rule[SetArgs, Store]("saddlebag: {seed_fault}", _bad_seed, FAILED)
no_field_to_unset = Rule[UnsetArgs, Store](
    USAGE_UNSET + "the following arguments are required: --field", _no_field_to_unset, USAGE)
no_such_field_to_unset = Rule[UnsetArgs, Store](
    USAGE_UNSET + "argument --field: invalid choice: {quoted_field} (choose from 'password', 'totp')",
    _no_such_field_to_unset, USAGE)

invalid_first_key = Rule[UnmetaArgs, Store](
    "saddlebag: invalid metadata key '{first}': " + META_KEY, _unmeta_invalid("first"), FAILED)
lacking_first_key = Rule[UnmetaArgs, Store]("saddlebag: {name} has no metadata {first}", _unmeta_lacking("first"), FAILED)
invalid_second_key = Rule[UnmetaArgs, Store](
    "saddlebag: invalid metadata key '{second}': " + META_KEY, _unmeta_invalid("second"), FAILED)
lacking_second_key = Rule[UnmetaArgs, Store]("saddlebag: {name} has no metadata {second}", _unmeta_lacking("second"), FAILED)


def _some_secret_holds_no_value(a: DoctorArgs, s: Store, by: Actor | None) -> bool:
    return any(not r.fields for r in s.secrets)


unhealthy = Rule[DoctorArgs, Store](
    "", _some_secret_holds_no_value, FAILED,
    why="doctor prints its report on stdout and exits 1 while a secret holds no stored value, so stderr stays empty.")


NOT_A_FILE = "saddlebag: cannot read {file}: No such file or directory"
USAGE_FILL = ("usage: saddlebag fill [-h] [--field FIELD] --selector CSS\n"
              "                      [--url-contains TEXT] [--cdp URL] [--min-seconds N]\n"
              "                      [--json]\n                      name\n"
              "saddlebag fill: error: ")
LACKS = "saddlebag: {name} has no {named_field}. Store one with: saddlebag secret set {name} --field {named_field}"
UNKNOWN_FIELD = "saddlebag: unknown field {field_repr}: expected one of username, password, totp or meta.<key>"
LOOPBACK = ("saddlebag: refusing to send a secret to non-loopback CDP endpoint {cdp_repr}. A DevTools port grants full control "
            "of the browser and is never authenticated; saddlebag will only talk to one on this machine.")
NO_BROWSER = ("saddlebag: no browser answering at {cdp}: <urlopen error [Errno 111] Connection refused>. Start one with "
              "--remote-debugging-port, e.g. `chromium --remote-debugging-port=9222 --user-data-dir=/tmp/qa-profile`")
NO_ADB = "saddlebag: adb was not found. Put the Android platform-tools on PATH or set ANDROID_HOME where saddlebag runs."


def _field_unknown(field: str) -> bool:
    if field in ("username", "password", "totp"):
        return False
    return not (field.startswith("meta.") and words.META_KEY.fullmatch(field[5:]))


def _field_bad_meta(field: str) -> bool:
    return field.startswith("meta.") and words.META_KEY.fullmatch(field[5:]) is None


def _value_missing(s: Store, name: str, field: str) -> bool:
    secret = s.secrets.get(name)
    return secret is not None and secret.value(field) is None


def _fill_no_secret(a: Request, s: Store, by: Actor | None) -> bool:
    return a.name not in s.secrets


def _fill_field_unknown(a: Request, s: Store, by: Actor | None) -> bool:
    return _field_unknown(a.field or "password") and not _field_bad_meta(a.field or "password")


def _fill_field_bad_key(a: Request, s: Store, by: Actor | None) -> bool:
    return _field_bad_meta(a.field or "password")


def _no_selector(a: FillArgs, s: Store, by: Actor | None) -> bool:
    return a.selector is None


def _lacks_stored(a: Request, s: Store, by: Actor | None) -> bool:
    field = a.field or "password"
    return field in ("password", "totp") and _value_missing(s, a.name, field)


def _lacks_username(a: Request, s: Store, by: Actor | None) -> bool:
    return (a.field or "password") == "username" and _value_missing(s, a.name, "username")


def _lacks_meta(a: Request, s: Store, by: Actor | None) -> bool:
    field = a.field or "password"
    return field.startswith("meta.") and not _field_bad_meta(field) and _value_missing(s, a.name, field)


def _away_from_here(a: FillArgs, s: Store, by: Actor | None) -> bool:
    return a.cdp is not None and not a.cdp.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]"))


def _no_browser(a: FillArgs, s: Store, by: Actor | None) -> bool:
    return a.cdp is not None and not _away_from_here(a, s, by)


def _no_adb(a: TypeArgs, s: Store, by: Actor | None) -> bool:
    return True


fill_no_selector = Rule[FillArgs, Store](USAGE_FILL + "the following arguments are required: --selector", _no_selector, USAGE)
fill_field_unknown = Rule[Request, Store](UNKNOWN_FIELD, _fill_field_unknown, FAILED)
fill_field_bad_key = Rule[Request, Store](
    "saddlebag: invalid metadata key {key_repr}: " + META_KEY, _fill_field_bad_key, FAILED)
lacks_stored = Rule[Request, Store](LACKS, _lacks_stored, FAILED)
lacks_username = Rule[Request, Store]("saddlebag: {name} has no username.", _lacks_username, FAILED)
lacks_meta = Rule[Request, Store](
    "saddlebag: {name} has no {named_field}. Set one with: saddlebag secret meta {name} {key}=...", _lacks_meta, FAILED)
not_loopback = Rule[FillArgs, Store](LOOPBACK, _away_from_here, FAILED)
no_browser = Rule[FillArgs, Store](
    NO_BROWSER, _no_browser, FAILED,
    why="the book points fill at a loopback port nothing listens on, so it plays the refusal and never a fill.")
no_adb = Rule[TypeArgs, Store](
    NO_ADB, _no_adb, FAILED,
    why="the sandbox's PATH holds no adb, so type is refused after the secret and its value are checked.")


def _exec_no_command(a: ExecArgs, s: Store, by: Actor | None) -> bool:
    return a.run is None


def _exec_nothing_to_fill(a: ExecArgs, s: Store, by: Actor | None) -> bool:
    return not a.tag and not a.env


def _exec_bad_binding(a: ExecArgs, s: Store, by: Actor | None) -> bool:
    return any(words.binding_of(e) is None for e in a.env or ())


def _exec_bad_tag(a: ExecArgs, s: Store, by: Actor | None) -> bool:
    return words.first_bad_tag(a.tag) is not None


def _tagged(a: ExecArgs, s: Store):
    needs = {words.tag_of(t) for t in a.tag or ()}
    return [r for r in sorted(s.secrets, key=lambda r: r.name) if needs <= set(r.tags)] if needs else []


def _no_tagged(a: ExecArgs, s: Store, by: Actor | None) -> bool:
    return bool(a.tag) and not _tagged(a, s)


def _tagged_lacks(name: str):
    def broken(a: ExecArgs, s: Store, by: Actor | None) -> bool:
        first = next((r for r in _tagged(a, s) if r.password is None), None)
        return first is not None and first.name == name
    return broken


def _binding_var_bad(a: ExecArgs, s: Store, by: Actor | None) -> bool:
    return a.binding is not None and words.VAR.fullmatch(a.binding[0]) is None


def _binding_no_secret(a: ExecArgs, s: Store, by: Actor | None) -> bool:
    return a.binding is not None and a.binding[1] not in s.secrets


def _binding_field_unknown(a: ExecArgs, s: Store, by: Actor | None) -> bool:
    return a.binding is not None and _field_unknown(a.binding[2]) and not _field_bad_meta(a.binding[2])


def _binding_field_bad_key(a: ExecArgs, s: Store, by: Actor | None) -> bool:
    return a.binding is not None and _field_bad_meta(a.binding[2])


def _binding_lacks_stored(a: ExecArgs, s: Store, by: Actor | None) -> bool:
    return a.binding is not None and a.binding[2] in ("password", "totp") and _value_missing(s, a.binding[1], a.binding[2])


def _binding_lacks_username(a: ExecArgs, s: Store, by: Actor | None) -> bool:
    return a.binding is not None and a.binding[2] == "username" and _value_missing(s, a.binding[1], "username")


def _binding_lacks_meta(a: ExecArgs, s: Store, by: Actor | None) -> bool:
    return (a.binding is not None and a.binding[2].startswith("meta.") and not _field_bad_meta(a.binding[2])
            and _value_missing(s, a.binding[1], a.binding[2]))


def exec_values(a: ExecArgs, s: Store) -> dict[str, str]:
    """The variables exec hands the command: each tagged secret's password under its var, then each binding."""
    values: dict[str, str] = {}
    for secret in _tagged(a, s):
        if secret.var is not None and secret.password is not None:
            values[secret.var] = secret.password
    for text in a.env or ():
        var, name, field = words.binding_of(text) or ("", "", "")
        secret = s.secrets.get(name)
        found = secret.value(field) if secret is not None else None
        if found is not None:
            values[var] = found
    return values


def _cannot_run(a: ExecArgs, s: Store, by: Actor | None) -> bool:
    return a.run != "printenv"


def _nothing_to_show(a: ExecArgs, s: Store, by: Actor | None) -> bool:
    return a.show not in exec_values(a, s)


exec_no_command = Rule[ExecArgs, Store]("saddlebag: exec needs a command after --", _exec_no_command, USAGE)
exec_nothing_to_fill = Rule[ExecArgs, Store]("saddlebag: exec needs at least one --tag or --env", _exec_nothing_to_fill, USAGE)
exec_bad_binding = Rule[ExecArgs, Store](
    "saddlebag: invalid --env {bad_binding}: expected VAR=NAME or VAR=NAME[.field|.meta.key]", _exec_bad_binding, USAGE)
exec_bad_tag = Rule[ExecArgs, Store]("saddlebag: invalid tag {bad_tag}: expected key=value", _exec_bad_tag, USAGE)
no_tagged = Rule[ExecArgs, Store]("saddlebag: no secret carries all of those tags", _no_tagged, FAILED)
tagged_acme_lacks = Rule[ExecArgs, Store](
    "saddlebag: acme has no password. Store one with: saddlebag secret set acme --field password", _tagged_lacks("acme"), FAILED)
tagged_beta_lacks = Rule[ExecArgs, Store](
    "saddlebag: beta has no password. Store one with: saddlebag secret set beta --field password", _tagged_lacks("beta"), FAILED)
binding_var_bad = Rule[ExecArgs, Store]("saddlebag: invalid environment variable name {binding_var}", _binding_var_bad, FAILED)
binding_no_secret = Rule[ExecArgs, Store]("saddlebag: no such secret: {binding_name}", _binding_no_secret, FAILED)
binding_field_unknown = Rule[ExecArgs, Store](
    "saddlebag: unknown field {binding_field_repr}: expected one of username, password, totp or meta.<key>",
    _binding_field_unknown, FAILED)
binding_field_bad_key = Rule[ExecArgs, Store](
    "saddlebag: invalid metadata key {binding_key_repr}: " + META_KEY, _binding_field_bad_key, FAILED)
binding_lacks_stored = Rule[ExecArgs, Store](
    "saddlebag: {binding_name} has no {binding_field}. Store one with: saddlebag secret set {binding_name} --field {binding_field}",
    _binding_lacks_stored, FAILED)
binding_lacks_username = Rule[ExecArgs, Store]("saddlebag: {binding_name} has no username.", _binding_lacks_username, FAILED)
binding_lacks_meta = Rule[ExecArgs, Store](
    "saddlebag: {binding_name} has no {binding_field}. Set one with: saddlebag secret meta {binding_name} {binding_key}=...",
    _binding_lacks_meta, FAILED)
cannot_run = Rule[ExecArgs, Store](
    "saddlebag: cannot run {run}: No such file or directory", _cannot_run, Exited(127),
    why="the command is run after the secrets are resolved, so a missing program is the last thing exec reports.")
nothing_to_show = Rule[ExecArgs, Store](
    "", _nothing_to_show, FAILED,
    why="printenv exits 1 for a variable the command was not handed, and exec passes the child's exit code through.")


def _file_missing(a: Request, s: Store, by: Actor | None) -> bool:
    return a.file not in s.files


def _no_keys(a: EnvImportArgs, s: Store, by: Actor | None) -> bool:
    return not [k for k in (a.keys or "").split(",") if k.strip()]


def _keys_twice(a: EnvImportArgs, s: Store, by: Actor | None) -> bool:
    keys = [k.strip() for k in (a.keys or "").split(",") if k.strip()]
    return len(set(keys)) != len(keys)


def keys_of(a: EnvImportArgs) -> list[str]:
    return [k.strip() for k in (a.keys or "").split(",") if k.strip()]


def name_of(a: EnvImportArgs, key: str) -> str:
    return (a.prefix or "") + key.lower().replace("_", "-")


def _key_unnamed(a: EnvImportArgs, s: Store, by: Actor | None) -> bool:
    present = dict(world.entries(s, a.file or ""))
    return any(key in present and present[key] and words.NAME.fullmatch(name_of(a, key)) is None for key in keys_of(a))


def _tag_bad(a: EnvImportArgs, s: Store, by: Actor | None) -> bool:
    return words.first_bad_tag(a.tag) is not None


def _import_clash_first(a: EnvImportArgs, s: Store, by: Actor | None) -> bool:
    keys = keys_of(a)
    return bool(keys) and name_of(a, keys[0]) in s.secrets


def _import_clash_second(a: EnvImportArgs, s: Store, by: Actor | None) -> bool:
    keys = keys_of(a)
    return len(keys) > 1 and name_of(a, keys[1]) in s.secrets and not _import_clash_first(a, s, by)


def _var_unusable(a: EnvImportArgs, s: Store, by: Actor | None) -> bool:
    keys = keys_of(a)
    return bool(keys) and words.VAR.fullmatch(keys[0]) is None


env_no_file = Rule[Request, Store](NOT_A_FILE, _file_missing, FAILED)
import_no_keys = Rule[EnvImportArgs, Store]("saddlebag: --keys names no key", _no_keys, USAGE)
import_keys_twice = Rule[EnvImportArgs, Store]("saddlebag: --keys names a key twice", _keys_twice, USAGE)


def _import_key_absent(a: EnvImportArgs, s: Store, by: Actor | None) -> bool:
    present = dict(world.entries(s, a.file or ""))
    for key in keys_of(a):
        if key not in present:
            return True
        if not present[key]:
            return False
    return False


import_key_absent = Rule[EnvImportArgs, Store]("saddlebag: {file} has no {first_missing}", _import_key_absent, USAGE)
import_name_invalid = Rule[EnvImportArgs, Store](
    "saddlebag: {first_unnamed} does not make a valid secret name ({first_unnamed_name})", _key_unnamed, USAGE)
import_bad_tag = Rule[EnvImportArgs, Store]("saddlebag: invalid tag {bad_tag}: expected key=value", _tag_bad, USAGE)
import_clash_first = Rule[EnvImportArgs, Store]("saddlebag: secret {first_name} already exists", _import_clash_first, FAILED)
import_clash_second = Rule[EnvImportArgs, Store](
    "saddlebag: secret {second_name} already exists", _import_clash_second, FAILED,
    why="a key is stored before the next is created, so the keys ahead of the clash stay stored.")
import_var_invalid = Rule[EnvImportArgs, Store](
    "saddlebag: invalid environment variable name {first_var_repr}", _var_unusable, FAILED)


def _not_a_dotenv_key(a: EnvSetArgs, s: Store, by: Actor | None) -> bool:
    return words.VAR.fullmatch(a.key or "") is None


def _unwritable(a: EnvSetArgs, s: Store, by: Actor | None) -> bool:
    return words.quoted(a.value or "") is None


def _secret_by(rule: str):
    def broken(a: EnvSetArgs, s: Store, by: Actor | None) -> bool:
        pairs = [(k, v) for k, v in world.entries(s, a.file or "") if k == a.key] + [(a.key or "", a.value or "")]
        found = next((r for r in (world.verdict(s, k, v) for k, v in pairs) if r is not None), None)
        return found == rule
    return broken


SECRET_LITERAL = ("saddlebag: {key} is secret ({rule}); env set writes literals only. Store it with `saddlebag secret` "
                  "and run its consumer under `saddlebag exec --env {key}=NAME`, or ask the operator to edit {file}")
set_not_a_key = Rule[EnvSetArgs, Store]("saddlebag: {key_repr} is not a dotenv key", _not_a_dotenv_key, USAGE)
set_unwritable = Rule[EnvSetArgs, Store]("saddlebag: cannot write {key}: a value cannot span lines", _unwritable, USAGE)
set_secret = tuple(
    Rule[EnvSetArgs, Store](SECRET_LITERAL.replace("{rule}", rule), _secret_by(rule), USAGE)
    for rule in ("held-value", "registered-var", "key-name", "token-shape", "url-userinfo"))


def _export_suffix(a: ExportArgs, s: Store, by: Actor | None) -> bool:
    return not (a.file or "").endswith(".saddlebag.json")


def _export_needs_a_person(a: ExportArgs, s: Store, by: Actor | None) -> bool:
    return True


export_bad_suffix = Rule[ExportArgs, Store](
    "saddlebag: an export file's name ends in .saddlebag.json, so the guard keeps agents out of it: {file}",
    _export_suffix, USAGE)
export_needs_a_person = Rule[ExportArgs, Store](
    "saddlebag: export writes every secret in plaintext, so it runs only from a terminal a person answers",
    _export_needs_a_person, USAGE,
    why="the book runs every command with no terminal, so export is refused here and its success stays unplayed.")


def _import_unreadable(a: ImportArgs, s: Store, by: Actor | None) -> bool:
    return a.file not in s.files


def _import_broken(a: ImportArgs, s: Store, by: Actor | None) -> bool:
    return a.file == BROKEN


def _import_foreign(a: ImportArgs, s: Store, by: Actor | None) -> bool:
    return a.file == FOREIGN


def _import_clash(a: ImportArgs, s: Store, by: Actor | None) -> bool:
    return a.file == EXPORT and "imported" in s.secrets and not a.replace


import_unreadable = Rule[ImportArgs, Store](NOT_A_FILE, _import_unreadable, FAILED)
import_broken = Rule[ImportArgs, Store](
    "saddlebag: {file} is not JSON: Expecting property name enclosed in double quotes at line 2 column 1",
    _import_broken, USAGE)
import_foreign = Rule[ImportArgs, Store](
    'saddlebag: not a saddlebag export: the top-level object needs "format": "saddlebag-export"', _import_foreign, FAILED)
import_clash = Rule[ImportArgs, Store](
    "saddlebag: already in the store: imported. Pass --replace to overwrite them", _import_clash, FAILED)

USAGE_INSTALL = "usage: saddlebag guard install [-h] (--user | --project)\nsaddlebag guard install: error: "


def _install_both(a: GuardInstallArgs, s: Store, by: Actor | None) -> bool:
    return bool(a.user) and bool(a.project)


def _install_neither(a: GuardInstallArgs, s: Store, by: Actor | None) -> bool:
    return not a.user and not a.project


install_both = Rule[GuardInstallArgs, Store](
    USAGE_INSTALL + "argument --project: not allowed with argument --user", _install_both, USAGE)
install_neither = Rule[GuardInstallArgs, Store](
    USAGE_INSTALL + "one of the arguments --user --project is required", _install_neither, USAGE)


def _serve_no_address(a: ServeArgs, s: Store, by: Actor | None) -> bool:
    return not a.keep_token and not a.vault_addr


def _serve_no_token(a: ServeArgs, s: Store, by: Actor | None) -> bool:
    return not (a.token or "").strip()


serve_no_token_to_keep = Rule[ServeArgs, Store](
    "saddlebag: stdin gave an empty Vault token: pipe the token to `saddlebag serve`",
    lambda a, s, by: bool(a.keep_token) and _serve_no_token(a, s, by), USAGE)
serve_no_address = Rule[ServeArgs, Store](
    "saddlebag: no Vault address: set VAULT_ADDR or pass --vault-addr", _serve_no_address, USAGE)
serve_no_token = Rule[ServeArgs, Store](
    "saddlebag: stdin gave an empty Vault token: pipe the token to `saddlebag serve`", _serve_no_token, USAGE,
    why="serve reads the token from stdin first, and the book never pipes one in with an address, which would reach a Vault.")


guard_needs_a_choice = Rule[Request, Store]("saddlebag: guard needs --hook or the install subcommand", lambda a, s, by: True, USAGE)

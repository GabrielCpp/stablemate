"""What each command does to the store and what it prints."""

from __future__ import annotations

import json
from dataclasses import replace

from dataclasses import dataclass

from ostler.book import Action, Actor, Create, Delete, Show, Transaction, Update

from ..fixtures import (CreateArgs, DoctorArgs, EnvClassifyArgs, EnvImportArgs, EnvKeysArgs, EnvSetArgs, EnvShowArgs,
                        ExecArgs, ExportArgs, FillArgs, GuardBareArgs, GuardHookArgs, GuardInstallArgs, ImportArgs, ListArgs,
                        LookArgs, MetaArgs, RemoveArgs, ServeArgs, SetArgs, TagArgs, TagsArgs, TypeArgs, UnmetaArgs, UnsetArgs,
                        UntagArgs, VersionArgs)
from . import guard, rules, words, world
from .files import (BACKEND_DAEMON, BACKEND_KEYRING, CONFIG, EXISTING_SETTINGS, HOOK, PROJECT_SETTINGS,
                    USER_SETTINGS, VAULT_TOKEN, FileRecord)
from .records import SecretRecord
from .state import Store

VERSION = "2.1.0"


@dataclass(frozen=True)
class Shelf:
    """What `list --json` shows: every secret."""

    secrets: tuple[SecretRecord, ...]


def entry(secret: SecretRecord) -> dict[str, object]:
    return {
        "name": secret.name,
        "username": secret.username,
        "description": secret.description,
        "var": secret.var,
        "tags": [list(pair) for pair in secret.tags],
        "fields": secret.fields,
        "metadata": dict(sorted(secret.metadata)),
    }


def document(value: object) -> tuple[str, ...]:
    return tuple(json.dumps(value, indent=2).splitlines())


def table(rows: list[list[str]], header: list[str]) -> tuple[str, ...]:
    widths = [max(len(row[i]) for row in [header, *rows]) for i in range(len(header))]
    return tuple("  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()
                 for row in [header, *rows])


def matching(s: Store, wanted: list[str] | None) -> list[SecretRecord]:
    needs = {words.tag_of(t) for t in wanted or ()}
    return [secret for secret in sorted(s.secrets, key=lambda r: r.name) if needs <= set(secret.tags)]


def pairs(text: list[str] | None) -> set[tuple[str, str]]:
    return {pair for pair in (words.tag_of(t) for t in text or ()) if pair is not None}


class RunVersion(Action[VersionArgs, Store]):
    accept = VersionArgs

    @staticmethod
    def reduce(a: VersionArgs, s: Store, by: Actor | None) -> Transaction:
        return Transaction(says=(f"saddlebag {VERSION}",))


class RunList(Action[ListArgs, Store]):
    accept = ListArgs
    rules = (rules.bad_tag, rules.no_daemon)

    @staticmethod
    def reduce(a: ListArgs, s: Store, by: Actor | None) -> Transaction:
        found = matching(s, a.tag)
        if a.json:
            return Transaction(says=document({"secrets": [entry(r) for r in found]}))
        rows = [[r.name, r.username or "", r.var or "", ",".join(r.fields),
                 ",".join(f"{k}={v}" for k, v in r.tags),
                 ",".join(f"{k}={v}" for k, v in sorted(r.metadata)), r.description or ""] for r in found]
        return Transaction(says=table(rows, ["NAME", "USERNAME", "VAR", "VALUES", "TAGS", "METADATA", "DESCRIPTION"]))


class RunTags(Action[TagsArgs, Store]):
    accept = TagsArgs
    rules = (rules.bad_tag, rules.no_daemon)

    @staticmethod
    def reduce(a: TagsArgs, s: Store, by: Actor | None) -> Transaction:
        found = {pair for r in matching(s, a.tag) for pair in r.tags}
        return Transaction(says=tuple(f"{k}={v}" for k, v in sorted(found)))


class ListSecrets(Action[LookArgs, Store]):
    accept = LookArgs
    rules = (rules.no_daemon,)

    @staticmethod
    def reduce(a: LookArgs, s: Store, by: Actor | None) -> Show:
        return Show(Shelf(tuple(sorted(s.secrets, key=lambda r: r.name))))


class RunCreate(Action[CreateArgs, Store]):
    accept = CreateArgs
    rules = (rules.bad_tag, rules.bad_meta_shape, rules.bad_meta_key, rules.no_daemon, rules.invalid_name,
             rules.already_exists, rules.invalid_var, rules.meta_twice)

    @staticmethod
    def reduce(a: CreateArgs, s: Store, by: Actor | None) -> Transaction:
        assert a.name is not None
        record = SecretRecord(
            name=a.name, username=a.username, description=a.description, var=a.var,
            tags=tuple(sorted(pairs(a.tag))),
            metadata=tuple(sorted(p for p in (words.meta_of(t) for t in a.meta or ()) if p is not None)))
        says = document({"secret": entry(record)}) if a.json else (f"created {a.name}",)
        return Transaction(Create(s.secrets, record), says=says)


class RunSet(Action[SetArgs, Store]):
    accept = SetArgs
    rules = (rules.no_such_field_to_set, rules.empty_stdin, rules.no_daemon, rules.no_secret, rules.bad_seed)

    @staticmethod
    def reduce(a: SetArgs, s: Store, by: Actor | None) -> Transaction:
        value = (a.value or "").rstrip("\r\n")
        field = a.field or "password"
        record = replace(s.secrets[a.name], **{field: value})
        return Transaction(Update(s.secrets, a.name, record),
                           says=(f"stored {len(value)} characters as {a.name} {field}",))


class RunUnset(Action[UnsetArgs, Store]):
    accept = UnsetArgs
    rules = (rules.no_field_to_unset, rules.no_such_field_to_unset, rules.no_daemon, rules.no_secret)

    @staticmethod
    def reduce(a: UnsetArgs, s: Store, by: Actor | None) -> Transaction:
        record = replace(s.secrets[a.name], **{a.field or "": None})
        return Transaction(Update(s.secrets, a.name, record), says=(f"cleared {a.field} of {a.name}",))


class RunRemove(Action[RemoveArgs, Store]):
    accept = RemoveArgs
    rules = (rules.no_daemon, rules.no_secret)

    @staticmethod
    def reduce(a: RemoveArgs, s: Store, by: Actor | None) -> Transaction:
        return Transaction(Delete(s.secrets, a.name), says=(f"removed {a.name}",))


class RunTag(Action[TagArgs, Store]):
    accept = TagArgs
    rules = (rules.bad_tag, rules.no_daemon, rules.no_secret)

    @staticmethod
    def reduce(a: TagArgs, s: Store, by: Actor | None) -> Transaction:
        record = s.secrets[a.name]
        kept = tuple(sorted(set(record.tags) | pairs(a.given)))
        return Transaction(Update(s.secrets, a.name, replace(record, tags=kept)), says=(f"tagged {a.name}",))


class RunUntag(Action[UntagArgs, Store]):
    accept = UntagArgs
    rules = (rules.bad_tag, rules.no_daemon, rules.no_secret)

    @staticmethod
    def reduce(a: UntagArgs, s: Store, by: Actor | None) -> Transaction:
        record = s.secrets[a.name]
        kept = tuple(sorted(set(record.tags) - pairs(a.given)))
        return Transaction(Update(s.secrets, a.name, replace(record, tags=kept)), says=(f"untagged {a.name}",))


class RunMeta(Action[MetaArgs, Store]):
    accept = MetaArgs
    rules = (rules.bad_meta_shape, rules.bad_meta_key, rules.no_daemon, rules.no_secret, rules.meta_twice)

    @staticmethod
    def reduce(a: MetaArgs, s: Store, by: Actor | None) -> Transaction:
        record = s.secrets[a.name]
        merged = {**dict(record.metadata), **dict(p for p in (words.meta_of(t) for t in a.given) if p is not None)}
        return Transaction(Update(s.secrets, a.name, replace(record, metadata=tuple(sorted(merged.items())))),
                           says=(f"updated metadata of {a.name}",))


class RunUnmeta(Action[UnmetaArgs, Store]):
    accept = UnmetaArgs
    rules = (rules.no_daemon, rules.no_secret, rules.invalid_first_key, rules.lacking_first_key,
             rules.invalid_second_key, rules.lacking_second_key)

    @staticmethod
    def reduce(a: UnmetaArgs, s: Store, by: Actor | None) -> Transaction:
        record = s.secrets[a.name]
        left = tuple(p for p in record.metadata if p[0] not in a.given)
        return Transaction(Update(s.secrets, a.name, replace(record, metadata=left)),
                           says=(f"dropped metadata of {a.name}",))


class RunDoctor(Action[DoctorArgs, Store]):
    accept = DoctorArgs
    rules = (rules.no_daemon, rules.unhealthy)

    @staticmethod
    def reduce(a: DoctorArgs, s: Store, by: Actor | None) -> Transaction:
        bare = [r.name for r in sorted(s.secrets, key=lambda r: r.name) if not r.fields]
        configured = s.files[CONFIG].holds
        token = VAULT_TOKEN in s.files
        chosen = {BACKEND_KEYRING: "keyring"}.get(BACKEND_KEYRING if BACKEND_KEYRING in configured else "")
        if a.json:
            report = {
                "backend": "keyring", "route": "in-process", "version": VERSION, "store_reachable": True,
                "vault_authenticated": True, "secrets_without_value": bare, "missing_items": [], "orphan_items": [],
                "interpreter": None, "token_source": None, "vault_token_file": token,
                "preference": None if chosen is None else {"backend": chosen, "source": "<sandbox>/config.toml"},
            }
            return Transaction(says=document(report))
        lines = ["backend: keyring", "route: in-process",
                 "preference: none (auto)" if chosen is None else f"preference: {chosen} (<sandbox>/config.toml)",
                 "store reachable: yes", f"secrets without a stored value: {', '.join(bare) or 'none'}",
                 "orphan keyring items: none"]
        if token:
            lines.append("warning: ~/.vault-token exists; any process of this user can read it")
        return Transaction(says=tuple(lines))


class PreferDaemon(Action[object, Store]):
    @staticmethod
    def reduce(a: object, s: Store, by: Actor | None) -> Transaction:
        return Transaction(Update(s.files, CONFIG, FileRecord.holding(CONFIG, BACKEND_DAEMON)))


class PreferKeyring(Action[object, Store]):
    @staticmethod
    def reduce(a: object, s: Store, by: Actor | None) -> Transaction:
        return Transaction(Update(s.files, CONFIG, FileRecord.holding(CONFIG, BACKEND_KEYRING)))


class PutVaultToken(Action[object, Store]):
    @staticmethod
    def reduce(a: object, s: Store, by: Actor | None) -> Transaction:
        return Transaction(Create(s.files, FileRecord.holding(VAULT_TOKEN, "vault-token")))


class RunExec(Action[ExecArgs, Store]):
    accept = ExecArgs
    rules = (rules.exec_no_command, rules.exec_nothing_to_fill, rules.exec_bad_binding, rules.exec_bad_tag, rules.no_daemon,
             rules.no_tagged, rules.tagged_acme_lacks, rules.tagged_beta_lacks, rules.binding_var_bad,
             rules.binding_no_secret, rules.binding_field_unknown, rules.binding_field_bad_key, rules.binding_lacks_stored,
             rules.binding_lacks_username, rules.binding_lacks_meta, rules.cannot_run, rules.nothing_to_show)

    @staticmethod
    def reduce(a: ExecArgs, s: Store, by: Actor | None) -> Transaction:
        value = rules.exec_values(a, s)[a.show or ""]
        plain = False
        for text in a.env or ():
            var, _, field = words.binding_of(text) or ("", "", "")
            if var == a.show:
                plain = field == "username" or field.startswith("meta.")
        hidden = not plain and len(value) >= words.MIN_LENGTH
        return Transaction(says=("[REDACTED]" if hidden else value,))


def classified(s: Store, path: str) -> list[tuple[str, str, str | None]]:
    return [(key, value, world.verdict(s, key, value)) for key, value in world.entries(s, path)]


class RunEnvShow(Action[EnvShowArgs, Store]):
    accept = EnvShowArgs
    rules = (rules.env_no_file, rules.no_daemon)

    @staticmethod
    def reduce(a: EnvShowArgs, s: Store, by: Actor | None) -> Transaction:
        verdicts = {key: rule for key, _, rule in classified(s, a.file or "")}
        out: list[str] = []
        masked = 0
        for line in world.lines(s, a.file or ""):
            pair = words.key_of(line)
            if pair is not None and verdicts[pair[0]] is not None:
                masked += 1
                out.append(f"{pair[0]}=[REDACTED]")
            else:
                out.append(line)
        return Transaction(says=(*out, f"masked {masked} of {len(world.entries(s, a.file or ''))} values"))


class RunEnvKeys(Action[EnvKeysArgs, Store]):
    accept = EnvKeysArgs
    rules = (rules.env_no_file, rules.no_daemon)

    @staticmethod
    def reduce(a: EnvKeysArgs, s: Store, by: Actor | None) -> Transaction:
        return Transaction(says=tuple(f"{key}  (secret: {rule})" if rule else key for key, _, rule in classified(s, a.file or "")))


class RunEnvClassify(Action[EnvClassifyArgs, Store]):
    accept = EnvClassifyArgs
    rules = (rules.env_no_file, rules.no_daemon)

    @staticmethod
    def reduce(a: EnvClassifyArgs, s: Store, by: Actor | None) -> Transaction:
        found = classified(s, a.file or "")
        if a.json:
            return Transaction(says=document({"file": a.file, "verdicts": [
                {"key": key, "secret": rule is not None, "rule": rule} for key, _, rule in found]}))
        return Transaction(says=tuple(f"{key}\tsecret:{rule}" if rule else f"{key}\tliteral" for key, _, rule in found))


class RunEnvImport(Action[EnvImportArgs, Store]):
    accept = EnvImportArgs
    rules = (rules.import_no_keys, rules.import_keys_twice, rules.env_no_file, rules.import_key_absent,
             rules.import_name_invalid, rules.import_bad_tag, rules.no_daemon, rules.import_clash_first,
             rules.import_var_invalid, rules.import_clash_second)

    @staticmethod
    def reduce(a: EnvImportArgs, s: Store, by: Actor | None) -> Transaction:
        present = dict(world.entries(s, a.file or ""))
        tags = tuple(sorted(pairs(a.tag)))
        created = [SecretRecord(name=a.named(key), var=key, tags=tags, password=present[key]) for key in a.listed]
        if a.json:
            says = document({"file": a.file, "stored": [{"key": key, "name": a.named(key)} for key in a.listed]})
        else:
            says = tuple(f"stored {key} as {a.named(key)}" for key in a.listed)
        return Transaction(*(Create(s.secrets, record) for record in created), says=says)


class RunEnvSet(Action[EnvSetArgs, Store]):
    accept = EnvSetArgs
    rules = (rules.set_not_a_key, rules.set_unwritable, rules.env_no_file, rules.no_daemon, *rules.set_secret)

    @staticmethod
    def reduce(a: EnvSetArgs, s: Store, by: Actor | None) -> Transaction:
        written = f"{a.key}={words.quoted(a.value or '')}"
        current = world.lines(s, a.file or "")
        found = any((words.key_of(line) or ("",))[0] == a.key for line in current)
        updated = [written if (words.key_of(line) or ("",))[0] == a.key else line for line in current]
        if not found:
            updated.append(written)
        return Transaction(Update(s.files, a.file, FileRecord.holding(a.file or "", *updated)),
                           says=(f"{'set' if found else 'added'} {a.key} in {a.file}",))


class RunFill(Action[FillArgs, Store]):
    accept = FillArgs
    rules = (rules.fill_no_selector, rules.no_daemon, rules.no_secret, rules.fill_field_unknown, rules.fill_field_bad_key,
             rules.lacks_stored, rules.lacks_username, rules.lacks_meta, rules.not_loopback, rules.no_browser)

    @staticmethod
    def reduce(a: FillArgs, s: Store, by: Actor | None) -> Transaction:
        return Transaction(says=())


class RunType(Action[TypeArgs, Store]):
    accept = TypeArgs
    rules = (rules.no_daemon, rules.no_secret, rules.fill_field_unknown, rules.fill_field_bad_key, rules.lacks_stored,
             rules.lacks_username, rules.lacks_meta, rules.no_adb)

    @staticmethod
    def reduce(a: TypeArgs, s: Store, by: Actor | None) -> Transaction:
        return Transaction(says=())


class RunExport(Action[ExportArgs, Store]):
    accept = ExportArgs
    rules = (rules.export_bad_suffix, rules.export_needs_a_person)

    @staticmethod
    def reduce(a: ExportArgs, s: Store, by: Actor | None) -> Transaction:
        return Transaction(says=())


class RunImport(Action[ImportArgs, Store]):
    accept = ImportArgs
    rules = (rules.import_unreadable, rules.import_broken, rules.no_daemon, rules.import_foreign, rules.import_clash)

    @staticmethod
    def reduce(a: ImportArgs, s: Store, by: Actor | None) -> Transaction:
        record = SecretRecord(name="imported", var="IMPORTED_PW", tags=(("origin", "export"),), password="exported-secret")
        change = Update(s.secrets, "imported", record) if "imported" in s.secrets else Create(s.secrets, record)
        says = document({"file": a.file, "imported": ["imported"]}) if a.json else ("imported imported",)
        return Transaction(change, says=says)


class RunGuardHook(Action[GuardHookArgs, Store]):
    accept = GuardHookArgs

    @staticmethod
    def reduce(a: GuardHookArgs, s: Store, by: Actor | None) -> Transaction:
        reason = guard.decide(a.payload or "")
        if reason is None:
            return Transaction(says=())
        answer = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                         "permissionDecisionReason": reason}}
        return Transaction(says=(json.dumps(answer),))


class RunGuardInstall(Action[GuardInstallArgs, Store]):
    accept = GuardInstallArgs
    rules = (rules.install_both, rules.install_neither)

    @staticmethod
    def reduce(a: GuardInstallArgs, s: Store, by: Actor | None) -> Transaction:
        path = USER_SETTINGS if a.user else PROJECT_SETTINGS
        kept = s.files.get(path)
        record = FileRecord.holding(path, HOOK, *(kept.holds if kept is not None else ()))
        change = Update(s.files, path, record) if kept is not None else Create(s.files, record)
        return Transaction(change, says=(f"installed PreToolUse guard in <sandbox>/{path}",))


class RunGuardBare(Action[GuardBareArgs, Store]):
    accept = GuardBareArgs
    rules = (rules.guard_needs_a_choice,)

    @staticmethod
    def reduce(a: GuardBareArgs, s: Store, by: Actor | None) -> Transaction:
        return Transaction()


class RunServe(Action[ServeArgs, Store]):
    accept = ServeArgs
    rules = (rules.serve_no_token_to_keep, rules.serve_no_address, rules.serve_no_token)

    @staticmethod
    def reduce(a: ServeArgs, s: Store, by: Actor | None) -> Transaction:
        return Transaction(says=())


class LeaveSettings(Action[object, Store]):
    @staticmethod
    def reduce(a: object, s: Store, by: Actor | None) -> Transaction:
        return Transaction(Create(s.files, FileRecord.holding(PROJECT_SETTINGS, EXISTING_SETTINGS)))

"""The saddlebag commands the book plays: what a person types, and every way each one can end."""

from __future__ import annotations

from ostler.book import STDERR, Bool, Command, Exit, Field, Flag, Lines, Map, Object, Positional, Str, Switch
from ostler.book import List as Many

from .fixtures import ALLOW_PAYLOAD, EXPORT_PAYLOAD, KEY_PAYLOAD
from .model import actions as act

CLI = "saddlebag/saddlebag/cli.py"
VERBS = "saddlebag/saddlebag/verbs.py"
MODELS = "saddlebag/saddlebag/models.py"
ROUTE = "saddlebag/saddlebag/route.py"

UNREACHABLE = "the preference names the daemon and no daemon listens on its socket"


def text(does: str, **classes: str) -> Field:
    return Field(Str(classes={label.replace("_", " "): value for label, value in classes.items()}), required=False, does=does)


def tags(does: str = "K=V, repeatable") -> Field:
    return Field(Many(Str(classes={"a tag with no value": "env="})), required=False, does=does)


SECRET = Object(
    "Secret",
    name=Field(Str()), username=Field(Str(), nullable=True), description=Field(Str(), nullable=True),
    var=Field(Str(), nullable=True), tags=Field(Many(Many(Str())), reads="tag_pairs"), fields=Field(Many(Str())),
    metadata=Field(Map(Str()), reads="metadata_map"))
SECRETS = Object("Secrets", secrets=Field(Many(SECRET)))

JSON = Field(Bool(), required=False, does="print JSON in place of text")
NAME = text("the secret's name", a_name_with_a_space="two words")


class Version(Command):
    does = "Print the installed saddlebag version."
    program = "saddlebag"
    argv = ("--version",)
    args = Object("VersionArgs")
    answers = (Exit(0, Lines(), "saddlebag and the version number"),)
    carries = act.RunVersion
    source = (f"{CLI}::build_parser",)


class Inventory(Command):
    does = "List the secrets, or the ones that carry every tag given, with what each is for and which values it holds."
    program = "saddlebag"
    argv = ("list", Flag("--tag", "tag"), Switch("--json", "json"))
    args = Object("ListArgs", tag=tags("match secrets that carry every one of these tags"), json=JSON)
    answers = (
        Exit(0, Lines(), "a table of the secrets with their value fields, or their JSON"),
        Exit(1, STDERR, UNREACHABLE),
        Exit(2, STDERR, "a tag is not key=value"),
    )
    carries = act.RunList
    source = (f"{CLI}::cmd_list", f"{CLI}::_table", f"{CLI}::_pairs", f"{VERBS}::Verbs.verb_list",
              f"{VERBS}::Verbs._matching", f"{MODELS}::matches", "saddlebag/saddlebag/store.py::StoreUnavailable",
              "saddlebag/saddlebag/store.py::RouteError")


class Tags(Command):
    does = "List the distinct tags of the secrets that carry every tag given."
    program = "saddlebag"
    argv = ("tags", Flag("--tag", "tag"))
    args = Object("TagsArgs", tag=tags("restrict to the secrets that carry every one of these tags"))
    answers = (
        Exit(0, Lines(), "one key=value line per distinct tag, sorted"),
        Exit(1, STDERR, UNREACHABLE),
        Exit(2, STDERR, "a tag is not key=value"),
    )
    carries = act.RunTags
    source = (f"{CLI}::cmd_tags", f"{VERBS}::Verbs.verb_tags")


class Create(Command):
    does = "Create a secret with no value yet: its name, who it is for, the variable exec fills, its tags and metadata."
    program = "saddlebag"
    argv = ("secret", "create", Positional("name"), Flag("--username", "username"), Flag("--description", "description"),
            Flag("--var", "var"), Flag("--tag", "tag"), Flag("--meta", "meta"), Switch("--json", "json"))
    args = Object(
        "CreateArgs", name=NAME, username=text("the login name, printed in the clear", a_plain_name="ana", a_name_with_a_dot="ana.b"),
        description=text("what the secret is for", a_short_phrase="the acme login", a_phrase_with_a_comma="the login, for ci"),
        var=text("the variable exec fills with the password", a_name_with_a_dash="a-b"),
        tag=tags("K=V, repeatable"),
        meta=Field(Many(Str(classes={"a key with a dot": "a.b=1"})), required=False, does="printable K=V, repeatable"),
        json=JSON)
    answers = (
        Exit(0, Lines(), "created NAME, or the record as JSON"),
        Exit(1, STDERR, "the store cannot be reached, the name is not valid, the name is taken, the variable is not valid or a metadata key is given twice"),
        Exit(2, STDERR, "a tag or a metadata pair is not key=value"),
    )
    carries = act.RunCreate
    source = (f"{CLI}::cmd_create", f"{CLI}::_check_tags", f"{CLI}::_check_meta", f"{VERBS}::Verbs.verb_create",
              f"{MODELS}::validate_name", f"{MODELS}::validate_var", f"{MODELS}::parse_tag", f"{MODELS}::parse_meta",
              f"{MODELS}::validate_meta_key")


class Edit(Command):
    does = "Change a secret's username, description or variable after it was created. An empty value clears the field."
    program = "saddlebag"
    argv = ("secret", "edit", Positional("name"), Flag("--username", "username"), Flag("--description", "description"),
            Flag("--var", "var"), Switch("--json", "json"))
    args = Object(
        "EditArgs", name=NAME,
        username=text("the new login name, printed in the clear; empty clears it", a_plain_name="bo", nothing="",
                      a_name_with_a_dot="bo.c"),
        description=text("what the secret is for; empty clears it", a_short_phrase="the acme admin", nothing=""),
        var=text("the variable exec fills with the password; empty clears it", a_name_with_a_dash="a-b", nothing=""),
        json=JSON)
    answers = (
        Exit(0, Lines(), "edited NAME, or the record as JSON"),
        Exit(1, STDERR, "the store cannot be reached, no such secret, or the variable is not valid"),
        Exit(2, STDERR, "none of --username, --description or --var is given"),
    )
    carries = act.RunEdit
    source = (f"{CLI}::cmd_edit", f"{VERBS}::Verbs.verb_edit", f"{MODELS}::validate_var")


class SetValue(Command):
    does = "Store the value read from stdin as a secret's password or TOTP seed."
    program = "saddlebag"
    argv = ("secret", "set", Positional("name"), Flag("--field", "field"))
    stdin = "value"
    args = Object(
        "SetArgs", name=NAME,
        field=text("password or totp, password when left out", a_field_no_value_is_stored_in="username"),
        value=Field(Str(classes={"a plain value": "hunter2", "a value with a space": "two words"}), required=False, does="the value, read from stdin"))
    answers = (
        Exit(0, Lines(), "the number of characters stored"),
        Exit(1, STDERR, "the store cannot be reached, no such secret, or the seed is not base32"),
        Exit(2, STDERR, "the field is not one a value is stored in, or stdin gave an empty value"),
    )
    carries = act.RunSet
    source = (f"{CLI}::cmd_set", f"{VERBS}::Verbs.verb_set", "saddlebag/saddlebag/totp.py::decode_seed")


class Unset(Command):
    does = "Forget a stored password or TOTP seed."
    program = "saddlebag"
    argv = ("secret", "unset", Positional("name"), Flag("--field", "field"))
    args = Object("UnsetArgs", name=NAME, field=text("password or totp", a_field_no_value_is_stored_in="username"))
    answers = (
        Exit(0, Lines(), "cleared FIELD of NAME"),
        Exit(1, STDERR, "the store cannot be reached or no such secret"),
        Exit(2, STDERR, "the field is left out or is not one a value is stored in"),
    )
    carries = act.RunUnset
    source = (f"{CLI}::cmd_unset", f"{VERBS}::Verbs.verb_unset")


class Remove(Command):
    does = "Delete a secret and every value stored under it."
    program = "saddlebag"
    argv = ("secret", "remove", Positional("name"))
    args = Object("RemoveArgs", name=NAME)
    answers = (
        Exit(0, Lines(), "removed NAME"),
        Exit(1, STDERR, "the store cannot be reached or no such secret"),
    )
    carries = act.RunRemove
    source = (f"{CLI}::cmd_remove", f"{VERBS}::Verbs.verb_remove")


class TagSecret(Command):
    does = "Add tags to a secret."
    program = "saddlebag"
    argv = ("secret", "tag", Positional("name"), Positional("first"), Positional("second"))
    args = Object("TagArgs", name=NAME, first=text("a K=V tag", a_tag_with_no_value="env="),
                  second=text("another K=V tag", a_tag="team=b", a_tag_with_a_dash="tier-x=2"))
    answers = (
        Exit(0, Lines(), "tagged NAME"),
        Exit(1, STDERR, "the store cannot be reached or no such secret"),
        Exit(2, STDERR, "a tag is not key=value"),
    )
    carries = act.RunTag
    source = (f"{CLI}::cmd_tag", f"{VERBS}::Verbs.verb_tag")


class UntagSecret(Command):
    does = "Remove tags from a secret."
    program = "saddlebag"
    argv = ("secret", "untag", Positional("name"), Positional("first"), Positional("second"))
    args = Object("UntagArgs", name=NAME, first=text("a K=V tag", a_tag_with_no_value="env="),
                  second=text("another K=V tag", a_tag="team=b", a_tag_with_a_dash="tier-x=2"))
    answers = (
        Exit(0, Lines(), "untagged NAME"),
        Exit(1, STDERR, "the store cannot be reached or no such secret"),
        Exit(2, STDERR, "a tag is not key=value"),
    )
    carries = act.RunUntag
    source = (f"{CLI}::cmd_tag", f"{VERBS}::Verbs.verb_untag")


class Meta(Command):
    does = "Add or overwrite printable metadata of a secret."
    program = "saddlebag"
    argv = ("secret", "meta", Positional("name"), Positional("first"), Positional("second"))
    args = Object("MetaArgs", name=NAME, first=text("a K=V pair", a_key_with_a_dot="a.b=1", a_pair_with_no_value="region="),
                  second=text("another K=V pair", a_pair="tier=2", a_pair_with_a_dash="data-class=pii"))
    answers = (
        Exit(0, Lines(), "updated metadata of NAME"),
        Exit(1, STDERR, "the store cannot be reached, no such secret, or a key is given twice"),
        Exit(2, STDERR, "a pair is not key=value"),
    )
    carries = act.RunMeta
    source = (f"{CLI}::cmd_meta", f"{VERBS}::Verbs.verb_meta", f"{VERBS}::_metadata")


class Unmeta(Command):
    does = "Drop metadata keys of a secret."
    program = "saddlebag"
    argv = ("secret", "unmeta", Positional("name"), Positional("first"), Positional("second"))
    args = Object("UnmetaArgs", name=NAME, first=text("a metadata key", a_key_the_secret_lacks="nonesuch"),
                  second=text("another metadata key", a_key="region", a_key_with_a_dash="data-class"))
    answers = (
        Exit(0, Lines(), "dropped metadata of NAME"),
        Exit(1, STDERR, "the store cannot be reached, no such secret, a key is not valid or the secret lacks it"),
    )
    carries = act.RunUnmeta
    source = (f"{CLI}::cmd_unmeta", f"{VERBS}::Verbs.verb_unmeta")


class Doctor(Command):
    does = "Report the route, the store and the secrets that hold no value."
    program = "saddlebag"
    argv = ("doctor", Switch("--json", "json"))
    args = Object("DoctorArgs", json=JSON)
    answers = (
        Exit(0, Lines(), "the report, and every secret holds a value"),
        Exit(1, STDERR, "a secret holds no value, the report then on stdout, or the store cannot be reached"),
    )
    carries = act.RunDoctor
    source = (f"{CLI}::cmd_doctor", f"{VERBS}::Verbs.verb_doctor", "saddlebag/saddlebag/preference.py",
              "saddlebag/saddlebag/keyring_store.py::KeyringStore.health")


class Look(Command):
    does = "List the secrets as JSON, as the watch reads them after every step."
    program = "saddlebag"
    argv = ("list", "--json")
    args = Object("LookArgs")
    answers = (Exit(0, SECRETS, "the secrets as JSON"), Exit(1, STDERR, UNREACHABLE))
    carries = act.ListSecrets
    source = (f"{CLI}::cmd_list",)


class Fill(Command):
    does = "Type a stored value into a field of an open browser page over the DevTools protocol."
    program = "saddlebag"
    argv = ("fill", Positional("name"), Flag("--field", "field"), Flag("--selector", "selector"),
            Flag("--url-contains", "url_contains"), Flag("--cdp", "cdp"), Switch("--json", "json"))
    args = Object(
        "FillArgs", name=NAME,
        field=text("username, password, totp or meta.KEY, password when left out", a_field_the_secret_lacks="meta.realm"),
        selector=text("the CSS selector of the input", an_id_selector="#user", a_class_selector=".login"),
        url_contains=text("which open page, by a part of its URL", a_host="example.com", a_path="/login"),
        cdp=text("the DevTools endpoint, loopback only", a_browser_on_another_host="http://example.com:9222"),
        json=JSON)
    answers = (
        Exit(0, Lines(), "the number of characters typed, the selector and the page's URL"),
        Exit(1, STDERR, "the store cannot be reached, no such secret, the field is unknown or holds nothing, or the browser is not reachable"),
        Exit(2, STDERR, "the selector is left out"),
    )
    carries = act.RunFill
    source = (f"{CLI}::cmd_fill", f"{VERBS}::Verbs.verb_fill", f"{VERBS}::Verbs._typable", f"{VERBS}::Verbs._value",
              "saddlebag/saddlebag/browser.py", "saddlebag/saddlebag/totp.py::code", "saddlebag/saddlebag/totp.py::seconds_remaining")


class TypeInto(Command):
    does = "Type a stored value into the focused field of an Android device over adb."
    program = "saddlebag"
    argv = ("type", Positional("name"), Flag("--field", "field"), Flag("--device", "device"), Switch("--json", "json"))
    args = Object(
        "TypeArgs", name=NAME,
        field=text("username, password, totp or meta.KEY, password when left out", a_field_the_secret_lacks="meta.realm"),
        device=text("the adb serial", a_serial="emulator-5554", another_serial="R5CT1234"), json=JSON)
    answers = (
        Exit(0, Lines(), "the number of characters typed, the field and the device"),
        Exit(1, STDERR, "the store cannot be reached, no such secret, the field holds nothing, or adb or the device is not usable"),
    )
    carries = act.RunType
    source = (f"{CLI}::cmd_type", f"{VERBS}::Verbs.verb_type", "saddlebag/saddlebag/device.py")


class Exec(Command):
    does = "Run a command with secrets in its environment and mask their values in what it prints."
    program = "saddlebag"
    argv = ("exec", Flag("--tag", "tag"), Flag("--env", "env"), "--", Positional("run"), Positional("show"))
    args = Object(
        "ExecArgs", tag=tags("fill the var of every secret that carries every one of these tags"),
        env=Field(Many(Str(classes={"a binding with no variable": "=acme"})), required=False, does="VAR=NAME[.field|.meta.KEY], repeatable"),
        run=text("the program to run", a_program_that_does_not_exist="no-such-tool"),
        show=Field(Str(classes={"the variable a secret fills": "ACME_PW"}), required=False, does="the variable printenv prints"))
    answers = (
        Exit(0, Lines(), "what the command printed, a stored value masked"),
        Exit(1, STDERR, "the store cannot be reached, a secret or its value is missing, or the command itself exited 1"),
        Exit(2, STDERR, "no command, nothing to fill, or a malformed binding or tag"),
        Exit(127, STDERR, "the program does not exist"),
    )
    carries = act.RunExec
    source = (f"{CLI}::cmd_exec", f"{CLI}::_binding", f"{CLI}::_on_terminal", f"{VERBS}::Verbs.verb_env", "saddlebag/saddlebag/redact.py")


class EnvShow(Command):
    does = "Print a dotenv file with every secret value masked."
    program = "saddlebag"
    argv = ("env", "show", Positional("file"))
    args = Object("EnvShowArgs", file=text("a dotenv file", a_file_that_is_not_there="missing.env"))
    answers = (
        Exit(0, Lines(), "the file, each secret value replaced, and how many were masked"),
        Exit(1, STDERR, "the store cannot be reached or the file cannot be read"),
    )
    carries = act.RunEnvShow
    source = (f"{CLI}::cmd_env", f"{CLI}::_classified", f"{CLI}::_read_dotenv", "saddlebag/saddlebag/dotenv.py",
              f"{VERBS}::Verbs.verb_classify", "saddlebag/saddlebag/shapes.py")


class EnvKeys(Command):
    does = "List a dotenv file's keys, marking the secret ones and the rule that says so."
    program = "saddlebag"
    argv = ("env", "keys", Positional("file"))
    args = Object("EnvKeysArgs", file=text("a dotenv file", a_file_that_is_not_there="missing.env"))
    answers = (
        Exit(0, Lines(), "one line per key"),
        Exit(1, STDERR, "the store cannot be reached or the file cannot be read"),
    )
    carries = act.RunEnvKeys
    source = (f"{CLI}::cmd_env", f"{CLI}::_classified")


class EnvClassify(Command):
    does = "Say which of a dotenv file's keys are secret, as text or JSON."
    program = "saddlebag"
    argv = ("env", "classify", Positional("file"), Switch("--json", "json"))
    args = Object("EnvClassifyArgs", file=text("a dotenv file", a_file_that_is_not_there="missing.env"), json=JSON)
    answers = (
        Exit(0, Lines(), "one verdict per key"),
        Exit(1, STDERR, "the store cannot be reached or the file cannot be read"),
    )
    carries = act.RunEnvClassify
    source = (f"{CLI}::cmd_env", f"{CLI}::_classified")


class EnvImport(Command):
    does = "Store chosen keys of a dotenv file as secrets, one record per key, named after the key."
    program = "saddlebag"
    argv = ("env", "import", Positional("file"), Flag("--keys", "keys"), Flag("--tag", "tag"), Flag("--prefix", "prefix"),
            Switch("--json", "json"))
    args = Object(
        "EnvImportArgs", file=text("a dotenv file", a_file_that_is_not_there="missing.env"),
        keys=text("KEY[,KEY...]", a_key_the_file_lacks="NOPE", the_same_key_twice="PORT,PORT", a_key_that_is_no_variable="C.D"),
        tag=tags("tag every record"),
        prefix=text("put this before each record name", a_prefix_no_name_may_hold="bad prefix "),
        json=JSON)
    answers = (
        Exit(0, Lines(), "one `stored KEY as NAME` line per key, or the keys and names as JSON"),
        Exit(1, STDERR, "the store cannot be reached, the file cannot be read, a secret of that name exists or a key is no variable"),
        Exit(2, STDERR, "no key, a key twice, a key the file lacks, a name that is not valid or a tag that is not key=value"),
    )
    carries = act.RunEnvImport
    source = (f"{CLI}::cmd_env_import", f"{CLI}::_read_dotenv", f"{VERBS}::Verbs.verb_create", f"{VERBS}::Verbs.verb_set")


class EnvSet(Command):
    does = "Assign a literal to a key of a dotenv file, when neither the key nor the value is secret."
    program = "saddlebag"
    argv = ("env", "set", Positional("file"), Positional("key"), Positional("value"))
    args = Object(
        "EnvSetArgs", file=text("a dotenv file", a_file_that_is_not_there="missing.env"),
        key=text("the dotenv key", a_key_that_is_not_a_name="bad key", a_key_that_names_a_secret="API_TOKEN"),
        value=text("the literal", a_value_over_two_lines="a\nb"))
    answers = (
        Exit(0, Lines(), "set KEY, or added it, in the file"),
        Exit(1, STDERR, "the store cannot be reached or the file cannot be read"),
        Exit(2, STDERR, "the key is not a dotenv key, the value cannot be written, or the key or value is secret"),
    )
    carries = act.RunEnvSet
    source = (f"{CLI}::cmd_env_set", "saddlebag/saddlebag/dotenv.py::assign", "saddlebag/saddlebag/dotenv.py::quote",
              f"{VERBS}::Verbs.verb_classify")


class Export(Command):
    does = "Write every secret with its values to a new plaintext JSON file, from a terminal a person answers."
    program = "saddlebag"
    argv = ("export", Positional("file"))
    args = Object("ExportArgs", file=text("a new file named *.saddlebag.json", a_name_without_the_suffix="out.json"))
    answers = (
        Exit(0, Lines(), "the number of secrets exported and where"),
        Exit(1, STDERR, "the file exists, the person declines, or the store cannot be reached"),
        Exit(2, STDERR, "the name lacks the suffix, or no person answers at a terminal"),
    )
    carries = act.RunExport
    source = (f"{CLI}::cmd_export", f"{CLI}::_operator_present", f"{CLI}::_confirmed", "saddlebag/saddlebag/transfer.py::export",
              "saddlebag/saddlebag/transfer.py::render")


class Import(Command):
    does = "Load a file written by export into the store."
    program = "saddlebag"
    argv = ("import", Positional("file"), Switch("--replace", "replace"), Switch("--json", "json"))
    args = Object(
        "ImportArgs", file=text("a file written by export", a_file_that_is_not_there="missing.json"),
        replace=Field(Bool(), required=False, does="overwrite secrets whose names are in the store"), json=JSON)
    answers = (
        Exit(0, Lines(), "one `imported NAME` line per secret, or the names as JSON"),
        Exit(1, STDERR, "the store cannot be reached, the file cannot be read, it is no export, or a name is taken"),
        Exit(2, STDERR, "the file is not JSON"),
    )
    carries = act.RunImport
    source = (f"{CLI}::cmd_import", f"{VERBS}::Verbs.verb_import", "saddlebag/saddlebag/transfer.py::load",
              "saddlebag/saddlebag/transfer.py::read")


class GuardHook(Command):
    does = "Judge a Claude Code PreToolUse payload from stdin and print a deny decision when it would read a secret file."
    program = "saddlebag"
    argv = ("guard", "--hook")
    stdin = "payload"
    args = Object(
        "GuardHookArgs",
        payload=Field(Str(classes={"an action that is allowed": ALLOW_PAYLOAD, "a read of a key file": KEY_PAYLOAD,
                                    "a read of an export": EXPORT_PAYLOAD}), required=False, does="the hook payload, JSON"))
    answers = (Exit(0, Lines(), "a deny decision as one JSON line, or nothing when the action is allowed"),)
    carries = act.RunGuardHook
    source = (f"{CLI}::cmd_guard", f"{CLI}::main", "saddlebag/saddlebag/guard.py::hook", "saddlebag/saddlebag/guard.py::decide")


class GuardInstall(Command):
    does = "Register the guard as a PreToolUse hook in Claude Code's user or project settings."
    program = "saddlebag"
    argv = ("guard", "install", Switch("--user", "user"), Switch("--project", "project"))
    args = Object("GuardInstallArgs", user=Field(Bool(), required=False, does="edit ~/.claude/settings.json"),
                  project=Field(Bool(), required=False, does="edit ./.claude/settings.json"))
    answers = (
        Exit(0, Lines(), "the settings file written"),
        Exit(2, STDERR, "neither or both of --user and --project"),
    )
    carries = act.RunGuardInstall
    source = (f"{CLI}::cmd_guard", "saddlebag/saddlebag/guard.py::install")


class GuardBare(Command):
    does = "Refuse a guard command that names neither --hook nor install."
    program = "saddlebag"
    argv = ("guard",)
    args = Object("GuardBareArgs")
    answers = (Exit(2, STDERR, "guard needs --hook or the install subcommand"),)
    carries = act.RunGuardBare
    source = (f"{CLI}::cmd_guard",)


class Serve(Command):
    does = "Run the daemon that holds the Vault token, or keep a Vault token in the OS keyring and exit."
    program = "saddlebag"
    argv = ("serve", Flag("--socket", "socket"), Flag("--vault-addr", "vault_addr"), Switch("--keep-token", "keep_token"))
    stdin = "token"
    args = Object(
        "ServeArgs", socket=text("the socket to listen on", a_socket_path="run/sb.sock", a_nested_socket_path="run/deep/sb.sock"), vault_addr=text("the Vault address", an_http_address="http://vault.example.com:8200", an_https_address="https://vault.example.com"),
        keep_token=Field(Bool(), required=False, does="store the token from stdin in the keyring and exit"),
        token=Field(Str(classes={"a token": "s.abc123", "a token with a dash": "hvs.ab-12"}), required=False, does="the Vault token, read from stdin"))
    answers = (
        Exit(0, Lines(), "the token is kept, which only stderr says"),
        Exit(2, STDERR, "no Vault address, or stdin gave no token"),
    )
    carries = act.RunServe
    source = (f"{CLI}::cmd_serve", "saddlebag/saddlebag/custody.py", "saddlebag/saddlebag/vault.py::VaultStore",
              "saddlebag/saddlebag/daemon.py", "saddlebag/saddlebag/protocol.py", "saddlebag/saddlebag/sockets.py",
              "saddlebag/saddlebag/route.py")


ALL = (Version, Inventory, Tags, Create, Edit, SetValue, Unset, Remove, TagSecret, UntagSecret, Meta, Unmeta, Fill, TypeInto, Exec,
       EnvShow, EnvKeys, EnvClassify, EnvImport, EnvSet, Export, Import, GuardHook, GuardInstall, GuardBare, Doctor, Serve,
       Look)

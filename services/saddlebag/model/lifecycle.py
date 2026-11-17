"""The lifecycle matrix of the store: how far it has come, and what each command does to it there."""

from __future__ import annotations

from datetime import date
from typing import Callable

from ostler.book import Axes, Scene

from .. import commands as c
from .. import fixtures as f
from ..events import ChooseDaemon
from .files import BACKEND_DAEMON, CONFIG
from .state import Store

TODAY = date(2026, 11, 16)


def stage(model: Store) -> str:
    if BACKEND_DAEMON in model.files[CONFIG].holds:
        return "daemon-preferred"
    acme = model.secrets.get(f.ACME)
    if acme is None:
        return "empty"
    return "stocked" if acme.fields else "registered"


SCENES = (
    Scene("empty", "no secret is stored", lambda today: ()),
    Scene("registered", f"{f.ACME!r} is created and holds no value", lambda today: (c.Create(f.acme()),)),
    Scene("stocked", f"{f.ACME!r} holds a password and a TOTP seed and {f.BETA!r} holds a password",
          lambda today: (c.Create(f.acme()), c.SetValue(f.set_value()), c.SetValue(f.set_seed()),
                         c.Create(f.beta()), c.SetValue(f.set_value(f.BETA, f.BETA_PASSWORD)))),
    Scene("daemon-preferred", "the home config prefers the daemon and none runs", lambda today: (ChooseDaemon(),)),
)

ACTIONS: dict[str, Callable[[Store], object]] = {
    "version": lambda m: c.Version(f.version()),
    "list": lambda m: c.Inventory(f.list_()),
    "list json": lambda m: c.Inventory(f.list_(json=True)),
    "list by a tag": lambda m: c.Inventory(f.list_(tag=["env=ci"])),
    "list by a malformed tag": lambda m: c.Inventory(f.list_(tag=["env"])),
    "tags": lambda m: c.Tags(f.tags()),
    "tags of one tag": lambda m: c.Tags(f.tags(tag=["team=a"])),
    "tags of a malformed tag": lambda m: c.Tags(f.tags(tag=["team"])),
    "create": lambda m: c.Create(f.acme()),
    "create json": lambda m: c.Create(f.acme(json=True)),
    "create beta": lambda m: c.Create(f.beta()),
    "create malformed name": lambda m: c.Create(f.create("two words")),
    "create malformed var": lambda m: c.Create(f.create("gamma", var="a-b")),
    "create malformed tag": lambda m: c.Create(f.create("gamma", tag=["env"])),
    "create malformed meta": lambda m: c.Create(f.create("gamma", meta=["a.b=1"])),
    "create meta twice": lambda m: c.Create(f.create("gamma", meta=["k=1", "k=2"])),
    "set password": lambda m: c.SetValue(f.set_value()),
    "set seed": lambda m: c.SetValue(f.set_seed()),
    "set bad seed": lambda m: c.SetValue(f.set_seed(value="not base32!")),
    "set empty": lambda m: c.SetValue(f.set_value(value="\n")),
    "set unknown": lambda m: c.SetValue(f.set_value("nonesuch")),
    "set username": lambda m: c.SetValue(f.set_value(field="username")),
    "unset password": lambda m: c.Unset(f.unset()),
    "unset seed": lambda m: c.Unset(f.unset(field="totp")),
    "unset without a field": lambda m: c.Unset(f.unset(field=None)),
    "unset unknown": lambda m: c.Unset(f.unset("nonesuch")),
    "remove": lambda m: c.Remove(f.remove()),
    "remove unknown": lambda m: c.Remove(f.remove("nonesuch")),
    "tag": lambda m: c.TagSecret(f.tag()),
    "tag malformed": lambda m: c.TagSecret(f.tag(first="env")),
    "tag unknown": lambda m: c.TagSecret(f.tag("nonesuch")),
    "untag": lambda m: c.UntagSecret(f.untag()),
    "meta": lambda m: c.Meta(f.meta()),
    "meta malformed": lambda m: c.Meta(f.meta(first="region")),
    "meta bad key": lambda m: c.Meta(f.meta(first="a.b=1")),
    "meta twice": lambda m: c.Meta(f.meta(first="k=1", second="k=2")),
    "unmeta": lambda m: c.Unmeta(f.unmeta()),
    "unmeta lacking": lambda m: c.Unmeta(f.unmeta(first="nonesuch")),
    "unmeta bad key": lambda m: c.Unmeta(f.unmeta(first="a.b")),
    "doctor": lambda m: c.Doctor(f.doctor()),
    "doctor json": lambda m: c.Doctor(f.doctor(json=True)),
    "look": lambda m: c.Look(f.look()),
    "exec by a binding": lambda m: c.Exec(f.run("ACME_PW", env=["ACME_PW=acme"])),
    "exec by a tag": lambda m: c.Exec(f.run("ACME_PW", tag=["team=a"])),
    "exec by a tag beta": lambda m: c.Exec(f.run("BETA_PW", tag=["team=b"])),
    "exec a short value": lambda m: c.Exec(f.run("BETA_PW", env=["BETA_PW=beta"])),
    "exec a username": lambda m: c.Exec(f.run("WHO", env=["WHO=acme.username"])),
    "exec a metadata value": lambda m: c.Exec(f.run("REALM", env=["REALM=acme.meta.realm"])),
    "exec a seed that is not stored": lambda m: c.Exec(f.run("OTP", env=["OTP=beta.totp"])),
    "exec a variable it was not handed": lambda m: c.Exec(f.run("NOT_HANDED", env=["ACME_PW=acme"])),
    "exec with no command": lambda m: c.Exec(f.run(None, program=None, env=["ACME_PW=acme"])),
    "exec with nothing to fill": lambda m: c.Exec(f.run("ACME_PW")),
    "exec a malformed binding": lambda m: c.Exec(f.run("ACME_PW", env=["ACME_PW"])),
    "exec a malformed tag": lambda m: c.Exec(f.run("ACME_PW", tag=["team"])),
    "exec a tag nobody carries": lambda m: c.Exec(f.run("ACME_PW", tag=["team=zz"])),
    "exec a bad variable": lambda m: c.Exec(f.run("X", env=["1X=acme"])),
    "exec an unknown secret": lambda m: c.Exec(f.run("X", env=["X=nonesuch"])),
    "exec an unknown field": lambda m: c.Exec(f.run("X", env=["X=acme.bogus"])),
    "exec a bad metadata key": lambda m: c.Exec(f.run("X", env=["X=acme.meta.a.b"])),
    "exec a missing username": lambda m: c.Exec(f.run("X", env=["X=beta.username"])),
    "exec a missing metadata": lambda m: c.Exec(f.run("X", env=["X=acme.meta.nope"])),
    "exec a program that does not exist": lambda m: c.Exec(f.run("ACME_PW", env=["ACME_PW=acme"], program="no-such-tool")),
    "env show": lambda m: c.EnvShow(f.env_show()),
    "env show a missing file": lambda m: c.EnvShow(f.env_show("missing.env")),
    "env keys": lambda m: c.EnvKeys(f.env_keys()),
    "env classify": lambda m: c.EnvClassify(f.env_classify()),
    "env classify json": lambda m: c.EnvClassify(f.env_classify(json=True)),
    "env import": lambda m: c.EnvImport(f.env_import()),
    "env import json": lambda m: c.EnvImport(f.env_import("PORT", tag=["env=dev"], prefix="app-", json=True)),
    "env import no key": lambda m: c.EnvImport(f.env_import(" ")),
    "env import a key twice": lambda m: c.EnvImport(f.env_import("PORT,PORT")),
    "env import a key the file lacks": lambda m: c.EnvImport(f.env_import("NOPE")),
    "env import a bad name": lambda m: c.EnvImport(f.env_import("PORT", prefix="bad prefix ")),
    "env import a bad tag": lambda m: c.EnvImport(f.env_import("PORT", tag=["env"])),
    "env import a bad variable": lambda m: c.EnvImport(f.env_import("PORT,ACME_PW", prefix="x.")),
    "env set": lambda m: c.EnvSet(f.env_set()),
    "env set a new key": lambda m: c.EnvSet(f.env_set("REGION", "eu")),
    "env set a secret key": lambda m: c.EnvSet(f.env_set("API_TOKEN", "abc")),
    "env set a registered key": lambda m: c.EnvSet(f.env_set("ACME_PW", "x")),
    "env set a token": lambda m: c.EnvSet(f.env_set("PORT", "ghp_abcdefghijkl")),
    "env set a url": lambda m: c.EnvSet(f.env_set("STAGING_URL", "https://ana:pw@example.com/db")),
    "env set a bad key": lambda m: c.EnvSet(f.env_set("bad key")),
    "env set two lines": lambda m: c.EnvSet(f.env_set("PORT", "a\nb")),
    "fill": lambda m: c.Fill(f.fill()),
    "fill a seed": lambda m: c.Fill(f.fill(field="totp")),
    "fill a username": lambda m: c.Fill(f.fill(field="username")),
    "fill a metadata value": lambda m: c.Fill(f.fill(field="meta.realm")),
    "fill a missing metadata value": lambda m: c.Fill(f.fill(field="meta.nope")),
    "fill an unknown field": lambda m: c.Fill(f.fill(field="bogus")),
    "fill a bad metadata key": lambda m: c.Fill(f.fill(field="meta.a.b")),
    "fill with no selector": lambda m: c.Fill(f.fill(selector=None)),
    "fill another host": lambda m: c.Fill(f.fill(cdp="http://example.com:9222")),
    "fill an unknown secret": lambda m: c.Fill(f.fill("nonesuch")),
    "type": lambda m: c.TypeInto(f.type_()),
    "type a username": lambda m: c.TypeInto(f.type_(field="username")),
    "type an unknown secret": lambda m: c.TypeInto(f.type_("nonesuch")),
    "export": lambda m: c.Export(f.export()),
    "export a bad name": lambda m: c.Export(f.export("out.json")),
    "import": lambda m: c.Import(f.import_()),
    "import and replace": lambda m: c.Import(f.import_(replace=True)),
    "import json": lambda m: c.Import(f.import_(json=True)),
    "import a missing file": lambda m: c.Import(f.import_("missing.json")),
    "import a broken file": lambda m: c.Import(f.import_("broken.saddlebag.json")),
    "import a foreign file": lambda m: c.Import(f.import_("foreign.json")),
    "guard hook denies": lambda m: c.GuardHook(f.hook()),
    "guard hook allows": lambda m: c.GuardHook(f.hook(f.ALLOW_PAYLOAD)),
    "guard hook allows an example": lambda m: c.GuardHook(f.hook(f.EXAMPLE_PAYLOAD)),
    "guard hook denies a key": lambda m: c.GuardHook(f.hook(f.KEY_PAYLOAD)),
    "guard hook denies an export": lambda m: c.GuardHook(f.hook(f.EXPORT_PAYLOAD)),
    "guard hook allows exec": lambda m: c.GuardHook(f.hook(f.EXEC_PAYLOAD)),
    "guard hook reads garbage": lambda m: c.GuardHook(f.hook("not json")),
    "guard install in the project": lambda m: c.GuardInstall(f.install_guard()),
    "guard install for the user": lambda m: c.GuardInstall(f.install_guard(user=True, project=None)),
    "guard install for neither": lambda m: c.GuardInstall(f.install_guard(project=None)),
    "guard install for both": lambda m: c.GuardInstall(f.install_guard(user=True)),
    "guard alone": lambda m: c.GuardBare(f.GuardBareArgs()),
    "serve with no address": lambda m: c.Serve(f.serve()),
    "serve and keep a token": lambda m: c.Serve(f.serve(keep_token=True, token="vault-token")),
    "serve and keep no token": lambda m: c.Serve(f.serve(keep_token=True)),
    "serve with an address and no token": lambda m: c.Serve(f.serve(vault_addr="http://127.0.0.1:1")),
}

MATRICES = (Axes[Store]("store", TODAY, SCENES, ACTIONS, stage, state_of=lambda m, _: stage(m)),)

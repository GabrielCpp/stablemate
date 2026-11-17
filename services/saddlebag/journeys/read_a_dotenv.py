from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from .. import commands as c
from .. import fixtures as f


class ReadADotenv(Journey):
    """A person reads the app's dotenv without seeing a secret. With an empty store, the token and the credentialed
    URL are masked by their shapes and the registered password is a literal. Once the acme login is registered its
    variable is secret, and once its password is stored the same value is secret by what it holds. They change a
    literal and add a new one, are refused a key or value that is secret, a key that is not a name and a value on
    two lines, and import two keys of the file as secrets of their own."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            c.EnvShow(f.env_show()),
            c.EnvKeys(f.env_keys()),
            c.EnvClassify(f.env_classify()),
            c.EnvClassify(f.env_classify(json=True)),
            c.EnvShow(f.env_show("missing.env")),
            c.Create(f.acme()),
            c.EnvKeys(f.env_keys()),
            c.EnvSet(f.env_set("ACME_PW", "x")),
            c.SetValue(f.set_value()),
            c.EnvKeys(f.env_keys()),
            c.EnvShow(f.env_show()),
            c.EnvSet(f.env_set("ACME_PW", "x")),
            c.EnvSet(f.env_set()),
            c.EnvSet(f.env_set("REGION", "eu")),
            c.EnvSet(f.env_set("API_TOKEN", "abc")),
            c.EnvSet(f.env_set("PORT", "ghp_abcdefghijkl")),
            c.EnvSet(f.env_set("STAGING_URL", "https://ana:pw@example.com/db")),
            c.EnvSet(f.env_set("bad key")),
            c.EnvSet(f.env_set("PORT", "a\nb")),
            c.EnvSet(f.env_set(file="missing.env")),
            c.EnvShow(f.env_show()),
            c.EnvImport(f.env_import("PORT,LOG_LEVEL", tag=["env=dev"], prefix="app-")),
            c.EnvImport(f.env_import("PORT", prefix="app-")),
            c.EnvImport(f.env_import("LOG_LEVEL,PORT", prefix="app-")),
            c.EnvImport(f.env_import("REGION_X")),
            c.EnvImport(f.env_import("NOPE")),
            c.EnvImport(f.env_import("PORT,PORT")),
            c.EnvImport(f.env_import(" ")),
            c.EnvImport(f.env_import("PORT", prefix="bad prefix ")),
            c.EnvImport(f.env_import("PORT", tag=["env"])),
            c.EnvImport(f.env_import("PORT", file="missing.env")),
            c.EnvImport(f.env_import("PORT", json=True)),
            c.EnvImport(f.env_import("ACME_PW", prefix="x.")),
            c.Inventory(f.list_()),
        )

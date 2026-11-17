from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from .. import commands as c
from .. import fixtures as f


class RunWithSecrets(Journey):
    """A person registers the acme and beta logins and stores a password for each and a TOTP seed for acme. They run
    a program with a login's password in its environment by name and by tag, and see a value of eight characters or
    more masked in what it prints, a shorter one left as it is, and the username and metadata in the clear. They are
    refused a command with nothing to fill, a malformed binding or tag, a tag nobody carries, an unknown secret, a field
    the secret lacks, a variable the program was not handed and a program that does not exist."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            c.Create(f.acme()),
            c.Create(f.beta()),
            c.Exec(f.run("ACME_PW", tag=["team=a"])),
            c.SetValue(f.set_value()),
            c.SetValue(f.set_seed()),
            c.SetValue(f.set_value(f.BETA, f.BETA_PASSWORD)),
            c.Exec(f.run("ACME_PW", env=["ACME_PW=acme"])),
            c.Exec(f.run("ACME_PW", tag=["team=a"])),
            c.Exec(f.run("BETA_PW", tag=["team=b"])),
            c.Exec(f.run("BETA_PW", env=["BETA_PW=beta"])),
            c.Exec(f.run("WHO", env=["WHO=acme.username"])),
            c.Exec(f.run("REALM", env=["REALM=acme.meta.realm"])),
            c.Exec(f.run("OTP", env=["OTP=beta.totp"])),
            c.Exec(f.run("NOT_HANDED", env=["ACME_PW=acme"])),
            c.Exec(f.run(None, program=None, env=["ACME_PW=acme"])),
            c.Exec(f.run("ACME_PW")),
            c.Exec(f.run("ACME_PW", env=["ACME_PW"])),
            c.Exec(f.run("ACME_PW", tag=["team"])),
            c.Exec(f.run("ACME_PW", tag=["team=zz"])),
            c.Exec(f.run("X", env=["1X=acme"])),
            c.Exec(f.run("X", env=["X=nonesuch"])),
            c.Exec(f.run("X", env=["X=acme.bogus"])),
            c.Exec(f.run("X", env=["X=acme.meta.a.b"])),
            c.Exec(f.run("X", env=["X=beta.username"])),
            c.Exec(f.run("X", env=["X=acme.meta.nope"])),
            c.Exec(f.run("ACME_PW", env=["ACME_PW=acme"], program="no-such-tool")),
            c.Unset(f.unset(f.BETA)),
            c.Exec(f.run("BETA_PW", tag=["team=b"])),
            c.Exec(f.run("BETA_PW", env=["BETA_PW=beta"])),
            c.Unset(f.unset(f.ACME)),
            c.Exec(f.run("ACME_PW", tag=["team=a"])),
            c.Unset(f.unset(f.ACME, "totp")),
            c.Exec(f.run("X", env=["X=acme.totp"])),
            c.Doctor(f.doctor()),
        )

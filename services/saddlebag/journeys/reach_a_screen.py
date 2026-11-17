from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from .. import commands as c
from .. import fixtures as f


class ReachAScreen(Journey):
    """A person asks saddlebag to type the acme login into a browser page and an Android field, and is told what
    stands in the way: no such secret, nothing stored under the field, a selector left out, a browser on another host,
    no browser listening and no adb. They keep a Vault token for the daemon and are refused a daemon with no address or
    no token."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            c.Fill(f.fill("nonesuch")),
            c.Create(f.acme()),
            c.Fill(f.fill()),
            c.Fill(f.fill(field="username")),
            c.Fill(f.fill(field="meta.realm")),
            c.Fill(f.fill(field="meta.nope")),
            c.Fill(f.fill(field="bogus")),
            c.Fill(f.fill(field="meta.a.b")),
            c.Fill(f.fill(selector=None)),
            c.SetValue(f.set_value()),
            c.SetValue(f.set_seed()),
            c.Fill(f.fill(cdp="http://example.com:9222")),
            c.Fill(f.fill()),
            c.Fill(f.fill(field="totp")),
            c.TypeInto(f.type_("nonesuch")),
            c.TypeInto(f.type_(field="meta.nope")),
            c.TypeInto(f.type_()),
            c.TypeInto(f.type_(field="totp")),
            c.Serve(f.serve()),
            c.Serve(f.serve(keep_token=True)),
            c.Serve(f.serve(keep_token=True, token="vault-token")),
            c.Serve(f.serve(vault_addr="http://127.0.0.1:1")),
        )

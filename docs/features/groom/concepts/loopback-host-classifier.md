---
type: concept
slug: loopback-host-classifier
title: Loopback host classifier
---
# Loopback host classifier

Loopback host classifier is the command-layer decision used by the
[`groom serve`](../groom-cli.md#groom-serve) invocation before server startup. It classifies the
operator-selected bind host as loopback or externally reachable for the startup exposure warning;
it does not validate that the host can bind, normalize the host string, enforce authentication, or
change the address passed to the server runner.

- code: groom/groom/cli.py::_is_loopback

## Contract

- input: `host` is the exact string selected for `groom serve --host`, after argparse applies the
  command default when the operator omits the flag.
- output: returns `true` only when the host is explicitly recognized as loopback.
- loopback names: the literal host string `localhost` is accepted as loopback without DNS lookup.
- loopback IPs: parseable IP addresses use their address-family loopback property, so IPv4 and IPv6
  loopback literals are accepted.
- non-loopback result: non-loopback IP addresses and host strings that cannot be parsed as an IP
  address both return `false` for warning purposes.
- side effects: performs no I/O, DNS lookup, logging, warning emission, binding, or server startup.
- failure handling: malformed or non-IP host strings are converted to `false`; no validation error is
  surfaced to the command handler.

## Methods

### method-_is_loopback

- sig: `_is_loopback(host: str) -> bool`
- raises: none for ordinary host strings; unparsable hosts are classified as non-loopback.
- code: groom/groom/cli.py::_is_loopback
- algorithm:
  1. Return `true` when `host` is exactly `localhost`.
  2. Otherwise, attempt to interpret `host` as an IP address.
  3. Return the parsed address's loopback classification when parsing succeeds.
  4. Return `false` when parsing fails.

---
type: concept
slug: loopback-classifier-authority
title: Loopback classifier authority
---
# Loopback classifier authority

`cli.py` has exactly one loopback classifier, `_is_loopback(host)`, documented by two `method`
nodes at different depths: [Groom CLI entrypoints module](groom-cli-entrypoints-module.md#method-_is-loopback)
states the two return-value cases in the context of `groom serve`'s exposure-warning decision;
[loopback host classifier](loopback-host-classifier.md#method-_is_loopback) is the full contract —
the `localhost`-literal special case, the IP-address-family loopback check, and the ordered
algorithm the two return values come out of.

These are not competing implementations to choose between; the code has exactly one. The two docs
exist at different zoom levels of the same function, and a reader who needs the algorithm itself —
why `localhost` never hits `ipaddress.ip_address`, or what happens when parsing fails — has to
leave the entrypoints module's summary and read the full contract.

- rule: read [loopback host classifier](loopback-host-classifier.md#method-_is_loopback) for the
  classifier's full algorithm; [Groom CLI entrypoints module](groom-cli-entrypoints-module.md#method-_is-loopback)
  states only the two return-value cases as they bear on the exposure warning and defers to the
  classifier for the algorithm.
- prefers: [loopback host classifier](loopback-host-classifier.md#method-_is_loopback)


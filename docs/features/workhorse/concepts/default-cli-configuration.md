---
type: concept
slug: default-cli-configuration
title: Default CLI configuration
---
# Default CLI configuration

`resolve_default_cli` and `write_default_cli` form the read and write sides of the
same `default_cli` setting; neither replaces the other. A run uses the resolver
after higher-precedence invocation and environment choices have been considered.
The resolver returns the built-in `claude` fallback when the stored value is
absent, empty, or not a string. Configuration tooling uses the writer when an
operator changes that persisted fallback; the writer strips and lowercases the
name before delegating the durable write to `write_config_key`.

The resolver deliberately does not validate a backend name because the backend
registry belongs to workhorse's selection boundary. The writer therefore must
not be used as a validation API either: it records the normalized preference,
and the boundary reports an unknown name in the same way as an invalid `--cli`
value.

- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::resolve_default_cli`
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::write_default_cli`
- rule: use `resolve_default_cli` to obtain the effective configured fallback for a run, and use `write_default_cli` only to persist an operator-selected fallback; neither API is a backend validator

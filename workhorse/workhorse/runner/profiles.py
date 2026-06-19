"""Run-level profiles — a self-contained ``{cli, env, models}`` bundle that drives
a whole run on a specific CLI through a (proxied) provider.

Background. A node's ``model:`` is normally a per-CLI map (``{claude: opus, codex:
"@gpt-5.5"}``) and the CLI is chosen per-run via ``--cli`` / ``AGENT_CLI``. That is
the implicit **``default`` profile**: native models, no proxy wiring. A **named
profile** is the alternative input — it is mutually exclusive with ``--cli`` — and
bundles everything needed to run somewhere else:

* ``cli``           — the one backend this profile runs on (claude/codex/copilot).
* ``models``        — logical name → concrete CLI model string for that backend.
* ``default_model`` — the logical model used by any node that doesn't pick one.
* ``env``           — provider/proxy env vars injected into the CLI subprocess
                      (``${VAR}`` is expanded from the process env so secrets stay
                      out of the file). For codex the model string carries the
                      ``~/.codex/config.toml`` profile name (``mimo@mimo`` → that
                      lower-level codex profile + the ``-m mimo`` override); that
                      codex config profile is a DISTINCT concept from this
                      workhorse profile, carried here only as data.
* ``effort``        — optional override of every node's reasoning effort under this
                      profile; ``"none"`` suppresses it (e.g. MiMo isn't a
                      reasoning model). Unset → leave each node's effort untouched.

Resolution lives in ``runner/agent.py`` (``_resolve_model``): under a named profile
the node's CLI-map is NOT consulted — the node picks one of the profile's models by
the profile-name key in its ``model:`` map, else the profile default. ``main.py``
sets ``AGENT_CLI`` from the profile, injects ``env`` once, and health-checks the
proxy before the run.
"""
from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

import yaml

# A node's model map keys CLI names for the default profile and profile names for
# named profiles; a profile named after a CLI would make those keys ambiguous.
_RESERVED_CLI_NAMES = frozenset({"claude", "codex", "copilot"})
# The implicit no-proxy profile (today's behaviour). Never a registry entry.
DEFAULT_PROFILE = "default"

_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

# Parsed-registry cache keyed by the resolved file path. Tests clear it.
_CACHE: dict[str, dict] = {}


@dataclass(frozen=True)
class ProxySpec:
    """A proxy whose **lifecycle workhorse owns** so a profiled run works out of the
    box — no ``.env`` to maintain and nothing to ``export``.

    When a profile declares a proxy, workhorse generates a stable *local-only* auth
    token (NOT a real upstream credential — the proxy injects that), starts the proxy
    with ``start`` if it isn't already healthy, waits for it, and injects the token +
    base URL into the agent CLI. The only real secret (e.g. ``OPENROUTER_API_KEY``)
    is pulled from the ambient environment and named in ``passthrough_env``.

    Fields (all but ``start`` optional, with LiteLLM-friendly defaults):

    * ``start``           — command (argv list) that brings the proxy up when it is
                            down. Run with the ambient env PLUS the managed token
                            (``secret_env``), base URL (``base_url_env``) and, if
                            ``port`` is set, the port (``port_env``). ``${VAR}`` in
                            any arg is expanded from the environment.
    * ``port``            — host port; ``base_url`` defaults to
                            ``http://localhost:<port>`` and the port is exported to
                            ``start`` as ``port_env``.
    * ``base_url``        — explicit proxy base URL (overrides the port-derived one).
    * ``health_path``     — readiness probe path (any ``<500`` means up).
    * ``passthrough_env`` — ambient vars REQUIRED to start the proxy (validated, then
                            inherited by ``start``); the real provider key lives here.
    * ``secret_env`` / ``base_url_env`` / ``port_env`` — names under which workhorse
                            exposes the managed token / base URL / port.
    """

    start: tuple[str, ...]
    port: int | None = None
    base_url: str | None = None
    health_path: str = "/health/readiness"
    secret_env: str = "LITELLM_MASTER_KEY"
    base_url_env: str = "LITELLM_BASE_URL"
    port_env: str = "LITELLM_PORT"
    passthrough_env: tuple[str, ...] = ()
    ready_timeout_s: float = 90.0

    @property
    def resolved_base_url(self) -> str:
        if self.base_url:
            return self.base_url.rstrip("/")
        if self.port is not None:
            return f"http://localhost:{self.port}"
        return "http://localhost:4000"


@dataclass(frozen=True)
class Profile:
    """A resolved run-level profile (env already ``${VAR}``-interpolated)."""

    name: str
    cli: str
    models: dict[str, str]
    default_model: str
    env: dict[str, str] = field(default_factory=dict)
    effort: str | None = None
    proxy: ProxySpec | None = None

    def model_for(self, logical: str | None) -> str:
        """Concrete CLI model string for ``logical`` (or the profile default)."""
        key = logical or self.default_model
        if key not in self.models:
            raise ValueError(
                f"profile '{self.name}' has no model '{key}'; "
                f"available: {sorted(self.models)}"
            )
        return self.models[key]


def _interpolate(value: str, environ: Mapping[str, str]) -> str:
    """Expand ``${NAME}`` from ``environ``; a missing var is a hard error (fail
    fast — a half-wired proxy is worse than a clear 'set LITELLM_MASTER_KEY')."""

    def repl(m: re.Match[str]) -> str:
        name = m.group(1)
        if name not in environ:
            raise ValueError(
                f"environment variable ${{{name}}} referenced by a profile is not "
                f"set (source tooling/openrouter-cache/.env or export it)"
            )
        return environ[name]

    return _VAR_RE.sub(repl, value)


def _config_dir() -> Path:
    """``$XDG_CONFIG_HOME/workhorse`` (default ``~/.config/workhorse``)."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "workhorse"


def proxy_local_secret() -> str:
    """A stable, local-only auth token shared between a workhorse-managed proxy and
    the agent CLI it fronts. This is NOT a real upstream credential — the proxy
    injects the provider key; this token only gates the loopback proxy. Generated
    once and persisted at ``~/.config/workhorse/proxy-secret`` (mode 600), so the
    same value is reused across runs (and matches an already-running managed proxy)."""
    path = _config_dir() / "proxy-secret"
    try:
        existing = path.read_text().strip()
        if existing:
            return existing
    except OSError:
        pass
    token = "sk-local-" + secrets.token_hex(16)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return token


def _parse_proxy(name: str, raw: object, environ: Mapping[str, str]) -> ProxySpec:
    """Validate + interpolate a profile's ``proxy:`` block into a ``ProxySpec``."""
    if not isinstance(raw, dict):
        raise ValueError(f"profile '{name}': 'proxy' must be a mapping")
    start = raw.get("start")
    if not isinstance(start, list) or not start:
        raise ValueError(
            f"profile '{name}': proxy.start must be a non-empty list — the command "
            "that brings the proxy up when it is down (e.g. ['docker','compose','-f',"
            "'/abs/compose.litellm.yaml','up','-d'])"
        )
    start_cmd = tuple(_interpolate(str(a), environ) for a in start)
    port = raw.get("port")
    if port is not None:
        try:
            port = int(port)
        except (TypeError, ValueError):
            raise ValueError(f"profile '{name}': proxy.port must be an integer") from None
    passthrough = tuple(str(v) for v in (raw.get("passthrough_env") or []))
    return ProxySpec(
        start=start_cmd,
        port=port,
        base_url=(str(raw["base_url"]) if raw.get("base_url") else None),
        health_path=str(raw.get("health_path", "/health/readiness")),
        secret_env=str(raw.get("secret_env", "LITELLM_MASTER_KEY")),
        base_url_env=str(raw.get("base_url_env", "LITELLM_BASE_URL")),
        port_env=str(raw.get("port_env", "LITELLM_PORT")),
        passthrough_env=passthrough,
        ready_timeout_s=float(raw.get("ready_timeout_s", 90)),
    )


def _user_global_path() -> Path:
    """The user-global profiles file: ``$XDG_CONFIG_HOME/workhorse/profiles.yaml``
    (default ``~/.config/workhorse/profiles.yaml``)."""
    return _config_dir() / "profiles.yaml"


def _resolve_registry_path(
    explicit: str | None, workflow_dir: Path | None
) -> Path | None:
    """Locate the profiles file. Profiles are an operator/runtime concern (proxy
    endpoints, provider credentials), so this package ships NO embedded default —
    the file is entirely user-supplied. Discovery order:

      ``--profiles-file`` → ``AGENT_PROFILES_FILE`` →
      ``$AGENT_REPO_DIR/.agents/workhorse-profiles.yaml`` →
      ``<workflow-dir>/workhorse-profiles.yaml`` →
      ``$XDG_CONFIG_HOME/workhorse/profiles.yaml`` (~/.config/...)

    An explicitly requested path (flag or env) that is missing is a hard error; the
    implicit candidates are skipped when absent. Returns ``None`` when nothing is
    found (no profiles configured)."""
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            raise FileNotFoundError(f"--profiles-file not found: {p}")
        return p
    env_path = os.environ.get("AGENT_PROFILES_FILE")
    if env_path:
        p = Path(env_path)
        if not p.is_file():
            raise FileNotFoundError(f"AGENT_PROFILES_FILE not found: {p}")
        return p
    candidates: list[Path] = []
    repo = os.environ.get("AGENT_REPO_DIR")
    if repo:
        candidates.append(Path(repo) / ".agents" / "workhorse-profiles.yaml")
    if workflow_dir:
        candidates.append(Path(workflow_dir) / "workhorse-profiles.yaml")
    candidates.append(_user_global_path())
    for c in candidates:
        if c.is_file():
            return c
    return None


def load_profiles(
    path: str | None = None, workflow_dir: Path | None = None
) -> dict[str, dict]:
    """Discover + parse the profiles file → ``{name: raw_spec}`` (uninterpolated).

    Returns an empty mapping when no profiles file is found or it declares none.
    Caches by resolved path. Rejects a profile named after a CLI backend or
    ``default``."""
    registry_path = _resolve_registry_path(path, workflow_dir)
    if registry_path is None:
        return {}
    key = str(registry_path.resolve())
    if key in _CACHE:
        return _CACHE[key]
    raw = yaml.safe_load(registry_path.read_text()) or {}
    profiles = raw.get("profiles") or {}
    if not isinstance(profiles, dict):
        raise ValueError(f"profiles file {registry_path}: 'profiles' must be a mapping")
    for name in profiles:
        if name in _RESERVED_CLI_NAMES:
            raise ValueError(
                f"profile '{name}' collides with a CLI backend name; profiles must "
                "not be named claude/codex/copilot"
            )
        if name == DEFAULT_PROFILE:
            raise ValueError("'default' is reserved (the implicit no-profile run)")
    _CACHE[key] = profiles
    return profiles


def resolve_profile(
    name: str | None,
    *,
    path: str | None = None,
    workflow_dir: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Profile | None:
    """Resolve a profile name to a validated ``Profile`` (env interpolated).

    ``None`` / ``"default"`` → ``None`` (the caller keeps today's per-CLI behaviour).
    An unknown name raises ``ValueError`` (fail fast, like an unknown ``--cli``)."""
    if not name or name == DEFAULT_PROFILE:
        return None
    registry = load_profiles(path, workflow_dir)
    if not registry:
        raise ValueError(
            f"profile {name!r} requested but no profiles file was found. Create "
            "~/.config/workhorse/profiles.yaml (or .agents/workhorse-profiles.yaml) "
            "or pass --profiles-file / set AGENT_PROFILES_FILE. See "
            "tooling/openrouter-cache/workhorse-profiles.yaml for an example."
        )
    if name not in registry:
        available = ", ".join(sorted(registry)) or "none"
        raise ValueError(f"unknown profile {name!r} (available: {available})")
    spec = registry[name]
    if not isinstance(spec, dict):
        raise ValueError(f"profile '{name}' must be a mapping")
    environ = os.environ if environ is None else environ

    cli = spec.get("cli")
    if cli not in _RESERVED_CLI_NAMES:
        raise ValueError(
            f"profile '{name}': 'cli' must be one of claude/codex/copilot (got {cli!r})"
        )
    models_raw = spec.get("models") or {}
    if not isinstance(models_raw, dict) or not models_raw:
        raise ValueError(f"profile '{name}': 'models' must be a non-empty mapping")
    models = {str(k): str(v) for k, v in models_raw.items()}

    default_model = spec.get("default_model")
    if default_model is None:
        if len(models) == 1:
            default_model = next(iter(models))  # single model → it is the default
        else:
            raise ValueError(
                f"profile '{name}': 'default_model' is required when 'models' lists "
                f"more than one entry (available: {sorted(models)})"
            )
    default_model = str(default_model)
    if default_model not in models:
        raise ValueError(
            f"profile '{name}': default_model '{default_model}' is not in 'models' "
            f"({sorted(models)})"
        )

    # A managed proxy contributes its generated token + base URL to the interpolation
    # environment, so the profile's `env` can reference ${LITELLM_MASTER_KEY} /
    # ${LITELLM_BASE_URL} without the operator setting (or even knowing) them.
    proxy = _parse_proxy(name, spec["proxy"], environ) if spec.get("proxy") else None
    interp_env: Mapping[str, str] = environ
    if proxy is not None:
        interp_env = {
            **environ,
            proxy.secret_env: proxy_local_secret(),
            proxy.base_url_env: proxy.resolved_base_url,
        }

    env = {k: _interpolate(str(v), interp_env) for k, v in (spec.get("env") or {}).items()}
    effort = spec.get("effort")
    return Profile(
        name=name,
        cli=cli,
        models=models,
        default_model=default_model,
        env=env,
        effort=str(effort) if effort is not None else None,
        proxy=proxy,
    )

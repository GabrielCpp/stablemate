"""The manifest: what travels off the machine, and what must never travel with it."""

from __future__ import annotations

import pytest
import yaml

from saddlebag import manifest
from saddlebag.models import (
    KIND_CONFIG,
    KIND_CREDENTIAL_REF,
    KIND_PENDING,
    KIND_SECRET,
    Environment,
    EnvironmentEntry,
)

WEB_LOCAL = Environment(
    id="env-001",
    name="web-local",
    env="local",
    project="predykt",
    target="web/.env.local",
    entries=(
        EnvironmentEntry(key="VITE_FIREBASE_PROJECT_ID", kind=KIND_CONFIG,
                         value="predykt", position=1),
        EnvironmentEntry(key="VITE_FIREBASE_AUTH_EMULATOR_HOST", kind=KIND_CONFIG,
                         value="127.0.0.1:9099", position=2,
                         note="unset this to point the web app at real Firebase Auth"),
        EnvironmentEntry(key="VITE_FIREBASE_API_KEY", kind=KIND_SECRET, position=3),
        EnvironmentEntry(key="TEST_USER_PASSWORD", kind=KIND_CREDENTIAL_REF,
                         cred_ref="cred-007:password", position=4),
        EnvironmentEntry(key="OPTIONAL_FLAG", kind=KIND_PENDING, required=False, position=5),
    ),
)


# -- export -------------------------------------------------------------------


def test_a_secret_entry_exports_as_a_declaration_never_as_a_secret(store):
    """The property that makes a manifest safe to commit."""
    store.put("predykt/env-001/VITE_FIREBASE_API_KEY", "AIzaSy-REAL-KEY")
    text = manifest.dumps(WEB_LOCAL)

    assert "AIzaSy-REAL-KEY" not in text
    entry = next(e for e in yaml.safe_load(text)["entries"]
                 if e["key"] == "VITE_FIREBASE_API_KEY")
    assert entry == {"key": "VITE_FIREBASE_API_KEY", "kind": "secret"}


def test_export_carries_config_values_notes_and_flags():
    data = yaml.safe_load(manifest.dumps(WEB_LOCAL))
    assert data["name"] == "web-local"
    assert data["target"] == "web/.env.local"
    assert data["entries"][0] == {
        "key": "VITE_FIREBASE_PROJECT_ID", "kind": "config", "value": "predykt",
    }
    assert data["entries"][1]["note"].startswith("unset this")
    assert data["entries"][3]["from"] == "cred-007:password"
    assert data["entries"][4]["required"] is False


def test_export_keeps_render_order():
    keys = [e["key"] for e in yaml.safe_load(manifest.dumps(WEB_LOCAL))["entries"]]
    assert keys == [e.key for e in WEB_LOCAL.entries]


# -- round trip ---------------------------------------------------------------


def test_a_manifest_round_trips():
    parsed = manifest.loads(manifest.dumps(WEB_LOCAL))
    assert parsed.name == WEB_LOCAL.name
    assert parsed.env == WEB_LOCAL.env
    assert parsed.target == WEB_LOCAL.target
    assert parsed.format == WEB_LOCAL.format
    assert parsed.entries == WEB_LOCAL.entries


# -- load rejects what must not be imported -----------------------------------


def test_a_value_on_a_secret_entry_is_rejected():
    """The DB's CHECK constraint, enforced at the other end of the pipe: someone who
    pastes a secret into a file bound for git gets an error, not an import."""
    with pytest.raises(manifest.ManifestError, match="must not carry a value"):
        manifest.loads(
            "name: web-local\nenv: local\n"
            "entries:\n  - key: API_KEY\n    kind: secret\n    value: sk_live_oops\n"
        )


def test_a_config_entry_without_a_value_is_rejected():
    with pytest.raises(manifest.ManifestError, match="needs a value"):
        manifest.loads("name: w\nenv: local\nentries:\n  - key: K\n    kind: config\n")


def test_a_credential_ref_without_a_from_is_rejected():
    with pytest.raises(manifest.ManifestError, match="needs a 'from:'"):
        manifest.loads("name: w\nenv: local\nentries:\n  - key: K\n    kind: credential-ref\n")


def test_a_credential_ref_to_an_unknown_field_is_rejected():
    with pytest.raises(manifest.ManifestError, match="unknown credential field"):
        manifest.loads("name: w\nenv: local\nentries:\n  - key: K\n"
                       "    kind: credential-ref\n    from: cred-007:token\n")


def test_an_unknown_kind_is_rejected():
    with pytest.raises(manifest.ManifestError, match="unknown entry kind"):
        manifest.loads("name: w\nenv: local\nentries:\n  - key: K\n    kind: plaintext\n")


def test_duplicate_keys_are_rejected():
    with pytest.raises(manifest.ManifestError, match="duplicate keys: K"):
        manifest.loads("name: w\nenv: local\nentries:\n"
                       "  - key: K\n    kind: config\n    value: a\n"
                       "  - key: K\n    kind: config\n    value: b\n")


def test_a_manifest_without_a_name_is_rejected():
    with pytest.raises(manifest.ManifestError, match="needs a name"):
        manifest.loads("env: local\nentries: []\n")


def test_an_unknown_format_is_rejected():
    with pytest.raises(manifest.ManifestError, match="unknown format"):
        manifest.loads("name: w\nenv: local\nformat: toml\nentries: []\n")


def test_not_yaml_is_rejected():
    with pytest.raises(manifest.ManifestError, match="must be a YAML mapping"):
        manifest.loads("- just\n- a\n- list\n")


def test_a_numeric_looking_config_value_is_read_as_text():
    """YAML would hand back `9099` as an int; a .env holds text, and rendering an
    int would crash the writer rather than quote it."""
    parsed = manifest.loads("name: w\nenv: local\nentries:\n"
                            "  - key: PORT\n    kind: config\n    value: 9099\n")
    assert parsed.entries[0].value == "9099"


# -- dispatch -----------------------------------------------------------------


def test_manifest_paths_are_recognised_by_suffix():
    assert manifest.is_manifest_path("env/web-local.yaml") is True
    assert manifest.is_manifest_path("env/web-local.YML") is True
    assert manifest.is_manifest_path("web/.env.example") is False
    assert manifest.is_manifest_path("web/.env.local") is False

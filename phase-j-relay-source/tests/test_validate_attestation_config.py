import json
import sys
import tempfile
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE / "scripts"))
import validate_attestation_config as validator  # noqa: E402


@pytest.fixture
def staging_dir():
    with tempfile.TemporaryDirectory(prefix="relay-config-test-", dir=SOURCE / "tests") as directory:
        yield Path(directory)


def _environment(registry):
    entries = [{
        "router_id": "65ab00000000000000000001",
        "site_id": "65ab00000000000000000002",
        "host": "192.168.88.1",
        "port": 8728,
        "username": "test-router-api",
        "enabled": True,
        "site_active": True,
    }]
    return (
        f"ATTESTATION_ROUTERS_JSON={json.dumps(entries if registry is None else registry)}\n"
        "MIKROTIK_API_PASSWORD_65AB00000000000000000001=test-secret-value\n"
    )


def test_staging_config_validator_checks_allowlist_and_hides_credentials(staging_dir, capsys):
    config = staging_dir / "staging-relay.env"
    config.write_text(_environment(None), encoding="utf-8")

    assert validator.validate(config) == 1
    output = capsys.readouterr().out
    assert "credentials present (values hidden)" in output
    assert "test-secret-value" not in output


def test_staging_config_validator_rejects_missing_router_credential(staging_dir):
    config = staging_dir / "staging-relay.env"
    config.write_text(
        "ATTESTATION_ROUTERS_JSON=" + json.dumps(json.loads(_environment(None).split("=", 1)[1].splitlines()[0])) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Credential value is missing"):
        validator.validate(config)


@pytest.mark.parametrize("field,value", [
    ("enabled", False),
    ("site_active", False),
    ("host", "127.0.0.1"),
])
def test_staging_config_validator_rejects_disabled_or_untrusted_entries(staging_dir, field, value):
    entries = json.loads(_environment(None).split("=", 1)[1].splitlines()[0])
    entries[0][field] = value
    config = staging_dir / "staging-relay.env"
    config.write_text(_environment(entries), encoding="utf-8")

    with pytest.raises(RuntimeError):
        validator.validate(config)

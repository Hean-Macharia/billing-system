#!/usr/bin/env python3
"""Validate a staging relay.env without printing any credential values."""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server  # noqa: E402


def read_assignments(path: Path) -> dict[str, str]:
    values = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid assignment at line {line_number}")
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ValueError(f"Invalid variable name at line {line_number}")
        if key in values:
            raise ValueError(f"Duplicate variable name at line {line_number}")
        values[key] = value.strip()
    return values


def validate(path: Path) -> int:
    values = read_assignments(path)
    raw = values.get("ATTESTATION_ROUTERS_JSON")
    if not raw:
        raise ValueError("ATTESTATION_ROUTERS_JSON is missing")
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("ATTESTATION_ROUTERS_JSON is not valid one-line JSON") from exc
    if not isinstance(entries, list) or not 1 <= len(entries) <= 64:
        raise ValueError("Router registry must contain between 1 and 64 entries")
    routers = [server._validate_allowlist_router(entry) for entry in entries]
    ids = [router["router_id"] for router in routers]
    if len(ids) != len(set(ids)):
        raise ValueError("Router IDs must be unique")
    for router in routers:
        credential_name = router["credential_env"]
        if not values.get(credential_name):
            raise ValueError(f"Credential value is missing for configured router {router['router_id']}")
    print(f"Valid attestation registry: {len(routers)} router entries; credentials present (values hidden).")
    return len(routers)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path, help="Explicit staging relay.env path")
    args = parser.parse_args()
    try:
        validate(args.env_file)
    except (OSError, ValueError, server.AttestationConfigurationError) as exc:
        print(f"Configuration invalid: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

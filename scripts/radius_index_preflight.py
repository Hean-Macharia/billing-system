"""Read-only preflight for RADIUS session/accounting unique indexes.

Uses STAGING_MONGODB_URL only and does not load .env or application settings.
The exact database name must also be provided interactively on the command
line. This script performs only ping, listIndexes, aggregate, and count reads.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.radius_index_migration import (
    ACCOUNTING_COMPOUND_KEYS,
    SESSION_COMPOUND_KEYS,
    SafetyError,
    has_blockers,
    migration_blockers,
    normalize_keys,
    require_confirmation,
    staging_environment,
    staging_target,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-staging-database", required=True, help="Must exactly match STAGING_DATABASE_NAME")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    uri, database_name, expected_host = staging_environment()
    try:
        host, database_name = staging_target(uri, database_name, expected_host)
        require_confirmation(args.confirm_staging_database, database_name)
    except SafetyError as exc:
        print(f"SAFETY STOP: {exc}", file=sys.stderr)
        return 2

    client = MongoClient(uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
    try:
        client.admin.command("ping")
        db = client[database_name]
        indexes = {}
        for collection_name in ("radius_sessions", "radius_accounting"):
            indexes[collection_name] = list(db[collection_name].list_indexes())

        print("Target verified from explicit staging settings:")
        print(json.dumps({"host": host, "database": database_name}, indent=2))
        print("Current indexes (names, key patterns, and options only):")
        for collection_name, collection_indexes in indexes.items():
            safe = []
            for index in collection_indexes:
                item = {
                    "name": index.get("name"),
                    "keys": normalize_keys(index),
                    "unique": bool(index.get("unique", False)),
                }
                for option in ("sparse", "expireAfterSeconds", "partialFilterExpression"):
                    if option in index:
                        item[option] = index[option]
                safe.append(item)
            print(f"{collection_name}: {json.dumps(safe, default=str)}")

        print("Proposed index changes:")
        print(json.dumps({
            "create_or_verify": [
                {"collection": "radius_sessions", "keys": SESSION_COMPOUND_KEYS, "unique": True},
                {"collection": "radius_accounting", "keys": ACCOUNTING_COMPOUND_KEYS, "unique": True},
            ],
            "remove_after_compound_indexes_succeed": [
                {"collection": "radius_sessions", "keys": [("acct_session_id", 1)], "unique": True,
                 "reason": "legacy global uniqueness conflicts with NAS-scoped session identity"},
            ],
        }, indent=2))

        summary = migration_blockers({
            "radius_sessions": db["radius_sessions"],
            "radius_accounting": db["radius_accounting"],
        })
        print("Duplicate/malformed-key summary (no record values are printed):")
        print(json.dumps(summary, indent=2))
        return 1 if has_blockers(summary) else 0
    except Exception as exc:  # safe category only; driver errors may include host data
        print(f"PREFLIGHT FAILED: {type(exc).__name__}; details withheld", file=sys.stderr)
        return 3
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())

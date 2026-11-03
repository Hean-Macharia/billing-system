"""Explicit, guarded index migration for an isolated staging database only.

This script is intentionally unusable without --execute, an exact staging DB
confirmation, and a verified staging-backup reference. It reads only
STAGING_MONGODB_URL and never loads .env or MONGODB_URL.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pymongo import MongoClient
from pymongo.read_preferences import ReadPreference

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


BACKUP_CONFIRMATION = "STAGING BACKUP VERIFIED"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", required=True,
                        help="Explicitly authorize staging index changes")
    parser.add_argument("--confirm-staging-database", required=True,
                        help="Must exactly match STAGING_DATABASE_NAME")
    parser.add_argument("--backup-confirmation", required=True,
                        help=f'Type exactly: "{BACKUP_CONFIRMATION}"')
    parser.add_argument("--backup-reference", required=True,
                        help="Non-secret identifier for the verified staging backup")
    return parser.parse_args()


def _ensure_unique_index(collection, keys: list[tuple[str, int]], name: str, changes: list[dict]) -> None:
    existing = list(collection.list_indexes())
    matching = [index for index in existing if normalize_keys(index) == keys]
    for index in matching:
        if index.get("unique") is True:
            changes.append({"action": "verified_existing", "collection": collection.name,
                            "name": index.get("name"), "keys": keys})
            return
    for index in matching:
        index_name = index.get("name")
        if index_name and index_name != "_id_":
            collection.drop_index(index_name)
            changes.append({"action": "removed", "collection": collection.name,
                            "name": index_name, "keys": keys,
                            "reason": "same key pattern existed without required uniqueness"})
    created_name = collection.create_index(keys, unique=True, name=name)
    changes.append({"action": "created", "collection": collection.name,
                    "name": created_name, "keys": keys, "unique": True})


def main() -> int:
    args = parse_args()
    uri, database_name, expected_host = staging_environment()
    try:
        host, database_name = staging_target(uri, database_name, expected_host)
        require_confirmation(args.confirm_staging_database, database_name)
    except SafetyError as exc:
        print(f"SAFETY STOP: {exc}", file=sys.stderr)
        return 2
    if args.backup_confirmation != BACKUP_CONFIRMATION or not args.backup_reference.strip():
        print("SAFETY STOP: verified staging backup confirmation and reference are required.", file=sys.stderr)
        return 2

    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        read_preference=ReadPreference.PRIMARY,
    )
    changes: list[dict] = []
    try:
        client.admin.command("ping")
        db = client[database_name]
        summary = migration_blockers({
            "radius_sessions": db["radius_sessions"],
            "radius_accounting": db["radius_accounting"],
        })
        print(f"Verified staging target: host={host}, database={database_name}")
        print("Pre-migration duplicate summary (key values withheld):")
        print(json.dumps(summary, indent=2))
        if has_blockers(summary):
            print("SAFETY STOP: duplicate or malformed keys block the compound unique indexes; no indexes changed.",
                  file=sys.stderr)
            return 4

        sessions = db["radius_sessions"]
        accounting = db["radius_accounting"]
        _ensure_unique_index(
            sessions, SESSION_COMPOUND_KEYS,
            "acct_session_id_1_nas_ip_address_1", changes,
        )
        _ensure_unique_index(
            accounting, ACCOUNTING_COMPOUND_KEYS,
            "acct_session_id_1_nas_ip_address_1", changes,
        )

        # Remove only the exact legacy globally-unique single-field index, and
        # only after both replacement compound indexes have been verified.
        for index in list(sessions.list_indexes()):
            if normalize_keys(index) == [("acct_session_id", 1)] and index.get("unique") is True:
                index_name = index.get("name")
                if index_name and index_name != "_id_":
                    sessions.drop_index(index_name)
                    changes.append({"action": "removed", "collection": "radius_sessions",
                                    "name": index_name, "keys": [("acct_session_id", 1)],
                                    "reason": "replaced by NAS-scoped compound unique index"})

        print("Index operations (backup reference value intentionally withheld):")
        print(json.dumps({
            "backup_verified": True,
            "created": [item for item in changes if item["action"] == "created"],
            "removed": [item for item in changes if item["action"] == "removed"],
            "verified_existing": [item for item in changes if item["action"] == "verified_existing"],
        }, indent=2))
        return 0
    except Exception as exc:  # avoid leaking Mongo URI/credentials in driver messages
        print(f"MIGRATION FAILED: {type(exc).__name__}; inspect staging indexes before retry; details withheld.",
              file=sys.stderr)
        if changes:
            print("Completed index operations before failure:")
            print(json.dumps(changes, indent=2))
        return 5
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())

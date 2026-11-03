"""Shared, defensive helpers for the RADIUS index staging tools.

These scripts deliberately use STAGING_MONGODB_URL only. They never load
.env, read MONGODB_URL, or infer a database from application configuration.
"""
from __future__ import annotations

import os
from urllib.parse import unquote, urlsplit


PRODUCTION_DATABASE_NAMES = {"isp_billing", "isp-billing", "production"}
SESSION_COMPOUND_KEYS = [("acct_session_id", 1), ("nas_ip_address", 1)]
ACCOUNTING_COMPOUND_KEYS = [("acct_session_id", 1), ("nas_ip_address", 1)]


class SafetyError(ValueError):
    """A staging guard failed; no database operation should be attempted."""


def staging_target(uri: str | None, database_name: str | None, expected_host: str | None) -> tuple[str, str]:
    """Validate explicit staging-only connection settings and return host/db.

    The expected host is supplied separately so a typo in the URI cannot
    silently redirect a migration. The URI itself is never included in errors.
    """
    if not uri or not database_name or not expected_host:
        raise SafetyError(
            "Set STAGING_MONGODB_URL, STAGING_DATABASE_NAME, and "
            "STAGING_MONGODB_HOST in the process environment."
        )
    try:
        parsed = urlsplit(uri)
        host = parsed.hostname
    except (TypeError, ValueError):
        raise SafetyError("STAGING_MONGODB_URL is not a valid MongoDB URI.") from None
    if parsed.scheme not in {"mongodb", "mongodb+srv"} or not host:
        raise SafetyError("STAGING_MONGODB_URL must use mongodb:// or mongodb+srv:// and include a host.")
    if host.casefold() != expected_host.strip().casefold():
        raise SafetyError("MongoDB URI hostname does not match STAGING_MONGODB_HOST.")

    name = database_name.strip()
    if not name or name.casefold() in PRODUCTION_DATABASE_NAMES or "staging" not in name.casefold():
        raise SafetyError("STAGING_DATABASE_NAME must be an explicit non-production name containing 'staging'.")
    uri_database = unquote(parsed.path.lstrip("/").split("/", 1)[0]).strip()
    if uri_database and uri_database != name:
        raise SafetyError("MongoDB URI database does not match STAGING_DATABASE_NAME.")
    return host, name


def require_confirmation(provided: str | None, database_name: str) -> None:
    if provided != database_name:
        raise SafetyError("Pass --confirm-staging-database with the exact STAGING_DATABASE_NAME value.")


def normalize_keys(index: dict) -> list[tuple[str, int]]:
    keys = index.get("key", {})
    return [(str(field), int(direction)) for field, direction in keys.items()]


def duplicate_summary(collection, key_expression: dict) -> tuple[int, int]:
    """Return (duplicate group count, extra record count), without key values."""
    pipeline = [
        {"$group": {"_id": key_expression, "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
        {"$group": {"_id": None, "groups": {"$sum": 1}, "extra": {"$sum": {"$subtract": ["$count", 1]}}}},
    ]
    rows = list(collection.aggregate(pipeline, allowDiskUse=False))
    if not rows:
        return 0, 0
    return int(rows[0]["groups"]), int(rows[0]["extra"])


def migration_blockers(collections: dict) -> dict[str, dict[str, int]]:
    """Inspect all values participating in the compound unique indexes.

    Null/missing values are grouped like MongoDB unique compound-key values,
    so malformed legacy rows cannot slip through as an index-build surprise.
    """
    sessions = collections["radius_sessions"]
    accounting = collections["radius_accounting"]
    compound = {
        "acct_session_id": "$acct_session_id",
        "nas_ip_address": {"$ifNull": ["$nas_ip_address", None]},
    }
    session_groups, session_extra = duplicate_summary(sessions, compound)
    accounting_groups, accounting_extra = duplicate_summary(accounting, compound)
    legacy_groups, legacy_extra = duplicate_summary(sessions, {"acct_session_id": "$acct_session_id"})
    malformed_sessions = sessions.count_documents({
        "$or": [
            {"acct_session_id": {"$exists": False}}, {"acct_session_id": None}, {"acct_session_id": ""},
            {"nas_ip_address": {"$exists": False}}, {"nas_ip_address": None}, {"nas_ip_address": ""},
        ]
    })
    malformed_accounting = accounting.count_documents({
        "$or": [
            {"acct_session_id": {"$exists": False}}, {"acct_session_id": None}, {"acct_session_id": ""},
            {"nas_ip_address": {"$exists": False}}, {"nas_ip_address": None}, {"nas_ip_address": ""},
        ]
    })
    return {
        "radius_sessions": {
            "compound_duplicate_groups": session_groups,
            "compound_extra_records": session_extra,
            "legacy_session_id_duplicate_groups": legacy_groups,
            "legacy_session_id_extra_records": legacy_extra,
            "missing_or_empty_key_records": int(malformed_sessions),
        },
        "radius_accounting": {
            "compound_duplicate_groups": accounting_groups,
            "compound_extra_records": accounting_extra,
            "missing_or_empty_key_records": int(malformed_accounting),
        },
    }


def has_blockers(summary: dict[str, dict[str, int]]) -> bool:
    # A duplicate Acct-Session-Id across distinct NAS addresses is valid for
    # the proposed compound key, but is incompatible with a legacy global
    # single-field unique index. Report it for operator review, do not treat it
    # as a compound-index blocker by itself.
    blocking_fields = {"compound_duplicate_groups", "missing_or_empty_key_records"}
    return any(
        any(collection.get(field, 0) > 0 for field in blocking_fields)
        for collection in summary.values()
    )


def staging_environment() -> tuple[str, str, str]:
    return (
        os.environ.get("STAGING_MONGODB_URL", ""),
        os.environ.get("STAGING_DATABASE_NAME", ""),
        os.environ.get("STAGING_MONGODB_HOST", ""),
    )

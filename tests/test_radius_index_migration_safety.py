import pytest
import mongomock

from scripts.radius_index_migration import (
    SafetyError,
    has_blockers,
    normalize_keys,
    migration_blockers,
    require_confirmation,
    staging_target,
)


def test_staging_target_does_not_expose_uri_credentials_and_checks_explicit_host():
    host, database = staging_target(
        "mongodb+srv://sensitive-user:sensitive-password@cluster.example/isp_billing_staging?retryWrites=true",
        "isp_billing_staging",
        "cluster.example",
    )
    assert (host, database) == ("cluster.example", "isp_billing_staging")


@pytest.mark.parametrize(
    ("uri", "database", "expected_host"),
    [
        ("mongodb://host/db", "isp_billing", "host"),
        ("mongodb://host/db", "isp_billing_staging", "other-host"),
        ("mongodb://host/production", "isp_billing_staging", "host"),
        ("https://host/db", "isp_billing_staging", "host"),
        ("mongodb://host/db", "db", "host"),
    ],
)
def test_staging_target_rejects_production_or_mismatched_targets(uri, database, expected_host):
    with pytest.raises(SafetyError):
        staging_target(uri, database, expected_host)


def test_staging_target_requires_separate_staging_host_value():
    with pytest.raises(SafetyError, match="STAGING_MONGODB_URL"):
        staging_target("mongodb://host/db", "isp_billing_staging", "")


def test_database_confirmation_must_match_exact_staging_database_name():
    require_confirmation("isp_billing_staging", "isp_billing_staging")
    with pytest.raises(SafetyError):
        require_confirmation("isp_billing", "isp_billing_staging")


def test_legacy_duplicate_session_ids_are_reported_but_are_not_compound_index_blockers():
    summary = {
        "radius_sessions": {
            "compound_duplicate_groups": 0,
            "legacy_session_id_duplicate_groups": 2,
            "missing_or_empty_key_records": 0,
        },
        "radius_accounting": {"compound_duplicate_groups": 0, "missing_or_empty_key_records": 0},
    }
    assert has_blockers(summary) is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("compound_duplicate_groups", 1),
        ("missing_or_empty_key_records", 1),
    ],
)
def test_compound_duplicate_or_malformed_keys_block_migration(field, value):
    summary = {
        "radius_sessions": {field: value},
        "radius_accounting": {},
    }
    assert has_blockers(summary) is True


def test_normalize_keys_returns_key_pattern_without_index_options():
    assert normalize_keys({"key": {"acct_session_id": 1, "nas_ip_address": 1}, "unique": True}) == [
        ("acct_session_id", 1),
        ("nas_ip_address", 1),
    ]


def test_read_only_duplicate_preflight_distinguishes_legacy_and_compound_collisions():
    db = mongomock.MongoClient()["preflight_test"]
    db.radius_sessions.insert_many([
        {"acct_session_id": "same-on-different-nas", "nas_ip_address": "192.0.2.1"},
        {"acct_session_id": "same-on-different-nas", "nas_ip_address": "192.0.2.2"},
        {"acct_session_id": "duplicate-pair", "nas_ip_address": "192.0.2.3"},
        {"acct_session_id": "duplicate-pair", "nas_ip_address": "192.0.2.3"},
    ])
    db.radius_accounting.insert_many([
        {"acct_session_id": "acct-duplicate", "nas_ip_address": "192.0.2.4"},
        {"acct_session_id": "acct-duplicate", "nas_ip_address": "192.0.2.4"},
    ])

    result = migration_blockers({
        "radius_sessions": db.radius_sessions,
        "radius_accounting": db.radius_accounting,
    })

    assert result["radius_sessions"]["legacy_session_id_duplicate_groups"] == 2
    assert result["radius_sessions"]["compound_duplicate_groups"] == 1
    assert result["radius_accounting"]["compound_duplicate_groups"] == 1
    assert has_blockers(result) is True


def test_missing_compound_index_fields_are_reported_as_blockers():
    db = mongomock.MongoClient()["preflight_missing_fields_test"]
    db.radius_sessions.insert_one({"acct_session_id": "session-without-nas"})

    result = migration_blockers({
        "radius_sessions": db.radius_sessions,
        "radius_accounting": db.radius_accounting,
    })

    assert result["radius_sessions"]["missing_or_empty_key_records"] == 1
    assert has_blockers(result) is True

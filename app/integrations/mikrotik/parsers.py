"""
Parsing helpers for the RouterOS 6.x legacy binary API.

The legacy API (accessed via routeros_api) returns every field as a
string, including numbers ("cpu-load": "5"), booleans
("disabled": "true"), byte counters, and durations
("uptime": "6w2d10h30m5s"). These helpers normalize those strings into
consistent Python types / dicts shared with the RouterOS 7 REST client's
output, so callers (router_service, dashboards) don't need to know which
API generation answered.
"""
from __future__ import annotations

import re
from typing import Any, Optional

_UPTIME_RE = re.compile(
    r"(?:(?P<weeks>\d+)w)?"
    r"(?:(?P<days>\d+)d)?"
    r"(?:(?P<hours>\d+)h)?"
    r"(?:(?P<minutes>\d+)m)?"
    r"(?:(?P<seconds>\d+)s)?"
)


def safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return default


def parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("true", "yes", "1")


def parse_uptime_to_seconds(value: Any) -> Optional[int]:
    """'6w2d10h30m5s' / '10h30m5s' / '45s' -> total seconds."""
    if not value:
        return None
    match = _UPTIME_RE.fullmatch(str(value).strip())
    if not match:
        return None
    parts = match.groupdict()
    if not any(parts.values()):
        return None
    weeks = int(parts["weeks"] or 0)
    days = int(parts["days"] or 0)
    hours = int(parts["hours"] or 0)
    minutes = int(parts["minutes"] or 0)
    seconds = int(parts["seconds"] or 0)
    return weeks * 7 * 86400 + days * 86400 + hours * 3600 + minutes * 60 + seconds


def parse_bytes(value: Any) -> int:
    return safe_int(value, default=0) or 0


def normalize_system_resource(raw: dict) -> dict:
    """Map `/system/resource` legacy output onto REST-client-equivalent field names."""
    return {
        "cpu_load_percent": safe_float(raw.get("cpu-load"), 0.0),
        "free_memory_bytes": safe_int(raw.get("free-memory"), 0),
        "total_memory_bytes": safe_int(raw.get("total-memory"), 0),
        "free_hdd_bytes": safe_int(raw.get("free-hdd-space"), 0),
        "total_hdd_bytes": safe_int(raw.get("total-hdd-space"), 0),
        "uptime_seconds": parse_uptime_to_seconds(raw.get("uptime")),
        "board_name": raw.get("board-name"),
        "version": raw.get("version"),
        "architecture": raw.get("architecture-name"),
        "cpu_count": safe_int(raw.get("cpu-count"), 1),
    }


def normalize_health(raw_rows: list[dict]) -> dict:
    """/system/health rows -> {"voltage": 24.1, "temperature": 38.0}"""
    result: dict[str, float] = {}
    for row in raw_rows or []:
        name = row.get("name")
        value = safe_float(row.get("value"))
        if name and value is not None:
            result[name] = value
    return result


def normalize_active_pppoe(rows: list[dict]) -> list[dict]:
    return [
        {
            "username": row.get("name"),
            "service": row.get("service"),
            "caller_id": row.get("caller-id"),
            "address": row.get("address"),
            "uptime_seconds": parse_uptime_to_seconds(row.get("uptime")),
            "encoding": row.get("encoding"),
            "session_id": row.get(".id") or row.get("id"),
        }
        for row in (rows or [])
    ]


def normalize_active_hotspot(rows: list[dict]) -> list[dict]:
    return [
        {
            "user": row.get("user"),
            "address": row.get("address"),
            "mac_address": row.get("mac-address"),
            "uptime_seconds": parse_uptime_to_seconds(row.get("uptime")),
            "bytes_in": parse_bytes(row.get("bytes-in")),
            "bytes_out": parse_bytes(row.get("bytes-out")),
            "session_id": row.get(".id") or row.get("id"),
        }
        for row in (rows or [])
    ]


def normalize_dhcp_lease(row: dict) -> dict:
    return {
        "address": row.get("address"),
        "mac_address": row.get("mac-address"),
        "hostname": row.get("host-name"),
        "status": row.get("status"),
        "expires_seconds": parse_uptime_to_seconds(row.get("expires-after")),
        "dynamic": parse_bool(row.get("dynamic")),
    }


def normalize_queue(row: dict) -> dict:
    max_limit = row.get("max-limit", "") or ""
    upload, _, download = max_limit.partition("/")
    bytes_field = row.get("bytes", "0/0") or "0/0"
    bytes_parts = bytes_field.split("/")
    return {
        "name": row.get("name"),
        "target": row.get("target"),
        "max_limit_upload": upload or None,
        "max_limit_download": download or None,
        "bytes_in": parse_bytes(bytes_parts[0]) if bytes_parts else 0,
        "bytes_out": parse_bytes(bytes_parts[-1]) if bytes_parts else 0,
        "disabled": parse_bool(row.get("disabled")),
    }


def normalize_interface(row: dict) -> dict:
    return {
        "name": row.get("name"),
        "type": row.get("type"),
        "mtu": safe_int(row.get("mtu")),
        "mac_address": row.get("mac-address"),
        "running": parse_bool(row.get("running")),
        "disabled": parse_bool(row.get("disabled")),
        "rx_bytes": parse_bytes(row.get("rx-byte")),
        "tx_bytes": parse_bytes(row.get("tx-byte")),
    }

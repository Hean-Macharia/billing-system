#!/usr/bin/env python3

import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import socket
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import routeros

LOGGER = logging.getLogger("isp_relay")

HOST = "127.0.0.1"
PORT = int(os.environ.get("ISP_RELAY_PORT", "8765"))
TOKEN_FILE = os.environ.get(
    "ISP_RELAY_TOKEN_FILE", os.path.expanduser("~/.config/isp-relay/relay.token")
)
RELAY_ENV_FILE = os.environ.get(
    "ISP_RELAY_ENV_FILE", os.path.expanduser("~/.config/isp-relay/relay.env")
)

MAX_BODY_SIZE = 16384
MAX_REQUESTS_PER_MINUTE = 60
ATTESTATION_DOMAIN = b"devzen/relay-attestation/v1"
ATTESTATION_ISSUER = "devzen-vps-relay"
ATTESTATION_AUDIENCE = "devzen-billing-api"
ATTESTATION_LIFETIME_SECONDS = 45
ATTESTATION_MAX_REQUEST_AGE_SECONDS = 30
ATTESTATION_FUTURE_TOLERANCE_SECONDS = 5
ATTESTATION_CONCURRENCY = threading.BoundedSemaphore(4)


class AttestationConfigurationError(RuntimeError):
    """Required server-side router, site, or credential configuration is invalid."""


class AttestationObservationError(RuntimeError):
    """Router evidence cannot safely be used for an attestation."""

ALLOWED_ACTIONS = {
    "system.identity",
    "system.resource",
    "system.health",
    "interface.list",
    "pppoe.active",
    "pppoe.secrets",
    "pppoe.add",
    "pppoe.disconnect",
    "hotspot.active",
    "hotspot.users",
    "hotspot.add",
    "hotspot.disconnect",
    "dhcp.leases",
    "queue.list",
}

# Per-client request rate tracking.
rate_lock = threading.Lock()
request_times = {}


def load_token():
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            token = f.read().strip()
    except OSError:
        raise RuntimeError("Relay token file is missing or unreadable.")

    if len(token) < 32:
        raise RuntimeError("Relay token must contain at least 32 characters.")

    return token


def check_rate_limit(client_ip):
    now = time.time()

    with rate_lock:
        recent = [
            t for t in request_times.get(client_ip, [])
            if now - t < 60
        ]

        if len(recent) >= MAX_REQUESTS_PER_MINUTE:
            request_times[client_ip] = recent
            return False

        recent.append(now)
        request_times[client_ip] = recent
        return True


def _relay_env_value(name):
    """Read one named non-secret value without logging other file contents."""
    try:
        with open(RELAY_ENV_FILE, "r", encoding="utf-8") as env_file:
            for line in env_file:
                line = line.rstrip("\r\n")
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        return ""
    return ""


def load_router_password():
    """Preserve the existing relay.env credential source and behavior."""
    password = _relay_env_value("MIKROTIK_API_PASSWORD")
    if not password:
        raise AttestationConfigurationError("Router credentials are not configured")
    return password


def load_router_password_for(router):
    """Read the router credential named by a trusted allowlist entry."""
    credential_env = router.get("credential_env") if isinstance(router, dict) else None
    if credential_env == "MIKROTIK_API_PASSWORD":
        return load_router_password()
    if not isinstance(credential_env, str) or not re.fullmatch(r"MIKROTIK_API_PASSWORD_[0-9A-F]{24}", credential_env):
        raise AttestationConfigurationError("Router credentials are not configured")
    password = _relay_env_value(credential_env)
    if not password:
        raise AttestationConfigurationError("Router credentials are not configured")
    return password


def _validate_allowlist_router(entry):
    """Validate one non-secret router/site entry from trusted relay config."""
    required = {"router_id", "site_id", "host", "port", "username", "enabled", "site_active"}
    if not isinstance(entry, dict) or set(entry) != required:
        raise AttestationConfigurationError("Attestation router allowlist entry is invalid")

    router_id = entry.get("router_id")
    site_id = entry.get("site_id")
    if not isinstance(router_id, str) or not re.fullmatch(r"[0-9a-fA-F]{24}", router_id):
        raise AttestationConfigurationError("Attestation router allowlist identity is invalid")
    if not isinstance(site_id, str) or not re.fullmatch(r"[0-9a-fA-F]{24}", site_id):
        raise AttestationConfigurationError("Attestation router allowlist site is invalid")
    if entry.get("enabled") is not True or entry.get("site_active") is not True:
        raise AttestationConfigurationError("Attestation router/site mapping is disabled or inactive")

    host = entry.get("host")
    if not isinstance(host, str) or len(host) > 64:
        raise AttestationConfigurationError("Attestation router management target is invalid")
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise AttestationConfigurationError("Attestation router management target must be a configured IP address") from exc
    if not address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified:
        raise AttestationConfigurationError("Attestation router management target is not an approved private address")

    port = entry.get("port")
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise AttestationConfigurationError("Attestation router management port is invalid")
    username = entry.get("username")
    if not isinstance(username, str) or not username or len(username) > 64:
        raise AttestationConfigurationError("Attestation router API username is invalid")

    normalized_router_id = router_id.lower()
    return {
        "router_id": normalized_router_id,
        "site_id": site_id.lower(),
        "host": str(address),
        "port": port,
        "username": username,
        "enabled": True,
        "site_active": True,
        "credential_env": "MIKROTIK_API_PASSWORD_" + normalized_router_id.upper(),
    }


def load_attestation_routers():
    """Load an explicit multi-router allowlist, with legacy single-router support.

    ATTESTATION_ROUTERS_JSON contains only router/site IDs and management
    targets. Credentials remain separate in relay.env under a router-specific
    variable name. The request body can never supply or override a target.
    """
    raw_registry = _relay_env_value("ATTESTATION_ROUTERS_JSON")
    if raw_registry:
        try:
            entries = json.loads(raw_registry)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AttestationConfigurationError("Attestation router allowlist is malformed") from exc
        if not isinstance(entries, list) or not entries or len(entries) > 64:
            raise AttestationConfigurationError("Attestation router allowlist is empty or too large")
        routers = [_validate_allowlist_router(entry) for entry in entries]
        ids = [router["router_id"] for router in routers]
        if len(ids) != len(set(ids)):
            raise AttestationConfigurationError("Attestation router allowlist contains duplicate identities")
        return routers

    router_id = _relay_env_value("ATTESTATION_ROUTER_ID")
    site_id = _relay_env_value("ATTESTATION_SITE_ID")
    router_enabled = _relay_env_value("ATTESTATION_ROUTER_ENABLED").lower()
    site_active = _relay_env_value("ATTESTATION_SITE_ACTIVE").lower()
    if not router_id or not site_id:
        raise AttestationConfigurationError("Attestation router/site mapping is not configured")
    if router_enabled != "true" or site_active != "true":
        raise AttestationConfigurationError("Attestation router/site mapping is disabled or inactive")
    if not re.fullmatch(r"[0-9a-fA-F]{24}", router_id) or not re.fullmatch(r"[0-9a-fA-F]{24}", site_id):
        raise AttestationConfigurationError("Attestation router/site mapping is invalid")
    import routeros
    return [{
        "router_id": router_id.lower(),
        "site_id": site_id.lower(),
        "host": routeros.HOST,
        "port": routeros.PORT,
        "username": routeros.USERNAME,
        "enabled": True,
        "site_active": True,
        "credential_env": "MIKROTIK_API_PASSWORD",
    }]


def load_attestation_router(router_id=None, site_id=None):
    """Resolve exactly one configured router/site pair; never select by order."""
    routers = load_attestation_routers()
    if router_id is None and site_id is None and len(routers) == 1:
        return routers[0]
    if not isinstance(router_id, str) or not isinstance(site_id, str):
        raise AttestationConfigurationError("Router and site identity are required for multi-router attestation")
    matches = [
        router for router in routers
        if router["router_id"] == router_id.lower() and router["site_id"] == site_id.lower()
    ]
    if len(matches) != 1:
        raise PermissionError("Requested router/site is not configured")
    return matches[0]


def _validate_attestation_request(request, router):
    expected_fields = {"router_id", "site_id", "client_ip", "client_mac", "nonce", "requested_at"}
    if set(request) != expected_fields:
        raise ValueError("Invalid attestation request fields")
    if request.get("router_id") != router["router_id"] or request.get("site_id") != router["site_id"]:
        raise PermissionError("Requested router/site is not configured")

    client_ip = request.get("client_ip")
    if not isinstance(client_ip, str) or not client_ip:
        raise ValueError("Client IP is required by the current FastAPI contract")
    try:
        parsed_ip = ipaddress.ip_address(client_ip)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid client IP") from exc
    if not parsed_ip.is_private or parsed_ip.is_loopback or parsed_ip.is_link_local or parsed_ip.is_multicast:
        raise ValueError("Client IP must be a private HotSpot address")
    request["client_ip"] = str(parsed_ip)

    mac = request.get("client_mac")
    if not isinstance(mac, str) or not re.fullmatch(r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", mac):
        raise ValueError("Invalid client MAC")
    request["client_mac"] = mac.replace("-", ":").upper()

    nonce = request.get("nonce")
    if not isinstance(nonce, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", nonce):
        raise ValueError("Invalid attestation nonce")

    requested_at = request.get("requested_at")
    if not isinstance(requested_at, int) or isinstance(requested_at, bool):
        raise ValueError("Invalid attestation request timestamp")
    now = int(time.time())
    if requested_at > now + ATTESTATION_FUTURE_TOLERANCE_SECONDS or now - requested_at > ATTESTATION_MAX_REQUEST_AGE_SECONDS:
        raise ValueError("Attestation request is expired")
    return request


def sign_attestation(attestation, relay_token):
    if not isinstance(relay_token, str) or len(relay_token) < 32:
        raise AttestationConfigurationError("Relay signing key is not configured")
    derived_key = hmac.new(
        relay_token.encode("utf-8"), ATTESTATION_DOMAIN, hashlib.sha256
    ).digest()
    canonical = json.dumps(
        attestation, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hmac.new(derived_key, canonical, hashlib.sha256).hexdigest()


def create_attestation(request, router, observation, relay_token, now=None):
    """Build the exact signed response consumed by the FastAPI verifier."""
    issued_at = int(time.time() if now is None else now)
    client_ip = observation.get("client_ip")
    observed = observation.get("observed")
    evidence = observation.get("evidence")
    if not isinstance(observed, bool) or not isinstance(evidence, dict):
        raise ValueError("Router observation is malformed")
    if observed:
        if not isinstance(client_ip, str):
            raise ValueError("A positive observation must include the observed client IP")
        try:
            parsed_ip = ipaddress.ip_address(client_ip)
        except ValueError as exc:
            raise ValueError("Router returned an invalid observed IP") from exc
        if not parsed_ip.is_private or parsed_ip.is_loopback or parsed_ip.is_link_local or parsed_ip.is_multicast:
            raise ValueError("Router returned a non-private observed IP")
        client_ip = str(parsed_ip)
        if request["client_ip"] and client_ip != request["client_ip"]:
            raise AttestationObservationError("Router observation does not match the requested IP")
        if (
            evidence.get("dhcp_lease_match") is not True
            or str(evidence.get("dhcp_lease_status", "")).lower() != "bound"
            or evidence.get("hotspot_host_match") is not True
        ):
            raise AttestationObservationError("Router observation evidence is incomplete")
    elif client_ip is not None:
        try:
            parsed_ip = ipaddress.ip_address(client_ip)
        except (TypeError, ValueError) as exc:
            raise ValueError("Router returned an invalid negative-observation IP") from exc
        if not parsed_ip.is_private or parsed_ip.is_loopback or parsed_ip.is_link_local or parsed_ip.is_multicast:
            raise ValueError("Router returned a non-private negative-observation IP")
        client_ip = str(parsed_ip)
        if request["client_ip"] and client_ip != request["client_ip"]:
            raise AttestationObservationError("Router negative observation identifies another IP")
    else:
        # The current FastAPI verifier requires a syntactically valid client
        # IP even for signed negative observations. Bind the negative result to
        # the original request hint; this value is never treated as observed.
        client_ip = request["client_ip"]

    attestation = {
        "issuer": ATTESTATION_ISSUER,
        "audience": ATTESTATION_AUDIENCE,
        "router_id": router["router_id"],
        "site_id": router["site_id"],
        "client_ip": client_ip,
        "client_mac": request["client_mac"],
        "issued_at": issued_at,
        "expires_at": issued_at + ATTESTATION_LIFETIME_SECONDS,
        "nonce": request["nonce"],
        "observed": observed,
        "evidence": {
            "dhcp_lease_match": evidence.get("dhcp_lease_match") is True,
            "dhcp_lease_status": str(evidence.get("dhcp_lease_status") or "missing").lower(),
            "hotspot_host_match": evidence.get("hotspot_host_match") is True,
            "observation_age_seconds": evidence.get("observation_age_seconds"),
        },
    }
    age = attestation["evidence"]["observation_age_seconds"]
    if not isinstance(age, (int, float)) or isinstance(age, bool) or age < 0 or age > 15:
        raise AttestationObservationError("Router observation is stale or has no trustworthy timestamp")
    return {"attestation": attestation, "signature": sign_attestation(attestation, relay_token)}


def handle_attestation(request, relay_token, router=None, observer=None, now=None):
    """Validate, query exactly the configured RouterOS target, then sign."""
    configured_router = router or load_attestation_router(
        request.get("router_id"), request.get("site_id")
    )
    normalized = _validate_attestation_request(request, configured_router)
    if observer is None:
        import routeros
        password = (
            load_router_password()
            if configured_router.get("credential_env") == "MIKROTIK_API_PASSWORD"
            else load_router_password_for(configured_router)
        )
        observation = routeros.observe_hotspot_client(
            normalized["client_ip"],
            normalized["client_mac"],
            password,
            router=configured_router,
        )
    else:
        # Injectable observer keeps isolated tests independent of RouterOS.
        observation = observer(
            normalized["client_ip"], normalized["client_mac"], "mock-only"
        )
    if now is not None:
        return create_attestation(normalized, configured_router, observation, relay_token, now=now)
    return create_attestation(normalized, configured_router, observation, relay_token)


class RelayHandler(BaseHTTPRequestHandler):
    server_version = "ISPRelay"
    sys_version = ""

    def log_message(self, fmt, *args):
        # Avoid logging authorization headers or request bodies.
        print(
            time.strftime("%Y-%m-%d %H:%M:%S"),
            self.client_address[0],
            fmt % args,
            flush=True,
        )

    def log_event(self, event, category, status, exception=None):
        LOGGER.warning(
            "event=%s category=%s http_status=%s correlation_id=%s exception_class=%s",
            event,
            category,
            status,
            getattr(self, "request_id", "unknown"),
            type(exception).__name__ if exception else "none",
            extra={
                "event": event,
                "category": category,
                "http_status": status,
                "request_id": getattr(self, "request_id", "unknown"),
                "exception_class": type(exception).__name__ if exception else None,
            },
        )

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if getattr(self, "request_id", None):
            self.send_header("X-Correlation-ID", self.request_id)
        self.end_headers()
        self.wfile.write(body)

    def set_request_id(self):
        supplied = self.headers.get("X-Correlation-ID", "")
        self.request_id = supplied if re.fullmatch(r"[a-fA-F0-9]{32}", supplied) else uuid.uuid4().hex

    def do_GET(self):
        self.set_request_id()
        if self.path != "/health":
            self.send_json(404, {"success": False, "message": "Not found"})
            return

        self.send_json(200, {
            "success": True,
            "service": "isp-router-relay",
            "status": "running",
        })

    def do_POST(self):
        self.set_request_id()
        if self.path not in {"/api/v1/router/relay", "/api/v1/router/attest"}:
            self.send_json(404, {"success": False, "message": "Not found"})
            return

        try:
            expected_token = load_token()
        except RuntimeError:
            self.send_json(503, {
                "success": False,
                "message": "Relay authentication is not configured",
            })
            return

        auth = self.headers.get("Authorization", "")
        supplied_token = ""

        if auth.startswith("Bearer "):
            supplied_token = auth[7:].strip()

        if not hmac.compare_digest(supplied_token, expected_token):
            self.send_json(401, {
                "success": False,
                "message": "Unauthorized",
            })
            return

        client_ip = self.client_address[0]
        if not check_rate_limit(client_ip):
            self.send_json(429, {
                "success": False,
                "message": "Rate limit exceeded",
            })
            return

        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("application/json"):
            self.send_json(415, {
                "success": False,
                "message": "Content-Type must be application/json",
            })
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0

        if length <= 0 or length > MAX_BODY_SIZE:
            self.send_json(413, {
                "success": False,
                "message": "Invalid request body size",
            })
            return

        try:
            raw = self.rfile.read(length)
            request = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {
                "success": False,
                "message": "Invalid JSON",
            })
            return

        if not isinstance(request, dict):
            self.send_json(400, {
                "success": False,
                "message": "JSON body must be an object",
            })
            return

        if self.path == "/api/v1/router/attest":
            if not ATTESTATION_CONCURRENCY.acquire(timeout=1):
                self.send_json(503, {"success": False, "message": "Attestation capacity is busy"})
                return
            try:
                result = handle_attestation(request, expected_token)
                claims = result["attestation"]
                LOGGER.info(
                    "event=router_attestation_completed outcome=%s router_id=%s site_id=%s correlation_id=%s",
                    "observed" if claims["observed"] else "not_observed",
                    claims["router_id"],
                    claims["site_id"],
                    self.request_id,
                    extra={
                        "event": "router_attestation_completed",
                        "outcome": "observed" if claims["observed"] else "not_observed",
                        "router_id": claims["router_id"],
                        "site_id": claims["site_id"],
                        "request_id": self.request_id,
                    },
                )
                self.send_json(200, result)
            except routeros.RouterOSAuthenticationError as exc:
                self.log_event("router_attestation_failed", "router_authentication_failed", 502, exc)
                self.send_json(502, {"success": False, "message": "Router API authentication failed"})
            except PermissionError as exc:
                self.log_event("router_attestation_rejected", "router_site_not_allowlisted", 403, exc)
                self.send_json(403, {"success": False, "message": "Requested router/site is not configured"})
            except ValueError as exc:
                self.log_event("router_attestation_rejected", "invalid_request", 400, exc)
                self.send_json(400, {"success": False, "message": "Invalid attestation request"})
            except AttestationConfigurationError as exc:
                self.log_event("router_attestation_failed", "invalid_configuration", 503, exc)
                self.send_json(503, {"success": False, "message": "Router attestation is not configured"})
            except AttestationObservationError as exc:
                self.log_event("router_attestation_failed", "invalid_router_observation", 502, exc)
                self.send_json(502, {"success": False, "message": "Router attestation could not be verified"})
            except TimeoutError as exc:
                self.log_event("router_attestation_failed", "router_timeout", 504, exc)
                self.send_json(504, {"success": False, "message": "Router did not respond in time"})
            except Exception as exc:
                if isinstance(exc, routeros.RouterOSConnectionError) or isinstance(exc, OSError):
                    category, status, message = "router_connection_failed", 502, "Router could not be reached"
                elif isinstance(exc, routeros.RouterOSCommandError):
                    category, status, message = "router_command_failed", 502, "Router observation command failed"
                elif isinstance(exc, routeros.RouterOSObservationError):
                    category, status, message = "invalid_router_observation", 502, "Router observation could not be verified"
                else:
                    category, status, message = "internal_attestation_error", 502, "Router attestation could not be verified"
                self.log_event("router_attestation_failed", category, status, exc)
                self.send_json(status, {"success": False, "message": message})
            finally:
                ATTESTATION_CONCURRENCY.release()
            return

        action = request.get("action")
        payload = request.get("payload", {})

        if not isinstance(action, str) or action not in ALLOWED_ACTIONS:
            self.send_json(400, {
                "success": False,
                "message": "Unsupported router action",
            })
            return

        if not isinstance(payload, dict):
            self.send_json(400, {
                "success": False,
                "message": "Payload must be an object",
            })
            return

        # Load the router credential without shell expansion or logging it.
        # Never accept arbitrary RouterOS command strings from HTTP callers.
        try:
            credential = ""

            with open(RELAY_ENV_FILE, "r", encoding="utf-8") as env_file:
                for line in env_file:
                    line = line.rstrip("\r\n")
                    if line.startswith("MIKROTIK_API_PASSWORD="):
                        credential = line.split("=", 1)[1]
                        break

            if not credential:
                self.send_json(503, {
                    "success": False,
                    "message": "Router credentials are not configured",
                })
                return

            os.environ["MIKROTIK_API_PASSWORD"] = credential

            from routeros import run_action

            result = run_action(action, payload)

            self.send_json(200, {
                "success": True,
                "data": result,
            })

        except NotImplementedError:
            self.send_json(501, {
                "success": False,
                "message": "This router operation is not enabled yet",
            })

        except (ValueError, TypeError):
            self.send_json(400, {
                "success": False,
                "message": "Invalid router action parameters",
            })

        except Exception as exc:
            # Keep credentials, network details, and tracebacks out of HTTP.
            self.log_event("router_management_failed", "router_operation_failed", 502, exc)
            self.send_json(502, {
                "success": False,
                "message": "Router operation failed",
            })


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    load_token()

    server = ThreadingHTTPServer((HOST, PORT), RelayHandler)
    server.daemon_threads = True
    server.request_queue_size = 20

    print(
        "ISP relay listening on http://%s:%s" % (HOST, PORT),
        flush=True,
    )

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nStopping relay.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

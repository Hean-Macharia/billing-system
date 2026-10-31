import ipaddress
import re
import socket
import threading
import time

HOST = "10.30.0.10"
PORT = 8728
USERNAME = "isp-billing-api"
TIMEOUT = 8


def encode_length(length):
    if length < 0x80:
        return bytes([length])
    if length < 0x4000:
        length |= 0x8000
        return bytes([(length >> 8) & 255, length & 255])
    if length < 0x200000:
        length |= 0xC00000
        return bytes([
            (length >> 16) & 255,
            (length >> 8) & 255,
            length & 255,
        ])
    if length < 0x10000000:
        length |= 0xE0000000
        return bytes([
            (length >> 24) & 255,
            (length >> 16) & 255,
            (length >> 8) & 255,
            length & 255,
        ])
    return b"\xf0" + length.to_bytes(4, "big")


def read_exact(sock, count):
    result = bytearray()
    while len(result) < count:
        chunk = sock.recv(count - len(result))
        if not chunk:
            raise ConnectionError("Router closed the connection")
        result.extend(chunk)
    return bytes(result)


def read_length(sock):
    first = read_exact(sock, 1)[0]

    if first < 0x80:
        return first
    if first < 0xC0:
        return ((first & 0x3F) << 8) | read_exact(sock, 1)[0]
    if first < 0xE0:
        return ((first & 0x1F) << 16) | int.from_bytes(
            read_exact(sock, 2), "big"
        )
    if first < 0xF0:
        return ((first & 0x0F) << 24) | int.from_bytes(
            read_exact(sock, 3), "big"
        )
    if first == 0xF0:
        return int.from_bytes(read_exact(sock, 4), "big")

    raise ValueError("Invalid RouterOS API length")


class RouterOS:
    def __init__(self, password, timeout=TIMEOUT):
        self.password = password
        self.timeout = timeout
        self.sock = None
        self.lock = threading.Lock()

    def connect(self):
        self.sock = socket.create_connection(
            (HOST, PORT), timeout=self.timeout
        )
        self.sock.settimeout(self.timeout)

        # RouterOS 6.49 supports legacy API login.
        reply = self._command([
            "/login",
            "=name=" + USERNAME,
            "=password=" + self.password,
        ])

        if any(sentence[0] == "!trap" for sentence in reply if sentence):
            raise PermissionError("RouterOS API authentication failed")

        if not any(sentence[0] == "!done" for sentence in reply if sentence):
            raise ConnectionError("RouterOS login response was unexpected")

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def _command(self, words):
        for word in words:
            encoded = word.encode("utf-8")
            self.sock.sendall(encode_length(len(encoded)) + encoded)
        self.sock.sendall(b"\x00")

        sentences = []

        while True:
            sentence = []
            while True:
                length = read_length(self.sock)
                if length == 0:
                    break
                sentence.append(
                    read_exact(self.sock, length).decode(
                        "utf-8", "replace"
                    )
                )

            if sentence:
                sentences.append(sentence)

            if sentence and sentence[0] in ("!done", "!trap", "!fatal"):
                if sentence[0] in ("!trap", "!fatal"):
                    message = next(
                        (
                            word.split("=", 2)[2]
                            for word in sentence
                            if word.startswith("=message=")
                        ),
                        "RouterOS command failed",
                    )
                    raise RuntimeError(message)
                return sentences

    def query(self, command, attributes=None):
        with self.lock:
            reply = self._command([command] + (attributes or []))

        rows = []
        for sentence in reply:
            if not sentence or sentence[0] != "!re":
                continue

            row = {}
            for word in sentence[1:]:
                if word.startswith("="):
                    parts = word.split("=", 2)
                    if len(parts) == 3:
                        row[parts[1]] = parts[2]
            rows.append(row)

        return rows


def run_action(action, payload=None):
    """
    Execute only predefined operations.
    The caller must authenticate the relay request before calling this.
    """
    payload = payload or {}

    import os

    password = os.environ.get("MIKROTIK_API_PASSWORD", "")
    if not password:
        raise RuntimeError("MIKROTIK_API_PASSWORD is not configured")

    api = RouterOS(password)

    try:
        api.connect()

        if action == "system.identity":
            rows = api.query("/system/identity/print")
            return rows[0] if rows else {}

        if action == "system.resource":
            rows = api.query("/system/resource/print")
            return rows[0] if rows else {}

        if action == "system.health":
            return api.query("/system/health/print")

        if action == "interface.list":
            return api.query("/interface/print")

        if action == "pppoe.active":
            return api.query("/ppp/active/print")

        if action == "pppoe.secrets":
            # Return only fields needed for billing management.
            rows = api.query("/ppp/secret/print")
            allowed = {
                ".id", "name", "service", "profile",
                "disabled", "comment", "remote-address",
            }
            return [
                {key: value for key, value in row.items() if key in allowed}
                for row in rows
            ]

        if action == "hotspot.active":
            return api.query("/ip/hotspot/active/print")

        if action == "hotspot.users":
            rows = api.query("/ip/hotspot/user/print")
            allowed = {
                ".id", "name", "profile", "disabled",
                "comment", "limit-uptime", "uptime",
            }
            return [
                {key: value for key, value in row.items() if key in allowed}
                for row in rows
            ]

        if action == "dhcp.leases":
            return api.query("/ip/dhcp-server/lease/print")

        if action == "queue.list":
            return api.query("/queue/simple/print")

        # Modifying actions are deliberately not enabled yet.
        if action in {
            "pppoe.add", "pppoe.disconnect",
            "hotspot.add", "hotspot.disconnect",
        }:
            raise NotImplementedError(
                "Modifying router actions are not enabled yet"
            )

        raise ValueError("Unsupported router action")

    finally:
        api.close()


def _normalize_mac(value):
    normalized = str(value or "").strip().replace("-", ":").upper()
    if not re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", normalized):
        raise ValueError("Invalid client MAC")
    return normalized


def _normalize_ip(value):
    try:
        address = ipaddress.ip_address(str(value).strip())
    except ValueError as exc:
        raise ValueError("Invalid client IP") from exc
    if not address.is_private or address.is_loopback or address.is_link_local or address.is_multicast:
        raise ValueError("Client IP must be a private HotSpot address")
    return str(address)


def observe_hotspot_client(client_ip, client_mac, password):
    """Read the DHCP lease and HotSpot host tables from this configured router.

    This operation is deliberately bound to the module's fixed, existing
    RouterOS management target. Callers cannot provide a host or command.
    The returned observation contains no router credentials or unrelated
    RouterOS fields.
    """
    normalized_mac = _normalize_mac(client_mac)
    normalized_ip = _normalize_ip(client_ip) if client_ip else None
    api = RouterOS(password, timeout=3)
    started = time.monotonic()
    try:
        api.connect()
        leases = api.query("/ip/dhcp-server/lease/print")
        hosts = api.query("/ip/hotspot/host/print")

        def matching_rows(rows):
            matches = []
            for row in rows:
                row_mac = str(row.get("mac-address") or "").strip().replace("-", ":").upper()
                try:
                    row_ip = str(ipaddress.ip_address(str(row.get("address") or "").strip()))
                except ValueError:
                    continue
                ip_match = normalized_ip is not None and row_ip == normalized_ip
                mac_match = row_mac == normalized_mac
                if ip_match or mac_match:
                    matches.append((row, row_ip, row_mac))
            return matches

        lease_matches = matching_rows(leases)
        if len(lease_matches) > 1:
            raise RuntimeError("Ambiguous DHCP observation")

        lease = lease_matches[0] if lease_matches else None
        observed_ip = normalized_ip
        if lease:
            lease_row, lease_ip, lease_mac = lease
            if observed_ip is None:
                observed_ip = lease_ip
            elif lease_ip != observed_ip or lease_mac != normalized_mac:
                # A conflicting record for either requested identifier is not
                # equivalent to an ordinary absent-client result.
                if lease_ip == observed_ip or lease_mac == normalized_mac:
                    raise RuntimeError("Conflicting DHCP observation")
                lease = None

        if observed_ip is None:
            # FastAPI accepts a signed negative observation without an IP only
            # when its original challenge also had no IP. Positive matches
            # always resolve their IP from the same bound DHCP lease.
            host_matches = []
        else:
            host_matches = matching_rows(hosts)
        if len(host_matches) > 1:
            raise RuntimeError("Ambiguous HotSpot host observation")
        host = host_matches[0] if host_matches else None

        lease_status = str((lease[0].get("status") if lease else "missing") or "missing").lower()
        lease_current = bool(lease and lease_status == "bound" and lease[1] == observed_ip and lease[2] == normalized_mac)
        host_current = bool(host and host[1] == observed_ip and host[2] == normalized_mac)

        if host and not host_current:
            raise RuntimeError("DHCP and HotSpot observations conflict")
        if host_current and not lease_current:
            raise RuntimeError("HotSpot observation has no current matching bound DHCP lease")
        else:
            observed = lease_current and host_current

        return {
            "client_ip": observed_ip,
            "observed": bool(observed),
            "evidence": {
                "dhcp_lease_match": bool(lease_current),
                "dhcp_lease_status": lease_status,
                "hotspot_host_match": bool(host_current),
                # The values are read directly from live, non-cached RouterOS
                # tables. The signed timestamp is generated immediately after
                # both replies, so its snapshot age at issuance is zero.
                "observation_age_seconds": 0,
            },
            "query_elapsed_seconds": round(time.monotonic() - started, 3),
        }
    finally:
        api.close()

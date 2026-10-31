from app.integrations.mikrotik.parsers import normalize_dhcp_lease


def test_normalizes_routeros_dhcp_lease_fields_and_expiry():
    lease = normalize_dhcp_lease({
        "address": "192.168.10.24",
        "mac-address": "AA:BB:CC:DD:EE:FF",
        "host-name": "customer-phone",
        "status": "bound",
        "expires-after": "1h2m3s",
    })

    assert lease == {
        "address": "192.168.10.24",
        "mac_address": "AA:BB:CC:DD:EE:FF",
        "hostname": "customer-phone",
        "status": "bound",
        "expires_seconds": 3723,
        "dynamic": False,
    }


def test_normalizes_rest_and_relay_lease_aliases():
    lease = normalize_dhcp_lease({
        "address": "192.168.10.25",
        "mac_address": "AA:BB:CC:DD:EE:00",
        "hostname": "living-room-tv",
        "status": "bound",
        "expires_seconds": 60,
    })

    assert lease["mac_address"] == "AA:BB:CC:DD:EE:00"
    assert lease["hostname"] == "living-room-tv"
    assert lease["expires_seconds"] == 60

from app.integrations.mpesa.daraja_client import DarajaClient


class _Response:
    def raise_for_status(self):
        return None

    @staticmethod
    def json():
        return {"ResponseCode": "0", "CheckoutRequestID": "mock-checkout"}


def test_stk_push_log_masks_customer_phone(monkeypatch, caplog):
    client = DarajaClient(
        consumer_key="test-key",
        consumer_secret="test-secret",
        shortcode="123456",
        passkey="test-passkey",
        callback_url="https://example.invalid/callback",
    )
    monkeypatch.setattr(client, "_get_access_token", lambda: "mock-token")
    monkeypatch.setattr("app.integrations.mpesa.daraja_client.requests.post", lambda *args, **kwargs: _Response())

    with caplog.at_level("INFO", logger="app.integrations.mpesa.daraja_client"):
        client.initiate_stk_push(
            phone_number="254712345678",
            amount=5,
            account_reference="TEST-ORDER",
            transaction_desc="Test purchase",
        )

    messages = [record.getMessage() for record in caplog.records]
    stk_log = next(message for message in messages if message.startswith("STK Push ->"))
    assert "***5678" in stk_log
    assert "254712345678" not in stk_log

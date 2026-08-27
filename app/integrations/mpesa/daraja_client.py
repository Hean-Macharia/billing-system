"""Safaricom M-Pesa Daraja API client.

Handles OAuth, STK Push initiation, and STK query.
Supports both sandbox and production environments.
"""
import base64
import json
from datetime import datetime, timezone
from typing import Optional

import requests

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class DarajaClient:
    """Low-level Safaricom Daraja API client."""

    def __init__(
        self,
        consumer_key: Optional[str] = None,
        consumer_secret: Optional[str] = None,
        shortcode: Optional[str] = None,
        passkey: Optional[str] = None,
        callback_url: Optional[str] = None,
        environment: str = "sandbox",
    ):
        self.consumer_key = consumer_key or getattr(settings, "MPESA_CONSUMER_KEY", "")
        self.consumer_secret = consumer_secret or getattr(settings, "MPESA_CONSUMER_SECRET", "")
        self.shortcode = shortcode or getattr(settings, "MPESA_SHORTCODE", "")
        self.passkey = passkey or getattr(settings, "MPESA_PASSKEY", "")
        self.callback_url = callback_url or getattr(settings, "MPESA_CALLBACK_URL", "")
        self.environment = environment or getattr(settings, "MPESA_ENVIRONMENT", "sandbox")

        self.base_url = (
            "https://api.safaricom.co.ke"
            if self.environment == "production"
            else "https://sandbox.safaricom.co.ke"
        )

    def _get_access_token(self) -> str:
        """Fetch OAuth access token from Safaricom."""
        if not self.consumer_key or not self.consumer_secret:
            raise RuntimeError("M-Pesa consumer key/secret not configured")

        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        auth_str = f"{self.consumer_key}:{self.consumer_secret}"
        auth_b64 = base64.b64encode(auth_str.encode()).decode()

        resp = requests.get(url, headers={"Authorization": f"Basic {auth_b64}"}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["access_token"]

    def _generate_password(self, timestamp: str) -> str:
        """Generate Base64 encoded password: Shortcode+Passkey+Timestamp."""
        raw = f"{self.shortcode}{self.passkey}{timestamp}"
        return base64.b64encode(raw.encode()).decode()

    def initiate_stk_push(
        self,
        phone_number: str,
        amount: float,
        account_reference: str,
        transaction_desc: str,
        callback_url: Optional[str] = None,
    ) -> dict:
        """Initiate M-Pesa STK Push (Lipa na M-Pesa Online).

        Returns:
            dict with MerchantRequestID and CheckoutRequestID
        """
        token = self._get_access_token()
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d%H%M%S")
        password = self._generate_password(timestamp)
        cb_url = callback_url or self.callback_url

        if not cb_url:
            raise RuntimeError("M-Pesa callback URL not configured")

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone_number,
            "PartyB": self.shortcode,
            "PhoneNumber": phone_number,
            "CallBackURL": cb_url,
            "AccountReference": account_reference[:20],  # Safaricom limit
            "TransactionDesc": transaction_desc[:50],      # Safaricom limit
        }

        url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        logger.info(f"STK Push -> {phone_number} | KES {amount} | Ref: {account_reference}")
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # Safaricom returns format:
        # {"MerchantRequestID":"...","CheckoutRequestID":"...","ResponseCode":"0","ResponseDescription":"..."}
        if data.get("ResponseCode") != "0":
            raise RuntimeError(f"Safaricom STK error: {data.get('ResponseDescription', 'Unknown')}")

        logger.info(f"STK Push accepted: CheckoutRequestID={data.get('CheckoutRequestID')}")
        return data

    def query_stk_status(self, checkout_request_id: str) -> dict:
        """Query status of an STK Push transaction."""
        token = self._get_access_token()
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d%H%M%S")
        password = self._generate_password(timestamp)

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        }

        url = f"{self.base_url}/mpesa/stkpushquery/v1/query"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
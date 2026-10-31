# 13 — Customer guide

## Connect to HotSpot Wi-Fi

1. Join the DEVZEN CREATIONS Wi-Fi network and open the captive portal (documented path `/hotspot/`).
2. Allow the portal to use the IP/MAC hints supplied by the router. Never type another device's MAC to bypass checks.
3. Choose a package shown by the backend and follow the M-Pesa prompt. Do not repeat payment while the status is pending; check the displayed status or contact support.
4. After backend-confirmed settlement, use the voucher credentials delivered by the portal and submit them to the MikroTik login flow. Payment confirmation means the purchase settled; it is not proof Internet access is working until the router grants a session.

If identification, payment or login fails, keep the transaction reference and contact the ISP. Do not share your M-Pesa PIN or account password with support.

## Customer portal

Use `/portal/` with credentials supplied through the ISP's supported onboarding process. The API exposes dashboard, subscription, usage, invoice, payment, receipt and support functions subject to account data. Self-registration and password reset are not available in this backend; do not submit credentials to unofficial forms. Usage/remaining balance may be unavailable if the backend has no corresponding data.

Support details must be confirmed from the active business contact configuration; this repository contains legacy/example contact references and does not prove current service contacts.

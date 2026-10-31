# 03 — API documentation

The complete method/path/schema inventory is maintained at [`../frontend-endpoint-inventory.md`](../frontend-endpoint-inventory.md) and is the authoritative local contract reference. The app's OpenAPI contract contains 146 operations across 112 paths; four internal RADIUS routes are secret-gated and intentionally not exposed in OpenAPI.

## Route families

| Family | Prefix / representative paths | Access pattern |
|---|---|---|
| Authentication and staff | `/api/v1/auth/*` | JWT; staff/user permissions on protected operations. Login, refresh, current user, password change and user administration exist. |
| Customers, plans, subscriptions | `/api/v1/customers`, `/services`, `/packages`, `/subscriptions` | Authenticated and permission-checked. List APIs use server pagination. |
| Billing | `/api/v1/invoices`, `/payments`, `/mpesa/*` | Authenticated administrative operations; public provider callback is separately verified by provider query before settlement. |
| HotSpot | `/api/v1/hotspot/*` | Public catalog/device/purchase/status flows plus protected plan administration. Trusted context is carried through the documented header contract. |
| Vouchers | `/api/v1/vouchers/*` | Staff CRUD/batch controls and limited public validity check. No balance endpoint exists. |
| Network | `/api/v1/routers/*`, `/sites/*`, `/radius/*` | Staff endpoints require permissions. Router credentials are not returned. Internal RADIUS calls use `X-RADIUS-API-Secret`. |
| Customer portal | `/api/v1/portal/*` | Customer identity dependency; dashboard, profile, subscription/usage, invoice/payment, notifications, receipt and support flows. Registration returns 503 pending proof of ownership. |
| Support/automation/dashboard | `/api/v1/support/*`, `/automation/*`, `/dashboard/*` | Role/permission protected except explicitly public operations. Automation endpoints can trigger consequential work and should not be casually exposed. |

## Response and pagination

Use the actual Pydantic schemas and endpoint inventory; do not assume a universal response envelope. Most list views support `page`/`limit`; inspect each route for exact filters and response shape. API exceptions are mapped centrally. RADIUS validation errors are filtered to avoid echoing sensitive attributes.

## Known absent contracts

No customer password-reset endpoint, trusted self-registration flow, advertising enquiry endpoint, voucher-balance endpoint, dedicated reports API, reseller API, or general outbound SMS endpoint was found. The RADIUS disconnect operation queues a marker and does not send a MikroTik CoA. These are backend dependencies, not frontend features to simulate.

## Security contract

Frontend checks are presentation only. Backend dependencies enforce authorization. Never send M-Pesa or RouterOS credentials from the browser. See endpoint inventory before implementing or changing an API call.

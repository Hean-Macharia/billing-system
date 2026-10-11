# Architecture overview

This project is structured around the required ISP architecture:

- FastAPI handles business logic and API endpoints.
- MongoDB stores operational data such as users, customers, invoices, subscriptions, vouchers, and sessions.
- FreeRADIUS accepts MikroTik authentication/accounting over UDP 1812/1813 and calls FastAPI's private REST handlers over the internal Compose network.
- FastAPI validates the RADIUS service secret, checks users/vouchers in MongoDB, and records accounting/session usage.
- Nginx serves the hotspot, admin, and customer portal frontends and blocks public access to the internal RADIUS auth/accounting handlers.
- MikroTik routers provide network enforcement and session monitoring.
- M-Pesa Daraja handles payment initiation and callback reconciliation.

## Typical workflow

1. Admin creates a site, router, package, and customer.
2. Customer receives a service and invoice.
3. Invoice payment is completed through M-Pesa.
4. Payment callback is validated and recorded.
5. Subscription is activated or renewed.
6. RADIUS authorization allows the customer to connect.
7. Accounting events record session usage.

## Production notes

- Keep secrets in environment variables; do not commit them.
- Give the MikroTik RADIUS transport and FreeRADIUS-to-API REST calls separate secrets.
- Keep UDP RADIUS ports on a VPN/private interface and firewall them to the NAS source address.
- Use MongoDB indexes for hot queries such as customer number, phone, invoice number, and voucher code.
- Use background jobs for billing cleanup and subscription enforcement.
- Keep route handlers thin and push business logic into services.

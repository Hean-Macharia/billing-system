# FastAPI Endpoint Inventory

**Source:** OpenAPI generated from the checked-in `create_app()` route registry on 2026-10-31. This is a source inventory; it does not verify deployed runtime configuration.

Responses use the shared `{success, message, data}` envelope where route helpers apply it; paginated lists may also include `meta`. Some endpoints return files or special protocol payloads as noted. Access policy is enforced by route dependencies; this table records contract shape, not a substitute for backend authorization.

| Method | Path | Request body | Query/path inputs | Success response |
|---|---|---|---|---|
| `POST` | `/api/v1/auth/register` | UserRegister: email, username, full_name, password, phone, role | — | 201 object |
| `POST` | `/api/v1/auth/login` | UserLogin: email, password | — | 200 object |
| `POST` | `/api/v1/auth/refresh` | RefreshTokenRequest: refresh_token | — | 200 object |
| `POST` | `/api/v1/auth/logout` | — | x-refresh-token (header) | 200 object |
| `GET` | `/api/v1/auth/me` | — | — | 200 object |
| `PATCH` | `/api/v1/auth/me` | UserUpdate: full_name, phone, avatar_url | — | 200 object |
| `POST` | `/api/v1/auth/change-password` | PasswordChange: current_password, new_password | — | 200 object |
| `GET` | `/api/v1/auth/users` | — | role (query), status (query), search (query), page (query), limit (query) | 200 object |
| `GET` | `/api/v1/auth/users/{user_id}` | — | user_id (path) | 200 object |
| `PATCH` | `/api/v1/auth/users/{user_id}/status` | — | user_id (path), status (query) | 200 object |
| `POST` | `/api/v1/customers` | CustomerCreate: customer_number, customer_code, full_name, email, phone, alt_phone, customer_type, address, installation_address, company_name, company_reg_no, tax_pin, industry, contacts, current_package, billing_day, auto_billing, payment_method, referral_source, notes, tags, user_id | — | 201 object |
| `GET` | `/api/v1/customers` | — | status (query), customer_type (query), search (query), assigned_to (query), package_id (query), page (query), limit (query) | 200 object |
| `GET` | `/api/v1/customers/{customer_id}` | — | customer_id (path) | 200 object |
| `PATCH` | `/api/v1/customers/{customer_id}` | CustomerUpdate: full_name, email, phone, alt_phone, customer_type, status, address, installation_address, company_name, company_reg_no, tax_pin, industry, contacts, current_package, billing_day, auto_billing, payment_method, outstanding_balance, credit_limit, referral_source, notes, tags, assigned_to | customer_id (path) | 200 object |
| `DELETE` | `/api/v1/customers/{customer_id}` | — | customer_id (path) | 200 object |
| `PATCH` | `/api/v1/customers/{customer_id}/status` | — | customer_id (path), status (query) | 200 object |
| `POST` | `/api/v1/customers/{customer_id}/package` | JSON object | customer_id (path) | 200 object |
| `GET` | `/api/v1/customers/code/{customer_code}` | — | customer_code (path) | 200 object |
| `POST` | `/api/v1/services` | ServicePlanCreate: plan_code, name, description, service_type, download_speed_mbps, upload_speed_mbps, burst_speed_mbps, base_price_kes, setup_fee_kes, equipment_fee_kes, billing_cycle, features, fair_usage_policy, data_cap_gb, minimum_contract_months, early_termination_fee_kes, grace_period_days, target_customer_types, tags, popularity_score | — | 201 object |
| `GET` | `/api/v1/services` | — | status (query), service_type (query), search (query), page (query), limit (query) | 200 object |
| `GET` | `/api/v1/services/{plan_id}` | — | plan_id (path) | 200 object |
| `PATCH` | `/api/v1/services/{plan_id}` | ServicePlanUpdate: name, description, status, download_speed_mbps, upload_speed_mbps, burst_speed_mbps, base_price_kes, setup_fee_kes, equipment_fee_kes, billing_cycle, features, fair_usage_policy, data_cap_gb, minimum_contract_months, early_termination_fee_kes, grace_period_days, target_customer_types, tags, popularity_score | plan_id (path) | 200 object |
| `DELETE` | `/api/v1/services/{plan_id}` | — | plan_id (path) | 200 object |
| `POST` | `/api/v1/subscriptions` | SubscriptionCreate: customer_id, plan_id, start_date, end_date, monthly_price_kes, setup_fee_kes, equipment_fee_kes, discount_kes, discount_reason, contract_months, auto_renew, notes, tags | — | 201 object |
| `GET` | `/api/v1/subscriptions` | — | customer_id (query), plan_id (query), status (query), page (query), limit (query) | 200 object |
| `GET` | `/api/v1/subscriptions/{sub_id}` | — | sub_id (path) | 200 object |
| `PATCH` | `/api/v1/subscriptions/{sub_id}` | SubscriptionUpdate: status, monthly_price_kes, discount_kes, discount_reason, auto_renew, end_date, next_billing_date, notes, tags, assigned_technician_id, installation_notes, pppoe_username, pppoe_password, ip_address, vlan_id | sub_id (path) | 200 object |
| `POST` | `/api/v1/subscriptions/{sub_id}/cancel` | — | sub_id (path), reason (query) | 200 object |
| `POST` | `/api/v1/subscriptions/{sub_id}/install` | — | sub_id (path) | 200 object |
| `POST` | `/api/v1/subscriptions/{sub_id}/invoice` | — | sub_id (path) | 200 object |
| `POST` | `/api/v1/invoices` | InvoiceCreate: customer_id, subscription_id, invoice_date, due_date, line_items, tax_rate_percent, discount_kes, notes, terms | — | 201 object |
| `GET` | `/api/v1/invoices` | — | customer_id (query), status (query), overdue_only (query), page (query), limit (query) | 200 object |
| `GET` | `/api/v1/invoices/overdue` | — | — | 200 object |
| `GET` | `/api/v1/invoices/{invoice_id}` | — | invoice_id (path) | 200 object |
| `PATCH` | `/api/v1/invoices/{invoice_id}` | InvoiceUpdate: status, due_date, notes, terms, footer_message | invoice_id (path) | 200 object |
| `POST` | `/api/v1/invoices/{invoice_id}/send` | — | invoice_id (path) | 200 object |
| `POST` | `/api/v1/payments` | PaymentCreate: customer_id, invoice_id, subscription_id, amount_kes, payment_method, payment_method_details, payment_date, notes, transaction_id, mpesa_phone_number, mpesa_receipt_number, bank_reference, bank_name, received_by, receipt_number | — | 201 object |
| `GET` | `/api/v1/payments` | — | customer_id (query), invoice_id (query), status (query), payment_method (query), page (query), limit (query) | 200 object |
| `GET` | `/api/v1/payments/{payment_id}` | — | payment_id (path) | 200 object |
| `PATCH` | `/api/v1/payments/{payment_id}` | PaymentUpdate: status, notes, mpesa_receipt_number, mpesa_result_code, mpesa_result_desc, bank_reference, reconciled | payment_id (path) | 200 object |
| `POST` | `/api/v1/payments/{payment_id}/confirm` | — | payment_id (path) | 200 object |
| `POST` | `/api/v1/payments/mpesa/callback` | — | — | 200 object |
| `POST` | `/api/v1/mpesa/stk-push` | StkPushRequest: phone_number, amount, account_reference, transaction_desc, customer_id, invoice_id, subscription_id | — | 201 object |
| `POST` | `/api/v1/mpesa/callback` | — | — | 200 object |
| `POST` | `/api/v1/mpesa/query` | StkQueryRequest: checkout_request_id | — | 200 object |
| `POST` | `/api/v1/mpesa/reconcile` | — | max_age_hours (query) | 200 object |
| `GET` | `/api/v1/mpesa/transactions` | — | customer_id (query), status (query), invoice_id (query), page (query), limit (query) | 200 object |
| `GET` | `/api/v1/mpesa/transactions/{tx_id}` | — | tx_id (path) | 200 object |
| `POST` | `/api/v1/radius/nas` | NasClientCreate: name, site_id, ip_address, nas_identifier, secret, description, location, nas_type, coa_port | — | 201 object |
| `GET` | `/api/v1/radius/nas` | — | site_id (query), status (query), page (query), limit (query) | 200 object |
| `GET` | `/api/v1/radius/nas/{nas_id}` | — | nas_id (path) | 200 object |
| `PATCH` | `/api/v1/radius/nas/{nas_id}` | NasClientUpdate: name, site_id, ip_address, nas_identifier, secret, description, location, nas_type, status, coa_port | nas_id (path) | 200 object |
| `DELETE` | `/api/v1/radius/nas/{nas_id}` | — | nas_id (path) | 200 object |
| `POST` | `/api/v1/radius/users` | RadiusUserCreate: username, password, user_type, customer_id, service_id, subscription_id, site_id, package_id, framed_ip_address, framed_ip_pool, session_timeout, idle_timeout, simultaneous_use, rate_limit | — | 201 object |
| `GET` | `/api/v1/radius/users` | — | customer_id (query), site_id (query), user_type (query), status (query), page (query), limit (query) | 200 object |
| `GET` | `/api/v1/radius/users/{user_id}` | — | user_id (path) | 200 object |
| `PATCH` | `/api/v1/radius/users/{user_id}` | RadiusUserUpdate: password, framed_ip_address, framed_ip_pool, session_timeout, idle_timeout, simultaneous_use, rate_limit, status, package_id | user_id (path) | 200 object |
| `DELETE` | `/api/v1/radius/users/{user_id}` | — | user_id (path) | 200 object |
| `POST` | `/api/v1/radius/users/sync/{subscription_id}` | — | subscription_id (path) | 200 object |
| `GET` | `/api/v1/radius/sessions` | — | site_id (query), nas_ip (query), page (query), limit (query) | 200 object |
| `POST` | `/api/v1/radius/sessions/{session_id}/terminate` | — | session_id (path) | 200 object |
| `POST` | `/api/v1/routers` | RouterCreate: name, site_id, nas_client_id, ip_address, api_type, port, username, password, use_ssl, ssl_verify, model_name, wan_interface, lan_interface, pppoe_server_interface, hotspot_interface, ip_pools, radius_server_ip, radius_secret, location, notes | — | 201 object |
| `GET` | `/api/v1/routers` | — | site_id (query), status (query), page (query), limit (query) | 200 object |
| `GET` | `/api/v1/routers/{router_id}` | — | router_id (path) | 200 object |
| `PATCH` | `/api/v1/routers/{router_id}` | RouterUpdate: name, site_id, nas_client_id, ip_address, api_type, port, username, password, use_ssl, ssl_verify, model_name, wan_interface, lan_interface, pppoe_server_interface, hotspot_interface, ip_pools, radius_server_ip, radius_secret, status, location, notes | router_id (path) | 200 object |
| `DELETE` | `/api/v1/routers/{router_id}` | — | router_id (path) | 200 object |
| `GET` | `/api/v1/routers/relay/health` | — | — | 200 object |
| `POST` | `/api/v1/routers/{router_id}/test` | — | router_id (path) | 200 object |
| `POST` | `/api/v1/routers/{router_id}/health` | — | router_id (path) | 200 object |
| `GET` | `/api/v1/routers/{router_id}/health` | — | router_id (path) | 200 object |
| `POST` | `/api/v1/routers/health/refresh-all` | — | — | 200 object |
| `GET` | `/api/v1/routers/{router_id}/interfaces` | — | router_id (path) | 200 object |
| `GET` | `/api/v1/routers/{router_id}/active-users` | — | router_id (path) | 200 object |
| `GET` | `/api/v1/routers/{router_id}/dhcp-leases` | — | router_id (path) | 200 object |
| `GET` | `/api/v1/routers/{router_id}/queues` | — | router_id (path) | 200 object |
| `POST` | `/api/v1/routers/{router_id}/pppoe-users` | — | router_id (path), username (query), password (query), profile (query) | 201 object |
| `POST` | `/api/v1/routers/{router_id}/pppoe-users/{username}/disconnect` | — | router_id (path), username (path) | 200 object |
| `GET` | `/api/v1/vouchers/public/check/{code}` | — | code (path) | 200 object |
| `POST` | `/api/v1/vouchers/batches` | VoucherBatchCreate: batch_name, site_id, router_id, quantity, code_prefix, code_length, plan_id, duration_hours, data_allowance_mb, rate_limit, max_devices, price, currency, activate_on_generation, validity_days_after_generation | — | 201 object |
| `GET` | `/api/v1/vouchers/batches` | — | site_id (query), page (query), limit (query) | 200 object |
| `GET` | `/api/v1/vouchers/batches/{batch_id}` | — | batch_id (path) | 200 object |
| `POST` | `/api/v1/vouchers/batches/{batch_id}/activate` | VoucherActivateRequest: voucher_ids | batch_id (path) | 200 object |
| `GET` | `/api/v1/vouchers/batches/{batch_id}/export` | — | batch_id (path) | 200 JSON/envelope |
| `GET` | `/api/v1/vouchers/batches/{batch_id}/print` | — | batch_id (path), org_name (query) | 200 JSON/envelope |
| `GET` | `/api/v1/vouchers` | — | batch_id (query), status_filter (query), site_id (query), page (query), limit (query) | 200 object |
| `GET` | `/api/v1/vouchers/{voucher_id}` | — | voucher_id (path) | 200 object |
| `POST` | `/api/v1/vouchers/{voucher_id}/activate` | — | voucher_id (path) | 200 object |
| `POST` | `/api/v1/vouchers/{voucher_id}/disable` | VoucherDisableRequest: reason | voucher_id (path) | 200 object |
| `POST` | `/api/v1/vouchers/expire-sweep` | — | — | 200 object |
| `POST` | `/api/v1/hotspot/plans` | HotspotPlanCreate: name, site_id, duration_hours, data_allowance_mb, rate_limit, max_devices, price, currency, description, is_active, sort_order | — | 201 object |
| `GET` | `/api/v1/hotspot/plans` | — | site_id (query), active_only (query) | 200 object |
| `GET` | `/api/v1/hotspot/plans/public` | — | site_id (query), X-Hotspot-Context (header) | 200 object |
| `POST` | `/api/v1/hotspot/devices/attest` | HotspotDeviceAttestationRequest: ip_address, mac_address | — | 200 object |
| `POST` | `/api/v1/hotspot/devices/lookup` | HotspotDeviceLookupRequest: ip_address, mac_address | — | 200 object |
| `POST` | `/api/v1/hotspot/purchase` | HotspotPurchaseRequest: plan_id, phone_number, device_type, device_mac, ip_address | X-Hotspot-Context (header) | 201 object |
| `GET` | `/api/v1/hotspot/purchase/status/{checkout_request_id}` | — | checkout_request_id (path) | 200 object |
| `POST` | `/api/v1/hotspot/free-trial` | HotspotTrialRequest: client_mac, ip_address | — | 201 object |
| `GET` | `/api/v1/hotspot/plans/{plan_id}` | — | plan_id (path) | 200 object |
| `PATCH` | `/api/v1/hotspot/plans/{plan_id}` | HotspotPlanUpdate: name, site_id, duration_hours, data_allowance_mb, rate_limit, max_devices, price, currency, description, is_active, sort_order | plan_id (path) | 200 object |
| `DELETE` | `/api/v1/hotspot/plans/{plan_id}` | — | plan_id (path) | 200 object |
| `GET` | `/api/v1/hotspot/routers/{router_id}/active-sessions` | — | router_id (path) | 200 object |
| `POST` | `/api/v1/portal/auth/register` | PortalRegisterRequest: customer_code, phone, email, password | — | — |
| `GET` | `/api/v1/portal/me` | — | — | 200 object |
| `GET` | `/api/v1/portal/dashboard` | — | — | 200 object |
| `GET` | `/api/v1/portal/subscriptions` | — | — | 200 object |
| `GET` | `/api/v1/portal/usage` | — | days (query) | 200 object |
| `GET` | `/api/v1/portal/notifications` | — | page (query), limit (query) | 200 object |
| `GET` | `/api/v1/portal/invoices` | — | status_filter (query), page (query), limit (query) | 200 object |
| `GET` | `/api/v1/portal/invoices/{invoice_id}` | — | invoice_id (path) | 200 object |
| `GET` | `/api/v1/portal/payments` | — | page (query), limit (query) | 200 object |
| `POST` | `/api/v1/portal/payments/stk-push` | PortalStkPushRequest: invoice_id, phone_number | — | 201 object |
| `GET` | `/api/v1/portal/payments/{payment_id}/receipt` | — | payment_id (path) | 200 JSON/envelope |
| `POST` | `/api/v1/portal/support/tickets` | TicketCreate: subject, category, priority, message | — | 201 object |
| `GET` | `/api/v1/portal/support/tickets` | — | status_filter (query), page (query), limit (query) | 200 object |
| `GET` | `/api/v1/portal/support/tickets/{ticket_id}` | — | ticket_id (path) | 200 object |
| `POST` | `/api/v1/portal/support/tickets/{ticket_id}/reply` | TicketReply: message | ticket_id (path) | 200 object |
| `GET` | `/api/v1/support/tickets` | — | status_filter (query), customer_id (query), assigned_to (query), page (query), limit (query) | 200 object |
| `GET` | `/api/v1/support/tickets/{ticket_id}` | — | ticket_id (path) | 200 object |
| `POST` | `/api/v1/support/tickets/{ticket_id}/reply` | TicketReply: message | ticket_id (path) | 200 object |
| `PATCH` | `/api/v1/support/tickets/{ticket_id}/status` | TicketStatusUpdate: status | ticket_id (path) | 200 object |
| `PATCH` | `/api/v1/support/tickets/{ticket_id}/assign` | TicketAssign: user_id | ticket_id (path) | 200 object |
| `GET` | `/api/v1/automation/status` | — | — | 200 object |
| `GET` | `/api/v1/automation/runs` | — | job_name (query), limit (query) | 200 object |
| `POST` | `/api/v1/automation/run/billing` | — | — | 200 object |
| `POST` | `/api/v1/automation/run/expiry` | — | — | 200 object |
| `POST` | `/api/v1/automation/run/suspension` | — | — | 200 object |
| `POST` | `/api/v1/automation/run/restoration` | — | — | 200 object |
| `POST` | `/api/v1/automation/run/reconciliation` | — | max_age_hours (query) | 200 object |
| `POST` | `/api/v1/automation/run/full-cycle` | — | — | 200 object |
| `GET` | `/api/v1/automation/notifications` | — | notification_type (query), status_filter (query), page (query), limit (query) | 200 object |
| `POST` | `/api/v1/packages` | PackageCreate: name, package_type, download_speed, upload_speed, price, validity_days, mikrotik_profile, max_devices | — | 201 object |
| `GET` | `/api/v1/packages` | — | package_type (query), active_only (query) | 200 object |
| `GET` | `/api/v1/packages/{package_id}` | — | package_id (path) | 200 object |
| `PATCH` | `/api/v1/packages/{package_id}` | PackageUpdate: name, download_speed, upload_speed, price, validity_days, mikrotik_profile, max_devices, status | package_id (path) | 200 object |
| `DELETE` | `/api/v1/packages/{package_id}` | — | package_id (path) | 200 object |
| `GET` | `/api/v1/dashboard/summary` | — | — | 200 object |
| `POST` | `/api/v1/sites` | SiteCreate: name, code, address, latitude, longitude, status, contact_person, contact_phone, notes | — | 201 object |
| `GET` | `/api/v1/sites` | — | status_filter (query), page (query), limit (query) | 200 object |
| `GET` | `/api/v1/sites/{site_id}` | — | site_id (path) | 200 object |
| `PATCH` | `/api/v1/sites/{site_id}` | SiteUpdate: name, code, address, latitude, longitude, status, contact_person, contact_phone, notes | site_id (path) | 200 object |
| `DELETE` | `/api/v1/sites/{site_id}` | — | site_id (path) | 200 object |
| `GET` | `/api/v1/system/info` | — | — | 200 JSON/envelope |
| `GET` | `/` | — | — | 200 JSON/envelope |
| `GET` | `/health` | — | — | 200 JSON/envelope |
| `GET` | `/health/live` | — | — | 200 JSON/envelope |
| `GET` | `/health/ready` | — | — | 200 JSON/envelope |

**Total operations:** 146.

## Internal RADIUS routes excluded from OpenAPI

These routes are deliberately mounted with `include_in_schema=False`; they are machine-to-machine interfaces for FreeRADIUS and are gated by `X-RADIUS-API-Secret`. They are not customer or admin browser endpoints.

| Method | Path | Request body | Success response |
|---|---|---|---|
| `POST` | `/api/v1/radius/auth` | `RadiusAuthRequest` (FreeRADIUS Access-Request attributes) | RADIUS JSON reply, including accept/reject attributes |
| `POST` | `/api/v1/radius/accounting` | `RadiusAccountingRequest` (Start/Interim/Stop attributes) | `204 No Content` |
| `GET` | `/api/v1/radius/sessions/online` | — | `{success, message, data, pagination}` |
| `POST` | `/api/v1/radius/sessions/{session_id}/disconnect` | — | `{success, message}`; marks disconnect pending, does not send MikroTik CoA |

The admin-facing RADIUS session routes are separate and use staff JWT permissions; see the main inventory.

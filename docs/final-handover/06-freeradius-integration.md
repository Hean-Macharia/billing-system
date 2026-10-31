# 06 — FreeRADIUS integration

## Implemented contract

The checked-in FreeRADIUS configuration uses REST integration to the FastAPI internal routes. Authentication and accounting are secret-gated with `X-RADIUS-API-Secret`; API route schemas/services decide voucher or RADIUS-user authorization and persist Start/Interim/Stop accounting. Relevant source is under `radius/`, `app/routes/radius_auth.py`, `app/routes/radius.py`, and `app/services/radius_auth_service.py` / accounting services. Internal endpoints are intentionally not in public OpenAPI.

## Local verification

Mock/unit tests cover RADIUS authentication payloads, voucher restrictions, NAS/site mapping, accounting identity preservation, and duplicate accounting behavior. The full Python suite result is in `09-testing-results.md`. No FreeRADIUS daemon, UDP 1812/1813 exchange, live NAS, or customer login was tested.

## Known gaps and deployment requirements

- `docker-compose.radius.yml` requires an operator-provided `.env.radius`; it is absent from the repository. `.env.radius.example` is illustrative and must not be used unchanged without verifying host, NAS, and shared-secret correspondence.
- RADIUS deployment configuration is not production-verified. Match client address/secret and API secret through approved secret handling; restrict network access to the intended VPN/interface.
- Source verification supports regular password comparison; CHAP/MS-CHAP PPPoE response validation is not established and is a high-priority protocol compatibility issue.
- Session disconnect API marks pending disconnect; no CoA transport is proven. Never tell staff the session is actually disconnected based only on that marker.

Do not change production FreeRADIUS or secrets in this phase. Validate with a staging FreeRADIUS and test NAS before rollout.

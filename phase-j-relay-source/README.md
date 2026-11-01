# Relay attestation staging source

This directory is a local copy of the relay implementation. It is not proof of the code currently running under `isp-relay.service`.

## Configuration

`ATTESTATION_ROUTERS_JSON` is a single-line JSON array containing 1–64 explicitly approved router/site entries. Start from `attestation-routers.example.json`, replace every placeholder only with values confirmed from authorized records, and put the JSON on one line in the **staging** relay environment file. Each router ID must be unique. The relay validates private management IPs, ports, IDs, enabled state and active site state. It will not infer missing IDs or choose a fallback router.

For each entry, add a separate password variable named `MIKROTIK_API_PASSWORD_<UPPERCASE_24_HEX_ROUTER_ID>` to the staging secret environment file. Keep the existing relay token file and bearer authentication architecture. The allowlist JSON must not contain passwords or relay tokens. Do not put secret values in source control or shell transcripts.

The currently verified `10.30.0.10` endpoint can only be assigned to the router/site that authorized records establish. Do not reuse it for Nakuru unless its own approved router record and reachable management target prove that mapping. The relay listener remains loopback-bound; keep RouterOS management traffic on the existing VPN path.

## Validate a staging environment file

Run the validator only against a staging environment file under operator control:

```sh
python3 scripts/validate_attestation_config.py --env-file /path/to/staging/relay.env
```

It validates the allowlist and confirms that each configured router credential is non-empty. It never prints credential values. Do not run it against a production file without explicit operational authorization.

## Build a source-only staging bundle

From Windows PowerShell in this directory:

```powershell
./package-staging.ps1 -OutputPath C:\staging\devzen-relay-attestation.zip
```

The script refuses to overwrite an existing bundle and packages only relay source, the non-deployable template, validator and this readme. It does not package environment files or tokens. Inspect the bundle before any upload. This script does not upload, deploy, restart, or alter any service.

## Endpoint behavior

`POST /api/v1/router/attest` uses the existing bearer token, exact FastAPI request claims, allowlist-selected RouterOS target, read-only DHCP lease and HotSpot host queries, canonical HMAC attestation signing, and safe correlation IDs. Positive observations require a current bound DHCP record and matching HotSpot host on that same router. Router failures produce errors, not signed negative observations. Existing `/health` and `/api/v1/router/relay` operations remain in the source.

Run relay unit tests from the repository root with:

```sh
python -m pytest phase-j-relay-source/tests/test_attestation.py -q
```

The cross-component test imports the FastAPI verifier and should be run from the billing repository with its test dependencies available. Mock tests are not production verification.

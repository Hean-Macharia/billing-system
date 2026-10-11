#!/bin/sh
set -eu

: "${RADIUS_SECRET:?RADIUS_SECRET must be set}"
: "${RADIUS_API_SECRET:?RADIUS_API_SECRET must be set}"
: "${MIKROTIK_NAS_CIDR:?MIKROTIK_NAS_CIDR must be set to the router source IP/CIDR}"
: "${RADIUS_API_BASE_URL:?RADIUS_API_BASE_URL must be set to the FastAPI base URL}"

case "$RADIUS_API_BASE_URL" in
    https://*|http://*) ;;
    *)
        echo "RADIUS_API_BASE_URL must start with https:// or http://" >&2
        exit 1
        ;;
esac

for secret in "$RADIUS_SECRET" "$RADIUS_API_SECRET"; do
    if [ "${#secret}" -ne 64 ]; then
        echo "RADIUS secrets must be exactly 64 hexadecimal characters" >&2
        exit 1
    fi
    case "$secret" in
        *[!0123456789abcdefABCDEF]*)
            echo "RADIUS secrets must be exactly 64 hexadecimal characters" >&2
            exit 1
            ;;
    esac
done

RADIUS_API_BASE_URL="${RADIUS_API_BASE_URL%/}"
sed 's|${RADIUS_API_BASE_URL}|'"${RADIUS_API_BASE_URL}"'|g' \
    /etc/raddb/mods-available/rest \
    > /etc/raddb/mods-available/rest.rendered
mv /etc/raddb/mods-available/rest.rendered /etc/raddb/mods-available/rest

sed \
    -e "s|\${RADIUS_SECRET}|${RADIUS_SECRET}|g" \
    -e "s|\${MIKROTIK_NAS_CIDR}|${MIKROTIK_NAS_CIDR}|g" \
    /etc/raddb/clients.conf.template \
    > /etc/raddb/clients.conf
sed \
    -e "s|\${RADIUS_API_SECRET}|${RADIUS_API_SECRET}|g" \
    /etc/raddb/sites-available/devzen.template \
    > /etc/raddb/sites-available/devzen.rendered
mv /etc/raddb/sites-available/devzen.rendered /etc/raddb/sites-available/devzen

exec "$@"

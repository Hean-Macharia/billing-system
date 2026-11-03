# DEVZEN CREATIONS PPPoE staging template for RouterOS 6.49.x.
# REVIEW ONLY. Every configuration command is commented out intentionally.
# Replace placeholders with verified staging values and review via Safe Mode.
# This file has NOT been executed on production or any router.
#
# Read-only preflight:
/system resource print
/system identity print
/radius print
/ppp aaa print
/ppp profile print
/ppp secret print
/interface pppoe-server server print
/ip pool print
/ppp active print
#
# REQUIRED design inputs (do not infer them):
# <PPPOE_INTERFACE_OR_VLAN>  Dedicated access interface/VLAN, separate from HotSpot.
# <PPPOE_POOL>               Reserved PPPoE client pool, non-overlapping with HotSpot/LAN/VPN.
# <PPPOE_GATEWAY>            Router-side local address for the PPP profile.
# <FREERADIUS_REACHABLE_IP>  Address RouterOS can reach over the approved network/VPN.
# <RADIUS_SECRET>            Retrieve from the approved secret manager; never commit here.
# <NAS_IDENTIFIER>           Must match the configured FreeRADIUS NAS record exactly.
#
# Example configuration commands (uncomment only after values and dependencies are approved):
# /ip pool add name=<PPPOE_POOL> ranges=<CLIENT_POOL_START>-<CLIENT_POOL_END>
# /ppp profile add name=<PPPOE_PROFILE> local-address=<PPPOE_GATEWAY> remote-address=<PPPOE_POOL> only-one=yes change-tcp-mss=yes
# /radius add service=ppp address=<FREERADIUS_REACHABLE_IP> secret=<RADIUS_SECRET> authentication-port=1812 accounting-port=1813 timeout=3s disabled=yes
# /ppp aaa set use-radius=yes accounting=yes interim-update=5m
# /interface pppoe-server server add interface=<PPPOE_INTERFACE_OR_VLAN> service-name=DEVZEN-PPPOE default-profile=<PPPOE_PROFILE> authentication=pap,chap one-session-per-host=yes disabled=yes
#
# Staging validation only after the configuration is applied deliberately:
# - Check RADIUS accepts the exact NAS-IP-Address and NAS-Identifier pair.
# - Verify PAP and CHAP end-to-end; do not enable MS-CHAP until separately supported.
# - Verify the Access-Accept pool/rate/session attributes, accounting Start/Interim/Stop,
#   expiration rejection, and disconnect confirmation.
# - Verify PPPoE pool routing/NAT/DNS independently; this template intentionally does
#   not invent IP ranges, VLANs, firewall rules, NAT, or internet routes.
# - Re-test the existing HotSpot login and accounting path unchanged.

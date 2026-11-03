# DEVZEN CREATIONS - RouterOS 6.49.21 PPPoE staging proposal.
# REVIEW ONLY. All configuration commands below remain commented out.
# Never upload/run against a production router. This file has not been applied.
#
# Required operator-supplied staging values; do not guess or copy production values:
# <PPPOE_INTERFACE_OR_VLAN>  Dedicated subscriber access interface/VLAN, separate from HotSpot.
# <PPPOE_POOL_NAME>          Unique name for the PPP client pool.
# <PPPOE_START>-<PPPOE_END>  Reserved subnet/range, non-overlapping with LAN, HotSpot, L2TP or other pools.
# <PPPOE_GATEWAY>            Local endpoint address on the dedicated PPPoE subnet.
# <PPPOE_DNS_1>              Approved DNS resolver reachable by subscribers.
# <WAN_INTERFACE>            Existing routed Internet uplink interface.
# <WAN_NEXT_HOP>             Existing upstream gateway, only if not already configured.
# <RADIUS_REACHABLE_IP>      FreeRADIUS address reachable from this staging router.
# <RADIUS_SOURCE_IP>         Router source/NAS IP that matches its staging NAS record.
# <STAGING_NAS_IDENTIFIER>   Exact identifier configured for the staging router/NAS.
# <FILTER_FORWARD_DROP_ID>   Existing final forward-chain drop rule number, if one is present.
# <RADIUS_SECRET>            Load via approved secret handling; never save in this file.
#
# Read-only preflight (safe to run on a staging router):
/system resource print
/system identity print
/ip address print
/ip route print
/ip pool print
/ip firewall filter print
/ip firewall nat print
/radius print count-only
/ppp aaa print
/ppp profile print
/ppp secret print count-only
/interface pppoe-server server print
/ppp active print

# ----- STAGING CONFIGURATION PROPOSAL: REVIEW AND SUBSTITUTE FIRST -----
# Dedicated PPP subscriber pool and profile. The values remain placeholders.
# /ip pool add name=<PPPOE_POOL_NAME> ranges=<PPPOE_START>-<PPPOE_END>
# /ppp profile add name=devzen-pppoe-staging local-address=<PPPOE_GATEWAY> remote-address=<PPPOE_POOL_NAME> dns-server=<PPPOE_DNS_1> only-one=yes change-tcp-mss=yes use-compression=no use-encryption=no
#
# Use the existing staging RADIUS shared secret only; service=ppp keeps this
# authorization path independent of the existing HotSpot service setting.
# Do not create a duplicate radius entry if a reviewed staging entry exists.
# /radius add service=ppp address=<RADIUS_REACHABLE_IP> src-address=<RADIUS_SOURCE_IP> secret=<RADIUS_SECRET> authentication-port=1812 accounting-port=1813 timeout=3s disabled=yes comment="DEVZEN PPPoE STAGING"
# /ppp aaa set use-radius=yes accounting=yes interim-update=5m
#
# FastAPI validates PAP and CHAP-MD5 for PPPoE. Do not enable MS-CHAP/MS-CHAPv2.
# Bind only to the dedicated access interface/VLAN, never the HotSpot bridge.
# Keep the local default profile free of static per-subscriber rate limits:
# RADIUS returns per-package Mikrotik-Rate-Limit (upload/download) attributes.
# /interface pppoe-server server add interface=<PPPOE_INTERFACE_OR_VLAN> service-name=DEVZEN-PPPOE default-profile=devzen-pppoe-staging authentication=pap,chap one-session-per-host=yes disabled=yes
#
# Forwarding/firewall example. Review existing rule order and policy first.
# The accept must be placed before the site's existing final forward drop rule;
# do not disable or replace the existing firewall policy.
# /ip firewall filter add chain=forward in-interface=<PPPOE_INTERFACE_OR_VLAN> out-interface=<WAN_INTERFACE> src-address=<PPPOE_SUBNET_CIDR> action=accept place-before=<FILTER_FORWARD_DROP_ID> comment="DEVZEN PPPoE staging subscribers to WAN"
# If the router provides DNS to the PPP pool, add narrowly scoped DNS rules
# before the existing input drop rule after confirming DNS service is enabled:
# /ip firewall filter add chain=input in-interface=<PPPOE_INTERFACE_OR_VLAN> src-address=<PPPOE_SUBNET_CIDR> protocol=udp dst-port=53 action=accept comment="DEVZEN PPPoE staging DNS UDP"
# /ip firewall filter add chain=input in-interface=<PPPOE_INTERFACE_OR_VLAN> src-address=<PPPOE_SUBNET_CIDR> protocol=tcp dst-port=53 action=accept comment="DEVZEN PPPoE staging DNS TCP"
#
# Add NAT only if the router is already the approved subscriber Internet NAT
# gateway. Do not add a duplicate masquerade rule if equivalent coverage exists.
# /ip firewall nat add chain=srcnat src-address=<PPPOE_SUBNET_CIDR> out-interface=<WAN_INTERFACE> action=masquerade comment="DEVZEN PPPoE staging NAT"
#
# Do not add a default route here unless the approved staging topology requires
# it. If needed, verify there is no existing default route before using:
# /ip route add dst-address=0.0.0.0/0 gateway=<WAN_NEXT_HOP> comment="DEVZEN PPPoE staging default route"
# ----- END PROPOSAL -----

# Staging acceptance checks after a separately approved application:
# - NAS-IP-Address and NAS-Identifier resolve to one matching active staging NAS.
# - PAP and CHAP-MD5 work; MS-CHAP is not enabled.
# - Access-Accept returns Framed-Protocol=PPP, Service-Type=Framed-User,
#   Acct-Interim-Interval=300, expiry Session-Timeout, and per-plan
#   Mikrotik-Rate-Limit. Verify direction/rates on RouterOS 6.49.21.
# - Verify one PPP active row, pool assignment, routing, DNS, NAT, and actual
#   Internet traffic from the isolated test subscriber.
# - Verify Accounting Start, Interim-Update, Stop; expired/suspended reject;
#   disconnect is confirmed by RouterOS before reporting success.
# - Repeat HotSpot authentication and accounting regression checks.

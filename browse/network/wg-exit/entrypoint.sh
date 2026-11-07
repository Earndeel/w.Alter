#!/bin/sh
# /run/wg/wg0.conf is mounted read-only from a host tmpfs and removed by the host once we are up.
set -eu
umask 077
mkdir -p /etc/wireguard
DNS=$(sed -n 's/^[[:space:]]*DNS[[:space:]]*=[[:space:]]*//p' /run/wg/wg0.conf | tr -d ' ' | cut -d, -f1)
grep -viE '^[[:space:]]*DNS[[:space:]]*=' /run/wg/wg0.conf > /etc/wireguard/wg0.conf
EP=$(sed -n 's/^[[:space:]]*Endpoint[[:space:]]*=[[:space:]]*//p' /etc/wireguard/wg0.conf | tr -d ' ')
EP_HOST=${EP%:*}; EP_PORT=${EP##*:}
BRIDGE=$(ip -4 -o addr show dev eth0 | awk '{print $4}')

wg-quick up wg0
rm -f /etc/wireguard/wg0.conf                        # keys now only in the kernel
ip rule add pref 100 to "$BRIDGE" lookup main        # replies to the host proxy client stay on eth0
[ -n "$DNS" ] && echo "nameserver $DNS" > /etc/resolv.conf

# Kill switch: on eth0 only the tunnel's own UDP and the proxy's replies to the host may pass.
iptables -P OUTPUT DROP
iptables -A OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -o wg0 -j ACCEPT
iptables -A OUTPUT -o eth0 -p udp -d "$EP_HOST" --dport "$EP_PORT" -j ACCEPT
iptables -A OUTPUT -o eth0 -d "$BRIDGE" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

trap 'wg-quick down wg0 2>/dev/null; exit 0' TERM INT
tinyproxy -d &
wait $!

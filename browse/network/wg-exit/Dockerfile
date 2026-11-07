# Scoped WireGuard exit: the tunnel lives only in this container's network namespace and is
# offered to the host as an HTTP proxy on loopback. Host routing (Tailscale included) is untouched.
FROM alpine:3.20
RUN apk add --no-cache wireguard-tools-wg-quick iptables iproute2 tinyproxy \
 && sed -i 's/cmd sysctl -q net.ipv4.conf.all.src_valid_mark=1/true/' /usr/bin/wg-quick \
 && ! grep -q 'cmd sysctl' /usr/bin/wg-quick
# ^ /proc/sys is read-only in a container; src_valid_mark is set with `docker run --sysctl` instead.
COPY entrypoint.sh /entrypoint.sh
COPY tinyproxy.conf /etc/tinyproxy/tinyproxy.conf
ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]

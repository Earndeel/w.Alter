#!/bin/sh
# (Re)create the Selkies display of Walter's browser: an X server + Selkies web streaming in a container, reachable
# only on the Tailscale address (port 3011, HTTPS). Its X socket is shared with the host through /run/walter-browse-x11
# and linked as display :101, where camoufox-max draws its windows. Managed by walter-browse-display.service.
set -eu
IP="${WALTER_TAILSCALE_IP:-$(tailscale ip -4 | head -1)}"
mkdir -p /run/walter-browse-x11 && chmod 1777 /run/walter-browse-x11
docker rm -f walter-browse-display >/dev/null 2>&1 || true
docker create --name walter-browse-display --restart no \
  -e PUID=0 -e PGID=0 -e TZ=Etc/UTC -e TITLE="Walter — navigateur" -e MAX_RES=1920x1200 \
  -p "$IP:3011:3001" -v /run/walter-browse-x11:/tmp/.X11-unix --shm-size=512m \
  lscr.io/linuxserver/baseimage-selkies:ubuntunoble >/dev/null
echo "walter-browse-display created (https://$IP:3011)"

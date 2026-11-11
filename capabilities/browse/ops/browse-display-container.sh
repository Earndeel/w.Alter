#!/bin/sh
# (Re)create the Selkies display of Walter's browser: an X server + Selkies web streaming in a container, reachable
# only on the Tailscale address (port 3011, HTTPS). Its X socket is shared with the host through /run/walter-browse-x11
# and linked as display :101, where camoufox-max draws its windows. Managed by walter-browse-display.service.
# Since 2026-11-11 the container's definition (image digest, settings, its /config folder) lives with the machine's
# operational services: /services/browse-display/compose.yaml. Stop camoufox-max and cloakbrowser-max first.
set -eu
COMPOSE="${WALTER_BROWSE_DISPLAY_COMPOSE:-/services/browse-display/compose.yaml}"
mkdir -p /run/walter-browse-x11 && chmod 1777 /run/walter-browse-x11
docker rm -f walter-browse-display >/dev/null 2>&1 || true
docker compose -f "$COMPOSE" create >/dev/null
echo "walter-browse-display created from $COMPOSE"

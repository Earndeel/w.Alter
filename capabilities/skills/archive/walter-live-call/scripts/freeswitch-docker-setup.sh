#!/bin/bash
# FreeSWITCH modern ARM64 Docker setup for W.Alter SIP bridge
# Image: walter/freeswitch-modern:arm64 (FS 1.10.12 + mod_audio_stream + mod_opus)

set -euo pipefail

IMAGE="walter/freeswitch-modern:arm64"
CONTAINER="freeswitch-modern"
CONFIG_DIR="/opt/freeswitch-modern/etc/freeswitch"

# 1. Extract default configs from image (first time only)
if [ ! -f "$CONFIG_DIR/freeswitch.xml" ]; then
    mkdir -p "$CONFIG_DIR"
    docker run --rm --platform linux/arm64 --entrypoint /bin/sh "$IMAGE" -lc \
        'tar -c -C /usr/local/freeswitch/etc/freeswitch .' | tar -x -C "$CONFIG_DIR"
    echo "Default configs extracted to $CONFIG_DIR"
fi

# 2. Key config modifications needed:
#    - vars.xml: add after STUN section:
#        <X-PRE-PROCESS cmd="set" data="external_rtp_ip=129.150.52.60"/>
#        <X-PRE-PROCESS cmd="set" data="external_sip_ip=129.150.52.60"/>
#        <X-PRE-PROCESS cmd="set" data="internal_rtp_ip=10.0.0.24"/>
#        <X-PRE-PROCESS cmd="set" data="internal_sip_ip=10.0.0.24"/>
#
#    - sip_profiles/internal.xml: HARDCODE IPs (Sofia doesn't resolve ${var}):
#        <param name="rtp-ip" value="10.0.0.24"/>
#        <param name="sip-ip" value="10.0.0.24"/>
#        <param name="sip-port" value="5070"/>  (Asterisk uses 5060)
#
#    - sip_profiles/external.xml: HARDCODE IPs:
#        <param name="rtp-ip" value="129.150.52.60"/>
#        <param name="sip-ip" value="129.150.52.60"/>
#        <param name="sip-port" value="5090"/>  (Asterisk uses 5080)
#
#    - autoload_configs/modules.conf.xml: add mod_audio_stream
#
#    - Remove sip_profiles/external/example.xml (default gateway)

# 3. Run container (--network host for SIP/RTP)
docker stop "$CONTAINER" 2>/dev/null || true
docker rm "$CONTAINER" 2>/dev/null || true

docker run -d --name "$CONTAINER" --platform linux/arm64 \
    --network host \
    -v "$CONFIG_DIR":/usr/local/freeswitch/etc/freeswitch \
    --entrypoint /usr/local/freeswitch/bin/freeswitch \
    "$IMAGE" \
    -nf -nonat

sleep 10

echo "=== Status ==="
docker exec "$CONTAINER" /usr/local/freeswitch/bin/fs_cli -x 'sofia status'
echo "=== Registration ==="
docker exec "$CONTAINER" /usr/local/freeswitch/bin/fs_cli -x 'sofia status gateway linphone-walter'
echo "=== mod_audio_stream ==="
docker exec "$CONTAINER" /usr/local/freeswitch/bin/fs_cli -x 'module_exists mod_audio_stream'

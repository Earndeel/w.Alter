#!/bin/bash
# Live validation of the NordVPN exits of Walter Browse (2026-11-11). Needs the grant `nordvpn` (account access token).
# Deterministic: no model call. Prints verdicts only (exit IPs are not secrets; no credential is ever printed).
#   1. Browse session explicitly on NordVPN (country A): IP, country, « protected », browser identity from that exit
#   2. second country B in another session; A's session unchanged (no mixing)
#   3. no bypass: exit change refused on a bound session, owner cookies refused, network=proxy refused
#   4. DNS: no plaintext DNS query of the session's hostnames on the host
#   5. tunnel cut: nothing leaves, the session does not move to another exit; exit down = refused
#   6. other exits (default, local, freebox-fr) unchanged; resources released at the end
# Usage: nordvpn-live.sh [A] [B]   (defaults jp us)
set -u
A=${1:-jp}; B=${2:-us}; AU=${A^^}; BU=${B^^}
CAM=http://127.0.0.1:9377; fail=0; T=$(mktemp -d /tmp/nordvpn-live-XXXX)
ok()  { echo "ok    $*"; }
bad() { echo "FAIL  $*"; fail=1; }
insights_js='document.body.innerText'
webrtc_js="(async()=>{try{const pc=new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});pc.createDataChannel('x');const ips=new Set();pc.onicecandidate=e=>{if(e.candidate){const m=e.candidate.candidate.match(/(\\d+\\.\\d+\\.\\d+\\.\\d+)/);if(m)ips.add(m[1])}};await pc.setLocalDescription(await pc.createOffer());await new Promise(r=>setTimeout(r,4000));pc.close();return [...ips].join(',')||'none'}catch(e){return 'blocked:'+e.name}})()"
ident_js="Intl.DateTimeFormat().resolvedOptions().timeZone+'|'+navigator.language"
VM_IP=$(curl -s -m 10 https://api.ipify.org)            # the server's own IP: must never be seen by a site
FR_IP=$(walter instance config browse network.toml | xargs sed -n 's/^public_ip *= *"\([0-9.]*\)".*/\1/p' | head -1)
snap_exits() { { walter-exit-default status 2>&1 | head -3; walter-exit-local status 2>&1 | head -3; walter-wg-exit status freebox-fr 2>&1; } | sed -E 's/[0-9]+(\.[0-9]+)? ?(s|ms)\b//g'; }
snap_exits > $T/exits.before

ev() { walter-browser -s "$1" eval "$2" 2>/dev/null | python3 -c "import json,sys; print(json.loads(sys.stdin.read() or '{}').get('result') or '')" 2>/dev/null; }
jsonfield() { python3 -c "import json,sys; d=json.loads(sys.stdin.read() or '{}'); print(d.get('$1'))" 2>/dev/null; }
browse_insights() {   # session -> JSON text of what NordVPN sees from that browser session
  walter-browser -s "$1" nav https://api.nordvpn.com/v1/helpers/ips/insights >/dev/null 2>&1 || return 1
  ev "$1" "$insights_js"
}

echo "== 1. session on NordVPN $AU"
tcpdump -i any -nn -l -w $T/dns.pcap 'port 53' >/dev/null 2>&1 & TCPD=$!
out=$(walter-wg-exit up nordvpn-$A 2>&1); echo "   $out"
echo "$out" | grep -q "NordVPN protected" && ok "exit nordvpn-$A up, checked through the tunnel" || bad "exit nordvpn-$A did not come up"
walter-browser -s nvt-$A exit nordvpn-$A >/dev/null && walter-browser -s nvt-$A new >/dev/null || bad "browser session nvt-$A not opened"
J=$(browse_insights nvt-$A); IP_A=$(echo "$J" | jsonfield ip)
[ "$(echo "$J" | jsonfield country_code)" = "$AU" ] && ok "browser sees country $AU ($IP_A)" || bad "browser country: $(echo "$J" | jsonfield country_code)"
[ "$(echo "$J" | jsonfield protected)" = "True" ] && ok "NordVPN reports the browser as protected" || bad "browser not protected"
[ -n "$IP_A" ] && [ "$IP_A" != "$VM_IP" ] && [ "$IP_A" != "$FR_IP" ] && ok "exit IP is neither the server's nor the owner's" || bad "exit IP $IP_A"
I=$(ev nvt-$A "$ident_js"); ok "browser identity: $I"
W=$(ev nvt-$A "$webrtc_js")
case ",$W," in *",$VM_IP,"*|*",$FR_IP,"*) bad "WebRTC shows $W";; *) ok "WebRTC: $W (no server or owner IP)";; esac
R=$(PYTHONPATH=/walter/capabilities/browse walter-python -c "
import json; from walter_browse import facade
out = facade._run_router(facade._validate_request({'url': 'https://api.nordvpn.com/v1/helpers/ips/insights', 'content_only': True, 'exit_country': '$A'}))
print(json.dumps(out, ensure_ascii=False, default=str))" 2>&1)
echo "$R" | grep -q "country_code[^A-Z]*$AU" && echo "$R" | grep -q "protected[^a-z]*true" && ok "MCP walter_browse(exit_country=$A) page read leaves from $AU, protected" || bad "MCP read: $(echo "$R" | tr '\n' ' ' | cut -c1-240)"

echo "== 2. second country $BU"
out=$(walter-wg-exit up nordvpn-$B 2>&1); echo "   $out"
walter-browser -s nvt-$B exit nordvpn-$B >/dev/null && walter-browser -s nvt-$B new >/dev/null || bad "browser session nvt-$B not opened"
J=$(browse_insights nvt-$B); IP_B=$(echo "$J" | jsonfield ip)
[ "$(echo "$J" | jsonfield country_code)" = "$BU" ] && ok "second session sees $BU ($IP_B)" || bad "second session country: $(echo "$J" | jsonfield country_code)"
J=$(browse_insights nvt-$A)
[ "$(echo "$J" | jsonfield country_code)" = "$AU" ] && ok "first session still on $AU (no mixing)" || bad "first session moved: $(echo "$J" | jsonfield country_code)"

echo "== 3. no bypass"
walter-browser -s nvt-$A exit nordvpn-$B >/dev/null 2>&1 && bad "exit change accepted on a bound session" || ok "exit change on a bound session refused"
c=$(curl -s -o /dev/null -w '%{http_code}' -X POST $CAM/session/cookies -H 'Content-Type: application/json' -d "{\"userId\":\"nvt-$A\",\"cookies\":[{\"name\":\"t\",\"value\":\"1\",\"domain\":\".example.com\",\"path\":\"/\"}]}")
[ "$c" = 409 ] && ok "owner cookies refused on a NordVPN session (HTTP 409)" || bad "cookies answer HTTP $c"
/walter/capabilities/browse/bin/universal-scraper --url https://example.com --network proxy --country $A --mode camoufox --expected-fields '{"content":["content"]}' --required-field content >/dev/null 2>&1 && bad "network=proxy accepted" || ok "network=proxy refused"
/walter/capabilities/browse/bin/universal-scraper --url https://example.com --network vpn --mode camoufox --expected-fields '{"content":["content"]}' --required-field content >/dev/null 2>&1 && bad "network=vpn without country accepted" || ok "network=vpn without a country refused"

echo "== 4. DNS"
LABEL="walter-dnsleak-$(head -c 6 /dev/urandom | od -An -tx1 | tr -d ' \n')"
walter-browser -s nvt-$B nav "https://$LABEL.example.com/" >/dev/null 2>&1
sleep 3; kill $TCPD 2>/dev/null; wait $TCPD 2>/dev/null
tcpdump -nn -r $T/dns.pcap 2>/dev/null | grep -q "$LABEL" && bad "plaintext DNS query for $LABEL seen on the host" || ok "no plaintext DNS query of the session's hostname on the host"

echo "== 5. tunnel cut on $AU"
docker exec walter-wg-nordvpn-$A ip link del wg0
b=$(curl -s -m 12 -x "$(walter-wg-exit url nordvpn-$A)" https://api.ipify.org)
[ -z "$b" ] && ok "tunnel cut: proxy request gets nothing" || bad "tunnel cut: proxy answered $b"
J=$(browse_insights nvt-$A)
[ -z "$(echo "$J" | jsonfield ip | grep -v None)" ] && ok "tunnel cut: browser session gets no answer (no other route)" || bad "tunnel cut: browser saw $(echo "$J" | jsonfield ip)"
walter-wg-exit down nordvpn-$A >/dev/null
walter-browser -s nvt-$A nav https://api.ipify.org >/dev/null 2>&1 && bad "exit down: session still browses" || ok "exit down: the session is refused, nothing replaces it"

echo "== 6. other exits and release"
for s in nvt-$A nvt-$B; do curl -s -X DELETE $CAM/sessions/$s >/dev/null; done
walter-wg-exit down nordvpn-$B >/dev/null
sleep 2
[ -z "$(docker ps -q --filter label=walter.provider=nordvpn)" ] && ok "no NordVPN container left" || bad "NordVPN containers still up"
grep -c "third-party exit browser through .* closed" /var/log/camoufox-max.log | xargs -I{} echo "      exit browsers closed so far: {}"
snap_exits > $T/exits.after
diff -q $T/exits.before $T/exits.after >/dev/null && ok "default, local and freebox-fr exits unchanged" || { bad "other exits changed:"; diff $T/exits.before $T/exits.after; }
rm -rf $T
echo; [ $fail = 0 ] && echo "ALL OK" || echo "SOME CHECKS FAILED"
exit $fail

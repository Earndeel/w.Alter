# FreeSWITCH side-by-side pivot for W.Alter live calls

Session learning: when Asterisk ExternalMedia/RTP becomes fragile for Gemini Live voice quality, use FreeSWITCH as a side-by-side media switch before retiring Asterisk.

## Durable pattern

- Do not kill Asterisk first. Run FreeSWITCH in parallel on non-conflicting ports, validate SIP/media/Gemini end-to-end, then retire Asterisk only after the FreeSWITCH path is strictly better.
- Keep Asterisk as rollback until these are all true:
  1. outbound call reaches Linphone/iPhone reliably;
  2. codec negotiation uses Opus/wideband rather than PCMU fallback;
  3. RTP/media path is clean;
  4. Gemini hears user speech and answers in real time;
  5. interruption/barge-in is acceptable.

## Known-good side-by-side test shape

- FreeSWITCH can run in Docker with host networking while Asterisk keeps port 5060.
- Use a separate SIP profile/port, e.g. SIP 5070 and a narrow RTP range such as 18000-18100.
- Register the same Linphone account only for test if it does not destabilize production registration.
- First test FreeSWITCH alone with a simple tone/playback call before connecting Gemini.
- In the observed successful baseline, FreeSWITCH -> Linphone negotiated Opus/48000 and completed RTP cleanly, which was already a better base than Asterisk PCMU/ExternalMedia.

## Audio bridge direction

Preferred path for Gemini integration:

1. FreeSWITCH Sofia handles SIP/Opus/WebRTC-like media negotiation.
2. `mod_audio_stream` streams call audio to a local WebSocket bridge.
3. The bridge converts streamed L16/raw audio to Gemini Live input and returns `streamAudio` JSON with base64 raw PCM for playback.

`mod_audio_stream` playback response shape:

```json
{
  "type": "streamAudio",
  "data": {
    "audioDataType": "raw",
    "sampleRate": 16000,
    "audioData": "<base64 signed linear PCM>"
  }
}
```

Supported raw sample-rate extensions in the module include 8000, 16000, 24000, 32000, 48000, and 64000.

## ARM64 build (proven 2026-05-23)

Most public FreeSWITCH Docker images are amd64-only or old. On ARM64 VPS, build from source.

### Dockerfile pattern (FreeSWITCH 1.10.12 + mod_audio_stream, ARM64)

Base: `ubuntu:24.04`. Install build deps, then compile 3 libraries from source before FreeSWITCH itself:

1. **spandsp3** — Ubuntu 24.04 ships spandsp2, but FreeSWITCH v1.10 requires >= 3.0. Clone `https://github.com/freeswitch/spandsp.git`, `./bootstrap.sh && ./configure --prefix=/usr/local && make && make install && ldconfig`.

2. **sofia-sip** — Ubuntu's `libsofia-sip-ua-dev` is too old (< 1.13.17). Clone `https://github.com/freeswitch/sofia-sip.git`, `./autogen.sh && ./configure --prefix=/usr/local && make && make install && ldconfig`.

3. **FreeSWITCH** — Clone `https://github.com/signalwire/freeswitch.git` branch `v1.10.12`. Run `./bootstrap.sh -j`, create minimal `modules.conf` (only: `mod_console`, `mod_logfile`, `mod_commands`, `mod_dptools`, `mod_dialplan_xml`, `mod_sofia`, `mod_event_socket`, `mod_opus`, `mod_sndfile`, `mod_native_file`, `mod_local_stream`, `mod_tone_stream`). Configure with `PKG_CONFIG_PATH=/usr/local/lib/pkgconfig:$PKG_CONFIG_PATH ./configure --prefix=/usr/local/freeswitch --disable-dependency-tracking`. Build and install.

4. **mod_audio_stream** — CMake-based, NOT make. Clone `https://github.com/amigniter/mod_audio_stream.git`, then `cd mod_audio_stream && git submodule update --init --recursive` (libwsc submodule is required). Build with:
   ```
   cmake -B build -DCMAKE_INSTALL_PREFIX=/usr/local/freeswitch -DENABLE_LOCAL=ON \
     -DCMAKE_C_FLAGS="-I/usr/src/freeswitch/src/include" \
     -DCMAKE_CXX_FLAGS="-I/usr/src/freeswitch/src/include"
   cmake --build build -j"$(nproc)"
   cp build/mod_audio_stream.so /usr/local/freeswitch/lib/freeswitch/mod/
   ```

5. **Container**: Use `--network host`. Run FreeSWITCH in foreground: `--entrypoint /usr/local/freeswitch/bin/freeswitch walter/freeswitch-modern:arm64 -nf -nonat`. The default CMD uses `-nc` which daemonizes and Docker thinks the process exited.

### Package requirements (apt)
`libspeex-dev libspeexdsp-dev` (both needed — FreeSWITCH checks for speex codec AND speexdsp), plus standard build tools, cmake, libssl-dev, libopus-dev, libsndfile1-dev, etc.

### Config path
FreeSWITCH default config lives at `/usr/local/freeswitch/etc/freeswitch/`, NOT `conf/`. Mount or copy configs there.

## Config pitfalls (proven 2026-05-23)

### 1. Variables not resolved at profile load time
FreeSWITCH XML preprocessor variables (`${external_sip_ip}`, `${global_codec_prefs}`) are NOT substituted in Sofia profile XML when the SIP UA is created. The profiles load before variable expansion. **Fix: hardcode IPs and codec strings in profile XML files.** Keep `vars.xml` for other sections (dialplan, etc.) but Sofia profiles need literal values.

### 2. Gateway must be in separate file under profile subdirectory
Gateways defined inside the profile XML (`external.xml`) are NOT reliably loaded. Place each gateway in its own XML file under the profile's subdirectory:
```
sip_profiles/external/linphone-walter.xml
```
The profile XML needs a `<gateways>` section with an include:
```xml
<profile name="external">
  <gateways>
    <X-PRE-PROCESS cmd="include" data="external/*.xml"/>
  </gateways>
  ...
</profile>
```

### 3. NAT: bind to private IP, declare public IP externally
On Oracle Cloud, the public IP (129.150.52.60) is NOT a local interface. FreeSWITCH cannot bind to it. Use:
```xml
<param name="rtp-ip" value="10.0.0.24"/>     <!-- local bind -->
<param name="sip-ip" value="10.0.0.24"/>     <!-- local bind -->
<param name="ext-rtp-ip" value="129.150.52.60"/>  <!-- NAT public IP -->
<param name="ext-sip-ip" value="129.150.52.60"/>  <!-- NAT public IP -->
```
Using `rtp-ip=129.150.52.60` fails with "The IP the profile is attempting to bind to is not local to this system."

### 4. Port conflicts with Asterisk
Asterisk uses port 5060. FreeSWITCH internal profile defaults to 5060 too. Change FreeSWITCH to different ports (e.g. 5070 internal, 5090 external). Also change IPv6 profiles to avoid conflicts.

### 5. Oracle Cloud Security List
Non-standard SIP ports (5070, 5090) may not be open in the Oracle Cloud Security List even if iptables allows them. The nftables rules on the host control VM-level filtering, but the Oracle VCN security list controls cloud-level filtering. Registration timeouts with 0 nftables counter packets suggest the outbound REGISTER packets are being sent but responses can't return through the security list.

### 6. Tailscale routing interference
If Tailscale exit node is active on the VPS, SIP traffic may route through the Tailscale interface (100.91.35.121) instead of the public interface. Check with `tcpdump -i enp0s6 -n port 5060` — if source IP shows 100.x.x.x instead of 10.0.0.24, Tailscale is intercepting. Fix: `tailscale set --exit-node=` + explicit route for SIP registrar IP.

### 7. sofia-sip ARM64: handle creation AND UDP sending broken (2026-05-23)
Building sofia-sip from HEAD (`--depth 1` without tag) produces a library where `nua_common.c:121 nh_create_handle()` fails on ARM64. FreeSWITCH starts, profiles load, but gateway registration never happens — the NUA stack can't create handles.

Using tag `v1.13.17` fixes handle creation. But a deeper bug remains: **sofia-sip does not send UDP packets on ARM64**. FreeSWITCH says "Registering linphone-walter", gateway shows TRYING, but `tcpdump -i any -n port 5090` captures zero packets on ALL interfaces (enp0s6, lo, docker0, tailscale0). Tested with `--privileged` container — same result. The `su_sendmsg`/`su_send` functions in sofia-sip silently fail on ARM64 Linux.

System sofia-sip (Ubuntu 24.04, version 1.12.11) is too old — FreeSWITCH 1.10.12 uses symbols added in 1.13.x (`sdp_bw_as`, `sdp_proto_msrp`, `sdp_media_text`). Patching the version check with `sed -i 's/sofia-sip-ua >= 1.13.17/sofia-sip-ua >= 1.12.0/g' configure` allows configure to pass but compilation fails on the missing symbols.

**Current status**: FreeSWITCH SIP is non-functional on ARM64. The only path forward is hybrid: Asterisk handles SIP registration/signaling, FreeSWITCH handles media (Opus) via ESL or direct RTP bridging. Or accept PCMU 8kHz quality with Asterisk alone.

### 8. DNS resolution for sip.linphone.org
`sip.linphone.org` resolves to IPv6 first (`2001:41d0:303:b0d2::4`). VPS without IPv6 connectivity will fail to send SIP. Use the IPv4 address directly in the gateway proxy config: `<param name="proxy" value="176.31.149.179"/>` instead of the hostname.

## Decision rule

If the goal is "quality like WebRTC," stop over-investing in Asterisk RTP/ExternalMedia fixes once FreeSWITCH proves Opus negotiation. Continue with FreeSWITCH + WebSocket audio bridge unless a hard blocker appears.

**ARM64 caveat (2026-05-23)**: FreeSWITCH SIP is blocked by sofia-sip ARM64 UDP sending bug. Until sofia-sip fixes this upstream or a workaround is found, the only viable paths are: (1) Asterisk with PCMU 8kHz (current production), (2) hybrid Asterisk-SIP + FreeSWITCH-media via ESL, or (3) native x86_64 FreeSWITCH (QEMU or different VPS).

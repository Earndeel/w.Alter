# SIP ↔ Gemini Live: WebRTC parity debugging note (2026-05-23)

## Context
Monsieur wanted SIP/Linphone calls to feel like the browser WebRTC path: same speed, same quality, same ability to interrupt and get a response. The SIP path was Asterisk ARI ExternalMedia → Python bridge → Gemini Live → RTP back to Linphone.

## Durable findings

### 1. Do not mistake a dead iPhone for SIP instability
Several outbound failures showed only `100 Trying` / `110 Push sent` and no bridge `Call start`. The immediate cause in this session was the iPhone being out of battery. Before redesigning SIP, verify the phone is powered, Linphone is logged in, and Asterisk receives `180 Ringing`/`200 OK`.

### 2. PCMU/8 kHz is not WebRTC quality
The current Asterisk ExternalMedia bridge uses PCMU/8 kHz toward SIP and resamples Gemini audio. Even with correct RTP pacing, this is narrowband telephony, not browser-quality WebRTC. If Monsieur asks for WebRTC-like quality/latency, treat it as an architecture target: wideband Opus end-to-end or native WebRTC, not more μ-law threshold tuning.

### 3. Packetization matters
Gemini audio chunks must be split into 20 ms PCMU RTP frames: 160-byte payload + 12-byte RTP header. Sending a whole Gemini chunk as one RTP packet produced dirty/broken audio.

### 4. Gemini Live API quirks observed
- `AudioTranscriptionConfig(language_codes=["fr-FR"])` fails: `language_codes parameter is not supported in Gemini API`.
- `explicit_vad_signal=True` fails: `explicit_vad_signal parameter is not supported in Gemini API`.
- `send_realtime_input(activity_start=types.ActivityStart())` and `activity_end=types.ActivityEnd()` are accepted by the Python SDK, but only when `realtime_input_config.automatic_activity_detection.disabled=True`.
- **Critical Python SDK receive loop:** `session.receive()` is a per-turn async iterator; it ends at `turn_complete`. A long-lived bridge must wrap it in `while True: async for response in session.receive(): ...`. Calling it once makes the initial greeting work, then all later Gemini responses are silently unobserved.
- Asterisk ExternalMedia can feed W.Alter's own outbound audio back into the input path in a mixing bridge. Suppress inbound VAD while model audio is being sent (`model_speaking_until`) or Gemini will interrupt itself.
- **Latence SIP Gemini < 2s atteignable** avec ces optimisations VAD: `min_start_frames=2` (~40ms), `min_end_frames=12` (~240ms), `SIP_STT_MIN_DURATION_S=0.20`, prebuffer max 10 frames (~200ms). Config par défaut était trop conservative (start=5, end=35, min_duration=0.35).
- **STT double doit être désactivé en mode direct** : en mode `SIP_DIRECT_AUDIO_TO_GEMINI=1`, le STT fallback doit être complètement désactivé (`if not SIP_DIRECT_AUDIO_TO_GEMINI`), pas juste ignoré. Gemini reçoit audio + texte en double → répétitions.
- **`send_client_content(text=..., turn_complete=True)` fonctionne** comme fallback texte quand l'audio direct n'est pas disponible. Le `realtime_input(text=...)` ne déclenche pas de réponse dans Gemini Live — c'est `send_client_content` qui crée un tour complet.

## FreeSWITCH + mod_audio_stream build (2026-05-23)
Image `walter/freeswitch-modern:arm64` construite avec succès: FreeSWITCH 1.10.12, mod_audio_stream, mod_opus, mod_sofia.
- Config path: `/usr/local/freeswitch/etc/freeswitch/` (PAS `conf/`)
- Docker: utiliser `--entrypoint /usr/local/freeswitch/bin/freeswitch` avec `-nf -nonat` (pas `-nc` qui daemonize et tue le container)
- `freeswitch.xml` par défaut charge `vars.xml`, `autoload_configs/*.xml`, `dialplan/*.xml`, `directory/*.xml`
- Variables `${external_sip_ip}` etc. NE SONT PAS résolues par Sofia au démarrage des profils — les IPs doivent être en dur dans les XML de profils SIP
- Port 5060/5080 déjà pris par Asterisk — FreeSWITCH doit utiliser 5070/5090
- `example.com` gateway vient du default config et doit être retiré du `sip_profiles/external/`
- Le build Docker nécessite: spandsp3 (de source), sofia-sip (de source), libspeex-dev, libspeexdsp-dev, libpq-dev, cmake pour mod_audio_stream, et `git submodule update --init --recursive` pour libwsc
- **Direct raw SIP audio to Live WORKS** after fixing the receive loop. On 2026-05-23 afternoon, `SIP_DIRECT_AUDIO_TO_GEMINI=1` with PCMU/8 kHz produced: speech_end → Gemini input transcription in ~0.2s, speech_end → first output transcription in ~1.8s. Gemini transcribed "Tu m'entends là ou pas ?" and replied "Fort et clair, Monsieur." The earlier "no response" was caused by the broken `session.receive()` iterator, NOT by the audio format. Once the receive loop was wrapped in `while True`, direct audio worked immediately.
- **STT fallback causes repetition when direct audio is on.** If both `SIP_DIRECT_AUDIO_TO_GEMINI=1` and the STT fallback task are active, Gemini receives audio AND duplicate text turns → repeats itself. Fix: gate STT fallback with `if not SIP_DIRECT_AUDIO_TO_GEMINI`.
- **ExternalMedia `slin16` breaks inbound audio.** Setting `EXTERNAL_MEDIA_FORMAT=slin16` sends 16 kHz outbound to the bridge, but Asterisk does NOT forward inbound RTP from the SIP leg in slin16 mode. Result: "RTP first inbound packet" never appears, no speech is detected. Only `ulaw` works bidirectionally. Do not set `slin16` without first verifying inbound audio.

## Debug checklist for future runs
1. `asterisk -rx 'pjsip show registrations'` — trunk registered.
2. Confirm the iPhone/Linphone is powered and logged in.
3. On call, look for SIP `180 Ringing` then `200 OK`.
4. Bridge logs must show:
   - `Call start`
   - `ExternalMedia channel`
   - `RTP remote set`
   - `RTP first inbound packet`
   - `Gemini input audio chunks sent`
5. If W.Alter speaks but does not answer after caller speech, check for:
   - `Gemini input transcription` — if present, Gemini received and understood audio
   - `Gemini output transcription` — if present, Gemini is responding
   - If input transcription appears but no output: check `receive_from_gemini()` loops around `session.receive()`; a single async iterator dies after `turn_complete`.
   - If neither appears: check `RTP first inbound packet` (missing = audio path broken, possibly slin16 issue)
6. If W.Alter repeats itself, check whether BOTH direct audio AND STT fallback are active. STT fallback must be gated with `if not SIP_DIRECT_AUDIO_TO_GEMINI`.
7. If activity markers fire but no transcription appears, do not keep patching RMS thresholds indefinitely. Verify the receive loop first, then check if the session has hit a spending cap or error.

## SIP registration fix (2026-05-23 late)
- **Root cause**: Asterisk had no transport on the private IP `10.0.0.24`. Only `transport-tailscale` (100.91.35.121:5060) and `transport-localhost` (127.0.0.1:5060). The linphone endpoint referenced `transport=transport-public` which didn't exist, so PJSIP fell back to the Tailscale transport. SIP packets went out from 100.91.35.121 → linphone.org never responded.
- **Fix**: Added `[transport-public]` in pjsip.conf: `bind=10.0.0.24:5060`, `external_media_address=129.150.52.60`, `external_signaling_address=129.150.52.60`. Registration immediately worked.
- **Also**: earndeel endpoint section was accidentally deleted by `sed` cleanup. Must be restored for outbound calls via `PJSIP/earndeel`.
- **FreeSWITCH sofia-sip ARM64 is fundamentally broken.** Three approaches tested:
  1. sofia-sip from HEAD (`--depth 1`, no tag): `nua_common.c:121 nh_create_handle() creating handle failed` — NUA can't create handles.
  2. sofia-sip tag `v1.13.17`: handle creation works, profiles load, gateway appears, but **zero UDP packets sent** on any interface. `tcpdump -i any` captures nothing. `--privileged` container doesn't help. The `su_sendmsg`/`su_send` functions silently fail on ARM64.
  3. System sofia-sip (Ubuntu 24.04, 1.12.11): too old — FreeSWITCH 1.10.12 compile fails on missing symbols (`sdp_bw_as`, `sdp_proto_msrp`, `sdp_media_text`). Patching version check allows configure but compilation still fails.
  **Conclusion**: FreeSWITCH SIP is non-functional on ARM64. Hybrid Asterisk-SIP + FreeSWITCH-media (via ESL) is the only theoretical path, but adds significant complexity. Current production stays on Asterisk PCMU 8kHz.
- **DNS**: `sip.linphone.org` resolves to IPv6 first. VPS without IPv6 must use `176.31.149.179` directly in gateway proxy config.

## Asterisk ExternalMedia quality limits (2026-05-23 late)
- **Opus IS negotiated on SIP leg** (`NativeFormats: opus`, `ReadFormat/WriteFormat: slin48`). The bottleneck is ExternalMedia forcing ulaw.
- **ExternalMedia slin16/slin48 breaks inbound audio completely.** Asterisk 20.6 does NOT forward SIP leg audio to ExternalMedia for ANY format other than ulaw. Tested slin16 (2x), slin48 (1x) — outbound works (Gemini speaks), inbound never arrives (no RTP first inbound packet). This is an Asterisk 20.6 limitation, not a config issue.
- **scipy.signal.resample_poly** replaces audioop.ratecv for higher quality resampling (polyphase filter vs linear interpolation). Installed scipy 1.17.1 system-wide.
- **FreeSWITCH SIP on ARM64 is dead.** sofia-sip v1.13.17 fixes handle creation but UDP send silently fails — zero packets leave the container. Tested with --privileged, IPv4 direct IP, all interfaces tcpdump. The library's su_sendmsg is broken on ARM64.
- **Practical ceiling on this VPS**: ulaw 8kHz bidirectional + scipy polyphase resampler. For true WebRTC parity, needs x86_64 FreeSWITCH build or Asterisk 22+ with improved ExternalMedia.

## Architecture guidance
For true WebRTC parity, prefer one of:
- Native WebRTC call path using the existing browser-direct architecture and Gemini Live realtime media semantics.
- SIP/WebRTC gateway that keeps Opus wideband and WebRTC-like jitter/VAD behavior as long as possible.
- Asterisk/FreeSWITCH configuration with Opus end-to-end and bridge code that sends Gemini 16 kHz/24 kHz PCM without PCMU bottleneck where possible.

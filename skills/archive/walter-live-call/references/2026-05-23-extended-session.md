# SIP ↔ Gemini Live: key learnings (2026-05-23 extended session)

## FreeSWITCH on ARM64: dead end
- sofia-sip v1.13.17 tag fixes nua handle creation but UDP send silently fails — zero packets leave container
- Tested: --privileged, IPv4 direct, all interfaces tcpdump → nothing
- sofia-sip 1.12.11 (Ubuntu) lacks symbols FS 1.10.12 needs (sdp_bw_tias, sdp_proto_msrp, sdp_media_text)
- ExternalMedia slin16/slin48 breaks inbound audio — Asterisk 20.6 limitation, tested 3 times

## SIP-Gemini direct bridge (abandoned)
- Built raw SIP/UDP server at /opt/sip-gemini-bridge/sip_bridge.py
- Registration with sip.linphone.org works with qop=auth (nc+cnonce, strip "Digest " prefix)
- Correct password: {{bw:9a13ec17-b3c5-4278-a6bc-a5e8517a5187:password}}
- Outbound INVITE to earndeel@sip.linphone.org → 482 Loop Detected (same provider)
- Routing through Asterisk ARI originate → Stasis race condition (call disappears before bridge attaches)
- Conclusion: overengineering. Asterisk already handles SIP perfectly.

## User preference
Don't rebuild from scratch what already works. Ship at 8kHz quality and iterate. User frustration = signal to simplify, not to add complexity.

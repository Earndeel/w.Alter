# Outbound Linphone regression — 2026-05-23

## What happened

During W.Alter SIP-call debugging, the user corrected the initial conclusion that Linphone outbound calls were inherently unreliable: earlier in the same session, Asterisk successfully called `PJSIP/earndeel` and played the stock female Asterisk prompts.

Confirmed in `/var/log/asterisk/cdr-csv/Master.csv`:

- `2026-05-23 09:28:19` — `PJSIP/earndeel`, `Playback(hello-world)`, `ANSWERED`.
- `2026-05-23 09:28:53` — `PJSIP/earndeel`, `Playback(hello-world)`, `ANSWERED`.
- `2026-05-23 09:33:46` — `PJSIP/earndeel`, `BackGround(demo-congrats)`, `ANSWERED`.
- `2026-05-23 10:21:43` — `PJSIP/earndeel` entered `Stasis(hermes_bridge)`, `ANSWERED`, with ExternalMedia channel attached.

Later attempts showed only `SIP/2.0 100 Trying` + `SIP/2.0 110 Push sent`, then no stable app execution. That does **not** prove Linphone is unusable; it means the current state diverged from a known-good one.

## Correction to workflow

Do **not** jump directly to “use PSTN trunk” when Linphone push fails once. First establish whether the basic Asterisk-to-Linphone path still works.

1. Check CDR for last known-good answered calls:
   ```bash
   grep -E 'Playback|BackGround|Stasis' /var/log/asterisk/cdr-csv/Master.csv | tail -30
   ```

2. Reproduce a pure Asterisk prompt, no Gemini:
   ```text
   AMI Originate
   Channel: PJSIP/earndeel
   Application: Playback
   Data: hello-world
   Timeout: 90000
   Async: yes
   ```

3. Reproduce the exact demo prompt path if that was the user-visible success:
   ```text
   AMI Originate
   Channel: PJSIP/earndeel
   Context: default
   Exten: s
   Priority: 1
   Timeout: 90000
   Async: yes
   ```

4. Compare app execution in CDR:
   - Working: CDR has `Playback`, `BackGround`, or `Stasis` and `disposition=ANSWERED`.
   - Broken before answer: live channel stuck as `AppDial2((Outgoing Line))`, `answer=0`, SIP trace ends around `110 Push sent`/`CANCEL cause=19`.

5. Compare recent changes before blaming Linphone:
   - Asterisk major version switch (20.6 package vs 22.9 source).
   - Endpoint media changes such as `media_encryption=sdes` / `media_encryption_optimistic=yes`.
   - Dialplan changes that alter `Context`, `Exten`, `Application` path.
   - AMI Originate shape (`Application` vs `Context/Exten` changes semantics).

6. If prompts worked earlier in the session, prefer rollback to known-good Asterisk/media config before introducing a new telephony provider.

## Key lesson

The user's “it worked before, I heard the female Asterisk voice” is high-value evidence. Treat it as a regression marker and inspect CDR/log history before forming architectural conclusions. Elegant, and less embarrassing.
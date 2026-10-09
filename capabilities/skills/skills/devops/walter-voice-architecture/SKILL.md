---
name: walter-voice-architecture
description: "W.Alter 3-tier voice + routing architecture -- Gemini Live for voice/social reflex, Hermes sync for mid-weight tasks, Hermes async for deep work. Routing rules, session flow, and infrastructure."
version: 1.4.0
author: Lucas + W.Alter
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [walter, architecture, voice, routing, gemini, hermes]
---

# W.Alter Voice & Routing Architecture

Walter s'est défini une architecture ou l'utilisateur interagit via voix temps reel avec la sensation de parler directement a W.Alter, tandis que les taches complexes s'executent en arriere-plan.

## 3-Tier Architecture

```
┌─────────────────────────────────────────────────┐
│  GEMINI LIVE (Interface sensorielle)            │
│  Voice time reel + reflexes sociaux courts      │
│  < 3s reponse, zero risque                      │
│  model: gemini-3.1-flash-live-preview           │
├─────────────────────────────────────────────────┤
│  HERMES SYNC (Cerveau moyen)                    │
│  Taches moyennes, outils, recherche             │
│  < 30s reponse                                  │
├─────────────────────────────────────────────────┤
│  HERMES ASYNC (Cerveau profond)                 │
│  Code, memoire profonde, orchestration          │
│  > 30s, background, Kanban/subagents            │
└─────────────────────────────────────────────────┘
```

## Roles

| Composant | Role | Model/Provider |
|-----------|------|---------------|
| Gemini Live | Voix temps reel, interactions sociales, requetes simples | gemini-3.1-flash-live-preview |
| W.Alter (Hermes) | Cerveau central, orchestration, memoire, code | Qwen 3.6 Plus via OpenRouter |
| Hindsight | Memoire longue duree (Qdrant + PG + ZeRank-2) | Voir skill hindsight-maintenance |
| Telegram + TUI | Continuite visuelle, asynchrone | -- |

## Routing Rules

1. **Gemini Live** gere les requetes < 3s sans risque (questions simples, status)
2. **Hermes sync** gere les requetes < 30s moyennes (recherche, lecture, operations simples)
3. **Hermes async** gere les taches > 30s complexes ou risquee (code, deploiement, memoire profonde, orchestration)

## Session References

- `references/conversation-buffer-pattern.md` — ConversationBuffer implementation for context-aware Hermes escalation
- `references/natural-speech-to-speech-routing-2026-05-18.md` — natural Gemini Live ↔ voice_router ↔ Hermes handoff pattern, prompt rules, sanitization, profile fallback, and regression probes from the speech-to-speech fluidity session.
- `references/voice-router-only-pattern.md` — voice_router as the ONLY data tool for Gemini Live; system prompt template, tool registration, normalizeToolCallArgs pattern, and lessons learned from the direct-tools bypass bug.
- `jarvis-memory-system` skill — Memory Gateway architecture, recall modes, local embedding, voice recall strategy.

## Pattern Voice → Hermes

Gemini Live n'a pas de support natif asynchrone robuste. Pour maintenir Hermes comme orchestrateur principal :

1. Live capte la requête vocale de Monsieur
2. Live appelle `voice_router` UNIQUEMENT (pas d'outils directs de données)
3. `voice_router` décide la route : réponse directe OU escalade Hermes async
4. Pour la mémoire : `voice_router` appelle Memory Gateway `/recall/ultra` (<50ms, local embedding) en priorité, fallback sur Hindsight `/recall` (Gemini API)
5. Hermes exécute avec outils/mémoire/completion
6. Résultat push via WebSocket → browser → Gemini Live parle instantanément

**Memory integration:** voice_router_service.py has `MEMORY_GATEWAY_ULTRA_URL` pointing to Memory Gateway. See `jarvis-memory-system` skill for full architecture.

## Conversation Buffer (v1.3, 2026-05-19)

**Problem:** When Gemini Live escalates to Hermes async, Hermes only receives the last utterance ("Mener une analyse approfondie") without conversation context. Hermes then says "I don't know what to analyze" because it doesn't know the user was talking about Microsoft 3D models.

**Solution:** `ConversationBuffer` in `voice_router_service.py` tracks the last 10 (user, assistant) turns per `call_id`. When `build_deep_prompt()` runs for hermes_async, it injects the buffer as "Contexte de la conversation vocale en cours".

**Implementation:**
- `RouteRequest` has new fields: `call_id`, `assistant_response`
- `conversation_buffer.add(call_id, role, text)` — called at route entry (user) and route exit (assistant)
- `conversation_buffer.get_context(call_id, last_n=6)` — returns formatted conversation for Hermes prompt
- `app.js` `normalizeToolCallArgs()` passes `state.callId` to voice_router
- Buffer is per-call, cleared when call ends (max_turns=10, LRU)

**Key learning:** Gemini Live treats each tool call as isolated. It does NOT pass conversation history to voice_router. The server-side buffer is essential for context-aware escalation.

**Files:**
- `voice_router_service.py` — ConversationBuffer class, build_deep_prompt() injection
- `app.js` — normalizeToolCallArgs() adds call_id

## Transient Messages + Message Queue (2026-05-19)

**Problem:** During multi-step Hermes jobs, the user heard nothing until completion. Also, job results could interrupt Gemini mid-sentence.

**Solution:** Two-part system:

### 1. Transient Message Streaming (voice_router)
`run_job()` reads Hermes stdout line by line. Lines with significant markers (🔧, ✓, ✗, Running, Created, Done, Error, Failed) are pushed via `push_transient_update()` to `/internal/transient-update` on the voice-call server.

### 2. Browser Multi-Job Message Queue (app.js)
All incoming messages (transient updates + job results) are queued with **per-job tracking**. The queue is FIFO-ordered and delivers results with full context.

**Architecture:**
```
activeJobs (Map)         — tracks job_id → { question, startedAt }
jobResultQueue (Array)   — FIFO queue of completed job results
state.messageQueue (Array) — transient updates with job context
currentDrainJobId        — which job result is currently being spoken
```

**Lifecycle:**
1. `enqueueJobStart(jobId, question)` — called when voice_router returns status=started with job_id
2. `enqueueTransientUpdate(jobId, message)` — transient updates tagged with job_id, includes original question context
3. `enqueueJobResult(jobId, prompt)` — completed job result queued in FIFO order
4. `drainQueue()` — prioritizes job results (FIFO) over transient updates, batches transients (max 3)
5. `markGeminiSpeaking()` — called on AUDIO response, blocks drain
6. `markGeminiDone()` — called on TURN_COMPLETE or INTERRUPTED, unblocks drain after 800ms

**Queue priority:** Job results first (FIFO order), then transient updates (batched).

**Key learning:** Without per-job tracking, concurrent jobs (e.g., "check my emails AND delete the Microsoft one AND check vast.ai") produce results in random order and Gemini Live can't tell which result belongs to which question. The FIFO queue + question context ensures ordered, attributable delivery.

**Files:**
- `voice_router_service.py` — `push_transient_update()`, streaming `run_job()`
- `server.py` — `/internal/transient-update` endpoint
- `app.js` — `enqueueJobStart()`, `enqueueJobResult()`, `enqueueTransientUpdate()`, `drainQueue()`, `markGeminiSpeaking()`, `markGeminiDone()`

## Memory Recall in Voice Router (2026-05-19)

Le `voice_router` (port 12110) utilise maintenant le Memory Gateway `/recall/ultra` comme source mémoire PRIMAIRE, avec Hindsight en fallback.

**Flow:**
```
Gemini Live → voice_router /route (intent: context_lookup)
  → Memory Gateway /recall/ultra (local embedding, ~40ms)
  → synthesize_for_voice (Gemini API, ~400-600ms)
  → spoken_response → Gemini Live parle
```

**Latence totale:** 500-750ms (vs ~1500ms avant avec Hindsight seul)

**Fallback chain:** local (8896) → Hindsight hybrid search (8889) → PG keyword

**Config env var:** `VOICE_ROUTER_MEMORY_GATEWAY_ULTRA=http://127.0.0.1:8891/recall/ultra`

**Pitfall:** Le `synthesize_for_voice` (Gemini API) est le vrai bottleneck vocal (~400-600ms). Le recall mémoire n'est que ~40ms. Optimiser la synthèse vocale serait le prochain gain de performance.

## Direct Relay Architecture (v1.4, 2026-06-09)

**Problem:** The `synthesize_for_voice()` Gemini Flash call added 400-600ms latency and sometimes reformulated Hermes' analysis poorly, losing key details.

**Solution:** Zero-secondary-LLM direct relay architecture.

### Deep path (hermes_async / deep_web)
1. **Hermes** produces a full analysis with structured labels:
   - `SPOKEN_SUMMARY:` — dense, concise vocal synthesis for audio decision support
   - `DECISION:` — conclusion/answer
   - `NEXT_ACTION:` — suggested next step
   - `CONFIDENCE:` — high/medium/low

2. **Regex extraction** (`_extract_speaking_parts()`) pulls these labels from Hermes output directly — no Gemini Flash pass needed.

3. **Browser Gemini Live** receives the spoken summary and **recites it verbatim** (system instruction: *"Récite ce texte tel quel, sans rien ajouter ni reformuler"*). Preserves Hermes' intent, tone, and content exactly.

### Fast path (direct_answer / quick_web / context_lookup / store_memory)
- `synthesize_for_voice()` Gemini Flash reformulation still applies (short, conversational responses)

### SPOKEN_SUMMARY prompt instruction
```
SPOKEN_SUMMARY: Résume ton résultat en une synthèse complète mais dense et courte
pour un retour audio agréable, dans l'objectif de transmettre les informations de
manière concise et efficace, pour aider Monsieur dans la prise de décision.
Écris-la comme une phrase que tu dirais à voix haute.
```

### Session continuity (call_id → Hermes session)
- `call_id` → `_hermes_sessions` dict tracks `call_id → session_id`
- First call: no `--resume`, stderr `session_id: <id>` captured and stored
- Subsequent calls: `--resume <session_id>` appended to `hermes chat` command
- Stale session fallback: if `--resume` fails (returncode != 0 + "Session not found"), retry without `--resume` and clear stored session

### Key helper functions
- `_extract_speaking_parts(text)` → `(spoken, decision, next_action, confidence)` via regex
- `_shorten_for_tts(text, max_len=400)` → fallback truncation when no SPOKEN_SUMMARY found

## Infrastructure

- Voix : Gemini Live WebSocket (bidirectionnel STT + LLM + TTS)
- Prix Live : $0.10/1M input tokens, $0.40/1M output tokens (~$0.003/conversation)
- Alternative xAI : Voice Agent API (`grok-voice-latest`) — $3/hr, sub-second, X Search + web_search + code_exec intégrés dans la voix, custom voice cloning. Voir `references/xai-voice-agent-api.md`.
- Alternative SIP : Asterisk SIP + Gemini Live audio bridge (voir skill `walter-live-call`)
- **Production voice call URL**: `https://call.walter-ai.cloud` (Cloudflare Tunnel, valid HTTPS, WebSocket OK, works on iPhone Safari without Tailscale). SIP signaling works (registration, call connect) but audio RTP blocked by Asterisk 20.6.0 `simple_bridge` bug. See `walter-live-call` skill for full ExternalMedia debugging evidence.
- **SIP-Gemini Direct Bridge** (`sip-gemini-bridge.service`, port 5062): raw SIP/UDP server that accepts Linphone calls and bridges Opus 48kHz audio directly to Gemini Live via WebSocket. Bypasses Asterisk ExternalMedia entirely. Pending real-call validation. See `walter-live-call` skill → `references/sip-gemini-direct-bridge.md`.
- Pipeline actuel remplace STT(Groq) + LLM(OpenRouter) + TTS(Edge) par un seul modele temps reel
- Hermes TTS/STT xAI : déjà supporté (`tts.provider: xai`, `stt.provider: xai`) — 5 voix, $15/1M chars TTS, $0.20/hr STT

## xAI Voice Agent vs Gemini Live

| Critère | xAI Voice Agent | Gemini 3.1 Flash Live |
|---|---|---|
| Prix | $3.00/heure (~$0.05/min) | ~$0.003/conversation |
| Latence | Sub-second | Sub-second |
| Tools dans la voix | web_search, X Search, code_exec, functions | functions uniquement |
| Custom voices | ✅ Clonage audio (max 120s) | ❌ |
| X Search temps réel | ✅ Unique | ❌ |
| Nombre de voix | 5 + custom | ~30 |
| Hermes realtime | ❌ Pas encore intégré | ❌ Pas encore intégré |

**Stratégie :** Gemini Live pour les interactions vocales rapides (coût imbattable). xAI Voice Agent quand X Search ou custom voices sont nécessaires dans la boucle vocale. Le custom voice cloning permettrait de créer une voix "butler" W.Alter.

## Gemini Live Configuration (2026-05-19)

### System Prompt Injection
The system prompt is injected via `client.setSystemInstructions(SYSTEM_PROMPT)` in app.js, which sends it as `systemInstruction.parts[{text}]` in the `BidiGenerateContentSetup` WebSocket message.

**3 layers stacked in SYSTEM_PROMPT:**
1. `AUDIO_STYLE` — voice director (tone, rhythm, accent, pacing)
2. `COMMUNICATION_STYLE` — content rules (butler style, vouvoiement, Monsieur)
3. `SYSTEM_PROMPT` — behavior (routing rules, tool usage, limits)

### Current Settings
| Setting | Value | Notes |
|---------|-------|-------|
| Temperature | 0.2 | Reduced from 0.7 for consistency |
| Thinking level | low | 1024 tokens budget |
| Voice | Algenib | French accent, deep resonant |
| Proactive audio | OFF | Not yet enabled |
| Affective dialog | OFF | Not yet enabled |
| Google Search | ON | grounding enabled |

### Thinking Levels Benchmark (gemini-2.5-flash, 2026-05-19)
| Level | Latency | Thinking tokens | Notes |
|-------|---------|-----------------|-------|
| off | 1.9s | 0 | Best for voice — 3x faster |
| low | 6.0s | ~930 | +4s overhead for reasoning |
| medium | 8.6s | ~1500 | +7s overhead |
| high | ERROR | — | Not supported on flash |

**Recommendation:** Use `off` for simple voice responses, `low` for complex reasoning. For voice, `off` gives 3x better latency.

### Features NOT yet enabled (available in API)
- **Proactive audio** — prevents responses to noise/hesitation
- **Affective dialog** — adapts tone to user emotion
- **Code execution** — run Python during voice session
- **Session resumption** — reconnect without losing context

## Pitfalls

- **WebSocket push remplace le polling (2026-05-18):** Les jobs async ne pollent plus `/jobs/{id}` toutes les 15s. Quand Hermes finit, `voice_router_service.py` POST vers `/internal/job-complete` → server.py broadcast WebSocket → browser → Gemini Live parle instantanément. Plus de notifications Telegram pour les jobs vocaux.
- **⚠️ Gemini Live ne doit AUCUN outil de données direct.** Si Gemini Live a accès à `get_inbox_digest` ou `get_beeper_conversation`, il les utilise AU LIEU de passer par `voice_router`. Ça court-circuit complètement Hermes. La règle : Gemini Live n'a qu'UN outil d'action : `voice_router`. Tout le reste (Beeper, email, web, code) passe par Hermes derrière `voice_router`. Correction utilisateur 2026-05-18.
- **user_utterance doit être verbatim.** Quand Gemini Live appelle `voice_router`, `user_utterance` doit être la phrase EXACTE de Monsieur. `normalizeToolCallArgs` injecte `state.lastUserTranscript` automatiquement. Le prompt système doit dire explicitement "ne reformule JAMAIS".
- Les sessions live ne persistent pas — chaque appel est un nouveau contexte sauf si Hermes alimente le prompt.
- Ne JAMAIS confondre live (interface) avec Hermes (cerveau) — le live n'a PAS d'accès aux outils, mémoire, ou filesystem.
- **server.py WS clients** : utiliser `app.state.ws_clients`, jamais une variable locale `_ws_clients` dans `create_app()` — Python scoping cause `UnboundLocalError` dans les fonctions endpoints imbriquées.
- **⚠️ server.py tourne en HTTPS.** Les appels internes de `voice_router_service.py` vers `server.py` doivent utiliser `https://127.0.0.1:8765/...` avec `httpx.AsyncClient(verify=False)`. Utiliser `http://` cause des échecs silencieux — aucun log d'erreur dans voice-router, aucune requête reçue par voice-call. C'est ce qui a cassé le push WebSocket pendant toute une session avant d'être diagnostiqué.
- **⚠️ Browser WebSocket stale state après restart.** Après un `systemctl restart hermes-voice-call`, le WebSocket du navigateur devient stale. Le serveur montre des cycles connect/disconnect immédiats. L'utilisateur DOIT recharger la page (Ctrl+Shift+R). Côté serveur tout est OK — le problème est dans le cache navigateur.
- **Ordre de redémarrage.** Toujours redémarrer voice-router AVANT voice-call pour éviter les erreurs transitoires de tool calls.
- **⚠️ Gemini API spending cap blocks ALL voice.** When Google AI Studio spending cap is exceeded, the Gemini Live WebSocket closes with code=1011 ("exceeded its monthly spending cap"). This blocks voice calls, token creation, and all Gemini-dependent features. Fix: go to https://ai.studio/spend and increase the cap. **Symptom:** browser shows "Gemini WebSocket closed (code=1011)" in a reconnect loop. **Monitoring:** add a cron to check Gemini API health before voice sessions.
- **⚠️ All requests route to hermes_async (known issue, 2026-05-19).** The voice_router currently sends almost everything to hermes_async, even simple requests like "check my emails" that should be handled directly. This causes Gemini Live to always say "Je lance ça en cerveau profond" and the actual result arrives 30-60s later via WebSocket. **Fix needed:** voice_router should differentiate between simple memory/context lookups (direct, <3s), tool actions (hermes_async but with proper routing), and deep research (hermes_async). The intent classification in the voice_router is too aggressive toward hermes_async.
- **⚠️ Gemini Live ne reçoit pas les résultats async (2026-05-19).** Quand un job hermes_async finit, le résultat est poussé via WebSocket au browser. Mais si Lucas a posé 3 autres questions entre-temps, Gemini Live n'a jamais vu le résultat. Le système de queue (FIFO avec per-job tracking) corrige partiellement ce problème, mais Gemini Live doit quand même recevoir le résultat comme `sendTextMessage` pour pouvoir en parler. Le résultat async doit être injecté dans la session Gemini Live dès qu'il arrive, pas juste mis en queue.
- **⚠️ Temperature 0.2 pour la voix.** La température a été réduite de 0.7 à 0.2 pour plus de cohérence et moins de divagations. Le thinking level est à "low" (1024 tokens) par défaut. Pour les réponses simples, "off" donne 3x moins de latence.
- **Voice router memory recall:** `voice_router` appelle `/recall/ultra` (local embedding) en premier, Hindsight en fallback. Si le local échoue silencieusement, le fallback se déclenche automatiquement. Vérifier `data.source` dans la réponse pour savoir quel pipeline a été utilisé.
- **synthesize_for_voice est le bottleneck vocal** (~400-600ms), pas le recall mémoire (~40ms). Pour améliorer la latence vocale, optimiser la synthèse (modèle plus rapide, cache de réponses, ou TTS local).
- **⚠️ Gemini Live features NOT yet enabled:** proactive audio, affective dialog, thinking config, Google Search, code execution. These are available in the API but not configured. Proactive audio prevents responses to noise/hesitation. Affective dialog adapts tone to user emotion. See `hermes-voice-module` skill → `references/gemini-live-api-reference.md` for config examples.

Pour les cas où Live n'est pas utilisé, Hermes a un module voix gemini (skill `hermes-voice-module`) :
- STT via Gemini 3.1 Flash Lite
- TTS via Gemini 3.1 Flash TTS
- 2-layer architecture: Layer 1 (Audio: voice/tone/speed) + Layer 2 (Communication: personality/humor/verbosity)
- Layer 2 (Communication) is in `~/.hermes/SOUL.md` for Telegram, and in `COMMUNICATION_STYLE` constant for Live
- Remplace le pipeline Groq STT + Edge TTS separe

## 2-Layer Voice Architecture

W.Alter a deux couches indépendantes :

| Couche | Contrôle | Fichiers |
|--------|----------|----------|
| **Layer 1: Audio** | Voix, ton, vitesse, rythme, accent | config.yaml (system_prompt), app.js/bridge.py (AUDIO_STYLE) |
| **Layer 2: Communication** | Personnalité, humour, sarcasme, verbosité | SOUL.md, app.js/bridge.py (COMMUNICATION_STYLE) |

Voir `hermes-voice-module` pour les détails complets et la synchronisation des fichiers.

## System Prompt Injection (detail)

See `references/system-prompt-injection.md` for the full 3-layer injection chain (AUDIO_STYLE → COMMUNICATION_STYLE → SYSTEM_PROMPT), client configuration, and the geminilive.js plumbing.

## Pitfalls (legacy — some may be outdated)

- Gemini 3.1 Flash Live **n'a PAS** de support asynchrone natif — ne peut pas faire des tool calls en background. D'où le pattern WebSocket push via `/internal/job-complete`.
- Ne route pas les données personnelles live (Beeper/Gmail exacts) vers Hindsight `context_lookup`: Hindsight donne la mémoire, pas l'état réel des inbox. Tout passe par voice_router → Hermes qui a accès aux outils Beeper/email.
- Gemini 2.5 Flash Live a un meilleur support async mais qualité vocale inférieure.
- Ne JAMAIS confondre live (interface) avec Hermes (cerveau) — le live n'a PAS d'accès aux outils, mémoire, ou filesystem.
- Les sessions live ne persistent pas — chaque appel est un nouveau contexte sauf si Hermes alimente le prompt.
- xAI Voice Agent est ~1000x plus cher que Gemini Live par interaction courte — ne pas l'utiliser pour des requêtes simples.
- xAI X Search (via API) et x_search Hermes sont des choses différentes : X Search est un tool Grok natif dans l'API xAI, pas un tool Hermes natif. Pour chercher sur X depuis Hermes, utiliser web_search ou browser_tool.

#!/usr/bin/env python3
"""
Model Benchmark Suite for Hindsight pipeline components.
Tests compression, extraction, and consolidation candidates empirically.

Usage:
  export OPENROUTER_API_KEY=sk-or-...
  export GEMINI_API_KEY=AIzaSy...
  python3 model_benchmark.py
"""

import os, json, time, sys, re, requests

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

OR_BASE = "https://openrouter.ai/api/v1"

COMPRESSION_MODELS = [
    ("deepseek/deepseek-v4-flash", "OpenRouter", "DeepSeek V4 Flash"),
    ("gemini-3.1-flash-lite-preview", "Gemini", "Gemini 3.1 Flash Lite (AI Studio)"),
    ("openai/gpt-oss-120b:free", "OpenRouter", "GPT-OSS 120B"),
]

EXTRACTION_MODELS = [
    ("deepseek/deepseek-v4-flash", "OpenRouter", "DeepSeek V4 Flash"),
    ("gemini-3.1-flash-lite-preview", "Gemini", "Gemini 3.1 Flash Lite (AI Studio)"),
    ("gemini-3-flash-preview", "Gemini", "Gemini 3 Flash (AI Studio)"),
]

CONSOLIDATION_MODELS = [
    ("gemini-3.1-pro-preview", "Gemini", "Gemini 3.1 Pro Preview"),
    ("gemini-3-flash-preview", "Gemini", "Gemini 3 Flash"),
    ("deepseek/deepseek-v4-pro", "OpenRouter", "DeepSeek V4 Pro"),
]

COMPRESSION_PROMPT = """Tu es un systeme de compression de contexte. Resume la conversation suivante en conservant TOUS les faits importants, decisions, et informations contextuelles. Sois concis mais exhaustif.

CONVERSATION:
User: Salut Walter, je travaille sur le projet Scena Factory. C'est une plateforme de video IA multi-tenant. Architecture: Cloudflare Workers + D1 + R2. Le auth utilise Clerk sur le frontend et custom JWT sur les workers. Le billing est Stripe avec checkout dynamique. J'ai aussi un systeme de memoire Hindsight avec Qdrant + Gemini Embed 2. La gateway Telegram est sur un bot @walter_0002_bot. Le dashboard est sur dashboard.walter-ai.cloud.

Assistant: OK, note. Scena Factory = plateforme video IA multi-tenant. Stack: Cloudflare Workers + D1 + R2. Auth: Clerk frontend + custom JWT workers. Billing: Stripe checkout dynamique. Memoire: Hindsight (Qdrant + Gemini Embed 2). Gateway Telegram: @walter_0002_bot. Dashboard: dashboard.walter-ai.cloud.

User: J'ai aussi un profile coder avec des scripts pour spawn des super coders. Le routing utilise Claude Code Sonnet pour le debug, Opus pour l'arch/auth/billing, et Gemini 2.5 Pro pour le design. Fallback DeepSeek v4.

Assistant: Profil coder ajoute. Routing: Claude Sonnet (debug), Claude Opus (arch/auth/billing), Gemini 2.5 Pro (design), fallback DeepSeek v4.

User: Mon credit Groq est a 7, Google a 21, OpenRouter a 5 free. Fal est epuise. Il faut que je surveille ca 24/7.

Assistant: Credits monitores: Groq 7, Google 21, OpenRouter 5 free, Fal epuise. Monitoring 24/7 active.

User: Je veux ajouter un systeme de generation video multi-modele. L'idee c'est de router le brief client vers le bon modele selon le style: Kling pour le realisme, Runway pour l'artistic, Luma pour le cinematic.

Assistant: Pipeline video multi-modele note. Routing par style: Kling (realisme), Runway (artistic), Luma (cinematic).

RESUME cette conversation en 5-8 phrases maximum, en conservant tous les faits techniques importants."""

EXTRACTION_PROMPT = """Tu es un systeme d'extraction de faits pour une memoire agentique. Extrais les faits atomiques de ce texte.

TEXT:
Lucas travaille sur Scena Factory, une plateforme de video IA multi-tenant. L'architecture utilise Cloudflare Workers avec D1 pour la base de donnees et R2 pour le stockage. L'authentification est geres par Clerk cote frontend et des JWT custom cote workers. Le billing passe par Stripe avec des checkout sessions dynamiques. Il a aussi mis en place un systeme de memoire appele Hindsight qui utilise Qdrant pour le stockage vectoriel et Gemini Embedding 2 pour les embeddings. La gateway Telegram tourne sur le bot @walter_0002_bot. Il y a un dashboard accessible sur dashboard.walter-ai.cloud. Lucas utilise un profil coder avec routing multi-modele: Claude Sonnet pour le debug, Claude Opus pour l'architecture/auth/billing, Gemini 2.5 Pro pour le design, et DeepSeek v4 en fallback. Ses credits API sont: Groq 7, Google 21, OpenRouter 5 free, Fal epuise. Il veut ajouter un pipeline video multi-modele qui route vers Kling pour le realisme, Runway pour l'artistique, et Luma pour le cinematic.

Reponds UNIQUEMENT avec un JSON valide respectant exactement ce schema:
{
  "extracted_facts": [
    {"fact": "phrase factuelle claire et atomique"}
  ]
}
"""

CONSOLIDATION_PROMPT = """Tu es un systeme de consolidation de memoire expert. Fusionne ces faits en supprimant les doublons.

FAITS:
1. Lucas utilise Stripe pour le billing de Scena Factory.
2. Le billing de Scena Factory est gere par Stripe avec checkout dynamique.
3. Scena Factory utilise Cloudflare Workers pour le backend.
4. Le backend de Scena Factory est deploye sur Cloudflare Workers avec D1 et R2.
5. Lucas a 7 credits Groq.
6. Les credits Groq de Lucas sont a 7 unites.
7. Fal est epuise.
8. La cle API Fal de Lucas n'a plus de credits.
9. Hindsight utilise Qdrant pour le stockage vectoriel.
10. Le systeme de memoire Hindsight stocke les vecteurs dans Qdrant avec Gemini Embedding 2.
11. Lucas a un profil coder avec routing multi-modele.
12. Le profil coder route vers Claude Sonnet pour le debug, Claude Opus pour arch/auth/billing, Gemini 2.5 Pro pour design, DeepSeek v4 fallback.

Reponds avec une liste numerotee de faits consolides (max 8). Sois precis et technique."""


def call_openrouter(model, messages, max_tokens=1024, temperature=0.3):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://walter-ai.cloud",
        "X-Title": "W.Alter Model Benchmark"
    }
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if "deepseek" in model:
        payload["max_tokens"] = 4096

    start = time.time()
    try:
        resp = requests.post(f"{OR_BASE}/chat/completions", headers=headers, json=payload, timeout=120)
        elapsed = time.time() - start
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}", "elapsed": elapsed}
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return {
            "content": content,
            "elapsed": elapsed,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }
    except Exception as e:
        return {"error": str(e), "elapsed": time.time() - start}


def call_gemini(model, prompt, max_tokens=1024, temperature=0.3):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        }
    }
    start = time.time()
    try:
        resp = requests.post(url, json=payload, timeout=120)
        elapsed = time.time() - start
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}", "elapsed": elapsed}
        data = resp.json()
        if "candidates" not in data or not data["candidates"]:
            return {"error": "No candidates", "elapsed": elapsed}
        content = data["candidates"][0]["content"]["parts"][0]["text"]
        usage = data.get("usageMetadata", {})
        return {
            "content": content,
            "elapsed": elapsed,
            "prompt_tokens": usage.get("promptTokenCount", 0),
            "completion_tokens": usage.get("candidatesTokenCount", 0),
            "total_tokens": usage.get("totalTokenCount", 0),
        }
    except Exception as e:
        return {"error": str(e), "elapsed": time.time() - start}


def call_model(model, backend, prompt, max_tokens=1024, temperature=0.3, system=None):
    if backend == "Gemini":
        full_prompt = prompt
        if system:
            full_prompt = f"{system}\n\n{prompt}"
        return call_gemini(model, full_prompt, max_tokens, temperature)
    else:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return call_openrouter(model, messages, max_tokens, temperature)


def test_compression(model, backend, name):
    result = call_model(model, backend, COMPRESSION_PROMPT, max_tokens=512, system="Tu resumes des conversations en conservant tous les faits importants.")
    if "error" in result:
        return {"model": name, "error": result["error"]}
    content = result["content"]
    key_facts = ["scena", "cloudflare", "clerk", "stripe", "hindsight", "qdrant", "telegram", "coder", "kling", "runway"]
    mentions = sum(1 for f in key_facts if f.lower() in content.lower())
    coverage = mentions / len(key_facts)
    return {
        "model": name, "elapsed_sec": round(result["elapsed"], 2),
        "tokens": result["total_tokens"], "coverage": round(coverage, 2),
        "output_len": len(content),
    }


def test_extraction(model, backend, name):
    result = call_model(model, backend, EXTRACTION_PROMPT, max_tokens=2048, temperature=0.1, system="Tu extrais des faits atomiques et reponds UNIQUEMENT en JSON valide.")
    if "error" in result:
        return {"model": name, "error": result["error"]}
    content = result["content"]
    json_valid = False
    fact_count = 0
    json_match = re.search(r'\{.*\}', content, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            facts = parsed.get("extracted_facts", [])
            fact_count = len(facts)
            json_valid = True
        except:
            pass
    if not json_valid:
        code_match = re.search(r'```json\s*(.*?)```', content, re.DOTALL)
        if code_match:
            try:
                parsed = json.loads(code_match.group(1))
                facts = parsed.get("extracted_facts", [])
                fact_count = len(facts)
                json_valid = True
            except:
                pass
    return {
        "model": name, "elapsed_sec": round(result["elapsed"], 2),
        "tokens": result["total_tokens"], "json_valid": json_valid,
        "fact_count": fact_count,
    }


def test_consolidation(model, backend, name):
    result = call_model(model, backend, CONSOLIDATION_PROMPT, max_tokens=1024, system="Tu fusionnes des faits en supprimant les doublons. Sois concis et precis.")
    if "error" in result:
        return {"model": name, "error": result["error"]}
    content = result["content"]
    key_concepts = ["stripe", "cloudflare", "groq", "fal", "hindsight", "qdrant", "claude", "deepseek"]
    mentions = sum(1 for c in key_concepts if c.lower() in content.lower())
    coverage = mentions / len(key_concepts)
    lines = [l.strip() for l in content.split('\n') if l.strip() and any(c.isdigit() for c in l[:5])]
    return {
        "model": name, "elapsed_sec": round(result["elapsed"], 2),
        "tokens": result["total_tokens"], "coverage": round(coverage, 2),
        "unique_facts": len(lines),
    }


def run_suite():
    print("=" * 80)
    print("W.ALTER MODEL BENCHMARK SUITE")
    print("=" * 80)

    print("\n--- TEST 1: COMPRESSION ---")
    for m, b, n in COMPRESSION_MODELS:
        print(f"  Testing {n}...", end=" ", flush=True)
        r = test_compression(m, b, n)
        if "error" in r:
            print(f"FAIL ({r['error'][:60]})")
        else:
            print(f"OK ({r['elapsed_sec']}s, {r['coverage']*100:.0f}% coverage)")

    print("\n--- TEST 2: EXTRACTION ---")
    for m, b, n in EXTRACTION_MODELS:
        print(f"  Testing {n}...", end=" ", flush=True)
        r = test_extraction(m, b, n)
        if "error" in r:
            print(f"FAIL ({r['error'][:60]})")
        else:
            status = "VALID" if r['json_valid'] else "INVALID"
            print(f"{status} ({r['elapsed_sec']}s, {r['fact_count']} faits)")

    print("\n--- TEST 3: CONSOLIDATION ---")
    for m, b, n in CONSOLIDATION_MODELS:
        print(f"  Testing {n}...", end=" ", flush=True)
        r = test_consolidation(m, b, n)
        if "error" in r:
            print(f"FAIL ({r['error'][:60]})")
        else:
            print(f"OK ({r['elapsed_sec']}s, {r['unique_facts']} faits, {r['coverage']*100:.0f}% coverage)")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    run_suite()

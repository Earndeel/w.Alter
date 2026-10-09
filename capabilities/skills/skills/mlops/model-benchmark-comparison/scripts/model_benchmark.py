#!/usr/bin/env python3
"""
Model Benchmark Suite — Test compression, extraction, consolidation.
Supports OpenRouter AND Google AI Studio (free tier).
Run:
  OPENROUTER_API_KEY=$(vault get openrouter api_key) \
  GEMINI_API_KEY=$(vault get gemini api_key) \
    python3 /root/.hermes/skills/mlops/model-benchmark-comparison/scripts/model_benchmark.py
"""

import os, json, time, sys, re, requests

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

OR_BASE = "https://openrouter.ai/api/v1"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# ── Model lists: (model_id, backend, display_name) ─────────────────────────

COMPRESSION_MODELS = [
    ("deepseek/deepseek-v4-flash", "OpenRouter", "DeepSeek V4 Flash"),
    ("gemini-3.1-flash-lite-preview", "Gemini", "Gemini 3.1 Flash Lite (AI Studio)"),
    ("gemini-2.5-flash-lite-preview-09-2025", "Gemini", "Gemini 2.5 Flash Lite (AI Studio)"),
    ("openai/gpt-oss-120b:free", "OpenRouter", "GPT-OSS 120B"),
]

EXTRACTION_MODELS = [
    ("deepseek/deepseek-v4-flash", "OpenRouter", "DeepSeek V4 Flash"),
    ("gemini-3.1-flash-lite-preview", "Gemini", "Gemini 3.1 Flash Lite (AI Studio)"),
    ("gemini-3-flash-preview", "Gemini", "Gemini 3 Flash (AI Studio)"),
    ("mistralai/mistral-small-4", "OpenRouter", "Mistral Small 4"),
]

CONSOLIDATION_MODELS = [
    ("gemini-3-flash-preview", "Gemini", "Gemini 3 Flash (AI Studio)"),
    ("deepseek/deepseek-v4-pro", "OpenRouter", "DeepSeek V4 Pro"),
    ("xiaomi/mimo-v2.5-pro", "OpenRouter", "MiMo V2.5 Pro"),
]

# ── Test prompts ──────────────────────────────────────────────────────────────────

COMPRESSION_PROMPT = """Tu es un système de compression de contexte. Résume la conversation suivante en conservant TOUS les faits importants, décisions, et informations contextuelles. Sois concis mais exhaustif.

CONVERSATION:
User: Salut Walter, je travaille sur le projet Scena Factory. C'est une plateforme de vidéo IA multi-tenant. Architecture: Cloudflare Workers + D1 + R2. Le auth utilise Clerk sur le frontend et custom JWT sur les workers. Le billing est Stripe avec checkout dynamique. J'ai aussi un système de mémoire Hindsight avec Qdrant + Gemini Embed 2. La gateway Telegram est sur un bot @walter_0002_bot. Le dashboard est sur dashboard.walter-ai.cloud.

Assistant: OK, noté. Scena Factory = plateforme vidéo IA multi-tenant. Stack: Cloudflare Workers + D1 + R2. Auth: Clerk frontend + custom JWT workers. Billing: Stripe checkout dynamique. Mémoire: Hindsight (Qdrant + Gemini Embed 2). Gateway Telegram: @walter_0002_bot. Dashboard: dashboard.walter-ai.cloud.

User: J'ai aussi un profile coder avec des scripts pour spawn des super coders. Le routing utilise Claude Code Sonnet pour le debug, Opus pour l'arch/auth/billing, et Gemini 2.5 Pro pour le design. Fallback DeepSeek v4.

Assistant: Profil coder ajouté. Routing: Claude Sonnet (debug), Claude Opus (arch/auth/billing), Gemini 2.5 Pro (design), fallback DeepSeek v4.

User: Mon crédit Groq est à 7, Google à 21, OpenRouter à 5 free. Fal est épuisé. Il faut que je surveille ça 24/7.

Assistant: Crédits monitorés: Groq 7, Google 21, OpenRouter 5 free, Fal épuisé. Monitoring 24/7 activé.

User: Je veux ajouter un système de génération vidéo multi-modèle. L'idée c'est de router le brief client vers le bon modèle selon le style: Kling pour le réalisme, Runway pour l'artistic, Luma pour le cinematic.

Assistant: Pipeline vidéo multi-modèle noté. Routing par style: Kling (réalisme), Runway (artistic), Luma (cinematic).

RÉSUME cette conversation en 5-8 phrases maximum, en conservant tous les faits techniques importants."""

EXTRACTION_PROMPT = """Tu es un système d'extraction de faits pour une mémoire agentique. Extrais les faits atomiques de ce texte.

TEXT:
Lucas travaille sur Scena Factory, une plateforme de vidéo IA multi-tenant. L'architecture utilise Cloudflare Workers avec D1 pour la base de données et R2 pour le stockage. L'authentification est gérée par Clerk côté frontend et des JWT custom côté workers. Le billing passe par Stripe avec des checkout sessions dynamiques. Il a aussi mis en place un système de mémoire appelé Hindsight qui utilise Qdrant pour le stockage vectoriel et Gemini Embedding 2 pour les embeddings. La gateway Telegram tourne sur le bot @walter_0002_bot. Il y a un dashboard accessible sur dashboard.walter-ai.cloud. Lucas utilise un profil coder avec routing multi-modèle: Claude Sonnet pour le debug, Claude Opus pour l'architecture/auth/billing, Gemini 2.5 Pro pour le design, et DeepSeek v4 en fallback. Ses crédits API sont: Groq 7, Google 21, OpenRouter 5 free, Fal épuisé. Il veut ajouter un pipeline vidéo multi-modèle qui route vers Kling pour le réalisme, Runway pour l'artistique, et Luma pour le cinematic.

Réponds UNIQUEMENT avec un JSON valide respectant exactement ce schéma:
{
  "extracted_facts": [
    {"fact": "phrase factuelle claire et atomique"}
  ]
}
"""

CONSOLIDATION_PROMPT = """Tu es un système de consolidation de mémoire expert. Fusionne ces faits en supprimant les doublons.

FAITS:
1. Lucas utilise Stripe pour le billing de Scena Factory.
2. Le billing de Scena Factory est géré par Stripe avec checkout dynamique.
3. Scena Factory utilise Cloudflare Workers pour le backend.
4. Le backend de Scena Factory est déployé sur Cloudflare Workers avec D1 et R2.
5. Lucas a 7 crédits Groq.
6. Les crédits Groq de Lucas sont à 7 unités.
7. Fal est épuisé.
8. La clé API Fal de Lucas n'a plus de crédits.
9. Hindsight utilise Qdrant pour le stockage vectoriel.
10. Le système de mémoire Hindsight stocke les vecteurs dans Qdrant avec Gemini Embedding 2.
11. Lucas a un profil coder avec routing multi-modèle.
12. Le profil coder route vers Claude Sonnet pour le debug, Claude Opus pour arch/auth/billing, Gemini 2.5 Pro pour design, DeepSeek v4 fallback.

Réponds avec une liste numérotée de faits consolidés (max 8). Sois précis et technique."""

# ── API callers ──────────────────────────────────────────────────────────────

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
    url = f"{GEMINI_BASE}/{model}:generateContent?key={GEMINI_KEY}"
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
            return {"error": f"No candidates: {json.dumps(data)[:200]}", "elapsed": elapsed}
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


# ── Test functions ──────────────────────────────────────────────────────────────────

def estimate_cost(model, backend, prompt_tokens, completion_tokens):
    if backend == "Gemini":
        return 0.0  # AI Studio free tier
    prices = {
        "deepseek/deepseek-v4-flash": (0.14, 0.28),
        "deepseek/deepseek-v4-pro": (1.74, 3.48),
        "openai/gpt-oss-120b:free": (0.0, 0.0),
        "mistralai/mistral-small-4": (0.15, 0.60),
        "xiaomi/mimo-v2.5-pro": (1.00, 3.00),
    }
    pin, pout = prices.get(model, (0.5, 3.0))
    return (prompt_tokens * pin + completion_tokens * pout) / 1_000_000


def test_compression(model, backend, name):
    result = call_model(model, backend, COMPRESSION_PROMPT, max_tokens=512, system="Tu résumes des conversations en conservant tous les faits importants.")

    if "error" in result:
        return {"model": name, "model_id": model, "backend": backend, "error": result["error"]}

    content = result["content"]
    key_facts = ["scena", "cloudflare", "clerk", "stripe", "hindsight", "qdrant", "telegram", "coder", "kling", "runway"]
    mentions = sum(1 for f in key_facts if f.lower() in content.lower())
    coverage = mentions / len(key_facts)
    cost = estimate_cost(model, backend, result["prompt_tokens"], result["completion_tokens"])

    return {
        "model": name, "model_id": model, "backend": backend,
        "elapsed_sec": round(result["elapsed"], 2),
        "tokens": result["total_tokens"],
        "cost_usd": round(cost, 6),
        "coverage": round(coverage, 2),
        "output_len": len(content),
        "summary": content[:200] + "..." if len(content) > 200 else content,
    }


def test_extraction(model, backend, name):
    result = call_model(model, backend, EXTRACTION_PROMPT, max_tokens=2048, temperature=0.1, system="Tu extrais des faits atomiques et réponds UNIQUEMENT en JSON valide.")

    if "error" in result:
        return {"model": name, "model_id": model, "backend": backend, "error": result["error"]}

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

    cost = estimate_cost(model, backend, result["prompt_tokens"], result["completion_tokens"])

    return {
        "model": name, "model_id": model, "backend": backend,
        "elapsed_sec": round(result["elapsed"], 2),
        "tokens": result["total_tokens"],
        "cost_usd": round(cost, 6),
        "json_valid": json_valid,
        "fact_count": fact_count,
        "output_preview": content[:300] + "..." if len(content) > 300 else content,
    }


def test_consolidation(model, backend, name):
    result = call_model(model, backend, CONSOLIDATION_PROMPT, max_tokens=1024, system="Tu fusionnes des faits en supprimant les doublons. Sois concis et précis.")

    if "error" in result:
        return {"model": name, "model_id": model, "backend": backend, "error": result["error"]}

    content = result["content"]
    key_concepts = ["stripe", "cloudflare", "groq", "fal", "hindsight", "qdrant"]
    mentions = sum(1 for c in key_concepts if c.lower() in content.lower())
    coverage = mentions / len(key_concepts)
    lines = [l.strip() for l in content.split('\n') if l.strip() and any(c.isdigit() for c in l[:5])]
    unique_lines = len(lines)
    cost = estimate_cost(model, backend, result["prompt_tokens"], result["completion_tokens"])

    return {
        "model": name, "model_id": model, "backend": backend,
        "elapsed_sec": round(result["elapsed"], 2),
        "tokens": result["total_tokens"],
        "cost_usd": round(cost, 6),
        "coverage": round(coverage, 2),
        "unique_facts": unique_lines,
        "output_preview": content[:300] + "..." if len(content) > 300 else content,
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def run_suite():
    print("=" * 80)
    print("W.ALTER MODEL BENCHMARK SUITE — AI Studio free tier for Gemini")
    print("=" * 80)

    print("\n" + "─" * 40)
    print("TEST 1: COMPRESSION DE CONTEXTE")
    print("─" * 40)
    comp_results = []
    for mid, backend, name in COMPRESSION_MODELS:
        print(f"  Testing {name}...", end=" ", flush=True)
        res = test_compression(mid, backend, name)
        comp_results.append(res)
        if "error" in res:
            print(f"FAIL ({res['error'][:60]})")
        else:
            print(f"OK ({res['elapsed_sec']}s, {res['coverage']*100:.0f}% coverage, ${res['cost_usd']})")

    print("\n  RÉSULTATS COMPRESSION:")
    print(f"  {'Modèle':<50} {'Temps':>8} {'Tokens':>8} {'Coût':>10} {'Coverage':>10}")
    for r in comp_results:
        if "error" in r:
            print(f"  {r['model']:<50} ERROR: {r['error'][:40]}")
        else:
            print(f"  {r['model']:<50} {r['elapsed_sec']:>8.2f}s {r['tokens']:>8} ${r['cost_usd']:>9.6f} {r['coverage']*100:>9.0f}%")

    print("\n" + "─" * 40)
    print("TEST 2: EXTRACTION JSON STRUCTURÉ")
    print("─" * 40)
    ext_results = []
    for mid, backend, name in EXTRACTION_MODELS:
        print(f"  Testing {name}...", end=" ", flush=True)
        res = test_extraction(mid, backend, name)
        ext_results.append(res)
        if "error" in res:
            print(f"FAIL ({res['error'][:60]})")
        else:
            status = "VALID" if res['json_valid'] else "INVALID"
            print(f"{status} ({res['elapsed_sec']}s, {res['fact_count']} faits, ${res['cost_usd']})")

    print("\n  RÉSULTATS EXTRACTION:")
    print(f"  {'Modèle':<50} {'Temps':>8} {'Tokens':>8} {'Coût':>10} {'JSON':>8} {'Faits':>8}")
    for r in ext_results:
        if "error" in r:
            print(f"  {r['model']:<50} ERROR: {r['error'][:40]}")
        else:
            json_status = "✓" if r['json_valid'] else "✗"
            print(f"  {r['model']:<50} {r['elapsed_sec']:>8.2f}s {r['tokens']:>8} ${r['cost_usd']:>9.6f} {json_status:>8} {r['fact_count']:>8}")

    print("\n" + "─" * 40)
    print("TEST 3: CONSOLIDATION MÉMOIRE")
    print("─" * 40)
    cons_results = []
    for mid, backend, name in CONSOLIDATION_MODELS:
        print(f"  Testing {name}...", end=" ", flush=True)
        res = test_consolidation(mid, backend, name)
        cons_results.append(res)
        if "error" in res:
            print(f"FAIL ({res['error'][:60]})")
        else:
            print(f"OK ({res['elapsed_sec']}s, {res['unique_facts']} faits, {res['coverage']*100:.0f}% coverage, ${res['cost_usd']})")

    print("\n  RÉSULTATS CONSOLIDATION:")
    print(f"  {'Modèle':<50} {'Temps':>8} {'Tokens':>8} {'Coût':>10} {'Coverage':>10} {'Faits':>8}")
    for r in cons_results:
        if "error" in r:
            print(f"  {r['model']:<50} ERROR: {r['error'][:40]}")
        else:
            print(f"  {r['model']:<50} {r['elapsed_sec']:>8.2f}s {r['tokens']:>8} ${r['cost_usd']:>9.6f} {r['coverage']*100:>9.0f}% {r['unique_facts']:>8}")

    print("\n" + "=" * 80)
    print("RÉSUMÉ ET RECOMMANDATIONS")
    print("=" * 80)

    valid_comp = [r for r in comp_results if "error" not in r]
    if valid_comp:
        best_speed = min(valid_comp, key=lambda x: x["elapsed_sec"])
        best_cost = min(valid_comp, key=lambda x: x["cost_usd"])
        best_coverage = max(valid_comp, key=lambda x: x["coverage"])
        print(f"\n  COMPRESSION — Meilleur coût: {best_cost['model']} (${best_cost['cost_usd']})")
        print(f"  COMPRESSION — Meilleur vitesse: {best_speed['model']} ({best_speed['elapsed_sec']}s)")
        print(f"  COMPRESSION — Meilleure couverture: {best_coverage['model']} ({best_coverage['coverage']*100:.0f}%)")

    valid_ext = [r for r in ext_results if "error" not in r]
    if valid_ext:
        valid_json = [r for r in valid_ext if r["json_valid"]]
        if valid_json:
            best_json_cost = min(valid_json, key=lambda x: x["cost_usd"])
            best_json_speed = min(valid_json, key=lambda x: x["elapsed_sec"])
            best_facts = max(valid_json, key=lambda x: x["fact_count"])
            print(f"\n  EXTRACTION — Meilleur JSON valide + coût: {best_json_cost['model']} (${best_json_cost['cost_usd']}, {best_json_cost['fact_count']} faits)")
            print(f"  EXTRACTION — Meilleur JSON valide + vitesse: {best_json_speed['model']} ({best_json_speed['elapsed_sec']}s, {best_json_speed['fact_count']} faits)")
            print(f"  EXTRACTION — Plus de faits: {best_facts['model']} ({best_facts['fact_count']} faits)")
        else:
            print("\n  EXTRACTION — Aucun modèle n'a produit de JSON valide!")

    valid_cons = [r for r in cons_results if "error" not in r]
    if valid_cons:
        best_cons_coverage = max(valid_cons, key=lambda x: x["coverage"])
        best_cons_cost = min(valid_cons, key=lambda x: x["cost_usd"])
        print(f"\n  CONSOLIDATION — Meilleur coût: {best_cons_cost['model']} (${best_cons_cost['cost_usd']})")
        print(f"  CONSOLIDATION — Meilleure couverture: {best_cons_coverage['model']} ({best_cons_coverage['coverage']*100:.0f}%)")

    out_path = "/root/.hermes/logs/model_benchmark_results.json"
    with open(out_path, "w") as f:
        json.dump({"compression": comp_results, "extraction": ext_results, "consolidation": cons_results}, f, indent=2, ensure_ascii=False)
    print(f"\n  Résultats complets sauvegardés: {out_path}")


if __name__ == "__main__":
    run_suite()

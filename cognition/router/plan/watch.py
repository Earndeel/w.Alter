"""Plan research on the web (part of `research plans` and of the 48 h cycle): the economic text tier (L1, Hermes
one-shot with web tools) looks for what is published about each of the owner's plans — the API value a plan carries
(SemiAnalysis Tokenomics, other measurements), tokens or messages per 5 h / week window, price and limit changes —
and answers in JSON. Each fact is stored in models.plan_evidence with its source and date; nothing is applied."""
from __future__ import annotations

import json
import re

from walter_router.plan import declared

METRICS = ("usd_value_month", "tokens_month", "messages_5h", "messages_week", "price_usd_month", "limit_note")
PROMPT = """Tu fais la veille des abonnements IA de {owner}. Ses plans actuels (JSON) :
{plans}

Faits déjà connus (ne les redonne pas sauf s'ils ont changé) :
{known}

Cherche sur le web (au plus 10 recherches, pages officielles d'abord : aide, tarifs, notes de version de l'éditeur ;
puis analyses sérieuses et datées : SemiAnalysis / Tokenomics, autres mesures publiées de la valeur d'un plan au prix
de l'API ou du nombre de tokens / messages par fenêtre). Pour CHAQUE plan : prix actuel, limites publiées (fenêtre de
5 h, hebdomadaire, modèles inclus), valeur mensuelle au prix API par modèle si quelqu'un l'a mesurée.

Réponds UNIQUEMENT par un tableau JSON, sans texte autour. Chaque élément :
{{"sub_id": "<id du plan ou null>", "vendor": "...", "plan": "...", "model_id": "<id router du modèle ou null>",
  "metric": "usd_value_month | tokens_month | messages_5h | messages_week | price_usd_month | limit_note",
  "value": <nombre ou null>, "unit": "...", "source_name": "...", "source_url": "https://...",
  "published": "AAAA-MM-JJ ou null", "quote": "<phrase exacte de la source, 300 caractères max>"}}
N'invente rien : un fait sans URL vérifiée n'est pas rendu. Tableau vide si rien de nouveau."""


def known(conn) -> list[dict]:
    return [dict(r) for r in conn.execute(
        """select sub_id, model_id, metric, value, unit, source_name, published from models.plan_evidence
           where origin = 'web' order by found_at desc limit 60""")]


def parse(text: str) -> list[dict]:
    """The JSON array of the agent's answer (tolerates text or a code fence around it)."""
    m = re.search(r"\[.*\]", text or "", re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except ValueError:
        return []
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or it.get("metric") not in METRICS or not it.get("source_url", "").startswith("http"):
            continue
        out.append(it)
    return out


def store(conn, items: list[dict], origin: str = "web") -> tuple[int, list[int]]:
    subs = {s["id"] for s in declared.read().get("subscriptions", [])}
    n, ids = 0, []
    for it in items:
        value = it.get("value")
        try:
            value = float(value) if value is not None else None
        except (TypeError, ValueError):
            value = None
        cur = conn.execute(
            """insert into models.plan_evidence (sub_id, vendor, plan, model_id, metric, value, unit, source_name,
               source_url, published, quote, origin) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               on conflict do nothing returning evidence_id""",
            (it.get("sub_id") if it.get("sub_id") in subs else None, it.get("vendor") or "?", it.get("plan") or "?",
             it.get("model_id"), it["metric"], value, it.get("unit"), it.get("source_name") or "?", it.get("source_url"),
             it.get("published") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(it.get("published") or "")) else None,
             (it.get("quote") or "")[:400], origin))
        n += cur.rowcount
        ids += [r["evidence_id"] for r in cur.fetchall()] if cur.rowcount and cur.description else []
    return n, ids


def run(conn) -> dict:
    from walter_router import instance
    from walter_router.serve.oneshot import ask_l1
    plans = [{k: s.get(k) for k in ("id", "vendor", "plan", "price_usd_month", "models", "execution")}
             for s in declared.read().get("subscriptions", [])]
    prompt = PROMPT.format(owner=instance.owner(), plans=json.dumps(plans, ensure_ascii=False),
                           known=json.dumps(known(conn), ensure_ascii=False, default=str))
    text = ask_l1(conn, prompt, "walter-router-plans", timeout=900, tools="web", max_turns=25)
    items = parse(text or "")
    added, ids = store(conn, items)
    from walter_router.plan import news
    return {"found": len(items), "new": added, "notices": len(news.from_web(conn, ids))}

"""A new benefit or change on a plan the owner has -> one Telegram notice each (owner, 2026-10-22: « s'il y a un nouvel
avantage ou une modification via un des abonnements que l'on possède, on doit être notifié »).

Two sources, both read by `walter-router research plans` (and the 48 h cycle):
- mails from the vendors of his plans (OpenAI / ChatGPT, Anthropic / Claude, Google One / Gemini…): product and plan
  news — new features or models, higher or changed limits, offers, plan changes. Receipts are handled by mail.py;
  sign-in codes and developer / API mails are left out. Deterministic: no mail content goes to a model.
- facts the web research (watch.py) adds for one of his plans that were not known before.
Each item is kept in models.plan_evidence; the notice is a 'plan_change' alert with action 'none' (button « 👁️ Vu »)."""
from __future__ import annotations

import html
import re
from email.utils import parsedate_to_datetime
from urllib.parse import quote

from walter_router.plan import declared, mail

# senders of plan news per vendor (marketing / product mails of the consumer plans, not the API platforms)
SENDERS = {"OpenAI": ("openai.com",), "Anthropic": ("anthropic.com",),
           "Google": ("googleone-noreply@google.com", "gemini-noreply@google.com"),
           "xAI": ("x.ai",), "Mistral": ("mistral.ai",), "Perplexity": ("perplexity.ai",)}
NOT_NEWS = re.compile(r"receipt|reçu|invoice|facture|commande|order|code|verify|vérif|sign.?in|connexion|password|"
                      r"essai|trial|expir|bienvenue|welcome|résili|cancel|"
                      r"mot de passe|security|sécurité|\bAPI\b|developer|développeur|DevDay|Dev News|Platform|Build Week|"
                      r"credit balance|webinar|survey|enquête|unsubscribe", re.I)
NEWS_DAYS = 21


INVISIBLE = re.compile(r"[\u034f\u200b-\u200f\u2060\ufeff\u00ad]+")
BOILER = re.compile(r"view (it )?in (your )?browser|afficher dans le navigateur|unsubscribe|se désabonner|privacy|confidentialité|"
                    r"©|all rights reserved|tous droits réservés|^https?://", re.I)


def clean(text: str) -> str:
    text = INVISIBLE.sub("", html.unescape(text or "")).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def body_text(token: str, mid: str, limit: int = 420) -> str | None:
    """First real sentences of the mail (text part, else the HTML without tags), boilerplate lines dropped."""
    import base64
    m = mail._get(token, f"messages/{mid}?format=full")
    plain, htm = [], []

    def walk(part: dict) -> None:
        data = (part.get("body") or {}).get("data")
        if data:
            raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
            (plain if part.get("mimeType") == "text/plain" else htm if part.get("mimeType") == "text/html" else []).append(raw)
        for p in part.get("parts") or []:
            walk(p)
    walk(m.get("payload") or {})
    text = "\n".join(plain) or re.sub(r"<(style|script)[^>]*>.*?</\1>|<[^>]+>", "\n", "\n".join(htm), flags=re.S | re.I)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)           # markdown links: keep the words
    if NOT_NEWS.search(clean(re.sub(r"<https?://[^>]*>|https?://\S+", "", text))[:120]):
        return None                                                      # « OpenAI Dev Newsletter »: not about the plan
    text = re.sub(r"<https?://[^>]*>|https?://\S+", "", text)        # tracking links
    lines = [clean(x) for x in text.splitlines()]
    keep = [x for x in lines if len(x) > 25 and not BOILER.search(x)]
    return mail.REDACT.sub("…", " ".join(keep))[:limit]


def _vendors_owned() -> dict[str, str]:
    return {s.get("vendor"): s["id"] for s in declared.read().get("subscriptions", []) if s.get("vendor")}


def _sender_vendor(sender: str, owned: dict[str, str]) -> str | None:
    s = (sender or "").lower()
    for vendor, marks in SENDERS.items():
        if vendor in owned and any(("@" in m and m in s) or re.search(r"[@.]" + re.escape(m) + r">?$", s.strip(">")) for m in marks):
            return vendor
    return None


def from_mail(conn, days: int = NEWS_DAYS) -> list[int]:
    """New product / plan mails from the vendors of the owner's plans -> evidence + notice. Returns alert ids."""
    owned = _vendors_owned()
    senders = sorted({m for v in owned for m in SENDERS.get(v, ())})   # exact addresses or vendor domains
    if not senders:
        return []
    token = mail._token()
    q = "from:(" + " OR ".join(senders) + f") newer_than:{days}d"
    ids = [m["id"] for m in mail._get(token, f"messages?maxResults=40&q={quote(q)}").get("messages", [])]
    seen = {r["source_url"] for r in conn.execute("select source_url from models.plan_evidence where origin = 'email'")}
    created = []
    from walter_router.analysis.alerts import _upsert
    for mid in ids:
        ref = f"gmail:{mid}"
        if ref in seen:
            continue
        m = mail._get(token, f"messages/{mid}?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date")
        h = {x["name"].lower(): x["value"] for x in m.get("payload", {}).get("headers", [])}
        vendor = _sender_vendor(h.get("from", ""), owned)
        subject = clean(h.get("subject", ""))
        if not vendor or not subject or NOT_NEWS.search(subject):
            continue
        try:
            day = parsedate_to_datetime(h["date"]).date()
        except Exception:  # noqa: BLE001
            day = None
        try:
            snippet = body_text(token, mid)
            if snippet is None:
                continue
            snippet = snippet or clean(m.get("snippet", ""))
        except Exception:  # noqa: BLE001 — the subject alone is still worth a notice
            snippet = clean(m.get("snippet", ""))
        snippet = mail.REDACT.sub("…", snippet)[:420]
        if NOT_NEWS.search(snippet[:80]):   # e.g. « OpenAI Dev Newsletter » under a product-looking subject
            continue
        sub_id = owned[vendor]
        plan = next((s.get("plan") for s in declared.read()["subscriptions"] if s["id"] == sub_id), vendor)
        conn.execute("""insert into models.plan_evidence (sub_id, vendor, plan, metric, unit, source_name, source_url,
                        published, quote, origin) values (%s,%s,%s,'limit_note','nouveauté',%s,%s,%s,%s,'email')
                        on conflict do nothing""",
                     (sub_id, vendor, plan, f"mail {vendor}", ref, day, f"{subject} — {snippet}"[:400]))
        ev = {"action": "none", "news": True, "sub_id": sub_id, "vendor": vendor, "plan": plan, "mail_date": str(day),
              "title": subject[:160], "quote": snippet, "source": f"mail {vendor} du {day}"}
        if _upsert(conn, "plan_change", "", f"{sub_id}:news:{ref}", ev, "open"):
            created.append(ref)
    return created


def from_web(conn, evidence_ids: list[int]) -> list[int]:
    """Facts the web research just added for one of the owner's plans, unless the same fact was already known."""
    created = []
    from walter_router.analysis.alerts import _upsert
    for r in conn.execute("""select e.* from models.plan_evidence e where e.evidence_id = any(%s) and e.sub_id is not null
                             and not exists (select 1 from models.plan_evidence o where o.evidence_id < e.evidence_id
                                             and o.sub_id = e.sub_id and o.metric = e.metric
                                             and coalesce(o.value, -1) = coalesce(e.value, -1)
                                             and coalesce(o.model_id, '') = coalesce(e.model_id, ''))""",
                          (evidence_ids,)).fetchall():
        title = f'{r["unit"] or r["metric"]}'.strip()
        ev = {"action": "none", "news": True, "sub_id": r["sub_id"], "vendor": r["vendor"], "plan": r["plan"],
              "mail_date": str(r["published"] or ""), "title": title[:160], "quote": (r["quote"] or "")[:240],
              "source": r["source_name"], "url": r["source_url"]}
        if _upsert(conn, "plan_change", "", f'{r["sub_id"]}:news:web:{r["evidence_id"]}', ev, "open"):
            created.append(r["evidence_id"])
    return created

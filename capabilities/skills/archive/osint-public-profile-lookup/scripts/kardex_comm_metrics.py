#!/usr/bin/env python3
"""
kardex_comm_metrics.py — Analyse de style de communication pour tout contact du Kardex.
Calcule la batterie complète de métriques depuis kardex.messages et stocke le résultat
dans kardex.communication_patterns (types normalisés, ré-exécutable = idempotent).

Usage:
  /root/.hermes/hermes-agent/venv/bin/python kardex_comm_metrics.py <contact_id> [<contact_id> ...]
  /root/.hermes/hermes-agent/venv/bin/python kardex_comm_metrics.py all
"""
import sys, json, re, statistics
from collections import Counter
from datetime import datetime, timezone, timedelta

import psycopg2

DB = dict(host="127.0.0.1", port=5433, dbname="hindsight", user="hindsight")

PATTERN_TYPES = [
    "comm_volume_direction", "comm_latency", "comm_initiative", "comm_turn_taking",
    "syntax_sentence_structure", "syntax_openers", "syntax_contractions",
    "system_emoji_inventory", "system_punctuation", "system_laughter",
    "lexicon_top_words", "evolution_daily_metrics", "comm_media_ratio",
]

EMOJI_RE = re.compile(r'[\U0001F300-\U0001FAFF\u2600-\u27BF\u2764\uFE0F]')
LAUGH_RE = re.compile(r'\bha+h+a*\b|\blol+\b|\blmao+\b|\bmdr\b|\bptdr\b|😂|🤣')

def pct(x, total): return round(100*x/total, 1) if total else 0.0

def analyze(msgs):
    """msgs: [{ts, sender('lucas'|'contact'), text, has_att}] chronologique."""
    out = {}
    L = [m for m in msgs if m["sender"]=="lucas" and m["text"].strip()]
    C = [m for m in msgs if m["sender"]=="contact" and m["text"].strip()]
    out["comm_volume_direction"] = {
        "total": len(msgs), "contact_texts": len(C), "lucas_texts": len(L),
        "direction_ratio_contact_per_lucas": round(len(C)/len(L), 2) if L else None,
    }
    # media
    att_msgs = sum(1 for m in msgs if m["has_att"])
    att_contact = sum(1 for m in msgs if m["has_att"] and m["sender"]=="contact")
    out["comm_media_ratio"] = {
        "messages_with_attachment": att_msgs,
        "contact_share_pct": pct(att_contact, att_msgs),
    }

    def texts(mlist): return [m["text"].strip() for m in mlist]
    ct_texts = texts(C)

    # latency
    lat_c, lat_l = [], []
    for i in range(1, len(msgs)):
        p, c = msgs[i-1], msgs[i]
        gap = (c["ts"] - p["ts"]).total_seconds()/60
        if p["sender"] != c["sender"] and 0.08 < gap < 120:
            (lat_c if c["sender"]=="contact" else lat_l).append(gap)
    out["comm_latency"] = {
        "contact_median_min": round(statistics.median(lat_c),1) if lat_c else None,
        "contact_under2min_pct": pct(sum(1 for x in lat_c if x<2), len(lat_c)),
        "lucas_median_min": round(statistics.median(lat_l),1) if lat_l else None,
        "n_pairs": len(lat_c)+len(lat_l),
    }

    # initiative after gaps >3h
    resumptions = Counter()
    for i in range(1, len(msgs)):
        gap = (msgs[i]["ts"] - msgs[i-1]["ts"]).total_seconds()
        if gap > 3*3600:
            resumptions[msgs[i]["sender"]] += 1
    out["comm_initiative"] = {"resumes_after_3h_gap": dict(resumptions)}

    # turn-taking (consecutive contact msgs before yield)
    bursts, cur = [], 0
    prev_s = None
    for m in msgs:
        if m["sender"]=="contact":
            cur = cur+1 if prev_s=="contact" else 1
        else:
            if cur: bursts.append(cur)
            cur = 0
        prev_s = m["sender"]
    if cur: bursts.append(cur)
    out["comm_turn_taking"] = {
        "median_consec_before_yield": statistics.median(bursts) if bursts else None,
        "single_msg_turns_pct": pct(sum(1 for b in bursts if b==1), len(bursts)),
    } if bursts else {}

    # length profile
    lc = [len(t) for t in texts(C)]
    out.setdefault("syntax_sentence_structure", {})
    out["length_profile"] = {
        "contact_median_chars": int(statistics.median(lc)) if lc else None,
        "contact_max": max(lc) if lc else None,
        "multi_line_pct": pct(sum(1 for t in C if "\n" in t), len(C)),
    }

    # syntax: sentences, words, openers, contractions, non-native markers
    spw, spm, openers = [], [], Counter()
    contr_used = contr_possible = space_punct = miss_apos = 0
    for t in texts(C):
        parts = [s.strip() for s in re.split(r'[.!?\n]+', t) if s.strip()]
        spm.append(max(1,len(parts)))
        for s in parts:
            ws = s.split()
            if ws: spw.append(len(ws))
        low = t.lower()
        if low.startswith("haha"): openers["haha"] += 1
        elif re.match(r"^i[\u2019' ]", low): openers["I"] += 1
        elif low.startswith("you"): openers["you"] += 1
        else: openers["other"] += 1
        contr_used += len(re.findall(r"\b\w+n['\u2019]t\b|\bi['\u2019]m\b|\byou['\u2019]re\b|\bit['\u2019]s\b|\bthat['\u2019]s\b", low))
        contr_possible += len(re.findall(r"\b(do not|do you|you are|i am|it is|that is)\b", low))
        space_punct += len(re.findall(r'\w ([!?])', t))
        miss_apos += bool(re.search(r"\b(whats|dont|cant|im\b|youre|thats|isnt|wont|lets)\b", low))

    out["syntax_openers"] = dict(openers)
    out["syntax_contractions"] = {
        "contracted": contr_used, "uncontracted_remaining": contr_possible,
        "rate_pct": pct(contr_used, contr_used+contr_possible),
        "missing_apostrophe_msgs": miss_apos,
    }
    nn_markers = {"space_before_punct": space_punct}
    out["non_native_markers"] = nn_markers
    out["syntax_sentence_structure"] = {
        "sentences_per_msg_median": statistics.median(spm) if spm else None,
        "words_per_sentence_median": statistics.median(spw) if spw else None,
        "words_per_sentence_p90": sorted(spw)[int(0.9*len(spw))] if spw else None,
    }

    # emoji
    emo = Counter(); emo_end = emo_mid = emo_start = 0
    for t in texts(C):
        found = EMOJI_RE.findall(t)
        for e in found: emo[e]+=1
        if found:
            body_wo = EMOJI_RE.sub("", t).strip()
            if t.rstrip().endswith(found[-1]): emo_end += 1
            elif t.startswith(found[0]): emo_start += 1
            else: emo_mid += 1
    total_e = sum(emo.values())
    out["system_emoji_inventory"] = {
        "per_msg_avg": round(total_e/len(C),2) if C else 0,
        "top10": dict(emo.most_common(10)),
        "placement": {"end": emo_end, "mid": emo_mid, "start": emo_start},
    }

    # punctuation
    dbang = sum(1 for t in ct_texts if "!!" in t)
    q_total = sum(t.count("?") for t in ct_texts)
    ellip = sum(1 for t in ct_texts if ".." in t)
    excl = sum(t.count("!") for t in ct_texts)
    out["system_punctuation"] = {
        "double_bang_msgs": dbang, "questions_total": q_total,
        "q_per_msg": round(q_total/len(C),2) if C else 0,
        "ellipsis_msgs": ellip, "bangs_total": excl,
    }

    # laughter
    laugh_variants = Counter()
    laugh_msgs = 0
    for t in texts(C):
        found = LAUGH_RE.findall(t.lower())
        if found:
            laugh_msgs += 1
            for f in found: laugh_variants[f]+=1
    out["system_laughter"] = {
        "laughing_messages_pct": pct(laugh_msgs, len(C)),
        "variants": dict(laugh_variants.most_common(8)),
    }

    # lexicon
    words = Counter()
    stop = set("that this with have just really about would there what when your from they been because will know think".split())
    for t in texts(C):
        for w in re.findall(r"[a-zA-Z']{4,}", t.lower()):
            if w not in stop: words[w]+=1
    out["lexicon_top_words"] = {"top20": dict(words.most_common(20))}

    # daily evolution
    days = {}
    for m in C:
        d = m["ts"].astimezone(timezone(timedelta(hours=7))).strftime("%d/%m")
        days.setdefault(d, []).append(m["text"])
    evo = {}
    for d in sorted(days):
        ts = days[d]
        evo[d] = {
            "n": len(ts),
            "len_med": int(statistics.median([len(t) for t in ts])),
            "emoji_per_msg": round(sum(len(EMOJI_RE.findall(t)) for t in ts)/len(ts),2),
            "haha_start_pct": pct(sum(1 for t in ts if t.lower().startswith("haha")), len(ts)),
        }
    out["evolution_daily_metrics"] = {"per_day_bkk": evo}

    return out

def store(conn, contact_id, metrics):
    cur = conn.cursor()
    # idempotent: purge les patterns auto précédents du contact
    cur.execute("DELETE FROM kardex.communication_patterns WHERE contact_id=%s AND pattern_type = ANY(%s)",
                (contact_id, PATTERN_TYPES + ["length_profile","non_native_markers"]))
    for ptype, metric in metrics.items():
        cur.execute("""
        INSERT INTO kardex.communication_patterns (contact_id, pattern_type, pattern, metric_value, confidence, status)
        VALUES (%s,%s,%s,%s,0.9,'confirmed')
        """, (contact_id, ptype, json.dumps(metric)[:4000] if isinstance(metric,str) else f"Métriques auto {ptype} (généré par kardex_comm_metrics.py)", json.dumps(metric)))
    conn.commit()

def main():
    args = sys.argv[1:]
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    if not args or args[0]=="all":
        cur.execute("SELECT DISTINCT contact_id FROM kardex.messages WHERE contact_id!=0")
        ids = [r[0] for r in cur.fetchall()]
    else:
        ids = [int(a) for a in args]

    for cid in ids:
        cur.execute("""
        SELECT timestamp, sender, COALESCE(text,''), has_attachments
        FROM kardex.messages WHERE contact_id=%s ORDER BY timestamp
        """, (cid,))
        rows = cur.fetchall()
        if not rows:
            print(f"contact {cid}: 0 messages, skip"); continue
        msgs = [{"ts": r[0], "sender": r[1], "text": r[2], "has_att": r[3]} for r in rows]
        metrics = analyze(msgs)
        store(conn, cid, metrics)
        vol = metrics["comm_volume_direction"]; lat = metrics["comm_latency"]
        lp = metrics["length_profile"]
        print(f"✅ contact {cid}: {vol['total']} msgs | ratio {vol['direction_ratio_contact_per_lucas']} | "
              f"latence contact {lat['contact_median_min']}min ({lat['contact_under2min_percent' if False else 'contact_under2min_pct']}%<2m) | "
              f"len méd {lp['contact_median_chars']} | patterns écrits: {len(metrics)}")
    conn.close()

if __name__ == "__main__":
    main()

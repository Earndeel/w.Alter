"""X Research — Sentiment, themes, language analysis"""
import re
from collections import Counter

POSITIVE_KW = ['fast','speed','impressed','amazing','great','excellent','incredible','powerful','smart','best','good','love','fantastic','solid','cheap','affordable','impressive','efficient','reliable','groundbreaking','game-changer','revolutionary','breakthrough','surpasses','beats','outperforms','frontier','SOTA','beautiful','smooth','clean','elegant','perfect','brilliant','wow','génial','excellent','parfait','incroyable','Harika','mükemmel','quick','capable']
NEGATIVE_KW = ['expensive','costly','overpriced','disappointing','bad','poor','terrible','hallucination','hallucinate','error','bug','broken','slow','worse','regression','downgrade','trash','awful','frustrating','useless','lazy','unreliable','inconsistent','mediocre','overhyped','overrated','fail','failure','struggle','weak','limited','catastrophic','absurd','joke','blague','ridiculous','meh','loses to','behind','below','disappoint','annoying','confusing','misleading','scam','waste']
DEFAULT_THEMES = {
    'Speed/Performance': ['fast','speed','latency','tok/s','quick','rapid','accelerat'],
    'Pricing/Cost': ['price','cost','pricing','expensive','cheap','affordable','budget','cher','coût'],
    'Coding/Agentic': ['coding','code','agentic','agent','CLI','IDE','cursor','dev','programming','SWE-bench'],
    'Quality/Intelligence': ['smart','intelligent','quality','reasoning','capable','thinking'],
    'Comparison Claude': ['claude','opus','sonnet','anthropic'],
    'Comparison GPT': ['gpt','chatgpt','openai','gpt-5'],
    'Google I/O': ['google i/o','i/o 2026','google io','hassabis'],
    'Hallucinations': ['hallucination','hallucinate','error','bug','wrong','incorrect'],
    'Vision/Images': ['vision','image','visual','video','multimodal'],
}
LANG_PATTERNS = {
    'ja': re.compile(r'[\u3040-\u309f\u30a0-\u30ff]'), 'zh': re.compile(r'[\u4e00-\u9fff]'),
    'fr': re.compile(r'[àâäéèêëïîôùûüÿç]', re.I), 'tr': re.compile(r'[ğüşıöçİÜŞÖÇ]'),
    'ru': re.compile(r'[а-яА-Я]'), 'es': re.compile(r'[ñáéíóú]', re.I),
    'de': re.compile(r'[äöüßÄÖÜ]'), 'ko': re.compile(r'[\uac00-\ud7af]'),
}

def detect_language(text):
    for lang, pattern in LANG_PATTERNS.items():
        if pattern.search(text): return lang
    return 'en'

def analyze_sentiment(text, positive_kw=POSITIVE_KW, negative_kw=NEGATIVE_KW):
    text_lower = text.lower()
    pos = sum(1 for kw in positive_kw if kw.lower() in text_lower)
    neg = sum(1 for kw in negative_kw if kw.lower() in text_lower)
    if pos > 0 and neg > 0: return 'mixed', round((pos - neg) / (pos + neg), 2)
    elif pos > neg: return 'positive', round(min(pos / 3.0, 1.0), 2)
    elif neg > pos: return 'negative', round(-min(neg / 3.0, 1.0), 2)
    return 'neutral', 0.0

def detect_themes(text, themes=DEFAULT_THEMES):
    text_lower = text.lower()
    return [theme for theme, keywords in themes.items() if any(kw.lower() in text_lower for kw in keywords)]

def enrich_post(post):
    text = post.get("text", "")
    sentiment, score = analyze_sentiment(text)
    post["sentiment"] = sentiment
    post["sentiment_score"] = score
    post["themes"] = detect_themes(text)
    post["language"] = detect_language(text)
    return post

def compute_stats(posts):
    total = len(posts)
    if total == 0: return {}
    sentiments = Counter(p.get("sentiment", "neutral") for p in posts)
    languages = Counter(p.get("language", "en") for p in posts)
    themes = Counter()
    for p in posts:
        for t in p.get("themes", []): themes[t] += 1
    likes = [p.get("likes", 0) for p in posts]
    positive = sorted([p for p in posts if p.get("sentiment") == "positive"], key=lambda x: x.get("likes", 0), reverse=True)
    negative = sorted([p for p in posts if p.get("sentiment") == "negative"], key=lambda x: x.get("likes", 0), reverse=True)
    return {
        "total_posts": total,
        "positive_pct": round(100 * sentiments.get("positive", 0) / total, 1),
        "negative_pct": round(100 * sentiments.get("negative", 0) / total, 1),
        "mixed_pct": round(100 * sentiments.get("mixed", 0) / total, 1),
        "neutral_pct": round(100 * sentiments.get("neutral", 0) / total, 1),
        "avg_likes": round(sum(likes) / total, 1),
        "top_themes": dict(themes.most_common(10)),
        "top_positive": [{"author": p.get("author"), "likes": p.get("likes"), "text": p.get("text", "")[:150]} for p in positive[:3]],
        "top_negative": [{"author": p.get("author"), "likes": p.get("likes"), "text": p.get("text", "")[:150]} for p in negative[:3]],
        "languages": dict(languages.most_common(10)),
    }

def format_report(topic, search_id, analysis):
    m = analysis["meta"]
    s = analysis["sentiment"]
    lines = [f"📊 **Recherche X : {topic}**", f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
             f"Posts: {m['total_posts']} | Auteurs: {m['unique_authors']} | Période: {m['date_from']} → {m['date_to']}", "", "**Sentiment:**"]
    for sent, label in [("positive","✅"),("negative","❌"),("neutral","⚪"),("mixed","🔀")]:
        if sent in s: lines.append(f"  {label} {sent}: {s[sent]['count']} posts (avg {s[sent]['avg_likes']} likes)")
    if analysis["themes"]:
        lines.append("\n**Thèmes:**")
        for theme, count in list(analysis["themes"].items())[:8]: lines.append(f"  • {theme}: {count} posts")
    if analysis["languages"]:
        lines.append("\n**Langues:**")
        for lang, count in list(analysis["languages"].items())[:5]:
            lines.append(f"  {lang}: {round(100*count/m['total_posts'])}%")
    if analysis["top_posts"]:
        lines.append("\n**Top posts par engagement:**")
        for i, p in enumerate(analysis["top_posts"][:5]):
            lines.append(f"  {i+1}. {p['author']} | {p['likes']} likes | {p['text'][:100]}...")
    return "\n".join(lines)
